import io
import json
from pathlib import Path

import pytest
from PIL import Image

from backend.conversion.judge import formula_sheet, page_judge
from backend.conversion.reading import vision_batches
from backend.conversion.store import reading_store
from backend.conversion.contract.page_contract import parse
from backend.conversion.judge.page_judge import Verdict, check_answer, judge_view, parse_verdict

P179 = parse((Path(__file__).resolve().parent / 'fixtures' / 'page_contract' / 'openstax-finance-2e_p0179.page.md').read_text(encoding='utf-8'), 'markdown')
P405 = parse((Path(__file__).resolve().parent / 'fixtures' / 'page_contract' / 'openstax-finance-2e_p0405.page.md').read_text(encoding='utf-8'), 'markdown')
PNG = io.BytesIO()
Image.new('L', (100, 140), 255).save(PNG, format='PNG')
PNG = PNG.getvalue()


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setitem(reading_store.ROOTS, 'free', tmp_path)
    monkeypatch.setattr(formula_sheet, 'sheets', lambda parsed: [PNG])
    return reading_store.open_store('free')


def record_on(store) -> dict:
    return {'reading_key': 'a' * 64, 'page_id': 'w:p0179', 'file': 'f.pdf', 'pdf_page': 179, 'work': 'w', 'mirror': 'free',
            'image_sha256': store.put_input(PNG, '.png'), 'image_size': [100, 140]}


def test_the_view_shows_bodies_and_labels_but_no_boxes_and_marks_what_is_derived():
    view = judge_view(P179)
    assert 'bbox' not in view and '1165 66' not in view
    assert '[b05 formula label=6.3]' in view and '[b09 heading in=b08]' in view and r'\frac{\$20{,}000' in view
    assert '[b23 description of=b21 form=prose DERIVED]' in judge_view(P405)


def test_the_view_shows_the_printed_words_an_attribute_carries():
    # decision 190.a: the judge saw a glossary entry's definition without its term and called the term missing
    from test_conversion_served_readings import page as reading_page
    view = page_judge.judge_view(parse(reading_page(
        '::: {#b01 .glossary_entry term="accrual-basis accounting" bbox="10 10 900 60"}\nan accounting system\n:::'), 'markdown'))
    assert '[b01 glossary_entry term=accrual-basis accounting]' in view


def test_the_view_holds_nothing_of_stage_2():
    for word in ('suspect', 'recall', 'unverifiable', 'finding'):
        assert word not in judge_view(P179).replace('Findings', '')


def test_the_verdict_schema_has_what_structured_outputs_require():
    def objects(node):
        if isinstance(node, dict):
            if node.get('type') == 'object':
                yield node
            for value in node.values():
                yield from objects(value)
        elif isinstance(node, list):
            for value in node:
                yield from objects(value)

    assert all(node['additionalProperties'] is False and set(node['required']) == set(node['properties']) for node in objects(page_judge.VERDICT_SCHEMA))


@pytest.mark.parametrize('verdict, findings, outcome', [
    ('ok', [], 'ok'),
    ('ok', [{'severity': 'minor'}], 'ok'),
    ('ok', [{'severity': 'major'}], 'issue'),
    ('bad', [{'severity': 'major'}], 'issue'),
    ('unsure', [], 'issue'),
])
def test_only_a_clean_verdict_stays_out_of_the_bin(verdict, findings, outcome):
    assert Verdict(verdict, findings).outcome == outcome


def test_an_answer_that_is_no_verdict_is_malformed_not_a_crash():
    assert parse_verdict('not json') is None and parse_verdict('{"verdict": "great", "findings": []}') is None
    assert parse_verdict('[1]') is None
    assert check_answer({}, 'not json', 'end_turn') == ('malformed', None)
    assert check_answer({}, '', 'refusal') == ('refused', None)
    assert check_answer({}, '{"ver', 'max_tokens') == ('truncated', None)
    result_class, kept = check_answer({}, json.dumps({'verdict': 'bad', 'findings': [{'block': 'b05', 'kind': 'wrong_value', 'severity': 'major', 'evidence': '30,000 against 50,000'}]}), 'end_turn')
    assert result_class == 'ok' and kept['outcome'] == 'issue' and kept['findings'][0]['block'] == 'b05'


def test_the_request_carries_both_images_the_view_the_schema_and_the_effort():
    params = page_judge.message_params(model='claude-haiku-5-5', system_text='rules', page_png=PNG, sheet_pngs=[PNG], view='the view', pdf_page=7)
    images = [part for part in params['messages'][0]['content'] if part['type'] == 'image']
    assert len(images) == 2 and all(image['transformations'] == {'oversized_image': 'error'} for image in images)
    assert params['messages'][0]['content'][-1]['text'] == 'the view'
    assert params['output_config']['format']['schema'] == page_judge.VERDICT_SCHEMA and params['output_config']['effort'] == 'high'
    assert params['system'][0]['cache_control'] == {'type': 'ephemeral'}


def test_the_key_changes_with_what_was_asked_and_only_with_that():
    base = dict(target_key='t', model='claude-haiku-5-5', system_sha='s', image_sha='i', view_sha='v', sheet_shas=['x'], max_tokens=2000)
    key = page_judge.judge_key(**base)
    assert key == page_judge.judge_key(**base)
    for name, value in (('target_key', 'u'), ('model', 'claude-sonnet-5-5'), ('system_sha', 'z'), ('image_sha', 'z'), ('view_sha', 'z'), ('sheet_shas', []), ('max_tokens', 1)):
        assert key != page_judge.judge_key(**{**base, name: value})


def test_an_entry_goes_through_the_runner_and_a_planted_page_is_a_different_request(store):
    record = record_on(store)
    entry = page_judge.entry_for(record, P179, 'claude-haiku-5-5')
    planted = type('P', (), {'kind': 'prose_digit_change', 'block': 'b04'})
    other = page_judge.entry_for(record, P179, 'claude-haiku-5-5', planted)
    assert entry['reading_key'] != other['reading_key'] and other['planted'] == 'prose_digit_change' and other['planted_block'] == 'b04'
    assert entry['estimate_usd'] > 0 and entry['custom_id'].startswith('r')
    params = vision_batches.params_for(entry)
    assert params['model'] == 'claude-haiku-5-5' and judge_view(P179) == params['messages'][0]['content'][-1]['text']


def test_the_runner_keeps_the_verdict_in_the_record(store):
    entry = page_judge.entry_for(record_on(store), P179, 'claude-haiku-5-5')
    usage = type('Usage', (), {'to_dict': lambda self: {'input_tokens': 10, 'output_tokens': 20}})()
    text = json.dumps({'verdict': 'ok', 'findings': []})
    message = type('Message', (), {'id': 'm', 'model': 'claude-haiku-5-5', 'stop_reason': 'end_turn', 'usage': usage,
                                   'content': [type('Text', (), {'type': 'text', 'text': text})()]})()
    record, stored_text = vision_batches.record_for(entry, 'succeeded', message)
    vision_batches.store_result(entry, record, stored_text)
    stored = store.reading(entry['reading_key'])
    assert stored['kind'] == 'judge' and stored['verdict']['outcome'] == 'ok' and stored['target_key'] == 'a' * 64
    assert stored['cost_usd'] > 0 and store.spent_usd() == stored['cost_usd']


def test_formula_rows_cover_formulas_inline_math_and_table_cells():
    rows = formula_sheet.rows_for(P179)
    assert ('b05', P179.block('b05').body, True) in rows and ('b17', r'\text{ART} = 8.46', False) in rows
    table = parse(P179 and (Path(__file__).resolve().parent / 'fixtures' / 'page_contract' / 'openstax-finance-2e_p0179.page.md').read_text(encoding='utf-8').replace('<td>80,000</td>', r'<td>\(x_1\)</td>', 1), 'markdown')
    assert ('b11', 'x_1', False) in formula_sheet.rows_for(table)


def test_no_formula_or_no_browser_gives_no_sheet(monkeypatch):
    assert formula_sheet.sheets(parse('---\nwork: w\n---\n', 'markdown')) == []
    monkeypatch.setattr(formula_sheet, 'find_browser', lambda: None)
    assert formula_sheet.sheets(P179) == []


@pytest.mark.skipif(formula_sheet.find_browser() is None, reason='no browser on this machine')
def test_a_sheet_is_an_image_inside_the_api_limits_and_a_broken_formula_is_named():
    page = parse((Path(__file__).resolve().parent / 'fixtures' / 'page_contract' / 'openstax-finance-2e_p0179.page.md').read_text(encoding='utf-8').replace(r'\text{Accounts Receivable Turnover} =', r'\frac{a}{b', 1), 'markdown')
    sheets = formula_sheet.sheets(page)
    assert sheets
    for png in sheets:
        width, height = Image.open(io.BytesIO(png)).size
        assert width <= 2576 and height <= 2576 and height > 40
