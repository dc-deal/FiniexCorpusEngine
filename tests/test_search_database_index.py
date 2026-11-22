"""The index in the database (issue #10, part B): pages and postings written as the librarian serves them rank exactly as
the in-memory port ranks them, filters included, and the stored vectors are found again by the HNSW index of their base."""
from types import SimpleNamespace

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


def work(key: str, knowledge_base: str = 'free') -> SimpleNamespace:
    return SimpleNamespace(key=key, knowledge_base=knowledge_base, title=key.title(), licence='CC BY', route='per page',
                           subject=None, view_id=key, edition=None, year=None, kept_for=None)


PAGES = [page('alpha', '1', 'momentum oscillator overbought oversold'),
         page('alpha', '2', 'momentum momentum trend following'),
         page('beta', '1', 'oscillator divergence momentum', knowledge_base='licensed'),
         page('beta', '2', 'trend channel breakout', knowledge_base='licensed'),
         page('gamma', '1', 'momentum oscillator overbought oversold'),  # the same words as alpha 1: a tie
         page('gamma', '2', 'momentum index page', searchable=False)]
WORKS = {'alpha': work('alpha'), 'beta': work('beta', 'licensed'), 'gamma': work('gamma')}


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
