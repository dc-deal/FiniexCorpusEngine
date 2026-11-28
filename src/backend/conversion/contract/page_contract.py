"""The reader's answer, parsed and checked against contract page/1: the first stage of the check flow.

One page is a set of front fields and a list of blocks, each with one class, attributes and a body.
It arrives in one of two forms, measured against each other in the mini pilot (decision OC-1.a):

    markdown  YAML front matter and colon-fenced blocks: ::: {#b05 .formula label="6.3" bbox="..."}
    json      {"front": [{"name", "value"}], "blocks": [{"id", "class", "attrs": [{"name", "value"}], "body"}]}

Both forms become the same `ParsedPage`, so everything downstream is form-agnostic, and both pass the same
validation. Parsing uses maintained libraries only: markdown-it-py with mdit-py-plugins (front matter, colon
fences, Djot attributes, inline math with brackets, attribute spans), PyYAML's BaseLoader (every scalar stays a
string, so `language: no` is not False), and the stdlib's html.parser for table bodies. What is written here
is the validation, the part no library can know: it was checked against JSON Schema, DocTags and DocLang,
and those leave the page's own rules to the caller (`contract_vocab.json` holds the vocabulary).

A reading that fails is stored and counted as malformed, never used. Every result falls into exactly one
class, and a refusal is final and never re-sent.
"""

import html.parser
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.attrs import attrs_plugin
from mdit_py_plugins.attrs.parse import ParseError as AttrParseError
from mdit_py_plugins.attrs.parse import parse as parse_attr_string
from mdit_py_plugins.colon_fence import colon_fence_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.texmath import texmath_plugin

VOCAB = json.loads((Path(__file__).resolve().parent / 'contract_vocab.json').read_text(encoding='utf-8'))
CONTRACT = VOCAB['contract']
FORMS = ('markdown', 'json')

BLOCK_MD = MarkdownIt('commonmark', {'html': False}).use(front_matter_plugin).use(colon_fence_plugin)
INLINE_MD = (MarkdownIt('commonmark', {'html': False}).enable('strikethrough')
             .use(texmath_plugin, delimiters='brackets').use(attrs_plugin, spans=True))

CLOSER = re.compile(r'^\s{0,3}:{3,}\s*$')
OPENER_IN_BODY = re.compile(r'^\s{0,3}:{3,}\s*\{')
BLOCK_ID = re.compile(r'^b\d{2,3}$')
BBOX = re.compile(r'^\d+ \d+ \d+ \d+$')
IMAGE_SIZE = re.compile(r'^(\d+)x(\d+)$')
DETACHED = re.compile(r'^@(prev|next|label:\S.*)$')
# page/1.4 (2026-11-18, the operator, F4.a): read in the source as written, so a backslash the page prints as text, written
# &#92; ("rate&#92;term", a table head whose rows are rates and columns terms), is not taken for a stray LaTeX command. Every
# other spelling still fails: markdown-it and html.parser decode &#92; and \\ to a bare backslash before the text is seen, and
# a doubled \\frac is what a reader writes when it escapes LaTeX twice, so only the entity says "a backslash, on purpose".
LATEX_OUTSIDE_MATH = re.compile(r'\\[A-Za-z]{2,}')
HTML_IN_PROSE = re.compile(r'</?(?:sup|sub|b|i|em|strong|u|br|span|div|p)\b[^<>]*>', re.I)
BARE_DOLLAR = re.compile(r'(?<!\\)\$')  # KaTeX refuses it, and a reader that was told once writes \$
DOLLAR_MATH = re.compile(r'\$[^$\n]*[\\^_{}][^$\n]*\$')  # '$100,000 of the $120,000' must not trip this
ESCAPED_DOLLAR = re.compile(r'\\\$')
# page/1.5 (2026-11-28, the operator, 49.a): an equation's printed number belongs in label=, never in its LaTeX. MinerU wrote
# \tag{11.26} on 11 of its 20 test pages, LaTeX's own place for it; it passed the validator, our converter and the judge, and
# the view drew (11.26) into the fraction (finance p. 343). No served reading held one when the rule came.
FORMULA_TAG = re.compile(r'\\tag\*?\s*\{')
INLINE_MARK_ATTRIBUTES = re.compile(r'\]\{[^}\n]*\}')  # the '{.fn}' of '[1]{.fn}'
CODE_SPAN = re.compile(r'`[^`]*`')
INLINE_MATH = re.compile(r'\\\(.*?\\\)', re.S)
CONTROL = re.compile(r'[\x00-\x09\x0b-\x1f\x7f]')  # a JSON string's unescaped \t or \f lands here: \text becomes TAB + 'ext'
# page/1.2 (2026-11-08): two ways of writing an attribute the parser refuses, though nothing in them is lost. A binding
# written without quotes, defines=@prev or of=@label:Figure\ 5-20, is read as if quoted; a brace inside a quoted value (a
# marker in LaTeX) stands in for itself while the line is parsed. Both are mended and kept as warnings.
UNQUOTED_BINDING = re.compile(r'(?<![\w-])(of|defines|near)=(@(?:\\ |[^\s"}])+)')
QUOTED_VALUE = re.compile(r'"(?:[^"\\]|\\.)*"')
BRACE_STAND_INS = str.maketrans({'{': '', '}': ''})
BRACES_BACK = str.maketrans({'': '{', '': '}'})
INLINE_BEARING = {'paragraph', 'list_item', 'quote', 'attribution', 'heading', 'caption', 'credit', 'box', 'footnote', 'callout',
                  'bib_entry', 'glossary_entry', 'toc_entry', 'index_entry', 'page_header', 'page_footer', 'page_number',
                  'margin_tab', 'watermark', 'other'}
# Bold or a superscript in a cell loses no text, so it costs no retry (mini pilot, 2026-10-30: <strong> in 3 of 80 readings).
TABLE_TAGS = {'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'br', 'b', 'strong', 'i', 'em', 'u', 'sup', 'sub', 'span'}
BODILESS_ALLOWED = {'figure', 'box', 'decoration'}
# page/1.3 (2026-11-11, decision 212.a): a numbered answer or an option ("7.", "A.") whose whole content is a journal table,
# a figure, a formula or a listing printed right after it is a marker alone; the content stands in its own block, so an
# empty body loses no text. 8 of the free corpus's 9 malformed accounting pages were only that, served from a text layer
# that lacks the tables where they are images (accounting p. 524).
CONTENT_BLOCKS = {'table', 'figure', 'formula', 'code'}
# A footnote marker, a superscript and a subscript keep their kind as a segment of their own (decision 205.a, 11 Nov): run
# into the text they stand beside, "1947–2020[2]{.fn}" read "1947–20202" and "12.5[2]{.sup}" read "12.52" in the index.
KEPT_MARKS = ('fn', 'sup', 'sub')


@dataclass(frozen=True)
class Expected:
    """What the caller gave the reader; the reading must echo it."""
    work: str
    pdf_page: int
    image_size: tuple[int, int]


@dataclass
class Cell:
    text: str
    header: bool = False
    rowspan: int = 1
    colspan: int = 1
    inline: dict | None = None
    source: str | None = None  # the cell as written in the table's body, its entities not decoded (page/1.4)
    start: int = 0  # where `source` begins in the table's body


@dataclass
class Block:
    id: str
    cls: str
    attrs: dict
    body: str
    line: int
    inline: dict | None = None
    # the page's line the body begins on, so a fault is named where it stands (page/1.4); None in the JSON form, which has none
    body_line: int | None = None
    rows: list[list[Cell]] | None = None  # a table's rows
    code: str | None = None  # a code body without its callout marks
    callouts: dict = field(default_factory=dict)  # a code body's line number -> callout numbers
    notices: list = field(default_factory=list)  # what was mended while its attributes were read (page/1.2)

    @property
    def bbox(self) -> tuple[int, int, int, int] | None:
        """The block's box in pixels of the image as sent, when it has a well-formed one."""
        value = self.attrs.get('bbox', '')
        return tuple(int(part) for part in value.split()) if BBOX.match(value) else None


@dataclass
class ParsedPage:
    form: str
    front: dict
    blocks: list[Block]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def found_page(self) -> bool:
        """Whether the answer is a page at all; a soft refusal or a chatty answer has neither part."""
        return bool(self.front or self.blocks)

    def block(self, block_id: str) -> Block | None:
        return next((block for block in self.blocks if block.id == block_id), None)

    def as_dict(self) -> dict:
        """What a stored reading record keeps of the check: no page text."""
        classes = {}
        for block in self.blocks:
            classes[block.cls] = classes.get(block.cls, 0) + 1
        spans = [span['class'] for block in self.blocks for span in (block.inline or {}).get('spans', [])]
        return {'valid': self.valid, 'found_page': self.found_page, 'errors': self.errors, 'warnings': self.warnings,
                'blocks': len(self.blocks), 'classes': classes, 'printed_label': self.front.get('printed_label'),
                'page_kind': self.front.get('page_kind'), 'unclear': spans.count('unclear'), 'gaps': spans.count('gap')}


# ---------------------------------------------------------------- inline marks

def _blank(found: re.Match) -> str:
    """The match as spaces, its line breaks kept, so a place in what is left is the same place in the source."""
    return re.sub(r'[^\n]', ' ', found.group(0))


def _on_line(scope: str, found: re.Match | None, first_line: int | None) -> str:
    """' on line N', N the page's line the match stands on, counted as the validator counts a page's lines (page/1.4: the
    block's opening line alone sent the operator to the wrong line, 18 Nov); '' without a line."""
    if first_line is None or found is None:
        return ''
    return f" on line {first_line + scope.count('\n', 0, found.start())}"


def parse_inline(text: str, source: str | None = None, first_line: int | None = None) -> dict:
    """Plain text with the math taken out, plus the math, the note markers, the spans and the problems.

    `source` is the text as written where `text` was decoded before (a table cell: html.parser decodes its entities), and
    `first_line` the page's line it begins on, so a problem names its line."""
    plain, math, markers, spans, segments, problems, notices = [], [], [], [], [], [], []
    stack = []
    for token in INLINE_MD.parseInline(text):
        for child in token.children or []:
            if child.type == 'text':
                plain.append(child.content)
                segments.append((stack[-1]['class'] if stack and stack[-1]['class'] in KEPT_MARKS else 'text', child.content))
                if stack:
                    stack[-1]['text'] += child.content
            elif child.type == 'math_inline':
                # Inside math a $ can only be a dollar sign. Sonnet wrote it bare in Markdown on a page of worked examples, in the first
                # run and again after the prompt said otherwise (2026-10-30), so it is repaired here instead of paying for a retry.
                latex = BARE_DOLLAR.sub(r'\\$', child.content)
                if latex != child.content:
                    notices.append('a bare dollar sign inside inline math, escaped')
                math.append(latex)
                segments.append(('math', latex))
                plain.append(' ')
            elif child.type == 'code_inline':
                plain.append(child.content)
                segments.append(('code', child.content))
            elif child.type in ('softbreak', 'hardbreak'):
                plain.append(' ')
                segments.append(('text', ' '))
            elif child.type == 'span_open':
                name = (child.attrs or {}).get('class', '')
                stack.append({'class': name, 'attrs': dict(child.attrs or {}), 'text': ''})
                if name and name not in VOCAB['inline_classes']:
                    notices.append(f'unknown inline class .{name}')  # the text inside it stays intact
            elif child.type == 'span_close':
                span = stack.pop() if stack else {'class': '?', 'attrs': {}, 'text': ''}
                spans.append(span)
                if span['class'] == 'fn':
                    markers.append(span['text'])
            elif not child.type.endswith(('_open', '_close')):
                problems.append(f'unexpected inline token {child.type}')
    without_code = CODE_SPAN.sub('', text)
    outside_math = INLINE_MATH.sub(' ', without_code)
    # The source with code, math and a mark's attributes blanked: what the prose was written as, every place where it stood.
    scope = INLINE_MATH.sub(_blank, CODE_SPAN.sub(_blank, text if source is None else source))
    scope = INLINE_MARK_ATTRIBUTES.sub(lambda found: ']' + _blank(found)[1:], scope)
    if without_code.count('\\(') != without_code.count('\\)'):
        problems.append('unbalanced inline math delimiter \\( \\)')
    outside = LATEX_OUTSIDE_MATH.search(scope)  # page/1.4: in the source, where &#92; is still an entity
    if outside:
        problems.append(f'LaTeX command outside math{_on_line(scope, outside, first_line)}: {outside.group(0)}')
    # Two \$ inside one \( \) are dollar amounts, and so are a prose amount with an escaped \$ or an inline mark such as
    # [1]{.fn} after it on the same line (page/1.1, 2026-11-02: 45 of 77 failed readings of the free corpus were only that).
    # Which page fails is decided as before; the source's blanked copy only finds the line (page/1.4).
    if DOLLAR_MATH.search(INLINE_MARK_ATTRIBUTES.sub(']', ESCAPED_DOLLAR.sub(' ', outside_math))):
        found = DOLLAR_MATH.search(ESCAPED_DOLLAR.sub(_blank, scope))
        problems.append(f'possible $...$ math{_on_line(scope, found, first_line)} (the contract uses \\( \\))')
    if HTML_IN_PROSE.search(outside_math):
        found = HTML_IN_PROSE.search(scope) if source is None else None  # a cell's source holds its table's own tags
        problems.append(f'HTML in prose{_on_line(scope, found, first_line)} (use the inline marks: [8]{{.sup}}, **bold**)')
    return {'plain': re.sub(r'\s+', ' ', ''.join(plain)).strip(), 'math': math, 'markers': markers, 'spans': spans,
            'segments': segments, 'problems': problems, 'notices': notices}


# ---------------------------------------------------------------- tables

class _TableParser(html.parser.HTMLParser):
    def __init__(self, body: str = '') -> None:
        super().__init__(convert_charrefs=True)
        self.body = body
        self.line_starts = [0] + [index + 1 for index, character in enumerate(body) if character == '\n']
        self.rows: list[list[Cell]] = []
        self.cell: Cell | None = None
        self.problems: list[str] = []

    def at(self) -> int:
        """Where in the body the tag being handled begins: html.parser moves its position on only after a tag's handler."""
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag not in TABLE_TAGS:
            self.problems.append(f'unexpected tag <{tag}> in table')
        if tag == 'tr':
            self.rows.append([])
        elif tag in ('td', 'th'):
            try:
                self.cell = Cell('', header=tag == 'th', rowspan=int(values.get('rowspan') or 1),
                                 colspan=int(values.get('colspan') or 1))
            except ValueError:
                self.problems.append(f'a span in <{tag}> is not a number')
                self.cell = Cell('', header=tag == 'th')
            self.cell.start = self.at() + len(self.get_starttag_text() or '')
        elif tag == 'br' and self.cell is not None:
            self.cell.text += ' '

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.cell.source = self.body[self.cell.start:self.at()]
            if not self.rows:
                self.rows.append([])
            self.rows[-1].append(self.cell)
            self.cell = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.text += data


def grid_widths(rows: list[list[Cell]]) -> list[int]:
    """The column count of each row, with rowspan and colspan honoured."""
    occupied, widths = set(), []
    for row_index, row in enumerate(rows):
        column = 0
        for cell in row:
            while (row_index, column) in occupied:
                column += 1
            for down in range(cell.rowspan):
                for across in range(cell.colspan):
                    occupied.add((row_index + down, column + across))
            column += cell.colspan
        widths.append(max((c for r, c in occupied if r == row_index), default=-1) + 1)
    return widths


def parse_table(body: str, first_line: int | None = None) -> tuple[list[list[Cell]], list[str], list[str]]:
    """A table's rows of cells, with the problems and notices of their text; `first_line` is the page's line the body
    begins on, so a cell's problem names its line (page/1.4)."""
    parser = _TableParser(body)
    parser.feed(body)
    parser.close()
    problems, notices = list(parser.problems), []
    for row in parser.rows:
        for cell in row:
            line = None if first_line is None else first_line + body.count('\n', 0, cell.start)
            cell.inline = parse_inline(cell.text, source=cell.source, first_line=line)
            problems.extend(cell.inline['problems'])
            notices.extend(cell.inline['notices'])
    widths = grid_widths(parser.rows)
    if len(set(widths)) > 1:  # the text is there, its place in doubt: stage 2 sends it to the judge rather than pay for a retry
        notices.append(f'ragged table: row widths {widths}')
    return parser.rows, problems, notices


# ---------------------------------------------------------------- code

def callout_number(character: str) -> int | None:
    """The number of a circled-digit mark, in any family: ① ⓫ ❶ ➀ ➊ ⓵ ㉑ ㊱. Unicode's names say which they are."""
    if 'CIRCLED' not in unicodedata.name(character, ''):
        return None
    try:
        return int(unicodedata.numeric(character))
    except ValueError:
        return None


def strip_callouts(code: str) -> tuple[str, dict]:
    """Take the callout marks off the line ends; return the clean code and {line number: [marks]}."""
    lines, marks = [], {}
    for number, line in enumerate(code.split('\n'), 1):
        found = []
        rest = line.rstrip()
        while rest and callout_number(rest[-1]) is not None:
            found.insert(0, callout_number(rest[-1]))
            rest = rest[:-1].rstrip()
        if found:
            marks[number] = found
            line = rest
        lines.append(line)
    return '\n'.join(lines), marks


# ---------------------------------------------------------------- the two forms

def lenient_attributes(info: str) -> tuple[str, list[str]]:
    """The attribute line as the parser takes it, and what was mended (page/1.2): a binding without quotes is quoted, and a
    brace inside a quoted value is replaced by a stand-in, put back once the values are read. Neither changes the text."""
    notices = []

    def quote(match: re.Match) -> str:
        notices.append(f'{match.group(1)}= written without quotes, read as {match.group(1)}="..."')
        return f'{match.group(1)}="{match.group(2).replace(chr(92) + " ", " ")}"'

    info = UNQUOTED_BINDING.sub(quote, info)

    def stand_in(match: re.Match) -> str:
        if '{' in match.group(0) or '}' in match.group(0):
            notices.append('a brace inside a quoted value, read as part of the value')
        return match.group(0).translate(BRACE_STAND_INS)

    head, brace, rest = info.partition('{')  # the braces that open and close the attribute block itself stay
    if brace:
        inner, closing, tail = rest.rpartition('}')
        if closing:
            info = head + brace + QUOTED_VALUE.sub(stand_in, inner) + closing + tail
    return info, notices


def _read_markdown(text: str) -> tuple[dict, list[Block], list[str]]:
    text = text.lstrip('﻿\r\n ')
    errors, blocks, front = [], [], {}
    lines = text.split('\n')
    for token in BLOCK_MD.parse(text):
        if token.type == 'front_matter':
            try:
                loaded = yaml.load(token.content, Loader=yaml.BaseLoader)
                front = loaded if isinstance(loaded, dict) else {}
                if not isinstance(loaded, dict):
                    errors.append('front matter is not a mapping')
            except yaml.YAMLError as error:
                errors.append(f'front matter is not YAML: {type(error).__name__}')
            continue
        if token.type != 'colon_fence':
            if token.nesting >= 0 and token.type != 'inline' and token.level == 0:
                errors.append(f'line {(token.map or [0])[0] + 1}: text outside any block ({token.type})')
            continue
        start, end = token.map
        if not (end - 1 > start and CLOSER.match(lines[end - 1] or '')):
            errors.append(f'line {start + 1}: block is not closed')
        for offset, body_line in enumerate(token.content.split('\n')):
            if OPENER_IN_BODY.match(body_line):
                errors.append(f"line {start + 2 + offset}: a block opens inside another block (missing ':::')")
        info, notices = lenient_attributes(token.info.strip())
        try:
            closing_brace, attrs = parse_attr_string(info)
        except AttrParseError as error:
            errors.append(f'line {start + 1}: attributes not parseable: {error}')
            continue
        attrs = {name: value.translate(BRACES_BACK) if isinstance(value, str) else value for name, value in attrs.items()}
        if info[closing_brace + 1:].strip():
            errors.append(f'line {start + 1}: text after the attributes')
        classes = (attrs.pop('class', '') or '').split()
        if len(classes) != 1:
            errors.append(f'line {start + 1}: exactly one class required, got {classes}')
        body = token.content[:-1] if token.content.endswith('\n') else token.content
        blocks.append(Block(id=attrs.pop('id', ''), cls=classes[0] if classes else '', attrs=attrs, body=body, line=start + 1,
                            body_line=start + 2, notices=notices))
    return front, blocks, errors


def _read_json(text: str) -> tuple[dict, list[Block], list[str]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return {}, [], [f'not JSON: {error.msg} at {error.pos}']
    if not isinstance(data, dict) or not isinstance(data.get('front'), list) or not isinstance(data.get('blocks'), list):
        return {}, [], ['not a page object with front and blocks']
    front = {item['name']: item['value'] for item in data['front']}
    blocks = [Block(id=item['id'], cls=item['class'], attrs={attr['name']: attr['value'] for attr in item['attrs']},
                    body=item['body'], line=index) for index, item in enumerate(data['blocks'], 1)]
    return front, blocks, []


def json_schema() -> dict:
    """The page as a JSON schema for structured outputs: attributes as name-value pairs, since an open map is not allowed."""
    front_names = VOCAB['front_matter']['required'] + VOCAB['front_matter']['optional']
    attr_names = sorted(set(VOCAB['common_attrs']) | {name for spec in VOCAB['classes'].values() for name in spec['attrs']})

    def pairs(names: list[str]) -> dict:
        return {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': ['name', 'value'],
                                           'properties': {'name': {'type': 'string', 'enum': names}, 'value': {'type': 'string'}}}}

    block = {'type': 'object', 'additionalProperties': False, 'required': ['id', 'class', 'attrs', 'body'],
             'properties': {'id': {'type': 'string'}, 'class': {'type': 'string', 'enum': sorted(VOCAB['classes'])},
                            'attrs': pairs(attr_names), 'body': {'type': 'string'}}}
    return {'type': 'object', 'additionalProperties': False, 'required': ['front', 'blocks'],
            'properties': {'front': pairs(front_names), 'blocks': {'type': 'array', 'items': block}}}


# ---------------------------------------------------------------- validation

def _check_front(front: dict, expected: Expected | None, errors: list[str]) -> tuple[int, int] | None:
    spec = VOCAB['front_matter']
    for name in spec['required']:
        if name not in front:
            errors.append(f"front matter: '{name}' missing")
    for name, allowed in spec['enums'].items():
        if name in front and str(front[name]) not in allowed:
            errors.append(f'front matter: {name}={front[name]!r} not in {allowed}')
    if front.get('contract') and front['contract'] != CONTRACT:
        errors.append(f"front matter: contract {front['contract']} is not {CONTRACT}")
    if 'pdf_page' in front and not str(front['pdf_page']).isdigit():
        errors.append('front matter: pdf_page must be an integer')
    size = None
    if 'image_size' in front:
        match = IMAGE_SIZE.match(str(front['image_size']))
        if match:
            size = (int(match.group(1)), int(match.group(2)))
        else:
            errors.append(f"front matter: image_size {front['image_size']!r} is not WIDTHxHEIGHT")
    if expected:
        if 'work' in front and front['work'] != expected.work:
            errors.append(f"work is {front['work']!r}, asked for {expected.work!r}")
        if str(front.get('pdf_page', expected.pdf_page)) != str(expected.pdf_page):
            errors.append(f"pdf_page is {front['pdf_page']!r}, asked for {expected.pdf_page}")
        if size and size != expected.image_size:
            errors.append(f'image_size is {size}, the image is {expected.image_size}')
        size = expected.image_size
    return size


def _check_bbox(block: Block, where: str, size: tuple[int, int] | None, errors: list[str]) -> None:
    if block.cls in VOCAB['bbox_exempt']:
        if 'bbox' in block.attrs:
            errors.append(f'{where}: .{block.cls} has no box')
        return
    if 'bbox' not in block.attrs:
        errors.append(f'{where}: .{block.cls} requires a bbox')
        return
    box = block.bbox
    if box is None:
        errors.append(f"{where}: bbox {block.attrs['bbox']!r} is not 'x0 y0 x1 y1'")
        return
    x0, y0, x1, y1 = box
    if not (x0 < x1 and y0 < y1):
        errors.append(f"{where}: bbox {block.attrs['bbox']!r} has no area")
    if size and (x1 > size[0] or y1 > size[1]):
        errors.append(f"{where}: bbox {block.attrs['bbox']!r} lies outside the image {size[0]}x{size[1]}")


def _check_body(block: Block, where: str, spec: dict, errors: list[str], warnings: list[str], content_follows: bool = False) -> None:
    empty = not block.body.strip()
    if block.cls == 'toc_entry' and '\t' in block.body and not CONTROL.search(block.body.replace('\t', '')):
        # page/1.2: in a contents entry a tab is the printed leader between the title and its page, not a lost \t escape.
        block.body = block.body.replace('\t', ' ')
        warnings.append(f'{where}: a tab between title and page, read as a space')
    if CONTROL.search(block.body):
        errors.append(f'{where}: a control character in the body (a tab, or a lost JSON escape)')
    if spec['content'] == '-':
        if not empty:
            errors.append(f'{where}: .{block.cls} has no body')
        return
    if spec['content'] in ('V', 'V*') and empty and block.attrs.get('status') != 'unreadable' and block.cls not in BODILESS_ALLOWED:
        if content_follows:  # page/1.3
            warnings.append(f'{where}: a list item whose content is the block after it')
        else:
            errors.append(f'{where}: empty body (use status=unreadable)')
    if block.cls in INLINE_BEARING:
        block.inline = parse_inline(block.body, first_line=block.body_line)
        errors.extend(f'{where}: {problem}' for problem in block.inline['problems'])
        warnings.extend(f'{where}: {notice}' for notice in block.inline['notices'])
    if block.cls == 'heading' and block.body.lstrip().startswith('#'):
        errors.append(f'{where}: a heading body is its text, without # marks')
    if block.cls == 'table' and not empty:
        block.rows, problems, notices = parse_table(block.body, block.body_line)
        errors.extend(f'{where}: {problem}' for problem in problems)
        warnings.extend(f'{where}: {notice}' for notice in notices)
        if not block.rows:
            errors.append(f'{where}: no table rows found')
    if block.cls == 'code':
        block.code, block.callouts = strip_callouts(block.body)
    if block.cls == 'formula':
        if block.body.strip().startswith(('$', '\\[', '\\(')):
            errors.append(f'{where}: a formula body is bare LaTeX, without delimiters')
        if block.attrs.get('label', '').startswith('('):
            errors.append(f'{where}: a formula label comes without brackets')
        if BARE_DOLLAR.search(block.body):
            errors.append(f'{where}: a dollar sign inside math must be \\$')
        if FORMULA_TAG.search(block.body):
            errors.append(f'{where}: an equation number inside the formula (\\tag); it belongs in label=')


def _check_block(block: Block, where: str, spec: dict, size: tuple[int, int] | None, errors: list[str], warnings: list[str],
                 content_follows: bool = False) -> None:
    allowed = set(VOCAB['common_attrs']) | set(spec['attrs'])
    for name in [name for name in block.attrs if name not in allowed]:  # a stray attribute holds no text: dropped, not paid for again
        warnings.append(f"{where}: attribute '{name}' not allowed on .{block.cls}, dropped")
        del block.attrs[name]
    for name in spec['required']:
        if name not in block.attrs:
            errors.append(f"{where}: .{block.cls} requires '{name}'")
    for name in spec.get('expected', []):  # page/1.2: a label that holds no text, so its absence costs no retry
        if name not in block.attrs:
            warnings.append(f"{where}: .{block.cls} without '{name}'")
    for name in spec.get('required_unless_cont_prev', []):
        if name in block.attrs or block.attrs.get('cont') in ('prev', 'both'):
            continue
        if name == 'marker' and block.cls == 'footnote' and block.attrs.get('kind') == 'table':
            # page/1.2: a note under a table often prints no marker, only a lead such as "Note:" or "Source:" in its text
            warnings.append(f"{where}: a table note without a marker")
            continue
        errors.append(f"{where}: .{block.cls} requires '{name}' unless it continues (cont=prev)")
    for name, values in VOCAB['enums'].items():
        if name in block.attrs and block.attrs[name] not in values:
            errors.append(f'{where}: {name}={block.attrs[name]!r} not in {values}')
    if spec.get('kinds') and 'kind' in block.attrs and block.attrs['kind'] not in spec['kinds']:
        warnings.append(f"{where}: kind={block.attrs['kind']!r} not in {spec['kinds']}")
    if 'forms' in spec and 'form' in block.attrs and block.attrs['form'] not in spec['forms']:
        errors.append(f"{where}: form={block.attrs['form']!r} not in {spec['forms']}")
    _check_bbox(block, where, size, errors)
    _check_body(block, where, spec, errors, warnings, content_follows)


def _check_bindings(blocks: list[Block], by_id: dict, errors: list[str], warnings: list[str]) -> None:
    for block in blocks:
        spec = VOCAB['classes'].get(block.cls) or {}
        where = f'block {block.id} (line {block.line})'
        for name in ('of', 'in', 'near', 'defines'):
            if name not in block.attrs:
                continue
            value = block.attrs[name]
            if value.startswith('@'):
                if name not in VOCAB['detached_binding_attrs']:
                    errors.append(f'{where}: {name}= stays on this page, got {value!r}')
                elif not DETACHED.match(value):
                    errors.append(f"{where}: malformed binding {name}={value!r} (use @prev, @next or @label:Figure 12.3)")
                continue
            target = by_id.get(value)
            if target is None:
                errors.append(f'{where}: {name}={value} points to no block on this page')
            elif name == 'in' and target.cls not in ('box', 'list_item'):  # page/1.2: a list item's second paragraph
                errors.append(f'{where}: in= must point to a box or a list item, not .{target.cls}')
            elif name == 'of' and spec.get('of_classes') and target.cls not in spec['of_classes']:
                errors.append(f"{where}: of= points to .{target.cls}, expected {spec['of_classes']}")
            elif name == 'defines' and target.cls != 'formula':
                warnings.append(f'{where}: defines= must point to a formula')
    captions = {}
    for block in blocks:  # a continued table's '(continued)' caption repeats the first one on purpose
        if block.cls == 'caption' and 'of' in block.attrs and block.attrs.get('cont') not in ('prev', 'both'):
            captions[block.attrs['of']] = captions.get(block.attrs['of'], 0) + 1
    warnings.extend(f'float {target} has {count} captions' for target, count in captions.items() if count > 1)


def validate(form: str, front: dict, blocks: list[Block], errors: list[str], expected: Expected | None = None) -> ParsedPage:
    warnings = []
    size = _check_front(front, expected, errors)
    by_id = {}
    bound = {block.attrs.get('in') for block in blocks}
    marker_alone = {block.id for index, block in enumerate(blocks)  # page/1.3
                    if block.cls == 'list_item' and block.attrs.get('marker') and not block.body.strip()
                    and (block.id in bound or (index + 1 < len(blocks) and blocks[index + 1].cls in CONTENT_BLOCKS))}
    for block in blocks:
        where = f"block {block.id or '?'} (line {block.line})"
        if not BLOCK_ID.match(block.id or ''):
            errors.append(f'{where}: id must look like b01')
        if block.id in by_id:
            errors.append(f'{where}: duplicate id')
        by_id[block.id] = block
        warnings.extend(f'{where}: {notice}' for notice in block.notices)
        spec = VOCAB['classes'].get(block.cls)
        if spec is None:
            errors.append(f"{where}: unknown class '{block.cls}'")
            continue
        _check_block(block, where, spec, size, errors, warnings, block.id in marker_alone)
    _check_bindings(blocks, by_id, errors, warnings)
    if front and not blocks and front.get('page_kind') != 'blank':
        errors.append('no blocks on a page that is not blank')
    return ParsedPage(form=form, front=front, blocks=blocks, errors=errors, warnings=warnings)


def parse(text: str, form: str, expected: Expected | None = None) -> ParsedPage:
    """Read an answer in its form and validate it; collect every problem rather than stop at the first."""
    if form not in FORMS:
        raise ValueError(f'unknown form {form!r}, expected one of {FORMS}')
    front, blocks, errors = _read_markdown(text) if form == 'markdown' else _read_json(text)
    return validate(form, front, blocks, errors, expected)


def classify(result_type: str, stop_reason: str | None, page: ParsedPage | None) -> str:
    """One class per result: ok, refused, truncated, no_page, malformed, unexpected, or the API's
    errored, canceled or expired."""
    if result_type != 'succeeded':
        return result_type
    if stop_reason == 'refusal':
        return 'refused'
    if stop_reason == 'max_tokens':
        return 'truncated'
    if stop_reason != 'end_turn':
        return 'unexpected'
    if page is None or not page.found_page:
        return 'no_page'  # a soft refusal or a format failure: a person looks at it
    return 'ok' if page.valid else 'malformed'
