"""The answer key for the page readers: what the publishers' own markup says is printed on a page.

The readers exist for the licensed corpus, where no such markup exists. The free corpus has it, so its pages are the test
bench, and the key depends on no model: a key made by correcting a reading would anchor on the model exactly where
plausible errors survive. The truth files are local and git-ignored, built once from the web edition of the OpenStax books
(aligned to PDF pages through the text layer), from a journal's JATS XML and from an arXiv paper's LaTeXML:

    _work/free/gold/truth/*.json            ten OpenStax pages: prose, formulas, tables, footnotes
    _work/free/gold/truth_papers/*.json     four paper pages: formulas only

This module only reads them into one shape, so that the scoring never sees either file format:

    load_gold(pdf_file, pdf_page) -> PageGold | None
    all_gold() -> [PageGold, ...]
    parse_gold(data) -> PageGold      for one truth file already read

Facts about the files that the shape absorbs (measured 2026-10-30 on those 14 pages):

- A block's `text_md` holds its formulas as `$latex$`, and the script that wrote it dropped the whitespace before closing
  punctuation inside them too, so `$( 1 + r)$` stands for the preview `( 1 + r )`. Prose dollars stay plain.
- A footnote marker is written `^8` in running text and `8 ` at the start of the footnote itself.
- `image` blocks are not in the prose: they are pictures, here two journals printed as images, and their alt text is the
  only truth about them. Their alt text paraphrases the labels ('Cash Debit' for a printed 'Cash DR'), and only its numbers
  match the print, so a raster's gold is the set of numbers in its alt text.
- The footer is not in the OpenStax files. Their even PDF pages carry `OPENSTAX_FOOTER`, their odd pages nothing (3 of 3
  and 7 of 7, read from the PDFs).
- The paper files hold no prose and no tables, and some of the journal paper's inline math is plain text in its XML: the
  formula list of a paper page is not exhaustive, and `placed_by` says how sure its place on the page is.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.configuration import data_paths

GOLD_ROOT = data_paths.FREE_WORKING / 'gold'
TRUTH_FOLDERS = ('truth', 'truth_papers')
OPENSTAX_FOOTER = 'Access for free at openstax.org'
PAPER_FURNITURE = {  # running head and foot, read from the pages' text layer; the folio is the printed label
    'carta_conversano_kelly_criterion_2020.pdf': ('Carta and Conversano Practical Implementation of the Kelly Criterion',
                                                  'Frontiers in Applied Mathematics and Statistics | www.frontiersin.org '
                                                  'October 2020 | Volume 6 | Article 577050'),
}
# This PDF's font prints the source's \mathbb{1} as ⊮ (U+22AE in its text layer, and so by eye on page 12). A reader may write
# what it sees or what it means, with \mathbb{I} a common spelling of the second: (what a reader wrote, what the gold has).
PRINTED_OTHERWISE = {r'\mathbb{1}': (('⊮', '1'), ('I', '1'))}
PROSE_KINDS = {'para', 'heading', 'list_item', 'caption', 'table_title'}
SPACE_BEFORE_PUNCTUATION = re.compile(r'\s+([,.;:!?)])')
FOOTNOTE_MARK_IN_TEXT = re.compile(r'(?<!\S)\^(\w+)')
FOOTNOTE_MARK_AT_START = re.compile(r'^\s*\^?(\d+)\s+')
NUMBER = re.compile(r'\d+(?:,\d{3})*(?:\.\d+)?')


def expand_spans(rows) -> list[list]:
    """Rows of cells with rowspan and colspan as a rectangle: a cell stands at its top-left position, a position it merely
    covers holds None, and a position nothing reaches also holds None. Written here because the two near components stop short:
    page_contract.grid_widths returns only each row's width, and docling-core's TableData.grid needs every cell's offsets already."""
    placed: dict[tuple[int, int], object] = {}
    for row_index, row in enumerate(rows):
        column = 0
        for cell in row:
            while (row_index, column) in placed:
                column += 1
            for down in range(cell.rowspan):
                for across in range(cell.colspan):
                    placed[(row_index + down, column + across)] = None
            placed[(row_index, column)] = cell
            column += cell.colspan
    width = max((column for _, column in placed), default=-1) + 1
    return [[placed.get((row_index, column)) for column in range(width)] for row_index in range(len(rows))]


@dataclass(frozen=True)
class GoldFormula:
    label: str | None
    mathml: str
    latex: str | None
    kind: str = 'inline'  # display, inline, or cell (it stands in a table cell)
    latex_origin: str = 'preview'  # preview: converted from this MathML by a script; author: the author's own LaTeX
    placed_by: str | None = None  # how a paper's formula was placed on the page; None on OpenStax pages
    accepts: tuple[tuple[str, str], ...] = ()  # token pairs that count as equal here: (what a reader wrote, what the gold has)


@dataclass(frozen=True)
class GoldText:
    """Words and formulas in reading order: each segment is ('text', str) or ('math', GoldFormula)."""
    segments: tuple = ()

    @property
    def text(self) -> str:
        """The words, the formulas taken out."""
        return ' '.join(' '.join(value.split()) for kind, value in self.segments if kind == 'text' and value.strip())

    @property
    def formulas(self) -> list[GoldFormula]:
        return [value for kind, value in self.segments if kind == 'math']


@dataclass(frozen=True)
class GoldBlock(GoldText):
    kind: str = 'para'
    starts_mid_block: bool = False  # the block began on the previous page
    ends_mid_block: bool = False  # the block runs on past this page
    marker: str | None = None  # a footnote's own marker, taken off its text


@dataclass(frozen=True)
class GoldCell(GoldText):
    header: bool = False
    rowspan: int = 1
    colspan: int = 1


@dataclass(frozen=True)
class GoldTable:
    rows: tuple[tuple[GoldCell, ...], ...]
    rows_kept: tuple[int, ...] | None = None  # set when the table runs across pages: the rows that stand on this page
    rows_total: int | None = None

    @property
    def cells(self) -> list[GoldCell]:
        return [cell for row in self.rows for cell in row]

    def grid(self) -> list[list[GoldCell | None]]:
        return expand_spans(self.rows)


@dataclass(frozen=True)
class GoldRaster:
    """A picture on the page, known only through the publisher's alt text."""
    alt: str

    @property
    def values(self) -> list[str]:
        """The distinct numbers of the alt text: what can be held against a reading of the picture."""
        return sorted(set(NUMBER.findall(self.alt)))


@dataclass
class PageGold:
    gold_id: str
    pdf_file: str
    pdf_page: int
    printed_label: str | None
    header: str = ''
    footer: str = ''
    prose: list[GoldBlock] = field(default_factory=list)  # paragraphs, list items, headings, captions, in reading order
    display: list[GoldFormula] = field(default_factory=list)
    inline: list[GoldFormula] = field(default_factory=list)  # formulas in running text; those in table cells stay with their table
    tables: list[GoldTable] = field(default_factory=list)
    rasters: list[GoldRaster] = field(default_factory=list)
    footnotes: list[GoldBlock] = field(default_factory=list)
    has_prose: bool = True  # False on a paper page: its file holds formulas only
    unmapped: dict = field(default_factory=dict)  # block kinds this shape does not carry, with their count
    licence: str = ''

    @property
    def starts_mid_block(self) -> bool:
        """The page's first prose block began on the previous page."""
        return bool(self.prose) and self.prose[0].starts_mid_block

    @property
    def ends_mid_block(self) -> bool:
        """The page's last prose block runs on past this page."""
        return bool(self.prose) and self.prose[-1].ends_mid_block

    @property
    def cell_formulas(self) -> list[GoldFormula]:
        return [formula for table in self.tables for cell in table.cells for formula in cell.formulas]

    def all_formulas(self) -> list[GoldFormula]:
        return self.display + self.inline + self.cell_formulas


# ---------------------------------------------------------------- one file into the shape

def _segments(text_md: str | None, math: list[dict], kind: str) -> tuple:
    """Split a block's text at its formulas, in order. A formula that cannot be found in the text raises: the file is not
    what this module assumes, and a silent loss would score against the reader."""
    rest, segments = text_md or '', []
    for entry in math:
        wrapped = SPACE_BEFORE_PUNCTUATION.sub(r'\1', f"${entry['latex_preview']}$")
        at = rest.find(wrapped)
        if at < 0:
            raise ValueError(f'formula not found in its text: {wrapped[:60]}')
        segments.append(('text', FOOTNOTE_MARK_IN_TEXT.sub(r'\1', rest[:at])))
        segments.append(('math', GoldFormula(None, entry['mathml'], entry['latex_preview'], kind)))
        rest = rest[at + len(wrapped):]
    segments.append(('text', FOOTNOTE_MARK_IN_TEXT.sub(r'\1', rest)))
    return tuple(segment for segment in segments if segment[0] == 'math' or segment[1].strip())


def _prose_block(block: dict) -> GoldBlock:
    partial = block.get('partial') or {}
    return GoldBlock(segments=_segments(block.get('text_md'), block.get('math', []), 'inline'), kind=block['kind'],
                     starts_mid_block=bool(partial.get('starts_mid_block')), ends_mid_block=bool(partial.get('ends_mid_block')))


def _footnote(block: dict) -> GoldBlock:
    segments = list(_segments(block.get('text_md'), block.get('math', []), 'inline'))
    marker = None
    if segments and segments[0][0] == 'text':
        match = FOOTNOTE_MARK_AT_START.match(segments[0][1])
        if match:
            marker = match.group(1)
            segments[0] = ('text', segments[0][1][match.end():])
    return GoldBlock(segments=tuple(segments), kind='footnote', marker=marker)


def _table(block: dict) -> GoldTable:
    rows = tuple(tuple(GoldCell(segments=_segments(cell.get('text_md'), cell.get('math', []), 'cell'), header=cell.get('tag') == 'th',
                                rowspan=cell.get('rowspan', 1), colspan=cell.get('colspan', 1))
                       for cell in row['cells']) for row in block['rows'])
    partial = block.get('partial') or {}
    kept = partial.get('rows_kept')
    return GoldTable(rows, tuple(kept) if kept else None, partial.get('rows_total'))


def _display(block: dict) -> GoldFormula:
    """One numbered equation; if it has several math elements they stand on one line of the page's reading."""
    math = block['math']
    return GoldFormula(block.get('eq_number'), ''.join(entry['mathml'] for entry in math),
                       ' '.join(entry['latex_preview'] for entry in math), 'display')


def _parse_openstax(data: dict) -> PageGold:
    page = PageGold(gold_id=data.get('id', ''), pdf_file=data['pdf'], pdf_page=data['pdf_page'], printed_label=data.get('printed_page'),
                    header=data.get('pdf_header', ''), footer=OPENSTAX_FOOTER if data['pdf_page'] % 2 == 0 else '',
                    licence=data.get('licence', ''))
    for block in data['blocks']:
        kind = block['kind']
        if kind in PROSE_KINDS:
            page.prose.append(_prose_block(block))
            page.inline.extend(page.prose[-1].formulas)
        elif kind == 'equation':
            page.display.append(_display(block))
        elif kind == 'table':
            page.tables.append(_table(block))
        elif kind == 'footnote':
            page.footnotes.append(_footnote(block))
            page.inline.extend(page.footnotes[-1].formulas)
        elif kind == 'image':
            page.rasters.append(GoldRaster(block.get('alt', '')))
        elif kind == 'figure':  # its caption is prose, its alt text the only truth about the picture
            page.rasters.append(GoldRaster(block.get('alt', '')))
            if block.get('text_md'):
                page.prose.append(_prose_block(block | {'kind': 'caption'}))
                page.inline.extend(page.prose[-1].formulas)
        else:
            page.unmapped[kind] = page.unmapped.get(kind, 0) + 1
    return page


def _parse_paper(data: dict) -> PageGold:
    header, footer = PAPER_FURNITURE.get(data['pdf'], ('', ''))
    page = PageGold(gold_id=f"{Path(data['pdf']).stem}_p{data['pdf_page']:04d}", pdf_file=data['pdf'], pdf_page=data['pdf_page'],
                    printed_label=data.get('printed_page'), header=header, footer=footer, has_prose=False, licence=data.get('licence', ''))
    for entry in data['formulas']:
        if not entry.get('mathml'):
            page.unmapped['formula_without_mathml'] = page.unmapped.get('formula_without_mathml', 0) + 1
            continue
        origin = 'preview' if 'preview' in entry.get('latex_origin', 'preview') else 'author'
        latex = entry.get('latex') or ''
        accepts = tuple(pair for source, pairs in PRINTED_OTHERWISE.items() if source in latex for pair in pairs)
        formula = GoldFormula(entry.get('label'), entry['mathml'], entry.get('latex'), entry['kind'], origin, entry.get('placed_by'), accepts)
        (page.display if entry['kind'] == 'display' else page.inline).append(formula)
    return page


def parse_gold(data: dict) -> PageGold:
    """One truth file, already read, into the shape; a paper's file is the one that lists formulas."""
    return _parse_paper(data) if 'formulas' in data else _parse_openstax(data)


# ---------------------------------------------------------------- the files

def _truth_files() -> list[Path]:
    return [path for folder in TRUTH_FOLDERS for path in sorted((GOLD_ROOT / folder).glob('*.json')) if not path.name.startswith('_')]


def all_gold() -> list[PageGold]:
    """Every page with gold; an empty list where the local folder does not exist, as in a clone."""
    return [parse_gold(json.loads(path.read_text(encoding='utf-8'))) for path in _truth_files()]


def load_gold(pdf_file: str, pdf_page: int) -> PageGold | None:
    """The gold of one PDF page, or None when the page has none."""
    name = Path(pdf_file).name
    for path in _truth_files():
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('pdf') == name and data.get('pdf_page') == pdf_page:
            return parse_gold(data)
    return None
