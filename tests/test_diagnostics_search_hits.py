"""The search screen's API: the core's own search, built once, each hit linked to the page view that shows its page."""

import pytest
from fastapi.testclient import TestClient

from backend.diagnostics import search_hits
from backend.diagnostics.app import create_app
from backend.search import page_index, search_server

# TestClient's own host, "testserver", is refused like any other name that is not this machine's (app.TRUSTED_HOSTS)
LOCAL = 'http://127.0.0.1'

KELLY = 'carta_conversano_kelly_criterion_2020'
VISION = 'vision reading (claude-sonnet-5-5, page/1, validator page/1.1)'
# Two free pages as the core's search holds them: a page of an exported reading, under the search's own key for its work,
# and an HTML section, which the diagnostics does not show yet. Their words are invented.
READ = page_index.Page('carta-conversano-kelly-2020', '4', 1, 'The Kelly fraction maximises the growth rate of the bankroll.',
                       'corpus/readings/carta-conversano-kelly-2020/p0004.md', pdf='4', section='2 The model',
                       knowledge_base='free', route=VISION, printed='4', reading_key='2b2d48e77b246c95')
SECTION = page_index.Page('wikipedia_trading_set', 's2', 1, 'The Kelly criterion sizes a bet by its edge and its odds.',
                          'https://en.wikipedia.org/w/index.php?title=Kelly_criterion#Definition',
                          section='Kelly criterion > Definition', knowledge_base='free', route='html, parsed by section')


def a_service(*pages):
    works = {page.work: search_server.Work(page.work, f'title of {page.work}', 'free', 'CC BY', page.route) for page in pages}
    return search_server.SearchService({'free': (list(pages), works)})


@pytest.fixture
def built(monkeypatch):
    """The search over the two pages, and every request to build one, by the switch it was built with."""
    calls = []

    def build(public_only):
        calls.append(public_only)
        return a_service(READ, SECTION)

    monkeypatch.setattr(search_hits, 'build_service', build)
    return calls


@pytest.mark.readings
def test_a_hit_on_an_exported_reading_leads_to_its_page_view_and_others_name_their_file(built):
    answer = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/search', params={'q': 'kelly'}).json()
    assert answer['state'] == 'found' and answer['knowledge_bases'] == ['free']
    hits = {hit['work']: hit for hit in answer['hits']}
    assert hits['carta-conversano-kelly-2020']['view'] == {'knowledge_base': 'free', 'source_id': KELLY, 'pdf_page': 4}
    assert hits['carta-conversano-kelly-2020']['page'] == {'label': '4', 'pdf': '4', 'printed': '4'}
    # an HTML section has no page view yet: no link, and the place it comes from instead
    assert hits['wikipedia_trading_set']['view'] is None
    assert hits['wikipedia_trading_set']['where'].endswith('#Definition')


def test_nothing_found_is_an_answer(built):
    answer = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/search', params={'q': 'zebra'}).json()
    assert answer['state'] == 'nothing found' and answer['hits'] == []


@pytest.mark.parametrize('params', [{'q': 'kelly', 'corpus': 'other'}, {'q': 'kelly', 'hits': 0}, {'q': 'kelly', 'hits': search_server.MAX_HITS + 1}])
def test_an_unknown_corpus_and_a_count_out_of_bounds_are_refused(built, params):
    assert TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/search', params=params).status_code == 422


def test_the_search_is_built_once_with_the_apps_own_switch(built):
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    for query in ('kelly', 'growth', 'odds'):
        client.get('/api/search', params={'q': query})
    assert built == [True]


def test_public_only_never_reads_the_licensed_knowledge_base_for_the_search_either(monkeypatch):
    def refuse():
        raise AssertionError('the licensed knowledge base was read for the search')

    monkeypatch.setattr(search_server, 'licensed_pages', refuse)
    monkeypatch.setattr(search_server, 'free_pages', lambda: ([READ], {READ.work: search_server.Work(
        READ.work, 'Kelly', 'free', 'CC BY', VISION)}))
    # the core's own `knowledge_bases`, read in this process so the refusal above reaches it; the app reads it in a process
    # of its own with the same switch
    monkeypatch.setattr(search_hits, 'read_pages', search_server.knowledge_bases)
    answer = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/search', params={'q': 'kelly', 'corpus': 'licensed'}).json()
    assert answer['state'] == 'nothing found' and answer['knowledge_bases'] == ['free']


def pages_by_switch(public_only):
    """Invented pages: the switch they were read with and the process that read them. At module level, so a spawned
    process can import it."""
    import os

    return {'read_with': public_only, 'process': os.getpid()}


def test_the_pages_are_read_in_a_process_of_their_own_with_the_apps_switch(monkeypatch, capsys):
    import os

    read = search_hits.pages_in_a_process(True, read=pages_by_switch)
    assert read['read_with'] is True and read['process'] != os.getpid()

    def no_process(*args, **kwargs):
        raise OSError('no process can be started here')

    # where no process can be started, the pages are read in this one, and it says so
    monkeypatch.setattr(search_hits, 'ProcessPoolExecutor', no_process)
    assert search_hits.pages_in_a_process(False, read=pages_by_switch) == {'read_with': False, 'process': os.getpid()}
    assert 'in this process instead' in capsys.readouterr().err


def test_warming_builds_the_index_once_ahead_of_the_first_search(built):
    search = search_hits.Search(public_only=True)
    search.warm()
    assert search.service() is search.service()
    assert built == [True]
