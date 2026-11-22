import chromadb
import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding

from backend.ingestion import index_store
from backend.ingestion.sections import Section

MODEL = 'fake/embedding'

SOURCE = {'id': 'book', 'title': 'A Book', 'authors': 'A. Author', 'shelf': 'trading_finance',
          'format': 'pdf', 'licence': 'CC BY 4.0', 'licence_url': 'https://example.org/licence'}


def chunk(n: int) -> Document:
    return Document(page_content=f'chunk text {n}', metadata={
        'chunk_id': f'book:0000:{n:03d}', 'section_id': 'book:0000', 'source_id': 'book', 'tokens': 3})


def stores(tmp_path):
    connection = index_store.connect(tmp_path / 'knowledge.sqlite3')
    store = index_store.chroma(tmp_path / 'chroma', DeterministicFakeEmbedding(size=8), MODEL)
    return connection, store


def test_replace_source_writes_both_stores_and_records_the_fingerprint(tmp_path):
    connection, store = stores(tmp_path)
    section = Section('book', 0, ['Chapter'], 'section text', pages=[(0, 5, 3)])
    index_store.replace_source(connection, store, SOURCE, 'fp1', [section], [chunk(0), chunk(1)])
    assert index_store.stored_fingerprint(connection, 'book') == 'fp1'
    assert sorted(store.get(where={'source_id': 'book'})['ids']) == ['book:0000:000', 'book:0000:001']
    assert connection.execute('SELECT count(*) FROM chunks').fetchone()[0] == 2
    assert connection.execute('SELECT pdf_page_first, printed_page_first FROM sections').fetchone() == (5, 3)


def test_re_indexing_a_source_leaves_no_old_chunk_behind(tmp_path):
    connection, store = stores(tmp_path)
    section = Section('book', 0, ['Chapter'], 'text')
    index_store.replace_source(connection, store, SOURCE, 'fp1', [section], [chunk(0), chunk(1), chunk(2)])
    index_store.replace_source(connection, store, SOURCE, 'fp2', [section], [chunk(0)])
    assert store.get(where={'source_id': 'book'})['ids'] == ['book:0000:000']
    assert connection.execute('SELECT count(*) FROM chunks').fetchone()[0] == 1
    assert index_store.stored_fingerprint(connection, 'book') == 'fp2'


def test_a_new_collection_searches_by_cosine_with_the_measured_search_depth(tmp_path):
    # Chroma's default of 100 candidates missed 6.2 % of the exact top 10 for real questions.
    _, store = stores(tmp_path)
    configuration = store._collection.configuration_json['hnsw']
    assert configuration['space'] == 'cosine'
    assert configuration['ef_search'] == index_store.SEARCH_EF == 500


def test_a_new_collection_records_its_embedding_model(tmp_path):
    _, store = stores(tmp_path)
    assert store._collection.metadata[index_store.EMBEDDING_MODEL_KEY] == MODEL


def test_an_index_of_another_embedding_model_refuses_to_open(tmp_path):
    stores(tmp_path)
    with pytest.raises(index_store.EmbeddingModelMismatch, match='embedded with fake/embedding'):
        index_store.chroma(tmp_path / 'chroma', DeterministicFakeEmbedding(size=8), 'other/model')


def test_an_index_that_records_no_model_refuses_to_open(tmp_path):
    # An index built before the model was recorded: it cannot be trusted either.
    client = chromadb.PersistentClient(path=str(tmp_path / 'chroma'),
                                       settings=chromadb.config.Settings(anonymized_telemetry=False))
    client.create_collection(index_store.COLLECTION, metadata={'hnsw:space': 'cosine'})
    with pytest.raises(index_store.EmbeddingModelMismatch, match='an unrecorded model'):
        index_store.chroma(tmp_path / 'chroma', DeterministicFakeEmbedding(size=8), MODEL)


def test_an_embeddings_object_of_another_model_than_declared_is_refused(tmp_path):
    class Named(DeterministicFakeEmbedding):
        model: str = 'other/model'

    with pytest.raises(index_store.EmbeddingModelMismatch, match="'other/model'"):
        index_store.chroma(tmp_path / 'chroma', Named(size=8), MODEL)


@pytest.mark.corpus
def test_the_built_index_records_the_model_the_code_embeds_queries_with():
    from backend.providers import openrouter_client
    from backend.search import retrieval
    if not retrieval.CHROMA_DIRECTORY.exists():
        pytest.skip('no index yet - run python -m backend.ingestion.build')
    client = chromadb.PersistentClient(path=str(retrieval.CHROMA_DIRECTORY),
                                       settings=chromadb.config.Settings(anonymized_telemetry=False))
    metadata = client.get_collection(index_store.COLLECTION).metadata
    assert metadata[index_store.EMBEDDING_MODEL_KEY] == openrouter_client.EMBEDDING_MODEL


def test_a_similarity_search_runs_offline_on_the_stored_chunks(tmp_path):
    connection, store = stores(tmp_path)
    index_store.replace_source(connection, store, SOURCE, 'fp', [Section('book', 0, ['C'], 't')],
                               [chunk(0), chunk(1)])
    hits = store.similarity_search('chunk text 1', k=1)
    assert hits[0].metadata['source_id'] == 'book'


def test_a_call_never_carries_more_tokens_than_the_api_takes():
    # found 23 Nov: 500 chunks of a dense OCR scan went over the API's 300,000 tokens in one request
    chunks = [Document(page_content='x', metadata={'chunk_id': f'c{n}', 'tokens': 700}) for n in range(1000)]
    batches = index_store.request_batches(chunks, batch_size=500, max_tokens=250_000)
    assert all(sum(chunk.metadata['tokens'] for chunk in batch) <= 250_000 for batch in batches)
    assert [chunk.metadata['chunk_id'] for batch in batches for chunk in batch] == [f'c{n}' for n in range(1000)]
    assert max(len(batch) for batch in batches) == 357


def test_light_chunks_are_still_cut_by_their_number():
    chunks = [Document(page_content='x', metadata={'chunk_id': f'c{n}', 'tokens': 10}) for n in range(1200)]
    assert [len(batch) for batch in index_store.request_batches(chunks, batch_size=500)] == [500, 500, 200]
