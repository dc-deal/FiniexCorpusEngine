"""The chat as a client of the search server over MCP (decision 98.c): one retrieval, and the chat its control tool.

The chat no longer searches by itself. It talks to the search server the way an IDE session does, through the official SDK's
`mcp.Client`: by default it launches the server as a subprocess over stdio, as an MCP host would, so a clone needs nothing
running; in tests it connects to a server object in-process. Every tool the server offers becomes a LangChain tool for the
chat's agent, and the knowledge turn takes its passages from the server's `semantic_search`.

LangChain's own adapter was checked first: `langchain-mcp-adapters` 0.3.2 requires `mcp` below 2, and pip's dry run would
replace our `mcp` 2.3.0 with 1.30.0, which has no `MCPServer`, so the server itself would stop working. The few lines that turn
a server's tools into LangChain tools are therefore written here.

A chat turn calls tools synchronously, and an MCP session lives in an event loop whose task must open and close it.
The session therefore runs in one task of a background thread's loop, and each call is handed to that task and waited for.

    client = SearchClient()                      # launches `python -m backend.search.search_server` over stdio
    client.call('semantic_search', {'question': 'what is a bond discount?'})
    client.tools()                               # the server's tools as LangChain tools
"""

import asyncio
import base64
import concurrent.futures
import json
import sys
import threading
from pathlib import Path

import mcp
from langchain_core.tools import StructuredTool

REPO = Path(__file__).resolve().parents[3]
START_SECONDS = 120  # the server builds its keyword index when it starts (about 7 s here), and a cold machine is slower
CALL_SECONDS = 180  # a semantic search routes the question through a model first
SENT_IMAGE = 'sent_image'  # where a call's image block lands in its answer


def client_info(name: str = 'chat') -> mcp.types.Implementation:
    """How the chat names itself to the server, so its calls stand apart from an IDE session's in the server's console and call
    log (decision 99.a); without it the SDK sends its own default, 'mcp'. An evaluation run names itself 'evaluation', so its
    questions are never taken for a user's."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        installed = version('trading-knowledge-base')
    except PackageNotFoundError:  # run from a checkout without `pip install -e .`
        installed = '0'
    return mcp.types.Implementation(name=name, version=installed)


def stdio_server(public_only: bool = False, frozen_plans: Path | None = None) -> mcp.StdioServerParameters:
    """The search server as a subprocess of the chat, started the way an MCP host starts it; `frozen_plans` for evaluation
    runs only."""
    return mcp.StdioServerParameters(command=sys.executable, cwd=str(REPO),
                                     args=['-m', 'backend.search.search_server', *(['--public-only'] if public_only else []),
                                           *(['--frozen-plans', str(frozen_plans)] if frozen_plans else [])])


class SearchClient:
    """One session with the search server, held in a background thread; `call` and the tools are synchronous."""

    def __init__(self, server=None, call_seconds: float = CALL_SECONDS, client_name: str = 'chat'):
        self._server = server if server is not None else stdio_server()
        self._call_seconds = call_seconds
        self._client_name = client_name
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name='mcp-search-client', daemon=True)
        self._thread.start()
        self._requests: asyncio.Queue | None = None
        self._tools = concurrent.futures.Future()
        self._session = asyncio.run_coroutine_threadsafe(self._serve(), self._loop)
        self.server_tools = self._tools.result(timeout=START_SECONDS)

    async def _serve(self) -> None:
        self._requests = asyncio.Queue()
        try:
            async with mcp.Client(self._server, read_timeout_seconds=self._call_seconds,
                                  client_info=client_info(self._client_name)) as client:
                self._tools.set_result((await client.list_tools()).tools)
                while True:
                    name, arguments, answer = await self._requests.get()
                    if name is None:
                        return
                    try:
                        answer.set_result(await client.call_tool(name, arguments))
                    except Exception as error:  # the caller gets it; the session goes on
                        answer.set_exception(error)
        except Exception as error:
            if not self._tools.done():
                self._tools.set_exception(error)
            raise

    def call(self, name: str, arguments: dict) -> dict:
        """One tool call: the server's JSON answer as a dict, and an image, where it sends one, as base64 under 'sent_image'.

        Not under 'image': `page_image` already answers with an `image` key, the description of what it sends."""
        answer = concurrent.futures.Future()
        self._loop.call_soon_threadsafe(self._requests.put_nowait, (name, arguments, answer))
        result = answer.result(timeout=self._call_seconds)
        texts, image = [], None
        for block in result.content:
            if block.type == 'text':
                try:
                    texts.append(json.loads(block.text))
                except json.JSONDecodeError:
                    texts.append(block.text)
            elif block.type == 'image':
                image = {'mime_type': block.mime_type, 'data': block.data}
        # A list the server returns comes as one text block per item, and as {'result': [...]} in the structured content
        # (`works`); one JSON object comes as one text block (`search`, `semantic_search`, a page image's description).
        if isinstance(result.structured_content, dict):
            payload = dict(result.structured_content)
        else:
            payload = texts[0] if len(texts) == 1 and isinstance(texts[0], dict) else {'result': texts}
        if image is not None:
            payload[SENT_IMAGE] = image
        if result.is_error:
            payload.setdefault('state', 'error')
        return payload

    def tools(self) -> list[StructuredTool]:
        """Every tool the server offers, as a LangChain tool with the server's own name, description and argument schema.

        The model gets the server's JSON as text; an image comes back as an artifact for the interface, never into the
        model's context."""
        def bound(name: str):
            def run(**arguments) -> tuple[str, dict]:
                payload = self.call(name, {key: value for key, value in arguments.items() if value is not None})
                visible = {key: value for key, value in payload.items() if key != SENT_IMAGE}
                return json.dumps(visible, ensure_ascii=False), payload
            return run

        return [StructuredTool.from_function(func=bound(tool.name), name=tool.name, description=tool.description or tool.name,
                                             args_schema=tool.input_schema, response_format='content_and_artifact')
                for tool in self.server_tools]

    def close(self) -> None:
        if self._requests is not None:
            self._loop.call_soon_threadsafe(self._requests.put_nowait, (None, None, None))
        try:
            self._session.result(timeout=10)
        except Exception:  # closing: whatever the session ended with is no longer anyone's concern
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)


def image_bytes(payload: dict) -> bytes | None:
    """The image a `page_image` call sent, as bytes for the interface; None when there is none, or when the answer comes from
    the turn log, which keeps an image's type and size but not its pixels."""
    image = payload.get(SENT_IMAGE)
    return base64.b64decode(image['data']) if image and image.get('data') else None
