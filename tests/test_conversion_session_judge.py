"""The judge in a Claude Code session (N1.a, N2.a, N3.a): the API judge's request, answered by an agent, stored as a batch's is."""
import json
from types import SimpleNamespace

from backend.conversion.checks import check_run
from backend.conversion.judge import page_judge, session_judge
from backend.conversion.store import reading_store

OK = json.dumps({'verdict': 'ok', 'findings': []})
BAD = json.dumps({'verdict': 'bad', 'findings': [{'kind': 'invented', 'block': 'b02', 'severity': 'major', 'evidence': 'x'}]})


def entry(store, work: str, page: int, **fields) -> dict:
    """A judge request as `page_judge.entry_for` writes it, its inputs in the store."""
    image = store.put_input(b'png-' + f'{work}{page}'.encode(), '.png')
    view = store.put_input(b'Transcription:\n\n[b01 paragraph]\nA.', '.txt')
    key = f'{work}{page:03d}'.ljust(64, 'r')
    return {'kind': 'judge', 'reading_key': key, 'custom_id': key[:20], 'cell': 'JUDGE-SM', 'page_id': f'{work}:p{page:04d}',
            'judge_version': page_judge.FIRST_VERSION, 'file': f'{work}.pdf', 'pdf_page': page, 'work': work, 'mirror': 'free',
            'model': check_run.JUDGE_MODEL, 'mode': 'batch', 'attempt': 0, 'replicate': 0, 'max_tokens': 2000,
            'image_sha256': image, 'image_size': [100, 100], 'image_bytes': 10, 'sheet_sha256s': [], 'view_sha256': view,
            'target_key': f'{work}{page:03d}'.ljust(64, 't'), 'planted': None, 'planted_block': None, 'estimate_usd': 0.01, **fields}


def test_each_chunk_is_a_tenth_of_a_work_suspects_first_and_seeded():
    entries = [{'work': 'w', 'pdf_page': n, 'target_key': f't{n}'} for n in range(1, 21)] + [{'work': 'v', 'pdf_page': 1, 'target_key': 'v1'}]
    slices = session_judge.chunked({'entries': entries, 'suspicious': ['t17']}, 10)
    assert [len(part) for part in slices['w']] == [2] * 10 and slices['w'][0][0]['target_key'] == 't17'
    assert sorted(item['pdf_page'] for part in slices['w'] for item in part) == list(range(1, 21))  # each request once
    assert slices == session_judge.chunked({'entries': entries, 'suspicious': ['t17']}, 10)  # the same order every night
    assert [len(part) for part in slices['v']] == [1] + [0] * 9


def test_an_answer_is_stored_as_a_batch_s_judge_record_and_counts_unless_a_calibration(tmp_path, monkeypatch):
    store = reading_store.Store(tmp_path / 'vision')
    root = tmp_path / 'session'
    monkeypatch.setattr(session_judge, 'session_root', lambda base: root)
    monkeypatch.setattr(session_judge, 'open_store', lambda mirror: store)
    real, calibration = entry(store, 'w', 1), entry(store, 'w', 2)
    first = session_judge.write_folder(root, real, store)
    second = session_judge.write_folder(root, calibration, store, calibration=True)
    assert (first / 'page.png').exists() and (first / 'transcription.txt').exists()
    assert session_judge.write_folder(root, real, store) is None  # waits in its folder: never prepared twice
    (first / 'verdict.json').write_text(OK, encoding='utf-8')
    (second / 'verdict.json').write_text(BAD, encoding='utf-8')
    outcome = session_judge.store(SimpleNamespace(knowledge_base='free'))
    assert outcome == {'ok': 2} and not first.exists()
    stored = store.reading(session_judge.session_key(real))
    assert stored['mode'] == 'session' and stored['request_key'] == real['reading_key'] and stored['cost_usd'] == 0.0
    judged = check_run.verdicts_by_target(store)
    assert set(judged) == {real['target_key']}  # the calibration's answer is a check of the judge, never a verdict on the page


def test_the_calibration_passes_only_on_the_api_judge_s_own_gate():
    measures = {'groups': {'values': {'n': 30, 'to_issue': 30}, 'words': {'n': 19, 'to_issue': 18}},
                'clean': {'n': 8, 'issue': 0}, 'answered': 57}
    assert session_judge.calibration_gate(measures, 57)['passed']
    assert not session_judge.calibration_gate({**measures, 'clean': {'n': 8, 'issue': 1}}, 57)['passed']
    assert not session_judge.calibration_gate({**measures, 'groups': {'values': {'n': 49, 'to_issue': 47}}}, 57)['passed']
    assert not session_judge.calibration_gate(measures, 58)['passed']  # one request left unanswered


def test_a_page_a_filter_or_a_reader_turned_away_is_never_prepared(tmp_path, monkeypatch):
    # 280.a: never the same model by another door, to judge no more than to read
    store = reading_store.Store(tmp_path / 'vision')
    entries = [entry(store, 'w', 1), entry(store, 'w', 2), entry(store, 'held', 1)]
    store.write_report(check_run._plan_name(['C']), {'entries': entries, 'suspicious': [], 'policy': {}})
    monkeypatch.setattr(check_run, 'store_of', lambda cells: store)
    monkeypatch.setattr(session_judge, 'open_store', lambda mirror: store)
    monkeypatch.setattr(session_judge, 'session_root', lambda base: tmp_path / 'session')
    monkeypatch.setattr(session_judge, 'filtered_pages', lambda base: {('w.pdf', 2)})
    monkeypatch.setattr(session_judge.reading_cells, 'may_send', lambda name: name != 'held.pdf')
    made = session_judge.prepare(SimpleNamespace(cells='C', chunk=1, chunks=1))
    assert [folder.rsplit('\\', 1)[-1].rsplit('/', 1)[-1] for folder in made] == ['w__p0001']
    assert (tmp_path / 'session' / 'judge_instructions.md').exists() and (tmp_path / 'session' / 'verdict_schema.json').exists()


def test_a_work_over_the_stop_share_is_stopped_and_gets_no_further_chunk(tmp_path, monkeypatch):
    store = reading_store.Store(tmp_path / 'vision')
    root = tmp_path / 'session'
    entries = [entry(store, 'w', n) for n in range(1, 11)]
    store.write_report(check_run._plan_name(['C']), {'entries': entries, 'suspicious': [], 'policy': {'sample_per_work': 40, 'stop_above': 6}})
    monkeypatch.setattr(check_run, 'store_of', lambda cells: store)
    monkeypatch.setattr(session_judge, 'open_store', lambda mirror: store)
    monkeypatch.setattr(session_judge, 'session_root', lambda base: root)
    monkeypatch.setattr(session_judge, 'filtered_pages', lambda base: set())
    monkeypatch.setattr(session_judge.reading_cells, 'may_send', lambda name: True)
    monkeypatch.setattr(check_run, 'voided', lambda store, verdict, key: page_judge.with_void(verdict))
    for done in entries[:4]:  # two of four bad: 50 %, over 6 of 40
        folder = session_judge.write_folder(root, done, store)
        (folder / 'verdict.json').write_text(BAD if done['pdf_page'] <= 2 else OK, encoding='utf-8')
    session_judge.store(SimpleNamespace(knowledge_base='free'))
    result = session_judge.gate(SimpleNamespace(cells='C'))
    assert result['works']['w'] == {'judged': 4, 'bad': 2} and result['stopped'] == ['w'] and result['stop_share'] == 0.15
    assert session_judge.prepare(SimpleNamespace(cells='C', chunk=2, chunks=5)) == []


def test_a_calibration_folder_says_nothing_of_its_planted_error(tmp_path):
    # N1.a: the agent sees what the API judge saw, never the plan; judge/1's plan lists the clean readings first
    store = reading_store.Store(tmp_path / 'vision')
    planted = entry(store, 'w', 3, planted='wrong_value', planted_block='b05')
    folder = session_judge.write_folder(tmp_path / 'session', planted, store, calibration=True)
    assert folder.name.startswith('cal_') and 'b05' not in folder.name and 'wrong' not in folder.name
    assert sorted(path.name for path in folder.iterdir()) == ['page.png', 'transcription.txt']
    kept = json.loads((tmp_path / 'session' / session_judge.ENTRIES / f'{folder.name}.json').read_text(encoding='utf-8'))
    assert kept['planted'] == 'wrong_value' and kept['replicate'] == 1
