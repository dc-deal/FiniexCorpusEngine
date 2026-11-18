"""Plausible reading errors, planted one at a time: the measure of what stage 2 and the judge catch.

A reading gold shows to be right gets one known error, as in section 3.5 of the design. The answer is a detection rate per
kind of error, which no clean reading can give. The errors are content errors, never format errors: every mutated page still
passes stage 1. Deterministic by seed, so a measurement can be repeated. Like injecting known faults into a backtest's data to
see which validator notices.

    plant(parsed, kind, seed=0) -> Planted | None   # None: this page has nothing to plant that error on
"""

import copy
import random
import re
from dataclasses import dataclass

from backend.conversion.contract.page_contract import ParsedPage, parse

PROSE_CLASSES = ('paragraph', 'list_item', 'footnote', 'quote')
HIDDEN = re.compile(r'\\\(.*?\\\)|\{[^}]*\}|\[[^\]]*\]\{', re.S)  # inline math and attribute spans are not prose
DIGIT = re.compile(r'\d')
NUMBER = re.compile(r'\d[\d,.]*\d')
WORD = re.compile(r'[A-Za-z]{4,}')
PAIR = re.compile(r'\b([A-Za-z]{4,}) ([A-Za-z]{4,})\b')
SENTENCE_END = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')
OPERATOR_FLIPS = (('+', '-'), ('-', '+'), (r'\times', r'\div'), (r'\leq', r'\geq'), ('<', '>'))
TERM = re.compile(r' [+-] [^+\-=&\\{}^_]+(?=$| =| \\\\)')
CELL_TEXT = re.compile(r'>([^<]+)<')
ROW = re.compile(r'<tr\b.*?</tr>\s*', re.S)
CODE_TOKEN = re.compile(r'[A-Za-z_]{3,}')
NEAR_WORDS = {'increase': 'decrease', 'decrease': 'increase', 'higher': 'lower', 'lower': 'higher', 'more': 'less', 'less': 'more',
              'before': 'after', 'after': 'before', 'first': 'second', 'second': 'first', 'positive': 'negative',
              'negative': 'positive', 'larger': 'smaller', 'smaller': 'larger', 'debit': 'credit', 'credit': 'debit',
              'assets': 'liabilities', 'liabilities': 'assets', 'income': 'expense', 'expense': 'income', 'above': 'below',
              'below': 'above', 'high': 'low', 'long': 'short', 'short': 'long', 'buyer': 'seller', 'seller': 'buyer',
              'stricter': 'stronger', 'annual': 'monthly', 'current': 'prior', 'prior': 'current', 'total': 'average',
              'average': 'total', 'return': 'yield', 'value': 'price', 'price': 'value', 'rate': 'ratio', 'ratio': 'rate'}
INVENTED_SENTENCES = ('This holds for every period considered here.', 'The result is the same under either method.',
                      'Most firms report this figure each quarter.')
GROUPS = {'prose_digit_change': 'prose', 'prose_digit_drop': 'prose', 'word_replace': 'prose', 'word_swap': 'prose',
          'sentence_drop': 'prose', 'block_drop': 'prose', 'sentence_invented': 'prose', 'inline_math_invented': 'prose',
          'formula_digit_change': 'formula', 'formula_operator_flip': 'formula', 'formula_term_drop': 'formula',
          'formula_label_change': 'formula', 'table_cell_change': 'table', 'table_row_drop': 'table',
          'code_indent_change': 'code', 'code_token_change': 'code', 'figure_label_drop': 'figure',
          'caption_number_change': 'structure'}
KINDS = tuple(GROUPS)


@dataclass(frozen=True)
class Planted:
    kind: str
    block: str
    detail: str
    text: str  # the mutated page in markdown form


@dataclass(frozen=True)
class _Change:
    block: str
    body: str | None  # None drops the block
    attrs: dict | None = None
    detail: str = ''


def to_markdown(page: ParsedPage) -> str:
    """A parsed page in markdown form, whichever form it was read in."""
    lines = ['---'] + [f'{name}: "{value}"' for name, value in page.front.items()] + ['---', '']
    for block in page.blocks:
        colons = [len(line) - len(line.lstrip(':')) for line in block.body.split('\n')]
        fence = ':' * max(3, max(colons, default=0) + 1)
        attrs = ''.join(f' {name}="{str(value)}"' for name, value in block.attrs.items())
        lines += [f'{fence} {{#{block.id} .{block.cls}{attrs}}}', *block.body.split('\n'), fence, '']
    return '\n'.join(lines)


def _blocks(page: ParsedPage, classes: tuple[str, ...], rng: random.Random) -> list:
    chosen = [block for block in page.blocks if block.cls in classes and block.body.strip()]
    rng.shuffle(chosen)
    return chosen


def _free_spans(body: str, pattern: re.Pattern) -> list[tuple[int, int]]:
    masked = HIDDEN.sub(lambda match: ' ' * len(match.group(0)), body)
    return [match.span() for match in pattern.finditer(masked)]


def _other_digit(digit: str, rng: random.Random) -> str:
    return str((int(digit) + rng.choice((1, 2, 3))) % 10)


def _digit_changes(page, classes, rng):
    for block in _blocks(page, classes, rng):
        spans = _free_spans(block.body, DIGIT)
        rng.shuffle(spans)
        for start, _ in spans[:2]:
            new = _other_digit(block.body[start], rng)
            yield _Change(block.id, block.body[:start] + new + block.body[start + 1:], detail=f'a digit became {new}')


def prose_digit_change(page, rng):
    yield from _digit_changes(page, PROSE_CLASSES, rng)


def prose_digit_drop(page, rng):
    for block in _blocks(page, PROSE_CLASSES, rng):
        for start, end in _free_spans(block.body, NUMBER)[:2]:
            yield _Change(block.id, block.body[:start] + block.body[start + 1:], detail='a number lost its first digit')


def word_replace(page, rng):
    for block in _blocks(page, PROSE_CLASSES, rng):
        for start, end in _free_spans(block.body, WORD):
            word = block.body[start:end]
            near = NEAR_WORDS.get(word.lower())
            if near:
                near = near.capitalize() if word[0].isupper() else near
                yield _Change(block.id, block.body[:start] + near + block.body[end:], detail=f'{word} became {near}')


def word_swap(page, rng):
    for block in _blocks(page, PROSE_CLASSES, rng):
        spans = _free_spans(block.body, PAIR)
        if spans:
            start, end = rng.choice(spans)
            first, second = block.body[start:end].split(' ')
            yield _Change(block.id, block.body[:start] + f'{second} {first}' + block.body[end:], detail='two words swapped')


def sentence_drop(page, rng):
    for block in _blocks(page, ('paragraph',), rng):
        sentences = SENTENCE_END.split(block.body)
        if len(sentences) >= 2:
            index = rng.randrange(len(sentences))
            yield _Change(block.id, ' '.join(sentences[:index] + sentences[index + 1:]), detail='a sentence dropped')


def block_drop(page, rng):
    for block in _blocks(page, ('paragraph', 'list_item', 'heading'), rng):
        if not any(other.attrs.get('of') == block.id or other.attrs.get('in') == block.id for other in page.blocks):
            yield _Change(block.id, None, detail=f'a whole .{block.cls} dropped')


def sentence_invented(page, rng):
    for block in _blocks(page, ('paragraph',), rng):
        if block.body.rstrip().endswith('.'):
            yield _Change(block.id, f'{block.body.rstrip()} {rng.choice(INVENTED_SENTENCES)}', detail='a sentence invented')


def inline_math_invented(page, rng):
    for block in _blocks(page, ('paragraph',), rng):
        if '\\(' not in block.body and '. ' in block.body:
            yield _Change(block.id, block.body.replace('. ', r' \(r_t\). ', 1), detail='inline math invented')


def formula_digit_change(page, rng):
    yield from _digit_changes(page, ('formula',), rng)


def formula_operator_flip(page, rng):
    for block in _blocks(page, ('formula',), rng):
        for old, new in OPERATOR_FLIPS:
            if old in block.body and not block.body.lstrip().startswith(old):
                yield _Change(block.id, block.body.replace(old, new, 1), detail=f'{old} became {new}')


def formula_term_drop(page, rng):
    for block in _blocks(page, ('formula',), rng):
        terms = list(TERM.finditer(block.body))
        if terms:
            term = rng.choice(terms)
            yield _Change(block.id, block.body[:term.start()] + block.body[term.end():], detail='a term dropped')


def formula_label_change(page, rng):
    for block in _blocks(page, ('formula',), rng):
        label = block.attrs.get('label', '')
        if label and label[-1].isdigit():
            new = label[:-1] + _other_digit(label[-1], rng)
            yield _Change(block.id, block.body, attrs={'label': new}, detail=f'label {label} became {new}')


def _cell_digit_spans(body: str) -> list[int]:
    return [match.start(1) + digit.start() for match in CELL_TEXT.finditer(body) for digit in DIGIT.finditer(match.group(1))]


def table_cell_change(page, rng):
    for block in _blocks(page, ('table',), rng):
        spans = _cell_digit_spans(block.body)
        rng.shuffle(spans)
        for start in spans[:2]:
            new = _other_digit(block.body[start], rng)
            yield _Change(block.id, block.body[:start] + new + block.body[start + 1:], detail=f'a digit in a cell became {new}')


def table_row_drop(page, rng):
    for block in _blocks(page, ('table',), rng):
        rows = list(ROW.finditer(block.body))
        if len(rows) >= 3:
            row = rng.choice(rows[1:])
            yield _Change(block.id, block.body[:row.start()] + block.body[row.end():], detail='a table row dropped')


def code_indent_change(page, rng):
    for block in _blocks(page, ('code',), rng):
        lines = block.body.split('\n')
        indented = [index for index, line in enumerate(lines) if line.startswith('  ')]
        for index in indented[:3]:
            yield _Change(block.id, '\n'.join(lines[:index] + [lines[index][2:]] + lines[index + 1:]), detail='a line lost two spaces')
        printed = [index for index, line in enumerate(lines) if index and line.strip()]  # spaces on a blank line would change nothing
        if not indented and printed:
            index = rng.choice(printed)
            yield _Change(block.id, '\n'.join(lines[:index] + ['    ' + lines[index]] + lines[index + 1:]), detail='a line gained four spaces')


def code_token_change(page, rng):
    for block in _blocks(page, ('code',), rng):
        spans = [match.span() for match in DIGIT.finditer(block.body)]
        if spans:
            start, _ = rng.choice(spans)
            new = _other_digit(block.body[start], rng)
            yield _Change(block.id, block.body[:start] + new + block.body[start + 1:], detail=f'a digit became {new}')
        tokens = list(CODE_TOKEN.finditer(block.body))
        if tokens:
            token = rng.choice(tokens)
            yield _Change(block.id, block.body[:token.end() - 1] + block.body[token.end():], detail='an identifier lost its last letter')


def figure_label_drop(page, rng):
    for block in _blocks(page, ('figure',), rng):
        lines = [line for line in block.body.split('\n') if line.strip()]
        if len(lines) >= 2:
            lines.pop(rng.randrange(len(lines)))
            yield _Change(block.id, '\n'.join(lines), detail='a label inside a figure dropped')


def caption_number_change(page, rng):
    yield from _digit_changes(page, ('caption',), rng)


MUTATORS = {kind: globals()[kind] for kind in KINDS}


def plant(parsed: ParsedPage, kind: str, seed: int = 0) -> Planted | None:
    """One error of this kind on this page, or None when it has nothing to plant it on."""
    rng = random.Random(f'{kind}:{seed}')
    for change in MUTATORS[kind](parsed, rng):
        mutated = copy.deepcopy(parsed)
        block = mutated.block(change.block)
        if change.body is None:
            mutated.blocks.remove(block)
        else:
            block.body = change.body
        block.attrs.update(change.attrs or {})
        text = to_markdown(mutated)
        if parse(text, 'markdown').valid:
            return Planted(kind, change.block, change.detail, text)
    return None
