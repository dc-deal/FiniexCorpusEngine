"""PDF sources → cleaned sections, cut at the PDF's own outline.

Text and outline both come from PyMuPDF, called directly: `page.get_text()` per page, and the
PDF's bookmarks through `get_toc()`. Phase 1 measured why PyMuPDF and not pypdf: pypdf splits
words in one of the papers. LangChain's `PyMuPDFLoader` is not used, although it is the course's
kind of loader. Its package, `langchain-community`, was archived on 2026-06-19, and measured on
all 1,652 pages of the corpus its output is exactly `page.get_text().strip()`, so the wrapper
added a dependency and nothing else.

Cleaning, in order, all measured in phase 1:
1. Lines that repeat on many pages (digits ignored) are running headers and footers. Examples are
   "Access for free at openstax.org" on 311 of 629 pages, and a paper's author line on every page.
2. The page's own number is read from its footer and removed. It is accepted only where it agrees
   with the document's dominant offset between printed and PDF page, so a stray number at the
   bottom of a page is never taken for a page number.
3. Back matter that is a list rather than an explanation (contents, index, reference lists,
   author statements) is left out of the sections, as decided in phase 2.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from backend.ingestion.sections import Section

# Part of every PDF source's fingerprint: raising it re-indexes the PDFs, and only them.
# 2: tables read as rows and columns (2026-09-29).
# 3: pages from their verified readings where one may be served, stitched across page boundaries (phase 5, 2026-11-04).
# 4: a heading set in capitals is found at the start of its line where the outline's own spelling is not on the page
#    (phase 6, 2026-11-06): the Kelly paper's table above "DATA AVAILABILITY STATEMENT" had gone out with the back matter.
# 5: a 'Contents' entry no longer takes the entries nested under it out with it, and a PDF without an outline is cut at the
#    headings its readings found, else page by page (decision 121.b, 2026-11-08): SR 11-7 nests every chapter under
#    'Contents' and came out as its title alone; Regulation T has no outline and came out empty.
# 6: an outline of a single entry counts as none (decision 143.a, 2026-11-09): the EU regulation's one bookmark, its title,
#    made its 83 pages one section, so no hit could name Article 50.
# 7: the views' outline nests a heading with no text of its own over the next one, as loader 6's sections do (line 2's check
#    of 9 Nov found the EU regulation's chapters flat in the export); the chat's sections are unchanged.
# 8: a figure's text keeps its lines and its groups apart, as the reader wrote them (decision 156.a, 2026-11-10;
#    `served_readings.block_text`): 290 figures on 226 free pages had read as one run of words.
# 9: a glossary entry reads "term: definition"; the term stood in its attribute and reached no index (decision 190.a,
#    2026-11-10): 934 entries on 68 free pages.
# 10: a footnote marker reads "[2]" and a numeric superscript "^2", set apart from the number before them (decision 205.a,
#    2026-11-11): "1947–2020" with its note 2 had read "1947–20202", "12.5" squared "12.52"; 302 markers on 197 free pages.
LOADER_VERSION = 10

# A text-layer page goes on from the page before when the page before ends without a closing stop and this one begins in
# lower case; a word hyphenated at the end of a page is rejoined (decision 65.a).
_CLOSING = '.!?:;"\u201d\u2019)]}'

# A line on at least this share of pages (and at least 3 pages) is a running header or footer.
REPEATED_LINE_SHARE = 0.3

# find_tables() also reports a few one-row "tables" (5 of 365 in the two OpenStax books), which
# are single lines of figures, not tables. A table needs at least two rows and two columns.
MIN_TABLE_ROWS = 2
MIN_TABLE_COLUMNS = 2
_GENERATED_HEADER = re.compile(r'\|Col\d+(?=\|)')

# Outline titles whose sections are lists of titles, terms or page numbers rather than text that
# explains anything. Compared case-insensitively against the whole title.
BACK_MATTER_TITLES = {
    'contents', 'index', 'references', 'bibliography', 'data availability statement',
    'author contributions', 'acknowledgments', 'acknowledgements', 'conflict of interest',
    'funding', "publisher's note", 'blank page',
}

# Where a printed page number sits: alone on a line, or at either end of a running footer
# separated by a wide gap, e.g. "456     15 • How to Think about Investing".
_PAGE_ALONE = re.compile(r'^(\d{1,4})$')
_PAGE_LEFT = re.compile(r'^(\d{1,4})\s{3,}\S')
_PAGE_RIGHT = re.compile(r'\S\s{3,}(\d{1,4})$')
_DIGITS = re.compile(r'\d+')
_SPACE = re.compile(r'\s+')


def normalise(text: str) -> str:
    return _SPACE.sub(' ', text).strip()


def table_text(table) -> str:
    """One table as Markdown rows, so its rows and columns survive into the chunks.

    PyMuPDF's `to_markdown()` marks a line break inside a cell as `<br>`, writes `ColN` where
    the table has no header text, and bolds header cells. All three are markup, not content.
    """
    markdown = table.to_markdown().replace('<br>', ' ').replace('**', '')
    return _GENERATED_HEADER.sub('|', markdown).strip()


def _mostly_inside(block, box) -> bool:
    """Whether at least half of a text block lies inside a table's box."""
    overlap = block & box
    return not overlap.is_empty and overlap.get_area() >= 0.5 * block.get_area()


def page_text(page) -> str:
    """The text of one page, with each table as rows instead of one cell per line.

    Measured in phase 2: plain extraction turned the finance book's tables into 1,067 lines of
    bare numbers ("55", "0", "55", "45", ...), with no row or column left to read them by.
    PyMuPDF's own `find_tables()` recovers them, so no table logic is written here. This function
    only puts each table where its cells were: the text blocks that fall inside a table's box are
    replaced by that table, once, at the place of its first block.

    A page without a table is read exactly as before, with `get_text()`.
    """
    tables = [t for t in page.find_tables().tables
              if t.row_count >= MIN_TABLE_ROWS and t.col_count >= MIN_TABLE_COLUMNS]
    if not tables:
        return page.get_text().strip()
    boxes = [pymupdf.Rect(t.bbox) for t in tables]
    parts, placed = [], set()
    for x0, y0, x1, y1, text, _, block_type in page.get_text('blocks'):
        if block_type != 0:  # an image block
            continue
        inside = next((i for i, box in enumerate(boxes) if _mostly_inside(pymupdf.Rect(x0, y0, x1, y1), box)), None)
        if inside is None:
            parts.append(text.strip())
        elif inside not in placed:
            parts.append(table_text(tables[inside]))
            placed.add(inside)
    parts += [table_text(t) for i, t in enumerate(tables) if i not in placed]
    return '\n'.join(part for part in parts if part).strip()


def repeated_lines(pages: list[str]) -> set[str]:
    """Find the running headers and footers: lines on many pages, digits ignored.

    Args:
        pages: The text of every page.

    Returns:
        The set of digit-normalised lines to remove.
    """
    counts = Counter()
    for text in pages:
        counts.update({_DIGITS.sub('#', line.strip()) for line in text.splitlines() if line.strip()})
    threshold = max(3, REPEATED_LINE_SHARE * len(pages))
    return {line for line, count in counts.items() if count >= threshold}


def page_number_candidate(lines: list[str]) -> tuple[int, int] | None:
    """Look for a printed page number in the last lines of a page.

    Args:
        lines: The page's non-empty lines.

    Returns:
        (index of the line, the number), or None.
    """
    for index in range(len(lines) - 1, max(len(lines) - 4, -1), -1):
        line = lines[index].strip()
        for pattern in (_PAGE_ALONE, _PAGE_LEFT, _PAGE_RIGHT):
            match = pattern.search(line)
            if match:
                return index, int(match.group(1))
    return None


def clean_pages(pages: list[str]) -> tuple[list[str], list[int | None]]:
    """Remove running headers, footers and page-number lines; read the printed page numbers.

    Args:
        pages: The raw text of every page, in order (PDF page n is pages[n - 1]).

    Returns:
        The cleaned text of every page, and the printed page number of every page (None where
        the page has no printed number, e.g. before the numbering starts).
    """
    # The page number is looked for BEFORE repeated lines go: a line holding only the number
    # reads '#' on every page once digits are ignored, so it would be removed as repeated first.
    repeated = repeated_lines(pages)
    all_lines, candidates = [], []
    for pdf_page, text in enumerate(pages, start=1):
        lines = [line for line in text.splitlines() if line.strip()]
        all_lines.append(lines)
        candidates.append((pdf_page, page_number_candidate(lines)))

    offsets = Counter(pdf_page - found[1] for pdf_page, found in candidates if found)
    offset = offsets.most_common(1)[0][0] if offsets else None

    cleaned, printed = [], []
    for (pdf_page, found), lines in zip(candidates, all_lines):
        number_line = found[0] if found and offset is not None and pdf_page - found[1] == offset else None
        kept = [line for index, line in enumerate(lines)
                if index != number_line and _DIGITS.sub('#', line.strip()) not in repeated]
        number = pdf_page - offset if offset is not None and pdf_page - offset >= 1 else None
        cleaned.append('\n'.join(kept))
        printed.append(number)
    return cleaned, printed


def section_starts(toc: list[list], pages: list[str]) -> list[tuple[int, int, list[str]]]:
    """Place every outline entry at its page, and where possible at its heading on that page.

    Args:
        toc: PyMuPDF's outline, [level, title, 1-based page].
        pages: The cleaned text of every page.

    Returns:
        (PDF page, character offset in that page, heading path) for every entry, in outline
        order. A title is searched from the previous entry's position on the same page, so
        entries never swap places. An entry whose title is not found starts where the previous
        one on its page did, or at the top of the page.
    """
    starts = []
    path: list[str] = []
    last_page, last_position = 0, 0
    for level, title, page in toc:
        path = path[:level - 1] + [normalise(title)]
        if page < 1 or page > len(pages):
            continue
        floor = last_position if page == last_page else 0
        found = _find_title(pages[page - 1], title, floor)
        position = found if found is not None else floor
        starts.append((page, position, list(path)))
        last_page, last_position = page, position
    # Reading order is the order on the page, not the order of the outline: the finance book's
    # outline ends with a "Blank Page" entry pointing back to page 2, which in outline order made
    # one section span the whole book a second time (3.1 M characters from a 1.6 M book).
    return sorted(starts, key=lambda start: (start[0], start[1]))


def _find_title(page_text: str, title: str, start: int) -> int | None:
    """The offset of a heading in a page's text at or after `start`, across line breaks.

    In the outline's own spelling first, so every heading found before is found where it was. Where that spelling is not on
    the page, in any case as a line of its own: papers set headings in capitals ("DATA AVAILABILITY STATEMENT" for the
    outline's "Data Availability Statement"). Only a whole line, so a sentence that begins with the title's words ("discussions
    of risk follow" for "Discussion") is not taken for the heading. Such a heading line is looked for from `start`, and else
    on the whole page: where the outline's order differs from the page's (the Kelly paper's p. 15 lists Acknowledgments before
    References, the page prints them the other way round), a heading above the previous entry is found where it stands, and
    `section_starts` puts the units in reading order. Measured over the free PDFs: 5 outline entries move, all in the Kelly
    paper (phase 6; the review of 6 Nov found both cases this rule closes).
    """
    words = [re.escape(w) for w in normalise(title).split()]
    if not words:
        return None
    pattern = r'\s+'.join(words)
    exact = re.compile(pattern).search(page_text, start)
    if exact:
        return exact.start()
    heading_line = re.compile('^' + pattern + r'[ \t]*$', re.IGNORECASE | re.MULTILINE)
    match = heading_line.search(page_text, start) or heading_line.search(page_text, 0)
    return match.start() if match else None


def is_back_matter(heading_path: list[str]) -> bool:
    """A unit whose own title is back matter, or that lies under such a title: an index's letters, a reference list's parts.
    A 'Contents' entry is the exception as a parent: an outline may nest the whole document under it (SR 11-7 does)."""
    if not heading_path:
        return False
    return (heading_path[-1].lower() in BACK_MATTER_TITLES
            or any(heading.lower() in BACK_MATTER_TITLES - {'contents'} for heading in heading_path[:-1]))


def joiner(before: str, after: str, marked: bool | None) -> tuple[str, str]:
    """How a piece of one page joins the piece of the next inside a section: (the earlier piece as it now ends, the joint).

    A page the reader marked as going on from the page before joins with a space; so does a text-layer page that starts in lower
    case after a page without a closing stop. A word broken by a hyphen at the page's end is rejoined. Otherwise the pages meet as
    paragraphs. `marked` is the reader's own mark: True or False for a reading, None for a text-layer page."""
    end, start = before.rstrip(), after.lstrip()
    if not end or not start:
        return before, '\n\n'
    lower_start = start[0].islower()
    if end.endswith('-') and len(end) > 1 and end[-2].isalpha() and lower_start:
        return end[:-1], ''
    goes_on = marked if marked is not None else (lower_start and end[-1] not in _CLOSING)
    return (end, ' ') if goes_on else (before, '\n\n')


def _cuts(toc: list[list], pages: list[str]) -> list[tuple[int, list[str], list[tuple[int, int, int]]]]:
    """Every outline entry in reading order with the pieces of page text it covers: (start page, heading path, pieces), a piece
    being (PDF page, begin, stop). A piece is kept only where it holds text, so an entry followed at once by the next one covers
    no page. The one cut behind both the sections and the outline, so the two can never disagree."""
    starts = section_starts(toc, pages)
    cuts = []
    for number, (page, position, path) in enumerate(starts):
        if number + 1 < len(starts):
            end_page, end_position = starts[number + 1][0], starts[number + 1][1]
        else:
            end_page, end_position = len(pages), len(pages[-1])
        pieces = []
        for current in range(page, end_page + 1):
            text = pages[current - 1]
            begin = position if current == page else 0
            stop = end_position if current == end_page else len(text)
            if text[begin:stop].strip():
                pieces.append((current, begin, stop))
        cuts.append((page, path, pieces))
    return cuts


def heading_only(text: str, title: str) -> bool:
    """Whether a section's text is nothing but its own heading: no word beyond the title's (a heading's number in front
    counts as the title's, as '33 Article 33' over 'Article 33')."""
    found = re.findall(r'\w+', text.lower())
    return bool(found) and set(found) <= set(re.findall(r'\w+', title.lower()))


def build_sections(source_id: str, pages: list[str], printed: list[int | str | None],
                   toc: list[list], continues: list[bool | None] | None = None,
                   routes: dict[int, tuple[str, str | None]] | None = None,
                   fold_headings: bool = False) -> list[Section]:
    """Cut the cleaned pages into sections at the outline entries, stitched across page boundaries.

    Text before the first outline entry (cover, title and copyright pages) is dropped, and so
    is back matter. With `fold_headings`, for an outline the readings' headings made (they carry no levels), a section that
    holds nothing but its heading becomes a parent of the next one instead of a section of its own: 'Article 50' over
    'Information on costs and associated charges' (loader 6, decision 143.a).

    Args:
        source_id: The catalog id.
        pages: The cleaned text of every page.
        printed: The printed page number of every page.
        toc: PyMuPDF's outline.
        continues: Per page, the reader's mark that it goes on from the page before (True or
            False), or None for a text-layer page, which joins by rule.
        routes: PDF page -> (route, reading key), carried by each section for its pages.

    Returns:
        The sections, in reading order, numbered from 0.
    """
    continues = continues or [None] * len(pages)
    routes = routes or {}
    sections, parents = [], []
    for _, path, pieces in _cuts(toc, pages):
        if is_back_matter(path):
            parents = []
            continue
        text_so_far, marks = '', []
        for current, begin, stop in pieces:
            piece = pages[current - 1][begin:stop].strip()
            if text_so_far:
                text_so_far, joint = joiner(text_so_far, piece, continues[current - 1] if begin == 0 else False)
                text_so_far += joint
            marks.append((len(text_so_far), current, printed[current - 1]))
            text_so_far += piece
        if fold_headings and text_so_far and heading_only(text_so_far, path[-1]):
            parents.append(path[-1])
            continue
        if text_so_far:
            if parents:
                path, parents = [*path[:-1], *(title for title in parents if title not in path), path[-1]], []
            page_routes = {mark[1]: routes[mark[1]] for mark in marks if mark[1] in routes}
            sections.append(Section(source_id, len(sections), path, text_so_far, pages=marks, routes=page_routes))
    return sections


@dataclass(frozen=True)
class Unit:
    """One entry of a PDF's own outline, as the sections cut it: the order of the source itself (decision 84.a).

    `first_page` is where its heading is; `last_page` where its own text or its last sub-unit's text ends. `indexed` is False for
    back matter, which the chat's index leaves out but the source's order keeps."""
    id: str
    level: int
    title: str
    parent: str | None
    first_page: int
    last_page: int
    indexed: bool


@dataclass
class Outline:
    units: list[Unit]
    page_units: dict[int, list[str]] = field(default_factory=dict)  # PDF page -> the units with own text on it, in reading order


def outline_of(toc: list[list], pages: list[str], fold_headings: bool = False) -> Outline:
    """The PDF's outline as the sections cut it, and for each page the units whose own text lies on it.

    A page where 1.1 ends and 1.2 begins lists both; a page before the first entry, or one without text, lists none. A unit's
    parent is the latest unit before it whose heading path is its own without the last heading. With `fold_headings`, as for
    the sections (loader 6), a unit whose own text is nothing but its heading is the parent of the next one: 'Article 50' over
    'Information on costs and associated charges', so the views nest the outline as the chat's sections do."""
    units, latest, own = [], {}, {}
    page_units: dict[int, list[str]] = {}
    chain: list[Unit] = []  # with fold_headings: the heading-only units above the next one, outermost first
    for number, (start, path, pieces) in enumerate(_cuts(toc, pages)):
        unit_id = f'u{number + 1:03d}'
        parent, level = latest.get(tuple(path[:-1])), len(path)
        if fold_headings and chain:
            parent, level = chain[-1].id, chain[-1].level + 1
        unit = Unit(unit_id, level, path[-1], parent, start, start, not is_back_matter(path))
        units.append(unit)
        if fold_headings and pieces:
            text = ' '.join(pages[page - 1][begin:stop] for page, begin, stop in pieces)
            chain = [*chain, unit] if heading_only(text, path[-1]) and not is_back_matter(path) else []
        latest[tuple(path)] = unit_id
        own[unit_id] = [piece[0] for piece in pieces]
        for page, _, _ in pieces:
            page_units.setdefault(page, []).append(unit_id)
    last = {unit.id: max(own[unit.id], default=unit.first_page) for unit in units}
    for unit in reversed(units):  # a sub-unit always follows its parent, so its last page is final when the parent is reached
        if unit.parent is not None:
            last[unit.parent] = max(last[unit.parent], last[unit.id])
    return Outline([Unit(unit.id, unit.level, unit.title, unit.parent, unit.first_page, last[unit.id], unit.indexed) for unit in units],
                   page_units)


@dataclass
class PdfText:
    """A PDF's pages as the sections are cut from them: cleaned, with served readings in place, and its outline."""
    pages: list[str]
    printed: list[int | str | None]
    continues: list[bool | None]
    routes: dict[int, tuple[str, str | None]]
    toc: list[list]
    # 'bookmarks', 'readings' (the headings its readings found) or 'pages' (one entry a page, for the sections alone)
    toc_source: str = 'bookmarks'

    @property
    def outline_toc(self) -> list[list]:
        """The outline a view groups pages by: none where the entries are only the pages themselves (decision 84.a)."""
        return [] if self.toc_source == 'pages' else self.toc


def read_pdf(path: Path, served: dict | None = None) -> PdfText:
    """Read one PDF's pages and outline the way its sections are built.

    Args:
        path: The PDF file.
        served: PDF page -> what `served_readings.served_pages` gives for it: a page with a
            servable reading takes the reading's quotable text, its printed number and the
            reader's continuation mark; every page listed carries its route. None: the text
            layer alone, as before phase 5.
    """
    with pymupdf.open(path) as document:
        raw_pages = [page_text(page) for page in document]
        toc = document.get_toc() or None
    pages, printed = clean_pages(raw_pages)
    continues: list[bool | None] = [None] * len(pages)
    routes = {}
    for number, entry in (served or {}).items():
        if not 1 <= number <= len(pages):
            continue
        routes[number] = (entry['route'], entry['reading_key'])
        if entry['text'] is not None:
            pages[number - 1] = entry['text']
            printed[number - 1] = entry['printed'] if entry['printed'] is not None else printed[number - 1]
            continues[number - 1] = entry['continues']
    # An outline of one entry names the document, not its parts (the EU regulation of decision 143.a: its title over all 83
    # pages), so it counts as none and the PDF is cut as one without bookmarks (loader 6)
    if toc is not None and len(toc) > 1:
        return PdfText(pages, printed, continues, routes, toc)
    source, made = outline_without_bookmarks(served, printed)
    return PdfText(pages, printed, continues, routes, made, source)


def outline_without_bookmarks(served: dict | None, printed: list) -> tuple[str, list[list]]:
    """An outline for a PDF that has none: the headings its readings found where every page stands on a reading, since then
    no text lies outside the readings' view; else one entry per page, named by its printed number, so nothing is dropped. The
    readings give no heading levels (the contract leaves them to assembly), so every entry is of level 1."""
    served = served or {}
    read = all(served.get(number, {}).get('text') is not None for number in range(1, len(printed) + 1))
    headings = [[1, title, number] for number in range(1, len(printed) + 1) for title in served.get(number, {}).get('headings') or []]
    if read and headings:
        return 'readings', headings
    return 'pages', [[1, f'Page {printed[number - 1] if printed[number - 1] is not None else number}', number]
            for number in range(1, len(printed) + 1)]


def load_pdf_sections(source_id: str, path: Path, served: dict | None = None) -> list[Section]:
    """Load one PDF source into sections; `served` as for `read_pdf`.

    Returns:
        The cleaned sections.
    """
    text = read_pdf(path, served)
    return build_sections(source_id, text.pages, text.printed, text.toc, text.continues, text.routes,
                          fold_headings=text.toc_source == 'readings')


def load_pdf_outline(path: Path, served: dict | None = None) -> Outline:
    """One PDF's own outline over the same pages its sections are cut from; `served` as for `read_pdf`."""
    text = read_pdf(path, served)
    return outline_of(text.outline_toc, text.pages, fold_headings=text.toc_source == 'readings')
