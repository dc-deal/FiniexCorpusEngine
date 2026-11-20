"""Each page's and each section's own coverage ladder (the operator's V2.a, 20 Nov: "whatever refinement the material is at,
it should be reachable by link: the work, then the page, then the image; the detail view says that nothing was read, nothing
extracted, and so on").

A PDF page climbs five levels:
1. text layer: the characters its PDF's text layer holds, or none: a scan;
2. text served: what the librarian serves for it, its reading, the IDE's Markdown, the text layer or nothing, and why;
3. keyword search: whether search (BM25) holds it, and why not (no text, too short, mostly figures, a table);
4. semantic chunks: its chunks in the vector index; the licensed base is not vectorised yet (#8);
5. reading and check: none, or its reading and the state the lists count it by.
A section of an HTML or EPUB work climbs the same levels, its text layer and its reading those of a born-digital source.

The search's pages are the librarian's own (`search_server.knowledge_bases`), held by the app's search once built; the served
text is the search page's text. A page view never waits for that build (50 s with both bases) and says so while it runs.
Every page of the PDF is shown on this machine, a file the provenance list holds back too: the view is the operator's alone,
and the librarian goes on refusing that file's images to any model.
"""

import re
import threading
from pathlib import Path

import pymupdf

from backend.configuration import data_paths
from backend.conversion.store import served_readings
from backend.diagnostics import unread_pages
from backend.diagnostics.coverage_ladder import CHECKED, NOT_IN_INDEX, NOT_VECTORISED
from backend.diagnostics.ladder_types import PageLadder, PageRung
from backend.diagnostics.readings import NOT_SERVED_ROUTES, fallback_of, listed_state, route_parts
from backend.search import page_index, shelf

NOT_BUILT = 'not known yet: the search is built when the app starts and on a first search'
BORN_DIGITAL = 'not needed: born digital'
SERVER = {served_readings.LEGACY_ROUTE: "the IDE's Markdown", served_readings.TEXT_LAYER: "the PDF's text layer"}


def text_layer(pdf: Path | None, pdf_page: int) -> PageRung:
    """What the PDF's own text layer holds on the page, in characters."""
    if pdf is None or not pdf.exists():
        return PageRung(level='text layer', reached=None, said='not known: the PDF is not on this machine')
    with pymupdf.open(pdf) as document:
        if not 1 <= pdf_page <= document.page_count:
            return PageRung(level='text layer', reached=None, said=f'the PDF has {document.page_count:,} pages')
        characters = len(document[pdf_page - 1].get_text().strip())
    return PageRung(level='text layer', reached=characters > 0,
                    said=f'{characters:,} characters' if characters else 'none: a scan, or a page without text')


def served(row: dict) -> PageRung:
    """What the librarian serves for the page: its reading, or what stands in its place, and why."""
    if 'unread' in row:
        return PageRung(level='text served', reached=row['unread']['served_by'] != 'nothing', said=row['unread']['said'])
    source, reader, why = route_parts(row['route'])
    if row['route'] not in NOT_SERVED_ROUTES:
        return PageRung(level='text served', reached=True,
                        said=f"its reading, {source}{f' ({reader})' if reader else ''}" + (f': {why}' if why else ''))
    return PageRung(level='text served', reached=True, said=f"{SERVER.get(fallback_of(row), source)} in its reading's place: {why}")


def structural_why(text: str) -> str:
    """Why search (BM25) leaves a page out, by the branches of the core's `page_index.is_structural`, which says only that it
    does; its constants are the core's."""
    stripped = re.sub(r'!\[\]\([^)]*\)', '', text)
    if not stripped.strip():
        return 'no text'
    if len(stripped.strip()) < page_index.MIN_CHARS:
        return f'too short: under {page_index.MIN_CHARS} characters'
    words = page_index.TOKEN.findall(stripped.lower())
    if not words:
        return 'no words'
    if len(re.findall(r'\b\d{1,4}\b', stripped)) > len(words) / 3:
        return 'mostly figures, as a contents page or an index'
    if stripped.count('|---') > 2:
        return 'a table'
    return 'left out of the ranking'


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


def keyword(page, served_rung: PageRung, built: bool) -> tuple[PageRung, str | None, str | None]:
    """Whether search (BM25) holds the page, and the text the librarian serves for it, or why none is shown."""
    if not built:
        return PageRung(level='keyword search', reached=None, said=NOT_BUILT), None, NOT_BUILT
    if page is None:
        why = ('nothing is served for it' if not served_rung.reached
               else 'the search holds no page of it by this number: its text stands whole, named by no page')
        return PageRung(level='keyword search', reached=False, said=f'not in search (BM25): {why}'), None, why
    if page.searchable:
        return PageRung(level='keyword search', reached=True, said='in search (BM25)'), page.text, None
    return (PageRung(level='keyword search', reached=False, said=f'not in search (BM25): {structural_why(page.words)}'),
            page.text, None)


_SEMANTIC: dict[tuple, dict] = {}


def semantic_detail() -> dict:
    """The vector index's chunks by page and by section (`shelf.semantic_detail`), read once per state of its database."""
    db = data_paths.INDEX / 'knowledge.sqlite3'
    state = (unread_pages.stamp(db),)
    with _GUARD:
        if state not in _SEMANTIC:
            _SEMANTIC.clear()
            _SEMANTIC[state] = shelf.semantic_detail(db)
        return _SEMANTIC[state]


def semantic(knowledge_base: str, source_id: str, key: int | str, by: str) -> PageRung:
    """A page's or a section's chunks in the vector index; `by` 'pages' or 'sections'."""
    if knowledge_base == 'licensed':
        return PageRung(level='semantic chunks', reached=None, said=NOT_VECTORISED)
    detail = semantic_detail().get(source_id)
    if detail is None:
        return PageRung(level='semantic chunks', reached=None, said=NOT_IN_INDEX)
    chunks = detail[by].get(key) or detail[by].get(str(key)) or 0
    return PageRung(level='semantic chunks', reached=chunks > 0,
                    said=f"{chunks:,} {'chunk' if chunks == 1 else 'chunks'}" if chunks else f'no chunk of this {by[:-1]}')


def reading(row: dict) -> PageRung:
    """The page's reading and the state the lists count it by, or that it has none."""
    if 'unread' in row:
        return PageRung(level='reading and check', reached=False,
                        said='no reading' + ('; planned' if row['unread']['planned'] else ''))
    state = listed_state(row)
    return PageRung(level='reading and check', reached=state in CHECKED, said=f"reading {state.replace('_', ' ')}")


def page_ladder(knowledge_base: str, source_id: str, pdf_page: int, row: dict, pdf: Path | None, work_key: str | None,
                service, held: str | None) -> PageLadder:
    """A PDF page's own ladder; `row` its export row or the row of a page without a reading (`unread_pages`), `service` the
    built search or None, `held` the shelf's why where the provenance list holds the file back."""
    served_rung = served(row)
    page = search_pages(service).get((work_key, f'pdf:{pdf_page}')) if service is not None and work_key else None
    keyword_rung, text, why_not = keyword(page, served_rung, service is not None)
    return PageLadder(rungs=[text_layer(pdf, pdf_page), served_rung, keyword_rung,
                             semantic(knowledge_base, source_id, pdf_page, 'pages'), reading(row)],
                      served_text=text, served_why_not=why_not, held=held)


def section_ladder(knowledge_base: str, label: str, chunks: int | None, work_key: str, service) -> PageLadder:
    """An HTML or EPUB section's own ladder: born digital, so it has no text layer to extract and no reading to need; its
    text served is the section's own, its keyword level the search's, and its chunks those the section view shows (`chunks`),
    the licensed base's not vectorised yet (#8)."""
    page = search_pages(service).get((work_key, label)) if service is not None else None
    served_rung = PageRung(level='text served', reached=True, said='its own text, parsed by section')
    keyword_rung, text, why_not = keyword(page, served_rung, service is not None)
    if knowledge_base == 'licensed' or chunks is None:
        semantic_rung = PageRung(level='semantic chunks', reached=None, said=NOT_VECTORISED if knowledge_base == 'licensed' else NOT_IN_INDEX)
    else:
        semantic_rung = PageRung(level='semantic chunks', reached=chunks > 0,
                                 said=f"{chunks:,} {'chunk' if chunks == 1 else 'chunks'}" if chunks else 'no chunk of this section')
    return PageLadder(rungs=[PageRung(level='text layer', reached=None, said=BORN_DIGITAL), served_rung, keyword_rung, semantic_rung,
                             PageRung(level='reading and check', reached=None, said=BORN_DIGITAL)],
                      served_text=text, served_why_not=why_not)


def held_of(store, source_id: str) -> tuple[str | None, str | None]:
    """The search's key for a work and why the provenance list holds its file back, both from its base's shelf row of it."""
    from backend.diagnostics.coverage_ladder import row_for

    row = row_for(store.shelf_data(), source_id) or {}
    return row.get('work'), row.get('held')

