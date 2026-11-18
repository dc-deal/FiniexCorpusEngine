"""The shelf (decision 129.a): every work with the core's counts, each reason a page did not pass opening exactly those
pages by its route, the empty state where the shelf is not built, the licensed shelf never read under --public-only; and a
licensed hit named by its server key finding its page through the shelf."""

import copy

import pytest
from fastapi.testclient import TestClient

from backend.conversion.store.served_readings import TEXT_LAYER_WHY
from backend.diagnostics import search_hits, shelf_rows
from backend.diagnostics.app import create_app
from test_diagnostics_readings import KELLY, a_corpus, kelly_rows

# TestClient's own host, "testserver", is refused like any other name that is not this machine's (app.TRUSTED_HOSTS)
LOCAL = 'http://127.0.0.1'


def a_shelf(knowledge_base='free', **row):
    """A shelf in the core's shape; invented counts over a free work."""
    item = {'knowledge_base': knowledge_base, 'work': 'carta-conversano-kelly-2020', 'title': 'Kelly paper', 'source_id': KELLY,
            'file': f'{KELLY}.pdf', 'format': 'pdf', 'pages': 15, 'planned': 15, 'read': 15, 'passed': 11, 'share_passed': 0.7333,
            'not_passed': {'blocked': 3, 'issue': 1},
            'served': {'pages': 15, 'searchable': 15, 'from_readings': 11, 'by_route': {'vision reading': 11, 'text layer': 4}},
            'unplaced': {}, 'held': None, 'not_served': None, **row}
    return {'about': 'test', 'knowledge_base': knowledge_base, 'built_at': '2026-11-08T17:56:17+00:00',
            'totals': {'works': 1, 'planned': 15, 'passed': 11}, 'works': [item]}


@pytest.fixture
def shelves(monkeypatch):
    """The shelves the core would load, by knowledge base; every call is recorded."""
    given, asked = {}, []
    monkeypatch.setattr(shelf_rows.shelf, 'load', lambda name: asked.append(name) or given.get(name))
    return given, asked


@pytest.mark.readings
def test_every_work_stands_with_the_cores_counts_each_reason_opening_its_pages_by_route(shelves):
    given, _ = shelves
    given['free'] = a_shelf(unplaced={'unexplained': 2})
    free = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/shelf').json()['bases'][0]
    assert free['built_at'] == '2026-11-08T17:56:17+00:00' and free['totals']['planned'] == 15
    [row] = free['works']
    assert (row['planned'], row['passed'], row['share_passed'], row['has_pages']) == (15, 11, 0.7333, True)
    assert row['not_passed'] == [{'reason': 'blocked', 'count': 3, 'route': TEXT_LAYER_WHY['blocked']},
                                 {'reason': 'issue', 'count': 1, 'route': TEXT_LAYER_WHY['issue']}]
    # an unexplained count is the core's bug, passed on as it came so the view can show it
    assert row['unplaced'] == {'unexplained': 2} and row['unplaced_total'] == 2


def test_a_shelf_not_built_says_how_to_build_it_and_public_only_never_reads_the_licensed_one(shelves):
    _, asked = shelves
    listed = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/shelf').json()['bases']
    assert listed[0] == {'knowledge_base': 'free', 'why_not': shelf_rows.NOT_BUILT, 'built_at': None, 'in_step': None,
                         'totals': {}, 'works': []}
    assert listed[1]['why_not'] == shelf_rows.NOT_READ
    assert asked == ['free']


def test_a_work_this_app_holds_no_readings_of_opens_nothing(shelves):
    given, _ = shelves
    given['free'] = a_shelf(source_id='a_work_read_by_no_one', work=None)
    [row] = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/shelf').json()['bases'][0]['works']
    assert row['has_pages'] is False and row['work'] is None


@pytest.mark.readings
def test_a_licensed_hit_named_by_its_server_key_finds_its_page_through_the_shelf(shelves, tmp_path):
    given, _ = shelves
    row = copy.deepcopy(kelly_rows()[2])
    licensed = a_corpus(tmp_path, [row], knowledge_base='licensed')
    given['licensed'] = a_shelf('licensed', work='kelly')  # the server's own key, not the export's
    view_of = search_hits.page_links({'licensed': licensed})
    assert view_of('licensed', 'kelly', str(row['pdf_page'])).source_id == KELLY
    # the export's own key still works, and a key the shelf does not know finds nothing
    assert view_of('licensed', row['work'], str(row['pdf_page'])).source_id == KELLY
    assert view_of('licensed', 'unknown', str(row['pdf_page'])) is None


@pytest.mark.readings
def test_a_shelf_says_whether_it_was_built_from_the_export_this_app_serves(shelves):
    import hashlib

    from backend.diagnostics import readings

    given, _ = shelves
    served = hashlib.sha256(readings.Readings().index.read_bytes()).hexdigest()
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    given['free'] = a_shelf(export_sha256=None) | {'export_sha256': served}
    assert client.get('/api/shelf').json()['bases'][0]['in_step'] is True
    given['free'] = a_shelf() | {'export_sha256': '0' * 64}
    assert client.get('/api/shelf').json()['bases'][0]['in_step'] is False
    given['free'] = a_shelf()  # a shelf from before the field: nothing to compare, nothing said
    assert client.get('/api/shelf').json()['bases'][0]['in_step'] is None
