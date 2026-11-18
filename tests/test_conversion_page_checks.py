from pathlib import Path

import pymupdf
import pytest

from backend.configuration import data_paths
from backend.conversion.checks import page_checks
from backend.conversion.contract.page_contract import Expected, parse

ROOT = Path(__file__).resolve().parents[1]
P179 = (ROOT / 'tests' / 'fixtures' / 'page_contract' / 'openstax-finance-2e_p0179.page.md').read_text(encoding='utf-8')
EXPECTED = Expected('openstax-finance-2e', 179, (1688, 2184))
FRONT = '---\ncontract: page/1\nwork: w\npdf_page: 1\nimage_size: "612x792"\nprinted_label: none\npage_kind: body\n---\n\n'

# The planted errors of section 3.5 of the design: stage 2 catches these eight.
CAUGHT = {
    'a digit dropped': ('make up $100,000', 'make up $10,000', 'number_missing'),
    'a sentence omitted': (' They may also need to be more aggressive with collecting any outstanding accounts.', '', 'words_missing'),
    'a word rewritten toward the expected one': ('stricter credit', 'stronger credit', 'words_added'),
    'digits transposed': ('approximately 6.32', 'approximately 6.23', 'number_added'),
    'a block omitted': ('::: {#b16 .heading in=b08 bbox="211 1260 338 1299"}\nSolution:\n:::\n\n', '', 'words_missing'),
    'a label misread': ('label="6.3"', 'label="6.5"', 'formula_label'),
    'inline math invented': ('historical ratios.', 'historical ratios \\(r_t\\).', 'invented_math'),
    'two words swapped': ('key competitors', 'competitors key', 'word_order'),
}
# And these two it cannot catch: the classes without a text layer, the measured reason for stage 3.
MISSED = {
    'a value inside the drawn formula': ('\\$30{,}000', '\\$50{,}000', 'b05'),
    'a cell in the raster table': ('<td>$550,000</td>', '<td>$560,000</td>', 'b11'),
}


@pytest.fixture(scope='module')
def finance_page():
    if not (data_paths.FREE_RAW / 'openstax_principles_of_finance_2e.pdf').exists():
        pytest.skip('_data/corpus/raw/ is empty - run python -m backend.ingestion.acquire first')
    document = pymupdf.open(data_paths.FREE_RAW / 'openstax_principles_of_finance_2e.pdf')
    yield document[178]
    document.close()


def check_finance(text, page):
    parsed = parse(text, 'markdown', EXPECTED)
    assert parsed.valid, parsed.errors
    return page_checks.check_page(parsed, page)


def suspects(check) -> set[str]:
    return {finding.kind for finding in check.findings if finding.severity == 'suspect'}


@pytest.mark.corpus
def test_the_clean_page_has_no_suspect_finding(finance_page):
    check = check_finance(P179, finance_page)
    assert check.has_layer and not check.suspicious and check.recall == 1.0 and check.precision == 1.0


@pytest.mark.corpus
@pytest.mark.parametrize('name', sorted(CAUGHT))
def test_a_planted_error_is_caught(finance_page, name):
    old, new, kind = CAUGHT[name]
    assert old in P179
    check = check_finance(P179.replace(old, new, 1), finance_page)
    assert check.suspicious and kind in suspects(check)


@pytest.mark.corpus
@pytest.mark.parametrize('name', sorted(MISSED))
def test_what_the_layer_lacks_goes_to_the_judge_instead(finance_page, name):
    old, new, block = MISSED[name]
    assert old in P179
    check = check_finance(P179.replace(old, new, 1), finance_page)
    assert not check.suspicious
    assert block in {item.block for item in check.unverifiable}


@pytest.mark.corpus
def test_a_stored_record_holds_no_page_words_unless_asked(finance_page):
    old, new, _ = CAUGHT['a word rewritten toward the expected one']
    check = check_finance(P179.replace(old, new, 1), finance_page)
    assert 'stronger' not in str(check.as_dict())
    assert 'stronger' in str(check.as_dict(words=True))


@pytest.mark.corpus
def test_a_stage_1_failure_cannot_reach_stage_2(finance_page):
    with pytest.raises(ValueError):
        page_checks.check_page(parse('nothing', 'markdown'), finance_page)


# ---------------------------------------------------------------- on small pages built here

def built_page(lines, font='helv', x=72):
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    y = 100
    for text in lines:
        indent = len(text) - len(text.lstrip(' '))
        page.insert_text((x + indent * 0.6 * 10, y), text.lstrip(' '), fontname=font, fontsize=10)
        y += 14
    return page


def block(body, cls='paragraph', attrs='bbox="60 80 560 400"', ident='b01'):
    return f'::: {{#{ident} .{cls} {attrs}}}\n{body}\n:::\n\n'


def check_built(page, *blocks):
    parsed = parse(FRONT + ''.join(blocks), 'markdown')
    assert parsed.valid, parsed.errors
    return page_checks.check_page(parsed, page)


def test_a_word_split_at_a_line_end_may_be_written_joined_or_with_its_real_hyphen():
    page = built_page(['We consider a stric-', 'ter credit policy for Coca-', 'Cola and its long term plan for all.'])
    assert not check_built(page, block('We consider a stricter credit policy for Coca-Cola and its long term plan for all.')).suspicious


def test_a_block_written_elsewhere_than_the_layer_has_it_is_no_error():
    page = built_page(['The first paragraph stands here with its own words.', 'A box with other words entirely, set apart.', 'The last paragraph follows after that box.'])
    check = check_built(page, block('A box with other words entirely, set apart.', attrs='bbox="60 90 560 120"'),
                        block('The first paragraph stands here with its own words.', attrs='bbox="60 90 560 110"', ident='b02'),
                        block('The last paragraph follows after that box.', attrs='bbox="60 120 560 140"', ident='b03'))
    assert not check.suspicious


def test_lacking_words_is_a_suspect_and_a_number_on_one_side_is_too():
    page = built_page(['The firm earned 1,250 in the first year and spent most of it on rent.'])
    assert 'words_missing' in suspects(check_built(page, block('The firm earned 1,250 in the first year and spent most of it.')))
    assert 'number_added' in suspects(check_built(page, block('The firm earned 1,260 in the first year and spent most of it on rent.')))


def test_more_words_than_the_layer_in_a_figure_is_only_a_note():
    page = built_page(['A short sentence stands on this page as its only printed text.'])
    check = check_built(page, block('A short sentence stands on this page as its only printed text.', attrs='bbox="60 90 560 110"'),
                        block('Revenue\nCost\nProfit\nMargin\nYear', cls='figure', attrs='kind=chart bbox="60 200 560 400"', ident='b02'))
    assert not check.suspicious


CODE = ['def total(values):', '    if a<b and c>d:', '        return sum(values)', '    return 0']


def test_code_between_angle_brackets_stays_and_right_indentation_passes():
    page = built_page(CODE, font='cour')
    check = check_built(page, block('\n'.join(CODE), cls='code', attrs='lang=python bbox="60 80 560 400"'))
    assert not check.suspicious, check.findings


def test_lost_indentation_is_a_suspect():
    page = built_page(CODE, font='cour')
    flat = '\n'.join(line.lstrip() for line in CODE)
    assert 'code_indent' in suspects(check_built(page, block(flat, cls='code', attrs='bbox="60 80 560 400"')))


def test_python_that_does_not_parse_is_a_suspect_unless_it_is_a_fragment():
    lines = ['def total(values:', '    return 0']
    page = built_page(lines, font='cour')
    body = '\n'.join(lines)
    assert suspects(check_built(page, block(body, cls='code', attrs='lang=python bbox="60 80 560 400"')))
    assert not check_built(page, block(body, cls='code', attrs='lang=python cont=next bbox="60 80 560 400"')).suspicious


def test_a_printed_label_the_layer_lacks_is_a_suspect():
    page = built_page(['A sentence with enough words to count as a text layer here.'])
    front = FRONT.replace('printed_label: none', 'printed_label: "99"')
    parsed = parse(front + block('A sentence with enough words to count as a text layer here.'), 'markdown')
    assert 'printed_label' in suspects(page_checks.check_page(parsed, page))


# What the first mini pilot raised as false alarms on right readings, 2026-10-30.
def test_a_symbol_the_layer_glues_to_a_word_is_no_error():
    page = built_page(['The y-intercept and the slope of the line, where g*is the rate, are both given here.'])
    check = check_built(page, block(r'The \(y\)-intercept and the slope of the line, where \(g*\) is the rate, are both given here.'))
    assert not check.suspicious, check.findings


def test_a_lone_extra_word_is_a_note_but_a_replaced_word_and_an_invented_sentence_are_suspects():
    line = 'A short sentence stands on this page as its only printed text.'
    page = built_page([line])
    assert not check_built(page, block('LO ' + line)).suspicious
    assert 'words_added' in suspects(check_built(page, block(line.replace('short', 'small'))))
    assert 'words_added' in suspects(check_built(page, block(line + ' The result is the same either way.')))


def test_a_ragged_table_is_a_suspect():
    page = built_page(['Name 10', 'Other 20 30'])
    table = '<table><tr><td>Name</td><td>10</td></tr><tr><td>Other</td><td>20</td><td>30</td></tr></table>'
    assert 'table_ragged' in suspects(check_built(page, block(table, cls='table')))


def test_a_page_without_a_layer_has_no_text_findings_and_everything_goes_to_the_judge():
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    body = ' '.join(['Words that only the reader saw on a scanned page'] * 4)
    check = check_built(page, block(body))
    assert not check.has_layer and not check.suspicious
    assert {item.why for item in check.unverifiable} == {'no_layer'}


def test_a_blank_reading_of_a_blank_page_passes():
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    parsed = parse(FRONT.replace('page_kind: body', 'page_kind: blank'), 'markdown')
    assert parsed.valid
    assert not page_checks.check_page(parsed, page).suspicious


def test_broken_latex_is_a_suspect_when_katex_has_rendered():
    page = built_page(['A sentence with enough words to count as a text layer here.'])
    good = FRONT + block('A sentence with enough words to count as a text layer here.', attrs='bbox="60 90 560 110"')
    parsed = parse(good + block(r'\frac{a}{b', cls='formula', attrs='bbox="60 200 560 260"', ident='b02'), 'markdown')
    assert parsed.valid
    assert 'katex' in suspects(page_checks.check_page(parsed, page, page_checks.render_formulas([parsed])))
