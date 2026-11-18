from pathlib import Path

import pytest

from backend.conversion.judge import planted_errors
from backend.conversion.contract.page_contract import parse
from backend.conversion.judge.planted_errors import GROUPS, KINDS, plant, to_markdown

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'page_contract'
P179 = parse((FIXTURES / 'openstax-finance-2e_p0179.page.md').read_text(encoding='utf-8'), 'markdown')
P405 = parse((FIXTURES / 'openstax-finance-2e_p0405.page.md').read_text(encoding='utf-8'), 'markdown')
P446 = parse((FIXTURES / 'openstax-finance-2e_p0446.page.md').read_text(encoding='utf-8'), 'markdown')


@pytest.mark.parametrize('page', [P179, P405, P446], ids=['p179', 'p405', 'p446'])
def test_the_serialiser_round_trips(page):
    again = parse(to_markdown(page), 'markdown')
    assert again.valid, again.errors
    assert [(b.id, b.cls, b.attrs, b.body) for b in again.blocks] == [(b.id, b.cls, b.attrs, b.body) for b in page.blocks]
    assert again.front == page.front


def test_a_listing_with_a_colon_line_gets_a_longer_fence():
    page = parse(to_markdown(P446), 'markdown')
    page.block('b03').body = '::: note\ntext\n:::'
    assert parse(to_markdown(page), 'markdown').block('b03').body == '::: note\ntext\n:::'


@pytest.mark.parametrize('kind', KINDS)
def test_a_planted_error_changes_the_page_and_stays_valid(kind):
    planted = next((found for found in (plant(page, kind) for page in (P179, P405, P446)) if found), None)
    if kind == 'formula_term_drop' and planted is None:
        return  # the example formulas have no free term; other pages do
    assert planted is not None, kind
    mutated = parse(planted.text, 'markdown')
    assert mutated.valid, mutated.errors
    assert planted.detail and planted.kind == kind


def test_planting_is_deterministic_and_the_seed_can_vary_it():
    assert plant(P179, 'prose_digit_change', 3) == plant(P179, 'prose_digit_change', 3)
    assert len({plant(P179, 'prose_digit_change', seed).text for seed in range(6)}) > 1


def test_a_page_with_nothing_to_plant_on_says_so():
    assert plant(P179, 'code_indent_change') is None
    assert plant(P179, 'figure_label_drop') is None


def test_a_prose_digit_is_never_planted_inside_math():
    planted = plant(P179, 'prose_digit_change')
    mutated = parse(planted.text, 'markdown')
    assert mutated.block('b17').inline['math'] == P179.block('b17').inline['math']


def test_a_formula_error_touches_the_formula_and_a_label_error_only_the_label():
    planted = plant(P179, 'formula_digit_change')
    assert parse(planted.text, 'markdown').block(planted.block).body != P179.block(planted.block).body
    planted = plant(P179, 'formula_label_change')
    mutated = parse(planted.text, 'markdown').block(planted.block)
    assert mutated.attrs['label'] != P179.block(planted.block).attrs['label'] and mutated.body == P179.block(planted.block).body


def test_a_dropped_block_is_gone_and_nothing_points_to_it():
    planted = plant(P179, 'block_drop')
    mutated = parse(planted.text, 'markdown')
    assert mutated.block(planted.block) is None and mutated.valid


def test_a_table_row_is_dropped_whole_and_a_cell_digit_stays_in_its_cell():
    planted = plant(P179, 'table_row_drop')
    assert len(parse(planted.text, 'markdown').block('b11').rows) == len(P179.block('b11').rows) - 1
    planted = plant(P179, 'table_cell_change')
    cells = [[cell.text for cell in row] for row in parse(planted.text, 'markdown').block('b11').rows]
    original = [[cell.text for cell in row] for row in P179.block('b11').rows]
    assert sum(a != b for one, other in zip(cells, original) for a, b in zip(one, other)) == 1


def test_every_kind_belongs_to_a_group():
    assert set(GROUPS) == set(KINDS) == set(planted_errors.MUTATORS)
