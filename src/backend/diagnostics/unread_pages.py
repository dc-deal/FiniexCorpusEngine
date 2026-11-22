"""Every PDF page of a work that no reader has read yet (the operator's V1.b, 20 Nov): a work's page list shows each PDF page,
not only those with a reading, and one line above it says how many are read and what serves the rest.

What serves a page without a reading is the librarian's rule (`search_server.licensed_pages`), asked here of the data that rule
is built from, never of the librarian itself, which builds every licensed page to answer (183.7 s natively, 20 Nov):
- a licensed work with page-numbered legacy Markdown (`search_server.legacy_fallback_pages`) serves that Markdown where it has
  the page and nothing where it has not, since its PDF's text layer never stands in for it (`search_server.with_readings`);
- any other PDF serves its text layer where the page has text, and nothing on a page without (a scan, a blank page).
Measured against the librarian's own pages on 20 Nov: every unread licensed page was served as this rule says, and the rule
first proposed, the text layer wherever no Markdown has the page, would have named it for a legacy work's pages the Markdown
leaves out, which the librarian serves nothing for. A PDF beside an EPUB or a stand-in that serves its work would serve
nothing, which the rule does not see; no exported work is one today.

A licensed page is planned where the rollout's plan holds it (`rollout.FOLDER / 'plan.json'`) or a session's list of pages to
read (`reading_cells.DIRECT_PAGES`, why 'unread'); a free page where the corpus cell reads its work whole or a session's list
holds it (`reading_cells.free_planned_pages`). Any other free PDF is planned nowhere: a NoDerivatives work is never read
(72.a), and a work taken in later serves its text layer until its reading is decided (line 1, 22 Nov: the view called every
unread free page planned, the FIX specification's among them).

Each unread page stands as a row of the export's shape in a state of its own, `not_read`, so the summary, the routes, the
chapters and the facet bar count it as they count a read page; it has no reading to open and no image. It is built once per
state of the export, the PDF, the legacy pages and the plans, and the legacy pages once per state of the licensed export
(15.8 s natively, warmed at the app's start). The licensed knowledge base is never read under --public-only, and neither is
anything here of it.

Whether a page has a text layer is the one question asked of the PDF itself, and the start command's app keeps the answers on
disk, in each knowledge base's working folder, by file and for as long as the PDF's stamp holds (`TextLayers`, line 1's 1.d,
22 Nov): asked anew of every unread page of every PDF at each start, it took 187 s of a 265 s warm-up in the container. A
test's app keeps them in memory alone, so no test reads or writes this machine's.
"""

import json
import os
import sys
import threading
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pymupdf
from pydantic import BaseModel

from backend.configuration import data_paths
from backend.conversion.store import served_readings
from backend.diagnostics import stamps

UNREAD = 'not_read'  # the state of a page without a reading: its own and quiet, since nothing is wrong with it
UNREAD_LEVEL = 'not read'  # its route level, beside the core's three (`served_readings.ROUTE_LEVELS`)
UNREAD_LEVEL_SAYS = ("a PDF page no reader has read yet: the IDE's legacy Markdown serves it where it has the page, else the "
                     "PDF's text layer where the page has text, else nothing")
NOTHING = 'nothing served'
NOTHING_ROUTE = f'{NOTHING}: the page has no reading'
WHY_JUDGED = 'not read: no reader has read this page yet'

ServedBy = Literal['legacy markdown', 'text layer', 'nothing']
# the route an unread page is served by: the core's own words for a page without a reading (`served_readings.route_of(None)`
# and its legacy twin), and where nothing serves it, words in the same shape
ROUTES: dict[str, str] = {served_readings.LEGACY_ROUTE: served_readings.LEGACY_WHY['unread'],
                          served_readings.TEXT_LAYER: served_readings.TEXT_LAYER_WHY['unread'], 'nothing': NOTHING_ROUTE}
SERVERS = {served_readings.LEGACY_ROUTE: "the IDE's Markdown", served_readings.TEXT_LAYER: "the PDF's text layer"}


class UnreadPart(BaseModel):
    """The unread pages of a work one thing serves."""

    served_by: ServedBy
    pages: int


class Coverage(BaseModel):
    """A PDF work's pages: how many are read, what serves the rest, and how many of those are planned, said in one line."""

    pdf_pages: int
    read: int  # the pages the export has a row of: a reader was sent each, whatever came back
    unread: list[UnreadPart]  # the Markdown first, then the text layer, then nothing; only what serves a page
    planned: int  # of the unread pages, those a plan holds
    said: str


def served_said(served_by: str, legacy_work: bool) -> str:
    """What serves an unread page, in a page list's Why: where nothing does, why not."""
    if served_by == 'nothing':
        return f"{NOTHING}: the IDE's Markdown has no such page" if legacy_work else f'{NOTHING}: the page has no text layer'
    return f'served from {SERVERS[served_by]}'


def coverage_said(pdf_pages: int, read: int, parts: list[UnreadPart], planned: int) -> str:
    """'120 of 300 PDF pages read; the other 180 are served from the IDE's Markdown', split where more than one thing serves
    them, and how many of them are planned."""
    said = f"{read:,} of {pdf_pages:,} PDF {'page' if pdf_pages == 1 else 'pages'} read"
    unread = sum(part.pages for part in parts)
    if not unread:
        return said
    other = 'the other one' if unread == 1 else f'the other {unread:,}'
    serving = [part for part in parts if part.served_by != 'nothing']
    nothing = sum(part.pages for part in parts if part.served_by == 'nothing')
    if len(parts) == 1:
        part = parts[0]
        said += (f'; nothing serves {other}' if part.served_by == 'nothing'
                 else f"; {other} {'is' if unread == 1 else 'are'} served from {SERVERS[part.served_by]}")
    else:
        froms = [f"{part.pages:,} {'is' if part.pages == 1 else 'are'} served from {SERVERS[part.served_by]}" if at == 0
                 else f'{part.pages:,} from {SERVERS[part.served_by]}' for at, part in enumerate(serving)]
        said += f"; of {other}, {' and '.join(froms)}" + (f'; nothing serves {nothing:,}' if nothing else '')
    if planned == unread:
        said += '; it is planned' if unread == 1 else '; every one of them is planned'
    elif planned:
        said += f"; {planned:,} of them {'is' if planned == 1 else 'are'} planned"
    return said


_GUARD = threading.Lock()
_LEGACY: dict[tuple, dict[str, set[int]]] = {}
_PLANNED: dict[tuple, set[tuple[str, int]]] = {}
_FREE_PLANNED: dict[tuple, set[tuple[str, int]]] = {}
_NOT_SERVED: dict[tuple, dict[str, str]] = {}


def stamp(path: Path) -> stamps.Stamp | None:
    """A file's modification time and size, looked at once a request (`stamps`); None where it does not exist."""
    return stamps.stamp(path)


def legacy_pages() -> dict[str, set[int]]:
    """PDF file -> the pages its legacy Markdown serves, the librarian's own (`search_server.legacy_fallback_pages`), once per
    state of the licensed export, which names the same fallback in its rows: 15.8 s natively."""
    from backend.diagnostics import readings
    from backend.search import search_server

    state = (stamp(readings.LICENSED_EXPORT / 'index.json'),)
    with _GUARD:  # one build at a time: a request during the warm-up waits for it rather than building again
        if state not in _LEGACY:
            _LEGACY.clear()
            _LEGACY[state] = search_server.legacy_fallback_pages()
        return _LEGACY[state]


def planned_pages() -> set[tuple[str, int]]:
    """(file, PDF page) of every licensed page a plan holds: the rollout's plan and a session's pages to read, once per state
    of the two. The free base asks `free_planned_pages`."""
    from backend.conversion.reading import reading_cells, rollout

    plan, direct = rollout.FOLDER / 'plan.json', reading_cells.DIRECT_PAGES['licensed']
    state = (stamp(plan), stamp(direct))
    with _GUARD:
        if state not in _PLANNED:
            found = set()
            if plan.exists():
                found |= {(entry['file'], entry['pdf_page']) for entry in json.loads(plan.read_text(encoding='utf-8'))['order']}
            if direct.exists():
                found |= {(page['file'], page['pdf_page']) for page in json.loads(direct.read_text(encoding='utf-8')).get('pages', [])
                          if page.get('why') == 'unread'}
            _PLANNED.clear()
            _PLANNED[state] = found
        return _PLANNED[state]


def free_planned_pages() -> set[tuple[str, int]]:
    """(file, PDF page) of every free page a plan holds, the core's own (`reading_cells.free_planned_pages`): every page of the
    works the corpus cell reads whole and a session's pages to read, once per state of the cell's page list and the session's.
    The free PDFs are unmodified copies, so their stamps are not asked (line 1, 22 Nov)."""
    from backend.conversion.reading import reading_cells

    source, direct = Path(reading_cells.CORPUS_CELLS['FREE-SM'].page_source), reading_cells.DIRECT_PAGES['free']
    state = (stamp(source), stamp(direct))
    with _GUARD:
        if state not in _FREE_PLANNED:
            _FREE_PLANNED.clear()
            _FREE_PLANNED[state] = reading_cells.free_planned_pages()
        return _FREE_PLANNED[state]


WHOLE_LEGACY = 'whole legacy'  # a file's work served by its legacy Markdown whole, which names no PDF page (U1.a)
WHOLE_LEGACY_SAID = "served from the IDE's Markdown, whose text names no PDF page and stands for the whole work"


@lru_cache(maxsize=2)
def shelf_path(knowledge_base: str = 'licensed') -> Path:
    """Where a knowledge base's shelf lies, asked of its store once: opening the store calls git, and a page list and the
    Sources list ask for the shelf's state on every call."""
    from backend.conversion.store.reading_store import open_store
    from backend.search import shelf

    return open_store(knowledge_base).path('reports', shelf.SHELF)


def not_served_files() -> dict[str, str]:
    """Source id -> how the librarian serves a file other than page by page, as the licensed shelf last said it (U1.a), once
    per state of the shelf; {} where the shelf is not built here. Its why where it serves the file not at all (a file held
    back that belongs to no work, a stand-in beside the legacy text that stands); `WHOLE_LEGACY` where the work's legacy
    Markdown serves it and names no PDF page, so it stands whole (`search_server.with_readings`) and is in no page map."""
    from backend.diagnostics import readings
    from backend.search import shelf

    path = shelf_path('licensed')

    legacy = legacy_pages()  # before the guard, which it takes itself
    state = (stamp(path), stamp(readings.LICENSED_EXPORT / 'index.json'))  # the shelf's, and the legacy pages'
    with _GUARD:
        if state not in _NOT_SERVED:
            data = shelf.load('licensed') or {}
            _NOT_SERVED.clear()
            _NOT_SERVED[state] = {row['source_id']: row['not_served'] or WHOLE_LEGACY for row in data.get('works') or []
                                  if row.get('source_id') and (row.get('not_served') or (
                                      row.get('format') == 'pdf' and row.get('file') not in legacy
                                      and served_readings.LEGACY_ROUTE in ((row.get('served') or {}).get('by_route') or {})))}
        return _NOT_SERVED[state]


TEXT_LAYERS_ABOUT = ("Which pages of each PDF have a text layer, for the diagnostics view's pages without a reading "
                     "(line 1's 1.d, 22 Nov): by file, kept while the PDF's stamp (modified in nanoseconds, size) holds. "
                     "Derived: deleting it costs one slow start.")


def text_layers_file(knowledge_base: str) -> Path:
    """Where a knowledge base's text layers are kept: its working folder, on this machine alone (274.a)."""
    working = data_paths.LICENSED_WORKING if knowledge_base == 'licensed' else data_paths.FREE_WORKING
    return working / 'diagnostics' / 'text_layers.json'


class TextLayers:
    """Which pages of each PDF have a text layer, the one question a page without a reading asks of its PDF, kept by file
    while the PDF's stamp holds: a page is opened with pymupdf only where no entry of that stamp knows it. With a `path` the
    answers are read from it at the first question and written to it whole after each PDF that taught something new; without,
    they live as long as this object. Built here rather than taken from a library: `diskcache` and `joblib.Memory` key by
    arguments and cannot tell that a PDF changed, nor add the pages a later question asks to what an earlier one learned."""

    def __init__(self, path: Path | None):
        self.path = path
        self._entries: dict[str, dict] | None = None
        self._lock = threading.Lock()
        self._said = False

    def _load(self) -> dict[str, dict]:
        if self._entries is None:
            self._entries = {}
            if self.path is not None and self.path.exists():
                try:
                    self._entries = dict(json.loads(self.path.read_text(encoding='utf-8')).get('pdfs') or {})
                except (OSError, ValueError, AttributeError, TypeError):  # a damaged file is built anew
                    self._entries = {}
        return self._entries

    def _save(self) -> None:
        """Written whole through a file of this process's own beside it, so a reader never sees half of it; where the folder
        cannot be written, the answers stay in memory, said once."""
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            part = self.path.with_name(f'{self.path.name}.{os.getpid()}.part')
            part.write_text(json.dumps({'about': TEXT_LAYERS_ABOUT, 'pdfs': self._entries}, separators=(',', ':')),
                            encoding='utf-8')
            part.replace(self.path)
        except OSError as error:
            if not self._said:
                print(f'the text layers stay in memory: {error}', file=sys.stderr, flush=True)
                self._said = True

    def pages(self, pdf: Path, file: str, read: set[int], needs_text: bool) -> tuple[int, set[int]]:
        """The PDF's page count and, of its pages not in `read`, those with a text layer; none asked where `needs_text` is
        False (a work its legacy Markdown or nothing serves). The PDF is opened only where the count or one of those pages is
        not known for its stamp, and then outside the lock, so a question about another PDF never waits for it."""
        found = stamp(pdf)
        held = list(found) if found else None
        with self._lock:
            entry = self._load().get(file)
        known = entry is not None and entry.get('stamp') == held
        count: int | None = entry['pages'] if known else None
        text: set[int] = set(entry['text']) if known else set()
        none: set[int] = set(entry['none']) if known else set()

        def wanted(pages: int) -> list[int]:
            return [number for number in range(1, pages + 1)
                    if needs_text and number not in read and number not in text and number not in none]

        if count is None or wanted(count):
            with pymupdf.open(pdf) as document:
                count = document.page_count
                for number in wanted(count):
                    (text if document[number - 1].get_text().strip() else none).add(number)
            with self._lock:
                self._load()[file] = {'stamp': held, 'pages': count, 'text': sorted(text), 'none': sorted(none)}
                self._save()
        return count, (text - read) if needs_text else set()


def units_at(outline: list[dict] | None, pdf_page: int) -> list[str] | None:
    """The units a page without a reading lies in, by the outline's ranges: each deepest unit whose pages hold it, in reading
    order, two where one ends and the next begins on it. The export's own units of a read page come from where its text lies,
    which a page without a reading has not; [] before the first unit, None where the export carries no outline."""
    if outline is None:
        return None
    holding = [unit for unit in outline if unit['first_page'] <= pdf_page <= unit['last_page']]
    parents = {unit['parent'] for unit in holding}
    return [unit['id'] for unit in holding if unit['id'] not in parents]


def unread_rows(work: dict, rows: list[dict], pdf: Path, legacy: dict[str, set[int]] | None,
                planned: set[tuple[str, int]] | None, not_served: str | None = None,
                layers: TextLayers | None = None) -> tuple[list[dict], Coverage] | None:
    """The rows of a work's PDF pages that have none in the export, and the work's coverage; None where its PDF is not on this
    machine. `legacy`: the licensed works' legacy pages (None for the free base); `planned`: None where every page is;
    `not_served`: how the librarian serves the file other than page by page, as the shelf says it (`not_served_files`): not at
    all, so nothing serves any of its pages, or by the legacy Markdown whole; `layers`: which pages have a text layer, as
    the start command's app keeps them (`TextLayers`); None: asked of the PDF."""
    if not pdf.exists() or pdf.suffix.lower() != '.pdf':
        return None
    read = {row['pdf_page'] for row in rows}
    file = work['file']
    legacy_work = legacy is not None and file in legacy
    # only a page the text layer may serve is asked whether it has one
    count, with_text = (layers or TextLayers(None)).pages(pdf, file, read, needs_text=not not_served and not legacy_work)
    found = []
    for number in range(1, count + 1):
        if number in read:
            continue
        if not_served == WHOLE_LEGACY:
            served_by = served_readings.LEGACY_ROUTE
        elif not_served:
            served_by = 'nothing'
        elif legacy_work:
            served_by = served_readings.LEGACY_ROUTE if number in legacy[file] else 'nothing'
        else:
            served_by = served_readings.TEXT_LAYER if number in with_text else 'nothing'
        found.append((number, served_by))
    out = [{'knowledge_base': work['knowledge_base'], 'source_id': work['source_id'], 'work': work.get('work'), 'file': file,
            'pdf_page': number, 'printed_label': None, 'units': units_at(work.get('outline'), number), 'route': ROUTES[served_by],
            'route_level': UNREAD_LEVEL, 'fallback': None if served_by == 'nothing' else served_by,
            'check': {'state': UNREAD, 'reasons': [], 'judged': False, 'why_judged': WHY_JUDGED, 'verdict': None},
            'class_when_collected': '', 'class_now': '', 'attempt': 0, 'cost_usd': None, 'error_message': None, 'human': [],
            'category': None, 'page_kind': None,
            'unread': {'served_by': served_by, 'said': (WHOLE_LEGACY_SAID if not_served == WHOLE_LEGACY else f'{NOTHING}: {not_served}'
                                                        if not_served else served_said(served_by, legacy_work)),
                       'planned': planned is None or (file, number) in planned}}
           for number, served_by in found]
    order = (served_readings.LEGACY_ROUTE, served_readings.TEXT_LAYER, 'nothing')
    parts = [UnreadPart(served_by=kind, pages=pages) for kind in order
             if (pages := sum(1 for _, served_by in found if served_by == kind))]
    planned_count = sum(1 for row in out if row['unread']['planned'])
    return out, Coverage(pdf_pages=count, read=len(read), unread=parts, planned=planned_count,
                         said=coverage_said(count, len(read), parts, planned_count))
