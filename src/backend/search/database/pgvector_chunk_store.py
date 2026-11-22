"""The semantic search's vectors read from the index database (issue #10, part C2): one knowledge base's chunks in the
`chunks` table, searched by its own HNSW index, answering as LangChain's Chroma store answers the one call the chain makes.

`retrieval.retrieve` asks a store for `similarity_search_with_score(query, k, filter)` and reads (document, cosine
distance) pairs back; `PgvectorChunkStore` answers exactly that, so the chain, its fusion and the relevance floor (calibrated
on 1 - distance) stay as they are. The query is embedded by the same route as Chroma's queries (`embedding_route`), and
the rows must record the model the index was built with, or the store refuses to search (`EmbeddingModelMismatch`).

Built here rather than taken from `langchain-postgres` (0.0.19, read 22 Nov 2026), whose `PGVectorStore` can point at an
existing table. It lost on four measured points: it pins `pgvector<0.4` where this project pins 0.5.1 for its import;
it adds SQLAlchemy, asyncpg and psycopg-pool for one query; it filters on real columns only, not on keys of the
metadata JSON, where `shelf` lives; and it binds the knowledge base as a parameter, which a generic plan cannot match to
the per-base partial HNSW indexes (schema 002), so a search could scan every vector. Here the base is a literal of the
statement, so its own index serves.

    store = PgvectorChunkStore(database_url(), 'licensed', embedding_route.embeddings())
    store.similarity_search_with_score('kelly criterion position sizing', k=10)   # [(Document, distance), ...]
"""

import numpy
import psycopg
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.types.json import Jsonb

from backend.ingestion.index_store import EmbeddingModelMismatch
from backend.providers.embedding_route import INDEX_MODEL, index_name
from backend.search.database.database_index import CONNECT_TIMEOUT_SECONDS

KNOWLEDGE_BASES = ('free', 'licensed')
# How many candidates HNSW keeps while it walks its graph, set for each query; Chroma's is 500 (`index_store.SEARCH_EF`),
# pgvector's default 40. Measured 22 Nov 2026 on 300 stored vectors per base against an exact search, a tie at the tenth
# distance counted as found: free 0.976 / 0.987 / 1.0 recall@10 at 100 / 200 / 400, licensed 0.996 / 0.9997 / 1.0; below
# 400 single queries found none of the exact ten (worst 0.0), likely walks caught by the ~300 duplicate vectors per base
# (up to 21 identical); at 400 none did, at 6.0 and 9.6 ms median.
SEARCH_EF = 400

NEAREST = """
SELECT id, text, metadata, embedding <=> %(query)s AS distance
FROM chunks WHERE knowledge_base = {base}{where}
ORDER BY embedding <=> %(query)s LIMIT %(k)s
"""


class PgvectorChunkStore:
    """One knowledge base's chunks in the database, searched by meaning. One connection, opened on first use and opened
    again once when it was lost (the database restarted), as `DatabaseIndex` keeps its own."""

    def __init__(self, url: str, knowledge_base: str, embeddings: Embeddings, search_ef: int = SEARCH_EF,
                 model: str = INDEX_MODEL):
        if knowledge_base not in KNOWLEDGE_BASES:
            raise ValueError(f'a knowledge base is one of {KNOWLEDGE_BASES}, not {knowledge_base!r}')
        self.knowledge_base, self.embeddings, self.search_ef, self.model = knowledge_base, embeddings, search_ef, model
        self._url = url
        self._connection: psycopg.Connection | None = None
        self._checked = False

    def connection(self) -> psycopg.Connection:
        if self._connection is None or self._connection.closed:
            # never a prepared statement: psycopg prepares a query after five runs, and a cached plan keeps whatever scan it
            # was made with (found 22 Nov: a plan made under an exact search kept scanning every row at ef 400)
            self._connection = psycopg.connect(self._url, autocommit=True, connect_timeout=CONNECT_TIMEOUT_SECONDS,
                                               prepare_threshold=None)
            register_vector(self._connection)
        return self._connection

    def _ask(self, ask):
        try:
            return ask(self.connection())
        except psycopg.OperationalError:
            self._connection = None
            return ask(self.connection())

    def check_model(self) -> None:
        """Refuse rows embedded by another model than the queries' (`index_store.check_embedding_model`'s rule): vectors of
        two models share no meaning, and with the same dimension nothing else would notice."""
        actual = getattr(self.embeddings, 'model', None)  # OpenAIEmbeddings has it; test fakes do not
        if actual is not None and index_name(actual) != self.model:
            raise EmbeddingModelMismatch(f'the embeddings object is {actual!r}, but {self.model!r} was declared')
        recorded = [row[0] for row in self._ask(lambda c: c.execute(
            'SELECT DISTINCT model FROM chunks WHERE knowledge_base = %s', (self.knowledge_base,)).fetchall())]
        if recorded and recorded != [self.model]:
            raise EmbeddingModelMismatch(
                f'the {self.knowledge_base} chunks in the index database were embedded with {", ".join(recorded)}, but this '
                f'code embeds queries with {self.model}: python -m backend.search.database.index_import after a rebuild')
        self._checked = True

    def nearest(self, vector, k: int, filter: dict | None = None) -> list[tuple[str, str, dict, float]]:
        """The k chunks nearest to a query vector: (id, text, metadata, cosine distance), nearest first.

        `filter` is metadata equality ({'shelf': 'architecture'}), as Chroma's flat filter; pgvector then scans its index
        on until k rows pass (`hnsw.iterative_scan`), so a filter does not shrink the result to what ef found."""
        if filter and any(isinstance(value, dict) or key.startswith('$') for key, value in filter.items()):
            raise ValueError(f'only metadata equality is supported, not {filter!r}')
        statement = sql.SQL(NEAREST).format(base=sql.Literal(self.knowledge_base),
                                            where=sql.SQL(' AND metadata @> %(filter)s' if filter else ''))
        values = {'query': numpy.asarray(vector, dtype=numpy.float32), 'k': k, **({'filter': Jsonb(filter)} if filter else {})}

        def ask(connection: psycopg.Connection):
            with connection.transaction():  # the settings hold for this query alone
                connection.execute("SELECT set_config('hnsw.ef_search', %s, true)", (str(self.search_ef),))
                if filter:
                    connection.execute("SELECT set_config('hnsw.iterative_scan', 'strict_order', true)")
                return connection.execute(statement, values).fetchall()

        return [(chunk_id, text, metadata, float(distance)) for chunk_id, text, metadata, distance in self._ask(ask)]

    def similarity_search_with_score(self, query: str, k: int = 4, filter: dict | None = None) -> list[tuple[Document, float]]:
        """LangChain's Chroma call: the query embedded, the k nearest chunks with their cosine distance (1 - similarity)."""
        if not self._checked:
            self.check_model()
        rows = self.nearest(self.embeddings.embed_query(query), k, filter)
        return [(Document(page_content=text, metadata=metadata, id=chunk_id), distance)
                for chunk_id, text, metadata, distance in rows]

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
