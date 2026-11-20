"""A night's run (N3.a): its ledger and batches, generalised from the first whole work read in a session."""
import json
from types import SimpleNamespace

from backend.conversion.reading import night_run


def test_a_run_starts_with_its_works_and_their_judge_share_and_logs_its_parts(tmp_path, monkeypatch):
    added = []
    monkeypatch.setattr(night_run, 'runs_folder', lambda base: tmp_path / 'night')
    monkeypatch.setattr(night_run.direct_reader, 'pages', lambda args: added.append((args.add_work, args.judge_share)))
    ledger = night_run.start(SimpleNamespace(knowledge_base='licensed', run='n1', work=['scan.pdf'], judge_share=0.6))
    assert added == [(['scan.pdf'], 0.6)] and ledger['chunks'] == night_run.CHUNKS
    night_run.log(SimpleNamespace(run='n1', number=1, judge_chunk=None, tokens=200_000, ms=600_000, pages=20, note=None))
    night_run.log(SimpleNamespace(run='n1', number=None, judge_chunk=1, tokens=50_000, ms=120_000, pages=10, note='chunk 1'))
    kept = json.loads((tmp_path / 'night' / 'n1.json').read_text(encoding='utf-8'))
    assert kept['batches']['1']['tokens_per_page'] == 10_000 and kept['batches']['1']['seconds_per_page'] == 30
    assert night_run.totals(kept['judge_chunks']) == {'parts': 1, 'pages': 10, 'agent_tokens': 50_000, 'duration_s': 120,
                                                      'tokens_per_page': 5_000, 'seconds_per_page': 12}


def test_a_batch_takes_only_the_run_s_own_waiting_pages_and_none_another_batch_holds(tmp_path, monkeypatch):
    session = tmp_path / 'session'
    for name in ('scan__p0001', 'scan__p0002', 'scan__p0003', 'other__p0001'):
        (session / name).mkdir(parents=True)
        entry = {'file': name.split('__')[0] + '.pdf', 'pdf_page': int(name[-4:])}
        (session / name / 'entry.json').write_text(json.dumps(entry), encoding='utf-8')
    monkeypatch.setattr(night_run, 'listed_pages', lambda base: {('scan.pdf', 1), ('scan.pdf', 2), ('scan.pdf', 3), ('other.pdf', 1)})
    (session / 'scan__p0003' / 'reading.md').write_text('read', encoding='utf-8')
    monkeypatch.setattr(night_run, 'runs_folder', lambda base: tmp_path / 'night')
    monkeypatch.setattr(night_run.direct_reader, 'session_folder', lambda base: session)
    monkeypatch.setattr(night_run.direct_reader, 'pages', lambda args: None)
    prepared = []
    monkeypatch.setattr(night_run.direct_reader, 'prepare', lambda args: prepared.append(args.work))
    night_run.start(SimpleNamespace(knowledge_base='licensed', run='n1', work=['scan.pdf'], judge_share=0.6))
    assert night_run.batch(SimpleNamespace(run='n1', number=1, size=1)) == ['scan__p0001']
    assert night_run.batch(SimpleNamespace(run='n1', number=2, size=5)) == ['scan__p0002']  # read and held pages are not taken
    assert prepared == [['scan.pdf']]  # too few waiting: more prepared, of the run's works only


def test_a_batch_a_rate_limit_cut_short_gives_its_unread_pages_back(tmp_path, monkeypatch):
    session = tmp_path / 'session'
    for name in ('scan__p0001', 'scan__p0002'):
        (session / name).mkdir(parents=True)
        (session / name / 'entry.json').write_text(json.dumps({'file': 'scan.pdf', 'pdf_page': int(name[-4:])}), encoding='utf-8')
    monkeypatch.setattr(night_run, 'listed_pages', lambda base: {('scan.pdf', 1), ('scan.pdf', 2)})
    monkeypatch.setattr(night_run, 'runs_folder', lambda base: tmp_path / 'night')
    monkeypatch.setattr(night_run.direct_reader, 'session_folder', lambda base: session)
    monkeypatch.setattr(night_run.direct_reader, 'pages', lambda args: None)
    monkeypatch.setattr(night_run.direct_reader, 'prepare', lambda args: None)
    monkeypatch.setattr(night_run.direct_reader, 'store', lambda args: {'ok': 1})
    night_run.start(SimpleNamespace(knowledge_base='licensed', run='n1', work=['scan.pdf'], judge_share=0.6))
    assert night_run.batch(SimpleNamespace(run='n1', number=1, size=2)) == ['scan__p0001', 'scan__p0002']
    (session / 'scan__p0001' / 'reading.md').write_text('read', encoding='utf-8')  # the agent stopped after its first page
    night_run.store(SimpleNamespace(run='n1', number=1))
    assert not (session / 'scan__p0001').exists()
    assert night_run.batch(SimpleNamespace(run='n1', number=2, size=2)) == ['scan__p0002']


def test_a_prepared_page_the_cell_no_longer_lists_is_never_batched(tmp_path, monkeypatch):
    # N5.a (20 Nov): a born-digital work's prose pages left the list; their folders prepared before must not be read
    session = tmp_path / 'session'
    for name in ('book__p0001', 'book__p0002'):
        (session / name).mkdir(parents=True)
        (session / name / 'entry.json').write_text(json.dumps({'file': 'book.pdf', 'pdf_page': int(name[-4:])}), encoding='utf-8')
    monkeypatch.setattr(night_run, 'runs_folder', lambda base: tmp_path / 'night')
    monkeypatch.setattr(night_run.direct_reader, 'session_folder', lambda base: session)
    monkeypatch.setattr(night_run.direct_reader, 'pages', lambda args: None)
    monkeypatch.setattr(night_run.direct_reader, 'prepare', lambda args: None)
    monkeypatch.setattr(night_run, 'listed_pages', lambda base: {('book.pdf', 2)})
    night_run.start(SimpleNamespace(knowledge_base='licensed', run='n1', work=['book.pdf'], judge_share=0.6))
    assert night_run.batch(SimpleNamespace(run='n1', number=1, size=5)) == ['book__p0002']
