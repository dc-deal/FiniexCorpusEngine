"""The keyword ranking computed in the index database (issue #10): the IDE's BM25 port, its tokenizer, `K1`, `B` and idf
unchanged (decision 56.b), summed in SQL over the postings of the query's terms, so one page's change is one page's rows.

Measured on 22 Nov 2026 against the in-memory port over both knowledge bases: the same top six with the same scores on
every coverage-gate probe; 47 ms in the median per probe, 0.3 s for a query of common words (the port: 10 ms). A repeated
query term counts once per repetition, as in the port, and a tie breaks on the higher ordinal, as the port's sort does.
"""

import psycopg

from backend.search import page_index

RANKED = """
WITH q AS (SELECT term, count(*) AS qtf FROM unnest(%(terms)s::text[]) AS term GROUP BY term),
stats AS (SELECT count(*)::float8 AS n, avg(length)::float8 AS avgdl FROM pages WHERE searchable),
df AS (SELECT p.term, count(*)::float8 AS df FROM postings p JOIN q USING (term) GROUP BY p.term)
SELECT pg.id,
       sum(q.qtf * ln(1 + (stats.n - df.df + 0.5) / (df.df + 0.5))
           * p.tf * (%(k1)s + 1) / (p.tf + %(k1)s * (1 - %(b)s + %(b)s * pg.length / stats.avgdl))) AS score
FROM postings p JOIN q USING (term) JOIN df USING (term) JOIN pages pg ON pg.id = p.page_id CROSS JOIN stats
WHERE (%(base)s::text IS NULL OR pg.knowledge_base = %(base)s) AND (%(work)s::text IS NULL OR pg.work = %(work)s)
GROUP BY pg.id, pg.ordinal
ORDER BY score DESC, pg.ordinal DESC
LIMIT %(hits)s
"""


def ranked(connection: psycopg.Connection, query: str, hits: int | None = 6, knowledge_base: str | None = None,
           work: str | None = None) -> list[tuple[int, float]]:
    """The best pages for a query as (page id, score), best first; `hits` None gives every page holding a term. A filter by
    knowledge base or work ranks on the statistics of the whole index, as the port's filtered search does (decision 71.a)."""
    terms = page_index.tokenize(query)
    if not terms:
        return []
    rows = connection.execute(RANKED, {'terms': terms, 'k1': page_index.K1, 'b': page_index.B, 'hits': hits,
                                       'base': knowledge_base, 'work': work}).fetchall()
    return [(page_id, score) for page_id, score in rows if score > 0]
