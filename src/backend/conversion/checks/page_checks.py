"""Stage 2 of the check flow: a reading against the PDF's own text layer and drawings.

The reader saw only the page image, so the layer is an independent witness: where the two disagree, one of them is
wrong, and this module says where and in which direction. Lacking words is the real suspect. Holding words the layer
lacks is often text in pictures, so it depends on the block they sit in. A number on one side only is always a suspect,
because a digit error barely moves a ratio.

    rendered = render_formulas(parsed_pages)         # KaTeX once per batch of pages
    check = check_page(parsed, pdf_page, rendered)   # no API call, no network
    check.suspicious, check.findings, check.unverifiable, check.as_dict()

What stage 2 cannot check goes to the judge in `unverifiable`: formula bodies drawn as vector paths, raster tables,
figure text inside images (the two planted errors section 3.5 of the design says it misses, pinned by a test).

Text is aligned, never assigned by box, since reader boxes are approximate. Each block is laid over the page's token
stream by greedy string tiling: the longest common run first, claimed tokens masked out, longest blocks first, so moved
boxes and columns do not matter and two identical short blocks cannot claim the same words. Tiling is built on the
stdlib's difflib.SequenceMatcher.find_longest_match. The component checked first was rapidfuzz's
fuzz.partial_ratio_alignment plus Levenshtein.opcodes, as the design proposed. Its gap, measured 2026-10-30: it finds one
window of the block's own length, and opcodes then scatter isolated matches in it, so a block with a sentence dropped
from its middle claims stray words of that sentence and leaves the same words unclaimed after it. rapidfuzz stays for
what it fits: pairing a block's code lines with the layer's.

Console output and logs carry ids and counts: `Finding.detail` holds no page text, the words stand apart in
`Finding.words`, and `as_dict()` leaves them out unless asked.
"""

import ast
import doctest
import difflib
import html.parser
import itertools
import re
import unicodedata
import warnings
from collections import Counter
from dataclasses import asdict, dataclass, field
from functools import cached_property
from statistics import median

import pymupdf
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from backend.conversion.checks import katex_check
from backend.conversion.contract.page_contract import Block, ParsedPage, grid_widths

Box = tuple[float, float, float, float]

# Starting values, to calibrate on the mini pilot: none of them is measured on real page/1 readings yet (2026-10-30).
MISSING_WORDS_SUSPECT = 1  # layer words outside pictures that no block claims: 'Solution:' alone is one word of 325
ADDED_WORDS_ALONE = 3  # reader words the layer lacks, with none missing beside them, that make a block suspect; below this: a tag like 'LO' printed as a picture
DRAWN_SHARE = 0.5  # drawn glyphs per character of the reader's extra words from which those words count as drawn, so unverifiable
ADDED_WORDS_REPLACED = 1  # reader words in a text block that the layer lacks: 'stronger' for 'stricter' is one of 64
PRECISION_LOW = 0.90  # below this with recall near 1, and with the extra words in pictures, the page gets a note
RECALL_NEAR_ONE = 0.98
MIN_LAYER_WORDS = 5  # fewer than this while the reading has READING_HAS_MANY tokens: a scan, or as good as one
READING_HAS_MANY = 20
TILE_FLOORS = (8, 4, 2)  # the longest runs on the page claim first, so a short run cannot break up a long one
BREAKS_IN_A_ROW = 2  # broken bigrams in a row that mean a swap; one alone is a column or float interruption
BOX_PAD_PT = 4.0  # reader boxes are approximate
BAND_PAD_PT = 8.0  # the vertical slack of a formula's band when its label is looked for
GLYPH_MAX_PT = 40.0  # a filled path this small in both directions may be a drawn glyph
RULE_THICKNESS_PT, RULE_LENGTH_PT = 1.0, 12.0  # thinner and longer than this it is a rule, not a minus sign
INDENT_TOLERANCE_CHARS = 0.5
MONOSPACE_SPREAD = 0.05  # the advance widths of a line differ by at most this share in a monospace font
RASTER_SHARE = 0.5  # a table counts as text when the layer holds this share of its tokens inside its box
LINE_FUZZ_MIN = 80  # a misread code line still pairs with its layer line above this rapidfuzz ratio

# Math in the free papers measured 2026-10-30: MTSY, RMTMI, MTEX, MSBM10, CMMI*, CMSY*, CMEX10. The rest are their families.
MATH_FONTS = re.compile(r'math|symbol|cmsy|cmbsy|cmmi|cmex|msbm|msam|mtsy|mtmi|mtex|eufm|eurm|euex|rsfs|wasy|stmary|'
                        r'(?:tx|px)(?:mi|sy|ex)|dingbat|wingding', re.I)
WHITE = 0xFFFFFF
TEXT_FLAGS = pymupdf.TEXTFLAGS_WORDS
PICTURE_CLASSES = {'figure', 'decoration'}
NOT_COMPARED = {'description', 'decoration'}
NO_ORDER_CLASSES = {'table', 'figure', 'formula'}
PYTHON_NAMES = {'python', 'python3', 'py'}
PYTHON_KINDS_SKIPPED = {'console', 'pseudocode', 'config'}
FRAGMENT_STATUS = {'partial', 'truncated_by_source'}

# NFKC leaves curly quotes, dashes and U+2212 alone, and they sit on most pages.
GLYPHS = str.maketrans({'’': "'", '‘': "'", '‚': "'", '‛': "'", '′': "'", '“': '"', '”': '"', '„': '"', '‟': '"',
                        '‐': '-', '‑': '-', '‒': '-', '–': '-', '—': '-', '―': '-', '−': '-', '﹣': '-'})
EDGE = '.,;:!?()[]{}"\'•·†‡§¶|«»‹›'
CURRENCY = '$€£¥'
AMOUNT_GAP = re.compile(rf'([{re.escape(CURRENCY)}])\s+(?=\d)')
PERCENT_GAP = re.compile(r'(?<=\d)\s+%')
PURE_NUMBER = re.compile(rf'^[-+({re.escape(CURRENCY)}]*\d[\d.,]*[%)]*$')
LINE_END_HYPHENS = ('-', '‐', '\u00ad')
LATEX_ENVIRONMENT = re.compile(r'\\(?:begin|end)\s*\{[^}]*\}(?:\{[^}]*\})?')
LATEX_COMMAND = re.compile(r'\\([A-Za-z]+)')
LATEX_NAMES_PRINTED = {'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'log', 'ln', 'lg', 'exp', 'min', 'max', 'lim', 'sup', 'inf',
                       'det', 'gcd', 'arg', 'dim', 'ker', 'deg', 'hom', 'Pr', 'sinh', 'cosh', 'tanh', 'arcsin', 'arccos', 'arctan'}
LATEX_LARGE_OPERATORS = {'sum': 'Σ', 'prod': 'Π'}


@dataclass(frozen=True)
class LayerWord:
    """One word of the text layer, in stream order. Untrusted words are math or broken encoding: evidence, not words."""
    token: str
    box: Box
    font: str
    line: int
    alias: str | None = None  # the other accepted form of a word joined at a line-end hyphen
    trusted: bool = True
    hidden: bool = False  # white or fully transparent: claimable, but a vision reader cannot be asked to see it


@dataclass(frozen=True)
class Finding:
    kind: str
    block: str | None
    detail: str
    severity: str  # 'suspect' or 'note'
    words: tuple[str, ...] = ()  # the page words behind it, kept out of `detail` so that a log stays free of page text


@dataclass(frozen=True)
class Unverifiable:
    block: str
    cls: str
    why: str  # formula_body, inline_math, raster_table, figure_text, no_layer


@dataclass
class BlockCheck:
    id: str
    cls: str
    coverage: float | None = None
    precision: float | None = None
    order_ok: bool | None = None
    snapped: Box | None = None
    iou: float | None = None
    vector_glyphs: int | None = None  # small filled paths inside the box: drawn math, a number for now
    math_symbols: int | None = None  # the symbols of its MathML, to set against vector_glyphs
    label_ok: bool | None = None
    katex_ok: bool | None = None
    indent_lines: int | None = None  # code lines whose indentation could be compared
    grid_reader: tuple[int, int] | None = None
    grid_found: tuple[int, int] | None = None


@dataclass
class PageCheck:
    has_layer: bool
    recall: float | None = None
    precision: float | None = None
    layer_only: list[str] = field(default_factory=list)
    reader_only: list[str] = field(default_factory=list)
    numbers_layer_only: list[str] = field(default_factory=list)  # outside pictures: these are suspects
    numbers_reader_only: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    blocks: list[BlockCheck] = field(default_factory=list)
    unverifiable: list[Unverifiable] = field(default_factory=list)

    @property
    def suspicious(self) -> bool:
        return any(finding.severity == 'suspect' for finding in self.findings)

    def as_dict(self, words: bool = False) -> dict:
        """What a stored record keeps: ids, counts and ratios, no page text. words=True adds the words themselves, for a
        record that lies beside the reading in the git-ignored data folder and never reaches a console or a log."""
        record = {'has_layer': self.has_layer, 'suspicious': self.suspicious,
                  'recall': _rounded(self.recall), 'precision': _rounded(self.precision),
                  'counts': {'layer_only': len(self.layer_only), 'reader_only': len(self.reader_only),
                             'numbers_layer_only': len(self.numbers_layer_only),
                             'numbers_reader_only': len(self.numbers_reader_only)},
                  'findings': [{'kind': finding.kind, 'block': finding.block, 'detail': finding.detail,
                                'severity': finding.severity} for finding in self.findings],
                  'blocks': [asdict(block) for block in self.blocks],
                  'unverifiable': [asdict(item) for item in self.unverifiable]}
        if words:
            for name in ('layer_only', 'reader_only', 'numbers_layer_only', 'numbers_reader_only'):
                record[name] = list(getattr(self, name))
            for row, finding in zip(record['findings'], self.findings):
                row['words'] = list(finding.words)
        return record


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


# ---------------------------------------------------------------- the shared normaliser

def _normalise(text: str) -> str:
    """NFKC, one quote and one dash, without soft hyphens, zero-width and control characters."""
    text = unicodedata.normalize('NFKC', text).translate(GLYPHS)
    return ''.join(ch for ch in text if ch.isspace() or unicodedata.category(ch) not in ('Cc', 'Cf'))


def tokens_of(text: str) -> list[str]:
    """The words of a text as both sides and scoring compare them. Case stays: alignment folds it, scoring may not."""
    clean = PERCENT_GAP.sub('%', AMOUNT_GAP.sub(r'\1', _normalise(text)))
    tokens = (word.strip(EDGE) for word in clean.split())
    return [token for token in tokens if any(ch.isalnum() or ch in '%' or ch in CURRENCY for ch in token)]


def _key(token: str) -> str:
    return token.casefold()


def _loose(token: str) -> str:
    """A token without its punctuation, for a word the two sides split differently. A number keeps its separators:
    3,400 and 3.400 are different numbers."""
    if PURE_NUMBER.match(token):
        return ''.join(ch for ch in token if ch.isdigit() or ch in '.,')
    return ''.join(ch for ch in token.casefold() if ch.isalnum())


def _has_digit(token: str) -> bool:
    return any(ch.isdigit() for ch in token)


# ---------------------------------------------------------------- geometry

def _centre(box: Box) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _holds(box: Box, point: tuple[float, float], pad: float = 0.0) -> bool:
    return box[0] - pad <= point[0] <= box[2] + pad and box[1] - pad <= point[1] <= box[3] + pad


def _area(box: Box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _intersection(one: Box, other: Box) -> float:
    return max(0.0, min(one[2], other[2]) - max(one[0], other[0])) * max(0.0, min(one[3], other[3]) - max(one[1], other[1]))


def _iou(one: Box, other: Box) -> float:
    inter = _intersection(one, other)
    union = _area(one) + _area(other) - inter
    return inter / union if union else 0.0


def _union(boxes: list[Box]) -> Box | None:
    if not boxes:
        return None
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


# ---------------------------------------------------------------- the text layer

@dataclass
class _RawWord:
    """A word as it is built from pymupdf's rawdict, with what the checks need of its characters."""
    line: int
    text: str = ''
    box: Box | None = None
    baseline: float = 0.0
    math: bool = False
    visible: bool = False
    fonts: Counter = field(default_factory=Counter)
    advances: list[float] = field(default_factory=list)

    def add(self, char: dict, font: str, math_font: bool, hidden: bool) -> None:
        ch, x0, y0, x1, y1 = char['c'], *char['bbox']
        box = self.box
        self.box = (x0, y0, x1, y1) if box is None else (min(box[0], x0), min(box[1], y0), max(box[2], x1), max(box[3], y1))
        if not self.text:
            self.baseline = char['origin'][1]
        self.text += ch
        self.fonts[font] += 1
        self.advances.append(x1 - x0)
        self.visible = self.visible or not hidden
        # A digit in CMR beside a letter in CMMI is math; a minus in Symbol before '5%' does not make that word math.
        self.math = self.math or (math_font and ch.isalnum())


def _raw_words(page: pymupdf.Page, bad_fonts: tuple[str, ...]) -> list[_RawWord]:
    """Per span, because font trust is decided per span: one line can hold prose and math. pymupdf's 'words' output has
    no fonts, and its boxes would have to be mapped back onto the spans, so this reads rawdict once instead."""
    bad = {name.casefold() for name in bad_fonts}
    words, number = [], 0
    for block in page.get_text('rawdict', flags=TEXT_FLAGS)['blocks']:
        for line in block.get('lines', []):
            number += 1
            current = None
            for span in line['spans']:
                font = span['font'].split('+')[-1]
                math_font = MATH_FONTS.search(font) is not None or font.casefold() in bad
                hidden = span.get('alpha', 255) == 0 or span['color'] == WHITE
                for char in span['chars']:
                    if char['c'].isspace():
                        current = None
                        continue
                    if current is None:
                        current = _RawWord(line=number)
                        words.append(current)
                    current.add(char, font, math_font, hidden)
    return words


def _is_garbled(text: str) -> bool:
    return any(ch == '\ufffd' or unicodedata.category(ch) == 'Co' for ch in text)


def _joins(word: _RawWord, following: _RawWord | None) -> bool:
    """A word broken at a line end: it ends in a hyphen, and the next word opens the next line, below and to the left."""
    if following is None or word.line == following.line or word.math or following.math:
        return False
    if not word.text.endswith(LINE_END_HYPHENS) or not word.text[:-1][-1:].isalnum() or not following.text[:1].isalnum():
        return False
    height = word.box[3] - word.box[1]
    return following.box[1] > word.box[1] and following.box[1] - word.box[3] < 2 * height and following.box[0] < word.box[2]


def _joined(word: _RawWord, following: _RawWord) -> tuple[str, str]:
    """(token, alias). Stric-ter becomes stricter, Coca-Cola keeps its hyphen; both forms are accepted either way."""
    head, tail = word.text[:-1], following.text
    closed, hyphened = (tokens_of(head + tail) or [head + tail])[0], (tokens_of(f'{head}-{tail}') or [f'{head}-{tail}'])[0]
    return (closed, hyphened) if tail[0].islower() else (hyphened, closed)


def _merge_amounts(words: list[LayerWord]) -> list[LayerWord]:
    """The same rule as tokens_of for what the layer holds as two words: '$' '50,000' and '5' '%'."""
    merged = []
    for word in words:
        last = merged[-1] if merged else None
        if last is not None and last.line == word.line and last.trusted == word.trusted:
            if (last.token in tuple(CURRENCY) and word.token[0].isdigit()) or (word.token == '%' and last.token[-1].isdigit()):
                merged[-1] = LayerWord(last.token + word.token, _union([last.box, word.box]), last.font, last.line,
                                       trusted=last.trusted, hidden=last.hidden and word.hidden)
                continue
        merged.append(word)
    return merged


def _layer_from(raw: list[_RawWord]) -> list[LayerWord]:
    words, index = [], 0
    while index < len(raw):
        word = raw[index]
        following = raw[index + 1] if index + 1 < len(raw) else None
        font = word.fonts.most_common(1)[0][0]
        if _joins(word, following):
            token, alias = _joined(word, following)
            words.append(LayerWord(token, _union([word.box, following.box]), font, word.line, alias=alias,
                                   hidden=not (word.visible or following.visible)))
            index += 2
            continue
        tokens = tokens_of(word.text)
        if tokens:
            words.append(LayerWord(tokens[0], word.box, font, word.line, trusted=not (word.math or _is_garbled(word.text)),
                                   hidden=not word.visible))
        index += 1
    return _merge_amounts(words)


def layer_words(page: pymupdf.Page, bad_fonts: tuple[str, ...] = ()) -> list[LayerWord]:
    """The words of the page's text layer in stream order. bad_fonts names fonts known to extract as garbage."""
    return _layer_from(_raw_words(page, tuple(bad_fonts)))


# ---------------------------------------------------------------- drawn evidence

def _is_glyph(drawing: dict) -> bool:
    """A drawn glyph is a small filled outline. A fraction bar is one plain rectangle, a table rule a long thin shape;
    a tall bracket is an outline of 20.6 pt (both measured on OpenStax pages, 2026-10-30)."""
    rect, items = drawing['rect'], drawing['items']
    if drawing.get('fill') is None or max(rect.width, rect.height) >= GLYPH_MAX_PT or (len(items) == 1 and items[0][0] == 're'):
        return False
    return not (min(rect.width, rect.height) < RULE_THICKNESS_PT and max(rect.width, rect.height) >= RULE_LENGTH_PT)


class _Drawn:
    """The page's drawings, images and tables, read only when a check needs them: they cost time on a busy page."""

    def __init__(self, page: pymupdf.Page) -> None:
        self.page = page

    @cached_property
    def glyphs(self) -> list[Box]:
        return [tuple(drawing['rect']) for drawing in self.page.get_drawings() if _is_glyph(drawing)]

    @cached_property
    def images(self) -> list[Box]:
        return [tuple(info['bbox']) for info in self.page.get_image_info()]

    @cached_property
    def tables(self) -> list:
        return list(self.page.find_tables().tables)

    def glyphs_in(self, box: Box, pad: float = 0.0) -> list[Box]:
        return [glyph for glyph in self.glyphs if _holds(box, _centre(glyph), pad)]


class _MathMLSymbols(html.parser.HTMLParser):
    """Counts what MathML prints: KaTeX puts the LaTeX source in an annotation, which is not printed."""
    PRINTED = {'mi', 'mn', 'mo', 'mtext', 'ms'}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.open: list[str] = []
        self.count = 0

    def handle_starttag(self, tag, attrs):
        self.open.append(tag)

    def handle_endtag(self, tag):
        if tag in self.open:
            while self.open.pop() != tag:
                pass

    def handle_data(self, data):
        if self.open and self.open[-1] in self.PRINTED and 'annotation' not in self.open:
            self.count += sum(1 for ch in data if not ch.isspace() and unicodedata.category(ch) != 'Cf')


def _symbols_in(mathml: str) -> int:
    parser = _MathMLSymbols()
    parser.feed(mathml)
    return parser.count


def _latex_symbol(match: re.Match) -> str:
    """A LaTeX command as what it prints, where that is a letter: the layer holds σ, the source says \\sigma."""
    name = match.group(1)
    if name in LATEX_NAMES_PRINTED:
        return f' {name} '
    if name in LATEX_LARGE_OPERATORS:
        return LATEX_LARGE_OPERATORS[name]
    base = name.removeprefix('var')
    case = 'CAPITAL' if base[0].isupper() else 'SMALL'
    try:
        return unicodedata.lookup(f'GREEK {case} LETTER {base.upper()}')
    except KeyError:
        return ' '


def _math_text(latex: str) -> str:
    """The letters and digits a LaTeX source prints, folded. A regex is enough here: nothing but LaTeX passes through it,
    and latex2mathml, the library checked (a docling-core dependency), is not a declared one."""
    source = LATEX_COMMAND.sub(_latex_symbol, LATEX_ENVIRONMENT.sub(' ', latex))
    return ''.join(ch for ch in _normalise(source).casefold() if ch.isalnum())


# ---------------------------------------------------------------- the reader's side

@dataclass
class _Reading:
    """One block's tokens on their way through the alignment."""
    block: Block
    box: Box | None
    tokens: list[str] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)
    optional: list[bool] = field(default_factory=list)  # a marker or a callout: no penalty when the layer lacks it
    matches: list[int | None] = field(default_factory=list)

    def add(self, tokens: list[str], aliases: dict, optional: bool = False) -> None:
        self.tokens.extend(tokens)
        self.keys.extend(aliases.get(_key(token), _key(token)) for token in tokens)
        self.optional.extend([optional] * len(tokens))
        self.matches.extend([None] * len(tokens))

    def unmatched_runs(self) -> list[tuple[int, int]]:
        runs, start = [], None
        for index, match in enumerate(self.matches + [0]):
            if match is None and start is None:
                start = index
            elif match is not None and start is not None:
                runs.append((start, index))
                start = None
        return runs

    def neighbour(self, index: int) -> int | None:
        """Where the layer should hold this token, judged from the nearest matched token of the block."""
        for distance in range(1, len(self.matches)):
            if index - distance >= 0 and self.matches[index - distance] is not None:
                return self.matches[index - distance] + distance
            if index + distance < len(self.matches) and self.matches[index + distance] is not None:
                return self.matches[index + distance] - distance
        return None


def _block_math(block: Block) -> list[str]:
    """The inline math of a block, table cells included."""
    math = list((block.inline or {}).get('math', []))
    for row in block.rows or []:
        for cell in row:
            math.extend((cell.inline or {}).get('math', []))
    return math


def _attribute_tokens(block: Block, body: list[str]) -> list[str]:
    """What the contract keeps in an attribute although it is printed: a marker, a heading's number, a caption's label."""
    tokens = []
    for name in ('marker', 'number', 'label'):
        if name == 'label' and block.cls == 'formula':
            continue
        printed = tokens_of(block.attrs.get(name, ''))
        keys, body_keys = [_key(token) for token in printed], [_key(token) for token in body]
        inside = any(body_keys[start:start + len(keys)] == keys for start in range(len(body_keys) - len(keys) + 1))
        if printed and not inside:
            tokens.extend(printed)
    return tokens


def _body_tokens(block: Block) -> list[str]:
    if block.cls == 'code':
        return tokens_of(block.code or '')
    if block.cls == 'table':
        return [token for row in block.rows or [] for cell in row for token in tokens_of((cell.inline or {}).get('plain', cell.text))]
    if block.cls == 'figure':
        return tokens_of(block.body)
    if block.inline is not None:
        return tokens_of(block.inline['plain'])
    return []


# ---------------------------------------------------------------- alignment

class _Stream:
    """The page's trusted tokens in stream order, with who has claimed what."""

    def __init__(self, words: list[LayerWord]) -> None:
        self.words = words
        self.keys = [_key(word.token) for word in words]
        self.owner: list[_Reading | None] = [None] * len(words)
        self.masked = list(self.keys)
        self.free: dict[str, list[int]] = {}
        for index, key in enumerate(self.keys):
            self.free.setdefault(key, []).append(index)
        self._matcher: difflib.SequenceMatcher | None = None

    def claim(self, index: int, reading: _Reading) -> None:
        self.owner[index] = reading
        self.masked[index] = '\0'
        self.free[self.keys[index]].remove(index)
        self._matcher = None

    def is_free(self, index: int) -> bool:
        return 0 <= index < len(self.words) and self.owner[index] is None

    def longest_run(self, reading: _Reading, start: int, stop: int) -> difflib.Match:
        if self._matcher is None:
            self._matcher = difflib.SequenceMatcher(None, [], self.masked, autojunk=False)
        self._matcher.set_seq1(reading.keys)
        return self._matcher.find_longest_match(start, stop, 0, len(self.masked))


def _claim_runs(reading: _Reading, stream: _Stream, floor: int) -> None:
    """Claim every run of at least `floor` tokens that this block and the free stream share, longest first."""
    while True:
        best = None
        for start, stop in reading.unmatched_runs():
            if stop - start >= floor:
                run = stream.longest_run(reading, start, stop)
                if run.size >= floor and (best is None or run.size > best.size):
                    best = run
        if best is None:
            return
        for offset in range(best.size):
            reading.matches[best.a + offset] = best.b + offset
            stream.claim(best.b + offset, reading)


def _claim_singles(reading: _Reading, stream: _Stream, optional: bool, box: Box | None = None) -> None:
    """Lone tokens take the free copy nearest to where their neighbours say they belong."""
    for index, key in enumerate(reading.keys):
        if reading.matches[index] is not None or reading.optional[index] != optional:
            continue
        free = stream.free.get(key, [])
        if box is not None:
            free = [position for position in free if _holds(box, _centre(stream.words[position].box), BOX_PAD_PT)]
        if free:
            expected = reading.neighbour(index)
            position = free[0] if expected is None else min(free, key=lambda candidate: abs(candidate - expected))
            reading.matches[index] = position
            stream.claim(position, reading)


def _claim_split_words(reading: _Reading, stream: _Stream) -> int:
    """A word the two sides split differently, or that differs in punctuation only: 'Com pany', 'risk.' '3', 'U.S' 'US'.
    Whitespace in a text layer is a guess of the PDF's producer, so this is not a reading error. Returns how many."""
    repaired = 0
    for start, stop in reading.unmatched_runs():
        for index in range(start, stop):
            if reading.matches[index] is not None:
                continue
            expected = reading.neighbour(index)
            target = _loose(reading.tokens[index])
            if target and _claim_layer_parts(reading, stream, index, target, expected):
                repaired += 1
                continue
            # the other way round: several reader tokens against one layer token
            text = target
            for length in range(2, min(4, stop - index) + 1):
                if reading.matches[index + length - 1] is not None:
                    break
                text += _loose(reading.tokens[index + length - 1])
                position = _free_token_with(stream, text, expected)
                if position is not None:
                    stream.claim(position, reading)
                    for offset in range(length):
                        reading.matches[index + offset] = position
                    repaired += 1
                    break
    return repaired


def _free_token_with(stream: _Stream, text: str, expected: int | None) -> int | None:
    """The free layer token that reads `text` once its punctuation is gone, nearest to where it is expected."""
    candidates = [index for index, word in enumerate(stream.words) if stream.owner[index] is None and _loose(word.token) == text]
    if not candidates:
        return None
    return candidates[0] if expected is None else min(candidates, key=lambda candidate: abs(candidate - expected))


def _claim_layer_parts(reading: _Reading, stream: _Stream, index: int, target: str, expected: int | None) -> bool:
    """One reader token against one to four neighbouring free layer tokens."""
    starts = [position for position, word in enumerate(stream.words)
              if stream.owner[position] is None and target.startswith(_loose(word.token) or '\0')]
    if expected is not None:
        starts.sort(key=lambda candidate: abs(candidate - expected))
    for start in starts:
        text = ''
        for length in range(1, 5):
            if not stream.is_free(start + length - 1):
                break
            text += _loose(stream.words[start + length - 1].token)
            if text == target:
                reading.matches[index] = start
                for offset in range(length):
                    stream.claim(start + offset, reading)
                return True
            if not target.startswith(text):
                break
    return False


def _align(readings: list[_Reading], stream: _Stream) -> int:
    """Lay every block over the stream; figures come last and only inside their own box, so that a chart's labels cannot
    claim a word a paragraph left out. Returns how many words were split differently on the two sides."""
    text_readings = sorted((reading for reading in readings if reading.block.cls != 'figure'),
                           key=lambda reading: len(reading.tokens), reverse=True)
    for floor in TILE_FLOORS:
        for reading in text_readings:
            _claim_runs(reading, stream, floor)
    for reading in text_readings:
        _claim_singles(reading, stream, optional=False)
    repaired = sum(_claim_split_words(reading, stream) for reading in text_readings)
    for reading in text_readings:
        _claim_singles(reading, stream, optional=True)
    for reading in readings:
        if reading.block.cls == 'figure':
            _claim_singles(reading, stream, optional=False, box=reading.box)
    return repaired


def _longest_break_run(matches: list[int | None]) -> int:
    """Broken bigrams in a row, by rank among the block's own claimed tokens: what lies between them on the page
    (math, a word another block claims, a dropped word) does not break anything."""
    ranks = {position: rank for rank, position in enumerate(sorted({match for match in matches if match is not None}))}
    run = longest = 0
    for left, right in itertools.pairwise(matches):
        if left is None or right is None or ranks[right] - ranks[left] in (0, 1):
            run = 0
        else:
            run += 1
            longest = max(longest, run)
    return longest


# ---------------------------------------------------------------- one page

@dataclass
class _Run:
    """Everything one page's check works on."""
    parsed: ParsedPage
    page: pymupdf.Page
    rendered: dict | None
    raw: list[_RawWord]
    stream: _Stream
    untrusted: list[LayerWord]
    aliases: dict
    drawn: _Drawn
    boxes: dict
    readings: list[_Reading] = field(default_factory=list)
    raster_tables: set = field(default_factory=set)
    findings: list[Finding] = field(default_factory=list)
    unverifiable: list[Unverifiable] = field(default_factory=list)

    def find(self, kind: str, block: str | None, detail: str, severity: str = 'suspect', words=()) -> None:
        self.findings.append(Finding(kind, block, detail, severity, tuple(words)))

    def unverified(self, block: Block, why: str) -> None:
        self.unverifiable.append(Unverifiable(block.id, block.cls, why))

    def smallest_block_at(self, point: tuple[float, float]) -> Block | None:
        holding = [block for block in self.parsed.blocks if block.id in self.boxes and _holds(self.boxes[block.id], point)]
        return min(holding, key=lambda block: _area(self.boxes[block.id]), default=None)

    def is_picture(self, block: Block | None) -> bool:
        return block is not None and (block.cls in PICTURE_CLASSES or block.id in self.raster_tables)


def _boxes_in_points(parsed: ParsedPage, page: pymupdf.Page) -> dict:
    width, height = (int(part) for part in parsed.front['image_size'].split('x'))
    x_scale, y_scale = page.rect.width / width, page.rect.height / height
    return {block.id: (block.bbox[0] * x_scale, block.bbox[1] * y_scale, block.bbox[2] * x_scale, block.bbox[3] * y_scale)
            for block in parsed.blocks if block.bbox is not None}


def _is_raster_table(block: Block, tokens: list[str], run: _Run) -> bool:
    """The reader's raster flag is a guess from pixels, so the layer decides: words of the table inside its box make it
    text whatever the flag says, and no such words with an image under the box make it raster."""
    box = run.boxes[block.id]
    inside = Counter(key for key, word in zip(run.stream.keys, run.stream.words) if _holds(box, _centre(word.box)))
    shared = sum((inside & Counter(_key(token) for token in tokens)).values())
    flagged = block.attrs.get('raster') == '1'
    if tokens and shared >= RASTER_SHARE * len(tokens):
        if flagged:
            run.find('raster_flag_wrong', block.id, 'marked raster, but the layer holds its words: compared as text', 'note')
        return False
    if flagged:
        return True
    if any(_intersection(box, image) > 0.5 * _area(box) for image in run.drawn.images):
        run.find('raster_flag_wrong', block.id, 'not marked raster, but it lies on an image without layer words', 'note')
        return True
    return False


def _prepare_readings(run: _Run) -> None:
    for block in run.parsed.blocks:
        if block.cls in NOT_COMPARED or block.cls == 'formula':
            continue
        body = _body_tokens(block)
        if block.cls == 'table' and _is_raster_table(block, body, run):
            run.raster_tables.add(block.id)
            continue
        if not body and not block.attrs.get('marker'):
            continue
        reading = _Reading(block, run.boxes.get(block.id))
        reading.add(_attribute_tokens(block, body), run.aliases, optional=True)
        reading.add(body, run.aliases)
        if block.callouts:
            reading.add([str(mark) for marks in block.callouts.values() for mark in marks], run.aliases, optional=True)
        run.readings.append(reading)


def _claim_formula_labels(run: _Run) -> dict:
    """A label stands in the formula's vertical band, usually to its right. Claimed first, by position, because the same
    number can stand in prose as well: 'Figure 6.3' beside equation 6.3 on the worked example."""
    outcome = {}
    for block in run.parsed.blocks:
        label = block.attrs.get('label') if block.cls == 'formula' else None
        if not label:
            continue
        box = run.boxes[block.id]
        reading = _Reading(block, box)
        reading.add(tokens_of(label), run.aliases)
        band = [index for index, word in enumerate(run.stream.words)
                if run.stream.owner[index] is None and box[1] - BAND_PAD_PT <= _centre(word.box)[1] <= box[3] + BAND_PAD_PT]
        for at, key in enumerate(reading.keys):
            found = [index for index in band if run.stream.keys[index] == key and run.stream.owner[index] is None]
            if found:
                position = max(found, key=lambda index: run.stream.words[index].box[0])  # the rightmost one
                reading.matches[at] = position
                run.stream.claim(position, reading)
        outcome[block.id] = None not in reading.matches
        if not outcome[block.id]:
            run.find('formula_label', block.id, 'the label does not stand in the layer in the band of the formula', words=[label])
        run.readings.append(reading)
    return outcome


def _math_owners(run: _Run) -> list[tuple[Box, set]]:
    """The boxes that hold math on this page, each with the characters its math prints."""
    owners = []
    for block in run.parsed.blocks:
        math = [block.body] if block.cls == 'formula' else _block_math(block)
        if math and block.id in run.boxes:
            owners.append((run.boxes[block.id], set(''.join(_math_text(latex) for latex in math))))
    return owners


def _is_credited(word: LayerWord, owners: list[tuple[Box, set]], page_math: list[str]) -> bool:
    """The layer sometimes holds math as garbled words, which prose does not contain. A token is credited when its
    characters occur in the math of the block it stands in. Elsewhere on the page a word is credited when it stands in a
    formula as it is; a number is not: worked examples repeat prose numbers in formulas, so a page-wide credit would
    hide the '$100,000' dropped from a paragraph when equation 6.4 happens to use it (page 179)."""
    text = ''.join(ch for ch in _normalise(word.token).casefold() if ch.isalnum())
    if not text:
        return False
    centre = _centre(word.box)
    if any(_holds(box, centre, BOX_PAD_PT) and set(text) <= chars for box, chars in owners):
        return True
    return not _has_digit(text) and any(text in math for math in page_math)


@dataclass
class _Leftover:
    word: LayerWord
    index: int
    block: Block | None
    picture: bool


def _leftovers(run: _Run) -> tuple[list[_Leftover], int]:
    """The layer tokens no block claims, each attributed to the block it lies in or, failing that, to the one claiming the
    token before it. Credited and hidden tokens drop out. Returns them and how many hidden ones were left unread."""
    owners = _math_owners(run)
    page_math = [_math_text(latex) for block in run.parsed.blocks
                 for latex in ([block.body] if block.cls == 'formula' else _block_math(block))]
    leftovers, hidden, last_owner = [], 0, None
    for index, word in enumerate(run.stream.words):
        owner = run.stream.owner[index]
        if owner is not None:
            last_owner = owner.block
            continue
        if word.hidden:
            hidden += 1
            continue
        if _is_credited(word, owners, page_math):
            continue
        at = run.smallest_block_at(_centre(word.box))
        leftovers.append(_Leftover(word, index, at or last_owner, run.is_picture(at)))
    return leftovers, hidden


def _is_drawn(run: _Run, block: str, tokens: list[str]) -> bool:
    """Whether the block's box holds enough drawn glyphs to print these words: math the reader wrote as text, or a table's
    cells drawn as paths (the free page 393, measured 2026-10-30). Nothing to compare them with, so the judge's."""
    box = run.boxes.get(block)
    return box is not None and len(run.drawn.glyphs_in(box, BOX_PAD_PT / 2)) >= DRAWN_SHARE * sum(len(token) for token in tokens)


def _glued_to_math(layer: str, reader: str, chars: set) -> bool:
    """The layer glues a symbol to the next word ('y-intercept', 'g∗is') where the reader rightly writes \\(y\\)-intercept. One side
    then holds the word and the other the whole. They are a match if the rest is made of what the block's math prints."""
    if not reader or layer == reader or not (layer.startswith(reader) or layer.endswith(reader)):
        return False
    rest = layer[len(reader):] if layer.startswith(reader) else layer[:-len(reader)]
    letters = {ch for ch in _normalise(rest).casefold() if ch.isalnum()}
    return bool(letters) and letters <= chars


def _credit_glued_math(leftovers: list[_Leftover], reader_only: list[tuple[_Reading, str]]) -> tuple[list, list]:
    remaining, kept = list(reader_only), []
    for item in leftovers:
        partner = next((pair for pair in remaining if (item.block is None or pair[0].block is item.block) and _glued_to_math(
            _key(item.word.token), _key(pair[1]), set(''.join(_math_text(latex) for latex in _block_math(pair[0].block))))), None)
        if partner is None:
            kept.append(item)
        else:
            remaining.remove(partner)
    return kept, remaining


def _report_text(run: _Run, leftovers: list[_Leftover], reader_only: list[tuple[_Reading, str]], check: PageCheck) -> None:
    """The direction matters: lacking words is the suspect, extra words depend on the block they sit in."""
    text_leftovers = [item for item in leftovers if not item.picture]
    missing: dict = {}
    for item in text_leftovers:
        missing.setdefault(item.block.id if item.block else None, []).append(item.word.token)
    extra: dict = {}
    for reading, token in reader_only:
        if reading.block.cls != 'figure':
            extra.setdefault(reading.block.id, []).append(token)
    total_missing = sum(not _has_digit(token) for tokens in missing.values() for token in tokens)
    for block, tokens in missing.items():
        words, numbers = [t for t in tokens if not _has_digit(t)], [t for t in tokens if _has_digit(t)]
        if words:
            run.find('words_missing', block, f'{len(words)} layer words no block claims',
                     'suspect' if total_missing >= MISSING_WORDS_SUSPECT else 'note', words[:30])
        if numbers:
            run.find('number_missing', block, f'{len(numbers)} numbers in the layer only', words=numbers[:30])
    for block, tokens in extra.items():
        words, numbers = [t for t in tokens if not _has_digit(t)], [t for t in tokens if _has_digit(t)]
        if block not in missing and _is_drawn(run, block, tokens):
            run.find('text_drawn', block, f'{len(tokens)} reader words the layer lacks, drawn on the page', 'note', tokens[:30])
            run.unverified(run.parsed.block(block), 'drawn_text')
            continue
        if words:
            replaced = block in missing and len(words) >= ADDED_WORDS_REPLACED
            run.find('words_added', block, f'{len(words)} reader words the layer lacks',
                     'suspect' if replaced or len(words) >= ADDED_WORDS_ALONE else 'note', words[:30])
        if numbers:
            run.find('number_added', block, f'{len(numbers)} numbers in the reading only', words=numbers[:30])
    check.numbers_layer_only = [item.word.token for item in text_leftovers if _has_digit(item.word.token)]
    check.numbers_reader_only = [token for reading, token in reader_only
                                 if reading.block.cls != 'figure' and _has_digit(token)]
    picture_extra = [token for reading, token in reader_only if reading.block.cls == 'figure']
    if picture_extra and check.precision is not None and check.precision < PRECISION_LOW and (check.recall or 0) >= RECALL_NEAR_ONE:
        run.find('text_in_pictures', None, f'{len(picture_extra)} reader words in figures the layer lacks', 'note', picture_extra[:30])


def _check_math(run: _Run, records: dict) -> None:
    """KaTeX's verdict on every formula and inline math; drawn or text evidence for each."""
    for block in run.parsed.blocks:
        record = records[block.id]
        if block.cls == 'formula':
            _check_formula(run, block, record)
            continue
        math = _block_math(block)
        if not math:
            continue
        verdicts = [_verdict(run, latex, False) for latex in math]
        _report_katex(run, block, record, verdicts)
        box = run.boxes.get(block.id)
        record.vector_glyphs = len(run.drawn.glyphs_in(box, BOX_PAD_PT / 2)) if box else None
        symbols = [_symbols_in(verdict.mathml) for verdict in verdicts if verdict is not None and verdict.mathml]
        record.math_symbols = sum(symbols) if symbols else None
        if box is not None and not record.vector_glyphs and not _text_evidence(run, block, box, math):
            run.find('invented_math', block.id, f'{len(math)} inline math with neither vector nor text evidence in its block')
        run.unverified(block, 'inline_math')


def _verdict(run: _Run, latex: str, display: bool) -> katex_check.Rendered | None:
    return None if run.rendered is None else run.rendered.get((latex, display))


def _report_katex(run: _Run, block: Block, record: BlockCheck, verdicts: list) -> None:
    known = [verdict for verdict in verdicts if verdict is not None]
    record.katex_ok = all(verdict.ok for verdict in known) if known else None
    errors = [verdict.error or '' for verdict in known if not verdict.ok]
    if errors:
        run.find('katex', block.id, f'{len(errors)} of {len(verdicts)} math bodies fail in KaTeX strict mode', words=errors)


def _text_evidence(run: _Run, block: Block, box: Box, math: list[str]) -> bool:
    """Math-font words in the box, or free layer words in the box made of the characters this math prints."""
    if any(_holds(box, _centre(word.box), BOX_PAD_PT) for word in run.untrusted):
        return True
    chars = set(''.join(_math_text(latex) for latex in math))
    for index, word in enumerate(run.stream.words):
        if run.stream.owner[index] is None and _holds(box, _centre(word.box), BOX_PAD_PT):
            text = ''.join(ch for ch in _normalise(word.token).casefold() if ch.isalnum())
            if text and (set(text) <= chars or any(_math_text(latex) and _math_text(latex) in text for latex in math)):
                return True
    return False


def _check_formula(run: _Run, block: Block, record: BlockCheck) -> None:
    latex = block.body.strip()
    if not latex:
        run.unverified(block, 'formula_unreadable')
        return
    verdict = _verdict(run, latex, True)
    _report_katex(run, block, record, [verdict])
    if verdict is not None and verdict.mathml:
        record.math_symbols = _symbols_in(verdict.mathml)
    record.vector_glyphs = len(run.drawn.glyphs_in(run.boxes[block.id], BOX_PAD_PT / 2))
    run.unverified(block, 'formula_body')


# ---------------------------------------------------------------- code

def _check_python(run: _Run, block: Block) -> None:
    if block.attrs.get('lang', '').casefold() not in PYTHON_NAMES or block.attrs.get('kind') in PYTHON_KINDS_SKIPPED:
        return
    code = block.code or ''
    if block.attrs.get('kind') == 'repl':
        sources = [example.source for example in doctest.DocTestParser().get_examples(code)]
    else:
        sources = [code]
    error = next(filter(None, (_python_error(source) for source in sources)), None)
    if error is None:
        return
    if 'cont' in block.attrs or block.attrs.get('status') in FRAGMENT_STATUS:
        run.find('python_fragment', block.id, 'a fragment that does not parse on its own', 'note')
    elif "Missing parentheses in call to 'print'" in error:
        run.find('python2_print', block.id, 'a Python 2 print statement', 'note')
    else:
        run.find('python_syntax', block.id, 'the code does not parse', words=[error])


def _python_error(source: str) -> str | None:
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')  # an invalid escape in a printed listing is the book's business
        try:
            ast.parse(source)
        except (SyntaxError, ValueError, RecursionError) as error:
            return str(error)
    return None


def _line_key(text: str) -> str:
    return ''.join(_normalise(text).casefold().split())


def _layer_code_lines(run: _Run, words: list[LayerWord], numbered: bool) -> list[dict]:
    """The printed lines around the words a code block claims, built by baseline: a wide gap can split one printed line
    into two text lines. Each has its text key, its x and its advance if the line is monospace."""
    box = _union([word.box for word in words])
    height = median(word.box[3] - word.box[1] for word in words)
    area = (box[0] - height, box[1] - height, box[2] + height, box[3] + height)
    rows: dict = {}
    for word in run.raw:
        if _holds(area, _centre(word.box)):
            rows.setdefault(round(word.baseline), []).append(word)
    lines = []
    for _, row in sorted(rows.items()):
        row.sort(key=lambda word: word.box[0])
        if numbered and row[0].text.isdigit() and len(row) > 1:
            row = row[1:]
        advances = [advance for word in row for advance in word.advances]
        middle = median(advances)
        mono = middle > 0 and (max(advances) - min(advances)) <= MONOSPACE_SPREAD * middle
        lines.append({'key': _line_key(''.join(word.text for word in row)), 'x': row[0].box[0], 'advance': middle if mono else None})
    return lines


def _paired_lines(reader_keys: list[str], layer_keys: list[str]) -> list[tuple[int, int]]:
    pairs = []
    for op in Levenshtein.opcodes(reader_keys, layer_keys):
        if op.tag == 'equal':
            pairs.extend(zip(range(op.src_start, op.src_end), range(op.dest_start, op.dest_end)))
        elif op.tag == 'replace' and op.src_end - op.src_start == op.dest_end - op.dest_start:
            pairs.extend((src, dest) for src, dest in zip(range(op.src_start, op.src_end), range(op.dest_start, op.dest_end))
                         if fuzz.ratio(reader_keys[src], layer_keys[dest]) >= LINE_FUZZ_MIN)
    return pairs


def _check_indentation(run: _Run, reading: _Reading, record: BlockCheck) -> None:
    """Text layers lose indentation, which is the main reason code is read at all. Reader lines are matched to layer
    lines by their text, and the x offset of a layer line, in characters of its monospace font, is the printed indent."""
    block = reading.block
    claimed = [run.stream.words[match] for match in reading.matches if match is not None]
    if not claimed:
        return
    layer_lines = _layer_code_lines(run, claimed, block.attrs.get('numbered') == '1')
    reader_lines = [line for line in (block.code or '').split('\n') if line.strip()]
    pairs = _paired_lines([_line_key(line) for line in reader_lines], [line['key'] for line in layer_lines])
    pairs = [(src, dest) for src, dest in pairs if layer_lines[dest]['advance'] is not None]
    record.indent_lines = len(pairs)
    if len(pairs) < 2:
        return
    advance = median(layer_lines[dest]['advance'] for _, dest in pairs)
    left = min(layer_lines[dest]['x'] for _, dest in pairs)
    lead = {src: len(reader_lines[src]) - len(reader_lines[src].lstrip(' ')) for src, _ in pairs}
    base = min(lead.values())
    wrong = [src for src, dest in pairs
             if abs((layer_lines[dest]['x'] - left) / advance - (lead[src] - base)) > INDENT_TOLERANCE_CHARS]
    if wrong:
        run.find('code_indent', block.id, f'{len(wrong)} of {len(pairs)} code lines are indented differently from the layer')


def _credit_line_numbers(run: _Run, reading: _Reading) -> None:
    """Printed line numbers go to first_line= in a reading, so the layer alone holds them; the range is the check."""
    block = reading.block
    first = block.attrs.get('first_line', '')
    if block.attrs.get('numbered') != '1' or not first.isdigit():
        return
    claimed = [run.stream.words[match] for match in reading.matches if match is not None]
    box = _union([word.box for word in claimed])
    if box is None:
        return
    count = len((block.code or '').split('\n'))
    allowed = {str(number) for number in range(int(first), int(first) + count)}
    area = (box[0] - 40.0, box[1] - BOX_PAD_PT, box[2], box[3] + BOX_PAD_PT)
    for index, word in enumerate(run.stream.words):
        if run.stream.owner[index] is None and word.token in allowed and _holds(area, _centre(word.box)):
            run.stream.claim(index, reading)


def _check_ragged(run: _Run, block: Block) -> None:
    widths = sorted(set(grid_widths(block.rows or [])))
    if len(widths) > 1:
        run.find('table_ragged', block.id, f'rows of {widths} columns: a value may stand in the wrong column')


def _check_table_grid(run: _Run, block: Block, record: BlockCheck) -> None:
    """Rows and columns against pymupdf's table finder, only when exactly one found table overlaps the block."""
    box = run.boxes[block.id]
    overlapping = [table for table in run.drawn.tables if _intersection(box, tuple(table.bbox)) > 0]
    record.grid_reader = (len(block.rows), max(grid_widths(block.rows), default=0))
    if len(overlapping) != 1:
        return
    record.grid_found = (overlapping[0].row_count, overlapping[0].col_count)
    if record.grid_found != record.grid_reader:
        run.find('table_grid', block.id, f'{record.grid_reader[0]} x {record.grid_reader[1]} in the reading, '
                                         f'{record.grid_found[0]} x {record.grid_found[1]} found on the page', 'note')


# ---------------------------------------------------------------- assembling the result

def _snap(run: _Run, block: Block, reading: _Reading | None, children: dict) -> Box | None:
    """Float boxes snap to the page's own images and drawings, text boxes to their words."""
    box = run.boxes.get(block.id)
    if box is None:
        return None
    if block.id in run.raster_tables or block.cls == 'figure':
        images = [image for image in run.drawn.images if _intersection(box, image) > 0]
        if images:
            return max(images, key=lambda image: _intersection(box, image))
    if block.cls == 'formula':
        glyphs = run.drawn.glyphs_in(box, BOX_PAD_PT / 2)
        if glyphs:
            return _union(glyphs)
    words = [run.stream.words[match].box for match in (reading.matches if reading else []) if match is not None]
    if block.cls == 'box':
        words += children.get(block.id, [])
    return _union(words)


def _block_records(run: _Run, leftovers: list[_Leftover], reader_only: list[tuple[_Reading, str]]) -> dict:
    by_block = {reading.block.id: reading for reading in run.readings}
    missing = Counter(item.block.id for item in leftovers if item.block is not None)
    extra = Counter(reading.block.id for reading, _ in reader_only)
    records, children = {}, {}
    for block in run.parsed.blocks:
        reading = by_block.get(block.id)
        record = BlockCheck(block.id, block.cls)
        records[block.id] = record
        if reading is not None:
            mandatory = [match for match, optional in zip(reading.matches, reading.optional) if not optional]
            matched = sum(match is not None for match in mandatory)
            claimed = sum(owner is reading for owner in run.stream.owner)
            if claimed + missing[block.id]:
                record.coverage = round(claimed / (claimed + missing[block.id]), 4)
            if matched + extra[block.id]:
                record.precision = round(matched / (matched + extra[block.id]), 4)
            if block.cls not in NO_ORDER_CLASSES and len(mandatory) >= 2:
                record.order_ok = _longest_break_run(mandatory) < BREAKS_IN_A_ROW
                if not record.order_ok:
                    run.find('word_order', block.id, 'two or more broken word pairs in a row: words stand in a different order than in the layer')
        record.snapped = _snap(run, block, reading, children)
        if record.snapped is not None and block.id in run.boxes:
            record.iou = round(_iou(run.boxes[block.id], record.snapped), 3)
            if 'in' in block.attrs:
                children.setdefault(block.attrs['in'], []).append(record.snapped)
    for block in run.parsed.blocks:  # a box comes before its children, so its box is snapped again once they are known
        if block.cls == 'box' and block.id in children:
            record = records[block.id]
            record.snapped = _snap(run, block, by_block.get(block.id), children)
            record.iou = round(_iou(run.boxes[block.id], record.snapped), 3) if record.snapped else None
    return records


def _reader_only(run: _Run) -> list[tuple[_Reading, str]]:
    """Reader tokens the layer lacks. Tokens of math fonts count on neither side: a word the layer holds in a math font
    may well be what the reader wrote."""
    math_keys = {_key(word.token) for word in run.untrusted}
    return [(reading, token) for reading in run.readings
            for token, match, optional in zip(reading.tokens, reading.matches, reading.optional)
            if match is None and not optional and _key(token) not in math_keys]


def _check_without_layer(run: _Run) -> PageCheck:
    """A scan: nothing to compare the words with, but KaTeX and ast.parse do not need a layer."""
    records = {block.id: BlockCheck(block.id, block.cls) for block in run.parsed.blocks}
    for block in run.parsed.blocks:
        math = [block.body.strip()] if block.cls == 'formula' and block.body.strip() else _block_math(block)
        if math:
            display = block.cls == 'formula'
            _report_katex(run, block, records[block.id], [_verdict(run, latex, display) for latex in math])
        if block.cls == 'code':
            _check_python(run, block)
        if block.cls == 'table':
            _check_ragged(run, block)
        run.unverified(block, 'no_layer')
    return PageCheck(False, findings=run.findings, blocks=list(records.values()), unverifiable=run.unverifiable)


def check_page(parsed: ParsedPage, page: pymupdf.Page, rendered: dict | None = None, bad_fonts: tuple[str, ...] = ()) -> PageCheck:
    """The reading of one page against that page of the source PDF, in the frame the reader was shown (`page_render.upright`):
    the reading's pixel boxes are mapped onto the page's points, so both must stand the same way up."""
    from backend.conversion.reading import page_render

    with page_render.upright(page):
        return _check_page(parsed, page, rendered, bad_fonts)


def _check_page(parsed: ParsedPage, page: pymupdf.Page, rendered: dict | None = None, bad_fonts: tuple[str, ...] = ()) -> PageCheck:
    """The reading of one page against that page of the source PDF.

    Args:
        parsed: A reading that passed stage 1.
        page: The pymupdf page it was read from.
        rendered: render_formulas' answer for a batch holding this page. Without it KaTeX has not run, which is no finding.
        bad_fonts: Names of fonts known to extract as garbage; their words count on neither side, like math fonts.

    Raises:
        ValueError: When the reading failed stage 1; such a reading is never used.
    """
    if not parsed.valid:
        raise ValueError('stage 2 needs a reading that passed stage 1')
    raw = _raw_words(page, tuple(bad_fonts))
    words = _layer_from(raw)
    trusted = [word for word in words if word.trusted]
    aliases = {_key(word.alias): _key(word.token) for word in words if word.alias}
    run = _Run(parsed, page, rendered, raw, _Stream(trusted), [word for word in words if not word.trusted], aliases,
               _Drawn(page), _boxes_in_points(parsed, page))
    read_tokens = sum(len(_body_tokens(block)) for block in parsed.blocks if block.cls not in NOT_COMPARED)
    if not trusted or (len(trusted) < MIN_LAYER_WORDS and read_tokens >= READING_HAS_MANY):
        return _check_without_layer(run)

    labels = _claim_formula_labels(run)
    _prepare_readings(run)
    repaired = _align(run.readings, run.stream)
    for reading in run.readings:
        if reading.block.cls == 'code':
            _credit_line_numbers(run, reading)
    leftovers, hidden = _leftovers(run)
    leftovers, reader_only = _credit_glued_math(leftovers, _reader_only(run))
    claimed = sum(owner is not None for owner in run.stream.owner)
    matched = sum(match is not None for reading in run.readings for match, optional in zip(reading.matches, reading.optional) if not optional)
    check = PageCheck(True, recall=claimed / (claimed + len(leftovers)) if claimed + len(leftovers) else None,
                      precision=matched / (matched + len(reader_only)) if matched + len(reader_only) else None,
                      layer_only=[item.word.token for item in leftovers], reader_only=[token for _, token in reader_only])
    _report_text(run, leftovers, reader_only, check)
    records = _block_records(run, leftovers, reader_only)
    for block_id, found in labels.items():
        records[block_id].label_ok = found
    _check_math(run, records)
    for reading in run.readings:
        if reading.block.cls == 'code':
            _check_python(run, reading.block)
            _check_indentation(run, reading, records[reading.block.id])
    for block in parsed.blocks:
        if block.cls == 'table':
            _check_ragged(run, block)
        if block.cls == 'table' and block.id in run.raster_tables:
            run.unverified(block, 'raster_table')
        elif block.cls == 'table' and block.rows:
            _check_table_grid(run, block, records[block.id])
        elif block.cls == 'figure' and any(r.block is block and None in r.matches for r in run.readings):
            run.unverified(block, 'figure_text')
    _check_printed_label(run, words)
    if hidden:
        run.find('hidden_text', None, f'{hidden} white or invisible layer words left unread', 'note')
    if repaired:
        run.find('spacing_differs', None, f'{repaired} words split differently in the reading and the layer', 'note')
    check.findings = run.findings
    check.blocks = list(records.values())
    check.unverifiable = run.unverifiable
    return check


def _check_printed_label(run: _Run, words: list[LayerWord]) -> None:
    label = str(run.parsed.front.get('printed_label', 'none'))
    if label == 'none':
        return
    present = {_key(word.token) for word in words}
    if not all(_key(token) in present for token in tokens_of(label)):
        run.find('printed_label', None, 'the printed label does not occur in the layer', words=[label])


def render_formulas(parsed_pages: list[ParsedPage]) -> dict:
    """KaTeX's verdict on every formula and inline math of a batch of pages, once for each distinct body.

    The answer is keyed by (latex, display), what katex_check.check_many takes: block ids repeat across pages, so a key
    with a page index would hand a page another page's verdict if the caller passed the wrong index.

    Raises:
        katex_check.KatexUnavailable: When the child process failed, which says nothing about the formulas.
    """
    items = set()
    for parsed in parsed_pages:
        for block in parsed.blocks:
            if block.cls == 'formula':
                if block.body.strip():
                    items.add((block.body.strip(), True))
            else:
                items.update((latex, False) for latex in _block_math(block))
    ordered = sorted(items)
    return dict(zip(ordered, katex_check.check_many(ordered)))
