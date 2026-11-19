"""The overview (the operator's O3.a, 19 Nov): one corpus, a headline summed in the API over the knowledge bases served with
each base's part kept as its detail, and the latest runs of both; every count the removed tables gave stays reachable
through the page list's filters, and the overview never asks every reading file for its integrity."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.conversion.store import pipeline_db
from backend.diagnostics import overview, page_integrity, readings, runs
from backend.diagnostics.app import create_app
from backend.search import shelf

# TestClient's own host, "testserver", is refused like any other name that is not this machine's (app.TRUSTED_HOSTS)
LOCAL = 'http://127.0.0.1'
# invented shelves, as the core writes their totals: no licensed count stands in a test
SHELVES = {'free': {'works': 15, 'planned': 1822, 'read': 1822, 'passed': 1815, 'served': 2554},
           'licensed': {'works': 4, 'planned': 400, 'read': 390, 'passed': 380, 'served': 900}}
# an invented history as the core keeps it (X1.a): a line taken over with both bases summed, then lines with each base apart
HISTORY = {'about': 'invented', 'rows': [
    {'at': '2026-11-08', 'milestone': 'taken over', 'bases': {'both': {'planned': 2000, 'read': None, 'passed': 1900,
                                                                   'share_passed': 0.95, 'served': None, 'judge_issues': 3}}},
    {'at': '2026-11-18', 'milestone': 'licensed alone', 'bases': {'licensed': {'planned': 400, 'read': 390, 'passed': 380,
                                                                            'share_passed': 0.95, 'served': 900}}},
    {'at': '2026-11-19', 'milestone': 'both apart', 'bases': {
        'free': {'planned': 1822, 'read': 1822, 'passed': 1815, 'share_passed': 0.9962, 'served': 2554},
        'licensed': {'planned': 400, 'read': 390, 'passed': 380, 'share_passed': 0.95, 'served': 900}}},
]}


@pytest.fixture
def no_runs(monkeypatch, tmp_path):
    """No pipeline database on this machine, as on a clone."""
    monkeypatch.setattr(pipeline_db, 'PATHS', {'free': tmp_path / 'free.sqlite', 'licensed': tmp_path / 'licensed.sqlite'})
    return tmp_path


@pytest.fixture
def shelves(monkeypatch):
    """Each base's shelf as the core last built it, invented, and the corpus's history; a base left out of the dict has no
    shelf built."""
    built = dict(SHELVES)
    monkeypatch.setattr(shelf, 'load', lambda name: {'totals': built[name]} if name in built else None)
    monkeypatch.setattr(shelf, 'history', lambda: HISTORY)
    return built


def test_the_headline_sums_the_free_base_alone_under_public_only_and_says_so(monkeypatch, no_runs, shelves):
    def refuse():
        raise AssertionError('the licensed knowledge base was read')

    monkeypatch.setattr(readings, 'licensed_readings', refuse)
    answer = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/overview').json()
    headline = answer['headline']
    assert headline['bases'] == ['free']
    assert headline['left_out'] == [{'knowledge_base': 'licensed', 'why': overview.NOT_READ}]
    # the shelf's figures, the core's, summed over the free base alone, each with its part
    assert headline['works'] == {'total': 15, 'by_base': {'free': 15}}
    assert (headline['planned']['total'], headline['passed']['total'], headline['served']['total']) == (1822, 1815, 2554)
    assert headline['share_passed'] == pytest.approx(1815 / 1822)
    # the export's: what a person settled is no longer to look at (211.a), and what every reading and judgement cost
    rows = readings.Readings().rows()
    assert headline['to_look_at']['total'] == sum(1 for row in rows if readings.listed_state(row) in readings.LISTED_AS_ISSUE)
    cost = sum(value or 0.0 for row in rows for value in overview.paid_by('provider', row).values())
    assert headline['cost_usd']['total'] == pytest.approx(cost, abs=1e-3)
    # each provider's part, which the figure's card carries where the per-model tables stood (line 1, 19 Nov)
    assert sum(headline['cost_usd']['by_provider'].values()) == pytest.approx(cost, abs=1e-3)
    assert answer['runs'] is None and 'pipeline database' in answer['runs_why_not']  # said, not guessed
    # the tables are gone from the overview, whose counts the page list's filters keep (O3.a)
    assert set(answer) == {'headline', 'history', 'runs', 'runs_why_not'}
    # the history under --public-only: the free base's figures alone, never a line that holds licensed counts (X1.a)
    assert [(line['at'], line['planned'], list(line['parts'])) for line in answer['history']] == [('2026-11-19', 1822, ['free'])]
    # and never a line's name, which may name a licensed work (81.a)
    assert [line['milestone'] for line in answer['history']] == [None]


@pytest.mark.readings
def test_the_headline_sums_both_bases_and_keeps_each_part_as_its_detail(tmp_path, no_runs, shelves):
    from test_diagnostics_readings import a_corpus, kelly_rows

    rows = kelly_rows()[:3]
    free = a_corpus(tmp_path / 'free', rows)
    licensed = a_corpus(tmp_path / 'licensed', [{**row, 'knowledge_base': 'licensed'} for row in rows], knowledge_base='licensed')
    headline = overview.overview({'free': free, 'licensed': licensed}, False).headline
    assert headline.bases == ['free', 'licensed'] and headline.left_out == []
    assert headline.planned.total == 1822 + 400 and headline.planned.by_base == {'free': 1822, 'licensed': 400}
    assert headline.share_passed == pytest.approx((1815 + 380) / (1822 + 400))
    assert headline.read.total == 1822 + 390 and headline.share_read == pytest.approx((1822 + 390) / (1822 + 400))
    looked = sum(1 for row in rows if readings.listed_state(row) in readings.LISTED_AS_ISSUE)
    assert headline.to_look_at.by_base == {'free': looked, 'licensed': looked} and headline.to_look_at.total == 2 * looked


def test_the_history_sums_each_line_over_the_bases_served_newest_first_and_keeps_a_summed_line_as_it_is(shelves):
    found = overview.milestones(['free', 'licensed'], False)
    assert [line.milestone for line in found] == ['both apart', 'licensed alone', 'taken over']
    newest = found[0]
    assert (newest.planned, newest.read, newest.passed, newest.served) == (2222, 2212, 2195, 3454)
    assert newest.share_passed == pytest.approx(2195 / 2222, abs=1e-4) and not newest.summed
    assert newest.parts['licensed'].passed == 380
    # a line taken over summed stands as the core kept it, without parts; what it did not keep stays unknown
    taken = found[2]
    assert taken.summed and taken.parts == {} and (taken.planned, taken.read, taken.served) == (2000, None, None)
    # a base this app does not serve is left out of every line, and a line of it alone is left out whole
    assert [line.milestone for line in overview.milestones(['free'], False)] == ['both apart', 'taken over']


@pytest.mark.readings
def test_a_base_whose_shelf_is_not_built_is_left_out_of_the_shelfs_figures_and_says_so(tmp_path, no_runs, shelves):
    from test_diagnostics_readings import a_corpus, kelly_rows

    del shelves['free']
    headline = overview.overview({'free': a_corpus(tmp_path, kelly_rows()[:2])}, False).headline
    assert (headline.works, headline.planned, headline.passed, headline.served, headline.share_passed) == (None,) * 5
    assert [(left.knowledge_base, left.why) for left in headline.shelf_left_out] == [('free', overview.NO_SHELF)]
    assert headline.to_look_at.by_base == {'free': headline.to_look_at.total}  # the export's figures stand all the same


def test_the_overview_never_asks_a_reading_file_for_its_integrity(monkeypatch, no_runs, shelves):
    # each load stat-ed some 10,200 reading files for the integrity table (48.5 s in the container, 19 Nov); it is asked
    # through the page list's filter alone now
    monkeypatch.setattr(page_integrity, 'state', lambda export, row: pytest.fail('a reading file was asked for its integrity'))
    overview._COUNTED.clear()  # counted afresh, so the check reaches the counting too
    assert TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/overview').status_code == 200


def a_run(db, base: str, number: int, outcome: str | None = 'ok', ended: str | None = '2026-11-05T09:00:00+00:00'):
    db.execute('INSERT INTO runs (knowledge_base, command, started_at, ended_at, outcome, cost_usd, batch_ids) VALUES (?, ?, ?, ?, ?, ?, ?)',
               (base, f'python -m backend.conversion.checks.check_run {number}', f'2026-11-05T{number:02d}:00:00+00:00', ended, outcome,
                0.01 * number, '["msgbatch_01"]' if number == 10 else None))


def test_the_latest_runs_of_both_bases_stand_newest_first_each_with_its_base(no_runs, shelves):
    with sqlite3.connect(no_runs / 'free.sqlite') as db:
        db.executescript(pipeline_db.SCHEMA)
        for number in range(1, 11, 2):
            a_run(db, 'free', number)
    with sqlite3.connect(no_runs / 'licensed.sqlite') as db:
        db.executescript(pipeline_db.SCHEMA)
        for number in range(2, 11, 2):
            a_run(db, 'licensed', number)
    base_list = {'free': readings.Readings(), 'licensed': readings.Readings()}
    listed = overview.overview(base_list, False).runs
    assert [(run.knowledge_base, int(run.command.split()[-1])) for run in listed] == [
        ('licensed', 10), ('free', 9), ('licensed', 8), ('free', 7), ('licensed', 6), ('free', 5), ('licensed', 4), ('free', 3)]
    assert listed[0].batch_ids == ['msgbatch_01'] and listed[1].batch_ids == []


def test_a_new_run_stands_at_once_though_the_runs_are_kept_between_loads(no_runs):
    # the overview keeps a base's runs while its database is unchanged (0.27 s a base each load before, 19 Nov)
    with sqlite3.connect(no_runs / 'free.sqlite') as db:
        db.executescript(pipeline_db.SCHEMA)
        a_run(db, 'free', 1)
    assert [int(run.command.split()[-1]) for run in runs.recent('free', 8)] == [1]
    with sqlite3.connect(no_runs / 'free.sqlite') as db:
        a_run(db, 'free', 2)
    assert [int(run.command.split()[-1]) for run in runs.recent('free', 8)] == [2, 1]


def test_a_run_that_recorded_no_end_says_so_and_never_that_it_failed(no_runs):
    with sqlite3.connect(no_runs / 'free.sqlite') as db:
        db.executescript(pipeline_db.SCHEMA)
        a_run(db, 'free', 1, outcome=None, ended=None)
        a_run(db, 'free', 2, outcome='failed: the provider answered 529')
        a_run(db, 'free', 3)
    listed = {int(run.command.split()[-1]): run for run in runs.recent('free', 8)}
    # line 1's word (19 Nov): the process stopped before it could write its end, or it still runs; the row cannot tell which
    assert (listed[1].outcome, listed[1].outcome_why) == (runs.NO_END, runs.NO_END_WHY) == ('no end recorded', runs.NO_END_WHY)
    assert (listed[2].outcome, listed[2].outcome_why) == ('failed: the provider answered 529', None)
    assert (listed[3].outcome, listed[3].outcome_why) == ('ok', None)


@pytest.mark.readings
def test_every_count_of_the_removed_tables_stays_reachable_through_its_page_filter(no_runs):
    # O3.a's check (the operator, 19 Nov): each row of the removed tables linked `/api/pages?<field>=<value>`; for every field
    # the most common values, as the rows give them, the filter lists exactly those pages. Integrity is held by its own
    # tests below, asked only when chosen
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    rows = readings.Readings().rows()
    for field in ('route', 'state', 'person', 'review', 'category', 'why_judged', 'verdict', 'reason', 'reader', 'judge', 'provider'):
        counts: dict[str, int] = {}
        for row in rows:
            for value in overview.values_of(field, row):
                counts[value] = counts.get(value, 0) + 1
        for value, count in sorted(counts.items(), key=lambda pair: -pair[1])[:2]:
            listed = client.get('/api/pages', params={'knowledge_base': 'free', field: value}).json()['rows']
            assert len(listed) == count, (field, value)


def test_a_page_list_resolves_each_works_title_once_not_once_per_page(monkeypatch, no_runs):
    # asked per page, each title cost a stat of the export's index: 28,854 for the unfiltered list, 114 s over the
    # container's bind mount (19 Nov)
    asked = []
    title = readings.Readings.title
    monkeypatch.setattr(readings.Readings, 'title', lambda self, source_id: asked.append(source_id) or title(self, source_id))
    listed = overview.pages({'free': readings.Readings()}, {}).rows
    assert listed and len(asked) == len({page.source_id for page in listed})
    asked.clear()
    issues = readings.issues({'free': readings.Readings()}).rows
    assert len(asked) == len({page.source_id for page in issues})


@pytest.mark.readings
def test_every_page_of_the_list_carries_its_words_in_each_field_the_pages_view_narrows_by(no_runs):
    # P1.a (the operator, 19 Nov): the view narrows in the browser by these words, so they are the page list's filters' own
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    answer = client.get('/api/pages').json()
    rows = {(row['source_id'], row['pdf_page']): row for row in readings.Readings().rows()}
    assert len(answer['rows']) == len(rows) and answer['state_order'] == list(readings.STATE_ORDER)
    for page in answer['rows'][:50]:
        row = rows[(page['source_id'], page['pdf_page'])]
        assert page['filtered_by'] == {field: overview.values_of(field, row) for field in overview.WORDED}
    # never the integrity of a reading file, which is asked of the disk only through its own filter
    assert all('integrity' not in page['filtered_by'] for page in answer['rows'])
    # the Issues narrow by their own fields and carry none
    assert all(page['filtered_by'] is None for page in client.get('/api/issues').json()['rows'])


@pytest.mark.readings
def test_the_unfiltered_list_is_kept_while_no_export_changes_and_built_anew_after_one(tmp_path):
    from test_diagnostics_readings import a_corpus, kelly_rows

    corpus = a_corpus(tmp_path, kelly_rows()[:3])
    first = overview.pages({'free': corpus}, {})
    assert overview.pages({'free': corpus}, {}) is first  # kept, not built again
    assert overview.pages({'free': corpus}, {'state': 'ok'}) is not first  # a filter is answered afresh
    index = json.loads(corpus.index.read_text(encoding='utf-8'))
    index['pages'] = index['pages'][:2]
    corpus.index.write_text(json.dumps(index), encoding='utf-8')
    assert len(overview.pages({'free': corpus}, {}).rows) == 2


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


@pytest.mark.readings
def test_a_page_a_person_settled_is_not_to_look_at_and_opens_by_its_bucket(tmp_path):
    from test_diagnostics_readings import KELLY, settled_corpus

    corpus, (accepted, noted, archived, untouched, passed) = settled_corpus(tmp_path)
    assert overview.counted(corpus).to_look_at == sum(1 for row in corpus.rows() if readings.listed_state(row) in readings.LISTED_AS_ISSUE)
    # a bucket opens exactly its pages
    listed = overview.pages({'free': corpus}, {'state': readings.DECIDED}).rows
    assert sorted(page.pdf_page for page in listed if page.source_id == KELLY) == sorted([accepted, noted])


@pytest.mark.readings
def test_a_reading_file_changed_after_its_check_is_found_by_the_integrity_filter(tmp_path):
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
def test_the_headline_counts_an_export_anew_once_it_is_written_again(tmp_path):
    from test_diagnostics_readings import a_corpus, kelly_rows

    corpus = a_corpus(tmp_path, kelly_rows()[:3])
    assert overview.counted(corpus).pages == 3
    index = json.loads(corpus.index.read_text(encoding='utf-8'))
    index['pages'] = index['pages'][:2]
    corpus.index.write_text(json.dumps(index), encoding='utf-8')
    assert overview.counted(corpus).pages == 2
