"""Fill the index database from what the librarian serves today (issue #10, part B): its works and pages exactly as the
librarian builds them, each ranked page's BM25 postings, and every chunk with the vector both Chroma stores already hold,
so nothing is embedded again. A whole import, inside transactions: a reader sees the old index or the new one, never half.

    python -m backend.search.database.index_import          # import both knowledge bases, then run the gate
    python -m backend.search.database.index_import --no-gate

The gate (`index_gate`) compares the database with the in-memory ranking built from the same pages before anything reads
from it. Prints counts and timings only, never page text.
"""

import argparse
import collections
import dataclasses
import json
import sys
import time
from pathlib import Path

import chromadb
import numpy
import psycopg
from pgvector.psycopg import register_vector

from backend.configuration import data_paths
from backend.database.database_url import database_url
from backend.database.migration_runner import MigrationRunner
from backend.ingestion import index_store
from backend.search import page_index

KNOWLEDGE_BASES = ('free', 'licensed')
BATCH = 5000


@dataclasses.dataclass(frozen=True)
class Imported:
    works: int
    pages: int
    ranked: int
    postings: int
    chunks: dict


def chroma_stores() -> dict[str, Path]:
    """Each knowledge base's Chroma folder, where it exists on this machine."""
    stores = {'free': data_paths.INDEX / 'chroma', 'licensed': data_paths.LICENSED_INDEX / 'chroma'}
    return {base: path for base, path in stores.items() if path.exists()}


def served_pages(bases: dict) -> tuple[list[page_index.Page], dict]:
    """The pages and works of every knowledge base as the librarian assembles them (`search_server.knowledge_bases`)."""
    pages, works = [], {}
    for knowledge_base, (base_pages, base_works) in bases.items():
        works.update(base_works)
        pages += [page if page.knowledge_base else dataclasses.replace(page, knowledge_base=knowledge_base)
                  for page in base_pages]
    return pages, works


def write_pages(connection: psycopg.Connection, pages: list[page_index.Page], works: dict) -> tuple[int, int, int]:
    """Works, pages and postings, replacing what was there. A page's id is its place in the librarian's own order, so a
    work's pages come back in that order (its contents are built from them); its ordinal is its number in the in-memory
    ranking, so a tie breaks as there, and -1 for a page outside the ranking, which has no postings."""
    order = pages
    connection.execute('TRUNCATE works, pages, postings')
    with connection.cursor() as cursor:
        with cursor.copy('COPY works (key, knowledge_base, title, licence, route, subject, view_id, edition, year, kept_for, '
                         'pages) FROM STDIN') as copy:
            for work in works.values():
                copy.write_row((work.key, work.knowledge_base, work.title, work.licence, work.route, work.subject,
                                work.view_id, work.edition, work.year, work.kept_for, work.pages))
        postings = 0
        with cursor.copy('COPY pages (id, work, knowledge_base, label, line, line_end, path, pdf, printed, section, route, '
                         'reading_key, searchable, text, index_text, length, ordinal) FROM STDIN') as copy:
            tokens, ranked = {}, 0
            for position, page in enumerate(order):
                words = page_index.tokenize(page.words) if page.searchable else []
                ordinal = ranked if page.searchable else -1
                ranked += page.searchable
                tokens[position + 1] = words
                copy.write_row((position + 1, page.work, page.knowledge_base, page.page, page.line, page.line_end, page.path,
                                page.pdf, page.printed, page.section, page.route or '', page.reading_key, page.searchable,
                                page.text, page.index_text, len(words), ordinal))
        with cursor.copy('COPY postings (term, page_id, tf) FROM STDIN') as copy:
            for page_id, words in tokens.items():
                for term, frequency in collections.Counter(words).items():
                    copy.write_row((term, page_id, frequency))
                    postings += 1
        cursor.execute('UPDATE index_state SET generation = generation + 1, changed_at = now()')  # a running librarian reloads
    return len(works), len(order), postings


def write_chunks(connection: psycopg.Connection, stores: dict[str, Path]) -> dict[str, int]:
    """Every chunk of each Chroma store with its stored vector and the model the store records, replacing what was there."""
    register_vector(connection)
    connection.execute('TRUNCATE chunks')
    counts = {}
    with connection.cursor() as cursor:
        with cursor.copy('COPY chunks (id, knowledge_base, work, text, metadata, model, embedding) FROM STDIN '
                         'WITH (FORMAT BINARY)') as copy:
            copy.set_types(['text', 'text', 'text', 'text', 'jsonb', 'text', 'vector'])
            for base, path in stores.items():
                client = chromadb.PersistentClient(path=str(path),
                                                   settings=chromadb.config.Settings(anonymized_telemetry=False))
                collection = client.get_collection(index_store.COLLECTION)
                model = (collection.metadata or {}).get(index_store.EMBEDDING_MODEL_KEY) or ''
                counts[base] = 0
                for offset in range(0, collection.count(), BATCH):
                    batch = collection.get(include=['embeddings', 'metadatas', 'documents'], limit=BATCH, offset=offset)
                    for chunk_id, vector, metadata, text in zip(batch['ids'], batch['embeddings'], batch['metadatas'],
                                                                 batch['documents']):
                        metadata = dict(metadata or {})
                        copy.write_row((chunk_id, base, metadata.get('source_id') or '', text or '',
                                        json.dumps(metadata, ensure_ascii=False), model,
                                        numpy.asarray(vector, dtype=numpy.float32)))
                        counts[base] += 1
    return counts


def import_index(url: str, bases: dict, stores: dict[str, Path]) -> Imported:
    """Both parts in their own transactions: the pages first, the chunks after; the schema must be current."""
    pending = MigrationRunner(url).status().pending
    if pending:
        raise SystemExit(f'the schema has pending migrations {[m.version for m in pending]}: run '
                         'python -m backend.database.migrate first')
    pages, works = served_pages(bases)
    with psycopg.connect(url) as connection:
        work_count, page_count, postings = write_pages(connection, pages, works)
        connection.commit()
        chunks = write_chunks(connection, stores)
        connection.commit()
        connection.autocommit = True
        connection.execute('ANALYZE works')
        connection.execute('ANALYZE pages')
        connection.execute('ANALYZE postings')
        connection.execute('ANALYZE chunks')
    return Imported(work_count, page_count, sum(page.searchable for page in pages), postings, chunks)


def main(argv: list[str] | None = None) -> int:
    from backend.search import search_server
    from backend.search.database import index_gate

    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    run = parser.add_mutually_exclusive_group()
    run.add_argument('--no-gate', action='store_true', help='import only; skip the comparison with the in-memory ranking')
    run.add_argument('--gate-only', action='store_true', help='compare what the database holds now; import nothing')
    args = parser.parse_args(argv)
    url = database_url()
    started = time.perf_counter()
    bases = search_server.knowledge_bases()
    print(f'pages assembled as the librarian does in {time.perf_counter() - started:.0f} s', flush=True)
    if not args.gate_only:
        started = time.perf_counter()
        imported = import_index(url, bases, chroma_stores())
        print(f'imported in {time.perf_counter() - started:.0f} s: {imported.works} works, {imported.pages} pages '
              f'({imported.ranked} ranked), {imported.postings:,} postings, chunks {imported.chunks}', flush=True)
    if args.no_gate:
        return 0
    report = index_gate.run(url, served_pages(bases)[0], chroma_stores())
    print(json.dumps(report['summary'], indent=1))
    return 0 if report['summary']['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
