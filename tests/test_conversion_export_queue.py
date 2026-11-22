"""The export behind a verdict from the page view (decision 213.b): one at a time, at most one more after it, a failure said."""

import json
import threading

import pytest

from backend.conversion.checks import human_verdict
from backend.conversion.store import export_queue, pipeline_db, reading_export


def a_queue(run) -> export_queue.ExportQueue:
    return export_queue.ExportQueue(reading_export.BASES['free'], run=run)


def test_requests_while_an_export_runs_make_exactly_one_more_run():
    gate, runs = threading.Event(), []

    def run():
        runs.append(1)
        gate.wait(5)

    queue = a_queue(run)
    first = queue.request()
    assert first['running'] is True
    for _ in range(3):  # three verdicts given while the first export runs
        assert queue.request()['pending'] is True
    gate.set()
    assert queue.wait(5)
    assert len(runs) == 2 and queue.finished == 2 and queue.status()['running'] is False


def test_a_failed_export_is_said_in_the_status_and_the_next_request_runs_again():
    calls = []

    def run():
        calls.append(1)
        if len(calls) == 1:
            raise OSError('the disk is full')

    queue = a_queue(run)
    queue.request()
    assert queue.wait(5)
    assert queue.status()['last_error'] == 'OSError: the disk is full'
    queue.request()
    assert queue.wait(5)
    assert queue.status()['last_error'] is None and queue.finished == 2


@pytest.fixture
def a_base(tmp_path, monkeypatch):
    """One page in an export outside the repository, and the pipeline database beside it."""
    monkeypatch.setattr(pipeline_db, 'PATHS', {base: tmp_path / base / 'pipeline.sqlite' for base in ('free', 'licensed')})
    monkeypatch.setattr(pipeline_db, '_spent', lambda base: {'anthropic': 0.0, 'openrouter': 0.0})
    monkeypatch.setattr(pipeline_db, '_batch_ids', lambda: set())
    export = tmp_path / 'readings'
    export.mkdir()
    row = {'work': 'w', 'file': 'w.pdf', 'pdf_page': 7, 'reading_key': 'k' * 64, 'route': 'vision reading',
           'attempts': [{'reading_key': 'old' + 'k' * 61}]}
    (export / 'index.json').write_text(json.dumps({'pages': [row]}), encoding='utf-8')
    return reading_export.KnowledgeBase('free', export, tmp_path, lambda: (), tracked=False)


def test_a_verdict_from_the_view_is_recorded_as_its_own_run_and_asks_for_an_export(a_base):
    class Queue:
        def request(self, works=None):
            self.works = works
            return {'running': True, 'pending': False}

    queue = Queue()

    made = human_verdict.from_view(a_base, queue, 'w', 7, 'note', 'reading_wrong', block='b03',
                                   correction='<table><tbody><tr><td>Cash</td><td>150</td></tr></tbody></table>',
                                   judge_assessment='right')
    assert made['export'] == {'running': True, 'pending': False} and made['reading_key'] == 'k' * 64
    assert queue.works == {'w'}  # the work the verdict touched, for the index database (issue #10, D)
    stored = pipeline_db.human_verdicts('free')[('w.pdf', 7)][0]
    assert stored['given_by'] == 'maintainer' and stored['correction'].startswith('<table>') and stored['run_id']


@pytest.mark.parametrize('fields', [{'pdf_page': 8}, {'reading_key': 'x' * 64}, {'block': 'b3; drop'},
                                    {'reason': 'other'}, {'verdict': 'approve'}, {'correction': 'text'}])
def test_an_input_the_record_refuses_is_a_value_error_the_view_can_answer(a_base, fields):
    given = {'work': 'w', 'pdf_page': 7, 'verdict': 'accept', 'reason': 'judge_misread_name', 'by': 'maintainer', **fields}
    with pytest.raises(ValueError):
        human_verdict.record(a_base, **given)
    assert ('w.pdf', 7) not in pipeline_db.human_verdicts('free')


def test_the_status_says_since_when_an_export_runs_and_how_long_one_usually_takes(tmp_path, monkeypatch):
    # E1.a (the operator, 21 Nov): a person who records a verdict is told how long it waits for the export
    import sqlite3
    import threading

    from backend.conversion.store import pipeline_db

    database = tmp_path / 'pipeline.sqlite3'
    with pipeline_db.connect('free', database) as db:
        rows = [('python -m backend.conversion.store.reading_export --knowledge-base free', '2026-11-20T10:00:00+00:00', '2026-11-20T10:05:00+00:00'),
                ('python -m backend.conversion.store.reading_export --knowledge-base free', '2026-11-19T10:00:00+00:00', '2026-11-19T10:03:00+00:00'),
                (export_queue.VIEW_COMMAND.format('free'), '2026-11-21T10:00:00+00:00', '2026-11-21T10:10:00+00:00')]
        for command, started, ended in rows:
            db.execute("INSERT INTO runs (knowledge_base, command, started_at, ended_at, outcome) VALUES ('free', ?, ?, ?, 'ok')",
                       (command, started, ended))
    assert export_queue.expected_seconds('free', database) == 600  # the view's own runs first: its container is slower
    monkeypatch.setattr(export_queue, 'expected_seconds', lambda name: 600)
    release = threading.Event()
    queue = export_queue.ExportQueue(reading_export.BASES['free'], run=lambda: release.wait(5))
    queue.request()
    running = queue.status()
    assert running['running'] and running['started_at'] and running['expected_seconds'] == 600
    release.set()
    assert queue.wait(5)
    idle = queue.status()
    assert idle['started_at'] is None and idle['expected_seconds'] is None


def test_the_works_a_verdict_touched_are_written_after_the_export_that_carries_them():
    import threading

    written, release = [], threading.Event()
    queue = export_queue.ExportQueue(reading_export.BASES['free'], run=lambda: release.wait(5), after=written.append)
    queue.request({'alpha'})
    queue.request({'beta'})  # during the running export: it goes with the next one
    release.set()
    assert queue.wait(10)
    assert written == [{'alpha'}, {'beta'}]


def test_a_failure_writing_the_database_is_reported_and_never_raised():
    def after(works):
        raise RuntimeError('database down')

    queue = export_queue.ExportQueue(reading_export.BASES['free'], run=lambda: None, after=after)
    queue.request({'alpha'})
    assert queue.wait(10) and 'database down' in queue.status()['last_error']


def test_the_database_is_not_written_where_the_librarian_reads_files(monkeypatch):
    from backend.configuration.app_config_manager import AppConfigManager
    from backend.types.config_types.app_config_types import DatabaseConfig, IndexSource

    monkeypatch.setattr(AppConfigManager, 'get_database', lambda self: DatabaseConfig(librarian_reads=IndexSource.MEMORY))
    monkeypatch.setattr('backend.search.database.index_import.import_works',
                        lambda *args: (_ for _ in ()).throw(AssertionError('no write expected')))
    export_queue.write_to_database({'alpha'})


def test_a_verdict_s_work_is_named_as_the_librarian_names_it(monkeypatch):
    from backend.search import search_server

    monkeypatch.setattr(search_server, 'legacy_keys', lambda: {'invented_key': 'invented_stem'})
    monkeypatch.setattr(search_server, 'stand_in_rule', lambda: ('__replacement', {'invented_key'}))
    assert export_queue.librarian_keys({'invented_stem'}) == {'invented_stem', 'invented_key'}
    assert export_queue.librarian_keys({'invented_stem__replacement'}) >= {'invented_key'}
    assert export_queue.librarian_keys({'new_book'}) == {'new_book'}
