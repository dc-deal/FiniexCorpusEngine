"""Each page's and each section's own coverage ladder (the operator's V2.a, 20 Nov: "whatever refinement the material is at,
it should be reachable by link: the work, then the page, then the image; the detail view says that nothing was read, nothing
extracted, and so on").

A PDF page climbs five levels:
1. text layer: the characters its PDF's text layer holds, or none: a scan;
2. text served: what the librarian serves for it, its reading, the IDE's Markdown, the text layer or nothing, and why;
3. keyword search: whether search (BM25) holds it, and why not, in the core's words (`page_index.structural_why`: no text,
   too short, no words, mostly figures, a table), the rule the search itself follows;
4. semantic search: its chunks in its base's vector index, the private base's its own (#8): a free page's by its source id, a
   licensed one's by its work key; a work held back is never embedded;
5. reading and check: none, or its reading and the state the lists count it by.
A section of an HTML or EPUB work climbs the same levels, its text layer and its reading those of a born-digital source.

The search's pages are the librarian's own (`search_server.knowledge_bases`), held by the app's search once built; the served
text is the search page's text. A page view never waits for that build (50 s with both bases) and says so while it runs.
Every page of the PDF is shown on this machine, a file the provenance list holds back too: the view is the operator's alone,
and the librarian goes on refusing that file's images to any model.
"""

import threading
from functools import lru_cache
from pathlib import Path

import pymupdf

from backend.configuration import data_paths
from backend.conversion.store import served_readings
from backend.diagnostics import stamps, unread_pages, work_editions
from backend.diagnostics.coverage_ladder import CHECKED, NOT_IN_INDEX, not_embedded
from backend.diagnostics.ladder_types import PageLadder, PageRung
from backend.diagnostics.readings import NOT_SERVED_ROUTES, fallback_of, listed_state, route_parts
from backend.search import page_index, shelf

NOT_BUILT = 'BM25 being built after a start'  # the keyword level's words while the search is built (the operator, 21 Nov)
SERVED_WAITS = 'not known yet: the search is built when the app starts and on a first search'  # why no served text is shown
BORN_DIGITAL = 'not needed: born digital'
SERVER = {served_readings.LEGACY_ROUTE: "the IDE's Markdown", served_readings.TEXT_LAYER: "the PDF's text layer"}
# a fallback in its shortest words, for the ladder folded to one line
SHORT_SERVER = {served_readings.LEGACY_ROUTE: 'IDE Markdown', served_readings.TEXT_LAYER: 'text layer', 'nothing': 'nothing served'}


# the PDF the page view read last, opened from its bytes so no file handle stays open on it (Windows would lock the file
# against the core), and the one lock its pages are read under (line 1, 20 Nov: each page's view opened the whole PDF, 0.37 s
# of a large file through the container's mount, to count one page's characters, which take 0.01 to 0.06 s)
_PDF: dict[str, tuple[str, stamps.Stamp, pymupdf.Document]] = {}
_PDF_LOCK = threading.Lock()


@lru_cache(maxsize=4096)
def characters_of(pdf: str, stamp: stamps.Stamp, pdf_page: int) -> tuple[int, int | None]:
    """(the PDF's pages, the characters on the page's text layer), counted once per page and state of the file; None for a
    page the PDF does not have."""
    with _PDF_LOCK:
        kept = _PDF.get('last')
        if kept is None or kept[:2] != (pdf, stamp):
            if kept is not None:
                kept[2].close()
            kept = (pdf, stamp, pymupdf.open(stream=Path(pdf).read_bytes(), filetype='pdf'))
            _PDF['last'] = kept
        document = kept[2]
        if not 1 <= pdf_page <= document.page_count:
            return document.page_count, None
        return document.page_count, len(document[pdf_page - 1].get_text().strip())


def text_layer(pdf: Path | None, pdf_page: int) -> PageRung:
    """What the PDF's own text layer holds on the page, in characters."""
    found = stamps.stamp(pdf) if pdf is not None else None
    if found is None:
        return PageRung(level='text layer', reached=None, said='not known: the PDF is not on this machine', short='PDF not here')
    pages, characters = characters_of(str(pdf), found, pdf_page)
    if characters is None:
        return PageRung(level='text layer', reached=None, said=f'the PDF has {pages:,} pages', short='not in the PDF')
    return PageRung(level='text layer', reached=characters > 0,
                    said=f'{characters:,} characters' if characters else 'none: a scan, or a page without text',
                    short='text layer' if characters else 'no text layer')


def served(row: dict) -> PageRung:
    """What the librarian serves for the page: its reading, or what stands in its place, and why."""
    if 'unread' in row:
        return PageRung(level='text served', reached=row['unread']['served_by'] != 'nothing', said=row['unread']['said'],
                        short=SHORT_SERVER.get(row['unread']['served_by'], 'served'))
    source, reader, why = route_parts(row['route'])
    if row['route'] not in NOT_SERVED_ROUTES:
        return PageRung(level='text served', reached=True,
                        said=f"its reading, {source}{f' ({reader})' if reader else ''}" + (f': {why}' if why else ''),
                        short='its reading')
    return PageRung(level='text served', reached=True, said=f"{SERVER.get(fallback_of(row), source)} in its reading's place: {why}",
                    short=SHORT_SERVER.get(fallback_of(row), source))


def served_by(row: dict) -> str | None:
    """What serves the page in its reading's place, where something does; None where its reading is served or nothing is."""
    if 'unread' in row:
        return SERVER.get(row['unread']['served_by'])
    return SERVER.get(fallback_of(row), route_parts(row['route'])[0]) if row['route'] in NOT_SERVED_ROUTES else None


_SEARCH_PAGES: dict[int, dict[tuple[str, str], object]] = {}
_GUARD = threading.Lock()


def search_pages(service) -> dict[tuple[str, str], object]:
    """The search's pages by (work key, PDF page or section label), made once per built search."""
    with _GUARD:
        found = _SEARCH_PAGES.get(id(service))
        if found is None:
            found = {}
            for page in service.by_page.values():
                found.setdefault((page.work, str(page.page)), page)
                if page.pdf:
                    found[(page.work, f'pdf:{page.pdf}')] = page
            _SEARCH_PAGES.clear()
            _SEARCH_PAGES[id(service)] = found
        return found


def kept_said(kept: str) -> str:
    """A kept edition's page or section at its keyword level (E1.a): never searched, and which edition is."""
    return f'kept: not searched; the {kept} is served'


def keyword(page, served_rung: PageRung, built: bool, kept: str | None = None) -> tuple[PageRung, str | None, str | None]:
    """Whether search (BM25) holds the page, and the text the librarian serves for it, or why none is shown. A kept
    edition's page (`kept`, the served edition in a sentence's words) is never searched, built or not, and says so, its text
    shown all the same: it is there and opens by its own key (line 1, 20 Nov, E1.a)."""
    if kept is not None:
        return (PageRung(level='keyword search', reached=False, said=kept_said(kept), short='kept'),
                page.text if page is not None else None,
                None if page is not None else (SERVED_WAITS if not built else 'the search holds no page of it by this number'))
    if not built:
        return PageRung(level='keyword search', reached=None, said=NOT_BUILT, short=NOT_BUILT), None, SERVED_WAITS
    if page is None:
        why = ('nothing is served for it' if not served_rung.reached
               else 'the search holds no page of it by this number: its text stands whole, named by no page')
        return PageRung(level='keyword search', reached=False, said=f'not in search (BM25): {why}', short='not in BM25'), None, why
    if page.searchable:
        return PageRung(level='keyword search', reached=True, said='in search (BM25)', short='in BM25'), page.text, None
    # the core's rule, which the ranking follows (`is_structural`); a page it would rank that the search leaves out all the
    # same was left out for another reason, which the page does not carry
    why = page_index.structural_why(page.words) or 'left out of the ranking'
    return PageRung(level='keyword search', reached=False, said=f'not in search (BM25): {why}', short='not in BM25'), page.text, None


_SEMANTIC: dict[str, tuple[tuple, dict]] = {}
INDEX_DB = {'free': lambda: data_paths.INDEX / 'knowledge.sqlite3', 'licensed': lambda: data_paths.LICENSED_INDEX / 'knowledge.sqlite3'}


def semantic_detail(knowledge_base: str) -> dict:
    """A base's vector index's chunks by page and by section (`shelf.semantic_detail`), each base's its own (#8), read once per
    state of its database: {source: {'pages': {pdf_page: chunks}, 'sections': {section_id: chunks}}}."""
    db = INDEX_DB[knowledge_base]()
    state = (unread_pages.stamp(db),)
    with _GUARD:
        kept = _SEMANTIC.get(knowledge_base)
        if kept is None or kept[0] != state:
            kept = (state, shelf.semantic_detail(db))
            _SEMANTIC[knowledge_base] = kept
        return kept[1]


def chunks_said(chunks: int, of_what: str) -> PageRung:
    counted = f"{chunks:,} {'chunk' if chunks == 1 else 'chunks'}"
    return PageRung(level='semantic search', reached=chunks > 0, said=counted if chunks else f'no chunk of this {of_what}',
                    short=counted if chunks else 'no chunk')


def unknown_semantic(said: str) -> PageRung:
    """A page's or a section's semantic level where its base's index cannot say: not built here, never embedded."""
    short = 'never embedded' if 'never embedded' in said else 'not vectorised' if 'not vectorised' in said else 'not in the index'
    return PageRung(level='semantic search', reached=None, said=said, short=short)


def semantic(knowledge_base: str, source: str | None, key: int | str, by: str, held: str | None = None) -> PageRung:
    """A page's or a section's chunks in its base's vector index; `source` the index's name of its work (a free work's
    source id, a licensed one's work key), `by` 'pages' or 'sections'."""
    detail = semantic_detail(knowledge_base).get(source) if source else None
    if detail is None:
        return unknown_semantic(not_embedded(knowledge_base, held))
    return chunks_said(detail[by].get(key) or detail[by].get(str(key)) or 0, by[:-1])


def reading(row: dict) -> PageRung:
    """The page's reading and the state the lists count it by, or that it has none."""
    if 'unread' in row:
        return PageRung(level='reading and check', reached=False,
                        said='no reading' + ('; planned' if row['unread']['planned'] else ''),
                        short='planned' if row['unread']['planned'] else 'no reading')
    state = listed_state(row)
    said = f"reading {state.replace('_', ' ')}"
    return PageRung(level='reading and check', reached=state in CHECKED, said=said, short=said)


def page_ladder(knowledge_base: str, source_id: str, pdf_page: int, row: dict, pdf: Path | None, work_key: str | None,
                service, held: str | None, kept: str | None = None) -> PageLadder:
    """A PDF page's own ladder; `row` its export row or the row of a page without a reading (`unread_pages`), `service` the
    built search or None, `held` the shelf's why where the provenance list holds the file back, `kept` the served edition
    where the work is a kept one (E1.a)."""
    served_rung = served(row)
    page = search_pages(service).get((work_key, f'pdf:{pdf_page}')) if service is not None and work_key else None
    keyword_rung, text, why_not = keyword(page, served_rung, service is not None, kept)
    return PageLadder(rungs=[text_layer(pdf, pdf_page), served_rung, keyword_rung,
                             semantic(knowledge_base, work_key if knowledge_base == 'licensed' else source_id, pdf_page, 'pages',
                                      held), reading(row)],
                      served_text=text, served_why_not=why_not, held=held, served_by=served_by(row))


def section_ladder(knowledge_base: str, label: str, chunks: int | None, work_key: str, service, held: str | None = None,
                   kept: str | None = None) -> PageLadder:
    """An HTML or EPUB section's own ladder: born digital, so it has no text layer to extract and no reading to need; its
    text served is the section's own, its keyword level the search's. Its chunks: a free HTML section's those its view shows
    (`chunks`); a licensed EPUB section's in the private index (#8), named `<work key>:<ordinal>`, its ordinal its position
    from 0 in four figures (`s1` is `0000`, line 1, 20 Nov)."""
    page = search_pages(service).get((work_key, label)) if service is not None else None
    served_rung = PageRung(level='text served', reached=True, said='its own text, parsed by section', short='its own text')
    keyword_rung, text, why_not = keyword(page, served_rung, service is not None, kept)
    if knowledge_base == 'licensed':
        semantic_rung = semantic('licensed', work_key, f'{work_key}:{int(label[1:]) - 1:04d}', 'sections', held)
    elif chunks is None:
        semantic_rung = unknown_semantic(NOT_IN_INDEX)
    else:
        semantic_rung = chunks_said(chunks, 'section')
    return PageLadder(rungs=[PageRung(level='text layer', reached=None, said=BORN_DIGITAL, short='born digital'), served_rung,
                             keyword_rung, semantic_rung,
                             PageRung(level='reading and check', reached=None, said=BORN_DIGITAL, short='born digital')],
                      served_text=text, served_why_not=why_not)


def shelf_row(store, source_id: str) -> tuple[dict, list[dict]]:
    """A work's row on its base's shelf ({} where it has none) and every row, an EPUB's by the work key its view takes."""
    from backend.diagnostics.coverage_ladder import row_for

    built = store.shelf_data()
    return row_for(built, source_id, source_id) or {}, (built or {}).get('works') or []


def held_of(store, source_id: str) -> tuple[str | None, str | None]:
    """The search's key for a work and why the provenance list holds its file back, both from its base's shelf row of it."""
    row, _ = shelf_row(store, source_id)
    return row.get('work'), row.get('held')


def kept_of(store, source_id: str) -> str | None:
    """Where a work is a kept edition (E1.a), the served edition in a sentence's words ("2nd edition, 2001"); None else."""
    row, rows = shelf_row(store, source_id)
    return work_editions.served_named(row, rows) if row else None

