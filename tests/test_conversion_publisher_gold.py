import json

import pytest

from backend.conversion.measurement import publisher_gold
from backend.conversion.measurement.publisher_gold import GoldCell, GoldTable, parse_gold

# Short literals in the truth files' shape, from OpenStax Principles of Finance 2e and Principles of Accounting (CC BY-NC-SA 4.0).
MATH = '<math display="inline"><semantics><mrow><mo>(</mo><mn>1</mn><mo>+</mo><mi>r</mi><mo>)</mo></mrow></semantics></math>'
EQUATION = '<math display="block"><semantics><mrow><mi>FV</mi><mo>=</mo><mi>PV</mi></mrow></semantics></math>'
OPENSTAX_PAGE = {
    'id': 'fin_p0204', 'pdf': 'openstax_principles_of_finance_2e.pdf', 'pdf_page': 204, 'printed_page': '190',
    'pdf_header': '190 7 • Time Value of Money I: Single Payment Value', 'licence': 'CC BY-NC-SA 4.0',
    'blocks': [
        {'kind': 'para', 'partial': {'starts_mid_block': True, 'ends_mid_block': False}, 'text_md': 'of 4% reflects the interest the account would earn.', 'math': []},
        {'kind': 'equation', 'eq_number': '7.9', 'partial': None, 'text_md': None, 'math': [{'latex_preview': r'\mathrm{FV} = \mathrm{PV}', 'mathml': EQUATION, 'display': 'block'}]},
        {'kind': 'heading', 'level': 3, 'partial': None, 'text_md': 'Rating Agencies ^8', 'math': []},
        # The script that wrote text_md dropped the space before ')' inside the formula too.
        {'kind': 'list_item', 'ordered': True, 'number': 3, 'partial': None, 'text_md': 'we multiply by $( 1 + r)$ each year, $\\$ 5$ more.', 'math': [
            {'latex_preview': '( 1 + r )', 'mathml': MATH, 'display': 'inline'}, {'latex_preview': '\\$ 5', 'mathml': '<math><mo>$</mo><mn>5</mn></math>', 'display': 'inline'}]},
        {'kind': 'table_title', 'partial': None, 'text_md': 'Types of Business Structures', 'math': []},
        {'kind': 'table', 'partial': {'rows_kept': [0, 1], 'rows_total': 12}, 'rows': [
            {'section': 'thead', 'cells': [{'tag': 'th', 'colspan': 2, 'rowspan': 1, 'text_md': 'Year', 'math': []}, {'tag': 'th', 'colspan': 1, 'rowspan': 2, 'text_md': 'Sum', 'math': []}]},
            {'section': 'tbody', 'cells': [{'tag': 'td', 'colspan': 1, 'rowspan': 1, 'text_md': '$22.50', 'math': []},
                                           {'tag': 'td', 'colspan': 1, 'rowspan': 1, 'text_md': '$( 1 + r)$', 'math': [{'latex_preview': '( 1 + r )', 'mathml': MATH}]}]},
        ]},
        {'kind': 'caption', 'partial': {'starts_mid_block': False, 'ends_mid_block': True}, 'text_md': 'Table 13.3 Calculations for', 'math': []},
        {'kind': 'image', 'partial': None, 'alt': 'Journal entry one: debit Electricity Expense 100; credit Accounts Payable 100. Page 65: 4,000 on January 3, 2019.', 'text_md': None, 'math': []},
        {'kind': 'footnote', 'partial': None, 'text_md': '8 Michael Schmidt. “When to Trust Bond Rating Agencies.”', 'math': []},
    ],
}
PAPER_PAGE = {
    'pdf': 'carta_conversano_kelly_criterion_2020.pdf', 'pdf_page': 5, 'printed_page': '5', 'licence': 'CC BY 4.0',
    'formulas': [
        {'id': 'E14', 'kind': 'display', 'label': '4', 'placed_by': 'printed label', 'latex': r'\frac{W_n}{W_0}', 'latex_origin': 'preview from JATS MathML', 'mathml': MATH},
        {'id': None, 'kind': 'inline', 'label': None, 'placed_by': 'before', 'latex': 'n', 'latex_origin': 'LaTeXML alttext (arXiv HTML)', 'mathml': '<math><mi>n</mi></math>'},
        {'id': None, 'kind': 'inline', 'label': None, 'placed_by': 'after', 'latex': None, 'latex_origin': 'preview from JATS MathML', 'mathml': None},
    ],
}
HAVE_GOLD = (publisher_gold.GOLD_ROOT / 'truth').is_dir()
needs_gold = pytest.mark.skipif(not HAVE_GOLD, reason='the local gold folder is missing, as in a clone')


def test_the_page_facts_arrive():
    gold = parse_gold(OPENSTAX_PAGE)
    assert (gold.pdf_file, gold.pdf_page, gold.printed_label) == ('openstax_principles_of_finance_2e.pdf', 204, '190')
    assert gold.header.startswith('190 7') and gold.has_prose and gold.licence == 'CC BY-NC-SA 4.0' and gold.unmapped == {}


def test_blocks_become_prose_formulas_tables_rasters_and_footnotes():
    gold = parse_gold(OPENSTAX_PAGE)
    assert [block.kind for block in gold.prose] == ['para', 'heading', 'list_item', 'table_title', 'caption']
    assert [(formula.label, formula.kind) for formula in gold.display] == [('7.9', 'display')]
    assert [formula.latex for formula in gold.inline] == ['( 1 + r )', '\\$ 5']
    assert len(gold.tables) == 1 and len(gold.rasters) == 1 and len(gold.footnotes) == 1


def test_a_formula_is_cut_out_of_its_text_though_the_script_dropped_a_space_inside_it():
    block = parse_gold(OPENSTAX_PAGE).prose[2]
    assert block.text == 'we multiply by each year, more.'
    assert [formula.latex for formula in block.formulas] == ['( 1 + r )', '\\$ 5']
    assert [kind for kind, _ in block.segments] == ['text', 'math', 'text', 'math', 'text']


def test_a_prose_dollar_is_not_math():
    page = dict(OPENSTAX_PAGE, blocks=[{'kind': 'para', 'partial': None, 'text_md': 'the $1,000 deposit and the $40 interest', 'math': []}])
    assert parse_gold(page).prose[0].text == 'the $1,000 deposit and the $40 interest'


def test_a_formula_the_text_does_not_hold_raises_rather_than_scoring_against_the_reader():
    page = dict(OPENSTAX_PAGE, blocks=[{'kind': 'para', 'partial': None, 'text_md': 'no math here', 'math': [{'latex_preview': 'x', 'mathml': MATH}]}])
    with pytest.raises(ValueError, match='not found'):
        parse_gold(page)


def test_footnote_markers_lose_their_caret_and_a_footnote_its_own_number():
    gold = parse_gold(OPENSTAX_PAGE)
    assert gold.prose[1].text == 'Rating Agencies 8'
    assert gold.footnotes[0].marker == '8' and gold.footnotes[0].text.startswith('Michael Schmidt.')


def test_the_partial_flags_arrive_per_block_and_per_page():
    gold = parse_gold(OPENSTAX_PAGE)
    assert gold.prose[0].starts_mid_block and not gold.prose[0].ends_mid_block
    assert gold.prose[-1].ends_mid_block
    assert gold.starts_mid_block and gold.ends_mid_block
    assert gold.tables[0].rows_kept == (0, 1) and gold.tables[0].rows_total == 12


def test_a_page_without_prose_has_no_partial_edges():
    gold = parse_gold(PAPER_PAGE)
    assert not gold.starts_mid_block and not gold.ends_mid_block and not gold.has_prose


def test_a_table_cell_keeps_its_text_spans_and_math():
    table = parse_gold(OPENSTAX_PAGE).tables[0]
    head = table.rows[0][0]
    assert (head.text, head.header, head.colspan) == ('Year', True, 2)
    assert table.rows[1][0].text == '$22.50' and not table.rows[1][0].header
    assert [formula.kind for formula in table.rows[1][1].formulas] == ['cell']


def test_cell_math_stays_with_its_table_but_counts_among_all_formulas():
    gold = parse_gold(OPENSTAX_PAGE)
    assert len(gold.inline) == 2 and len(gold.cell_formulas) == 1
    assert len(gold.all_formulas()) == 4


def test_the_grid_expands_spans_and_a_covered_position_is_no_cell():
    cell = GoldCell(segments=(('text', 'x'),))
    wide = GoldCell(segments=(('text', 'wide'),), colspan=2)
    tall = GoldCell(segments=(('text', 'tall'),), rowspan=2)
    grid = GoldTable(((wide, tall), (cell, cell))).grid()
    assert [[None if value is None else value.text for value in row] for row in grid] == [['wide', None, 'tall'], ['x', 'x', None]]


def test_an_empty_table_has_an_empty_grid():
    assert GoldTable(()).grid() == []


def test_a_rasters_gold_is_the_distinct_numbers_of_its_alt_text():
    assert parse_gold(OPENSTAX_PAGE).rasters[0].values == sorted(['100', '65', '4,000', '3', '2019'])


def test_a_figure_gives_its_caption_to_the_prose_and_its_alt_to_the_rasters():
    page = dict(OPENSTAX_PAGE, blocks=[{'kind': 'figure', 'partial': None, 'alt': 'A line rises to 42.', 'text_md': 'Figure 2.1 Growth', 'math': []}])
    gold = parse_gold(page)
    assert [block.kind for block in gold.prose] == ['caption'] and gold.rasters[0].values == ['42']


def test_a_kind_this_shape_does_not_carry_is_counted_not_lost():
    page = dict(OPENSTAX_PAGE, blocks=[{'kind': 'code', 'partial': None, 'text_md': 'x = 1', 'math': []}])
    assert parse_gold(page).unmapped == {'code': 1}


@pytest.mark.parametrize('page, footer', [(204, publisher_gold.OPENSTAX_FOOTER), (205, '')])
def test_the_openstax_footer_stands_on_even_pages(page, footer):
    assert parse_gold(dict(OPENSTAX_PAGE, pdf_page=page, blocks=[])).footer == footer


def test_a_paper_page_holds_formulas_only():
    gold = parse_gold(PAPER_PAGE)
    assert gold.prose == [] and gold.tables == [] and gold.footnotes == []
    assert [(formula.label, formula.kind, formula.placed_by) for formula in gold.display + gold.inline] == [('4', 'display', 'printed label'), (None, 'inline', 'before')]
    assert gold.header.startswith('Carta and Conversano') and 'Frontiers' in gold.footer


def test_a_paper_formula_says_whether_its_latex_is_the_authors():
    gold = parse_gold(PAPER_PAGE)
    assert gold.display[0].latex_origin == 'preview' and gold.inline[0].latex_origin == 'author'


def test_a_paper_formula_without_mathml_is_counted_not_lost():
    assert parse_gold(PAPER_PAGE).unmapped == {'formula_without_mathml': 1}


def test_a_source_symbol_the_font_prints_otherwise_is_accepted_both_ways():
    page = dict(PAPER_PAGE, formulas=[dict(PAPER_PAGE['formulas'][0], latex=r'\mathbb{1}(x)')])
    assert parse_gold(page).display[0].accepts == (('⊮', '1'), ('I', '1'))
    assert parse_gold(PAPER_PAGE).display[0].accepts == ()


def test_the_files_are_found_and_summaries_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(publisher_gold, 'GOLD_ROOT', tmp_path)
    (tmp_path / 'truth').mkdir()
    (tmp_path / 'truth_papers').mkdir()
    (tmp_path / 'truth' / 'fin_p0204.json').write_text(json.dumps(OPENSTAX_PAGE), encoding='utf-8')
    (tmp_path / 'truth' / '_summary.json').write_text('[]', encoding='utf-8')
    (tmp_path / 'truth_papers' / 'kelly_p0005.json').write_text(json.dumps(PAPER_PAGE), encoding='utf-8')
    assert [gold.pdf_page for gold in publisher_gold.all_gold()] == [204, 5]
    assert publisher_gold.load_gold('openstax_principles_of_finance_2e.pdf', 204).printed_label == '190'
    assert publisher_gold.load_gold('corpus/raw/carta_conversano_kelly_criterion_2020.pdf', 5).has_prose is False
    assert publisher_gold.load_gold('openstax_principles_of_finance_2e.pdf', 999) is None


def test_a_clone_without_the_local_folder_has_no_gold(tmp_path, monkeypatch):
    monkeypatch.setattr(publisher_gold, 'GOLD_ROOT', tmp_path / 'nowhere')
    assert publisher_gold.all_gold() == []
    assert publisher_gold.load_gold('openstax_principles_of_finance_2e.pdf', 204) is None


# ---------------------------------------------------------------- the real files, where they exist

@needs_gold
def test_the_real_gold_has_every_page_of_the_candidate_list():
    listed = json.loads((publisher_gold.GOLD_ROOT / 'candidates_public_exact.json').read_text(encoding='utf-8'))['candidates']
    pages = {(gold.pdf_file, gold.pdf_page): gold for gold in publisher_gold.all_gold()}
    assert len(pages) == 14 and set(pages) == {(row['file'], row['pdf_page']) for row in listed}
    assert all(pages[(row['file'], row['pdf_page'])].printed_label == row['printed_page'] for row in listed)


@needs_gold
def test_the_real_gold_maps_every_block_it_holds():
    assert {gold.gold_id: gold.unmapped for gold in publisher_gold.all_gold() if gold.unmapped} == {}


@needs_gold
def test_the_real_gold_keeps_the_counts_its_builder_reported():
    summary = {row['id']: row for row in json.loads((publisher_gold.GOLD_ROOT / 'truth' / '_summary.json').read_text(encoding='utf-8'))}
    for gold in publisher_gold.all_gold():
        if gold.gold_id in summary:
            row = summary[gold.gold_id]
            assert len(gold.display) == row['n_display_math'], gold.gold_id
            assert len(gold.inline) + len(gold.cell_formulas) == row['n_inline_math'], gold.gold_id
            assert sum(len(table.cells) for table in gold.tables) == row['n_table_cells'], gold.gold_id
            assert len(gold.prose) == sum(row['kinds'].get(kind, 0) for kind in publisher_gold.PROSE_KINDS), gold.gold_id
            assert len(gold.footnotes) == row['kinds'].get('footnote', 0), gold.gold_id


@needs_gold
def test_the_real_gold_counts_the_paper_formulas_its_builder_reported():
    summary = {(row['pdf_page'], row['display']): row for row in json.loads((publisher_gold.GOLD_ROOT / 'truth_papers' / '_papers_summary.json').read_text(encoding='utf-8'))}
    papers = [gold for gold in publisher_gold.all_gold() if not gold.has_prose]
    assert len(papers) == 4
    for gold in papers:
        assert summary[(gold.pdf_page, len(gold.display))]['inline'] == len(gold.inline)
