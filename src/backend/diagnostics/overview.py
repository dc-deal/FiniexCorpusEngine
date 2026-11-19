"""The overview, one corpus at a glance (the operator's O3.a, 19 Nov: "today there is only one corpus"), and the pages behind
every figure.

Every figure is counted here, never in the browser. A headline sums the knowledge bases served: the works, the pages
planned, those read and those that passed with their shares, the pages the search serves, from each base's shelf as the
core builds it, and the pages to look at and what the work cost, from each export; each figure keeps each base's part
beside it as its detail. Beneath it the corpus's history, a line per milestone the core recorded (X1.a), and the latest
runs of both bases, newest first, each marked with its base. A base not served is left out of every sum and says why:
under `--public-only` the licensed one is never read (81.a).

The overview counted every page by route, state, verdict, category, model and the integrity of its reading file in tables
until O3.a. Those counts stay reachable through the page list's filters (`pages`), each asked only when chosen; the
integrity of every reading file above all, which stat-ed some 10,200 files on each load (48.5 s in the container, 19 Nov).
"""

import threading
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from backend.diagnostics import page_integrity
from backend.diagnostics.readings import (LISTED_AS_ISSUE, IssueRow, KnowledgeBase, Readings, check_of, category_of,
                                          issue_row, listed_state, person_mark)
from backend.diagnostics.runs import RunLine, recent
from backend.search import shelf

BASES: tuple[KnowledgeBase, ...] = ('free', 'licensed')
RUNS_SHOWN = 8
NOT_READ = 'not read: the app was started with --public-only'
NO_EXPORT = 'no export of it on this machine'
NO_SHELF = 'no shelf built on this machine: `python -m backend.search.shelf` builds it'
NO_RUNS = 'No runs recorded on this machine: the pipeline database is local and not tracked.'
# the fields a page's work is paid for by, which the page list filters by: a reading's model, a judgement's, both by provider
PAID = frozenset({'reader', 'judge', 'provider'})


class Figure(BaseModel):
    """A headline figure: its sum over the knowledge bases it was counted in, and each base's part, the detail."""

    total: int
    by_base: dict[KnowledgeBase, int]


class Cost(BaseModel):
    """What every reading and judgement cost, retries included, in USD: its sum, each base's part, and each provider's over
    the bases, a cost the export does not give counted as none (line 1, 19 Nov: the per-model tables go, the providers stay
    in the figure's card)."""

    total: float
    by_base: dict[KnowledgeBase, float]
    by_provider: dict[str, float]


class LeftOut(BaseModel):
    """A knowledge base a sum leaves out, and why: not served, no export, or no shelf built here."""

    knowledge_base: KnowledgeBase
    why: str


class Shares(BaseModel):
    """A milestone's figures for one knowledge base, as the core kept them (X1.a): None where it kept none."""

    planned: int | None = None
    read: int | None = None
    passed: int | None = None
    share_passed: float | None = None
    served: int | None = None


class Milestone(BaseModel):
    """One line of the corpus's history (X1.a, line 1, 19 Nov): its date, its name, and its figures summed over the knowledge
    bases it holds that this app serves, each base's part beside them. A line taken over from the person's file before
    19 Nov holds both bases summed (`summed`, no parts), and is never shown under `--public-only`, as it holds licensed
    counts."""

    at: str  # YYYY-MM-DD
    # its name as line 1 wrote it; None under `--public-only`, as a name may name a licensed work (found 19 Nov: the newest
    # line named one), and nothing of the licensed base is shown there (81.a)
    milestone: str | None
    planned: int | None
    read: int | None
    passed: int | None
    share_passed: float | None  # passed of planned, 0 to 1
    served: int | None
    summed: bool  # both bases summed as taken over, so no part per base
    parts: dict[KnowledgeBase, Shares]


class Headline(BaseModel):
    """The corpus in one line: summed over the knowledge bases served, each base's part kept as the detail. The shelf's
    figures are summed over the bases whose shelf is built (`shelf_left_out` names the others); the export's over the
    bases served (`left_out`)."""

    bases: list[KnowledgeBase]  # the knowledge bases served, which every export figure sums
    left_out: list[LeftOut]  # a base not served, and why
    # from each base's shelf, the core's: works on the shelf, pages planned, passed and the search serves
    works: Figure | None
    planned: Figure | None
    read: Figure | None
    share_read: float | None  # read of planned over the summed shelves, 0 to 1, above 1 where pages were read outside the plan
    passed: Figure | None
    share_passed: float | None  # passed of planned over the summed shelves, 0 to 1; None without a page planned
    served: Figure | None
    shelf_left_out: list[LeftOut]
    # from each export: the pages the Issues list, and what all the readings and judgements cost
    to_look_at: Figure
    cost_usd: Cost


class Overview(BaseModel):
    headline: Headline
    history: list[Milestone]  # newest first; [] where no history is kept on this machine
    # the latest runs of both bases, newest first, each with its base; None where no base keeps a pipeline database here
    runs: list[RunLine] | None
    runs_why_not: str | None = None


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
    """The values a page has in a field, as the page list filters by it: one each, none for a verdict it lacks, each
    reason, model or provider once. A page's integrity is asked of its reading file in `export`, only when the filter is
    chosen; the file is hashed again only when its modification time or size changed (`page_integrity`)."""
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
        return [mark.standing] if (mark := person_mark(row)) and mark.by_a_person else []
    if field == 'review':  # an automated review's, never counted as a person's (the operator's 2.a, 18 Nov)
        return [mark.standing] if (mark := person_mark(row)) and not mark.by_a_person else []
    if field == 'why_judged':
        return [check.why_judged]
    if field == 'verdict':
        return [check.verdict.verdict] if check.verdict else []
    return sorted(set((row.get('check') or {}).get('reasons') or []))


@dataclass(frozen=True)
class Counted:
    """What an export's rows give the headline, counted once per state of the export."""

    works: int
    pages: int
    judged: int
    to_look_at: int
    cost_usd: float
    cost_by_provider: dict[str, float]


# one export's counts by its index file's modification time: the rows change only when the export is written again
_COUNTED: dict[Path, tuple[int, Counted]] = {}
_COUNTING = threading.Lock()


def counted(store: Readings) -> Counted:
    """The export's rows counted for the headline, again only after the export was written anew. The time is taken before
    the rows, so rows newer than it are counted again on the next call, never older rows kept as new."""
    modified = store.index.stat().st_mtime_ns if store.index.exists() else 0
    rows = store.rows()
    with _COUNTING:
        known = _COUNTED.get(store.index)
    if known is not None and known[0] == modified:
        return known[1]
    by_provider: dict[str, float] = {}
    for row in rows:
        for provider, value in paid_by('provider', row).items():
            by_provider[provider] = by_provider.get(provider, 0.0) + (value or 0.0)
    found = Counted(works=len({row['source_id'] for row in rows}), pages=len(rows),
                    judged=sum(1 for row in rows if (row.get('check') or {}).get('judged')),
                    to_look_at=sum(1 for row in rows if listed_state(row) in LISTED_AS_ISSUE), cost_usd=sum(by_provider.values()),
                    cost_by_provider=by_provider)
    with _COUNTING:
        _COUNTED[store.index] = (modified, found)
    return found


def summed(parts: dict[KnowledgeBase, int]) -> Figure:
    return Figure(total=sum(parts.values()), by_base=parts)


def latest_runs(served: list[KnowledgeBase]) -> list[RunLine] | None:
    """The latest runs of the bases served, newest first, both together; None where none keeps a pipeline database."""
    kept = [lines for name in served if (lines := recent(name, RUNS_SHOWN)) is not None]
    if not kept:
        return None
    return sorted((line for lines in kept for line in lines), key=lambda line: line.started_at, reverse=True)[:RUNS_SHOWN]


def overview(bases: dict[str, Readings], public_only: bool) -> Overview:
    """The overview: the export's figures counted once per state of each export (`counted`), the shelf's as the core last
    built each base's shelf, every figure summed over the bases it was counted in."""
    served = [name for name in BASES if name in bases]
    left_out = [LeftOut(knowledge_base=name, why=NOT_READ if public_only else NO_EXPORT) for name in BASES if name not in bases]
    exported = {name: counted(bases[name]) for name in served}
    shelves = {name: data.get('totals') or {} for name in served if (data := shelf.load(name)) is not None}
    shelf_left_out = [LeftOut(knowledge_base=name, why=NO_SHELF) for name in served if name not in shelves]

    def from_shelf(key: str) -> Figure | None:
        return summed({name: int(totals.get(key) or 0) for name, totals in shelves.items()}) if shelves else None

    planned, read, passed = from_shelf('planned'), from_shelf('read'), from_shelf('passed')
    headline = Headline(
        bases=served, left_out=left_out, works=from_shelf('works'), planned=planned, read=read,
        share_read=read.total / planned.total if planned and read and planned.total else None, passed=passed,
        share_passed=passed.total / planned.total if planned and passed and planned.total else None,
        served=from_shelf('served'), shelf_left_out=shelf_left_out,
        to_look_at=summed({name: found.to_look_at for name, found in exported.items()}),
        cost_usd=Cost(total=round(sum(found.cost_usd for found in exported.values()), 4),
                      by_base={name: round(found.cost_usd, 4) for name, found in exported.items()},
                      by_provider={provider: round(sum(found.cost_by_provider.get(provider, 0.0) for found in exported.values()), 4)
                                   for provider in sorted({name for found in exported.values() for name in found.cost_by_provider})}))
    runs = latest_runs(served)
    return Overview(headline=headline, history=milestones(served, public_only), runs=runs,
                    runs_why_not=NO_RUNS if runs is None else None)


def milestones(served: list[KnowledgeBase], public_only: bool) -> list[Milestone]:
    """The corpus's history as the core keeps it (`shelf.history`), newest first, each line summed over the bases it holds
    that this app serves. A line taken over summed (`both`) stands as it is, never under `--public-only`, and a line that
    holds none of the bases served is left out."""
    found = []
    for row in shelf.history().get('rows') or []:
        kept = row.get('bases') or {}
        name = None if public_only else row['milestone']
        if 'both' in kept:
            if public_only:
                continue
            both = Shares(**{field: kept['both'].get(field) for field in Shares.model_fields})
            found.append(Milestone(at=row['at'], milestone=name, summed=True, parts={}, **both.model_dump()))
            continue
        parts = {name: Shares(**{field: kept[name].get(field) for field in Shares.model_fields}) for name in served if name in kept}
        if not parts:
            continue

        def total(field: str) -> int | None:
            values = [getattr(part, field) for part in parts.values()]
            return None if any(value is None for value in values) else sum(values)

        planned, passed = total('planned'), total('passed')
        found.append(Milestone(at=row['at'], milestone=name, planned=planned, read=total('read'), passed=passed,
                               share_passed=round(passed / planned, 4) if planned and passed is not None else None,
                               served=total('served'), summed=False, parts=parts))
    return list(reversed(found))


FILTERS = ('knowledge_base', 'state', 'person', 'review', 'category', 'route', 'integrity', 'why_judged', 'verdict', 'reason', 'reader',
           'judge', 'provider')


def matches(row: dict, filters: dict[str, str], export: Path) -> bool:
    return all(filters[field] in values_of(field, row, export) for field in FILTERS[1:] if field in filters)


def pages(bases: dict[str, Readings], filters: dict[str, str]) -> PageList:
    """The pages a filter names: those of the knowledge bases served that match every filter given, by base, work and
    page. Each work's title is resolved once per list: asked per page, each asked for a stat of the export's index, 28,854
    of them for the unfiltered list, 114 s over the container's bind mount (O3.a, 19 Nov)."""
    chosen = {name: store for name, store in bases.items() if filters.get('knowledge_base') in (None, name)}
    found = sorted(((store, row) for store in chosen.values() for row in store.rows() if matches(row, filters, store.export)),
                   key=lambda pair: (pair[1]['knowledge_base'], pair[1]['source_id'], pair[1]['pdf_page']))
    titles = {(store.index, source_id): store.title(source_id)
              for store, source_id in {(store, row['source_id']) for store, row in found}}
    return PageList(filters=filters, rows=[issue_row(store, row, titles[(store.index, row['source_id'])]) for store, row in found])
