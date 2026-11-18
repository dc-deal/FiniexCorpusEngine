"""The runs view (21.a): every run newest first over both knowledge bases, one run whole with its code, its cost by provider
and the pages it chose, a base without a pipeline database said so, the licensed one never read under --public-only."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.conversion.store import pipeline_db
from backend.diagnostics import runs
from backend.diagnostics.app import create_app
from test_diagnostics_readings import KELLY, a_corpus, kelly_rows

# TestClient's own host, "testserver", is refused like any other name that is not this machine's (app.TRUSTED_HOSTS)
LOCAL = 'http://127.0.0.1'


@pytest.fixture
def databases(monkeypatch, tmp_path):
    """Pipeline databases of this test's own, none of them written yet, as on a clone."""
    paths = {'free': tmp_path / 'free.sqlite', 'licensed': tmp_path / 'licensed.sqlite'}
    monkeypatch.setattr(pipeline_db, 'PATHS', paths)
    return paths


def record(path, knowledge_base, *, started, command='python -m backend.conversion.reading.replay reread --work kelly --page 3',
           clean=1, by_provider=None, batches=None, chose=()):
    """One run, and the pages it chose; returns its id."""
    with sqlite3.connect(path) as db:
        db.executescript(pipeline_db.SCHEMA)
        cursor = db.execute(
            'INSERT INTO runs (knowledge_base, command, started_at, ended_at, outcome, code_commit, code_clean, code_sha256, '
            'cost_usd, cost_by_provider, batch_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (knowledge_base, command, started, started, 'ok', 'abc123def4567890', clean, 'f00d' * 16,
             sum((by_provider or {}).values()), json.dumps(by_provider) if by_provider else None, json.dumps(batches or [])))
        for file, pdf_page in chose:
            db.execute('INSERT INTO chosen_readings (knowledge_base, file, pdf_page, reading_key, why, run_id, chosen_at) '
                       'VALUES (?, ?, ?, ?, ?, ?, ?)', (knowledge_base, file, pdf_page, 'k' * 16, 'replay --reread: judged ok',
                                                       cursor.lastrowid, started))
        return cursor.lastrowid


@pytest.mark.readings
def test_every_run_stands_newest_first_over_both_bases(databases, tmp_path):
    record(databases['free'], 'free', started='2026-11-05T08:00:00+00:00')
    record(databases['licensed'], 'licensed', started='2026-11-05T09:00:00+00:00')
    record(databases['free'], 'free', started='2026-11-05T10:00:00+00:00', batches=['msgbatch_01'])
    bases = {'free': a_corpus(tmp_path / 'f', kelly_rows()[:1]), 'licensed': a_corpus(tmp_path / 'l', kelly_rows()[:1], 'licensed')}
    listed = runs.run_list(bases, public_only=False)
    assert [(line.knowledge_base, line.run_id) for line in listed.runs] == [('free', 2), ('licensed', 1), ('free', 1)]
    assert listed.runs[0].batch_ids == ['msgbatch_01'] and all(base.why_not is None for base in listed.bases)


@pytest.mark.readings
def test_a_run_names_its_code_its_cost_by_provider_and_the_pages_it_chose(databases):
    kelly = kelly_rows()[2]
    run = record(databases['free'], 'free', started='2026-11-05T08:52:35+00:00', clean=0,
                 by_provider={'anthropic': 0.058, 'openrouter': 0.108},
                 chose=[(kelly['file'], kelly['pdf_page']), ('a_book_not_exported.pdf', 7)])
    shown = TestClient(create_app(public_only=True), base_url=LOCAL).get(f'/api/free/runs/{run}').json()
    assert shown['code_commit'] == 'abc123def4567890' and shown['code_clean'] is False
    assert shown['cost_by_provider'] == {'anthropic': 0.058, 'openrouter': 0.108}
    exported, unknown = shown['chose']
    # a page the export holds opens its page view; one it does not stands by its file, with no view to open
    assert (exported['source_id'], exported['pdf_page'], exported['why']) == (KELLY, kelly['pdf_page'], 'replay --reread: judged ok')
    assert exported['title'] != KELLY
    assert (unknown['source_id'], unknown['title']) == (None, 'a_book_not_exported.pdf')


def test_a_machine_without_a_pipeline_database_says_so_and_knows_no_run(databases):
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    listed = client.get('/api/runs').json()
    assert listed['runs'] == [] and listed['bases'][0] == {'knowledge_base': 'free', 'why_not': runs.NO_DATABASE}
    assert client.get('/api/free/runs/1').status_code == 404


def test_public_only_never_reads_the_licensed_runs(databases, monkeypatch):
    record(databases['licensed'], 'licensed', started='2026-11-05T09:00:00+00:00')
    asked = []
    original = pipeline_db.runs
    monkeypatch.setattr(pipeline_db, 'runs', lambda knowledge_base, path=None: asked.append(knowledge_base) or original(knowledge_base, path))
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    listed = client.get('/api/runs').json()
    assert listed['bases'][1] == {'knowledge_base': 'licensed', 'why_not': runs.NOT_READ}
    assert client.get('/api/licensed/runs/1').status_code == 404
    assert 'licensed' not in asked
