"""The gate before the switch (issue #10, part B): the index database must rank as the in-memory index ranks, on the same
pages, before the librarian reads from it.

- **Keyword:** every coverage-gate probe (one per work, `coverage_gate.build_probe`) asked of both; the top six pages and
  their scores must agree, and so must the gate's own result (works reached in the top six, works at rank 1).
- **Semantic:** sample stored vectors of each knowledge base as queries; the database's HNSW top ten against an exact
  search over the same base, recall@10 at least `MIN_RECALL`, at the `ef_search` the semantic search queries with. A
  found chunk counts when its distance is within the exact tenth's: a base holds about 300 duplicate vectors (up to 21
  identical), and among equal distances the exact ten are an arbitrary pick, which counting ids scored as misses. The
  samples are stored vectors, which flatters recall a little, as the prototype said.

A report goes to `_work/database/` with each probe's work and the pages that differed (keys and labels, never text).
"""

import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import chromadb
import numpy
import psycopg
from pgvector.psycopg import register_vector

from backend.configuration import data_paths
from backend.ingestion import index_store
from backend.search import coverage_gate, page_index
from backend.search.database import keyword_sql
from backend.search.database.pgvector_chunk_store import SEARCH_EF

HITS = 6
SCORE_TOLERANCE = 1e-9
SAMPLES = 100
K = 10
MIN_RECALL = 0.98
TIE = 1e-5  # a distance this close to the exact tenth's is a tie with it
REPORTS = data_paths.WORKING / 'database'


def keyword_gate(connection: psycopg.Connection, pages: list[page_index.Page]) -> dict:
    """Each work's probe through the in-memory port and through the database; ids compared as (work, label)."""
    ranked = [page for page in pages if page.searchable]
    port = page_index.PageIndex(ranked)
    labels = {page_id: f'{work}\x00{label}' for page_id, work, label in connection.execute('SELECT id, work, label FROM pages')}
    texts = {}
    for page in pages:
        texts.setdefault(page.work, []).append(page.text)
    rows, port_ms, sql_ms = [], [], []
    for work, joined in sorted(texts.items()):
        probe = coverage_gate.build_probe('\n'.join(joined))
        if not probe:
            continue
        started = time.perf_counter()
        expected = [(score, f'{ranked[number].work}\x00{ranked[number].page}') for score, number in port.scored(probe)[:HITS]]
        port_ms.append(1000 * (time.perf_counter() - started))
        started = time.perf_counter()
        found = [(score, labels[page_id]) for page_id, score in keyword_sql.ranked(connection, probe, HITS)]
        sql_ms.append(1000 * (time.perf_counter() - started))
        same_pages = [key for _, key in expected] == [key for _, key in found]
        same_scores = same_pages and all(abs(a - b) <= SCORE_TOLERANCE for (a, _), (b, _) in zip(expected, found))
        rows.append({'work': work, 'same_pages': same_pages, 'same_scores': same_scores,
                     'port_reached': work in [key.split('\x00')[0] for _, key in expected],
                     'sql_reached': work in [key.split('\x00')[0] for _, key in found],
                     'port_first': bool(expected) and expected[0][1].split('\x00')[0] == work,
                     'sql_first': bool(found) and found[0][1].split('\x00')[0] == work,
                     'differing': [] if same_pages else {'port': [key.replace('\x00', ' p.') for _, key in expected],
                                                         'database': [key.replace('\x00', ' p.') for _, key in found]}})
    count = lambda field: sum(1 for row in rows if row[field])
    return {'probes': len(rows), 'same_pages': count('same_pages'), 'same_scores': count('same_scores'),
            'gate_port': {'reached': count('port_reached'), 'rank_1': count('port_first')},
            'gate_database': {'reached': count('sql_reached'), 'rank_1': count('sql_first')},
            'ms_median_port': round(statistics.median(port_ms), 1) if port_ms else None,
            'ms_median_database': round(statistics.median(sql_ms), 1) if sql_ms else None,
            'rows': [row for row in rows if not row['same_scores']]}


def semantic_gate(connection: psycopg.Connection, stores: dict[str, Path]) -> dict:
    """Per knowledge base: HNSW recall@10 against an exact search, on sample stored vectors."""
    register_vector(connection)
    connection.execute(f'SET hnsw.ef_search = {SEARCH_EF}')
    result = {}
    for base, path in stores.items():
        collection = chromadb.PersistentClient(path=str(path), settings=chromadb.config.Settings(anonymized_telemetry=False)
                                               ).get_collection(index_store.COLLECTION)
        ids, parts = [], []
        for offset in range(0, collection.count(), 5000):
            stored = collection.get(include=['embeddings'], limit=5000, offset=offset)
            ids += stored['ids']
            parts.append(numpy.asarray(stored['embeddings'], dtype=numpy.float32))
        vectors = numpy.vstack(parts)
        normed = vectors / numpy.linalg.norm(vectors, axis=1, keepdims=True)
        step = max(1, len(ids) // SAMPLES)
        recalls, times = [], []
        for query in normed[::step][:SAMPLES]:
            tenth = float(1 - numpy.sort(normed @ query)[-K])  # the exact tenth's cosine distance
            started = time.perf_counter()
            found = [row[0] for row in connection.execute(
                'SELECT embedding <=> %s FROM chunks WHERE knowledge_base = %s ORDER BY embedding <=> %s LIMIT %s',
                (query, base, query, K))]
            times.append(1000 * (time.perf_counter() - started))
            recalls.append(sum(1 for distance in found if distance <= tenth + TIE) / K)
        result[base] = {'chunks': len(ids), 'samples': len(recalls), 'recall_at_10': round(statistics.mean(recalls), 4),
                        'ms_median': round(statistics.median(times), 1)}
    return result


def run(url: str, pages: list[page_index.Page], stores: dict[str, Path]) -> dict:
    """Both gates; the report written, its summary returned with `passed`."""
    with psycopg.connect(url) as connection:
        keyword = keyword_gate(connection, pages)
        semantic = semantic_gate(connection, stores)
    passed = (keyword['probes'] > 0 and keyword['same_scores'] == keyword['probes']
              and keyword['gate_port'] == keyword['gate_database']
              and all(base['recall_at_10'] >= MIN_RECALL for base in semantic.values()))
    summary = {'passed': passed, **{key: value for key, value in keyword.items() if key != 'rows'}, 'semantic': semantic}
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    (REPORTS / f'gate_{stamp}.json').write_text(json.dumps({'summary': summary, 'differing': keyword['rows']}, indent=1,
                                                          ensure_ascii=False), encoding='utf-8')
    return {'summary': summary}
