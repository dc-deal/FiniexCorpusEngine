"""A document pipeline's blocks into page/1 (decision 51, 28 Nov): real boxes, an equation number bound to the formula whose
row it shares, the page's number as the printed label, a table from its raw answer, never the pipeline's rewritten HTML."""

from backend.conversion.contract.page_contract import Expected, parse
from backend.conversion.reading import local_reader

PAGE = {'work': 'w', 'pdf_page': 3, 'width': 1000, 'height': 1400}


def block(label, box, raw, **more):
    return {'label': label, 'box': box, 'raw': raw, **more}


RESULT = {'blocks': [
    block('number', [60, 30, 90, 50], '12'),
    block('header', [100, 30, 600, 50], 'Chapter 2 • Interest'),
    block('paragraph_title', [100, 100, 600, 130], '## Simple Interest'),
    block('text', [100, 150, 900, 220], 'A deposit of $1,000 earns \\(r = 4\\%\\)\na year.'),
    block('display_formula', [300, 240, 700, 280], '\\[FV = PV \\times (1 + r)\\]'),
    block('formula_number', [880, 245, 920, 275], '(2.1)'),
    block('display_formula', [300, 300, 700, 340], '\\[PV = FV / (1 + r) \\tag{2.2}\\]'),
    block('table', [100, 400, 900, 600], '<fcel>a<fcel>b<nl>', html_from_raw='<table><tr><td>a</td><td>b</td></tr></table>',
          content='<table><tr><td>rewritten</td></tr></table>'),
    block('table_title', [100, 610, 600, 630], 'Table 2.1 Rates'),
    block('seal', [100, 700, 200, 800], ''),
    block('mystery', [100, 900, 600, 930], 'something'),
]}


def test_the_blocks_become_a_valid_page_with_real_boxes():
    text, notes = local_reader.blocks_page(RESULT, PAGE)
    page = parse(text, 'markdown', Expected('w', 3, (1000, 1400)))
    assert page.valid, page.errors
    assert page.front['printed_label'] == '12' and page.front['label_position'] == 'header'
    assert page.block('b04').bbox == (100, 150, 900, 220)
    assert notes['converter'] == local_reader.BLOCKS_CONVERTER and notes['numbers_bound'] == 1


def test_an_equation_number_and_a_tag_become_the_formula_label():
    text, _ = local_reader.blocks_page(RESULT, PAGE)
    page = parse(text, 'markdown', Expected('w', 3, (1000, 1400)))
    formulas = [one for one in page.blocks if one.cls == 'formula']
    assert [one.attrs.get('label') for one in formulas] == ['2.1', '2.2']
    assert all('\\tag' not in one.body for one in formulas)
    assert not any(one.body == '(2.1)' for one in page.blocks)  # the bound number is written once, as the label


def test_a_table_comes_from_its_raw_answer_and_its_caption_names_it():
    text, _ = local_reader.blocks_page(RESULT, PAGE)
    page = parse(text, 'markdown', Expected('w', 3, (1000, 1400)))
    table = next(one for one in page.blocks if one.cls == 'table')
    assert 'rewritten' not in table.body and 'a' in table.body
    caption = next(one for one in page.blocks if one.cls == 'caption')
    assert caption.attrs['of'] == table.id


def test_prose_keeps_its_money_sign_and_an_unknown_label_is_kept_as_other():
    text, _ = local_reader.blocks_page(RESULT, PAGE)
    page = parse(text, 'markdown', Expected('w', 3, (1000, 1400)))
    assert '$1,000' in page.block('b04').body
    other = next(one for one in page.blocks if one.cls == 'other')
    assert other.attrs['why'] == 'layout label mystery'
    assert next(one for one in page.blocks if one.cls == 'figure').attrs['kind'] == 'other'
