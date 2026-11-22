"""The semantic search's vectors in the index database (issue #10, part C2): `PgvectorChunkStore` answers the chain's one
call as the Chroma store answers it on the same chunks and vectors, keeps each knowledge base to its own chunks, filters
on metadata as Chroma's flat filter does, and refuses rows of another embedding model."""
import psycopg
import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from pgvector.psycopg import register_vector
from psycopg.types.json import Jsonb

from backend.database.migration_runner import MigrationRunner
from backend.ingestion import index_store
from backend.ingestion.index_store import EmbeddingModelMismatch
from backend.search import retrieval
from backend.search.database.pgvector_chunk_store import PgvectorChunkStore

MODEL = 'fake/embedding'
EMBEDDINGS = DeterministicFakeEmbedding(size=1536)  # the schema's dimension
CHUNKS = [
    ('free', 'alpha:0001:000', 'alpha', 'architecture', 'retries with exponential backoff and jitter'),
    ('free', 'alpha:0002:000', 'alpha', 'architecture', 'a circuit breaker opens after repeated failures'),
    ('free', 'beta:0001:000', 'beta', 'trading', 'the kelly criterion sizes a position by its edge'),
    ('free', 'beta:0002:000', 'beta', 'trading', 'walk-forward validation keeps the test period unseen'),
    ('free', 'beta:0003:000', 'beta', 'trading', 'a moving average crossover as a trend signal'),
    ('free', 'beta:0004:000', 'beta', 'trading', 'slippage and commissions lower a backtest return'),
    ('licensed', 'gamma:0001:000', 'gamma', 'trading', 'volatility targeting scales positions by risk'),
    ('licensed', 'gamma:0002:000', 'gamma', 'trading', 'carry is the return when prices stay the same'),
]
QUESTIONS = ['how do I size a position?', 'what makes a backtest honest?', 'how should a client retry a call?']


def metadata(chunk_id: str, work: str, shelf: str) -> dict:
    return {'chunk_id': chunk_id, 'source_id': work, 'source_title': work.title(), 'shelf': shelf, 'licence': 'CC BY',
            'pdf_page': int(chunk_id.split(':')[1]), 'route': 'vision reading'}


@pytest.fixture
def url(scratch_database):
    MigrationRunner(scratch_database).apply()
    with psycopg.connect(scratch_database) as connection:
        register_vector(connection)
        for base, chunk_id, work, shelf, text in CHUNKS:
            connection.execute('INSERT INTO chunks (id, knowledge_base, work, text, metadata, model, embedding) '
                               'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                               (chunk_id, base, work, text, Jsonb(metadata(chunk_id, work, shelf)), MODEL,
                                EMBEDDINGS.embed_query(text)))
        connection.commit()
    return scratch_database


def chroma_of(tmp_path, base: str):
    store = index_store.chroma(tmp_path / base, EMBEDDINGS, MODEL)
    rows = [row for row in CHUNKS if row[0] == base]
    store.add_documents([Document(page_content=text, metadata=metadata(chunk_id, work, shelf))
                         for _, chunk_id, work, shelf, text in rows], ids=[row[1] for row in rows])
    return store


@pytest.mark.database
@pytest.mark.parametrize('question', QUESTIONS)
@pytest.mark.parametrize('shelf', [None, 'architecture'])
def test_it_answers_the_chain_s_call_as_chroma_does_on_the_same_vectors(url, tmp_path, question, shelf):
    filters = {'shelf': shelf} if shelf else None
    chroma = retrieval.retrieve(question, k=4, filters=filters, store=chroma_of(tmp_path, 'free'))
    database = retrieval.retrieve(question, k=4, filters=filters, store=PgvectorChunkStore(url, 'free', EMBEDDINGS, model=MODEL))
    assert [hit['chunk_id'] for hit in database] == [hit['chunk_id'] for hit in chroma]
    assert [hit['text'] for hit in database] == [hit['text'] for hit in chroma]
    assert [hit['citation'] for hit in database] == [hit['citation'] for hit in chroma]
    assert all(abs(a['similarity'] - b['similarity']) <= 1e-5 for a, b in zip(database, chroma))


@pytest.mark.database
def test_each_knowledge_base_finds_its_own_chunks_alone(url):
    for base in ('free', 'licensed'):
        found = PgvectorChunkStore(url, base, EMBEDDINGS, model=MODEL).similarity_search_with_score('position sizing', k=20)
        assert {document.id for document, _ in found} == {row[1] for row in CHUNKS if row[0] == base}


@pytest.mark.database
def test_a_filter_returns_every_match_however_far_it_lies(url):
    found = PgvectorChunkStore(url, 'free', EMBEDDINGS, search_ef=1, model=MODEL).similarity_search_with_score(
        'kelly criterion', k=5, filter={'shelf': 'architecture'})
    assert sorted(document.id for document, _ in found) == ['alpha:0001:000', 'alpha:0002:000']


@pytest.mark.database
def test_rows_of_another_embedding_model_are_refused(url):
    with pytest.raises(EmbeddingModelMismatch, match='free chunks'):
        PgvectorChunkStore(url, 'free', EMBEDDINGS, model='other/model').similarity_search_with_score('anything')


def test_only_a_known_base_and_flat_equality_are_accepted():
    with pytest.raises(ValueError, match='knowledge base'):
        PgvectorChunkStore('postgresql://nowhere/none', 'shared', EMBEDDINGS)
    store = PgvectorChunkStore('postgresql://nowhere/none', 'free', EMBEDDINGS)
    with pytest.raises(ValueError, match='equality'):
        store.nearest([0.0] * 1536, 3, {'shelf': {'$in': ['a', 'b']}})
