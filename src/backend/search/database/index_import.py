"""Fill the index database from what the librarian serves today (issue #10, part B): its works and pages exactly as the
librarian builds them, each ranked page's BM25 postings, and every chunk with the vector both Chroma stores already hold,
so nothing is embedded again. A whole import, inside transactions: a reader sees the old index or the new one, never half.

    python -m backend.search.database.index_import          # import both knowledge bases, then run the gate
    python -m backend.search.database.index_import --no-gate
    python -m backend.search.database.index_import --works KEY …   # those works alone, in seconds

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


def copy_rows(connection: psycopg.Connection, pages: list[page_index.Page], works: dict, first_id: int,
              first_ordinal: int) -> int:
    """Works, pages and their postings copied in: page ids from `first_id` in the librarian's own order, so a work's pages
    come back in that order (its contents are built from them); ordinals from `first_ordinal` for the ranked pages, so a
    tie breaks as the in-memory ranking breaks it, and -1 for a page outside the ranking, which has no postings. The
    index's generation is raised, so a running librarian loads it again. Returns the count of postings."""
    with connection.cursor() as cursor:
        with cursor.copy('COPY works (key, knowledge_base, title, licence, route, subject, view_id, edition, year, kept_for, '
                         'pages) FROM STDIN') as copy:
            for work in works.values():
                copy.write_row((work.key, work.knowledge_base, work.title, work.licence, work.route, work.subject,
                                work.view_id, work.edition, work.year, work.kept_for, work.pages))
        postings = 0
        with cursor.copy('COPY pages (id, work, knowledge_base, label, line, line_end, path, pdf, printed, section, route, '
                         'reading_key, searchable, text, index_text, length, ordinal) FROM STDIN') as copy:
            tokens, ranked = {}, first_ordinal
            for position, page in enumerate(pages, start=first_id):
                words = page_index.tokenize(page.words) if page.searchable else []
                ordinal = ranked if page.searchable else -1
                ranked += page.searchable
                tokens[position] = words
                copy.write_row((position, page.work, page.knowledge_base, page.page, page.line, page.line_end, page.path,
                                page.pdf, page.printed, page.section, page.route or '', page.reading_key, page.searchable,
                                page.text, page.index_text, len(words), ordinal))
        with cursor.copy('COPY postings (term, page_id, tf) FROM STDIN') as copy:
            for page_id, words in tokens.items():
                for term, frequency in collections.Counter(words).items():
                    copy.write_row((term, page_id, frequency))
                    postings += 1
        cursor.execute('UPDATE index_state SET generation = generation + 1, changed_at = now()')  # a running librarian reloads
    return postings


def write_pages(connection: psycopg.Connection, pages: list[page_index.Page], works: dict) -> tuple[int, int, int]:
    """Every work, page and posting, replacing what was there: a whole import."""
    connection.execute('TRUNCATE works, pages, postings')
    return len(works), len(pages), copy_rows(connection, pages, works, 1, 0)


def write_works(connection: psycopg.Connection, keys: set[str], pages: list[page_index.Page], works: dict) -> tuple[int, int]:
    """The rows of the named works replaced, the rest untouched (issue #10, part D: a verdict writes its own work). Every
    key named loses its rows; those `works` holds come back with `pages`, after the highest id and ordinal, so their ties
    may break otherwise than in a whole import, which restores the order. Returns the works written and their pages."""
    keys = set(keys)
    connection.execute('DELETE FROM works WHERE key = ANY(%s)', (sorted(keys),))  # pages and postings go with them
    first_id, first_ordinal = connection.execute('SELECT coalesce(max(id), 0) + 1, coalesce(max(ordinal), -1) + 1 FROM pages'
                                                 ).fetchone()
    kept = {key: work for key, work in works.items() if key in keys}
    own = [page for page in pages if page.work in kept]
    copy_rows(connection, own, kept, first_id, first_ordinal)
    return len(kept), len(own)


def write_chunks(connection: psycopg.Connection, stores: dict[str, Path], keys: set[str] | None = None) -> dict[str, int]:
    """Every chunk of each Chroma store with its stored vector and the model the store records, replacing what was there;
    with `keys`, the chunks of those works alone (issue #10, part D)."""
    register_vector(connection)
    if keys is None:
        connection.execute('TRUNCATE chunks')
    else:
        connection.execute('DELETE FROM chunks WHERE work = ANY(%s)', (sorted(keys),))
    where = None if keys is None else {'source_id': {'$in': sorted(keys)}}
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
                    batch = collection.get(include=['embeddings', 'metadatas', 'documents'], limit=BATCH, offset=offset,
                                           where=where)
                    if not batch['ids']:
                        break
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


def import_works(url: str, keys: set[str], stores: dict[str, Path]) -> tuple[int, int, dict]:
    """The named works written again from what the librarian would serve of them now, pages and chunks, the rest of the
    index untouched (issue #10, part D); only those works are assembled, so it takes seconds, not a whole import's minutes.
    Returns the works written, their pages and their chunks by knowledge base."""
    from backend.search import search_server

    pages, works = served_pages({'free': search_server.free_pages(keys), 'licensed': search_server.licensed_pages(keys)})
    with psycopg.connect(url) as connection:
        work_count, page_count = write_works(connection, keys, pages, works)
        connection.commit()
        chunks = write_chunks(connection, stores, keys)
        connection.commit()
    return work_count, page_count, chunks


def main(argv: list[str] | None = None) -> int:
    from backend.search import search_server
    from backend.search.database import index_gate

    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    run = parser.add_mutually_exclusive_group()
    run.add_argument('--no-gate', action='store_true', help='import only; skip the comparison with the in-memory ranking')
    run.add_argument('--gate-only', action='store_true', help='compare what the database holds now; import nothing')
    run.add_argument('--works', nargs='+', metavar='KEY',
                     help='write these works again, pages and chunks, and leave the rest of the index as it is')
    args = parser.parse_args(argv)
    url = database_url()
    if args.works:
        started = time.perf_counter()
        works, pages, chunks = import_works(url, set(args.works), chroma_stores())
        print(f'{works} of {len(args.works)} works written again in {time.perf_counter() - started:.1f} s: {pages} pages, '
              f'chunks {chunks}')
        return 0
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
