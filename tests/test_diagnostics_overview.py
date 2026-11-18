"""The overview: every figure counted in the API, each value once with its count per knowledge base, each count opening
exactly the pages it counts, a base not served saying why."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.conversion.store import pipeline_db
from backend.diagnostics import overview, readings, search_hits
from backend.diagnostics.app import create_app
from backend.search import page_index, search_server

# TestClient's own host, "testserver", is refused like any other name that is not this machine's (app.TRUSTED_HOSTS)
LOCAL = 'http://127.0.0.1'


@pytest.fixture
def no_runs(monkeypatch, tmp_path):
    """No pipeline database on this machine, as on a clone."""
    monkeypatch.setattr(pipeline_db, 'PATHS', {'free': tmp_path / 'free.sqlite', 'licensed': tmp_path / 'licensed.sqlite'})
    return tmp_path


def answer_of(client):
    answer = client.get('/api/overview').json()
    boxes = answer['sections'] + [answer['search']]
    return {base['knowledge_base']: base for base in answer['bases']}, {section['title']: section for section in boxes}


def test_each_base_has_its_headline_and_the_licensed_one_says_it_is_not_read(monkeypatch, no_runs):
    def refuse():
        raise AssertionError('the licensed knowledge base was read')

    monkeypatch.setattr(readings, 'licensed_readings', refuse)
    bases, _ = answer_of(TestClient(create_app(public_only=True), base_url=LOCAL))
    free, licensed = bases['free'], bases['licensed']
    rows = readings.Readings().rows()
    assert free['served'] and free['pages'] == len(rows) and free['works'] == len({row['source_id'] for row in rows})
    assert free['judged'] == sum(1 for row in rows if (row.get('check') or {}).get('judged'))
    # what a person settled is no longer to look at (211.a)
    assert free['to_look_at'] == sum(1 for row in rows if readings.listed_state(row) in readings.LISTED_AS_ISSUE)
    assert licensed['served'] is False and '--public-only' in licensed['why_not']
    assert free['runs'] is None  # no pipeline database here: said, not guessed


def test_each_value_stands_once_with_its_count_per_base(no_runs):
    _, sections = answer_of(TestClient(create_app(public_only=True), base_url=LOCAL))
    rows = readings.Readings().rows()
    for title in ('How the text is made', 'State', 'Why judged, or why not'):
        values = [row['value'] for row in sections[title]['rows']]
        assert len(values) == len(set(values)), title
        assert sum(row['free'] for row in sections[title]['rows']) == len(rows), title
        assert all(row['licensed'] is None for row in sections[title]['rows'])  # not served
    states = [row['value'] for row in sections['State']['rows']]
    assert states == sorted(states, key=readings.STATE_ORDER.index)


def test_every_count_opens_exactly_the_pages_it_counts(no_runs):
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    _, sections = answer_of(client)
    for section in sections.values():
        if not section['linked']:
            continue
        for row in section['rows'][:3]:
            listed = client.get('/api/pages', params={'knowledge_base': 'free', section['field']: row['value']}).json()
            assert len(listed['rows']) == row['free'], (section['title'], row['value'])


def test_each_model_counts_the_pages_it_worked_on_and_what_all_its_work_on_them_cost(no_runs):
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    models = {section['title']: section for section in client.get('/api/overview').json()['models']}
    rows = readings.Readings().rows()
    attempts = [(row, attempt) for row in rows for attempt in row.get('attempts') or []]
    judged = [(row, row['check']['judge']) for row in rows if (row.get('check') or {}).get('judge')]
    for found in models['Readings by model']['rows']:
        mine = [(row, attempt) for row, attempt in attempts if overview.reader_of(attempt) == found['value']]
        assert found['free'] == len({(row['work'], row['pdf_page']) for row, _ in mine}), found['value']
        assert found['free_usd'] == pytest.approx(sum(attempt['cost_usd'] for _, attempt in mine), abs=1e-3)
        assert found['licensed'] is None and found['licensed_usd'] is None  # not served
    assert sum(found['free_usd'] for found in models['Judgements by model']['rows']) == pytest.approx(
        sum(judge['cost_usd'] for _, judge in judged), abs=1e-3)
    # a provider is paid for its readings and its judgements alike
    providers = {found['value']: found['free_usd'] for found in models['By provider, readings and judgements']['rows']}
    assert sum(providers.values()) == pytest.approx(sum(attempt['cost_usd'] for _, attempt in attempts)
                                                    + sum(judge['cost_usd'] for _, judge in judged), abs=1e-3)
    # the headline's cost is what the provider box adds up to
    free = next(base for base in client.get('/api/overview').json()['bases'] if base['knowledge_base'] == 'free')
    assert free['cost_usd'] == pytest.approx(sum(providers.values()), abs=1e-3)
    for section in models.values():
        assert section['linked']
        for found in section['rows'][:2]:
            listed = client.get('/api/pages', params={'knowledge_base': 'free', section['field']: found['value']}).json()
            assert len(listed['rows']) == found['free'], (section['title'], found['value'])


def test_a_cost_the_export_does_not_give_stays_unknown_and_a_known_one_is_never_lost():
    row = {'attempts': [{'model': 'claude-sonnet-5-5', 'provider': 'anthropic', 'upstream': None},
                        {'model': 'mistralai/mistral-large-4-0', 'provider': 'openrouter', 'upstream': 'Mistral', 'cost_usd': 0.02},
                        {'model': 'mistralai/mistral-large-4-0', 'provider': 'openrouter', 'upstream': 'Mistral'}],
           'check': {'judge': {'model': 'claude-sonnet-5-5', 'provider': 'anthropic', 'mode': 'batch', 'cost_usd': 0.01}}}
    assert overview.paid_by('reader', row) == {'claude-sonnet-5-5': None, 'mistralai/mistral-large-4-0 · Mistral': 0.02}
    assert overview.paid_by('judge', row) == {'claude-sonnet-5-5': 0.01}
    assert overview.paid_by('provider', row) == {'anthropic': 0.01, 'openrouter': 0.02}
    assert overview.paid_by('judge', {'attempts': [], 'check': None}) == {}


@pytest.mark.readings
def test_filters_add_up_and_a_page_list_names_its_work(no_runs):
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    blocked = client.get('/api/pages', params={'state': 'blocked'}).json()['rows']
    both = client.get('/api/pages', params={'state': 'blocked', 'reason': 'errored'}).json()['rows']
    assert blocked and both and len(both) <= len(blocked)
    assert all(row['check']['state'] == 'blocked' and row['title'] for row in both)
    assert client.get('/api/pages', params={'knowledge_base': 'other'}).status_code == 422


def test_the_latest_runs_stand_newest_first_with_their_batches(no_runs):
    with sqlite3.connect(no_runs / 'free.sqlite') as db:
        db.executescript(pipeline_db.SCHEMA)
        for number in range(1, 11):
            db.execute('INSERT INTO runs (knowledge_base, command, started_at, outcome, cost_usd, batch_ids) VALUES (?, ?, ?, ?, ?, ?)',
                       ('free', f'python -m backend.conversion.checks.check_run {number}', f'2026-11-05T0{number % 10}:00:00+00:00',
                        'ok', 0.01 * number, '["msgbatch_01"]' if number == 10 else None))
    bases, _ = answer_of(TestClient(create_app(public_only=True), base_url=LOCAL))
    runs = bases['free']['runs']
    assert [run['run_id'] for run in runs] == [10, 9, 8, 7, 6, 5, 4, 3]
    assert runs[0]['batch_ids'] == ['msgbatch_01'] and runs[1]['batch_ids'] == []


def test_the_search_is_counted_once_it_is_built_and_says_so_before(monkeypatch, no_runs):
    page = page_index.Page('wikipedia_trading_set', 's2', 1, 'The Kelly criterion sizes a bet.', 'corpus/raw/x.html',
                           knowledge_base='free', route='html, parsed by section')
    service = search_server.SearchService({'free': ([page], {page.work: search_server.Work(
        page.work, 'Wikipedia', 'free', 'CC BY-SA', page.route)})})
    monkeypatch.setattr(search_hits, 'build_service', lambda public_only: service)
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    bases, before = answer_of(client)
    assert before['In the search, every medium']['rows'] == [] and 'still being built' in before['In the search, every medium']['note']
    # what the search serves is not known before the index stands, and not guessed
    assert (bases['free']['served_works'], bases['free']['served_pages']) == (None, None)
    client.get('/api/search', params={'q': 'kelly'})  # builds it
    bases, after = answer_of(client)
    search = after['In the search, every medium']
    assert search['linked'] is False and search['note'] is None
    assert search['rows'] == [{'value': 'html, parsed by section', 'free': 1, 'licensed': None}]
    # the headline says what the search serves beside what was read, counted as the server's start banner counts it
    # (the operator's 1.a): an HTML work the readings never hold is served all the same
    free = bases['free']
    assert (free['served_works'], free['served_pages']) == (1, 1)
    assert free['works'] == len({row['source_id'] for row in readings.Readings().rows()})
    assert 'free 1 pages in 1 works' in search_server.banner(service, [], None, True)[2]
    assert bases['licensed']['served'] is False and bases['licensed']['served_works'] is None


@pytest.mark.readings
def test_the_overview_counts_a_page_a_person_settled_apart_from_what_is_to_look_at_and_opens_it_by_its_bucket(tmp_path):
    from test_diagnostics_readings import KELLY, settled_corpus

    corpus, (accepted, noted, archived, untouched, passed) = settled_corpus(tmp_path)
    counted = overview.counted(corpus)
    states = counted.counts['state']
    assert states[readings.DECIDED] == 2 and states['issue'] == 2
    assert counted.to_look_at == sum(1 for row in corpus.rows() if readings.listed_state(row) in readings.LISTED_AS_ISSUE)
    # a figure opens exactly the pages it counts, the bucket too
    listed = overview.pages({'free': corpus}, {'state': readings.DECIDED}).rows
    assert sorted(page.pdf_page for page in listed if page.source_id == KELLY) == sorted([accepted, noted])


@pytest.mark.readings
def test_a_reading_file_changed_after_its_check_is_counted_at_once_and_its_page_listed(tmp_path):
    from test_diagnostics_readings import KELLY, a_corpus, kelly_rows

    rows = [row for row in kelly_rows() if row.get('text_file')][:2]
    corpus = a_corpus(tmp_path, rows)
    assert [overview.values_of('integrity', row, corpus.export) for row in rows] == [['whole'], ['whole']]
    (corpus.export / rows[0]['text_file']).write_text('tampered\n', encoding='utf-8')
    listed = overview.pages({'free': corpus}, {'integrity': 'tampered'}).rows
    assert [(page.source_id, page.pdf_page) for page in listed] == [(KELLY, rows[0]['pdf_page'])]


@pytest.mark.readings
def test_a_reading_file_is_hashed_again_only_when_its_time_or_size_changed(tmp_path, monkeypatch):
    from backend.conversion.checks import integrity
    from backend.diagnostics import page_integrity
    from test_diagnostics_readings import a_corpus, kelly_rows

    row = next(row for row in kelly_rows() if row.get('text_file'))
    corpus = a_corpus(tmp_path, [row])
    hashed = []
    monkeypatch.setattr(integrity, 'page_state', lambda export, one: hashed.append(one['pdf_page']) or 'whole')
    assert [page_integrity.state(corpus.export, row) for _ in range(3)] == ['whole'] * 3
    assert len(hashed) == 1  # asked three times, hashed once
    monkeypatch.undo()
    target = corpus.export / row['text_file']
    target.write_bytes(target.read_bytes() + b'\n')
    assert page_integrity.state(corpus.export, row) == 'tampered'
    target.unlink()
    assert page_integrity.state(corpus.export, row) == 'missing'
    # a page without a reading file is said as the core says it, without a stat
    assert page_integrity.state(corpus.export, {**row, 'text_file': None}) == integrity.page_state(corpus.export, {**row, 'text_file': None})


@pytest.mark.readings
def test_the_overview_counts_an_export_anew_once_it_is_written_again(tmp_path, no_runs):
    import json

    from test_diagnostics_readings import a_corpus, kelly_rows

    corpus = a_corpus(tmp_path, kelly_rows()[:3])
    search = search_hits.Search(True)
    assert overview.overview({'free': corpus}, search, True).bases[0].pages == 3
    index = json.loads(corpus.index.read_text(encoding='utf-8'))
    index['pages'] = index['pages'][:2]
    corpus.index.write_text(json.dumps(index), encoding='utf-8')
    assert overview.overview({'free': corpus}, search, True).bases[0].pages == 2


def test_the_overview_says_whether_each_reading_is_what_was_checked(no_runs):
    _, sections = answer_of(TestClient(create_app(public_only=True), base_url=LOCAL))
    box = sections['Is the reading what was checked']
    assert box['field'] == 'integrity' and box['linked']
    assert sum(row['free'] for row in box['rows']) == len(readings.Readings().rows())


@pytest.mark.readings
def test_a_persons_verdicts_are_counted_by_their_standing_and_open_their_pages(no_runs):
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    _, sections = answer_of(client)
    marks = [mark.standing for row in readings.Readings().rows() if (mark := readings.person_mark(row))]
    counted = {row['value']: row['free'] for row in sections["A person's verdict"]['rows']}
    assert counted == {standing: marks.count(standing) for standing in set(marks)} and counted.get('accepted')
    listed = client.get('/api/pages', params={'person': 'accepted'}).json()['rows']
    assert len(listed) == counted['accepted'] and all(row['person']['standing'] == 'accepted' for row in listed)


@pytest.mark.readings
def test_the_pages_are_counted_by_category_and_each_count_opens_its_pages(no_runs):
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    _, sections = answer_of(client)
    counted = {row['value']: row['free'] for row in sections['Page category']['rows']}
    rows = readings.Readings().rows()
    assert sum(counted.values()) == len(rows) and counted['exercise'] == sum(row.get('category') == 'exercise' for row in rows)
    listed = client.get('/api/pages', params={'category': 'exercise'}).json()['rows']
    assert len(listed) == counted['exercise'] and all(row['category'] == 'exercise' for row in listed)
