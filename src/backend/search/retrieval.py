"""Retrieval: a question in, the closest chunks out, each with its full citation.

This is the one search function of the project, with two doors: the chatbot uses it, and later a
coding session can call it as a tool over MCP. It therefore needs **no chat model**.
The caller may be a language model that rewrites its own question and writes its own answer.

Phase 3 is plain vector search (`retrieve`): the question is embedded with the same model as the
chunks, and Chroma returns the chunks nearest by cosine distance. Phase 4 rewrites the query around
it; phase 5 adds keyword search (`KeywordIndex`, BM25) and runs both (`hybrid_retrieve`). The
fusion, `reciprocal_rank_fusion`, lives here, because both phases merge ranked lists with it.
"""

import functools
import json
import re
import sqlite3
from pathlib import Path

from rank_bm25 import BM25Okapi

from backend.configuration import data_paths
from backend.ingestion import index_store
from backend.providers import embedding_route

CHROMA_DIRECTORY = data_paths.INDEX / 'chroma'
DATABASE = data_paths.INDEX / 'knowledge.sqlite3'

# The metadata a caller gets with every chunk, enough to quote and cite it without the index.
CITATION_FIELDS = ('source_id', 'source_title', 'authors', 'licence', 'licence_url', 'shelf',
                   'format', 'chapter', 'section', 'heading_path', 'printed_page', 'pdf_page',
                   'url', 'anchor',
                   'pdf_page_end', 'printed_page_end', 'route', 'reading_key',  # the trace of phase 5, shown with a hit (98.c)
                   'knowledge_base')  # a private chunk says so (#8); a free chunk has none, and a hit reads it as free


@functools.cache
def default_store():
    """The persistent index, opened once per process."""
    return index_store.chroma(CHROMA_DIRECTORY, embedding_route.embeddings(), embedding_route.INDEX_MODEL)


def retrieve(query: str, k: int = 5, filters: dict | None = None, store=None) -> list[dict]:
    """The k chunks closest in meaning to the query.

    Args:
        query: The question, as asked.
        k: How many chunks to return.
        filters: A Chroma metadata filter, e.g. {'shelf': 'architecture'}; None searches all.
        store: The vector store to search; the persistent index when None (tests pass their own).

    Returns:
        One dict per chunk, best first: `chunk_id`, `similarity` (cosine, 1 = same direction),
        `text`, and `citation` with the fields in CITATION_FIELDS that the chunk has.
    """
    if not query or not query.strip():
        raise ValueError('an empty query cannot be searched')
    store = store if store is not None else default_store()
    hits = store.similarity_search_with_score(query, k=k, filter=filters)
    results = []
    for document, distance in hits:
        metadata = document.metadata
        results.append({
            'chunk_id': metadata['chunk_id'],
            # Chroma's cosine space returns a distance, 1 - cosine similarity.
            'similarity': round(1.0 - distance, 6),
            'text': document.page_content,
            'citation': {field: metadata[field] for field in CITATION_FIELDS if field in metadata},
        })
    return results


# Keyword search (phase 5): BM25 as the course teaches it (lesson 2, `rank-bm25` 0.2.2, BM25Okapi).
# The course splits at spaces; here words are lower-cased and cut at anything that is not a letter
# or digit, except a joining &, - or ' inside a word, so "P&L", "walk-forward" and "tom-next" stay
# one token (decided 2026-09-30, 2.a). No stemming. A few English function words are dropped: they
# match everywhere and only add noise to the scores.
_TOKEN = re.compile(r"[a-z0-9]+(?:[&'\-][a-z0-9]+)*")
STOPWORDS = frozenset(
    'a an and are as at be by can do does for from how i in is it its me my of on or should that '
    'the their this to was what when where which who why will with you your'.split())


def tokenize(text: str) -> list[str]:
    """The words BM25 compares: lower-cased, joined terms kept whole, function words dropped."""
    return [token for token in _TOKEN.findall(text.lower()) if token not in STOPWORDS]


class KeywordIndex:
    """BM25 over every chunk's text, built in memory from the SQLite store (decided 2026-09-30, 1.a).

    The chunks table holds exactly what Chroma holds, from the same build, so both searches see the
    same corpus. Building takes a few seconds; nothing is written to disk.
    """

    def __init__(self, rows: list[tuple[str, str, dict]]):
        self.ids = [row[0] for row in rows]
        self.texts = [row[1] for row in rows]
        self.metadata = [row[2] for row in rows]
        self.bm25 = BM25Okapi([tokenize(text) for text in self.texts])

    @classmethod
    def from_database(cls, path: Path = DATABASE) -> 'KeywordIndex':
        with sqlite3.connect(path) as connection:
            rows = connection.execute('SELECT id, text, metadata FROM chunks ORDER BY id').fetchall()
        return cls([(chunk_id, text, json.loads(metadata)) for chunk_id, text, metadata in rows])

    def search(self, query: str, k: int = 5, filters: dict | None = None) -> list[dict]:
        """The k chunks with the highest BM25 score, in the shape `retrieve` returns.

        Args:
            query: The search text.
            k: How many chunks to return.
            filters: Metadata equality, e.g. {'shelf': 'architecture'}; None searches all.

        Returns:
            One dict per chunk with a score above 0, best first. `similarity` is None (there is no
            vector here); `bm25` holds the score.
        """
        scores = self.bm25.get_scores(tokenize(query))
        allowed = range(len(self.ids)) if not filters else [
            i for i, metadata in enumerate(self.metadata)
            if all(metadata.get(key) == value for key, value in filters.items())]
        best = sorted((i for i in allowed if scores[i] > 0), key=lambda i: scores[i], reverse=True)[:k]
        return [{
            'chunk_id': self.ids[i],
            'similarity': None,
            'bm25': round(float(scores[i]), 4),
            'text': self.texts[i],
            'citation': {field: self.metadata[i][field] for field in CITATION_FIELDS if field in self.metadata[i]},
        } for i in best]


@functools.cache
def default_keyword_index() -> KeywordIndex:
    """The keyword index over the built corpus, built once per process."""
    return KeywordIndex.from_database()


LICENSED_CHROMA = data_paths.LICENSED_INDEX / 'chroma'
LICENSED_DATABASE = data_paths.LICENSED_INDEX / 'knowledge.sqlite3'


def licensed_index_built() -> bool:
    """Whether this machine holds the private base's vector index (#8); a clone, and every --public-only start, has none."""
    return LICENSED_DATABASE.exists() and LICENSED_CHROMA.exists()


@functools.cache
def licensed_store():
    """The private base's vector index, opened once per process; only where it was built (`licensed_index_built`)."""
    return index_store.chroma(LICENSED_CHROMA, embedding_route.embeddings(), embedding_route.INDEX_MODEL)


@functools.cache
def licensed_keyword_index() -> KeywordIndex:
    """The keyword index over the private base's chunks, as the free one is over its own."""
    return KeywordIndex.from_database(LICENSED_DATABASE)


def demoted(results: list[dict], sections) -> list[dict]:
    """The fused list with every chunk of a listed section moved behind all others, each group in its own order (phase 6's
    first hypothesis): a textbook's exercise pages repeat a chapter's vocabulary without explaining it, and outranked the
    explanation. A listed section stays retrievable when nothing else answers; only its rank yields."""
    if not sections:
        return results
    listed = [result for result in results if (result.get('citation') or {}).get('section') in sections]
    return [result for result in results if result not in listed] + listed


def hybrid_retrieve(queries: list[str], k: int = 5, filters: dict | None = None, store=None,
                    keyword_index: KeywordIndex | None = None,
                    keyword_queries: list[str] | None = None, with_signal: bool = False,
                    trace: dict | None = None, demote_sections=frozenset()):
    """Vector search for every query and BM25 next to it, all lists fused by RRF (phase 5, 3.a).

    The course's rule of thumb (lesson 2): concepts → embeddings, exact terms → BM25, mixed → hybrid.
    This corpus has both: questions about concepts, and terms of art such as Kelly criterion, trial
    balance or tom-next, which an embedding may rank below a loosely related passage.

    Args:
        keyword_queries: What BM25 searches; the same `queries` when None.
        with_signal: Also return the best cosine similarity of the vector searches, the value the
            relevance floor was measured on (phase 5).
        trace: A dict to fill with every list before fusion and where each fused chunk came from
            (phase 10, for the interface's *Search* tab). It changes nothing in the result.

    Returns:
        The fused list, or (fused list, best similarity) with `with_signal`.
    """
    keyword_index = keyword_index if keyword_index is not None else default_keyword_index()
    vector_lists = [retrieve(query, k=k, filters=filters, store=store) for query in queries]
    keyword_lists = [keyword_index.search(query, k=k, filters=filters) for query in (keyword_queries or queries)]
    # Demoted before the cut, so a passage below the cut can take a listed section's place among the k.
    fused = demoted(reciprocal_rank_fusion(vector_lists + keyword_lists), demote_sections)[:k]
    if trace is not None:
        record_lists(trace, [('vector', q, found) for q, found in zip(queries, vector_lists)]
                     + [('bm25', q, found) for q, found in zip(keyword_queries or queries, keyword_lists)], fused)
    if with_signal:
        return fused, max((found[0]['similarity'] for found in vector_lists if found), default=None)
    return fused


def _where(result: dict) -> dict:
    citation = result.get('citation') or {}
    return {'source': citation.get('source_id'), 'section': citation.get('section') or citation.get('chapter')}


def record_lists(trace: dict, lists: list[tuple[str, str, list[dict]]], fused: list[dict]) -> None:
    """Write the ranked lists and the fusion into `trace`: what each search found, and what came of it.

    Args:
        lists: (kind, query, results) per search, kind 'vector' or 'bm25', in the order they were fused.
        fused: The fused list as returned, best first.
    """
    trace['lists'] = []
    found_by: dict[str, list[str]] = {}
    for number, (kind, query, results) in enumerate(lists, start=1):
        score_key = 'similarity' if kind == 'vector' else 'bm25'
        hits = []
        for rank, result in enumerate(results, start=1):
            score = result.get(score_key)
            hits.append({'rank': rank, 'chunk_id': result['chunk_id'], **_where(result),
                         'score': round(score, 3) if score is not None else None})
            found_by.setdefault(result['chunk_id'], []).append(f'list {number} #{rank}')
        trace['lists'].append({'kind': kind, 'query': query, 'hits': hits})
    trace['fused'] = [{'rank': rank, 'chunk_id': result['chunk_id'], **_where(result),
                       'fused_score': round(result.get('fused_score', 0.0), 4),
                       'similarity': result.get('similarity'), 'bm25': result.get('bm25'),
                       'from': found_by.get(result['chunk_id'], [])}
                      for rank, result in enumerate(fused, start=1)]


RRF_K = 60


def reciprocal_rank_fusion(result_lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """Merge several ranked result lists into one, by reciprocal rank fusion (RRF).

    The course's RAG-Fusion step (rag_from_scratch 5-9), with its formula and its k = 60: a chunk
    scores 1 / (rank + k) in every list it appears in, with rank counted from 0, and the scores add
    up. A chunk that several lists rank well rises; one that a single list ranks first does not
    automatically win. Only ranks count, so lists whose scores are not comparable (vector
    similarity, BM25) can be merged.

    Written out, as in the course, rather than taken from a library: the course's version keys
    documents by `langchain_core.load.dumps`, which would treat two copies of the same chunk with
    different similarity values as different documents. Here the key is the chunk id.

    Args:
        result_lists: Lists as `retrieve` returns them, each best first.
        k: The RRF constant. Larger values flatten the difference between ranks.

    Returns:
        Every chunk once, best fused score first, with `fused_score` added, the best `similarity`
        any vector list gave it (None if only keyword lists found it) and the best `bm25` score.
    """
    fused: dict[str, dict] = {}
    for results in result_lists:
        for rank, result in enumerate(results):
            entry = fused.setdefault(result['chunk_id'], {**result, 'fused_score': 0.0})
            entry['fused_score'] += 1 / (rank + k)
            for key in ('similarity', 'bm25'):
                values = [v for v in (entry.get(key), result.get(key)) if v is not None]
                entry[key] = max(values) if values else None
    return sorted(fused.values(), key=lambda entry: entry['fused_score'], reverse=True)
