"""The whole pipeline at a glance, the knowledge bases side by side (the operator, 2026-11-05), and the pages behind every figure.

Every figure is counted here, from the exports, the search index and the pipeline databases, never in the browser. The
overview has a headline per knowledge base (works, pages, judged, pages to look at, cost, latest runs) and sections in
which each value stands once, with its count in each knowledge base beside it (the operator's 16.a), so nothing is labelled twice.
A section names the field it counts, the page list filters by that field, and so every count of pages opens the pages it
counts. Under the headlines stands which model did what (the operator's 17.a): the pages each reader and judge worked on, by model
and by provider, and what that work cost. A knowledge base this app does not serve says why: under `--public-only` the
licensed one is never read (81.a).
"""

import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from backend.diagnostics import page_integrity
from backend.diagnostics.readings import (LISTED_AS_ISSUE, STATE_ORDER, IssueRow, KnowledgeBase, Readings, check_of,
                                          category_of, issue_row, listed_state, person_mark)
from backend.diagnostics.runs import RunLine, recent
from backend.diagnostics.search_hits import Search

BASES: tuple[KnowledgeBase, ...] = ('free', 'licensed')
RUNS_SHOWN = 8
# The sections, in the order they stand: their title and the field of a page each one counts.
SECTIONS = (('How the text is made', 'route'), ('State', 'state'), ("A person's verdict", 'person'),
            ('Page category', 'category'),
            ('Is the reading what was checked', 'integrity'),
            ('Why judged, or why not', 'why_judged'), ("The judge's verdicts", 'verdict'), ('Reasons a page carries', 'reason'))
# Which model did what (the operator's 17.a): the pages each one worked on, and what that work cost.
MODEL_SECTIONS = (('Readings by model', 'reader'), ('Judgements by model', 'judge'),
                  ('By provider, readings and judgements', 'provider'))
PAID = frozenset(field for _, field in MODEL_SECTIONS)


class BaseHeadline(BaseModel):
    knowledge_base: KnowledgeBase
    served: bool
    why_not: str | None = None  # why a knowledge base is not served: never read, or no export on this machine
    works: int = 0  # the works its export holds page readings of: read page by page
    pages: int = 0  # the pages read: every row of the export
    # What the search serves of it, every route counted (an HTML source, legacy Markdown, a text layer), as the search
    # server's start banner counts it (the operator's 1.a): the banner said 15 works where the tile said 11, both right. None while
    # the index is still being built.
    served_works: int | None = None
    served_pages: int | None = None
    judged: int = 0
    to_look_at: int = 0  # the pages the Issues list
    # what every reading of the pages and every judgement of them cost, retries included: the provider box's sum
    cost_usd: float = 0.0
    runs: list[RunLine] | None = None  # the latest runs, newest first; None where this machine keeps no pipeline database


class SectionRow(BaseModel):
    """One value of a section's field, with its count in each knowledge base; None where it does not occur there."""

    value: str
    free: int | None
    licensed: int | None


class Section(BaseModel):
    title: str
    field: str  # the page list's filter that opens the pages behind each count
    linked: bool  # the search's counts have no page list behind them
    note: str | None = None  # why a section has no rows yet
    rows: list[SectionRow]


class ModelRow(SectionRow):
    """A model or a provider: the pages it worked on in each knowledge base and what all its work on them cost, retries
    included. A cost is None where it did not work there, or where the export gives no cost."""

    free_usd: float | None
    licensed_usd: float | None


class ModelSection(Section):
    rows: list[ModelRow]


class Overview(BaseModel):
    """The overview in its bands (the operator's 18.a): the key figures, which model did what, the pages through the pipeline,
    what the search holds; the latest runs stand with each base's key figures."""

    bases: list[BaseHeadline]
    models: list[ModelSection]
    sections: list[Section]  # the pages through the pipeline
    search: Section


class PageList(BaseModel):
    filters: dict[str, str]
    rows: list[IssueRow]


def reader_of(attempt: dict) -> str:
    """A reading's model, with the upstream that served it where it went through OpenRouter."""
    return f"{attempt['model']} · {attempt['upstream']}" if attempt.get('upstream') else attempt['model']


def add(paid: dict[str, float | None], value: str | None, cost: float | None) -> None:
    """Adds a cost to a value's sum; the sum stays None only while no cost of it is known."""
    if value is None:
        return
    known = paid.get(value)
    paid[value] = cost if known is None else known + (cost or 0.0)


def paid_by(field: str, row: dict) -> dict[str, float | None]:
    """What a page's work cost, per model or provider: each reading by its model and upstream, the judgement by its
    model, both by their provider."""
    judge = (row.get('check') or {}).get('judge')
    paid: dict[str, float | None] = {}
    if field in ('reader', 'provider'):
        for attempt in row.get('attempts') or []:
            add(paid, reader_of(attempt) if field == 'reader' else attempt.get('provider'), attempt.get('cost_usd'))
    if judge and field in ('judge', 'provider'):
        add(paid, judge['model'] if field == 'judge' else judge.get('provider'), judge.get('cost_usd'))
    return paid


def values_of(field: str, row: dict, export: Path | None = None) -> list[str]:
    """The values a page has in a field: one each, none for a verdict it lacks, each reason, model or provider once. A
    page's integrity is asked of its reading file in `export` on every count, so a file changed a moment ago counts; it is
    hashed again only when its modification time or size changed (`page_integrity`)."""
    if field in PAID:
        return sorted(paid_by(field, row))
    if field == 'integrity':
        return [page_integrity.state(export, row)] if export else []
    check = check_of(row)
    if field == 'route':
        return [row['route']]
    if field == 'state':  # as the lists count it: a page a person settled in its own bucket (211.a)
        return [listed_state(row)]
    if field == 'category':  # what kind of page it is (172.a)
        return [category_of(row)]
    if field == 'person':  # a person's standing verdict on the reading shown (166.a)
        return [mark.standing] if (mark := person_mark(row)) else []
    if field == 'why_judged':
        return [check.why_judged]
    if field == 'verdict':
        return [check.verdict.verdict] if check.verdict else []
    return sorted(set((row.get('check') or {}).get('reasons') or []))


def merged(field: str, counts: dict[str, Counter]) -> list[SectionRow]:
    """Each value once, its count per knowledge base beside it: states in their one order, the rest by their total."""
    values = set().union(*(counter.keys() for counter in counts.values())) if counts else set()
    rank = {state: at for at, state in enumerate(STATE_ORDER)}

    def order(value: str):
        if field == 'state':
            return (rank.get(value, len(rank)), value)
        return (-sum(counter.get(value, 0) for counter in counts.values()), value)

    return [SectionRow(value=value, **{name: counts[name].get(value) if name in counts else None for name in BASES})
            for value in sorted(values, key=order)]


def spent(field: str, rows: list[dict]) -> dict[str, float | None]:
    """What every model or provider's work on these pages cost."""
    total: dict[str, float | None] = {}
    for row in rows:
        for value, cost in paid_by(field, row).items():
            add(total, value, cost)
    return total


def model_rows(field: str, counts: dict[str, Counter], costs: dict[str, dict]) -> list[ModelRow]:
    return [ModelRow(**row.model_dump(), **{f'{name}_usd': None if costs.get(name, {}).get(row.value) is None
                                            else round(costs[name][row.value], 4) for name in BASES})
            for row in merged(field, counts)]


@dataclass(frozen=True)
class Counted:
    """What an export's rows give the overview apart from their integrity, counted once per state of the export."""

    counts: dict[str, Counter]
    costs: dict[str, dict[str, float | None]]
    works: int
    pages: int
    judged: int
    to_look_at: int


# one export's counts by its index file's modification time: the rows change only when the export is written again
_COUNTED: dict[Path, tuple[int, Counted]] = {}
_COUNTING = threading.Lock()
STABLE_FIELDS = tuple(field for _, field in MODEL_SECTIONS + SECTIONS if field != 'integrity')


def counted(store: Readings) -> Counted:
    """The export's rows counted in every field but integrity, again only after the export was written anew. The time is
    taken before the rows, so rows newer than it are counted again on the next call, never older rows kept as new."""
    modified = store.index.stat().st_mtime_ns if store.index.exists() else 0
    rows = store.rows()
    with _COUNTING:
        known = _COUNTED.get(store.index)
    if known is not None and known[0] == modified:
        return known[1]
    found = Counted(counts={field: Counter(value for row in rows for value in values_of(field, row)) for field in STABLE_FIELDS},
                    costs={field: spent(field, rows) for field in PAID}, works=len({row['source_id'] for row in rows}),
                    pages=len(rows), judged=sum(1 for row in rows if (row.get('check') or {}).get('judged')),
                    to_look_at=sum(1 for row in rows if listed_state(row) in LISTED_AS_ISSUE))
    with _COUNTING:
        _COUNTED[store.index] = (modified, found)
    return found


def overview(bases: dict[str, Readings], search: Search, public_only: bool) -> Overview:
    """The overview, counted from the exports: their rows once per state of each export (`counted`), every page's integrity
    on every call, from a stat unless the file changed (`page_integrity`), so a reading file changed a moment ago counts."""
    fields = [field for _, field in MODEL_SECTIONS + SECTIONS]
    headlines, counts, costs = [], {field: {} for field in fields}, {field: {} for field in PAID}
    service = search.ready()
    # what the search serves, counted exactly as `search_server.banner` counts it, so a tile and the banner never part
    served_pages = None if service is None else Counter(page.knowledge_base for page in service.index.pages)
    served_works = None if service is None else Counter(work.knowledge_base for work in service.works.values())
    for name in BASES:
        if name not in bases:
            why = 'not read: the app was started with --public-only' if public_only else 'no export of it on this machine'
            headlines.append(BaseHeadline(knowledge_base=name, served=False, why_not=why))
            continue
        store = bases[name]
        known = counted(store)
        for field in STABLE_FIELDS:
            counts[field][name] = known.counts[field]
        counts['integrity'][name] = Counter(value for row in store.rows() for value in values_of('integrity', row, store.export))
        for field in PAID:
            costs[field][name] = known.costs[field]
        cost_usd = sum(cost or 0.0 for cost in costs['provider'][name].values())
        headlines.append(BaseHeadline(
            knowledge_base=name, served=True, works=known.works, pages=known.pages,
            served_works=None if served_works is None else served_works[name],
            served_pages=None if served_pages is None else served_pages[name],
            judged=known.judged, to_look_at=known.to_look_at, cost_usd=round(cost_usd, 4), runs=recent(name, RUNS_SHOWN)))
    sections = [Section(title=title, field=field, linked=True, rows=merged(field, counts[field])) for title, field in SECTIONS]
    indexed = {} if service is None else {
        name: Counter(page.route for page in service.index.pages if page.knowledge_base == name) for name in bases}
    searched = Section(title='In the search, every medium', field='route', linked=False, rows=merged('route', indexed),
                       note=None if service else 'The search index is still being built; it counts here once it stands.')
    models = [ModelSection(title=title, field=field, linked=True, rows=model_rows(field, counts[field], costs[field]))
              for title, field in MODEL_SECTIONS]
    return Overview(bases=headlines, models=models, sections=sections, search=searched)


FILTERS = ('knowledge_base', 'state', 'person', 'category', 'route', 'integrity', 'why_judged', 'verdict', 'reason', 'reader',
           'judge', 'provider')


def matches(row: dict, filters: dict[str, str], export: Path) -> bool:
    return all(filters[field] in values_of(field, row, export) for field in FILTERS[1:] if field in filters)


def pages(bases: dict[str, Readings], filters: dict[str, str]) -> PageList:
    """The pages every figure counts: those of the knowledge bases served that match every filter given, by base, work
    and page."""
    chosen = {name: store for name, store in bases.items() if filters.get('knowledge_base') in (None, name)}
    found = sorted(((store, row) for store in chosen.values() for row in store.rows() if matches(row, filters, store.export)),
                   key=lambda pair: (pair[1]['knowledge_base'], pair[1]['source_id'], pair[1]['pdf_page']))
    return PageList(filters=filters, rows=[issue_row(store, row) for store, row in found])
