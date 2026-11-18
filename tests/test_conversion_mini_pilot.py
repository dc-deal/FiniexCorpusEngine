import argparse
import json
import shutil
from pathlib import Path

import pytest
from PIL import Image

from backend.conversion.judge import formula_sheet
from backend.conversion.measurement import mini_pilot
from backend.conversion.store import reading_store
from backend.conversion.measurement.mini_pilot import judge_measures

ROOT = Path(__file__).resolve().parents[1]
P179 = (ROOT / 'tests' / 'fixtures' / 'page_contract' / 'openstax-finance-2e_p0179.page.md').read_text(encoding='utf-8')
PDF = 'openstax_principles_of_finance_2e.pdf'


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setitem(reading_store.ROOTS, 'free', tmp_path)
    monkeypatch.setattr(formula_sheet, 'sheets', lambda parsed: [])
    return reading_store.open_store('free')


def stored_reading(store, cell='MP-SM', text=P179, result_class='ok', key='a' * 64):
    png = Path(store.root) / 'blank.png'
    Image.new('L', (1688, 2184), 255).save(png)
    image_sha = store.put_input(png.read_bytes(), '.png')
    record = {'reading_key': key, 'cell': cell, 'kind': 'reading', 'form': 'markdown', 'file': PDF, 'pdf_page': 179, 'work': 'openstax-finance-2e',
              'image_size': [1688, 2184], 'image_sha256': image_sha, 'mirror': 'free', 'page_id': 'openstax-finance-2e:p0179', 'attempt': 0,
              'result_class': result_class, 'cost_usd': 0.01, 'usage': {'input_tokens': 100, 'output_tokens': 50}}
    store.save_reading(key, record, text)
    return record


@pytest.mark.corpus
def test_score_reads_a_stored_reading_and_writes_its_report_first(store, capsys):
    stored_reading(store)
    report = mini_pilot.score(argparse.Namespace())
    cell = report['cells']['MP-SM']
    assert cell['readings'] == 1 and cell['valid_first'] == 1 and cell['checked'] == 1 and cell['suspicious'] == 0
    assert cell['iou']['paragraph']['n'] > 0 and cell['usd_per_page'] == 0.01
    assert store.path('reports', 'mini_pilot_score.json').exists()
    assert 'valid on the first attempt' in capsys.readouterr().out


def test_a_malformed_reading_counts_against_its_cell(store):
    stored_reading(store, text=P179.replace('of=b11', 'of=b99'), result_class='malformed')
    cell = mini_pilot.score(argparse.Namespace())['cells']['MP-SM']
    assert cell['valid_first'] == 0 and cell['checked'] == 0 and cell['classes'] == {'malformed': 1}


@pytest.mark.corpus
def test_plant_counts_a_new_finding_as_a_catch_and_the_table_is_stored(store):
    stored_reading(store)
    report = mini_pilot.plant(argparse.Namespace(cell='MP-SM'))
    assert report['kinds']['prose_digit_change']['caught'] == report['kinds']['prose_digit_change']['applicable'] == 1
    assert report['kinds']['formula_digit_change']['caught'] == 0  # drawn formula: the judge's job
    assert store.path('reports', 'mini_pilot_plant.json').exists()


def fake_entry(key, planted=None, block=None):
    return {'reading_key': key, 'planted': planted, 'planted_block': block, 'target_key': 't'}


def judged(verdict, findings=(), cost=0.01):
    outcome = 'ok' if verdict == 'ok' and not [f for f in findings if f.get('severity') == 'major'] else 'issue'
    return {'cost_usd': cost, 'verdict': {'verdict': verdict, 'findings': list(findings), 'outcome': outcome}}


def test_judge_measures_separate_detection_false_alarms_and_failures():
    plan = {'model': 'm', 'entries': [fake_entry('c1'), fake_entry('c2'), fake_entry('c3'), fake_entry('p1', 'formula_digit_change', 'b05'),
                                      fake_entry('p2', 'formula_label_change', 'b06'), fake_entry('p3', 'table_cell_change', 'b11'),
                                      fake_entry('blocked', 'word_swap', 'b01'), fake_entry('missing', 'word_swap', 'b01')]}
    records = {'c1': judged('ok'), 'c2': judged('bad', [{'block': 'b01', 'severity': 'major'}]), 'c3': judged('unsure'),
               'p1': judged('bad', [{'block': 'b05', 'severity': 'major'}]), 'p2': judged('bad', [{'block': 'b09', 'severity': 'major'}]),
               'p3': judged('ok'), 'blocked': {'cost_usd': 0.0, 'result_class': 'errored'}}
    result = judge_measures(plan, records)
    assert result['clean'] == {'n': 3, 'issue': 2, 'unsure': 1, 'major': 1}
    assert result['groups']['formula'] == {'n': 2, 'to_issue': 2, 'on_block': 1}
    assert result['groups']['table'] == {'n': 1, 'to_issue': 0, 'on_block': 0}
    assert result['failed'] == {'errored': 1, 'not collected': 1} and result['answered'] == 6


@pytest.mark.corpus
def test_a_plan_holds_clean_and_planted_requests_and_a_submit_skips_what_is_judged(store, monkeypatch, capsys):
    stored_reading(store)
    monkeypatch.setattr(mini_pilot, '_gold_clean', lambda row: True)
    plan = mini_pilot.judge_plan(argparse.Namespace(cell='MP-SM', model='claude-haiku-5-5', clean=1, planted=1, seed=0))
    assert sum(1 for entry in plan['entries'] if entry['planted'] is None) == 1
    assert sum(1 for entry in plan['entries'] if entry['planted']) >= 8
    assert len({entry['reading_key'] for entry in plan['entries']}) == len(plan['entries'])
    sent = {}
    monkeypatch.setattr(mini_pilot.anthropic_client, 'client', lambda: None)
    monkeypatch.setattr(mini_pilot.vision_batches, 'send_entries', lambda client, entries, skipped, cap, dry_run=False: sent.update(entries=entries, skipped=skipped))
    store.save_reading(plan['entries'][0]['reading_key'], {'kind': 'judge'}, '{}')
    mini_pilot.judge_submit(argparse.Namespace(model='claude-haiku-5-5', cap=5, dry_run=True))
    assert len(sent['entries']) == len(plan['entries']) - 1 and sent['skipped']['already judged'] == 1


@pytest.mark.corpus
def test_the_summary_has_every_part_that_was_measured(store):
    stored_reading(store)
    mini_pilot.score(argparse.Namespace())
    mini_pilot.plant(argparse.Namespace(cell='MP-SM'))
    store.write_report('judge_score_m.json', judge_measures({'model': 'm', 'entries': [fake_entry('c1')]}, {'c1': judged('ok')}))
    mini_pilot.report(argparse.Namespace())
    text = store.path('reports', mini_pilot.SUMMARY).read_text(encoding='utf-8')
    assert '## Readings' in text and '## Planted errors' in text and '## Judge m' in text and 'n/a' in text
    json.dumps(text)
    shutil.rmtree(store.root, ignore_errors=True)
