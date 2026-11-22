"""The keyword index the MCP server serves, built here for what the views say of a page (V2.a): the core's own
`SearchService`, built once over the knowledge bases this app gives out, which a page's coverage reads to say whether the
search holds the page and what text it serves. A search a person runs goes to the running librarian over MCP instead, as a
client's does (`librarian`, L1.a): the search screen that called this index directly went with it.

Beside it, where the diagnostics shows a page the search names: a page of an exported reading, found by the work and the PDF
page, both of which the export carries beside the catalog id (the call log's links).

Where this machine's configuration has the librarian read the index database (issue #10, part C), the view reads it too (part
E, 22 Nov): the core's `build_service` loads it in seconds, against about three minutes to assemble it from files, which kept
the view's warm-up and every call during it slow after each restart. Files stay where the configuration says so, under
`--public-only`, and where the database cannot serve: they are read in a process of their own, the view's reader handed to
the core, since in this process the reading starved every request beside it. A service read from the database is asked, at
most every few seconds, whether an import or a verdict wrote the index since, and loads it again where one did.
"""

import multiprocessing
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

from pydantic import BaseModel

from backend.diagnostics.readings import KnowledgeBase, Readings
from backend.search import search_server, shelf

REFRESH_SECONDS = 5.0  # how often a page's view asks the index database whether its index was written since


class PageLink(BaseModel):
    """Where the diagnostics shows a hit's page: the page view of an exported reading."""

    knowledge_base: KnowledgeBase
    source_id: str
    pdf_page: int


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
    """The core's search over the knowledge bases given out: from the index database where this machine's configuration says
    so, else, and where the database cannot serve, from files read in a process of their own (`read_pages`, looked up at the
    call, so a test's own reader reaches it); with `public_only` files alone, the licensed base never read (81.a)."""
    return search_server.build_service(public_only, read=read_pages)


class Search:
    """The search, built once, on first use or ahead of it by `warm`, and shared by every request: a built index is only
    read, so requests may search it side by side."""

    def __init__(self, public_only: bool, clock=time.monotonic):
        self.public_only = public_only
        self._service: search_server.SearchService | None = None
        self._lock = threading.Lock()
        self._clock = clock
        self._asked = float('-inf')  # when the database was last asked whether the index was written
        self._said = False  # a database that could not be asked is said once

    def service(self) -> search_server.SearchService:
        with self._lock:
            if self._service is None:
                self._service = build_service(self.public_only)
            return self._service

    def ready(self) -> search_server.SearchService | None:
        """The search if it is built, without waiting for it: an overview never blocks on the index. One read from the database
        is asked at most every `REFRESH_SECONDS` whether an import or a verdict wrote the index since (one cheap query), and
        loads it again where one did, so a page says what the librarian serves; where the database cannot be asked, the index
        loaded last stays."""
        service = self._service
        if service is None or getattr(service, 'database_url', None) is None or self._clock() - self._asked < REFRESH_SECONDS:
            return service
        self._asked = self._clock()
        try:
            service.refresh()
        except Exception as error:  # noqa: BLE001 — the database gone for a moment: the index loaded last serves on
            if not self._said:
                print(f'the search keeps the index it loaded last: {type(error).__name__}: {error}', file=sys.stderr,
                      flush=True)
                self._said = True
        return service

    def warm(self) -> None:
        """Build the index in the background, so the first search does not wait for it."""
        threading.Thread(target=self.service, name='search-index', daemon=True).start()


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


def page_links(bases: dict[str, Readings]) -> Callable[[str, str, str | None], PageLink | None]:
    """The page view of a page the search names, by knowledge base, work and PDF page, where the export holds
    a reading of it; None for any other (an HTML section, a legacy Markdown page, a page no reading covers)."""
    sources = work_sources(bases)
    read = {(name, row['source_id'], row['pdf_page']) for name, store in bases.items() for row in store.rows()}

    def view_of(knowledge_base: str, work: str, pdf: str | None) -> PageLink | None:
        source_id = sources.get((knowledge_base, work))
        if not source_id or not (pdf and str(pdf).isdigit()) or (knowledge_base, source_id, int(pdf)) not in read:
            return None
        return PageLink(knowledge_base=knowledge_base, source_id=source_id, pdf_page=int(pdf))

    return view_of
