"""The search server's call log, shown (decision 98.c, "line 2 visualises the server's call log"; 19.a): who asked what,
which pages answered, how long it took.

The log is the core's (`search_server.CALL_LOG`, git-ignored): one JSON record a line, read here as the core writes it and
split at '\n' only, since a JSON string may hold other line separators. A record names its tool, its state, its time, its
caller (`client`, from the MCP handshake; "chat" for the chat, "evaluation" for a measurement run, absent before 5 Nov),
what was asked, and the pages that answered: strings `knowledge_base:work:label` before 5 Nov, objects with the PDF page
since. An old string names no PDF page, so it opens no page view: never a guess. Nothing of a page's text is in the log.

Under `--public-only` a call is listed only where it can be told to concern the free knowledge base alone: every page it
answered with is free, it asked no licensed corpus, and any work it named is a free one. An old string record cannot be
told, so it is left out there. How many calls are left out is said.
"""

import json
import statistics
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

from backend.diagnostics import sources
from backend.diagnostics.readings import Count, Readings
from backend.diagnostics.search_hits import PageLink, page_links, work_sources
from backend.search import search_server

LOG = search_server.CALL_LOG
CALLS_SHOWN = 500  # the newest; older ones are counted, not listed
STATES = ('found', 'nothing found', 'declined', 'no image', 'error')  # the order states are counted in; others follow
NOT_NAMED = 'not named'  # a caller that gave no name, as every call before 5 Nov
NO_LOG = 'No call log on this machine: the search server writes it to logs/, which is local and not tracked.'


class AnsweredPage(BaseModel):
    knowledge_base: str | None
    work: str | None
    title: str | None  # the work's title, where the export holds the page
    label: str
    pdf: str | None  # None in a record from before 5 Nov, which named no PDF page
    view: PageLink | None


class AnsweredWork(BaseModel):
    """A work that answered a search over works (`search_works`, decision 124.a)."""

    knowledge_base: str | None
    work: str | None  # the search server's key
    source_id: str | None  # where this app holds the work's page readings: its page list opens
    title: str | None


class Call(BaseModel):
    at: str  # UTC
    tool: str
    state: str | None  # `works` answers with its list and no state
    ms: float | None
    client: str | None
    client_version: str | None
    query: str | None  # the question or keywords asked
    corpus: str | None
    hits: int | None
    work: str | None
    page: str | None
    answered: list[AnsweredPage]
    answered_works: list[AnsweredWork]  # a search over works answers with works, not pages
    # the words this call is filtered by, as the counts below name them: its tool, its state, its caller, the bases of
    # its answered pages and works ('none' where none answered)
    filtered_by: dict[str, list[str]]


class ToolFigures(BaseModel):
    tool: str
    calls: int
    median_ms: float | None
    states: list[Count]


class CallList(BaseModel):
    why_not: str | None = None  # no call log on this machine
    hidden: int = 0  # left out under --public-only: they concern the licensed base, or cannot be told
    older: int = 0  # listed calls older than the newest CALLS_SHOWN
    tools: list[ToolFigures] = []
    states: list[Count] = []
    clients: list[Count] = []
    knowledge_bases: list[Count] = []
    calls: list[Call] = []  # newest first


def records(path: Path) -> list[dict]:
    """Every readable record of the log, as written; a line that is not a record is passed over."""
    found = []
    for line in path.read_text(encoding='utf-8').split('\n'):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and isinstance(record.get('tool'), str):
            found.append(record)
    return found


def free_alone(record: dict, free_works: set[str]) -> bool:
    answered = (record.get('answered') or []) + (record.get('answered_works') or [])
    return (all(isinstance(item, dict) and item.get('knowledge_base') == 'free' for item in answered)
            and record.get('corpus') != 'licensed' and (not record.get('work') or record['work'] in free_works))


def answered_of(item: object, bases: dict[str, Readings], view_of) -> AnsweredPage | None:
    if isinstance(item, str):
        knowledge_base, _, rest = item.partition(':')
        work, _, label = rest.partition(':')
        return AnsweredPage(knowledge_base=knowledge_base or None, work=work or None, title=None, label=label or item, pdf=None,
                            view=None)
    if not isinstance(item, dict):
        return None
    pdf = None if item.get('pdf') is None else str(item['pdf'])
    knowledge_base, work = item.get('knowledge_base'), item.get('work')
    view = view_of(knowledge_base, work, pdf) if knowledge_base in bases and work else None
    return AnsweredPage(knowledge_base=knowledge_base, work=work, label=str(item.get('label', '')), pdf=pdf, view=view,
                        title=bases[knowledge_base].title(view.source_id) if view else None)


def work_of(item: dict, bases: dict[str, Readings], work_ids: dict[tuple[str, str], str]) -> AnsweredWork:
    knowledge_base, work = item.get('knowledge_base'), item.get('work')
    source_id = work_ids.get((knowledge_base, work)) if knowledge_base in bases and work else None
    return AnsweredWork(knowledge_base=knowledge_base, work=work, source_id=source_id,
                        title=bases[knowledge_base].title(source_id) if source_id else None)


def call_of(record: dict, bases: dict[str, Readings], view_of, work_ids: dict[tuple[str, str], str]) -> Call:
    answered = [page for page in (answered_of(item, bases, view_of) for item in record.get('answered') or []) if page]
    works = [work_of(item, bases, work_ids) for item in record.get('answered_works') or [] if isinstance(item, dict)]
    filtered_by = {'tool': [record['tool']], 'state': [record.get('state') or 'answered'],
                   'client': [record.get('client') or NOT_NAMED],
                   'kb': sorted({item.knowledge_base for item in [*answered, *works] if item.knowledge_base}) or ['none']}
    return Call(at=str(record.get('at', '')), tool=record['tool'], state=record.get('state'), ms=record.get('ms'),
                client=record.get('client'), client_version=record.get('client_version'), query=record.get('query'),
                corpus=record.get('corpus'), hits=record.get('hits'), work=record.get('work'),
                page=None if record.get('page') is None else str(record['page']), answered=answered, answered_works=works,
                filtered_by=filtered_by)


def counted(values: list[str], order: tuple[str, ...] = ()) -> list[Count]:
    rank = {value: at for at, value in enumerate(order)}
    return [Count(value=value, count=count) for value, count in
            sorted(Counter(values).items(), key=lambda pair: (rank.get(pair[0], len(rank)), -pair[1], pair[0]))]


def call_list(bases: dict[str, Readings], public_only: bool, path: Path | None = None) -> CallList:
    log = path or LOG
    if not log.exists():
        return CallList(why_not=NO_LOG)
    found = records(log)
    hidden = 0
    if public_only:
        free_works = {row['work'] for row in bases['free'].rows()} | {work.id for work in sources.works()}
        kept = [record for record in found if free_alone(record, free_works)]
        hidden, found = len(found) - len(kept), kept
    view_of, work_ids = page_links(bases), work_sources(bases)
    listed = sorted((call_of(record, bases, view_of, work_ids) for record in found), key=lambda call: call.at, reverse=True)
    by_tool: dict[str, list[Call]] = {}
    for call in listed:
        by_tool.setdefault(call.tool, []).append(call)
    tools = [ToolFigures(tool=tool, calls=len(calls),
                         median_ms=round(statistics.median(timed), 1) if (timed := [call.ms for call in calls if call.ms is not None]) else None,
                         states=counted([word for call in calls for word in call.filtered_by['state']], STATES))
             for tool, calls in sorted(by_tool.items(), key=lambda pair: -len(pair[1]))]

    def words(key: str) -> list[str]:
        return [word for call in listed for word in call.filtered_by[key]]

    return CallList(hidden=hidden, older=max(0, len(listed) - CALLS_SHOWN), tools=tools, states=counted(words('state'), STATES),
                    clients=counted(words('client')), knowledge_bases=counted(words('kb')), calls=listed[:CALLS_SHOWN])
