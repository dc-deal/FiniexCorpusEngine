"""A reading scored against the publisher's own markup, class by class: how the readers are measured.

    canonical_math(mathml) -> [token, ...]
    score_reading(page, gold, rendered) -> PageScore      rendered: page_checks.render_formulas' answer, None renders here
    summarize([PageScore, ...]) -> {class: numbers}
    self_check() -> report                                the comparator held against the gold itself

Formulas. Nothing can compare LaTeX with LaTeX: the same print has many spellings, and the publisher has MathML anyway. So
both sides become MathML, KaTeX's on the reader's side, and MathML becomes a linear list of tokens: one token per printed
character, without whitespace and invisible operators, plus structure tokens for fractions, roots, scripts and accents. A
script's token follows its base with no opening mark, which is what makes `(1+r)^n` equal `{(1+r)}^n` (a script on the bracket
against a script on the group). OmniDocBench's CDM metric was checked and rejected: it needs TeX Live, ImageMagick and
Ghostscript. Parsing is BeautifulSoup, edit distance rapidfuzz; what is written here is the normal form, which neither can know.

What the normal form cannot see, on purpose: fonts (`\\mathbf{x}`, `\\mathcal{X}` and a plain letter are one token, the price of
`\\text{FV}` = `\\mathrm{FV}` = `<mi>FV</mi>`), the layout of several lines (rows and columns of an array, an aligned block or a
single line are the same), which base a script belongs to when no bracket says so (`{ab}^2` = `ab^2`), the spaces inside
`\\text{}`, and variant letters (`\\epsilon` = `\\varepsilon`).

A formula a reader writes as plain text is not lost: a gold formula without any structure ('n = 10') counts as found when its
characters stand in the reading's prose as whole words, because a page image does not say whether `n` was math. Conversely a
reader's formula of characters and scripts that matches no gold formula counts as prose: the web edition has `s 2` for a raised 2.

Prose. Token edit distance plus recall and precision over the token multiset: low recall means the reading lacks words, the real
suspect, while low precision means it holds words the gold lacks. The order only moves the edit distance. Math is out on both
sides. Tokens are those of page_checks.tokens_of, so the two measures of a reading speak of the same words. The publisher's first
and last block on a page may be cut at a word chosen by alignment, so at a page break a few tokens do not count in either
direction (`PAGE_BREAK_TOKENS`).

Tables. Every gold cell, present and in place, compared after the same normal form as formulas, so math in a cell is held
against math or plain text alike and case stays significant (Aaa is not AAA). Rows are aligned first: a lost row costs its own
cells, not every row below it. TEDS, which the plan left optional, is not computed.

Raster tables, furniture, page labels and the rewriting rate are explained at their functions. A score holds counts and
labels, never page text, so a stored score can sit beside a reading of a licensed page.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from backend.conversion.checks import katex_check, page_checks
from backend.conversion.measurement import publisher_gold
from backend.conversion.contract.page_contract import VOCAB, Block, Cell, ParsedPage
from backend.conversion.measurement.publisher_gold import GoldCell, GoldFormula, GoldTable, PageGold, expand_spans

FRAC, SQRT, ROOT, SUB, SUP, NEXT, END = '\\frac', '\\sqrt', '\\root', '\\sub', '\\sup', '\\next', '\\end'
OPENERS = (FRAC, SQRT, ROOT, SUB, SUP, '\\over:', '\\under:')
NOT_PRINTED = {'annotation', 'annotation-xml', 'mphantom', 'mspace', 'none', 'mprescripts', 'maligngroup', 'malignmark'}
INVISIBLE_CATEGORIES = {'Cf', 'Cc', 'Zs', 'Zl', 'Zp'}  # invisible operators, zero-width characters, every kind of space
BEFORE_NFKC = str.maketrans({'⋯': '…', '⋱': '…'})  # NFKC turns … into three dots; \cdots and \ldots stand for the same thing
CHAR_FOLD = {
    **dict.fromkeys('−–—‐‒―', '-'),  # a minus sign, a hyphen and a dash are one reading of one stroke
    **dict.fromkeys("'’ʹʼ", '′'),
    **dict.fromkeys('·∙', '⋅'),
    **dict.fromkeys('∕⁄', '/'),
    **dict.fromkeys('⩽≦', '≤'),
    **dict.fromkeys('⩾≧', '≥'),
    '∗': '*', '∣': '|', '∥': '‖', '〈': '⟨', '〉': '⟩', '∼': '~', '∖': '\\', '∆': 'Δ', '∶': ':', '∊': '∈',
}
ACCENT_NAMES = {
    **dict.fromkeys(('¯', '‾', '\N{COMBINING MACRON}', '\N{COMBINING OVERLINE}', '―', '_', '−', '-', 'ˉ', '‐', '–', '—'), 'bar'),
    **dict.fromkeys(('^', 'ˆ', '\N{COMBINING CIRCUMFLEX ACCENT}'), 'hat'),
    **dict.fromkeys(('~', '˜', '\N{COMBINING TILDE}', '∼'), 'tilde'),
    **dict.fromkeys(('→', '\N{COMBINING RIGHT ARROW ABOVE}'), 'vec'),
    **dict.fromkeys(('.', '˙', '\N{COMBINING DOT ABOVE}', '⋅', '·'), 'dot'),
    **dict.fromkeys(('¨', '\N{COMBINING DIAERESIS}'), 'ddot'),
    **dict.fromkeys(('⏟', '⏞', '︸', '︷'), 'brace'),
    **dict.fromkeys(('ˇ', '\N{COMBINING CARON}'), 'check'),
    **dict.fromkeys(('˘', '\N{COMBINING BREVE}'), 'breve'),
}
UNRENDERED = '\\unrendered'  # stands for a reader's formula KaTeX refused: it equals nothing
TRAILING_PUNCTUATION = {'.', ',', ';'}

PAGE_BREAK_TOKENS = 5
ABSENCE_THRESHOLD = 90  # rapidfuzz partial_ratio; a starting value: no false alarm on the 14 pages read perfectly (2026-10-30)
PROSE_CLASSES = {name for name, spec in VOCAB['classes'].items()
                 if spec['layer'] == 'body' and spec['content'] == 'V' and name not in ('code', 'table', 'figure', 'formula')}
PREFIX_ATTRIBUTE = {'heading': 'number', 'caption': 'label'}  # an attribute that may hold the block's first printed words


# ---------------------------------------------------------------- the canonical form of a formula

def _leaf(text: str) -> list[str]:
    """Printed characters in normal form, one token each."""
    folded = unicodedata.normalize('NFKC', text.translate(BEFORE_NFKC))
    return [CHAR_FOLD.get(char, char) for char in folded if unicodedata.category(char) not in INVISIBLE_CATEGORIES]


def _children(tag: Tag) -> list[Tag]:
    return [child for child in tag.children if isinstance(child, Tag)]


def _walk(node: Tag) -> list[str]:
    tokens = []
    for child in node.children:
        if isinstance(child, Tag):
            tokens.extend(_element(child))
        elif type(child) is NavigableString:  # not a comment
            tokens.extend(_leaf(str(child)))
    return tokens


def _accent(script: Tag) -> str | None:
    """The accent a script is when it holds one accent character and nothing else, whatever character the source chose."""
    return ACCENT_NAMES.get(''.join(script.get_text().split()))


def _sup_starts_at(tokens: list[str]) -> int | None:
    """Where the superscript group that ends these tokens opens, if they end in one."""
    depth = 0
    for index in range(len(tokens) - 1, -1, -1):
        if tokens[index] == END:
            depth += 1
        elif tokens[index].startswith(OPENERS):
            depth -= 1
            if depth == 0:
                return index if tokens[index] == SUP else None
        elif depth == 0:
            return None
    return None


def _with_scripts(base: list[str], sub: Tag | None, sup: Tag | None) -> list[str]:
    """The base with its scripts: subscript first, whichever way the source nested them."""
    tokens = base
    if sub is not None and (inner := _element(sub)):
        group = [SUB, *inner, END]
        at = _sup_starts_at(tokens)
        tokens = tokens + group if at is None else tokens[:at] + group + tokens[at:]
    if sup is not None and (inner := _element(sup)):
        tokens = tokens + inner if set(inner) == {'′'} else tokens + [SUP, *inner, END]  # x' is x with a prime, sup or not
    return tokens


def _scripted(tag: Tag, name: str) -> list[str]:
    """A limit under or over its operator is a sub or a superscript that moved: display style decides that, not the print.
    Only an accent keeps its own token, with an opening mark, since `\\overline{x-y}` is not `x-\\overline{y}`."""
    kids = _children(tag)
    if not kids:
        return []
    base = _element(kids[0])
    if name in ('mover', 'munder') and len(kids) > 1 and (accent := _accent(kids[1])):
        return [f'\\{name[1:]}:{accent}', *base, END]
    scripts = kids[1:] + [None, None]
    if name in ('msub', 'munder'):
        return _with_scripts(base, scripts[0], None)
    if name in ('msup', 'mover'):
        return _with_scripts(base, None, scripts[0])
    return _with_scripts(base, scripts[0], scripts[1])


def _fenced(tag: Tag) -> list[str]:
    """mfenced keeps its brackets and separators in attributes."""
    separators = ''.join((tag.get('separators', ',') or '').split())
    tokens = _leaf(tag.get('open', '('))
    for index, kid in enumerate(_children(tag)):
        if index and separators:
            tokens += _leaf(separators[min(index - 1, len(separators) - 1)])
        tokens += _element(kid)
    return tokens + _leaf(tag.get('close', ')'))


def _table_row(tag: Tag) -> list[str]:
    """A row without its equation number: mlabeledtr holds it first, KaTeX's \\tag after a second 50% spacer."""
    kids = _children(tag)
    if tag.name.endswith('mlabeledtr'):
        kids = kids[1:]
    spacers = [index for index, kid in enumerate(kids) if kid.get('width') == '50%']
    if len(spacers) == 2:
        kids = kids[:spacers[1]]
    return [token for kid in kids for token in _element(kid)]


def _element(tag: Tag) -> list[str]:
    name = tag.name.split(':')[-1].lower()
    if name in NOT_PRINTED:
        return []
    if name in ('msub', 'msup', 'msubsup', 'munder', 'mover', 'munderover'):
        return _scripted(tag, name)
    if name == 'mfrac':
        kids = _children(tag)
        return [FRAC, *_element(kids[0]), NEXT, *_element(kids[1]), END] if len(kids) >= 2 else _walk(tag)
    if name == 'msqrt':
        return [SQRT, *_walk(tag), END]
    if name == 'mroot':
        kids = _children(tag)
        return [ROOT, *_element(kids[1]), NEXT, *_element(kids[0]), END] if len(kids) >= 2 else _walk(tag)
    if name == 'mfenced':
        return _fenced(tag)
    if name in ('mtr', 'mlabeledtr'):
        return _table_row(tag)
    return _walk(tag)  # math, semantics, mrow, mstyle, mpadded, mtable, mtd: their content is what is printed


def canonical_math(mathml: str | None) -> list[str]:
    """The linear form of MathML, which may hold several math elements side by side, with or without KaTeX's span around them.

    A closing full stop, comma or semicolon goes: publishers set it inside the math ($169.72 x 10 = $1,697.20.), and on the
    page it cannot be told from the sentence's own punctuation, so a reader cannot know which side it belongs to.
    """
    if not mathml or '<' not in mathml:
        return []
    soup = BeautifulSoup(mathml, 'html.parser')
    roots = [root for root in soup.find_all('math') if root.find_parent('math') is None] or [soup]
    tokens = [token for root in roots for token in _walk(root)]
    if tokens and tokens[-1] in TRAILING_PUNCTUATION and tokens[-3:] != ['.', '.', '.']:  # an ellipsis is content
        tokens.pop()
    return tokens


def _is_flat(tokens: list[str]) -> bool:
    """No structure token: what could as well have been typed as plain text."""
    return all(len(token) == 1 for token in tokens)


def _reads_as_prose(tokens: list[str]) -> bool:
    """Characters and scripts only: `s^2` for what a publisher's text may hold as s with a raised 2."""
    return all(len(token) == 1 or token in (SUB, SUP, END) for token in tokens)


def compare_math(reader: list[str], gold: list[str], accepts: tuple[tuple[str, str], ...] = ()) -> tuple[bool, float]:
    """Exact equality and 1 - normalised edit distance of two canonical forms. `accepts` names token pairs that count as
    equal where they stand opposite each other, which is why it is not a translation: an I elsewhere in the formula stays an I."""
    if len(reader) == len(gold) and all(mine == theirs or (mine, theirs) in accepts for mine, theirs in zip(reader, gold)):
        return True, 1.0
    return False, round(Levenshtein.normalized_similarity(reader, gold), 4)


# ---------------------------------------------------------------- the reading's formulas

@dataclass
class ReaderFormula:
    latex: str
    block_id: str
    key: tuple[int, int]  # block index, math index inside the block: which occurrence this is
    label: str | None = None
    display: bool = False
    tokens: list[str] | None = None  # None: KaTeX refused it, or it was not rendered


def _is_prose(block: Block) -> bool:
    return block.cls in PROSE_CLASSES and block.inline is not None


def reader_formulas(page: ParsedPage) -> list[ReaderFormula]:
    """Displayed formulas and math in running text, in reading order; math in table cells stays with its table."""
    found = []
    for index, block in enumerate(page.blocks):
        if block.cls == 'formula' and block.body.strip():
            found.append(ReaderFormula(block.body.strip(), block.id, (index, 0), block.attrs.get('label'), True))
        elif _is_prose(block):
            found.extend(ReaderFormula(latex, block.id, (index, position)) for position, latex in enumerate(block.inline['math']))
    return found


def _rendered_tokens(latex: str, display: bool, rendered: dict) -> list[str] | None:
    """The canonical form of a reader's formula, from page_checks.render_formulas' answer or a plain map of LaTeX to MathML.
    The display flag cannot change the canonical form, so a verdict for the other flag serves as well."""
    value = rendered.get((latex, display), rendered.get((latex, not display), rendered.get(latex)))
    if isinstance(value, katex_check.Rendered):
        value = value.mathml if value.ok else None
    return canonical_math(value) if value else None


# ---------------------------------------------------------------- prose tokens

def _words(text: str) -> list[str]:
    """The tokens the text-layer check compares, with case folded: the web edition has 'Think It Through' where the page's
    style prints capitals, so case says nothing here."""
    return [token.casefold() for token in page_checks.tokens_of(text)]


def _plain_words(tokens: list[str]) -> str:
    """A formula as the words it would be in running text: 'n=10' becomes 'n = 10', and s^2 becomes 's 2'."""
    return ' '.join(re.findall(r'[\w.,%$]+|\S', ''.join(' ' if len(token) > 1 else token for token in tokens)))


def _block_prose(block: Block, as_text: dict[tuple[int, int], list[str]], index: int) -> list[str]:
    """A prose block's tokens: its text, and only the math the formula matching gave back to the prose."""
    parts, math_index = [], 0
    for kind, value in block.inline['segments']:
        if kind != 'math':
            parts.append(value)
            continue
        if (index, math_index) in as_text:
            parts.append(_plain_words(as_text[(index, math_index)]))
        math_index += 1
    tokens = _words(' '.join(parts))
    attribute = PREFIX_ATTRIBUTE.get(block.cls)
    prefix = _words(block.attrs.get(attribute, '')) if attribute else []
    return tokens if tokens[:len(prefix)] == prefix else prefix + tokens


def _found_as_text(tokens: list[str], page: ParsedPage) -> bool:
    """Whether a structureless formula's characters stand in the prose as whole words, whatever the spacing."""
    pattern = re.compile('(?:^|\x00)' + '\x00?'.join(re.escape(token) for token in tokens) + r'[.,;:!?]*(?:\x00|$)')
    texts = (value for block in page.blocks if _is_prose(block) for kind, value in block.inline['segments'] if kind != 'math')
    return any(pattern.search('\x00'.join(''.join(_leaf(word)) for word in text.split())) for text in texts)


# ---------------------------------------------------------------- formulas

def _normal_label(label: str | None) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFKC', label or '') if not ch.isspace()).strip('()[]')


def _match_formulas(gold: list[GoldFormula], gold_tokens: list[list[str]], reader: list[ReaderFormula]) -> dict[int, tuple[int, str]]:
    """Gold index -> (reader index, how): by printed number first, then the best edit distance anywhere, without reuse.
    Greedy rather than optimal: scipy's assignment solver is not a dependency here, and with exact matches taken first the
    two differ only among formulas that are wrong anyway."""
    matches: dict[int, tuple[int, str]] = {}
    used: set[int] = set()
    for gold_index, formula in enumerate(gold):
        if not formula.label:
            continue
        same = [index for index, candidate in enumerate(reader) if index not in used and candidate.label
                and _normal_label(candidate.label) == _normal_label(formula.label)]
        if same:
            best = max(same, key=lambda index: Levenshtein.normalized_similarity(reader[index].tokens or [], gold_tokens[gold_index]))
            matches[gold_index] = (best, 'label')
            used.add(best)
    pairs = []
    for gold_index in range(len(gold)):
        if gold_index in matches:
            continue
        for reader_index, candidate in enumerate(reader):
            if reader_index not in used and candidate.tokens:
                similarity = Levenshtein.normalized_similarity(candidate.tokens, gold_tokens[gold_index])
                if similarity > 0:
                    other_kind = candidate.display != (gold[gold_index].kind == 'display')
                    pairs.append((-similarity, other_kind, gold_index, reader_index))
    for _, _, gold_index, reader_index in sorted(pairs):
        if gold_index not in matches and reader_index not in used:
            matches[gold_index] = (reader_index, 'edit')
            used.add(reader_index)
    return matches


def _score_formulas(page: ParsedPage, gold: PageGold, rendered: dict) -> tuple[dict, set[int], dict[tuple[int, int], list[str]]]:
    """The formula class, plus what it decides for the prose: which gold formulas (by identity, since `t` may stand twice) and
    which reader formulas count as text. On a paper page `reader_extra` says little: its gold does not list all its math."""
    formulas = gold.display + gold.inline
    gold_tokens = [canonical_math(formula.mathml) for formula in formulas]
    reader = reader_formulas(page)
    for candidate in reader:
        candidate.tokens = _rendered_tokens(candidate.latex, candidate.display, rendered)
    matches = _match_formulas(formulas, gold_tokens, reader)
    items, gold_as_text = [], set()
    for index, (formula, tokens) in enumerate(zip(formulas, gold_tokens)):
        item = {'kind': formula.kind, 'label': formula.label, 'placed_by': formula.placed_by, 'how': None, 'reader_block': None,
                'exact': False, 'similarity': 0.0, 'label_ok': None if not formula.label else False}
        if index in matches:
            reader_index, how = matches[index]
            candidate = reader[reader_index]
            item.update(how=how, reader_block=candidate.block_id, label_ok=None if not formula.label else how == 'label')
            if candidate.tokens is None:
                item['how'] = 'unrendered'
            else:
                item['exact'], item['similarity'] = compare_math(candidate.tokens, tokens, formula.accepts)
        if not item['exact'] and _is_flat(tokens) and tokens and _found_as_text(tokens, page):
            item.update(how='as_text', reader_block=None, exact=True, similarity=1.0)
            gold_as_text.add(id(formula))
            matches.pop(index, None)
        items.append(item)
    used = {reader_index for reader_index, _ in matches.values()}
    reader_as_text = {candidate.key: candidate.tokens for index, candidate in enumerate(reader)
                      if index not in used and candidate.tokens and _reads_as_prose(candidate.tokens) and not candidate.display}
    exact = [item for item in items if item['exact']]
    numbered = [item for item in items if item['label']]
    score = {'gold': len(items), 'reader': len(reader), 'exact': len(exact), 'exact_rate': _rate(len(exact), len(items)),
             'mean_similarity': _mean([item['similarity'] for item in items]),
             'display': sum(1 for item in items if item['kind'] == 'display'),
             'display_exact': sum(1 for item in exact if item['kind'] == 'display'),
             'inline': sum(1 for item in items if item['kind'] != 'display'),
             'inline_exact': sum(1 for item in exact if item['kind'] != 'display'),
             'numbered': len(numbered), 'label_ok': sum(1 for item in numbered if item['label_ok']),
             'missing': sum(1 for item in items if item['how'] is None), 'as_text': len(gold_as_text),
             'unrendered': sum(1 for candidate in reader if candidate.tokens is None),
             'reader_extra': len(reader) - len(used) - len(reader_as_text), 'items': items}
    return score, gold_as_text, reader_as_text


def _rate(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


# ---------------------------------------------------------------- prose

def _trim_page_break(gold: list[str], reader: list[str], at_start: bool, at_end: bool) -> tuple[list[str], list[str]]:
    """A difference of a few tokens right at a page break counts in neither direction: the gold's cut was found by alignment."""
    operations = list(Levenshtein.opcodes(gold, reader))

    def small(operation) -> bool:
        return (operation.tag != 'equal'
                and max(operation.src_end - operation.src_start, operation.dest_end - operation.dest_start) <= PAGE_BREAK_TOKENS)

    gold_start, reader_start, gold_end, reader_end = 0, 0, len(gold), len(reader)
    if at_start and operations and small(operations[0]):
        gold_start, reader_start = operations[0].src_end, operations[0].dest_end
    if at_end and operations and small(operations[-1]):
        gold_end, reader_end = operations[-1].src_start, operations[-1].dest_start
    return gold[gold_start:gold_end], reader[reader_start:reader_end]


def _gold_prose_tokens(block, gold_as_text: set[int]) -> list[str]:
    parts = []
    for kind, value in block.segments:
        if kind == 'text':
            parts.append(value)
        elif id(value) in gold_as_text:
            parts.append(_plain_words(canonical_math(value.mathml)))
    return _words(' '.join(parts))


def _score_prose(page: ParsedPage, gold: PageGold, gold_as_text: set[int], reader_as_text: dict) -> dict | None:
    """Running text and footnotes are compared apart, since a footnote's place in the reading order says nothing, then added up."""
    if not gold.has_prose:
        return None
    reader_body, reader_notes = [], []
    for index, block in enumerate(page.blocks):
        if _is_prose(block):
            (reader_notes if block.cls == 'footnote' else reader_body).extend(_block_prose(block, reader_as_text, index))
    gold_body = [token for block in gold.prose for token in _gold_prose_tokens(block, gold_as_text)]
    gold_notes = [token for block in gold.footnotes for token in _gold_prose_tokens(block, gold_as_text)]
    gold_kept, reader_kept = _trim_page_break(gold_body, reader_body, gold.starts_mid_block, gold.ends_mid_block)
    distance = Levenshtein.distance(gold_kept, reader_kept) + Levenshtein.distance(gold_notes, reader_notes)
    longest = max(len(gold_kept), len(reader_kept)) + max(len(gold_notes), len(reader_notes))
    gold_bag, reader_bag = Counter(gold_body + gold_notes), Counter(reader_body + reader_notes)
    common = sum((gold_bag & reader_bag).values())
    # Excused is what the page break cut off and the other side really lacks: a word that only moved stays counted as present.
    gold_excused = sum(((Counter(gold_body) - Counter(gold_kept)) & (gold_bag - reader_bag)).values())
    reader_excused = sum(((Counter(reader_body) - Counter(reader_kept)) & (reader_bag - gold_bag)).values())
    gold_total, reader_total = gold_bag.total() - gold_excused, reader_bag.total() - reader_excused
    return {'gold_tokens': gold_total, 'reader_tokens': reader_total, 'common_tokens': common,
            'similarity': round(1 - distance / longest, 4) if longest else 1.0,
            'recall': _rate(common, gold_total), 'precision': _rate(common, reader_total)}


# ---------------------------------------------------------------- tables

def _gold_cell_tokens(cell: GoldCell) -> tuple[str, ...]:
    return tuple(token for kind, value in cell.segments
                 for token in (_leaf(value) if kind == 'text' else canonical_math(value.mathml)))


def _reader_cell_tokens(cell: Cell | None, rendered: dict) -> tuple[str, ...]:
    if cell is None or not cell.inline:
        return ()
    tokens = []
    for kind, value in cell.inline['segments']:
        if kind == 'math':
            tokens.extend(_rendered_tokens(value, False, rendered) or [UNRENDERED])
        else:
            tokens.extend(_leaf(value))
    return tuple(tokens)


def _same_cells(gold_row: list[tuple | None], reader_row: list[tuple]) -> int:
    """Cells in place. A position a span merely covers holds None in the gold: no cell of its own, so it is not counted."""
    return sum(1 for column, tokens in enumerate(gold_row)
               if tokens is not None and tokens == (reader_row[column] if column < len(reader_row) else ()))


def _align_rows(gold_rows: list[list[tuple | None]], reader_rows: list[list[tuple]]) -> list[tuple[int, int]]:
    """Row pairs in order that keep the most cells in place, by dynamic programming. rapidfuzz's opcodes and difflib treat a
    row as an atom, so a table with one wrong cell in every row leaves them no anchor."""
    height, across = len(gold_rows), len(reader_rows)
    best = [[0] * (across + 1) for _ in range(height + 1)]

    def paired(row: int, other: int) -> int:  # the +1 prefers pairing rows in order over skipping them when nothing else decides
        return best[row + 1][other + 1] + _same_cells(gold_rows[row], reader_rows[other]) + 1

    for row in range(height - 1, -1, -1):
        for other in range(across - 1, -1, -1):
            best[row][other] = max(best[row + 1][other], best[row][other + 1], paired(row, other))
    pairs, row, other = [], 0, 0
    while row < height and other < across:
        if best[row][other] == paired(row, other):
            pairs.append((row, other))
            row, other = row + 1, other + 1
        elif best[row][other] == best[row + 1][other]:
            row += 1
        else:
            other += 1
    return pairs


def _table_against(table: GoldTable, reader_block: Block | None, rendered: dict) -> dict:
    gold_rows = [[None if cell is None else _gold_cell_tokens(cell) for cell in row] for row in table.grid()]
    cells = [tokens for row in gold_rows for tokens in row if tokens is not None]
    filled = [tokens for tokens in cells if tokens]
    reader_rows = []
    if reader_block is not None:
        reader_rows = [[_reader_cell_tokens(cell, rendered) for cell in row] for row in expand_spans(reader_block.rows)]
    pairs = _align_rows(gold_rows, reader_rows)
    in_place = sum(_same_cells(gold_rows[row], reader_rows[other]) for row, other in pairs)
    present = sum((Counter(filled) & Counter(tokens for row in reader_rows for tokens in row if tokens)).values())
    return {'reader_block': reader_block.id if reader_block else None, 'lost': reader_block is None,
            'partial': table.rows_kept is not None, 'cells': len(cells), 'exact': in_place, 'exact_rate': _rate(in_place, len(cells)),
            'filled_cells': len(filled), 'present': present, 'gold_rows': len(gold_rows), 'reader_rows': len(reader_rows),
            'rows_aligned': len(pairs)}


def _raster_text(block: Block) -> str:
    if block.cls == 'table' and block.rows:
        return ' '.join(cell.text for row in block.rows for cell in row)
    return block.body


def _score_tables(page: ParsedPage, gold: PageGold, rendered: dict) -> dict | None:
    """Gold tables take the reader's tables that fit them best, without reuse. A table the page prints as a picture is known
    only through its alt text, which paraphrases the labels, so its gold is the numbers of the alt text. They must stand in a
    table no gold table claimed, in a figure or in a caption; a real table on the page cannot stand in for the picture."""
    if not gold.tables and not any(raster.values for raster in gold.rasters):
        return None
    candidates = [block for block in page.blocks if block.cls == 'table' and block.rows]
    scored = sorted((-_table_against(table, block, rendered)['exact'], table_index, candidate_index)
                    for table_index, table in enumerate(gold.tables) for candidate_index, block in enumerate(candidates))
    assigned, used = {}, set()
    for _, table_index, candidate_index in scored:
        if table_index not in assigned and candidate_index not in used:
            assigned[table_index] = candidate_index
            used.add(candidate_index)
    tables = [_table_against(table, candidates[assigned[index]] if index in assigned else None, rendered)
              for index, table in enumerate(gold.tables)]
    spare = [block for index, block in enumerate(candidates) if index not in used]
    spare += [block for block in page.blocks if block.cls in ('figure', 'caption')]
    numbers = set(publisher_gold.NUMBER.findall(' '.join(_raster_text(block) for block in spare)))
    values = sorted({value for raster in gold.rasters for value in raster.values})
    return {'tables': tables, 'cells': sum(row['cells'] for row in tables), 'exact': sum(row['exact'] for row in tables),
            'exact_rate': _rate(sum(row['exact'] for row in tables), sum(row['cells'] for row in tables)),
            'filled_cells': sum(row['filled_cells'] for row in tables), 'present': sum(row['present'] for row in tables),
            'lost': sum(1 for row in tables if row['lost']), 'reader_tables': len(candidates),
            'raster_values': len(values), 'raster_found': sum(1 for value in values if value in numbers)}


# ---------------------------------------------------------------- furniture and page label

def _without_folio(tokens: list[str], folio: list[str]) -> list[str]:
    if folio and tokens[:len(folio)] == folio:
        return tokens[len(folio):]
    if folio and tokens[-len(folio):] == folio:
        return tokens[:-len(folio)]
    return tokens


def _score_furniture(page: ParsedPage, gold: PageGold) -> dict:
    """The olmOCR-Bench absence test on tokens: the running head, the running foot and the page number must not stand in body
    blocks. The test type is reused on top of rapidfuzz, without installing olmocr, whose bench extra pulls in four model SDKs
    and Playwright. A phrase the gold's own body also holds tests nothing and is skipped: the running head of a section's
    first page repeats its heading. The folio alone counts only as a whole block, since '190' may be a figure in a sentence."""
    body_blocks = [_words(block.inline['plain']) for block in page.blocks if _is_prose(block)]
    reader_text = ' '.join(token for tokens in body_blocks for token in tokens)
    gold_text = ' '.join(token for block in gold.prose + gold.footnotes for token in _words(block.text))
    folio = _words(gold.printed_label or '')
    tests = {}
    for name, phrase in (('header', gold.header), ('footer', gold.footer)):
        needle = ' '.join(_without_folio(_words(phrase), folio))
        if needle and fuzz.partial_ratio(needle, gold_text) < ABSENCE_THRESHOLD:
            tests[name] = fuzz.partial_ratio(needle, reader_text) < ABSENCE_THRESHOLD
    if folio:
        tests['folio'] = folio not in body_blocks
    return {'tests': len(tests), 'passed': sum(tests.values()), 'failed': sorted(name for name, passed in tests.items() if not passed)}


def _score_label(page: ParsedPage, gold: PageGold) -> dict:
    read = str(page.front.get('printed_label', '')).strip()
    expected = gold.printed_label or 'none'
    return {'gold': expected, 'read': read, 'ok': read == expected}


# ---------------------------------------------------------------- one page, many pages

@dataclass
class PageScore:
    gold_id: str
    pdf_file: str
    pdf_page: int
    valid: bool
    formula: dict
    prose: dict | None
    table: dict | None
    page_label: dict
    furniture: dict
    rewriting: dict | None

    def as_dict(self) -> dict:
        return asdict(self)


def score_reading(page: ParsedPage, gold: PageGold, rendered: dict | None = None) -> PageScore:
    """One reading against its gold. `rendered` is page_checks.render_formulas' answer for a batch holding this page, or a plain
    map of LaTeX to MathML; None renders here, which starts a child process. A formula missing from the map counts as unrendered.

    Rewriting is the share of the reading's words the page does not hold (FaithC4 in the paper 'Do VLMs Read or Rewrite?'):
    1 - precision, on prose that has a publisher's wording, measured on the raw reading before any correction.
    """
    if rendered is None:
        rendered = page_checks.render_formulas([page])
    formula, gold_as_text, reader_as_text = _score_formulas(page, gold, rendered)
    prose = _score_prose(page, gold, gold_as_text, reader_as_text)
    rewriting = None
    if prose is not None and prose['precision'] is not None:
        rewriting = {'precision': prose['precision'], 'rate': round(1 - prose['precision'], 4)}
    return PageScore(gold.gold_id, gold.pdf_file, gold.pdf_page, page.valid, formula, prose, _score_tables(page, gold, rendered),
                     _score_label(page, gold), _score_furniture(page, gold), rewriting)


def summarize(scores: list[PageScore]) -> dict:
    """Per class over many pages. Rates are over items, so that a page with many formulas weighs more than one with few."""
    formula = [score.formula for score in scores]
    prose = [score.prose for score in scores if score.prose]
    tables = [score.table for score in scores if score.table]
    labels = [score.page_label for score in scores]
    furniture = [score.furniture for score in scores]
    rewriting = [score.rewriting for score in scores if score.rewriting]

    def total(rows: list[dict], key: str) -> int:
        return sum(row[key] for row in rows)

    labels_ok = sum(1 for row in labels if row['ok'])
    return {
        'pages': len(scores),
        'formula': {'gold': total(formula, 'gold'), 'exact': total(formula, 'exact'),
                    'exact_rate': _rate(total(formula, 'exact'), total(formula, 'gold')),
                    'mean_similarity': _mean([item['similarity'] for row in formula for item in row['items']]),
                    'display': total(formula, 'display'), 'display_exact': total(formula, 'display_exact'),
                    'inline': total(formula, 'inline'), 'inline_exact': total(formula, 'inline_exact'),
                    'numbered': total(formula, 'numbered'), 'label_ok': total(formula, 'label_ok'),
                    'missing': total(formula, 'missing'), 'as_text': total(formula, 'as_text'),
                    'unrendered': total(formula, 'unrendered'), 'reader_extra': total(formula, 'reader_extra')},
        'prose': {'pages': len(prose), 'gold_tokens': total(prose, 'gold_tokens'), 'reader_tokens': total(prose, 'reader_tokens'),
                  'mean_similarity': _mean([row['similarity'] for row in prose]),
                  'recall': _rate(total(prose, 'common_tokens'), total(prose, 'gold_tokens')),
                  'precision': _rate(total(prose, 'common_tokens'), total(prose, 'reader_tokens'))},
        'table': {'pages': len(tables), 'tables': sum(len(row['tables']) for row in tables), 'lost': total(tables, 'lost'),
                  'cells': total(tables, 'cells'), 'exact': total(tables, 'exact'),
                  'exact_rate': _rate(total(tables, 'exact'), total(tables, 'cells')),
                  'filled_cells': total(tables, 'filled_cells'), 'present': total(tables, 'present'),
                  'raster_values': total(tables, 'raster_values'), 'raster_found': total(tables, 'raster_found')},
        'page_label': {'pages': len(labels), 'ok': labels_ok, 'rate': _rate(labels_ok, len(labels))},
        'furniture': {'tests': total(furniture, 'tests'), 'passed': total(furniture, 'passed'),
                      'rate': _rate(total(furniture, 'passed'), total(furniture, 'tests'))},
        'rewriting': {'pages': len(rewriting), 'mean_rate': _mean([row['rate'] for row in rewriting])},
    }


# ---------------------------------------------------------------- the comparator held against the gold

GOLD_LATEX_FIXES = {'𝔼': r'\mathbb{E}'}  # the preview converter leaves this character raw, and strict KaTeX refuses it in math


def gold_latex_for_katex(latex: str) -> str:
    for raw, command in GOLD_LATEX_FIXES.items():
        latex = latex.replace(raw, command)
    return latex


def _mutations(latex: str) -> dict[str, str]:
    """A plausible misreading of each kind, planted once: every one must change the canonical form."""
    found = {}

    def plant(name: str, pattern: str, change) -> None:
        match = re.search(pattern, latex)
        if match and (changed := change(match)) != match.group():
            found[name] = f'{latex[:match.start()]}{changed}{latex[match.end():]}'

    plant('digit', r'\d', lambda m: str((int(m.group()) + 1) % 10))
    plant('sign', r'[+-]', lambda m: '-' if m.group() == '+' else '+')
    plant('exponent', r'\^\{([^{}]+)\}|\^(\w)', lambda m: f'^{{9{m.group(1) or m.group(2)}}}')
    plant('dropped_term', r'\s*\+\s*[^+=\-{}\\&]+', lambda m: '')
    plant('relation', r'=', lambda m: r'\approx ')
    plant('flipped_fraction', r'\\frac\{([^{}]*)\}\{([^{}]*)\}', lambda m: rf'\frac{{{m.group(2)}}}{{{m.group(1)}}}')
    plant('swapped_scripts', r'_\{([^{}]*)\}\^\{([^{}]*)\}', lambda m: f'_{{{m.group(2)}}}^{{{m.group(1)}}}')
    plant('dropped_accent', r'\\(?:overline|bar|hat)\{([^{}]*)\}', lambda m: m.group(1))
    plant('dropped_root', r'\\sqrt\{([^{}]*)\}', lambda m: m.group(1))
    plant('dropped_bracket', r'(?<!\\left)(?<!\\right)[()\[\]]', lambda m: '')
    plant('changed_letter', r'\\(?:mu|sigma|tau|epsilon)\b', lambda m: r'\theta')
    return found


def self_check(pages: list[PageGold] | None = None) -> dict:
    """Run KaTeX on every gold formula's LaTeX and compare the canonical form with that of the gold's MathML.

    Where the LaTeX is a preview converted from the same MathML, an agreement shows the normal form absorbs KaTeX's way of
    writing things; only the arXiv paper's LaTeX is independent of its MathML. Then a misreading of each kind is planted in
    every formula it applies to: the sensitivity, without which a comparator that folds everything would look perfect.
    """
    pages = publisher_gold.all_gold() if pages is None else pages
    rows = [(page, formula) for page in pages for formula in page.all_formulas() if formula.latex]
    results = katex_check.check_many([(gold_latex_for_katex(formula.latex), formula.kind == 'display') for _, formula in rows])
    report = {'formulas': len(rows), 'rendered': 0, 'agreed': 0, 'by_origin': {}, 'render_failed': [], 'disagreements': []}
    mutation_rows = []
    for (page, formula), result in zip(rows, results):
        origin = report['by_origin'].setdefault(formula.latex_origin, {'formulas': 0, 'rendered': 0, 'agreed': 0})
        origin['formulas'] += 1
        where = {'page': page.gold_id, 'kind': formula.kind, 'label': formula.label, 'latex': formula.latex}
        if not result.ok:
            report['render_failed'].append(where | {'error': result.error})
            continue
        report['rendered'] += 1
        origin['rendered'] += 1
        gold_tokens = canonical_math(formula.mathml)
        katex_tokens = canonical_math(result.mathml)
        same, similarity = compare_math(katex_tokens, gold_tokens)
        if same:
            report['agreed'] += 1
            origin['agreed'] += 1
        else:
            report['disagreements'].append(where | {'similarity': similarity, 'katex': katex_tokens, 'gold': gold_tokens})
        for name, mutated in _mutations(gold_latex_for_katex(formula.latex)).items():
            mutation_rows.append((name, mutated, formula.kind == 'display', katex_tokens, where))
    planted = {}
    mutated_results = katex_check.check_many([(mutated, display) for _, mutated, display, _, _ in mutation_rows])
    for (name, mutated, _, katex_tokens, where), result in zip(mutation_rows, mutated_results):
        kind = planted.setdefault(name, {'tried': 0, 'detected': 0, 'not_rendered': 0, 'missed': []})
        if not result.ok:
            kind['not_rendered'] += 1
            continue
        kind['tried'] += 1
        if canonical_math(result.mathml) != katex_tokens:
            kind['detected'] += 1
        else:
            kind['missed'].append(where | {'mutated': mutated})
    report['agreement_rate'] = _rate(report['agreed'], report['formulas'])
    report['mutations'] = planted
    return report


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    arguments = argparse.ArgumentParser(description='Hold the formula comparator against the gold itself.')
    arguments.add_argument('--out', type=Path, help='write the full report here')
    out = arguments.parse_args().out
    report = self_check()
    if out:
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    brief = {key: value for key, value in report.items() if key not in ('disagreements', 'render_failed')}
    print(json.dumps(brief, ensure_ascii=False, indent=1))
    print(f"disagreements: {len(report['disagreements'])}, not rendered: {len(report['render_failed'])}")


if __name__ == '__main__':
    main()
