"""Where the index lives: Chroma for meaning, SQLite for facts.

Both sit under corpus/index/ (git-ignored, derived, rebuilt by `python -m backend.ingestion.build`).

- **Chroma** holds each chunk's embedding, text and metadata. It answers "which chunks are close
  to this question". Cosine distance, as in the course.
- **SQLite** holds what is looked up by key rather than searched by similarity: the sources and
  their fingerprints, the sections, the chunks' text (for the keyword index of phase 5), and one
  record per build run with its token count and cost.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from backend.ingestion.sections import Section
from backend.providers.embedding_route import index_name

COLLECTION = 'corpus'

# How many candidates HNSW keeps while it walks its graph (Chroma's default is 100). Measured
# 2026-09-29 against an exact search over all 7,917 vectors: with 100, 6.2 % of the exact top 10 of
# the evaluation questions were missing, 7 times inside the top 5; with 500, none, at 2.3 ms instead
# of 2.2 ms per query. Questions sit far from every chunk (similarity 0.4-0.6), where the walk gets
# lost more easily than for chunk-like queries (0.1 % missing with 100). docs/phase_03_*.md
SEARCH_EF = 500

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, title TEXT, authors TEXT, shelf TEXT, format TEXT,
    licence TEXT, licence_url TEXT, fingerprint TEXT, indexed_at TEXT,
    sections INTEGER, chunks INTEGER, tokens INTEGER
);
CREATE TABLE IF NOT EXISTS sections (
    id TEXT PRIMARY KEY, source_id TEXT, ordinal INTEGER, heading_path TEXT,
    url TEXT, anchor TEXT, pdf_page_first INTEGER, printed_page_first INTEGER, text TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY, source_id TEXT, section_id TEXT, text TEXT, metadata TEXT
);
CREATE INDEX IF NOT EXISTS chunks_by_source ON chunks(source_id);
CREATE INDEX IF NOT EXISTS sections_by_source ON sections(source_id);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, finished_at TEXT, model TEXT,
    sources_indexed INTEGER, sources_unchanged INTEGER, chunks INTEGER, tokens INTEGER,
    estimated_usd REAL, measured_usd REAL, config TEXT
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    return connection


EMBEDDING_MODEL_KEY = 'embedding_model'


class EmbeddingModelMismatch(RuntimeError):
    """The index was embedded with another model than the one that would embed the queries."""


def check_embedding_model(recorded: str | None, expected: str, embeddings: Embeddings, directory: Path) -> None:
    """Refuse an index whose vectors and the query vectors would come from different models.

    Vectors from two embedding models share no meaning. When both have the same dimension (as
    text-embedding-3-small and ada-002 do, 1536), nothing else notices: the search runs and returns
    nonsense. Different dimensions would at least fail inside Chroma, but only at the first query.

    Raises:
        EmbeddingModelMismatch: When the collection records another model or none, or when the
            embeddings object says it is a different model from the one declared.
    """
    actual = getattr(embeddings, 'model', None)  # OpenAIEmbeddings has it; test fakes do not
    if actual is not None and index_name(actual) != expected:  # OpenAI direct names the same model bare (278.a)
        raise EmbeddingModelMismatch(f'the embeddings object is {actual!r}, but {expected!r} was declared')
    if recorded != expected:
        raise EmbeddingModelMismatch(
            f"the index in {directory} was embedded with {recorded or 'an unrecorded model'}, but this "
            f'code embeds queries with {expected}, and vectors of two models cannot be compared. '
            f'Rebuild the index: delete {directory.parent} and run python -m backend.ingestion.build '
            f'(about 7 minutes, about 0.03 USD).')


def chroma(directory: Path, embeddings: Embeddings, embedding_model: str) -> Chroma:
    """The persistent Chroma collection, checked against the embedding model.

    A new collection records `embedding_model` in its metadata; an existing one must already record
    the same, or opening it fails (`check_embedding_model`). Every caller, the build, the search and
    the evaluation, opens the index here, so no query can reach vectors of another model.

    Telemetry is switched off: chromadb otherwise reports usage to an outside service, which is
    network traffic nobody asked for (and which the offline test guard would refuse). The search
    settings in the metadata apply when the collection is created; an existing collection keeps the
    ones it was created with (measured 2026-09-30: opening with other metadata changes nothing).
    """
    directory.mkdir(parents=True, exist_ok=True)
    store = Chroma(
        collection_name=COLLECTION,
        embedding_function=embeddings,
        persist_directory=str(directory),
        collection_metadata={'hnsw:space': 'cosine', 'hnsw:search_ef': SEARCH_EF,
                             EMBEDDING_MODEL_KEY: embedding_model},
        client_settings=chromadb.config.Settings(anonymized_telemetry=False, is_persistent=True,
                                                 persist_directory=str(directory)),
    )
    check_embedding_model((store._collection.metadata or {}).get(EMBEDDING_MODEL_KEY), embedding_model,
                          embeddings, directory)
    return store


def stored_fingerprint(connection: sqlite3.Connection, source_id: str) -> str | None:
    row = connection.execute('SELECT fingerprint FROM sources WHERE id = ?', (source_id,)).fetchone()
    return row[0] if row else None


# The embedding API refuses a request over 300,000 tokens (found 23 Nov: 500 chunks of a dense OCR scan went over it);
# a call stays well below, by the tokens each chunk records
REQUEST_TOKENS = 250_000


def request_batches(chunks: list[Document], batch_size: int, max_tokens: int = REQUEST_TOKENS) -> list[list[Document]]:
    """The chunks in order, cut into calls of at most `batch_size` chunks and `max_tokens` tokens each."""
    batches, current, tokens = [], [], 0
    for chunk in chunks:
        cost = chunk.metadata.get('tokens') or len(chunk.page_content)
        if current and (len(current) >= batch_size or tokens + cost > max_tokens):
            batches.append(current)
            current, tokens = [], 0
        current.append(chunk)
        tokens += cost
    if current:
        batches.append(current)
    return batches


def replace_source(connection: sqlite3.Connection, store: Chroma, source: dict, fingerprint: str,
                   sections: list[Section], chunks: list[Document], batch_size: int = 500) -> None:
    """Replace everything indexed for one source with its new sections and chunks.

    The old chunks are removed first, so a source that now yields fewer chunks leaves none
    behind. SQLite is committed only after Chroma has taken every chunk, so a failure halfway
    through leaves the old fingerprint, and the next build retries the source.

    Args:
        connection: The SQLite connection.
        store: The Chroma collection.
        source: The catalog entry.
        fingerprint: The source's fingerprint (raw files + splitting configuration).
        sections: Its sections.
        chunks: Its chunks, each with a `chunk_id` in its metadata.
        batch_size: Chunks per Chroma call (each call embeds its batch).
    """
    old = store.get(where={'source_id': source['id']}, include=[])['ids']
    if old:
        store.delete(ids=old)
    for batch in request_batches(chunks, batch_size):
        store.add_documents(batch, ids=[chunk.metadata['chunk_id'] for chunk in batch])

    connection.execute('DELETE FROM chunks WHERE source_id = ?', (source['id'],))
    connection.execute('DELETE FROM sections WHERE source_id = ?', (source['id'],))
    connection.executemany(
        'INSERT INTO sections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [(s.id, s.source_id, s.ordinal, ' > '.join(s.heading_path), s.url, s.anchor,
          s.pages[0][1] if s.pages else None, s.pages[0][2] if s.pages else None, s.text)
         for s in sections])
    connection.executemany(
        'INSERT INTO chunks VALUES (?, ?, ?, ?, ?)',
        [(c.metadata['chunk_id'], source['id'], c.metadata['section_id'], c.page_content,
          json.dumps(c.metadata, ensure_ascii=False)) for c in chunks])
    connection.execute(
        'INSERT OR REPLACE INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (source['id'], source['title'], source['authors'], source['shelf'], source['format'],
         source['licence'], source['licence_url'], fingerprint,
         datetime.now(timezone.utc).isoformat(timespec='seconds'),
         len(sections), len(chunks), sum(c.metadata['tokens'] for c in chunks)))
    connection.commit()


def record_run(connection: sqlite3.Connection, run: dict) -> None:
    connection.execute(
        'INSERT INTO runs (started_at, finished_at, model, sources_indexed, sources_unchanged, '
        'chunks, tokens, estimated_usd, measured_usd, config) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (run['started_at'], run['finished_at'], run['model'], run['sources_indexed'],
         run['sources_unchanged'], run['chunks'], run['tokens'], run['estimated_usd'],
         run.get('measured_usd'), json.dumps(run['config'])))
    connection.commit()
