"""The calls view (19.a): the search server's call log read as the core writes it, both shapes of `answered`, every figure
counted here, and under --public-only only the calls that concern the free knowledge base alone."""

import json

import pytest
from fastapi.testclient import TestClient

from backend.diagnostics import calls, readings
from backend.diagnostics.app import create_app
from test_diagnostics_readings import KELLY, kelly_rows

# TestClient's own host, "testserver", is refused like any other name that is not this machine's (app.TRUSTED_HOSTS)
LOCAL = 'http://127.0.0.1'


def a_record(**fields):
    record = {'at': '2026-11-06T10:00:00+00:00', 'tool': 'search', 'state': 'found', 'ms': 3.0, 'client': 'claude-code',
              'client_version': '2.1', 'session': None, 'query': 'kelly criterion', 'corpus': 'all', 'hits': 3, 'work': None,
              'answered': []}
    return {**record, **fields}


@pytest.fixture
def log(tmp_path, monkeypatch):
    """A call log of this test's own, in the core's shape: one ASCII JSON record a line."""
    path = tmp_path / 'search_server.jsonl'
    monkeypatch.setattr(calls, 'LOG', path)
    return path


def write(path, *records, extra=''):
    path.write_text(''.join(json.dumps(record) + '\n' for record in records) + extra, encoding='utf-8')


def kelly_page():
    row = kelly_rows()[2]
    return {'knowledge_base': 'free', 'work': row['work'], 'label': str(row['pdf_page']), 'pdf': str(row['pdf_page'])}, row


@pytest.mark.readings
def test_every_call_stands_newest_first_its_answered_pages_opening_their_views(log):
    page, row = kelly_page()
    write(log, a_record(at='2026-11-06T09:00:00+00:00', answered=[page]),
          a_record(at='2026-11-06T11:00:00+00:00', tool='semantic_search', corpus=None, client='chat', ms=9880.0,
                   query='What is the Kelly criterion?', answered=[page]),
          # a record from before 5 Nov: a string per page, no PDF page, so no view, never a guess
          a_record(at='2026-11-03T18:59:33+00:00', client=None, answered=[f"free:{row['work']}:7"]),
          extra='not a record\n')
    # every call, as the operator's own view lists them, over the free knowledge base alone: no test reads the licensed export
    listed = calls.call_list(readings.knowledge_bases(public_only=True), public_only=False).model_dump()
    assert [call['at'][:13] for call in listed['calls']] == ['2026-11-06T11', '2026-11-06T09', '2026-11-03T18']
    answered = listed['calls'][0]['answered'][0]
    assert answered['view'] == {'knowledge_base': 'free', 'source_id': KELLY, 'pdf_page': row['pdf_page']}
    assert answered['title'] == readings.Readings().title(KELLY)
    old = listed['calls'][2]['answered'][0]
    assert (old['work'], old['label'], old['pdf'], old['view']) == (row['work'], '7', None, None)


def test_the_figures_per_tool_and_the_filters_are_counted_here(log):
    write(log, a_record(ms=2.0), a_record(ms=4.0), a_record(ms=30.0, state='nothing found'),
          a_record(tool='works', state=None, ms=0.1, query=None), a_record(tool='open_page', client=None, state='error', ms=None))
    listed = calls.call_list(readings.knowledge_bases(public_only=True), public_only=False)
    search = next(tool for tool in listed.tools if tool.tool == 'search')
    assert (search.calls, search.median_ms) == (3, 4.0)
    assert [(state.value, state.count) for state in search.states] == [('found', 2), ('nothing found', 1)]
    assert [state.value for state in listed.states] == ['found', 'nothing found', 'error', 'answered']
    assert {client.value: client.count for client in listed.clients} == {'claude-code': 4, calls.NOT_NAMED: 1}
    assert next(tool for tool in listed.tools if tool.tool == 'open_page').median_ms is None


@pytest.mark.readings
def test_public_only_lists_only_calls_that_concern_the_free_base_alone_and_says_how_many_it_left_out(log):
    page, row = kelly_page()
    licensed = {'knowledge_base': 'licensed', 'work': 'a_licensed_book', 'label': '12', 'pdf': '12'}
    write(log, a_record(answered=[page]),
          a_record(answered=[page, licensed]),
          a_record(corpus='licensed', answered=[]),
          a_record(tool='open_page', work='a_licensed_book', state='nothing found', answered=[]),
          a_record(answered=[f"free:{row['work']}:7"]),
          a_record(tool='semantic_search', corpus=None, answered=[page]))
    listed = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/calls').json()
    assert listed['hidden'] == 4
    assert [call['tool'] for call in listed['calls']] == ['search', 'semantic_search']
    assert 'a_licensed_book' not in json.dumps(listed)


def test_a_line_is_a_record_only_up_to_its_newline(log):
    # a record holding a line separator inside a string stays one record: the log is split at '\n' alone
    write(log, a_record(query='kelly criterion'), a_record(query='drawdown'))
    assert [call.query for call in calls.call_list(readings.knowledge_bases(public_only=True), False).calls] == \
        ['kelly criterion', 'drawdown']


def test_a_machine_without_a_call_log_says_so(log):
    listed = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/calls').json()
    assert listed['why_not'] == calls.NO_LOG and listed['calls'] == []


@pytest.mark.readings
def test_a_search_over_works_lists_its_works_each_opening_its_pages_and_a_licensed_one_stays_out_under_public_only(log):
    _, row = kelly_page()
    free_work = {'knowledge_base': 'free', 'work': row['work']}
    write(log, a_record(tool='search_works', answered=[], answered_works=[free_work]),
          a_record(tool='search_works', answered=[], answered_works=[free_work, {'knowledge_base': 'licensed', 'work': 'book_a'}]))
    listed = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/calls').json()
    # a licensed work is a licensed name: the call that named one is left out, as a licensed page would be
    assert listed['hidden'] == 1
    [call] = listed['calls']
    assert call['answered_works'] == [{'knowledge_base': 'free', 'work': row['work'], 'source_id': KELLY,
                                       'title': readings.Readings().title(KELLY)}]
    assert call['filtered_by']['kb'] == ['free']
