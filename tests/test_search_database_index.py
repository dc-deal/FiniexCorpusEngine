"""The index in the database (issue #10, part B): pages and postings written as the librarian serves them rank exactly as
the in-memory port ranks them, filters included, and the stored vectors are found again by the HNSW index of their base."""
import numpy
import psycopg
import pytest
from pgvector.psycopg import register_vector

from backend.database.migration_runner import MigrationRunner
from backend.search import page_index
from backend.search.database import index_import, keyword_sql

FILLER = ' '.join(['plain words about a market and its prices'] * 30)


def page(work: str, label: str, text: str, knowledge_base: str = 'free', searchable: bool = True) -> page_index.Page:
    return page_index.Page(work=work, page=label, line=1, text=f'{text} {FILLER}', path=f'{work}.md', pdf=label,
                           knowledge_base=knowledge_base, route='vision reading', searchable=searchable)


def work(key: str, knowledge_base: str = 'free', language: str = 'en'):
    from backend.search.search_server import Work

    ranked = sum(1 for p in PAGES if p.work == key and p.searchable)
    return Work(key, key.title(), knowledge_base, 'CC BY', 'per page', ranked, subject=f'what {key} is for', view_id=key,
                language=language)


PAGES = [page('alpha', '1', 'momentum oscillator overbought oversold'),
         page('alpha', '2', 'momentum momentum trend following'),
         page('beta', '1', 'oscillator divergence momentum', knowledge_base='licensed'),
         page('beta', '2', 'trend channel breakout', knowledge_base='licensed'),
         page('gamma', '1', 'momentum oscillator overbought oversold'),  # the same words as alpha 1: a tie
         page('gamma', '2', 'momentum index page', searchable=False)]
WORKS = {'alpha': work('alpha'), 'beta': work('beta', 'licensed'), 'gamma': work('gamma', language='de')}  # #11: carried
WORKS['gamma'].kept_because = 'the other edition has its formulas as text'  # #15: carried too


@pytest.fixture
def index(scratch_database):
    MigrationRunner(scratch_database).apply()
    with psycopg.connect(scratch_database) as connection:
        index_import.write_pages(connection, PAGES, WORKS)
        connection.commit()
        yield connection


def port_ranking(query: str, accept=None) -> list[tuple[str, str]]:
    ranked = page_index.PageIndex([p for p in PAGES if p.searchable])
    return [(p.work, p.page) for _, p in ranked.search(query, 6, accept)]


def database_ranking(connection, query: str, **filters) -> list[tuple[str, str]]:
    labels = {row[0]: (row[1], row[2]) for row in connection.execute('SELECT id, work, label FROM pages')}
    return [labels[page_id] for page_id, _ in keyword_sql.ranked(connection, query, 6, **filters)]


@pytest.mark.database
@pytest.mark.parametrize('query', ['momentum oscillator', 'momentum momentum', 'trend', 'divergence oversold', 'nothing'])
def test_the_database_ranks_as_the_in_memory_port_ranks_ties_included(index, query):
    assert database_ranking(index, query) == port_ranking(query)


@pytest.mark.database
def test_a_filter_ranks_on_the_whole_index_as_the_port_does(index):
    assert database_ranking(index, 'momentum', knowledge_base='licensed') == \
        port_ranking('momentum', lambda p: p.knowledge_base == 'licensed')
    assert database_ranking(index, 'momentum', work='alpha') == port_ranking('momentum', lambda p: p.work == 'alpha')


@pytest.mark.database
def test_a_page_outside_the_ranking_is_kept_whole_but_never_ranked(index):
    assert index.execute("SELECT searchable, length FROM pages WHERE work = 'gamma' AND label = '2'").fetchone() == (False, 0)
    assert ('gamma', '2') not in database_ranking(index, 'index page')


@pytest.mark.database
def test_a_nul_in_a_text_layer_is_dropped_not_refused(scratch_database):
    """PostgreSQL's text refuses NUL; a text layer may hold one (a paper's did, 22 Nov), so the import drops it."""
    MigrationRunner(scratch_database).apply()
    pages = [page('alpha', '1', 'momentum\x00 oscillator'), page('alpha', '2', 'trend')]
    with psycopg.connect(scratch_database) as connection:
        index_import.write_pages(connection, pages, {'alpha': work('alpha')})
        connection.commit()
        stored = connection.execute("SELECT text FROM pages WHERE label = '1'").fetchone()[0]
    assert '\x00' not in stored and stored.startswith('momentum oscillator')
    assert index_import.no_nul({'a': ['x\x00y'], 'b': 3}) == {'a': ['xy'], 'b': 3}


@pytest.mark.database
def test_one_page_written_again_is_seen_by_the_next_query(index):
    page_id = index.execute("SELECT id FROM pages WHERE work = 'beta' AND label = '2'").fetchone()[0]
    words = page_index.tokenize('a fresh zzmarker word')
    index.execute('DELETE FROM postings WHERE page_id = %s', (page_id,))
    index.execute('UPDATE pages SET text = %s, length = %s WHERE id = %s', ('a fresh zzmarker word', len(words), page_id))
    for term in dict.fromkeys(words):
        index.execute('INSERT INTO postings (term, page_id, tf) VALUES (%s, %s, %s)', (term, page_id, words.count(term)))
    assert database_ranking(index, 'zzmarker') == [('beta', '2')]


@pytest.mark.database
def test_stored_vectors_are_found_again_by_their_base_s_index(index, tmp_path):
    import chromadb

    from backend.ingestion import index_store

    vectors = numpy.random.default_rng(7).normal(size=(6, 1536)).astype(numpy.float32)
    stores = {}
    for base, rows in (('free', range(0, 3)), ('licensed', range(3, 6))):
        client = chromadb.PersistentClient(path=str(tmp_path / base), settings=chromadb.config.Settings(anonymized_telemetry=False))
        collection = client.create_collection(index_store.COLLECTION, metadata={index_store.EMBEDDING_MODEL_KEY: 'model-x'})
        collection.add(ids=[f'{base}:{i}' for i in rows], embeddings=[vectors[i].tolist() for i in rows],
                       documents=[f'chunk {i}' for i in rows], metadatas=[{'source_id': base} for _ in rows])
        stores[base] = tmp_path / base
    assert index_import.write_chunks(index, stores) == {'free': 3, 'licensed': 3}
    register_vector(index)
    nearest = index.execute("SELECT id, model FROM chunks WHERE knowledge_base = 'licensed' ORDER BY embedding <=> %s LIMIT 1",
                            (vectors[4],)).fetchone()
    assert nearest == ('licensed:4', 'model-x')
    # the metadata is stored as an object, so SQL reaches its keys (a dumped string was stored as a JSON string)
    assert index.execute("SELECT jsonb_typeof(metadata), metadata->>'source_id' FROM chunks WHERE id = 'free:1'").fetchone() == \
        ('object', 'free')


def services(url: str):
    """The same pages served twice: assembled in memory, as from files, and loaded from the database."""
    from backend.search.search_server import SearchService

    by_base = {}
    for base in ('free', 'licensed'):
        by_base[base] = ([p for p in PAGES if p.knowledge_base == base],
                         {key: w for key, w in WORKS.items() if w.knowledge_base == base})
    return SearchService(by_base, view_url=None), SearchService.from_database(url, view_url=None)


@pytest.mark.database
def test_the_service_read_from_the_database_answers_as_the_one_built_from_files(index, scratch_database):
    memory, database = services(scratch_database)
    for query, options in (('momentum oscillator', {}), ('momentum', {'corpus': 'licensed'}),
                           ('momentum', {'work': 'alpha'}), ('trend', {'hits': 2}), ('nothing here', {})):
        assert database.search(query, **options) == memory.search(query, **options), (query, options)
    assert database.search_works('momentum oscillator') == memory.search_works('momentum oscillator')
    assert database.open_page('beta', '1') == memory.open_page('beta', '1')
    assert database.open_page('gamma', '2') == memory.open_page('gamma', '2')  # outside the ranking, still opens
    assert database.list_works() == memory.list_works()


@pytest.mark.database
def test_the_service_read_from_the_database_searches_its_vectors_there_too(index, scratch_database, monkeypatch):
    """One switch (C2, 6.a): a librarian read from the database gives the semantic search a store per base over the
    `chunks` table; one built from files keeps the Chroma stores."""
    from backend.search import retrieval, semantic_search
    from backend.search.database.pgvector_chunk_store import PgvectorChunkStore

    built = []

    class Recorder:
        def __init__(self, sources, **options):
            built.append(options)

        def search(self, question, hits, **options):
            return {'state': 'nothing found', 'hits': []}

    monkeypatch.setattr(semantic_search, 'SemanticSearch', Recorder)
    monkeypatch.setattr(retrieval, 'licensed_index_built', lambda: True)
    monkeypatch.setattr('backend.providers.embedding_route.embeddings', lambda: object())
    memory, database = services(scratch_database)
    memory.semantic_search('anything', hits=3)
    database.semantic_search('anything', hits=3)
    assert 'store' not in built[0] and 'private_store' not in built[0]
    stores = [built[1]['store'], built[1]['private_store']]
    assert all(isinstance(store, PgvectorChunkStore) for store in stores)
    assert [store.knowledge_base for store in stores] == ['free', 'licensed']


@pytest.mark.database
def test_a_change_written_to_the_database_is_served_on_the_next_call_without_a_restart(index, scratch_database):
    from backend.search.search_server import SearchService

    service = SearchService.from_database(scratch_database, view_url=None)
    assert service.refresh() is False and service.search('zzfresh')['state'] == 'nothing found'
    changed = [page('alpha', '1', 'a zzfresh word')] + PAGES[1:]
    index_import.write_pages(index, changed, WORKS)
    index.commit()
    assert service.refresh() is True
    assert [hit['work'] for hit in service.search('zzfresh')['hits']] == ['alpha']


@pytest.mark.database
def test_a_database_that_cannot_serve_never_stops_the_librarian(monkeypatch, capsys):
    from backend.search import search_server

    monkeypatch.setattr('backend.database.database_url.database_url', lambda: 'postgresql://nobody:x@127.0.0.1:1/none')
    monkeypatch.setattr(search_server, 'knowledge_bases', lambda public_only=False: {'free': ([PAGES[0]], {'alpha': WORKS['alpha']})})
    service = search_server.build_service(False, 'database', view_url=None)
    assert service.database_url is None and list(service.works) == ['alpha']
    assert 'cannot serve' in capsys.readouterr().err
    # a caller's own reader serves the fallback (the view reads its pages in a process of its own)
    asked = []
    own = search_server.build_service(False, 'database', read=lambda public_only: asked.append(public_only) or
                                      {'free': ([PAGES[4]], {'gamma': WORKS['gamma']})}, view_url=None)
    assert asked == [False] and list(own.works) == ['gamma']


@pytest.mark.database
def test_one_work_written_again_leaves_the_others_untouched_and_is_served_at_once(index, scratch_database):
    from backend.search.search_server import SearchService

    service = SearchService.from_database(scratch_database, view_url=None)
    before = index.execute("SELECT id, text FROM pages WHERE work <> 'alpha' ORDER BY id").fetchall()
    changed = [page('alpha', '1', 'a zzfresh word'), page('alpha', '2', 'momentum momentum trend following')]
    assert index_import.write_works(index, {'alpha'}, changed, WORKS) == (1, 2)
    index.commit()
    assert index.execute("SELECT id, text FROM pages WHERE work <> 'alpha' ORDER BY id").fetchall() == before
    assert service.refresh() is True
    assert [hit['work'] for hit in service.search('zzfresh')['hits']] == ['alpha']
    assert service.search('overbought')['hits'][0]['work'] == 'gamma'  # alpha 1 no longer holds it


@pytest.mark.database
def test_a_work_named_but_no_longer_served_loses_its_rows(index):
    assert index_import.write_works(index, {'beta'}, [], {}) == (0, 0)
    index.commit()
    assert index.execute("SELECT count(*) FROM pages WHERE work = 'beta'").fetchone() == (0,)
    assert index.execute("SELECT count(*) FROM works WHERE key = 'beta'").fetchone() == (0,)
    assert index.execute('SELECT count(*) FROM postings p LEFT JOIN pages g ON g.id = p.page_id WHERE g.id IS NULL'
                         ).fetchone() == (0,)


@pytest.mark.database
def test_every_work_keeps_its_language_through_the_database(index, scratch_database):
    # #11: the database gives back what the catalog said, so a client is told the language of what it quotes
    memory, database = services(scratch_database)
    assert {work['work']: work['language'] for work in database.list_works()} == {'alpha': 'en', 'beta': 'en', 'gamma': 'de'}
    assert database.search('momentum oscillator')['hits'][0]['language'] in ('en', 'de')
    assert database.open_page('gamma', '1')['language'] == 'de'
    assert database.works['gamma'].kept_because == 'the other edition has its formulas as text'


def test_an_import_refuses_a_work_without_its_language():
    from backend.search.search_server import Work

    nameless = Work('x', 'X', 'free', 'CC BY', 'per page', 1)
    with pytest.raises(SystemExit, match='no language for'):
        index_import.served_pages({'free': ([page('x', '1', 'momentum')], {'x': nameless})})


def test_an_import_warms_the_running_librarian_and_never_fails_for_it(monkeypatch, capsys):
    # a client's fourth check, 24 Nov: the first semantic_search after the night's imports took 9.6 s
    from backend.chat import mcp_client

    calls = []

    class Client:
        def __init__(self, server, client_name):
            calls.append(('start', client_name))

        def call(self, tool, arguments):
            calls.append((tool, arguments))

    monkeypatch.setattr(mcp_client, 'SearchClient', Client)
    index_import.warm_up(server=object())
    assert [call[0] for call in calls] == ['start', 'works', 'search', 'semantic_search']
    assert 'librarian warmed' in capsys.readouterr().out

    def down(server, client_name):
        raise ConnectionError('no librarian')

    monkeypatch.setattr(mcp_client, 'SearchClient', down)
    index_import.warm_up(server=object())  # no error: the librarian loads the generation on its next call anyway
    assert 'warm-up skipped: ConnectionError' in capsys.readouterr().out
