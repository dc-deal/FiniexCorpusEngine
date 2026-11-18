"""What a tool of the search server learns about its caller from the MCP SDK (mcp 2.3.0), pinned because decision 99.a rests
on it: the client's name and version arrive in both protocol eras, and a session id only over HTTP with the 2025-11-25
handshake, since a 2026-07-28 request is a connection of its own. Measured first on 2026-11-05 with a probe server; this keeps
the measurement, through the server's own `caller_of`, should an update of the SDK change it."""

import asyncio
import json
import socket
import threading
import time

import mcp
import mcp.types as types
import pytest
from mcp.server.mcpserver import Context, MCPServer

from backend.search import search_server

CHAT = types.Implementation(name='chat', version='0.1.0')
NAMED = {'client': 'chat', 'client_version': '0.1.0', 'session': None}


def probe() -> MCPServer:
    server = MCPServer('probe')

    @server.tool()
    def who(*, ctx: Context) -> dict:
        """Who asked."""
        return search_server.caller_of(ctx)

    return server


async def asked_twice(target, **options) -> list[dict]:
    async with mcp.Client(target, client_info=CHAT, **options) as client:
        return [json.loads((await client.call_tool('who', {})).content[0].text) for _ in range(2)]


@pytest.mark.parametrize('mode', ['auto', 'legacy'])
def test_in_process_a_client_is_named_and_has_no_session(mode):
    assert asyncio.run(asked_twice(probe(), mode=mode)) == [NAMED, NAMED]


@pytest.fixture
def over_http():
    import uvicorn

    with socket.socket() as free:
        free.bind(('127.0.0.1', 0))
        port = free.getsockname()[1]
    web = uvicorn.Server(uvicorn.Config(probe().streamable_http_app(), host='127.0.0.1', port=port, log_level='warning'))
    thread = threading.Thread(target=web.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not web.started:
        assert time.monotonic() < deadline, 'the HTTP server did not start'
        time.sleep(0.05)
    yield f'http://127.0.0.1:{port}/mcp'
    web.should_exit = True
    thread.join(timeout=10)


def test_over_http_a_2025_handshake_has_a_session_of_its_own(over_http):
    first, second = asyncio.run(asked_twice(over_http, mode='legacy')), asyncio.run(asked_twice(over_http, mode='legacy'))
    assert first[0]['session'] and first[0] == first[1] and first[0]['client'] == 'chat'
    assert second[0]['session'] and second[0]['session'] != first[0]['session']


def test_over_http_a_2026_request_is_named_and_has_no_session(over_http):
    assert asyncio.run(asked_twice(over_http)) == [NAMED, NAMED]


def test_over_http_a_2026_request_with_a_session_header_of_its_own_still_has_none(over_http):
    # Such a request passes no session manager, so its header is the client's word (the review of 99.a forged one).
    import httpx

    body = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'who', 'arguments': {}, '_meta': {
        'io.modelcontextprotocol/protocolVersion': '2026-07-28', 'io.modelcontextprotocol/clientCapabilities': {},
        'io.modelcontextprotocol/clientInfo': {'name': 'chat', 'version': '0.1.0'}}}}
    headers = {'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'tools/call',
               'Mcp-Name': 'who', 'Mcp-Session-Id': 'forged-by-the-client'}
    text = httpx.post(over_http, json=body, headers=headers, timeout=30).text
    if 'data:' in text:  # an SSE frame
        text = next(line[5:].strip() for line in text.split('\n') if line.startswith('data:'))
    assert json.loads(json.loads(text)['result']['content'][0]['text']) == NAMED


# The chat's own transport in production: it starts the server over stdio. The probe runs as a subprocess, as an MCP host
# starts a server; in-process clients take another path through the SDK (the review of 99.a).
STDIO_PROBE = ("from mcp.server.mcpserver import Context, MCPServer\n"
               "from backend.search import search_server\n"
               "server = MCPServer('probe')\n"
               "@server.tool()\n"
               "def who(*, ctx: Context) -> dict:\n"
               "    '''Who asked.'''\n"
               "    return search_server.caller_of(ctx)\n"
               "server.run()\n")


@pytest.mark.parametrize('mode', ['auto', 'legacy'])
def test_over_stdio_a_client_is_named_and_has_no_session(mode):
    import sys

    probe_server = mcp.StdioServerParameters(command=sys.executable, args=['-c', STDIO_PROBE], cwd=str(search_server.REPO))
    assert asyncio.run(asked_twice(probe_server, mode=mode)) == [NAMED, NAMED]
