"""The keyword index the diagnostics builds for what it says of a page (V2.a): the core's own search, built once with the app's
own switch, and the page view of a page it names. A search a person runs goes to the running librarian (L1.a)."""

import pytest

from backend.diagnostics import readings, search_hits
from backend.diagnostics.search_hits import PageLink
from backend.search import page_index, search_server

KELLY = 'carta_conversano_kelly_criterion_2020'
VISION = 'vision reading (claude-sonnet-5-5, page/1, validator page/1.1)'
# A free page as the core's search holds it, under the search's own key for its work. Its words are invented.
READ = page_index.Page('carta-conversano-kelly-2020', '4', 1, 'The Kelly fraction maximises the growth rate of the bankroll.',
                       'corpus/readings/carta-conversano-kelly-2020/p0004.md', pdf='4', section='2 The model',
                       knowledge_base='free', route=VISION, printed='4', reading_key='2b2d48e77b246c95')


@pytest.fixture
def built(monkeypatch):
    """Every request to build the search, by the switch it was built with."""
    calls = []

    def build(public_only):
        calls.append(public_only)
        return search_server.SearchService({'free': ([READ], {READ.work: search_server.Work(READ.work, 'Kelly', 'free', 'CC BY', VISION)})})

    monkeypatch.setattr(search_hits, 'build_service', build)
    return calls


@pytest.mark.readings
def test_a_page_of_an_exported_reading_leads_to_its_page_view_and_any_other_to_none():
    view_of = search_hits.page_links(readings.knowledge_bases(public_only=True))
    assert view_of('free', 'carta-conversano-kelly-2020', '4') == PageLink(knowledge_base='free', source_id=KELLY, pdf_page=4)
    # an HTML section, or a page no reading covers: no page view
    assert view_of('free', 'wikipedia_trading_set', None) is None
    assert view_of('free', 'carta-conversano-kelly-2020', '99999') is None


def test_public_only_never_reads_the_licensed_knowledge_base_for_the_search_either(monkeypatch):
    def refuse():
        raise AssertionError('the licensed knowledge base was read for the search')

    monkeypatch.setattr(search_server, 'licensed_pages', refuse)
    monkeypatch.setattr(search_server, 'free_pages', lambda: ([READ], {READ.work: search_server.Work(
        READ.work, 'Kelly', 'free', 'CC BY', VISION)}))
    # the core's own `knowledge_bases`, read in this process so the refusal above reaches it; the app reads it in a process
    # of its own with the same switch
    monkeypatch.setattr(search_hits, 'read_pages', search_server.knowledge_bases)
    assert list(search_hits.Search(public_only=True).service().bases) == ['free']


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


def test_the_search_is_the_core_s_build_with_the_view_s_own_reader(monkeypatch):
    # issue #10 part E: the database where the configuration says so, else files read in a process of their own
    asked = []
    monkeypatch.setattr(search_server, 'build_service',
                        lambda public_only, read=None: asked.append((public_only, read)) or 'a service')
    assert search_hits.Search(public_only=True).service() == 'a service'
    assert asked == [(True, search_hits.read_pages)]


def test_a_search_read_from_the_database_asks_for_a_written_index_at_most_every_few_seconds(capsys):
    from types import SimpleNamespace

    now = [100.0]
    asked = []
    search = search_hits.Search(public_only=False, clock=lambda: now[0])
    search._service = SimpleNamespace(database_url='postgresql://invented', refresh=lambda: asked.append(now[0]))
    search.ready()
    search.ready()
    assert asked == [100.0]  # once within the few seconds
    now[0] += search_hits.REFRESH_SECONDS
    search.ready()
    assert asked == [100.0, 100.0 + search_hits.REFRESH_SECONDS]
    # a database that cannot be asked: the index loaded last serves on, said once
    def gone():
        raise ConnectionError('the database is down')

    search._service.refresh = gone
    for _ in range(2):
        now[0] += search_hits.REFRESH_SECONDS
        assert search.ready() is search._service
    assert capsys.readouterr().err.count('keeps the index it loaded last') == 1
    # one built from files is never asked
    files = search_hits.Search(public_only=True, clock=lambda: now[0])
    files._service = SimpleNamespace(database_url=None, refresh=lambda: asked.append('files'))
    files.ready()
    assert 'files' not in asked


def test_warming_builds_the_index_once_with_the_apps_own_switch(built):
    search = search_hits.Search(public_only=True)
    search.warm()
    assert search.service() is search.service()
    assert built == [True]
