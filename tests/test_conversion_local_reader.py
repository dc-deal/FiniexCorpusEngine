"""Test readings by local models (#17): the answers of a night on the bench machine, turned into page/1 and imported into the
store under the test cells, which nothing buys, chooses or serves."""

import hashlib
import json

from backend.conversion.reading import local_reader, reader_requests, reading_cells, vision_batches
from backend.conversion.store import reading_export, reading_store


def test_qwen_s_boxes_on_its_own_scale_are_rescaled_and_a_box_in_pixels_is_kept():
    text = '::: {#b01 .paragraph bbox="100 50 900 100"}\nA.\n:::\n\n::: {#b02 .page_footer bbox="80 2120 400 2140"}\nB\n:::'
    rescaled, counts = local_reader.rescale_boxes(text, 2000, 3000)
    assert 'bbox="200 150 1800 300"' in rescaled
    assert 'bbox="80 2120 400 2140"' in rescaled  # a value above 1000 says the box was written in pixels
    assert counts == {'boxes_rescaled': 1, 'boxes_kept': 1}


PAGE = {'work': 'openstax-finance-2e', 'pdf_page': 204, 'width': 1688, 'height': 2184}


def test_a_document_model_s_markdown_becomes_page1_blocks_with_its_money_left_as_text():
    raw = ('# 7.2 Basics\n\nThe deposit of $1,000 earns $40\nin a year.\n\n$$\n1,000 \\times 0.04 = 40\n$$\n\n'
           '\\[\nFV = PV (1 + r)\n\\]\n\n| Year | 1 |\n|---|---|\n| Coupon | $22.50 |\n\n'
           '<table><tr><td>a</td></tr></table>\n\n![](images/chart.png)')
    text, notes = local_reader.markdown_page(raw, PAGE)
    assert text.startswith('---\ncontract: page/1\nwork: openstax-finance-2e\npdf_page: 204\nimage_size: "1688x2184"\n')
    assert '::: {#b01 .heading bbox="0 0 1688 2184"}\n7.2 Basics\n:::' in text
    assert 'The deposit of $1,000 earns $40 in a year.' in text  # lines joined, the dollars untouched
    assert '.formula bbox="0 0 1688 2184"}\n1,000 \\times 0.04 = 40\n:::' in text
    assert 'FV = PV (1 + r)' in text
    assert '<thead><tr><th>Year</th><th>1</th></tr></thead>' in text and '<td>$22.50</td>' in text
    assert '<table><tr><td>a</td></tr></table>' in text
    assert notes['blocks'] == {'heading': 1, 'paragraph': 1, 'formula': 2, 'table': 2}
    assert notes['images_dropped'] == 1 and notes['converter'] == local_reader.CONVERTER


def test_a_display_formula_across_a_blank_line_stays_one_block():
    assert local_reader._chunks('$$\na = b\n\nc = d\n$$\n\nAfter.') == ['$$\na = b\n\nc = d\n$$', 'After.']


def test_a_body_with_a_colon_run_at_a_line_start_gets_a_longer_fence():
    text, _ = local_reader.markdown_page('$$\na\n:::\nb\n$$', PAGE)  # a formula keeps its lines, a paragraph joins them
    assert ':::: {#b01 .formula' in text and text.endswith('a\n:::\nb\n::::\n')


def test_a_converted_page_passes_the_format_check():
    text, _ = local_reader.markdown_page('A plain paragraph.\n\n$$\nx = y\n$$', PAGE)
    entry = {'form': 'markdown', 'work': PAGE['work'], 'pdf_page': PAGE['pdf_page'], 'image_size': [1688, 2184]}
    assert vision_batches.check_reading(entry, text, 'end_turn')[0] == 'ok'


def _run(tmp_path, answer: str, finish: str = 'stop'):
    """A run folder of one page and one document model, as the night's scripts wrote it."""
    run = tmp_path / 'night'
    gold, results = run / 'gold', run / 'results' / 'glm-ocr'
    gold.mkdir(parents=True)
    results.mkdir(parents=True)
    png = b'not a real png'
    page_id = 'openstax-finance-2e_p0204'
    (gold / f'{page_id}.png').write_bytes(png)
    (gold / 'system_page1_markdown.txt').write_bytes(reader_requests.system_prompt('markdown').encode('utf-8'))
    (gold / 'manifest.json').write_text(json.dumps({'pages': [{
        'id': page_id, 'work': 'openstax-finance-2e', 'file': 'openstax_principles_of_finance_2e.pdf', 'pdf_page': 204,
        'width': 1688, 'height': 2184, 'image_sha256': hashlib.sha256(png).hexdigest()}]}), encoding='utf-8')
    (results / f'{page_id}.md').write_text(answer, encoding='utf-8')
    (results / 'results.jsonl').write_text(
        json.dumps({'event': 'load', 'seconds': 3.5}) + '\n'
        + json.dumps({'id': page_id, 'seconds': 9.1, 'chars': len(answer), 'finish': finish, 'torch_peak_mib': 2900.0,
                      'input_tokens': 900, 'output_tokens': 700}) + '\n', encoding='utf-8')
    return run


def test_an_import_stores_a_test_reading_once_with_its_trace(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    run = _run(tmp_path, 'A plain paragraph.')
    assert local_reader.import_run(run, store) == {'LAB-GLMOCR-MP ok': 1}
    assert local_reader.import_run(run, store) == {'already stored': 1}  # the key covers everything: nothing twice
    record = store.readings()[0]
    assert record['cell'] == 'LAB-GLMOCR-MP' and record['mode'] == 'local' and record['cost_usd'] == 0.0
    assert record['deviation'] == local_reader.DEVIATION and record['seconds'] == 9.1
    assert record['usage'] == {'input_tokens': 900, 'output_tokens': 700}
    assert store.get_input(record['answer_sha256'], '.md') == b'A plain paragraph.'  # the model's own answer is kept
    assert store.get_prompt(record['user_sha256']) == 'Text Recognition:' and record['system_sha256'] is None
    assert record['conversion']['boxes'] == 'the whole page: the model gives none'
    assert vision_batches.readings_of(['LAB-GLMOCR-MP'], store) == [record]  # found by its label
    assert vision_batches.readings_of(['MP-SM'], store) == []  # no pipeline cell asks its question


def test_an_answer_cut_at_its_token_limit_is_stored_as_truncated(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    assert local_reader.import_run(_run(tmp_path, 'A plain paragraph.', finish='length'), store) \
        == {'LAB-GLMOCR-MP truncated': 1}


def test_test_cells_are_never_bought_and_stand_in_the_lab():
    assert not set(reading_cells.TEST_READING_CELLS) & set(reading_cells.submittable())
    assert set(reading_cells.TEST_READING_CELLS) <= set(reading_cells.known_cells())
    assert all(len(reading_cells.pages_for(cell)) == 20 for cell in reading_cells.TEST_READING_CELLS.values())
    assert all(cell.mode == reading_cells.LOCAL for cell in reading_cells.TEST_READING_CELLS.values())
    free = reading_export.BASES['free']
    assert set(reading_cells.TEST_READING_CELLS) <= set(reading_export.prototypes_beside(free))
    assert not set(reading_cells.TEST_READING_CELLS) & set(free.cells() + reading_export.cells_beside(free))
    assert reading_export.purpose_of({'cell': 'LAB-GLMOCR-MP'}) == 'a test reading by glm-ocr (local), never served'


def test_the_judge_plan_takes_every_test_reading_with_blocks_and_only_test_cells(tmp_path, monkeypatch):
    import pytest

    from backend.conversion.judge import page_judge

    store = reading_store.Store(tmp_path / 'vision')
    run = _run(tmp_path, 'A ratio \\frac{a}{b} outside math.')  # malformed, as PaddleOCR-VL's were; judged on what it says
    assert local_reader.import_run(run, store) == {'LAB-GLMOCR-MP malformed': 1}
    monkeypatch.setattr(page_judge, 'entry_for', lambda record, parsed, model: {'target_key': record['reading_key'],
                                                                               'blocks': len(parsed.blocks), 'estimate_usd': 0.01})
    plan = local_reader.judge_plan('LAB-GLMOCR-MP', store)
    assert [entry['blocks'] for entry in plan['entries']] == [1] and plan['lab'] is True
    assert store.path('reports', 'check_plan_LAB-GLMOCR-MP.json').exists()
    assert not store.path('reports', 'judge_sample.json').exists()  # the pipeline's kept sample is left alone
    with pytest.raises(ValueError):
        local_reader.judge_plan('FREE-SM', store)


def test_the_export_marks_a_test_reading_as_a_prototype_and_a_test_reading(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    local_reader.import_run(_run(tmp_path, 'A plain paragraph.'), store)
    (listed,) = reading_export.attempts_of(store, ('LAB-GLMOCR-MP',)).values()
    assert listed[0]['prototype'] is True and listed[0]['test_reading'] is True
    assert listed[0]['reader_version'] == 'glm-ocr/text' and listed[0]['mode'] == 'local'
