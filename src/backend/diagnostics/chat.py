"""The chat in this app (decision 100.a): one route that asks the core's chat agent and returns its turn.

It is the one route here that spends money, so it is guarded three ways: it answers only a request addressed to this
machine by name (127.0.0.1 or localhost, against a page elsewhere reaching it through DNS rebinding), it takes a JSON
body only (so a form on another site cannot send one without the browser's preflight, which this app never grants), and
the start command can switch it off, as the browser check does, so no test reaches a model.

The agent is the core's `ChatAgent`, unchanged. One is built per process on the first message, under a lock, so two first
messages never start two search servers; it is closed when the app shuts down. One turn runs at a time: the agent's MCP
session is serial anyway, and one conversation must never run two turns at once. Each conversation's turn log path is set
once, at its first turn, by the core's `turn_log.conversation_log`, so the monitoring reads it as one conversation. What the
route returns is the turn as the log stores it (`turn_log.stored`) with the pixels kept, minus the agent's own words, which
are never shown; it adds only where the diagnostics shows a cited page, by the same lookup as the search (V4).
"""

import re
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from mcp.shared.exceptions import MCPError
from pydantic import BaseModel, ConfigDict, Field, computed_field

from backend.chat import app_config, turn_log
from backend.diagnostics import work_editions
from backend.diagnostics.readings import Readings
from backend.diagnostics.search_hits import ArticleLink, PageLink, article_links, page_links

MESSAGE_LIMIT = 10_000  # the chat refuses more than 2,000 characters itself; this bounds what reaches its log
NEVER_SHOWN = ('agent_text', 'discarded_text')  # the agent's own words beside a tool's answer: kept in the log, never shown
IMAGE_TYPES = ('image/png', 'image/jpeg')
LOCAL_HOSTS = ('127.0.0.1', 'localhost', '::1')
SWITCHED_OFF = 'The chat is switched off in this app: it was started with --no-chat.'
# The chat's own search server runs with --public-only (decision 81.a): every page it cites is of the free knowledge base.
CHAT_BASE = 'free'


class ChatUnavailable(RuntimeError):
    """The chat agent cannot be built here, in the core's own words (a missing key, for one)."""


class Loose(BaseModel):
    """A part of the core's turn: the fields the view reads are typed, every other one passes through as it came."""

    model_config = ConfigDict(extra='allow')


class Citation(Loose):
    text: str = ''
    link: str | None = None
    licence: str | None = None


class CitedPage(Loose):
    label: str | None = None
    pdf: str | None = None
    printed: str | None = None


class Source(Loose):
    number: int
    work: str | None = None
    page: CitedPage | None = None
    citation: Citation = Citation()
    view: PageLink | None = None  # the page view of the passage's page, where the export holds a reading of it
    article: ArticleLink | None = None  # the article view of the passage's HTML section (164.a)


class Quote(Loose):
    passage: int  # the number of the source it is quoted from
    text: str  # verified word for word against its passage: shown as text, never as Markdown
    citation: Citation = Citation()
    view: PageLink | None = None
    article: ArticleLink | None = None


class KnowledgeTurn(Loose):
    behaviour: str
    answer: str = ''  # Markdown
    quotes: list[Quote] = []
    sources: list[Source] = []
    gaps: str | None = None
    follow_up: str | None = None
    disclaimer: str | None = None
    relevance: float | None = None  # the best passage's similarity, as the search measured it
    relevance_floor: float | None = None
    below_floor: bool | None = None  # the core's word that the best passage lies under the floor: a near miss, not a hit


class Hit(Loose):
    knowledge_base: str | None = None
    work: str | None = None
    title: str | None = None
    page: CitedPage | None = None
    section: str | None = None
    snippet: str | None = None
    view: PageLink | None = None
    edition: str | None = None  # the catalog's edition ("2nd") and year, as the search names them (E1.a)
    year: int | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def edition_said(self) -> str | None:
        """The edition its citation names beside the title (E1.a): "2nd edition, 2003", or the year alone."""
        return work_editions.words(self.edition, self.year)


class ServerAnswer(Loose):
    state: str | None = None  # absent for `works`, whose answer is its list
    hits: list[Hit] | None = None
    title: str | None = None
    page: CitedPage | str | None = None  # a plain label where nothing was found
    text: str | None = None  # an opened page, word for word
    why: str | None = None
    error: str | None = None
    result: list[Any] | None = None
    edition: str | None = None  # an opened page's edition and year (E1.a)
    year: int | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def edition_said(self) -> str | None:
        """The edition its citation names beside the title (E1.a): "2nd edition, 2003", or the year alone."""
        return work_editions.words(self.edition, self.year)


class ServerTurn(Loose):
    tool: str
    args: dict[str, Any] = {}
    answer: ServerAnswer = ServerAnswer()
    image_src: str | None = None  # a page image the server sent, as a data address; png or jpeg only


class SecurityCheck(Loose):
    check: str
    name: str
    status: str
    detail: str = ''


class ChatResult(Loose):
    kind: str
    turn_id: str
    question: str
    text: str = ''  # Markdown: a calculation's, written by code; a refusal's
    disclaimer: str | None = None
    turn: KnowledgeTurn | None = None
    server: ServerTurn | None = None
    usd: float | None = None
    seconds: float = 0.0
    model_calls: int = 0
    call_limit_reached: str | None = None
    security: list[SecurityCheck] = []
    logged: bool = True  # whether the turn reached its conversation's turn log


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    message: str = Field(max_length=MESSAGE_LIMIT)
    thread_id: uuid.UUID  # a conversation's id, also part of its log's file name: nothing else gets through


class ChatInfo(BaseModel):
    enabled: bool
    why_not: str | None
    examples: list[str]  # the chat's example questions, as every interface shows them


def local_host_only(request: Request) -> None:
    """Refuses a request not addressed to this machine by name: a page elsewhere must not reach the route that spends."""
    host = request.headers.get('host', '')
    name = host[1:host.index(']')] if host.startswith('[') and ']' in host else host.split(':')[0]
    if name not in LOCAL_HOSTS:
        raise HTTPException(403, 'The chat answers only requests addressed to this machine (127.0.0.1 or localhost).')


def default_agent() -> Any:
    """The core's chat agent, imported only when the first message needs it."""
    from backend.chat.chat_agent import ChatAgent
    from backend.providers import anthropic_client, openrouter_client

    try:
        return ChatAgent()
    except (openrouter_client.MissingApiKeyError, anthropic_client.MissingApiKeyError) as error:
        raise ChatUnavailable(str(error)) from error


def shaped(result: dict, view_of: Callable[[str, str, str | None], PageLink | None],
           article_of: Callable[[str, str | None, str | None], ArticleLink | None] = lambda *_: None) -> dict:
    """The turn as the view takes it: without the agent's own words, each cited page with its page view where there is
    one, each cited HTML section with its article view (164.a), a quote with its passage's, a page image as one data
    address instead of its fields."""
    shown = {name: value for name, value in result.items() if name not in NEVER_SHOWN}
    turn = shown.get('turn')
    if isinstance(turn, dict):
        sources = [{**source, 'view': view_of(CHAT_BASE, source.get('work'), (source.get('page') or {}).get('pdf')),
                    'article': article_of(CHAT_BASE, source.get('work'), (source.get('page') or {}).get('label'))}
                   for source in turn.get('sources') or []]
        views = {source.get('number'): (source['view'], source['article']) for source in sources}
        quotes = [{**quote, 'view': views.get(quote.get('passage'), (None, None))[0],
                   'article': views.get(quote.get('passage'), (None, None))[1]} for quote in turn.get('quotes') or []]
        shown['turn'] = {**turn, 'sources': sources, 'quotes': quotes}
    server = shown.get('server')
    if isinstance(server, dict) and isinstance(server.get('answer'), dict):
        answer = dict(server['answer'])
        if isinstance(answer.get('hits'), list):
            answer['hits'] = [{**hit, 'view': view_of(hit.get('knowledge_base') or CHAT_BASE, hit.get('work'),
                                                      (hit.get('page') or {}).get('pdf') if isinstance(hit.get('page'), dict) else None)}
                              for hit in answer['hits'] if isinstance(hit, dict)]
        image = answer.pop('sent_image', None)
        image_src = None
        if (isinstance(image, dict) and image.get('mime_type') in IMAGE_TYPES and isinstance(image.get('data'), str)
                and re.fullmatch(r'[A-Za-z0-9+/]+={0,2}', image['data'])):
            image_src = f"data:{image['mime_type']};base64,{image['data']}"
        shown['server'] = {**server, 'answer': answer, 'image_src': image_src}
    return shown


def failed(error: Exception) -> str:
    """A failed turn in one sentence: the error's kind and its own words, never a trace."""
    return f'The turn failed: {type(error).__name__}: {error}'[:500]


class ChatService:
    """One chat agent for this process, built on the first message and closed with the app; one turn at a time."""

    def __init__(self, factory: Callable[[], Any] | None, bases: dict[str, Readings]):
        self._factory = factory  # None: the chat is switched off
        self._bases = bases
        self._agent: Any = None
        self._build = threading.Lock()
        self._turn = threading.Lock()
        self._logs: dict[str, Path] = {}  # each conversation's turn log, set at its first turn

    @property
    def enabled(self) -> bool:
        return self._factory is not None

    def info(self) -> ChatInfo:
        return ChatInfo(enabled=self.enabled, why_not=None if self.enabled else SWITCHED_OFF,
                        examples=app_config.load()['answer']['examples'])

    def _agent_now(self) -> Any:
        with self._build:
            if self._agent is None:
                self._agent = self._factory()
            return self._agent

    def ask(self, message: str, thread_id: str) -> ChatResult:
        agent = self._agent_now()
        with self._turn:
            try:
                result = agent.ask(message, thread_id)
            except (MCPError, TimeoutError):
                # the search server is gone or stuck, and nothing restarts it: the next message builds a new agent
                self.close()
                raise
            logged = True
            try:
                if thread_id not in self._logs:
                    self._logs[thread_id] = turn_log.conversation_log(thread_id)
                turn_log.write(result, thread_id, self._logs[thread_id])
            except (OSError, ValueError):
                logged = False  # the answer stands even when its log could not be written
            shown = shaped(turn_log.stored(result, keep_pixels=True), page_links(self._bases), article_links())
            return ChatResult.model_validate({**shown, 'logged': logged})

    def close(self) -> None:
        with self._build:
            if self._agent is not None:
                agent, self._agent = self._agent, None
                agent.close()
