"""The shelf (decision 129.a): every work of both knowledge bases, how far it is converted, and why pages did not pass.

The shelf is the core's (`backend.search.shelf`), written by line 1 at milestones and only read here. Every count and the
share passed are the core's; nothing is counted again. A reason a page did not pass is, by construction, the route the
export wrote for that page (`served_readings.TEXT_LAYER_WHY[reason]`, pinned by a test in the core), so each reason's count
opens the work's pages filtered on that route: exactly the pages it counts. Under `--public-only` the licensed shelf is
never loaded (81.a); a machine where the shelf has not been built says how to build it.
"""

import hashlib

from pydantic import BaseModel

from backend.conversion.store.served_readings import TEXT_LAYER_WHY
from backend.diagnostics.readings import KnowledgeBase, Readings
from backend.search import shelf

BASES: tuple[KnowledgeBase, ...] = ('free', 'licensed')
NOT_READ = 'not read: the app was started with --public-only'
NOT_BUILT = ('No shelf on this machine yet: `python -m backend.search.shelf` builds it '
             '(`--public-only` for the free knowledge base alone).')


class Reason(BaseModel):
    reason: str  # blocked, refused, malformed, no_page, issue, stopped
    count: int
    route: str | None  # the work's pages on this route are the ones counted; None for a reason the core does not name


class Served(BaseModel):
    pages: int = 0
    searchable: int = 0
    from_readings: int = 0
    by_route: dict[str, int] = {}


class ShelfRow(BaseModel):
    knowledge_base: KnowledgeBase
    work: str | None  # the search server's key; None for a file no work serves
    title: str
    source_id: str | None  # the id this app's routes take
    file: str | None
    format: str
    pages: int | None
    planned: int | None
    read: int | None
    passed: int | None
    share_passed: float | None
    not_passed: list[Reason]
    served: Served
    unplaced: dict[str, int]  # passed readings the search does not serve, by why; "unexplained" would be a bug of the core
    unplaced_total: int  # their sum, so the view adds nothing up
    held: str | None
    not_served: str | None
    has_pages: bool  # the export holds this work's page readings, so its row opens its pages here


class ShelfBase(BaseModel):
    knowledge_base: KnowledgeBase
    why_not: str | None = None  # not read here, or not built on this machine
    built_at: str | None = None
    # whether the shelf was built from the export this app serves, by the sha256 of that export's index (line 1's
    # `export_sha256`); False where they part, so the counts and the pages a reason opens may disagree until a rebuild;
    # None where either side names none
    in_step: bool | None = None
    totals: dict[str, int | float] = {}  # counts, and since X1.a the shares of the planned pages
    works: list[ShelfRow] = []


class Shelf(BaseModel):
    bases: list[ShelfBase]


def row_of(item: dict, store: Readings | None) -> ShelfRow:
    return ShelfRow(
        knowledge_base=item['knowledge_base'], work=item.get('work'), title=item.get('title') or item.get('source_id') or '',
        source_id=item.get('source_id'), file=item.get('file'), format=item.get('format', ''), pages=item.get('pages'),
        planned=item.get('planned'), read=item.get('read'), passed=item.get('passed'), share_passed=item.get('share_passed'),
        not_passed=[Reason(reason=reason, count=count, route=TEXT_LAYER_WHY.get(reason))
                    for reason, count in (item.get('not_passed') or {}).items()],
        served=Served(**(item.get('served') or {})), unplaced=item.get('unplaced') or {},
        unplaced_total=sum((item.get('unplaced') or {}).values()), held=item.get('held'),
        not_served=item.get('not_served'),
        has_pages=bool(store and item.get('source_id') and store.work(item['source_id'])))


def shelf_of(bases: dict[str, Readings], public_only: bool) -> Shelf:
    listed = []
    for name in BASES:
        if public_only and name != 'free':
            listed.append(ShelfBase(knowledge_base=name, why_not=NOT_READ))
            continue
        data = shelf.load(name)
        if data is None:
            listed.append(ShelfBase(knowledge_base=name, why_not=NOT_BUILT))
            continue
        store = bases.get(name)
        served = hashlib.sha256(store.index.read_bytes()).hexdigest() if store and store.index.exists() else None
        built_from = data.get('export_sha256')
        listed.append(ShelfBase(knowledge_base=name, built_at=data.get('built_at'),
                                in_step=served == built_from if served and built_from else None, totals=data.get('totals') or {},
                                works=[row_of(item, store) for item in data.get('works') or []]))
    return Shelf(bases=listed)
