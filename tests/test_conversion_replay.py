"""The replay: a page read again as a new attempt in a cell of its own, its check a report of its own (decisions 54.a, 69.a)."""

import json

import pytest

from backend.conversion.reading import reading_cells, replay, vision_batches
from backend.conversion.store import reading_export, reading_store

PAGE = {'file': 'w.pdf', 'pdf_page': 3, 'work': 'w', 'gold': False, 'class_note': '', 'expected_output_tokens': 1900,
        'work_card': 'A card.', 'id': 'w:p0003'}


@pytest.fixture
def free(tmp_path, monkeypatch):
    monkeypatch.setattr(reading_cells, 'REPLAY_PAGES', {'free': tmp_path / 'replay' / 'pages.json', 'licensed': tmp_path / 'x.json'})
    return reading_export.KnowledgeBase('free', tmp_path / 'readings', tmp_path, lambda: ('FREE-SM',), tracked=True)


def test_a_replayed_page_is_listed_once_in_its_own_cell_read_over_the_standard_api(free):
    cell = replay.list_replayed(free, PAGE)
    replay.list_replayed(free, PAGE)
    listed = json.loads(reading_cells.REPLAY_PAGES['free'].read_text(encoding='utf-8'))
    assert cell.name == 'REPLAY-FREE' and cell.mode == 'standard' and cell.model == 'claude-sonnet-5-5'
    assert [page['pdf_page'] for page in listed['pages']] == [3] and listed['work_cards'] == {'w': 'A card.'}


def test_a_replay_takes_an_attempt_no_reading_of_the_page_has_had(monkeypatch):
    records = [{'file': 'w.pdf', 'pdf_page': 3, 'attempt': 0}, {'file': 'w.pdf', 'pdf_page': 3, 'attempt': 1},
               {'file': 'w.pdf', 'pdf_page': 4, 'attempt': 7}]
    monkeypatch.setattr(vision_batches, 'readings_of', lambda cells, store: records)
    assert replay.next_attempt(None, ['FREE-SM'], PAGE) == 2
    monkeypatch.setattr(vision_batches, 'readings_of', lambda cells, store: [])
    assert replay.next_attempt(None, ['FREE-SM'], PAGE) == 0


def test_a_later_replay_of_the_same_reading_replaces_its_row_in_the_replay_report(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    replay.write_check(store, 'REPLAY-FREE', {'key': 'k1', 'state': 'issue', 'replayed': True})
    replay.write_check(store, 'REPLAY-FREE', {'key': 'k2', 'state': 'ok', 'replayed': True})
    replay.write_check(store, 'REPLAY-FREE', {'key': 'k1', 'state': 'ok', 'replayed': True})
    report = json.loads(store.path('reports', 'check_report_REPLAY-FREE.json').read_text(encoding='utf-8'))
    assert report['cells'] == ['REPLAY-FREE'] and [(row['key'], row['state']) for row in report['pages']] == [('k2', 'ok'), ('k1', 'ok')]


def test_the_export_says_a_replayed_reading_was_judged_on_request(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    replay.write_check(store, 'REPLAY-FREE', {'key': 'k1', 'state': 'ok', 'reasons': [], 'in_sample': False, 'suspicious': False,
                                              'unverifiable': False, 'replayed': True})
    assert reading_export.check_states(store, ('REPLAY-FREE',))['k1']['why_judged'] == 'a replay, judged on request'


def test_judging_a_page_with_a_chosen_version_buys_once_shows_a_stored_verdict_and_asks_again_only_when_told(free, monkeypatch):
    from backend.conversion.checks import check_run
    from backend.conversion.judge import page_judge
    from test_conversion_served_readings import page as a_page

    stored = {}

    class Store:
        def reading(self, key):
            return {'r1': {'reading_key': 'r1', 'form': 'markdown', 'image_size': [100, 100], 'file': 'w.pdf'}}.get(key) or stored.get(key)

        def reading_text(self, key):
            return a_page('::: {#b01 .paragraph}\nArthur and Carlyse Ciocca\n:::')

    monkeypatch.setattr(replay, 'open_store', lambda name: Store())
    monkeypatch.setattr(replay, 'row_of', lambda base, work, pdf_page: {'reading_key': 'r1'})
    monkeypatch.setattr(page_judge, 'entry_for', lambda record, parsed, model, version=None, again=0: {
        'reading_key': f'{version}:{again}', 'estimate_usd': 0.01, 'judge_version': version})
    monkeypatch.setattr(check_run, 'page_layer', lambda file, pdf_page: 'Arthur and Carlyse Ciocca')
    monkeypatch.setattr(reading_export, 'export', lambda base, store=None: None)
    asked = []
    finding = {'kind': 'wrong_word', 'block': 'b01', 'severity': 'major', 'evidence': "printed 'Carlyse Ciocca' wait 'Carlyse'"}

    def asker(entry):
        asked.append(entry['reading_key'])
        stored[entry['reading_key']] = {'verdict': {'verdict': 'bad', 'outcome': 'issue', 'findings': [finding]}, 'cost_usd': 0.02}
        return stored[entry['reading_key']], '{}'

    first = replay.judge(free, 'w', 12, 'judge/2', cap=1.0, asker=asker)
    assert asked == ['judge/2:0'] and first['verdict']['outcome'] == 'ok' and first['verdict']['findings'][0]['void']
    replay.judge(free, 'w', 12, 'judge/2', cap=1.0, asker=asker)
    assert asked == ['judge/2:0']  # answered before: shown from the store, never bought twice
    again = replay.judge(free, 'w', 12, 'judge/2', cap=1.0, fresh=True, asker=asker)
    assert asked == ['judge/2:0', 'judge/2:1'] and again['again'] == 1


def test_a_replay_refuses_a_page_a_person_checked_unless_told_why(free, monkeypatch):
    # decision 191.a: a person's check is valuable; reading over it takes a reason, or a reset first
    from backend.conversion.store import pipeline_db

    monkeypatch.setattr(replay, 'page_of', lambda base, work, pdf_page: PAGE)
    monkeypatch.setattr(pipeline_db, 'refused_over_a_person',
                        lambda base, file, pdf_page, over: None if over else 'a person checked p. 3')
    with pytest.raises(SystemExit, match='a person checked'):
        replay.reread(free, 'w', 3, cap=1.0, dry_run=True)


def test_a_reread_after_a_review_is_told_its_findings_never_its_correction(free, tmp_path, monkeypatch):
    # M2.c (the operator, 18 Nov): the judge missed these errors, so the reader is told what the review found, block by block
    from backend.conversion.store import pipeline_db

    monkeypatch.setattr(pipeline_db, 'PATHS', {'free': tmp_path / 'p.sqlite', 'licensed': tmp_path / 'l.sqlite'})
    session = pipeline_db.delegated_giver('claude-opus-5-5', '18 Nov')
    pipeline_db.give_verdict('free', 'w.pdf', 3, 'k-standing', 'reject', 'reading_wrong', session, block='b04',
                             note='two values sit under swapped column headers', correction='<table><tr><td>secret</td></tr></table>')
    pipeline_db.give_verdict('free', 'w.pdf', 3, 'k-older', 'reject', 'reading_wrong', session, block='b09', note='an older one')
    found = replay.review_findings(free, 'w.pdf', 3, 'k-standing')
    hint = vision_batches.review_hint(found)
    assert [finding['block'] for finding in found] == ['b04']
    assert '- b04: two values sit under swapped column headers' in hint and 'secret' not in hint and 'b09' not in hint
    assert hint.startswith('A review of your previous reading')
