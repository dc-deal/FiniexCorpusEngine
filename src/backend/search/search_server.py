"""A keyword search over the knowledge bases, served over the Model Context Protocol (decisions 57.a, 71.a, phase 3).

Any MCP client can call it without a chat model: a coding session asks, the server answers with cited pages. Its tools:
`works` (the shelf), `search_works` (which works hold a subject), `toc`, `search`, `semantic_search`, `open_page` and
`page_image`; every hit names its knowledge base, work, page (its label, its PDF page where known, its
printed number), the section in effect, file and lines, licence, and the route that made the page's text, so a quote from an
unverified text layer is never mistaken for a checked reading. A search that finds nothing says so.

One index holds every page of both knowledge bases, so scores are comparable and a search over one base is the same ranking
with the other filtered out (decision 71.a, which replaced fusing two indexes). Ranking is the ported page BM25 (`page_index`).

- **Free** (what a reviewer runs): the PDFs from their verified page readings in `corpus/readings/` (decision 72.a); a page whose
  reading was blocked, stayed malformed, or is an issue the judge found falls back to its text layer, and says so; the HTML sources
  by section.
- **Licensed:** only on the machine that holds it; never leaves it. Per page its checked reading where one may be served, by the
  free corpus's rule, else the legacy Markdown; a work without legacy Markdown from its readings and text layer, as a free PDF
  (decision 125.a). The marks the provenance list records are stripped.

    python -m backend.search.search_server               # stdio: an MCP host starts it as a subprocess
    python -m backend.search.search_server --http 8765   # streamable HTTP on 127.0.0.1, behind the token in .env
    python -m backend.search.search_server --public-only # the free knowledge base alone, for a recorded review
"""

import bisect
import dataclasses
import json
import os
import re
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import pymupdf

from backend.configuration import data_paths
from backend.conversion.store.reading_store import REPO
from backend.conversion.store.served_readings import (LEGACY_ROUTE, READING_ROUTE, TEXT_LAYER_WHY, printed_of,  # noqa: F401
                                                route_of, text_layer_why)
from backend.search import page_index
from backend.types.config_types.app_config_types import IndexSource

CATALOG = REPO / 'corpus' / 'catalog.json'
MANIFEST = data_paths.FREE_RAW / '_manifest.json'
EXPORT = data_paths.FREE_READINGS
LEGACY = data_paths.LICENSED_WORKING / 'legacy_markdown'
PROVENANCE = data_paths.LICENSED_WORKING / 'provenance.json'
WORK_KEYS = REPO / 'src' / 'backend' / 'conversion' / 'reading' / 'mini_pilot_pages.json'  # the free works' keys, tracked
FURNITURE = {'page_header', 'page_footer', 'page_number', 'watermark', 'decoration', 'margin_tab', 'description'}
# 'description' is derived by the reader, never the author's words, so it is never searched as if quoted (OC-9.a)
CORPORA = ('all', 'free', 'licensed')
# The most hits one call returns (decision 96.a). Measured 2026-11-06 on the free knowledge base: a page hit is about 790
# characters, so 50 are about 40,000; a passage carries up to 1,000 characters of text besides. Without a bound one call
# asking for thousands would flood the calling model's context and keep the server busy building hits nobody reads.
MAX_HITS = 50
WORK_PAGES = 5  # a work's score in `search_works`: the sum of its best five pages, so breadth on a subject counts
MIN_BOOKMARKS = 5  # fewer bookmarks than this are a stub (one PDF has 3 for 447 pages): its headings are the contents
BEST_SECTIONS = 3  # the sections `search_works` names per work, its best pages' sections, each once


def hits_refused(hits: int) -> str | None:
    """Why a number of hits is refused, or None: both search tools take 1 to MAX_HITS."""
    return None if 1 <= hits <= MAX_HITS else f'hits must be 1 to {MAX_HITS}; got {hits}'


def free_work_keys() -> dict[str, str]:
    """File -> the free work's key, from the tracked page list: its pages and its corpus works (decision 121.b)."""
    source = json.loads(WORK_KEYS.read_text(encoding='utf-8'))
    return {page['file']: page['work'] for page in source['pages'] + source.get('corpus_works', [])}


@dataclass
class Work:
    key: str
    title: str
    knowledge_base: str
    licence: str
    route: str
    pages: int = 0
    printed: dict = dataclasses.field(default_factory=dict)  # kept for callers of the first version; pages carry it now
    subject: str | None = None  # what the work is for here, in one sentence (decision 124.a); None where none is written
    view_id: str | None = None  # the work's id in the diagnostics view, None where the view shows no page of it (226.a)
    # the edition a citation names (E1.a, 20 Nov): "2nd" and its year, from the catalog; None where the catalog has none
    edition: str | None = None
    year: int | None = None
    kept_for: str | None = None  # a kept edition (E1.a): the key of the edition its work serves; the searches skip it


def legacy_headings(path: Path, offset: int = 0) -> list[dict]:
    """A legacy Markdown work's headings in order, each with its level and the label of the page it stands on, the label
    the server gives that page (the marker's number, or its ordinal where the marker has none, moved by the work's measured
    offset, decision 127.a)."""
    text = path.read_text(encoding='utf-8')
    markers = [(marker.start(), marker.group(1) if marker.group(1) != 'None' else str(max(1, ordinal + offset)))
               for ordinal, marker in enumerate(page_index.PAGE_MARKER.finditer(text), start=1)]
    positions = [position for position, _ in markers]
    entries = []
    for head in page_index.ANY_HEADING.finditer(text):
        title = page_index.heading_text(head.group(0))
        if not title:
            continue
        at = bisect.bisect_left(positions, head.start())
        entries.append({'level': len(head.group(0)) - len(head.group(0).lstrip('#')), 'title': title,
                        'page': markers[at - 1][1] if at else (markers[0][1] if markers else None)})
    return entries


def headings_of(parsed) -> list[str]:
    return [' '.join((block.inline or {}).get('plain', block.body).split()) for block in parsed.blocks if block.cls == 'heading']








def export_rows_by_file(export: Path) -> dict[str, dict[int, dict]]:
    """File -> PDF page -> its row in an export's index.json; empty where nothing was exported."""
    index = export / 'index.json'
    rows: dict[str, dict[int, dict]] = {}
    for row in json.loads(index.read_text(encoding='utf-8'))['pages'] if index.exists() else []:
        rows.setdefault(row['file'], {})[row['pdf_page']] = row
    return rows


def pdf_work_pages(key: str, pdf: Path, rows: dict[int, dict], quoted: dict[int, str], export: Path, knowledge_base: str,
                   marks: list[str] = ()) -> list[page_index.Page]:
    """Every page of one PDF with the text the chat quotes for it (decision 93.a): its served reading, else its text layer
    cleaned as the chat cleans it, from the one function both use (`quoted`); the route says which, per page. `rows`: PDF page
    -> the export's row. The same for a free PDF and a licensed one (decision 125.a), so both bases serve a page alike."""
    from backend.conversion.contract.page_contract import parse

    pages, section = [], None
    with pymupdf.open(pdf) as document:
        count = document.page_count
    for number in range(1, count + 1):
        row, printed, reading_key = rows.get(number), None, None
        why = text_layer_why(row)
        parsed = None
        if row and row.get('text_file'):
            # The export judged the class under today's validator; here the reading is only read
            parsed = parse((export / row['text_file']).read_text(encoding='utf-8'), row['form'])
            printed = printed_of(parsed)
        start_section = section
        if parsed is not None:
            titles = headings_of(parsed)
            if titles:
                first_block = next((block for block in parsed.blocks if block.cls not in FURNITURE), None)
                start_section = titles[0] if first_block is not None and first_block.cls == 'heading' else section
                section = titles[-1]
        if why is None:
            where, reading_key = data_paths.stored(export / row['text_file'], REPO), row['reading_key']
        else:
            where = f"{data_paths.stored(pdf, REPO)}#page={number}"
        text = strip_stamps(quoted.get(number, ''), list(marks))
        if not text.strip():
            continue
        pages.append(page_index.Page(key, str(number), 1, text, where, pdf=str(number), section=start_section,
                                     knowledge_base=knowledge_base, route=route_of(row), printed=printed, reading_key=reading_key,
                                     index_text=page_index.without_latex(text), searchable=not page_index.is_structural(text)))
    return pages


def free_pdf_pages(only: set[str] | None = None) -> tuple[list[page_index.Page], dict]:
    """Every page of the free PDFs, each with its served reading or its text layer (`pdf_work_pages`); with `only`, the works
    whose key or source id it names alone (issue #10, part D: one work written again)."""
    from backend.conversion.store import reading_export

    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))['sources']
    keys = free_work_keys()
    rows = export_rows_by_file(EXPORT)
    pages, works = [], {}
    for source in catalog:
        if source.get('format') != 'pdf':
            continue
        path = data_paths.locate(source['files'][0]['path'])
        if not path.exists():
            continue
        key = keys.get(path.name, source['id'])
        if only is not None and key not in only and source['id'] not in only:
            continue
        work = works[key] = Work(key, source['title'], 'free', source['licence'], 'per page', subject=source.get('subject'),
                                 view_id=source['id'], year=source.get('year'))
        own = pdf_work_pages(key, path, rows.get(path.name, {}), reading_export.quoted_pages('free', path.name), EXPORT, 'free')
        pages += own
        work.pages += sum(page.searchable for page in own)
    return pages, works


def free_html_pages(only: set[str] | None = None) -> tuple[list[page_index.Page], dict]:
    """The free HTML sources by section: their markup already carries the structure, so no reader was needed; with `only`,
    the sources it names alone."""
    from backend.ingestion.clean_sections.html_sections import load_html_sections

    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))['sources']
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))['files'] if MANIFEST.exists() else {}
    pages, works = [], {}
    for source in catalog:
        if source.get('format') != 'html' or not all(data_paths.locate(entry['path']).exists() for entry in source['files']):
            continue
        if only is not None and source['id'] not in only:
            continue
        work = works[source['id']] = Work(source['id'], source['title'], 'free', source['licence'], 'html, parsed by section',
                                          subject=source.get('subject'), view_id=source['id'], year=source.get('year'))
        for section in load_html_sections(source, manifest, data_paths.DATA):
            if not section.text.strip():
                continue
            searchable = not page_index.is_structural(section.text)
            pages.append(page_index.Page(source['id'], f's{section.ordinal + 1}', 1, section.text, section.url or source['files'][0]['path'],
                                         section=' > '.join(section.heading_path) or None, knowledge_base='free',
                                         route='html, parsed by section', searchable=searchable))
            work.pages += searchable
    return pages, works


def free_pages(only: set[str] | None = None) -> tuple[list[page_index.Page], dict]:
    pdf_pages, pdf_works = free_pdf_pages(only)
    html_pages, html_works = free_html_pages(only)
    return pdf_pages + html_pages, {**pdf_works, **html_works}


def stamps() -> list[str]:
    """The page marks the provenance list records; they are page furniture and never reach an answer (decision 33)."""
    if not PROVENANCE.exists():
        return []
    files = json.loads(PROVENANCE.read_text(encoding='utf-8')).get('files', {})
    return sorted({str(entry['stamp']).strip().lower() for entry in files.values() if isinstance(entry, dict) and entry.get('stamp')})


def strip_stamps(text: str, marks: list[str]) -> str:
    if not marks:
        return text
    return '\n'.join(line for line in text.split('\n') if not any(mark in line.lower() for mark in marks))


LICENSED_ARCHIVE = data_paths.LICENSED_ARCHIVE
LICENSED_EXPORT = data_paths.LICENSED_WORKING / 'readings'
LICENSED_LICENCE = 'licensed, local use only'
STAND_INS = data_paths.LICENSED_WORKING / 'stand_ins.json'


def stand_in_rule() -> tuple[str | None, set[str]]:
    """How this machine's collection marks a stand-in file, and which works a stand-in serves (126.a), from a git-ignored list
    beside the licensed working data: {"suffix": ..., "works": [...]}; none on a machine without it. Kept there, not in the
    code, since it tells how the private collection is made up (251.a)."""
    if not STAND_INS.exists():
        return None, set()
    listed = json.loads(STAND_INS.read_text(encoding='utf-8'))
    return listed.get('suffix') or None, set(listed.get('works', []))


LICENSED_SUBJECTS = data_paths.LICENSED_WORKING / 'subjects.json'


def licensed_subjects() -> dict[str, str]:
    """Work key -> what the licensed work is for here, in one sentence, drawn from the curation of the collection's first
    owner (decision 124.a); empty on a machine without it."""
    return json.loads(LICENSED_SUBJECTS.read_text(encoding='utf-8'))['subjects'] if LICENSED_SUBJECTS.exists() else {}


def legacy_keys() -> dict[str, str]:
    """The legacy Markdown's citation keys, key -> file stem; empty on a machine without it."""
    keys_file = LEGACY / 'keys.json'
    return json.loads(keys_file.read_text(encoding='utf-8'))['keys'] if keys_file.exists() else {}


LEGACY_OFFSETS = data_paths.LICENSED_WORKING / 'legacy_pdf_offsets.json'


def legacy_offsets() -> dict[str, int]:
    """Work key -> the offset that turns the ordinal of a legacy marker without a number into its PDF page (decision 127.a):
    measured per work, never guessed; empty where nothing was measured."""
    return json.loads(LEGACY_OFFSETS.read_text(encoding='utf-8'))['offsets'] if LEGACY_OFFSETS.exists() else {}


def stand_ins(keys: dict[str, str]) -> dict[str, Path]:
    """Work key -> the stand-in PDF of its work (decision 126.a): where the file a legacy text was converted from is not
    held and its stand-in may be sent, the stand-in serves the work whole, since its pages can be checked against an image
    and the legacy text's page numbers point at a file that is not here."""
    from backend.conversion.reading import reading_cells

    suffix, works = stand_in_rule()
    if not suffix:
        return {}
    found = {key: LICENSED_ARCHIVE / f'{keys[key]}{suffix}.pdf' for key in works if key in keys}
    return {key: pdf for key, pdf in found.items() if pdf.exists() and reading_cells.may_send(pdf.name)}


def numbered(pages: list[page_index.Page], offset: int) -> list[page_index.Page]:
    """A legacy work's pages named by their PDF page, the ordinal moved by its measured offset; a page that falls before the
    PDF's first is left out (the marker of a header note, never served)."""
    return [dataclasses.replace(page, page=str(int(page.page) + offset), pdf=str(int(page.page) + offset))
            for page in pages if int(page.page) + offset >= 1]


def new_licensed_pdfs(keys: dict[str, str]) -> dict[str, Path]:
    """Work key -> PDF for the licensed PDFs without legacy Markdown: the new works (decision 125.a), keyed by their file's stem.
    A file the provenance list holds back is left out, and so is the stand-in of a work whose legacy text stands: two copies
    of one book would compete for every hit."""
    from backend.conversion.reading import reading_cells

    slugs = set(keys.values())
    suffix, _ = stand_in_rule()
    return {pdf.stem: pdf for pdf in sorted(LICENSED_ARCHIVE.glob('*.pdf'))
            if pdf.stem not in slugs and reading_cells.may_send(pdf.name)
            and not (suffix and pdf.stem.endswith(suffix) and pdf.stem.removesuffix(suffix) in slugs)}


def with_readings(legacy: list[page_index.Page], readings: list[page_index.Page]) -> list[page_index.Page]:
    """A work's legacy pages with each checked reading in place of the legacy page of its PDF page (decision 125.a), the legacy
    page's section kept, since its headings run through the whole work; a reading of a page the legacy text left out (a table, a
    short page) joins it, in the section in effect before it. Matched by the PDF page only where the legacy marker names it:
    a legacy text without PDF page numbers cannot be matched page by page, and stands whole."""
    import bisect

    numbered = sorted((int(page.pdf), page) for page in legacy if page.pdf)
    if not numbered or not readings:
        return legacy
    served = {page.pdf: page for page in readings if page.reading_key}
    numbers = [number for number, _ in numbered]
    out = [dataclasses.replace(served[page.pdf], work=page.work, section=page.section) if page.pdf in served else page
           for page in legacy]
    known = {page.pdf for page in legacy if page.pdf}
    for pdf, reading in sorted(served.items(), key=lambda item: int(item[0])):
        if pdf in known:
            continue
        before = bisect.bisect_left(numbers, int(pdf)) - 1
        out.append(dataclasses.replace(reading, work=numbered[0][1].work, section=numbered[before][1].section if before >= 0 else None))
    return sorted(out, key=lambda page: int(page.pdf) if page.pdf else 0) if all(page.pdf for page in out) else out


EPUB_ROUTE = 'epub, parsed by section'


def licensed_epubs(keys: dict[str, str]) -> dict[str, Path]:
    """Work key -> EPUB (decision 123.a, the operator's P1.a, 18 Nov). An EPUB of a legacy work serves it in place of its legacy
    text, since the EPUB is the file the text was made from; one without a legacy text joins under its file's stem. A
    stand-in EPUB serves its work in place of the legacy text too where the stand-ins' list names the work (`epub_stand_ins`);
    any other stays beside it. The provenance list does not matter here: nothing of an EPUB reaches a provider."""
    by_slug = {slug: key for key, slug in keys.items()}
    suffix, _ = stand_in_rule()
    own = {by_slug.get(path.stem, path.stem): path for path in sorted(LICENSED_ARCHIVE.glob('*.epub'))
           if not (suffix and path.stem.endswith(suffix))}
    return {**own, **epub_stand_ins(keys)}


def epub_stand_ins(keys: dict[str, str]) -> dict[str, Path]:
    """Work key -> the stand-in EPUB that serves it: where the file a legacy text was converted from is not held and the
    stand-ins' list names the work (126.a), the publisher's EPUB beats the conversion of a file no longer here (the operator,
    22 Nov, for two works: measured, their EPUBs hold 96 and 99.7 % of the legacy text's words, and the newer edition of
    one 13 % more)."""
    suffix, works = stand_in_rule()
    if not suffix:
        return {}
    found = {key: LICENSED_ARCHIVE / f'{keys[key]}{suffix}.epub' for key in works if key in keys}
    return {key: path for key, path in found.items() if path.exists()}


def epub_pages(key: str, path: Path, marks: list[str]) -> list[page_index.Page]:
    """An EPUB's sections as pages `s1`, `s2`, …, as the free HTML sources' are; an image stands as its mark in the text."""
    from backend.ingestion.clean_sections.epub_sections import IMAGE_MARK, load_epub_sections

    pages = []
    for item in load_epub_sections(path, key):
        section = item.section
        text = strip_stamps(section.text, marks)
        if not text.strip():
            continue
        pages.append(page_index.Page(key, f's{section.ordinal + 1}', 1, text, section.url or path.name,
                                     section=' > '.join(section.heading_path) or None, knowledge_base='licensed', route=EPUB_ROUTE,
                                     index_text=text.replace(IMAGE_MARK, ' ') if IMAGE_MARK in text else None,
                                     searchable=not page_index.is_structural(text)))
    return pages


LICENSED_CATALOG = data_paths.LICENSED_CATALOG
HTML_ROUTE = 'html, parsed by section'  # the free HTML sources' route, in the same words for a licensed one


def licensed_html() -> dict[str, tuple[Path, dict]]:
    """Work key -> (file, catalog entry) of each licensed HTML source the local catalog describes with its layout
    (`labelled_sections`, 22 Nov: a rule text whose structure is its paragraph labels), keyed by its file's stem as a new PDF
    is (125.a); empty on a machine without the catalog. The provenance list does not matter here, as for an EPUB: the
    search is local, and the private vector index holds a held file back itself."""
    if not LICENSED_CATALOG.exists():
        return {}
    found = {}
    for entry in json.loads(LICENSED_CATALOG.read_text(encoding='utf-8')).get('sources', []):
        if entry.get('format') != 'html' or not entry.get('labelled_sections') or not entry.get('file'):
            continue
        path = LICENSED_ARCHIVE / entry['file']
        if path.exists():
            found[path.stem] = (path, entry)
    return found


def html_pages(key: str, path: Path, entry: dict, marks: list[str]) -> list[page_index.Page]:
    """A licensed HTML source's sections as pages `s1`, `s2`, …, as the free HTML sources' are, cut at its paragraph labels;
    each links to its place on the source's page."""
    from backend.ingestion.clean_sections.html_labelled_sections import load_labelled_sections

    pages = []
    for section in load_labelled_sections(entry, path.parent):
        text = strip_stamps(section.text, marks)
        if not text.strip():
            continue
        pages.append(page_index.Page(key, f's{section.ordinal + 1}', 1, text, section.url or path.name,
                                     section=' > '.join(section.heading_path) or None, knowledge_base='licensed',
                                     route=HTML_ROUTE, searchable=not page_index.is_structural(text)))
    return pages


def legacy_by_work(keys: dict[str, str], marks: list[str], only: set[str] | None = None) -> dict[str, list[page_index.Page]]:
    """Each legacy work's pages by citation key, the provenance list's marks stripped (a page left as structure by the strip is
    dropped) and numbered through the work's measured offset (127.a); with `only`, the works it names alone."""
    legacy: dict[str, list[page_index.Page]] = {}
    stems = None if only is None else {keys.get(key, key) for key in only}
    for page in page_index.load_works(LEGACY, keys, stems) if keys else []:
        text = strip_stamps(page.text, marks)
        if text != page.text and page_index.is_structural(text):
            continue
        legacy.setdefault(page.work, []).append(dataclasses.replace(page, text=text, knowledge_base='licensed', route=LEGACY_ROUTE))
    for key, offset in legacy_offsets().items():
        if key in legacy:
            legacy[key] = numbered(legacy[key], offset)
    return legacy


def legacy_fallback_pages() -> dict[str, set[int]]:
    """PDF file -> its PDF pages whose legacy Markdown `licensed_pages` serves where the page's reading is not served
    (`with_readings`): a legacy work routed page by page, neither an EPUB's (123.a) nor a stand-in's (126.a). The export names
    this fallback in its rows, so a page never claims a text layer it does not serve (H2.a, 19 Nov: a scan has none)."""
    keys = legacy_keys()
    if not keys:
        return {}
    legacy = legacy_by_work(keys, stamps())
    for key in (*licensed_epubs(keys), *stand_ins(keys)):
        legacy.pop(key, None)
    out = {}
    for key, own in legacy.items():
        numbers, name = {int(page.pdf) for page in own if page.pdf}, f'{keys.get(key, key)}.pdf'
        if numbers and (LICENSED_ARCHIVE / name).exists():  # a legacy text without its PDF has no page that could fall back
            out[name] = numbers
    return out


def licensed_pages(only: set[str] | None = None) -> tuple[list[page_index.Page], dict]:
    """The licensed works by citation key; empty on a machine without them. Per page the checked reading where one may be served
    (the free corpus's rule, `text_layer_why`), else the legacy Markdown; a work without legacy Markdown (a new work, decision
    125.a) from its readings and its text layer, as a free PDF, and so does a stand-in file of a work (126.a). A legacy work
    whose markers carry no number is named by its PDF pages through its measured offset (127.a). An HTML source the local
    catalog describes, by its sections cut at its paragraph labels (`licensed_html`). The marks the provenance list records are
    stripped from every text. With `only`, the works it names alone, by the key the librarian gives them (issue #10, D)."""
    from backend.conversion.store import reading_export

    keys = legacy_keys()
    marks = stamps()
    rows = export_rows_by_file(LICENSED_EXPORT)
    legacy = legacy_by_work(keys, marks, only)
    standing_in = stand_ins(keys)
    pages, works = [], {}
    wanted = (lambda key: True) if only is None else (lambda key: key in only)
    for key, epub in licensed_epubs(keys).items():  # decision 123.a: the EPUB in place of the legacy text made from it
        if not wanted(key):
            continue
        legacy.pop(key, None)
        own = epub_pages(key, epub, marks)
        works[key] = Work(key, epub.stem, 'licensed', LICENSED_LICENCE, EPUB_ROUTE, sum(page.searchable for page in own),
                          view_id=key)
        pages += own
    for key, pdf in standing_in.items():
        if not wanted(key):
            continue
        legacy.pop(key, None)
        own = pdf_work_pages(key, pdf, rows.get(pdf.name, {}), reading_export.quoted_pages('licensed', pdf.name), LICENSED_EXPORT,
                             'licensed', marks)
        works[key] = Work(key, pdf.stem, 'licensed', LICENSED_LICENCE, 'per page', sum(page.searchable for page in own),
                          view_id=pdf.stem)
        pages += own
    for key, own in legacy.items():
        pdf = LICENSED_ARCHIVE / f'{keys.get(key, key)}.pdf'
        readings = []
        if pdf.exists() and rows.get(pdf.name) and any(page.pdf for page in own):
            readings = pdf_work_pages(key, pdf, rows[pdf.name], reading_export.quoted_pages('licensed', pdf.name), LICENSED_EXPORT,
                                      'licensed', marks)
        own = with_readings(own, readings)
        served = any(page.reading_key for page in own)
        works[key] = Work(key, keys.get(key, key), 'licensed', LICENSED_LICENCE, 'per page' if served else 'legacy markdown',
                          sum(page.searchable for page in own), view_id=pdf.stem if readings else None)
        pages += own
    for key, pdf in new_licensed_pdfs(keys).items():
        if not wanted(key):
            continue
        own = pdf_work_pages(key, pdf, rows.get(pdf.name, {}), reading_export.quoted_pages('licensed', pdf.name), LICENSED_EXPORT,
                             'licensed', marks)
        works[key] = Work(key, pdf.stem, 'licensed', LICENSED_LICENCE, 'per page', sum(page.searchable for page in own),
                          view_id=pdf.stem)
        pages += own
    for key, (path, entry) in licensed_html().items():  # an HTML source by its labelled sections; the view shows none of it yet
        if not wanted(key):
            continue
        own = html_pages(key, path, entry, marks)
        works[key] = Work(key, path.stem, 'licensed', LICENSED_LICENCE, HTML_ROUTE, sum(page.searchable for page in own))
        pages += own
    for key, subject in licensed_subjects().items():
        if key in works:
            works[key].subject = subject
    return with_editions(pages, works, keys)


def with_editions(pages: list[page_index.Page], works: dict, keys: dict[str, str], families: dict[str, dict] | None = None
                  ) -> tuple[list[page_index.Page], dict]:
    """Each licensed work's edition and year from the local catalog, and a kept edition's pages out of the keyword index (E1.a,
    the operator, 20 Nov): one edition of a work is served, the others kept. A kept edition's pages stay openable by its own key
    and keep their text, place and route, so its chunks in the private index stay as they are (their fingerprint holds no
    ranking flag) and a switch embeds nothing again."""
    from backend.ingestion.licensed_index import catalog_entries
    from backend.search import editions

    for key, entry in catalog_entries(keys).items():
        if key in works:
            works[key].edition, works[key].year = entry.get('edition'), entry.get('year')
    # the list names an edition by its file's stem, the catalog's id; a legacy work is keyed by its citation key (found by
    # line 2, 20 Nov: the served lecture's key is its legacy key), so a stem is turned into the key the server uses
    work_key = {slug: key for key, slug in keys.items()}.get
    kept = {work_key(key, key): work_key(served, served) for key, served in editions.kept(families).items()}
    for key, served in kept.items():
        if key in works:
            works[key].kept_for, works[key].pages = served, 0
    if kept:
        pages = [dataclasses.replace(page, searchable=False) if page.work in kept else page for page in pages]
    return pages, works


def free_sources() -> dict[str, dict]:
    """Source id -> the work key `search` uses for it and its raw file, so a passage and a page hit name a work alike."""
    keys = free_work_keys()
    return {source['id']: {'work': keys.get(Path(source['files'][0]['path']).name, source['id']), 'path': source['files'][0]['path']}
            for source in json.loads(CATALOG.read_text(encoding='utf-8'))['sources']}


def image_sources() -> dict[str, dict]:
    """Work key -> where its page images come from (decision 92.a): {'pdf': path}, or {'refused': why}. A free PDF from the
    catalog; a licensed work through the legacy keys, unless the file its text was converted from is not held, it came from
    an EPUB, or the provenance list holds its file back: such a file would reach a provider through the caller's own model,
    and it is never sent to one (decision 33)."""
    from backend.conversion.reading import reading_cells

    sources = {}
    keys = free_work_keys()
    for source in json.loads(CATALOG.read_text(encoding='utf-8'))['sources']:
        path = data_paths.locate(source['files'][0]['path'])
        sources[keys.get(path.name, source['id'])] = (
            {'pdf': path} if source.get('format') == 'pdf' else {'refused': 'no PDF page: an HTML source has sections, not pages'})
    keys_file = LEGACY / 'keys.json'
    if keys_file.exists():
        legacy = json.loads(keys_file.read_text(encoding='utf-8'))
        _, gone = stand_in_rule()
        for key, slug in legacy['keys'].items():
            pdf = LICENSED_ARCHIVE / f'{slug}.pdf'
            if key in gone:
                sources[key] = {'refused': 'no page image: no file of this text is held'}
            elif not pdf.exists():
                sources[key] = {'refused': 'no PDF: the work was converted from an EPUB'}
            elif not reading_cells.may_send(pdf.name):
                sources[key] = {'refused': 'held back by the provenance list: never sent to a provider'}
            else:
                sources[key] = {'pdf': pdf}
    sources.update({key: {'pdf': pdf} for key, pdf in new_licensed_pdfs(legacy_keys()).items()})  # sendable by construction
    sources.update({key: {'pdf': pdf} for key, pdf in stand_ins(legacy_keys()).items()})
    sources.update({key: {'refused': 'no PDF page: an HTML source has sections, not pages'} for key in licensed_html()})
    return sources


# Where `python -m backend.diagnostics` serves (decision 226.a): its default port, unless DIAGNOSTICS_VIEW_URL says where it
# runs. The variable reaches a server the chat starts too, since a subprocess inherits its parent's environment.
DEFAULT_VIEW_URL = os.environ.get('DIAGNOSTICS_VIEW_URL') or 'http://127.0.0.1:8001'


class SearchService:
    """The tools as plain methods, so they can be tested and timed without a transport."""

    def __init__(self, sources: dict[str, tuple[list, dict]], images: dict[str, dict] | None = None, semantic=None,
                 frozen_plans: dict | None = None, view_url: str | None = DEFAULT_VIEW_URL):
        self.view_url = view_url.rstrip('/') if view_url else None  # the diagnostics view a hit links into (226.a)
        self._images = images  # work key -> its page images' source, found on first use unless given
        self._semantic = semantic  # the chat's retrieval chain (98.c), built on its first question unless given
        self._frozen_plans = frozen_plans  # evaluation only: an earlier run's router plans, by question (phase 6)
        started = time.perf_counter()
        self.works, pages = {}, []
        for knowledge_base, (base_pages, works) in sources.items():
            self.works.update(works)
            pages += [page if page.knowledge_base else dataclasses.replace(page, knowledge_base=knowledge_base) for page in base_pages]
        self.index = page_index.PageIndex([page for page in pages if page.searchable])  # the ranking's statistics as before
        self.by_page = {(page.work, page.page): page for page in pages}  # open_page opens every page with text
        self.pdf_labelled = {page.work for page in pages if page.pdf}  # works whose page labels are their PDF's pages
        self.bases = sorted({page.knowledge_base for page in pages})
        self.start_seconds = time.perf_counter() - started
        self.database_url: str | None = None  # set where the index is read from the database (issue #10, part C)
        self.generation: int | None = None
        self._reload = threading.Lock()

    @classmethod
    def from_database(cls, url: str, **options) -> 'SearchService':
        """The service over the index database (issue #10, part C): works and pages loaded in seconds, the keyword ranking
        in SQL, and the index loaded again whenever its generation moves, so a written change is served without a
        restart. Built empty first, so every other setting stays the constructor's."""
        service = cls({}, **options)
        service.database_url = url
        service._load_from_database()
        return service

    def _load_from_database(self) -> None:
        import psycopg

        from backend.search.database import database_index

        started = time.perf_counter()
        with psycopg.connect(self.database_url, connect_timeout=database_index.CONNECT_TIMEOUT_SECONDS) as connection:
            pages, works, generation = database_index.load(connection, Work)
        previous = self.index
        self.works = works
        self.index = database_index.DatabaseIndex(self.database_url, pages)
        self.by_page = {(page.work, page.page): page for page in pages.values()}
        self.pdf_labelled = {page.work for page in pages.values() if page.pdf}
        self.bases = sorted({page.knowledge_base for page in pages.values()})
        self.generation = generation
        self.start_seconds = time.perf_counter() - started
        if isinstance(previous, database_index.DatabaseIndex):
            previous.close()

    def refresh(self) -> bool:
        """A service read from the database loads the index again where its generation moved; True when it did. One cheap
        query per call; a service built from files never changes."""
        if self.database_url is None:
            return False
        from backend.search.database import database_index

        with self._reload:
            if self.index._ask(database_index.generation) == self.generation:
                return False
            self._load_from_database()
            return True

    def ranked_pages(self) -> list:
        """The pages the keyword ranking holds, whichever index serves: for the banner and the start's checks."""
        pages = self.index.pages
        return [page for page in (pages.values() if isinstance(pages, dict) else pages) if page.searchable]

    def _where(self, page: page_index.Page) -> str:
        if page.line_end:
            return f'{page.path}:{page.line}-{page.line_end}'
        return page.path

    def view_of(self, work_key: str, label: str | None, pdf: str | None) -> str | None:
        """Where a person sees this page in the diagnostics view, with its image, its reading and every check (decision
        226.a, the operator, 12 Nov): a PDF page by its PDF number, an HTML section by its place. None where the view shows no page:
        a legacy text without a reading, or a server started without a view."""
        work = self.works.get(work_key)
        if not self.view_url or work is None or not work.view_id:
            return None
        if work.route.startswith('html') and label:
            return f'{self.view_url}/#/{work.knowledge_base}/html/{work.view_id}/{label}'
        if work.route == EPUB_ROUTE and label:  # the view's EPUB section (line 2, 18 Nov): the work by its key, URL-encoded
            return f'{self.view_url}/#/{work.knowledge_base}/epub/{quote(work.view_id, safe="")}/{label}'
        if pdf:
            return f'{self.view_url}/#/{work.knowledge_base}/sources/{work.view_id}/page/{pdf}'
        return None

    def _hit(self, score: float, page: page_index.Page, query: str) -> dict:
        work = self.works[page.work]
        found, missing = page_index.coverage(page.words, query)
        return {'score': round(score, 2), 'knowledge_base': page.knowledge_base, 'work': page.work, 'title': work.title,
                'edition': work.edition, 'year': work.year,
                'page': {'label': page.page, 'pdf': page.pdf, 'printed': page.printed}, 'section': page.section,
                'where': self._where(page), 'snippet': page_index.snippet(page.text, query), 'terms_found': found,
                'terms_missing': missing, 'licence': work.licence, 'route': page.route or work.route,
                'reading_key': page.reading_key, 'view_url': self.view_of(page.work, page.page, page.pdf)}

    def search(self, query: str, corpus: str = 'all', hits: int = 6, work: str | None = None) -> dict:
        if refused := hits_refused(hits):
            return {'state': 'error', 'error': refused, 'hits': []}
        if corpus not in CORPORA:
            return {'state': 'error', 'error': f'unknown corpus {corpus!r}; use one of {list(CORPORA)}', 'hits': []}
        if work is not None and work not in self.works:
            return {'state': 'error', 'error': f'unknown work {work!r}; the tool works lists every key', 'hits': []}
        accept = lambda page: (corpus == 'all' or page.knowledge_base == corpus) and (work is None or page.work == work)
        ranked = self.index.search(query, hits, accept)
        if not ranked:
            return {'state': 'nothing found', 'query': query, 'corpus': corpus, 'hits': []}
        return {'state': 'found', 'query': query, 'corpus': corpus, 'hits': [self._hit(score, page, query) for score, page in ranked]}

    def open_page(self, work: str, page: str, printed: bool = False) -> dict:
        """One page in full. With `printed`, `page` is the number printed on the page, as an index entry or a "see p. 291"
        gives it, and the page that prints it is opened (decision 175.a, the operator, 10 Nov): in OpenStax's accounting book printed
        655 is PDF page 669, and the same number as a label would open the wrong page without a word."""
        note = None
        if printed:
            matches = [candidate for candidate in self.by_page.values()
                       if candidate.work == work and (candidate.printed or '').strip() == str(page).strip()]
            matches.sort(key=lambda candidate: int(candidate.pdf) if str(candidate.pdf or '').isdigit() else 0)
            found = matches[0] if matches else None
            if len(matches) > 1:
                note = (f"printed page {page} stands on PDF pages {', '.join(str(match.pdf) for match in matches)}; "
                        'the first is opened')
        else:
            found = self.by_page.get((work, str(page)))
        if found is None:
            return {'state': 'nothing found', 'work': work, 'page': str(page), **({'printed': True} if printed else {})}
        meta = self.works[work]
        return {'state': 'found', 'work': work, 'title': meta.title, 'edition': meta.edition, 'year': meta.year,
                **({'kept_for': meta.kept_for} if meta.kept_for else {}), 'knowledge_base': found.knowledge_base,
                'page': {'label': found.page, 'pdf': found.pdf, 'printed': found.printed}, 'section': found.section,
                'where': self._where(found), 'text': found.text, 'licence': meta.licence, 'route': found.route or meta.route,
                'reading_key': found.reading_key, 'view_url': self.view_of(work, found.page, found.pdf),
                **({'note': note} if note else {})}

    def page_image(self, work: str, page: str) -> dict:
        """A page's image (decision 92.a), with what it is, or why there is none. A work the server does not serve, a licensed
        one under `--public-only` too, is not found."""
        from backend.search import page_images

        if work not in self.works:
            return {'state': 'nothing found', 'work': work, 'page': str(page)}
        if self._images is None:
            self._images = image_sources()
        # A page the keyword index leaves out (a contents page, a page of tables) still has an image: where a work's labels
        # are PDF pages, the label is the page.
        found = self.by_page.get((work, str(page)))
        pdf_page = found.pdf if found is not None else str(page) if work in self.pdf_labelled else None
        answer = {'state': 'no image', 'work': work, 'knowledge_base': self.works[work].knowledge_base,
                  'page': {'label': str(page), 'pdf': pdf_page, 'printed': found.printed if found is not None else None}}
        source = self._images.get(work, {'refused': 'no source known for this work'})
        if 'refused' in source:
            return {**answer, 'why': source['refused']}
        if not (pdf_page and str(pdf_page).isdigit()):
            return {**answer, 'why': 'no PDF page: this work counts its text, not the pages of a PDF'}
        try:
            image = page_images.page_image(source['pdf'], int(pdf_page))
        except page_images.NoSuchPage as missing:
            return {**answer, 'state': 'nothing found', 'why': str(missing)}
        return {**answer, 'state': 'found', 'image': image.describe(), 'data': image.data, 'format': image.format}

    def semantic_search(self, question: str, hits: int = 10, search_query: str | None = None, concept_query: str | None = None,
                        keywords: list[str] | None = None, route: bool = True) -> dict:
        """The chat's retrieval chain (decision 98.c): route, then search by meaning and by keywords; over the free index, and
        the private one fused by rank where this server gives the private base out and its index was built (#8)."""
        from backend.search import semantic_search

        if refused := hits_refused(hits):  # before the router is built or called: a refused call costs nothing
            return {'state': 'error', 'error': refused, 'question': question, 'hits': []}
        if self._semantic is None:
            from backend.search import retrieval

            # the private base's index too (#8), where this server gives that base out and its index was built here
            private = 'licensed' in self.bases and retrieval.licensed_index_built()
            kept = frozenset(key for key, work in self.works.items() if work.kept_for)  # a kept edition's chunks stay out (E1.a)
            self._semantic = semantic_search.SemanticSearch(free_sources(), frozen_plans=self._frozen_plans, private=private,
                                                            kept=kept)
        given = {'search_query': search_query, 'concept_query': concept_query, 'keywords': keywords}  # the caller's own translation
        # the router kept out of this call only when asked (S1.a); the default call stays the one every client makes
        found = self._semantic.search(question, hits, **{name: value for name, value in given.items() if value},
                                      **({} if route else {'route': False}))
        for hit in found.get('hits') or []:
            hit['view_url'] = self.view_of(hit.get('work'), (hit.get('page') or {}).get('label'), (hit.get('page') or {}).get('pdf'))
            work = self.works.get(hit.get('work'))
            hit['edition'], hit['year'] = (work.edition, work.year) if work else (None, None)
        return found

    def list_works(self) -> list[dict]:
        """Every work the server knows; a kept edition (E1.a) names the edition its work serves, the served one its kept ones."""
        kept_by: dict[str, list[str]] = {}
        for work in self.works.values():
            if work.kept_for:
                kept_by.setdefault(work.kept_for, []).append(work.key)
        return [{'work': work.key, 'title': work.title, 'edition': work.edition, 'year': work.year,
                 'knowledge_base': work.knowledge_base, 'licence': work.licence, 'route': work.route, 'pages': work.pages,
                 'subject': work.subject,
                 **({'kept_for': work.kept_for} if work.kept_for else {}),
                 **({'kept_editions': sorted(kept_by[work.key])} if work.key in kept_by else {})}
                for work in sorted(self.works.values(), key=lambda work: work.key)]

    def search_works(self, query: str, corpus: str = 'all', hits: int = 10) -> dict:
        """Which works hold a subject (decision 124.a): the page ranking of `search`, summed per work over its best
        WORK_PAGES pages, so a work about the subject outranks one strong page elsewhere, a glossary for one. Each work comes
        with its subject sentence, how many of its pages hold a query word and how many hold every one, and its best few
        sections. No library was needed: it is a sum over the index's own scores, the passage-to-document aggregation
        retrieval papers call SumP. A query no page holds in full says so: `pages_with_every_term` is 0."""
        if refused := hits_refused(hits):
            return {'state': 'error', 'error': refused, 'works': []}
        if corpus not in CORPORA:
            return {'state': 'error', 'error': f'unknown corpus {corpus!r}; use one of {list(CORPORA)}', 'works': []}
        inside = lambda page: corpus == 'all' or page.knowledge_base == corpus
        every = {number for number in self.index.holding_every_term(query) if inside(self.index.pages[number])}
        per_work: dict[str, list[tuple[float, int]]] = {}
        for score, number in self.index.scored(query):
            if inside(self.index.pages[number]):
                per_work.setdefault(self.index.pages[number].work, []).append((score, number))
        if not per_work:
            return {'state': 'nothing found', 'query': query, 'corpus': corpus, 'pages_with_every_term': 0, 'works': []}
        total = {key: sum(score for score, _ in scored[:WORK_PAGES]) for key, scored in per_work.items()}
        found = []
        for key in sorted(per_work, key=lambda key: (-total[key], key))[:hits]:
            work, sections, seen = self.works[key], [], set()
            for score, number in per_work[key]:
                page = self.index.pages[number]
                if page.section in seen:
                    continue
                seen.add(page.section)
                sections.append({'section': page.section, 'page': {'label': page.page, 'pdf': page.pdf, 'printed': page.printed},
                                 'score': round(score, 2)})
                if len(sections) == BEST_SECTIONS:
                    break
            found.append({'work': key, 'title': work.title, 'subject': work.subject, 'knowledge_base': work.knowledge_base,
                          'licence': work.licence, 'score': round(total[key], 2), 'pages_matching': len(per_work[key]),
                          'pages_with_every_term': sum(1 for _, number in per_work[key] if number in every),
                          'best_sections': sections})
        return {'state': 'found', 'query': query, 'corpus': corpus, 'pages_with_every_term': len(every), 'works': found}

    def toc(self, work: str, depth: int = 2) -> dict:
        """A work's table of contents, to descend into before reading (decision 124.a): its PDF's bookmarks where its page
        labels are PDF pages, else the headings of its legacy Markdown, else its HTML sections, else the headings its page
        readings found; each entry with the page label `open_page` takes. Entries deeper than `depth` are counted, not sent."""
        if work not in self.works:
            return {'state': 'error', 'error': f'unknown work {work!r}; the tool works lists every key', 'entries': []}
        if not 1 <= depth <= 6:
            return {'state': 'error', 'error': f'depth must be 1 to 6; got {depth}', 'entries': []}
        source, entries = self._contents(work)
        meta = self.works[work]
        if not entries:
            return {'state': 'nothing found', 'work': work, 'title': meta.title, 'why': 'no bookmarks and no headings', 'entries': []}
        kept = [entry for entry in entries if entry['level'] <= depth]
        return {'state': 'found', 'work': work, 'title': meta.title, 'knowledge_base': meta.knowledge_base, 'source': source,
                'depth': depth, 'entries': kept, 'left_out': len(entries) - len(kept)}

    def _contents(self, work: str) -> tuple[str, list[dict]]:
        own = [page for (key, _), page in self.by_page.items() if key == work]
        if self._images is None:
            self._images = image_sources()
        pdf = self._images.get(work, {}).get('pdf')
        if work in self.pdf_labelled and pdf is not None and Path(pdf).exists():
            with pymupdf.open(pdf) as document:
                bookmarks = [{'level': level, 'title': ' '.join(str(title).split()), 'page': str(page) if page >= 1 else None}
                             for level, title, page in document.get_toc(simple=True)]
            if len(bookmarks) >= MIN_BOOKMARKS:
                return 'pdf bookmarks', bookmarks
        else:
            bookmarks = []
        legacy = next((Path(page.path) for page in own if page.route == 'legacy markdown'), None)
        if legacy is not None and not legacy.is_absolute():
            legacy = REPO / legacy
        if legacy is not None and legacy.exists():
            headings = legacy_headings(legacy, legacy_offsets().get(work, 0))
            if len(headings) > len(bookmarks):
                return 'legacy markdown headings', headings
        if own and all(page.page.startswith('s') for page in own):
            return 'html sections', [{'level': (page.section or '').count(' > ') + 1,
                                      'title': (page.section or '').split(' > ')[-1] or page.page, 'page': page.page}
                                     for page in own]
        entries, last = [], None
        for page in own:
            if page.section and page.section != last:
                entries.append({'level': 1, 'title': page.section, 'page': page.page})
            last = page.section or last
        if len(entries) > len(bookmarks):
            return 'headings the readings found', entries
        return 'pdf bookmarks', bookmarks  # few, but the best there is


# What an MCP host shows its model about the server as a whole (a consumer's request of 8 Nov: nobody knew to ask the shelf
# first). The chat's agent sees only the tools it is given, so this changes nothing it was measured with.
# Since T1.a (the operator, 21 Nov) it also says what each tool costs and takes, in orders of magnitude a measurement keeps
# true (the call log of 21 Nov: search 36 ms, semantic_search 2.0 s in the median), and how to read what comes back.
INSTRUCTIONS = (
    'A library of trading, finance, accounting and software reliability books, each answer a cited page. Start with `works`: '
    'the whole shelf in one call, with a sentence per work on what it is for. Then go from cheap and exact to costly and '
    'broad. `search_works` (which works hold a subject, and that none does when none does) and `search` (exact words on '
    'pages, BM25) run locally in milliseconds and cost nothing. `semantic_search` (a question in plain words, by meaning and '
    'keywords at once) takes about two seconds and embeds the question through a paid API; without your own translation '
    '(`search_query`, `concept_query`, `keywords`) it also asks a language model to translate it, so bring the translation. '
    'Then `toc` and `open_page` to read the pages a hit names, and `page_image` only when a page\'s text is not enough to '
    'check a quote; all three are local and free, but an image weighs on your own context. No tool lets a model write or '
    'rephrase a text: every hit quotes the stored page as it stands. Every hit names its knowledge base, and its edition and '
    'year where the catalog has them. A score ranks the hits of one call only; it is not comparable between tools or calls. '
    'Where a work is held in more than one edition, the searches use one and skip the others, which `works` names.')


CALL_LOG = data_paths.LOGS / 'search_server.jsonl'  # git-ignored: one line per tool call, never a page's text


CONSOLE_TEXT = 60  # the most of a question a console line shows (decision 99.a)
NO_CALLER = {'client': None, 'client_version': None, 'session': None}


def utf8_stderr() -> None:
    """stderr as UTF-8 whatever it is connected to. Through a pipe, as an MCP host reads it, Windows wrote cp1252: an umlaut or
    the console line's ellipsis came out as U+FFFD in a UTF-8 reader, an arrow as an escape (the review of 99.a, 5 Nov). On a
    console this changes nothing; stdout is the SDK's own under stdio and stays untouched."""
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')


def console_width() -> int | None:
    """The width of the terminal stderr writes to; None for a pipe or a file, such as an MCP host's log."""
    try:
        return os.get_terminal_size(sys.stderr.fileno()).columns
    except (OSError, ValueError, AttributeError):  # io.UnsupportedOperation is both an OSError and a ValueError
        return None


def printable(text: str) -> str:
    """What a client sent, safe for a terminal: line breaks and runs of spaces collapsed to one space, and every character
    that is not printable gone, an escape sequence among them: `\\x1b[2J` in a question would clear the operator's screen."""
    return ''.join(character for character in ' '.join(str(text).split()) if character.isprintable())


def cells(text: str) -> int:
    """How many terminal columns `text` takes: a wide or fullwidth East Asian character two, a combining mark none.

    The stdlib's Unicode tables, not the `wcwidth` package: a dependency for a console's width was not worth it, and both
    count the cases a question brings (CJK, emoji, accents) alike."""
    return sum(0 if unicodedata.category(character) in ('Mn', 'Me') else
               2 if unicodedata.east_asian_width(character) in ('W', 'F') else 1 for character in text)


def shortened(text: str, width: int) -> str:
    """One printable line of at most `width` terminal columns, the end cut with an ellipsis."""
    flat = printable(text)
    if cells(flat) <= width:
        return flat
    kept, used = [], 0
    for character in flat:
        if used + cells(character) > width - 1:
            break
        kept.append(character)
        used += cells(character)
    return ''.join(kept).rstrip() + '…'


def padded(text: str, width: int) -> str:
    """`text` shortened to `width` columns and filled with spaces to exactly that many, so the columns stay aligned."""
    short = shortened(text, width)
    return short + ' ' * (width - cells(short))


def console_line(tool: str, state: str, count: int, seconds: float, client: str | None, asked: dict) -> str:
    """A call as one console line (decision 99.a): when, which tool, which client, what came of it, how long, and what was
    asked, last, so a narrow window shortens the question and never the columns: a question in quotes, a page as its work and
    label. Never a page's text."""
    from datetime import datetime

    status = f'found {count}' if state == 'found' else state
    head = f"{datetime.now():%H:%M:%S}  {tool:15}  {padded(client or '-', 11)}  {status:13}  {seconds * 1000:6.0f} ms"
    if asked.get('query'):
        text, quote = asked['query'], '"'
    elif asked.get('work'):
        text, quote = f"{asked['work']} {asked.get('page') or ''}", ''
    else:
        return head
    width = console_width()
    room = CONSOLE_TEXT if width is None else min(CONSOLE_TEXT, width - 1 - cells(head) - 2 - 2 * len(quote))
    return head if room < 8 else f'{head}  {quote}{shortened(text, room)}{quote}'


def client_line(client: str | None, client_version: str | None, session: str | None) -> str:
    """The line before a new client's first call (decision 99.a): its name and version, and its session where it has one."""
    from datetime import datetime

    who = shortened(' '.join(part for part in (client or 'unknown client', client_version) if part), 40)
    return f"{datetime.now():%H:%M:%S}  + {who}" + (f'  session {printable(session)[:8]}' if session else '')


def client_key(caller: dict):
    """A client as the console counts it: its session where it has one, else its name and version (decision 99.a)."""
    return caller['session'] or (caller['client'], caller['client_version'])


def caller_of(ctx) -> dict | None:
    """Who asked (decision 99.a): the client's name and version, from its handshake or the request's own envelope, and the
    transport's session where there is one; None outside a request (a test that calls a tool directly).

    Measured on mcp 2.3.0 on 5 Nov, over stdio, HTTP and in process: the name and version arrive in both protocol eras; a session
    id only over HTTP with a handshake-era protocol (up to 2025-11-25), as the `mcp-session-id` header, which the SDK's session
    manager has matched to a session it issued, an unknown one being refused with a 404. A 2026-07-28 request is a connection of
    its own and passes no session manager, so a session header on it is only the client's word and is ignored: the review of
    99.a forged one and got a new client line per call. `ctx.session` is built anew for every request, so it is no client's
    identity."""
    from mcp.types.version import HANDSHAKE_PROTOCOL_VERSIONS

    try:
        session, headers, era = ctx.session, ctx.headers or {}, ctx.protocol_version
    except ValueError:  # "Context is not available outside of a request"
        return None
    params = session.client_params
    info = params.client_info if params is not None else None
    sent = next((value for key, value in headers.items() if key.lower() == 'mcp-session-id'), None)
    return {'client': info.name if info else None, 'client_version': info.version if info else None,
            'session': sent if era in HANDSHAKE_PROTOCOL_VERSIONS else None}


def log_call(tool: str, result, seconds: float, log_path: Path | None, caller: dict | None = None, **asked) -> None:
    """One line per tool call on stderr and one record in the call log: who asked, what, which pages answered, how long it
    took. The line shows the question shortened to one line (decision 99.a); the record keeps it whole, as the caller's words
    and the raw material of future evaluation questions, with the client and its session. Neither ever holds a snippet or a
    page."""
    from datetime import datetime, timezone

    caller = caller or NO_CALLER
    found = result.get('hits', []) if isinstance(result, dict) else []
    state = result.get('state', 'found') if isinstance(result, dict) else 'found'
    listed = next((result[key] for key in ('hits', 'works', 'entries') if isinstance(result, dict) and isinstance(result.get(key), list)),
                  None)  # a search's pages, a work search's works, a contents' entries
    count = len(listed) if listed is not None else len(result) if isinstance(result, list) else 1
    print(console_line(tool, state, count, seconds, caller['client'], asked), file=sys.stderr)
    if log_path is None:
        return
    record = {'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'tool': tool, 'state': state, 'ms': round(seconds * 1000, 1),
              **caller, **asked,  # the client since 5 Nov (99.a); absent before
              'answered': [{'knowledge_base': hit['knowledge_base'], 'work': hit['work'], 'label': hit['page']['label'],
                            'pdf': hit['page']['pdf']} for hit in found]}  # objects since 5 Nov; strings before
    if tool == 'search_works' and isinstance(result, dict):  # the works that answered, without pages (since 8 Nov)
        record['answered_works'] = [{'knowledge_base': item['knowledge_base'], 'work': item['work']} for item in result.get('works', [])]
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'a', encoding='utf-8', newline='\n') as log:
            # ASCII JSON: a lone surrogate a client sent could not be written as UTF-8 and failed the call; a line separator
            # (U+2028, U+0085) split the record for every reader that splits on lines (the review of 99.a, 5 Nov).
            log.write(json.dumps(record) + '\n')
    except OSError as error:  # a full disk or a locked file must not cost the caller an answer the server already has
        print(f'corpus-search: the call log was not written ({type(error).__name__})', file=sys.stderr)


def knowledge_bases(public_only: bool = False) -> dict:
    """The knowledge bases a server gives out. With `public_only` the licensed one is never read, so no licensed title, hit or
    page can appear, which makes a recorded review safe by construction (decision 81.a)."""
    bases = {'free': free_pages()}
    if not public_only:
        bases['licensed'] = licensed_pages()
    return bases


def build_server(service: SearchService, log_path: Path | None = CALL_LOG):
    from mcp.server import MCPServer
    from mcp.server.mcpserver import Context
    from mcp.server.mcpserver.utilities.types import Image

    server = MCPServer('corpus-search', instructions=INSTRUCTIONS)
    seen, seen_lock = set(), threading.Lock()  # the clients this server has shown a line for (decision 99.a)

    def logged(tool: str, ctx, call, **asked):
        # Every tool takes the SDK's Context as `ctx` (keyword-only, never in its input schema): the one documented way
        # to reach the request, as MCPServer has no global accessor. A client is its session where it has one, else its
        # name and version: a 2026-07-28 request carries no session, so two sessions of one client version are one.
        caller = caller_of(ctx)
        if caller is not None:
            key = client_key(caller)
            with seen_lock:
                new = key not in seen
                seen.add(key)
            if new:
                print(client_line(**caller), file=sys.stderr)
        started = time.perf_counter()
        service.refresh()  # read from the database: a written change is served on the next call (issue #10)
        result = call()
        log_call(tool, result, time.perf_counter() - started, log_path, caller, **asked)
        return result

    @server.tool()
    def search(query: str, corpus: str = 'all', hits: int = 6, work: str | None = None, *, ctx: Context) -> dict:
        """Search the books by keywords (BM25 over pages): local, no model, milliseconds, free. Best for exact terms, names,
        numbers and a formula's symbols; for a question in plain words use `semantic_search`. Returns up to `hits` pages
        (1 to 50), best first, each with its knowledge base, work, edition and year, page (label, PDF page where known, printed
        number), section, file and lines, a snippet, licence and the route that made its text, and `view_url`, a link to show
        a person the page in the diagnostics view (image, reading, checks); or state "nothing found". The score ranks this
        call's hits only. A page under 200 characters, mostly digits or a table is left out of the ranking but opens with
        `open_page`. corpus: "all", "free" or "licensed". work: one key from `works`."""
        return logged('search', ctx, lambda: service.search(query, corpus, hits, work), query=query, corpus=corpus, hits=hits,
                      work=work)

    @server.tool()
    def open_page(work: str, page: str, printed: bool = False, *, ctx: Context) -> dict:
        """One page in full, by work key and page label as a search hit gives them: local and free, the text exactly as stored
        and served, never rewritten. With printed=true, `page` is the number
        printed on the page, as an index entry or a "see p. 291" in the text gives it; the answer names both numbers. `view_url`
        links the page in the diagnostics view, for a person to check it against its image."""
        return logged('open_page', ctx, lambda: service.open_page(work, page, printed), work=work, page=page, printed=printed)

    @server.tool()
    def works(*, ctx: Context) -> list[dict]:
        """Every work the server knows, local and free: key, title, edition and year, knowledge base, licence, route and how
        many pages are searchable. Where a work is held in more than one edition, one is searched and the others are kept: a kept edition
        names the edition searched (`kept_for`) and still opens by its own key."""
        return logged('works', ctx, service.list_works)

    @server.tool()
    def search_works(query: str, corpus: str = 'all', hits: int = 10, *, ctx: Context) -> dict:
        """Which works hold a subject: do we own a book about X? Local, no model, milliseconds, free. The same keyword ranking
        as `search`, summed per work over
        its best five pages, so a work about the subject outranks one strong page elsewhere (a glossary). Returns up to `hits`
        works (1 to 50), each with its key, title, the sentence on what it is for, knowledge base, licence, score, how many
        pages hold a query word and how many hold every one, and its best three sections with their pages; or state
        "nothing found". `pages_with_every_term` 0 means no page holds all the words, which is an answer too. corpus:
        "all", "free" or "licensed"."""
        return logged('search_works', ctx, lambda: service.search_works(query, corpus, hits), query=query, corpus=corpus,
                      hits=hits)

    @server.tool()
    def toc(work: str, depth: int = 2, *, ctx: Context) -> dict:
        """A work's table of contents, local and free, to descend into before reading a page: its PDF's bookmarks, else the
        headings of
        its text, each with the page label `open_page` takes, and where they come from. depth 1 to 6 (default 2): deeper
        entries are counted in `left_out`, not sent. work: one key from `works`."""
        return logged('toc', ctx, lambda: service.toc(work, depth), work=work, depth=depth)

    @server.tool()
    def semantic_search(question: str, hits: int = 10, search_query: str | None = None, concept_query: str | None = None,
                        keywords: list[str] | None = None, router: bool = True, *, ctx: Context) -> dict:
        """Search by meaning and by keywords at once, the way the chat does, over every knowledge base this server gives out
        (the licensed one beside the free one where it is given out, the two fused by rank). About two seconds; the question is
        embedded through a paid API (a fraction of a cent). Translate the question yourself for the best results and to spare
        a language model call: `search_query`, the question as a short standalone English search query in the words textbooks
        use; `concept_query`, a step back to the underlying concept as a textbook would name it; `keywords`, two to five terms
        of art. Without them the server's router, a language model, translates where it is switched on, else the question
        searches as it stands; `router` false keeps the language model out of this call even without a translation, so the
        question searches as it stands. The passages closest in meaning and the best keyword matches are fused by rank. Returns up to
        `hits` passages (1 to 50), each a chunk of about 1,000 characters with its full text, its knowledge base, work, edition
        and year, page and section, licence and route, its score, and `view_url`, a link to the page in the diagnostics view;
        or state "declined", "nothing found" or "error". `relevance` is the best similarity of meaning found; `below_floor`
        true means it lies under the floor that parts covered questions from uncovered ones, so the books likely say nothing
        on this: say so rather than answer from the passages. Use it for a question in plain words; use `search` for exact
        terms."""
        return logged('semantic_search', ctx,
                      lambda: service.semantic_search(question, hits, search_query, concept_query, keywords, route=router),
                      query=question, hits=hits)

    @server.tool()
    def page_image(work: str, page: str, *, ctx: Context) -> list[dict | Image]:
        """A page's image, on request only: when a page's text is not enough to check a quote. Local and free here, but an
        image weighs on the caller's own context. A scanned page comes with its
        own embedded pixels, never upscaled (a JPEG2000 or fax image as a PNG of the same pixels); a born-digital page as a
        150 dpi render. The first block says which, with the stored format, pixels, dpi and bytes, so a poor scan can be told
        apart before its image is read; or why there is no image (no source, no PDF page, held back). Same work key and page
        label as a search hit."""
        result = logged('page_image', ctx, lambda: service.page_image(work, page), work=work, page=page)
        if result.get('state') != 'found':
            return [result]
        return [{key: value for key, value in result.items() if key not in ('data', 'format')},
                Image(data=result['data'], format=result['format'])]

    return server


TOKEN_ENV = 'CORPUS_SEARCH_TOKEN'
# A container reaches a service of the host as host.docker.internal; the package's DNS-rebinding guard must know that name.
# The diagnostics view's container reaches the librarian by its compose service name (the operator's L1.a, 21 Nov).
ALLOWED_HOSTS = ['127.0.0.1:*', 'localhost:*', 'host.docker.internal:*', 'librarian:*']


class BearerGate:
    """An ASGI gate in front of the HTTP transport: a request without the shared token gets 401, so no other local process or
    container reads the books by accident. The token lives in the git-ignored .env, beside the API keys."""

    def __init__(self, app, token: str):
        self.app, self.expected = app, f'Bearer {token}'.encode()

    async def __call__(self, scope, receive, send):
        import hmac

        if scope['type'] in ('http', 'websocket'):
            supplied = [value for name, value in scope.get('headers') or [] if name.lower() == b'authorization']
            if len(supplied) != 1 or not hmac.compare_digest(supplied[0], self.expected):
                if scope['type'] == 'websocket':
                    await send({'type': 'websocket.close', 'code': 1008})
                    return
                await send({'type': 'http.response.start', 'status': 401, 'headers': [(b'content-type', b'text/plain')]})
                await send({'type': 'http.response.body', 'body': b'unauthorized'})
                return
        await self.app(scope, receive, send)


def http_app(server, token: str):
    from mcp.server.transport_security import TransportSecuritySettings

    return BearerGate(server.streamable_http_app(transport_security=TransportSecuritySettings(allowed_hosts=ALLOWED_HOSTS)), token)


def route_kind(route: str | None) -> str:
    """A route's kind without its particulars: 'vision reading (claude-sonnet-5-5, …)' is a vision reading."""
    return re.split(r'\s*[(:]', route or 'unknown', maxsplit=1)[0]


def banner(service: SearchService, tools: list[str], http: int | None, public_only: bool) -> list[str]:
    """What a server offers, said when it starts (the operator, 2026-11-04): its version, where it listens, its knowledge bases with their
    pages and works, the routes their texts come by, and its tools."""
    from collections import Counter

    from backend.conversion.store import pipeline_db

    code = pipeline_db.code_version()
    version = (f"commit {(code['code_commit'] or 'unknown')[:7]}{'' if code['code_clean'] else ' with uncommitted changes'}, "
               f"code {code['code_sha256'][:8]}")
    where = (f'http://127.0.0.1:{http}/mcp, from containers host.docker.internal:{http}; bearer token {TOKEN_ENV} from .env'
             if http else 'stdio')
    ranked = service.ranked_pages()
    pages = Counter(page.knowledge_base for page in ranked)
    works = Counter(work.knowledge_base for work in service.works.values())
    routes = Counter(route_kind(page.route) for page in ranked)
    bases = ' · '.join(f'{base} {pages[base]:,} pages in {works[base]} works' for base in sorted(pages))
    source = (f'the index database, generation {service.generation}, loaded' if service.database_url
              else 'files, assembled and indexed')
    return [f'corpus-search, {version}',
            f'  listening  {where}',
            f"  bases      {bases}{'; --public-only: the licensed base is not read' if public_only else ''}",
            '  routes     ' + ' · '.join(f'{kind} {count:,}' for kind, count in routes.most_common()),
            '  tools      ' + ' · '.join(tools),
            f'  index      {source} in {service.start_seconds:.1f} s']


def build_service(public_only: bool, index: str | None = None, **options) -> SearchService:
    """The service a start asks for (issue #10, part C): read from the index database where the configuration or `--index`
    says so, else from files, as always. `--public-only` reads files alone, so the licensed base is never touched. A
    database that cannot be read, or holds no work, never stops the librarian: it serves from files and says why."""
    from backend.configuration.app_config_manager import AppConfigManager

    source = IndexSource(index) if index else AppConfigManager().get_database().librarian_reads
    if source == IndexSource.DATABASE and not public_only:
        try:
            from backend.database.database_url import database_url

            service = SearchService.from_database(database_url(), **options)
            if service.works:
                return service
            reason = 'it holds no work yet: python -m backend.search.database.index_import'
        except Exception as error:  # the database down, not configured, or its schema behind: files serve instead
            reason = f'{type(error).__name__}: {str(error).splitlines()[0] if str(error) else ""}'
        print(f'corpus-search: the index database cannot serve ({reason}); the index is assembled from files',
              file=sys.stderr)
    return SearchService(knowledge_bases(public_only), **options)


def main() -> None:
    import argparse
    import asyncio
    import os

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--http', type=int, metavar='PORT', help='serve over streamable HTTP on 127.0.0.1:PORT instead of stdio')
    parser.add_argument('--host', default='127.0.0.1',
                        help='the address to listen on (default 127.0.0.1); 0.0.0.0 only inside a container, whose port is published on '
                             '127.0.0.1 alone (docker-compose.yml)')
    parser.add_argument('--public-only', action='store_true',
                        help='serve the free knowledge base alone: the licensed one is not even read (for a recorded review)')
    parser.add_argument('--view-url', default=DEFAULT_VIEW_URL, metavar='URL',
                        help=f'the diagnostics view a hit links into (default {DEFAULT_VIEW_URL}; "" for none)')
    parser.add_argument('--frozen-plans', type=Path, metavar='JSON',
                        help='evaluation only: route semantic_search by these plans, {question: plan}, instead of the router')
    parser.add_argument('--index', choices=[source.value for source in IndexSource],
                        help='where the index is read from (default: database.librarian_reads in configs/app_config.json); '
                             '--public-only always reads files, so the licensed base is never touched')
    args = parser.parse_args()
    utf8_stderr()
    frozen = json.loads(args.frozen_plans.read_text(encoding='utf-8')) if args.frozen_plans else None
    service = build_service(args.public_only, args.index, frozen_plans=frozen, view_url=args.view_url or None)
    server = build_server(service)
    tools = [tool.name for tool in asyncio.run(server.list_tools())]
    print('\n'.join(banner(service, tools, args.http, args.public_only)), file=sys.stderr)  # stdout is the protocol's under stdio
    if not any(page.knowledge_base == 'free' for page in service.ranked_pages()):
        print('corpus-search: WARNING, the free knowledge base is empty: is _data/corpus/raw downloaded?', file=sys.stderr)
    if args.http is None:
        server.run()
        return
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv(REPO / '.env')
    token = os.environ.get(TOKEN_ENV)
    if not token:
        sys.exit(f'set {TOKEN_ENV} in .env first: the HTTP transport never runs without a token')
    uvicorn.run(http_app(server, token), host=args.host, port=args.http, log_level='warning')


if __name__ == '__main__':
    main()
