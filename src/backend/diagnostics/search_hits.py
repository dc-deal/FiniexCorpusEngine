"""The keyword search the MCP server serves, shown in the diagnostics (V4): the core's own `SearchService`, called directly
and never through MCP, built once over the knowledge bases this app gives out.

Every hit is the core's, field for field. This module adds only where the diagnostics shows the hit's page: a page of an
exported reading, found by the work and the PDF page the hit names, both of which the export carries beside the catalog id.
A page the diagnostics does not show yet, an HTML section or a legacy Markdown page, gets no link and names its file and
lines instead. Building the index takes about 20 s over the free knowledge base and 50 s with the licensed one (measured
10 Nov), so the start command warms it while the app comes up, its pages read in a process of their own.
"""

import multiprocessing
import re
import sys
import threading
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Literal

from pydantic import BaseModel, computed_field

from backend.diagnostics import sources, work_editions
from backend.diagnostics.readings import KnowledgeBase, Readings
from backend.search import search_server, shelf

Corpus = Literal['all', 'free', 'licensed']


class HitPage(BaseModel):
    label: str  # the page as its source names it: a PDF page, a marker's number, or a section such as `s44`
    pdf: str | None  # the PDF page, where known; never a guess
    printed: str | None  # the number printed on the page, where a reading saw one


class PageLink(BaseModel):
    """Where the diagnostics shows a hit's page: the page view of an exported reading."""

    knowledge_base: KnowledgeBase
    source_id: str
    pdf_page: int


class ArticleLink(BaseModel):
    """Where the diagnostics shows an HTML section the chat cites: its article, scrolled to the section (decision 164.a)."""

    knowledge_base: KnowledgeBase = 'free'
    source_id: str
    label: str  # the section as the search labels it, `s` and its position from 1, as the article view addresses it


class SearchHit(BaseModel):
    score: float
    knowledge_base: KnowledgeBase
    work: str  # the search's own key for the work, which is not the catalog id: `view` names that
    title: str
    page: HitPage
    section: str | None  # the heading in effect where the page begins
    where: str  # the file the text comes from, with its lines where there are some
    snippet: str  # a few lines of the page around the match, as text
    terms_found: list[str]
    terms_missing: list[str]
    licence: str
    route: str  # how the page's text was made: a vision reading, a text layer and why, HTML by section, legacy Markdown
    reading_key: str | None
    view: PageLink | None
    edition: str | None = None  # the catalog's edition of the work ("2nd"), as the search names it (E1.a)
    year: int | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def edition_said(self) -> str | None:
        """The edition its citation names beside the title (E1.a): "2nd edition, 2003", or the year alone."""
        return work_editions.words(self.edition, self.year)


class SearchAnswer(BaseModel):
    state: Literal['found', 'nothing found', 'error']
    query: str
    corpus: str
    knowledge_bases: list[str]  # the bases the search holds: a choice of corpus is offered only where there is one
    hits: list[SearchHit]
    error: str | None = None


def pages_in_a_process(public_only: bool, read: Callable[[bool], dict] = search_server.knowledge_bases) -> dict:
    """The knowledge bases' pages, read by the core's `knowledge_bases` in a process of its own and handed back pickled.
    Reading them takes about 45 s, much of it in PyMuPDF, which holds the interpreter's lock: in a thread of this process it
    starved every request beside it, and the overview took 8 s instead of 0.7 s (measured 10 Nov). The pages, 57 MB pickled,
    cross in a quarter of a second. Where no process can be started, they are read here, as before."""
    try:
        with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn')) as pool:
            return pool.submit(read, public_only).result()
    except (OSError, BrokenProcessPool) as failed:
        print(f'the search reads its pages in this process instead: {failed}', file=sys.stderr, flush=True)
        return read(public_only)


def read_pages(public_only: bool) -> dict:
    """The pages the search is built over; a test reads them in its own process."""
    return pages_in_a_process(public_only)


def build_service(public_only: bool) -> search_server.SearchService:
    """The core's search over the knowledge bases given out; with `public_only` the licensed one is never read (81.a)."""
    return search_server.SearchService(read_pages(public_only))


class Search:
    """The search, built once, on first use or ahead of it by `warm`, and shared by every request: a built index is only
    read, so requests may search it side by side."""

    def __init__(self, public_only: bool):
        self.public_only = public_only
        self._service: search_server.SearchService | None = None
        self._lock = threading.Lock()

    def service(self) -> search_server.SearchService:
        with self._lock:
            if self._service is None:
                self._service = build_service(self.public_only)
            return self._service

    def ready(self) -> search_server.SearchService | None:
        """The search if it is built, without waiting for it: an overview never blocks on the index."""
        return self._service

    def warm(self) -> None:
        """Build the index in the background, so the first search does not wait for it."""
        threading.Thread(target=self.service, name='search-index', daemon=True).start()

    def answer(self, query: str, corpus: Corpus, hits: int, bases: dict[str, Readings]) -> SearchAnswer:
        service = self.service()
        result = service.search(query, corpus, hits)
        view_of = page_links(bases)
        return SearchAnswer(state=result['state'], query=query, corpus=corpus, knowledge_bases=list(service.bases),
                            error=result.get('error'),
                            hits=[SearchHit(**hit, view=view_of(hit['knowledge_base'], hit['work'], hit['page']['pdf']))
                                  for hit in result.get('hits', [])])


def work_sources(bases: dict[str, Readings]) -> dict[tuple[str, str], str]:
    """Every key the search names a work by, per knowledge base, to the id this app's routes take, for a work whose page
    readings the export holds. The search names a work by its server key, which for a licensed work is not the export's
    (`book_a` for a file the export names by its stem): the shelf maps one to the other, where it has been built (line 1,
    decision 125.a)."""
    found = {(name, row['work']): row['source_id'] for name, store in bases.items() for row in store.rows()}
    for name, store in bases.items():
        for item in (shelf.load(name) or {}).get('works') or []:
            if item.get('work') and item.get('source_id') and store.work(item['source_id']) is not None:
                found.setdefault((name, item['work']), item['source_id'])
    return found


SECTION_LABEL = re.compile(r's[1-9]\d*')


def article_links() -> Callable[[str, str | None, str | None], ArticleLink | None]:
    """The article view of an HTML section the search or the chat names, by knowledge base, work and page label (164.a).
    The search names a free HTML work by its catalog id and a section `s` and its position from 1 (`search_server.
    free_html_pages`), as the article view addresses both, so no mapping is needed beyond knowing the work is an HTML work
    of the free catalog; a test holds every HTML work's key to its catalog id."""
    html = {work.id for work in sources.works() if work.format == 'html' and work.knowledge_base == 'free'}

    def article_of(knowledge_base: str, work: str | None, label: str | None) -> ArticleLink | None:
        if knowledge_base != 'free' or work not in html or not label or not SECTION_LABEL.fullmatch(label):
            return None
        return ArticleLink(source_id=work, label=label)

    return article_of


def page_links(bases: dict[str, Readings]) -> Callable[[str, str, str | None], PageLink | None]:
    """The page view of a page the search or the chat names, by knowledge base, work and PDF page, where the export holds
    a reading of it; None for any other (an HTML section, a legacy Markdown page, a page no reading covers)."""
    sources = work_sources(bases)
    read = {(name, row['source_id'], row['pdf_page']) for name, store in bases.items() for row in store.rows()}

    def view_of(knowledge_base: str, work: str, pdf: str | None) -> PageLink | None:
        source_id = sources.get((knowledge_base, work))
        if not source_id or not (pdf and str(pdf).isdigit()) or (knowledge_base, source_id, int(pdf)) not in read:
            return None
        return PageLink(knowledge_base=knowledge_base, source_id=source_id, pdf_page=int(pdf))

    return view_of
