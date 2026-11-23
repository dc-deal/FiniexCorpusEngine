"""The Librarian page (the operator's L1.a, 21 Nov): what an MCP client gets from each of the librarian's tools, bare, for a
person and for debugging. It replaces the chat, which was built for the capstone's presentation.

Every call goes over MCP to the running librarian, never around it, so the page shows exactly what an IDE session gets,
errors included: the core's `mcp_client.SearchClient` over `mcp_client.http_server()` (LIBRARIAN_URL, in the container the
compose service's address, and the bearer token from .env). One session per process, opened on the page's first call under a
lock and kept, closed with the app; its calls name their client "view", so they stand apart in the call log. A librarian
that does not answer is said in words, and the next call tries again; a call that fails on its way closes the session, so
the next one opens it anew.

What the page draws is shaped here, so the view computes nothing: each tool's input schema as typed fields (a new tool or
argument appears by itself), its description and a line on cost and time taken from it, and each answer's parts for the
tool's own renderer (hits, works, contents, a page, an image), beside the answer as it came, the image's pixels left out.
"""

import os
import re
import threading
import time
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.diagnostics import code_works, work_editions

# the staggered order the server's instructions give (25b9fd3): from cheap and exact to costly and broad, then reading; the
# code catalog after the works it lists (#12, the server's instructions: the code part after `works` and its search tools)
TOOL_ORDER = ('works', 'search_works', 'code_catalog', 'search', 'semantic_search', 'toc', 'open_page', 'page_image')
# the two search tools as the view names them (the standing rule, dcd, 16 Nov): "search (BM25)" and "semantic (hybrid)"; their
# code names stay what a client calls, beside them in the tab's head, and in the address
LABELS = {'search': 'search (BM25)', 'semantic_search': 'semantic (hybrid)'}
# the view's own defaults where they differ from the server's: the operator wants the bare semantic search (S1.a, L1.a), so the
# router, a language model, runs only when a person ticks it; and its full answer (#14, line 1, 23 Nov): a client's is compact,
# without the candidate lists and each hit's citation and snippet, which the page's cards show, so the view asks for them,
# ticked in the form, and a person who unticks it sees exactly the compact answer a client gets
VIEW_DEFAULTS: dict[str, dict[str, Any]] = {'semantic_search': {'router': False, 'diagnostics': True}}
# the fields a person seldom fills, folded beneath the form under a title of their own: a caller's own translation
FOLDED: dict[str, tuple[str, tuple[str, ...]]] = {
    'semantic_search': ('your own translation, which spares the router', ('search_query', 'concept_query', 'keywords'))}
# the words of a description that say what a call costs and takes, in the order the description says them; "free" not where
# it names the free knowledge base
COST_WORDS = (r'\blocal\b', r'\bno model\b', r'\bmilliseconds\b', r'\bfree\b(?! one)(?! knowledge)', r'\babout two seconds\b',
              r'\ba paid API\b', r'\ba fraction of a cent\b')
IMAGE_TYPES = ('image/png', 'image/jpeg')
SENT_IMAGE = 'sent_image'  # the core's key for a call's image block (`mcp_client.SENT_IMAGE`)
# a page, a section, an article, or a code file with the lines a hit names (#12: `?lines=12-31`)
VIEW_ROUTE = re.compile(r'^/(free|licensed)/(sources|html|epub|code)/[^?#\s]+(\?lines=\d+-\d+)?$')
SWITCHED_OFF = 'The Librarian page calls nothing here: the app was started with --no-librarian.'
DOWN_AGAIN_SECONDS = 5.0  # a librarian found down is asked again no sooner, so a page's retries do not pile up sessions


class LibrarianDown(RuntimeError):
    """The librarian does not answer, in words: no session could be opened."""


class CallFailed(RuntimeError):
    """A call failed on its way, not in the tool: the session is closed and the next call opens it anew."""


class UnknownTool(LookupError):
    pass


class LibrarianField(BaseModel):
    """One argument of a tool, as its input schema gives it, for the form."""

    name: str
    kind: Literal['text', 'integer', 'number', 'boolean', 'list', 'choice']
    required: bool = False
    default: Any = None  # what the form starts with: the view's own default, else the server's
    server_default: Any = None
    choices: list[str] = []
    minimum: float | None = None
    maximum: float | None = None
    description: str | None = None
    folded: bool = False


class LibrarianTool(BaseModel):
    name: str  # what a client calls, and the address names
    label: str  # what its tab says: the name, or the view's name for a search tool
    description: str
    cost_said: str | None = None  # "local · no model · milliseconds · free", from the description's own words
    fields: list[LibrarianField] = []
    folded_title: str | None = None  # the title of the fold the `folded` fields stand in
    input_schema: dict[str, Any] = {}


class LibrarianInfo(BaseModel):
    enabled: bool
    url: str | None = None  # where the librarian is reached
    why_not: str | None = None  # switched off, or why it does not answer
    tools: list[LibrarianTool] = []


class CallRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    tool: str = Field(max_length=64)
    arguments: dict[str, Any] = {}


class CallHead(BaseModel):
    """The answer's head line: its state and words, relevance against its floor, how long it took, whether a model ran."""

    state: str | None = None
    said: str | None = None  # the server's why, error or note
    count: str | None = None  # "6 hits", "28 works", "41 entries"
    relevance: float | None = None
    relevance_floor: float | None = None
    below_floor: bool | None = None
    floor_said: str | None = None  # in the warning role where it lies below the floor
    seconds: float
    model_ran: bool = False
    model_said: str = 'no model'


class HitCard(BaseModel):
    rank: int
    knowledge_base: str | None = None
    work: str | None = None
    title: str | None = None
    edition_said: str | None = None
    page: str | None = None  # the label the tools take
    page_said: str | None = None  # "p. 456 (PDF p. 470)"
    section: str | None = None
    score: float | None = None
    snippet: str | None = None
    text: str | None = None  # semantic_search: the whole chunk
    route: str | None = None
    licence: str | None = None
    terms_missing: list[str] = []
    view: str | None = None  # the page in this view, from the hit's `view_url`
    kind: str | None = None  # 'text' or 'code' (#12); a code hit names its language and lines
    code_language: str | None = None
    lines: code_works.LineRange | None = None


class WorkRow(BaseModel):
    work: str
    title: str | None = None
    edition_said: str | None = None
    knowledge_base: str | None = None
    licence: str | None = None
    route: str | None = None
    pages: int | None = None
    subject: str | None = None
    kept_for: str | None = None
    pages_kept: int | None = None  # a kept edition's own pages, which open by its key and which the searches skip (#14)
    kept_editions: list[str] = []


class SectionHit(BaseModel):
    section: str | None = None
    page: str | None = None
    page_said: str | None = None
    score: float | None = None


class FoundWork(BaseModel):
    rank: int
    work: str
    title: str | None = None
    subject: str | None = None
    knowledge_base: str | None = None
    licence: str | None = None
    score: float | None = None
    pages_matching: int | None = None
    pages_with_every_term: int | None = None
    best_sections: list[SectionHit] = []


class TocEntry(BaseModel):
    level: int
    title: str
    page: str | None = None


class Contents(BaseModel):
    work: str | None = None
    title: str | None = None
    source: str | None = None
    left_out: int = 0
    entries: list[TocEntry] = []


class OpenedPage(BaseModel):
    work: str | None = None
    title: str | None = None
    edition_said: str | None = None
    knowledge_base: str | None = None
    page: str | None = None
    page_said: str | None = None
    section: str | None = None
    route: str | None = None
    licence: str | None = None
    text: str | None = None
    view: str | None = None
    kind: str | None = None  # 'code' for a source file (#12), drawn numbered
    code_language: str | None = None
    lines: code_works.LineRange | None = None


class CatalogUnit(BaseModel):
    """One unit `code_catalog` lists (#12): its file, what the core's catalog says of it, and its file in this view."""

    work: str
    page: str  # its file's label
    code_language: str | None = None
    companion_of: str | None = None
    view: str | None = None
    unit: code_works.CodeUnit


class CodeCatalog(BaseModel):
    total: int = 0
    categories: list[code_works.CategoryCount] = []  # the server's own count, the most first
    units: list[CatalogUnit] = []


class SentImage(BaseModel):
    src: str  # a data address, png or jpeg only
    described: list[tuple[str, str]] = []  # what the server says the image is, field by field
    page_said: str | None = None


class RouterPlan(BaseModel):
    """The plan the router made, where it ran."""

    search_query: str | None = None
    concept_query: str | None = None
    keywords: list[str] = []
    behaviour: str | None = None
    fell_back: bool | None = None


class LibrarianCall(BaseModel):
    tool: str
    arguments: dict[str, Any]
    head: CallHead
    hits: list[HitCard] | None = None
    works: list[WorkRow] | None = None
    found_works: list[FoundWork] | None = None
    contents: Contents | None = None
    catalog: CodeCatalog | None = None
    page: OpenedPage | None = None
    image: SentImage | None = None
    plan: RouterPlan | None = None
    answer: Any = None  # the answer as it came, the image's pixels left out


def cost_of(description: str) -> str | None:
    """What a call costs and takes, in the description's own words and order: "local · no model · milliseconds · free"."""
    # a sentence's capital dropped, an acronym's kept ("About" as "about", "API" as it is)
    found = sorted({(match.start(), match.group(0)[:1].lower() + match.group(0)[1:]) for pattern in COST_WORDS
                    for match in re.finditer(pattern, description, flags=re.IGNORECASE)})
    words = list(dict.fromkeys(word for _, word in found))
    return ' · '.join(words) or None


def field_of(name: str, spec: dict, required: bool, view_default: dict[str, Any], folded: tuple[str, ...]) -> LibrarianField:
    """One argument from its JSON schema: its kind from its type (an optional one's `anyOf` with null), its default, choices
    and bounds where the schema gives them."""
    options = [option for option in spec.get('anyOf', [spec]) if option.get('type') != 'null'] or [spec]
    first = options[0]
    choices = [str(choice) for choice in first.get('enum') or spec.get('enum') or []]
    kind = 'choice' if choices else {'boolean': 'boolean', 'integer': 'integer', 'number': 'number',
                                      'array': 'list'}.get(first.get('type'), 'text')
    server_default = spec.get('default')
    return LibrarianField(name=name, kind=kind, required=required, server_default=server_default,
                          default=view_default.get(name, server_default), choices=choices,
                          minimum=first.get('minimum'), maximum=first.get('maximum'),
                          description=spec.get('description'), folded=name in folded)


def tool_of(tool: Any) -> LibrarianTool:
    """A tool the server lists, for its tab."""
    schema = dict(tool.input_schema or {})
    required = set(schema.get('required') or [])
    folded_title, folded = FOLDED.get(tool.name, (None, ()))
    fields = [field_of(name, spec, name in required, VIEW_DEFAULTS.get(tool.name, {}), folded)
              for name, spec in (schema.get('properties') or {}).items()]
    description = tool.description or ''
    return LibrarianTool(name=tool.name, label=LABELS.get(tool.name, tool.name), description=description,
                         cost_said=cost_of(description), fields=fields,
                         folded_title=folded_title if folded else None, input_schema=schema)


def in_order(tools: list[Any]) -> list[Any]:
    """The tools in the server's staggered order; one it lists beyond them after, in its own order."""
    rank = {name: at for at, name in enumerate(TOOL_ORDER)}
    return sorted(tools, key=lambda tool: rank.get(tool.name, len(TOOL_ORDER)))


def view_of(view_url: Any) -> str | None:
    """The page a `view_url` names, as a route of this view, so it opens here whatever address the server links: the part
    after its '#', and only a route to a page, a section or an article."""
    if not isinstance(view_url, str) or '#' not in view_url:
        return None
    route = view_url.split('#', 1)[1]
    return route if VIEW_ROUTE.match(route) else None


def page_said(page: Any) -> str | None:
    """A page as a citation gives it, both numbers where both are known: "p. 456 (PDF p. 470)"."""
    if not isinstance(page, dict):
        return str(page) if page else None
    pdf, printed, label = page.get('pdf'), page.get('printed'), page.get('label')
    if pdf and printed and str(printed) != str(pdf):
        return f'p. {printed} (PDF p. {pdf})'
    if pdf:
        return f'PDF p. {pdf}'
    return str(label) if label else None


def label_of(page: Any) -> str | None:
    return str(page.get('label')) if isinstance(page, dict) and page.get('label') is not None else (str(page) if page else None)


def counted(count: int, word: str, words: str | None = None) -> str:
    """A count and its word, the plural where it is not one: "1 hit", "41 entries"."""
    return f"{count:,} {word if count == 1 else words or word + 's'}"


def head_of(tool: str, answer: Any, seconds: float) -> CallHead:
    """The answer's head line, in the server's fields and words."""
    if not isinstance(answer, dict):
        return CallHead(seconds=seconds)
    listed = answer.get('result') if tool == 'works' else None
    state = answer.get('state') or ('found' if isinstance(listed, list) else None)
    counts = {'hits': ('hit', 'hits'), 'works': ('work', 'works'), 'entries': ('entry', 'entries'), 'units': ('unit', 'units')}
    count = next((counted(len(answer[key]), *words) for key, words in counts.items() if isinstance(answer.get(key), list)
                  and state == 'found'), None)
    if isinstance(listed, list):
        count = counted(len(listed), 'work')
    said = answer.get('why') or answer.get('error') or answer.get('note')
    relevance, floor, below = answer.get('relevance'), answer.get('relevance_floor'), answer.get('below_floor')
    floor_said = None
    if below is True:
        floor_said = (f'below the floor ({relevance:.3f} < {floor:.3f}): the books likely say nothing on this'
                      if isinstance(relevance, (int, float)) and isinstance(floor, (int, float))
                      else 'below the floor: the books likely say nothing on this')
    elif below is False and isinstance(relevance, (int, float)) and isinstance(floor, (int, float)):
        floor_said = f'above the floor ({relevance:.3f} ≥ {floor:.3f})'
    model = ((answer.get('usage') or {}).get('router') or {}).get('model') if isinstance(answer.get('usage'), dict) else None
    model_said = f'a model ran: {model}' if model else ('no model ran' if tool == 'semantic_search' else 'no model')
    return CallHead(state=state, said=str(said) if said else None, count=count,
                    relevance=relevance if isinstance(relevance, (int, float)) else None,
                    relevance_floor=floor if isinstance(floor, (int, float)) else None,
                    below_floor=below if isinstance(below, bool) else None, floor_said=floor_said, seconds=round(seconds, 3),
                    model_ran=bool(model), model_said=model_said)


def hits_of(answer: dict) -> list[HitCard] | None:
    hits = answer.get('hits')
    if not isinstance(hits, list):
        return None
    return [HitCard(rank=at, knowledge_base=hit.get('knowledge_base'), work=hit.get('work'), title=hit.get('title'),
                    edition_said=work_editions.words(hit.get('edition'), hit.get('year')), page=label_of(hit.get('page')),
                    page_said=page_said(hit.get('page')), section=hit.get('section'), score=hit.get('score'),
                    snippet=hit.get('snippet'), text=hit.get('text'), route=hit.get('route'), licence=hit.get('licence'),
                    terms_missing=list(hit.get('terms_missing') or []), view=view_of(hit.get('view_url')),
                    kind=hit.get('kind'), code_language=hit.get('code_language'), lines=lines_of(hit.get('lines')))
            for at, hit in enumerate((one for one in hits if isinstance(one, dict)), 1)]


def lines_of(lines: Any) -> code_works.LineRange | None:
    """A code page's lines as the server gives them, `{first, last}`; None where it gives none."""
    if isinstance(lines, dict) and isinstance(lines.get('first'), int) and isinstance(lines.get('last'), int):
        return code_works.LineRange(first=lines['first'], last=lines['last'])
    return None


def catalog_of(answer: dict) -> CodeCatalog:
    """`code_catalog`'s answer: its units, each as the code work's page shows it, and its count by category."""
    counts = sorted(((str(key), value) for key, value in (answer.get('categories') or {}).items() if isinstance(value, int)),
                    key=lambda pair: (-pair[1], pair[0]))
    return CodeCatalog(total=int(answer.get('total') or 0),
                       categories=[code_works.CategoryCount(category=category, units=count) for category, count in counts],
                       units=[CatalogUnit(work=str(unit.get('work')), page=str(unit.get('page')),
                                          code_language=unit.get('code_language'), companion_of=unit.get('companion_of'),
                                          view=view_of(unit.get('view_url')), unit=code_works.unit_of(unit))
                              for unit in answer.get('units') or [] if isinstance(unit, dict) and unit.get('page')])


def works_of(listed: list) -> list[WorkRow]:
    return [WorkRow(work=str(work.get('work')), title=work.get('title'),
                    edition_said=work_editions.words(work.get('edition'), work.get('year')),
                    knowledge_base=work.get('knowledge_base'), licence=work.get('licence'), route=work.get('route'),
                    pages=work.get('pages'), subject=work.get('subject'), kept_for=work.get('kept_for'),
                    pages_kept=work.get('pages_kept'), kept_editions=list(work.get('kept_editions') or []))
            for work in listed if isinstance(work, dict)]


def found_works_of(found: list) -> list[FoundWork]:
    return [FoundWork(rank=at, work=str(work.get('work')), title=work.get('title'), subject=work.get('subject'),
                      knowledge_base=work.get('knowledge_base'), licence=work.get('licence'), score=work.get('score'),
                      pages_matching=work.get('pages_matching'), pages_with_every_term=work.get('pages_with_every_term'),
                      best_sections=[SectionHit(section=section.get('section'), page=label_of(section.get('page')),
                                                page_said=page_said(section.get('page')), score=section.get('score'))
                                     for section in work.get('best_sections') or [] if isinstance(section, dict)])
            for at, work in enumerate((one for one in found if isinstance(one, dict)), 1)]


def image_of(answer: dict) -> SentImage | None:
    """A page image the server sent, as a data address, png or jpeg only and its data base64 alone; and what it is."""
    image = answer.get(SENT_IMAGE)
    if not (isinstance(image, dict) and image.get('mime_type') in IMAGE_TYPES and isinstance(image.get('data'), str)
            and re.fullmatch(r'[A-Za-z0-9+/]+={0,2}', image['data'])):
        return None
    described = answer.get('image') if isinstance(answer.get('image'), dict) else {}
    return SentImage(src=f"data:{image['mime_type']};base64,{image['data']}", page_said=page_said(answer.get('page')),
                     described=[(str(key), str(value)) for key, value in described.items()])


def bare(answer: Any) -> Any:
    """The answer as it came, the image's pixels left out: they stand above it as the image."""
    if isinstance(answer, dict) and isinstance(answer.get(SENT_IMAGE), dict):
        image = answer[SENT_IMAGE]
        data = image.get('data')
        return {**answer, SENT_IMAGE: {**image, 'data': f'<{len(data):,} base64 characters, shown as the image>'
                                       if isinstance(data, str) else data}}
    return answer


def shaped(tool: str, arguments: dict, answer: Any, seconds: float) -> LibrarianCall:
    """An answer as the page draws it: its head, its tool's parts, and the answer as it came."""
    call = LibrarianCall(tool=tool, arguments=arguments, head=head_of(tool, answer, seconds), answer=bare(answer))
    if not isinstance(answer, dict):
        return call
    if tool == 'works' and isinstance(answer.get('result'), list):
        call.works = works_of(answer['result'])
    elif tool == 'search_works' and isinstance(answer.get('works'), list):
        call.found_works = found_works_of(answer['works'])
    elif tool == 'code_catalog' and isinstance(answer.get('units'), list):
        call.catalog = catalog_of(answer)
    elif tool == 'toc' and isinstance(answer.get('entries'), list):
        call.contents = Contents(work=answer.get('work'), title=answer.get('title'), source=answer.get('source'),
                                 left_out=answer.get('left_out') or 0,
                                 entries=[TocEntry(level=int(entry.get('level') or 1), title=str(entry.get('title') or ''),
                                                   page=entry.get('page'))
                                          for entry in answer['entries'] if isinstance(entry, dict)])
    elif tool == 'open_page' and answer.get('state') == 'found':
        call.page = OpenedPage(work=answer.get('work'), title=answer.get('title'),
                               edition_said=work_editions.words(answer.get('edition'), answer.get('year')),
                               knowledge_base=answer.get('knowledge_base'), page=label_of(answer.get('page')),
                               page_said=page_said(answer.get('page')), section=answer.get('section'),
                               route=answer.get('route'), licence=answer.get('licence'), text=answer.get('text'),
                               view=view_of(answer.get('view_url')), kind=answer.get('kind'),
                               code_language=answer.get('code_language'), lines=lines_of(answer.get('lines')))
    elif tool == 'page_image':
        call.image = image_of(answer)
    else:
        call.hits = hits_of(answer)
    plan = answer.get('plan')
    if isinstance(plan, dict) and plan.get('translated_by') == 'the router':
        call.plan = RouterPlan(search_query=plan.get('search_query'), concept_query=plan.get('concept_query'),
                               keywords=list(plan.get('keywords') or []), behaviour=answer.get('behaviour'),
                               fell_back=plan.get('fell_back'))
    return call


def leaf(error: BaseException) -> BaseException:
    """The error itself, out of the task groups the SDK's transport wraps it in."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return error


def librarian_url() -> str:
    from backend.chat import mcp_client

    return os.environ.get(mcp_client.LIBRARIAN_URL_ENV) or mcp_client.DEFAULT_LIBRARIAN_URL


def default_client() -> Any:
    """One session with the running librarian over HTTP, its calls named "view"."""
    from backend.chat import mcp_client

    return mcp_client.SearchClient(mcp_client.http_server(), client_name='view')


class LibrarianService:
    """The page's one session with the librarian, opened on the first call and kept; None as the factory switches it off."""

    def __init__(self, factory: Callable[[], Any] | None, url: Callable[[], str] = librarian_url,
                 clock: Callable[[], float] = time.monotonic):
        self._factory = factory
        self._url = url
        self._clock = clock
        self._client: Any = None
        self._open = threading.Lock()
        self._down: tuple[float, str] | None = None  # when it was last found down, and why

    @property
    def enabled(self) -> bool:
        return self._factory is not None

    def _session(self) -> Any:
        with self._open:
            if self._client is not None:
                return self._client
            if self._down and self._clock() - self._down[0] < DOWN_AGAIN_SECONDS:
                raise LibrarianDown(self._down[1])
            try:
                self._client = self._factory()
            except Exception as error:  # noqa: BLE001 — any failure to open is the librarian's not answering, said in words
                found = leaf(error)
                said = f'The librarian does not answer at {self._url()}: {type(found).__name__}: {found}'[:600]
                self._down = (self._clock(), said)
                raise LibrarianDown(said) from error
            self._down = None
            return self._client

    def info(self) -> LibrarianInfo:
        if not self.enabled:
            return LibrarianInfo(enabled=False, why_not=SWITCHED_OFF)
        try:
            client = self._session()
        except LibrarianDown as down:
            return LibrarianInfo(enabled=True, url=self._url(), why_not=str(down))
        return LibrarianInfo(enabled=True, url=self._url(), tools=[tool_of(tool) for tool in in_order(client.server_tools)])

    def call(self, tool: str, arguments: dict) -> LibrarianCall:
        client = self._session()
        if tool not in {offered.name for offered in client.server_tools}:
            raise UnknownTool(f'The librarian offers no tool {tool!r}.')
        started = time.perf_counter()
        try:
            answer = client.call(tool, arguments)
        except Exception as error:  # noqa: BLE001 — the transport or the session failed, not the tool: said, and opened anew
            self.close()
            found = leaf(error)
            raise CallFailed(f'The call failed on its way: {type(found).__name__}: {found}'[:600]) from error
        return shaped(tool, arguments, answer, time.perf_counter() - started)

    def close(self) -> None:
        with self._open:
            client, self._client = self._client, None
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001 — closing: whatever the session ended with is no longer anyone's concern
                pass
