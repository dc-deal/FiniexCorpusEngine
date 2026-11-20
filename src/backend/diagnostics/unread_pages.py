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

A page is planned where the rollout's plan holds it (`rollout.FOLDER / 'plan.json'`) or a session's list of pages to read
(`reading_cells.DIRECT_PAGES`, why 'unread'); a free PDF is read whole, so each of its pages is planned, as the shelf counts it.

Each unread page stands as a row of the export's shape in a state of its own, `not_read`, so the summary, the routes, the
chapters and the facet bar count it as they count a read page; it has no reading to open and no image. It is built once per
state of the export, the PDF, the legacy pages and the plans, and the legacy pages once per state of the licensed export
(15.8 s natively, warmed at the app's start). The licensed knowledge base is never read under --public-only, and neither is
anything here of it.
"""

import json
import threading
from pathlib import Path
from typing import Literal

import pymupdf
from pydantic import BaseModel

from backend.configuration import data_paths
from backend.conversion.store import served_readings

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


def stamp(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


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
    of the two. A free PDF is read whole, so the free base asks for none."""
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
                planned: set[tuple[str, int]] | None) -> tuple[list[dict], Coverage] | None:
    """The rows of a work's PDF pages that have none in the export, and the work's coverage; None where its PDF is not on this
    machine. `legacy`: the licensed works' legacy pages (None for the free base); `planned`: None where every page is."""
    if not pdf.exists() or pdf.suffix.lower() != '.pdf':
        return None
    read = {row['pdf_page'] for row in rows}
    file = work['file']
    legacy_work = legacy is not None and file in legacy
    found = []
    with pymupdf.open(pdf) as document:
        count = document.page_count
        for number in range(1, count + 1):
            if number in read:
                continue
            if legacy_work:
                served_by = served_readings.LEGACY_ROUTE if number in legacy[file] else 'nothing'
            else:
                served_by = served_readings.TEXT_LAYER if document[number - 1].get_text().strip() else 'nothing'
            found.append((number, served_by))
    out = [{'knowledge_base': work['knowledge_base'], 'source_id': work['source_id'], 'work': work.get('work'), 'file': file,
            'pdf_page': number, 'printed_label': None, 'units': units_at(work.get('outline'), number), 'route': ROUTES[served_by],
            'route_level': UNREAD_LEVEL, 'fallback': None if served_by == 'nothing' else served_by,
            'check': {'state': UNREAD, 'reasons': [], 'judged': False, 'why_judged': WHY_JUDGED, 'verdict': None},
            'class_when_collected': '', 'class_now': '', 'attempt': 0, 'cost_usd': None, 'error_message': None, 'human': [],
            'category': None, 'page_kind': None,
            'unread': {'served_by': served_by, 'said': served_said(served_by, legacy_work),
                       'planned': planned is None or (file, number) in planned}}
           for number, served_by in found]
    order = (served_readings.LEGACY_ROUTE, served_readings.TEXT_LAYER, 'nothing')
    parts = [UnreadPart(served_by=kind, pages=pages) for kind in order
             if (pages := sum(1 for _, served_by in found if served_by == kind))]
    planned_count = sum(1 for row in out if row['unread']['planned'])
    return out, Coverage(pdf_pages=count, read=len(read), unread=parts, planned=planned_count,
                         said=coverage_said(count, len(read), parts, planned_count))
