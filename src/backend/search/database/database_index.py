"""The librarian's index read from the database (issue #10, part C): its works and pages loaded in seconds instead of
assembled from files, the keyword ranking computed in SQL (`keyword_sql`), and the index's generation asked on every call,
so a change written to the database is served without a restart.

`DatabaseIndex` answers as `page_index.PageIndex` answers (`scored`, `holding_every_term`, `search`, `pages[number]`), so
the service's tools stay as they are; a page's number is its id in the database. Pages stay in memory as before: an open
page, a snippet and a work's contents need their text, and the whole index is about the size the librarian held already.
"""

import psycopg

from backend.search import page_index
from backend.search.database import keyword_sql

CONNECT_TIMEOUT_SECONDS = 5  # a database that is down is noticed at once, so the librarian falls back to files quickly
PAGE_COLUMNS = ('id, work, knowledge_base, label, line, line_end, path, pdf, printed, section, route, reading_key, '
                'searchable, text, index_text')
WORK_COLUMNS = ('key, knowledge_base, title, licence, route, subject, view_id, edition, year, kept_for, pages, code_language, '
                'companion_of, language')


def generation(connection: psycopg.Connection) -> int:
    return connection.execute('SELECT generation FROM index_state').fetchone()[0]


def load(connection: psycopg.Connection, work_type) -> tuple[dict[int, page_index.Page], dict, int]:
    """Every page by its id, every work by its key (built with `work_type`, the server's `Work`), and the generation they
    belong to, read inside one transaction so the three agree."""
    with connection.transaction():
        current = generation(connection)
        works = {}
        for (key, base, title, licence, route, subject, view_id, edition, year, kept_for, pages, code_language,
             companion_of, language) in connection.execute(f'SELECT {WORK_COLUMNS} FROM works ORDER BY key'):
            works[key] = work_type(key, title, base, licence, route, pages, subject=subject, view_id=view_id,
                                   edition=edition, year=year, kept_for=kept_for, code_language=code_language,
                                   companion_of=companion_of, language=language)
        pages = {}
        for (page_id, work, base, label, line, line_end, path, pdf, printed, section, route, reading_key, searchable, text,
             index_text) in connection.execute(f'SELECT {PAGE_COLUMNS} FROM pages ORDER BY id'):
            pages[page_id] = page_index.Page(work, label, line, text, path, pdf=pdf, section=section, line_end=line_end,
                                             knowledge_base=base, route=route, printed=printed, reading_key=reading_key,
                                             index_text=index_text, searchable=searchable)
    return pages, works, current


EVERY_TERM = """
SELECT page_id FROM postings WHERE term = ANY(%(terms)s::text[]) GROUP BY page_id
HAVING count(DISTINCT term) = %(count)s
"""


class DatabaseIndex:
    """The keyword ranking in the database over pages held in memory by id. One connection, opened on first use and opened
    again once when it was lost (the database restarted)."""

    def __init__(self, url: str, pages: dict[int, page_index.Page]):
        self._url = url
        self.pages = pages
        self._connection: psycopg.Connection | None = None

    def connection(self) -> psycopg.Connection:
        if self._connection is None or self._connection.closed:
            self._connection = psycopg.connect(self._url, autocommit=True, connect_timeout=CONNECT_TIMEOUT_SECONDS)
        return self._connection

    def _ask(self, ask):
        try:
            return ask(self.connection())
        except psycopg.OperationalError:
            self._connection = None
            return ask(self.connection())

    def scored(self, query: str) -> list[tuple[float, int]]:
        """Every page holding a query term with its score, best first, as `PageIndex.scored` gives them."""
        return [(score, page_id) for page_id, score in self._ask(lambda c: keyword_sql.ranked(c, query, None))]

    def holding_every_term(self, query: str) -> set[int]:
        terms = sorted(set(page_index.tokenize(query)))
        if not terms:
            return set()
        return {row[0] for row in self._ask(lambda c: c.execute(EVERY_TERM, {'terms': terms, 'count': len(terms)}).fetchall())}

    def search(self, query: str, hits: int = 6, accept=None) -> list[tuple[float, page_index.Page]]:
        """The best pages, best first; `accept` filters after scoring, so a filtered search ranks on the whole index's
        statistics, as `PageIndex.search` does (decision 71.a)."""
        if accept is None:
            ranked = self._ask(lambda c: keyword_sql.ranked(c, query, hits))
            return [(score, self.pages[page_id]) for page_id, score in ranked]
        accepted = [(score, page_id) for score, page_id in self.scored(query) if accept(self.pages[page_id])]
        return [(score, self.pages[page_id]) for score, page_id in accepted[:hits]]

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
