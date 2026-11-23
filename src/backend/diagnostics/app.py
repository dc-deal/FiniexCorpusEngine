"""The diagnostics UI's server: a read-only JSON API under /api, the Librarian page's calls, and the built UI at /.

The UI is a Vue app whose build is committed in `src/frontend/diagnostics/dist/`, so a reviewer needs no Node: this one
process serves both. During development Vite serves the UI instead and forwards /api here.

A work is addressed within its knowledge base, `/api/<knowledge base>/works/<id>/...`, because an id alone is not a key
(decision 80.a); the lists of works and of issues span every knowledge base served, each row marked with its own. The
Librarian page's call (L1.a) is the one route that can spend, a call over MCP to the running librarian, local only and
Origin-checked; see `librarian`. The app is read-only unless started with --allow-verdicts; then one write route, a
person's verdict from the page view, local only, Origin-checked, append-only; see `verdicts`.
Every route answers only a request addressed to this machine by name; see `TRUSTED_HOSTS`.
"""

import threading
import time
import traceback
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.chat import app_config
from backend.diagnostics import (calls, code_works, coverage_ladder, epub_works, error_classes, html_works, librarian,
                                 local_only, overview, page_integrity, page_chunks, page_ladder, prompts, readings, runs,
                                 search_hits, shelf_rows, sources, stamps, verdicts, work_editions)

DIST = sources.ROOT / 'src' / 'frontend' / 'diagnostics' / 'dist'
# the licensed catalog's fields the sources view shows beside a work's title (N1.a)
CATALOG_FIELDS = {'authors', 'publisher', 'year', 'edition', 'format', 'shelf', 'licence', 'notes', 'series', 'language'}

# The names a request may address this server by: a page elsewhere can point a domain of its own at 127.0.0.1 (DNS
# rebinding) and read what the GET routes serve, licensed pages and the coding sessions' questions among them, so any
# other Host is refused with 400 before a route runs. Starlette's TrustedHostMiddleware does the check; the Librarian's and
# the verdict routes' own Host and Origin checks stay as a second wall (`local_only`). An IPv6 address keeps its brackets, as the
# middleware parses it.
TRUSTED_HOSTS = ['127.0.0.1', 'localhost', '[::1]']


class AppInfo(BaseModel):
    """The name the view shows in its header and its browser tab (decision 149.c): a working name, kept in the app's own
    config so it changes in one place, without code."""

    title: str
    subtitle: str | None = None


def operation_id(route: APIRoute) -> str:
    """The route function's own name, where FastAPI's default appends path and method."""
    return route.name


Step = tuple[str, Callable[[], object]]


def warm_steps(bases: dict[str, readings.Readings], search: search_hits.Search, sources_list: Callable[[], object],
               overview_page: Callable[[], object]) -> list[Step]:
    """What the first requests after a start would otherwise wait for, in the order a person meets the views after a restart
    (line 1, 20 Nov: every merge restarts the container, and a work's page list took 24 s, its first page 18 s more): the
    Sources list first, a step of its own (9.a, 22 Nov: with the overview in one step it waited 11.4 s for both, on its own
    it is warm about 2 s after a start); then the overview, the landing page (each work's readings in figures, the shelves,
    every reading file's integrity: 6.6 s cold, measured 22 Nov); then what a work's page list needs (the legacy pages, 15.8 s
    natively, and the files not served), what any page's view needs (each base's vector index by page, which the first page
    of a base read whole), each work's pages without a reading, which its page list and its unread pages share (1.3 s for a
    work's first list in the container, the rest warm); then the Pages view's one load, the licensed EPUBs' cuts, which the
    Sources list counts their sections from, and last the search index, which only a search needs: a page's view never waits
    for it (read from the index database in 2.2 s where the configuration says so, issue #10 part E; assembled from files
    it took 202.3 s with both bases in the container)."""
    steps: list[Step] = [('the Sources list', sources_list), ('the overview', overview_page)]
    steps += [(f'the {name} legacy pages', store.legacy) for name, store in bases.items() if store.legacy]
    steps += [(f'the {name} files not served', store.not_served) for name, store in bases.items() if store.not_served]
    steps += [(f'the {name} vector index by page', lambda name=name: page_ladder.semantic_detail(name)) for name in bases]
    steps += [(f'the {name} pages without a reading', store.warm_unread) for name, store in bases.items()]
    steps.append(('the Pages view', lambda: overview.pages(bases, {})))
    if 'licensed' in bases:
        steps.append(('the licensed EPUBs', epub_works.cut_all))
    steps.append(('the search index', search.service))
    return steps


def run_warm(steps: list[Step], say: Callable[[str], None] = lambda line: print(line, flush=True)) -> None:
    """The steps one after the other, so they do not contend for the disk and the interpreter, each in a request's span so
    a file's stamp is looked at once. A step that fails is said and the next goes on: the warm-up never takes the view down,
    and a view whose step failed builds it on its own first call, as it would without a warm-up. Its last line says it is done.
    While it runs, a list's own call to cut the EPUBs ahead leaves them to it rather than cut beside it."""
    started = time.perf_counter()
    with epub_works.held():
        for name, step in steps:
            began = time.perf_counter()
            try:
                with stamps.one_look():
                    step()
            except Exception:  # noqa: BLE001 — any failure is the step's alone: said, and the rest goes on
                say(f'warm-up: {name} failed:\n{traceback.format_exc()}')
                continue
            say(f'warm-up: {name} in {time.perf_counter() - began:.1f} s')
    say(f'warm-up done in {time.perf_counter() - started:.0f} s')


def create_app(public_only: bool = False, warm_search: bool = False, librarian_client: Callable[[], Any] | None = None,
               allow_verdicts: bool = False, export_run: Callable[[], None] | None = None) -> FastAPI:
    """The app over the knowledge bases it may give out. With `public_only` the licensed one is never read (decision 81.a),
    so a recorded review cannot show a licensed title, page or count. `warm_search` keeps which pages of the PDFs have a text
    layer on disk (1.d), reads every reading file and builds the
    search index while the app comes up, as the start command does; the tests leave it off. `librarian_client` opens the
    Librarian page's one session with the running librarian on its first call (L1.a); without it the page calls nothing, as
    in every test, so no test reaches the librarian or a model.
    `allow_verdicts` opens the one write route, a person's verdict from the page view (213.b, 223.a); off, the app is
    read-only. `export_run` replaces the export a verdict sets going, for the tests, so none writes the real export."""
    bases = readings.knowledge_bases(public_only, keep_text_layers=warm_search)
    search = search_hits.Search(public_only)
    library = librarian.LibrarianService(librarian_client)
    judged = verdicts.VerdictService(allow_verdicts, bases, run=export_run)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        library.close()  # the page's one session with the librarian ends with the app

    app = FastAPI(title='Diagnostics', version='0.8.0', generate_unique_id_function=operation_id, lifespan=lifespan,
                  summary='Read-only views of the knowledge bases: where every source and reading came from.')
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)
    app.add_middleware(stamps.OneLook)  # each file's stamp looked at once a request (line 1, 20 Nov)
    # answers compressed where the browser takes it (9.a, measured 22 Nov: the Sources list's 298 KB as 28 KB, packed in 5 ms);
    # Starlette leaves the page images, PNG and JPEG already, as they are
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)

    def store_of(knowledge_base: str) -> readings.Readings:
        store = bases.get(knowledge_base)
        if store is None:
            raise HTTPException(404, f'no knowledge base {knowledge_base!r} is served here')
        return store

    def title_of(knowledge_base: str, source_id: str) -> str:
        work = store_of(knowledge_base).work(source_id)
        if work is not None:
            return work['title']
        # A work of the free catalog that is not read page by page (HTML, for one) has no page in the export, but it is a
        # work all the same: its page list is empty, not unknown.
        if knowledge_base == 'free':
            listed = next((work for work in sources.works() if work.id == source_id), None)
            if listed is not None:
                return listed.title
        # a licensed catalog entry with a PDF the export has no pages of: its list holds every page unread (U1.a)
        entry = store_of(knowledge_base).entry_work(source_id)
        if entry is not None:
            return entry['title']
        raise HTTPException(404, f'no work {source_id!r} in the {knowledge_base} knowledge base')

    @app.get('/api/app')
    def app_info() -> AppInfo:
        """The view's name, as `configs/app_config.json` holds it under `ui`."""
        ui = app_config.load().get('ui') or {}
        return AppInfo(title=ui.get('title') or 'Diagnostics', subtitle=ui.get('subtitle'))

    @app.get('/api/works')
    def list_works() -> list[sources.Work]:
        """Every work of every knowledge base served: the free catalog in its order, then the licensed works as their
        export lists them. Only the free knowledge base has a catalog."""
        listed: list[sources.Work] = []
        code: dict[str, list[readings.CatalogEntry]] = {}  # each base's code works, folded into their books' rows below (#12)
        for name, store in bases.items():
            if name == 'free':
                html = html_works.counts()
                listed += [free_work(store, work, html) for work in sources.works()]
            else:
                # a licensed work's title, authors and the rest from the local licensed catalog, where this machine has one
                # (N1.a); its store reads it, which no --public-only app has
                listed += [sources.Work(knowledge_base=work['knowledge_base'], id=work['source_id'], title=work['title'],
                                        readings=store.summary(work['source_id']), structure=sources.READ_PAGES, page_list=True,
                                        **catalog_fields(store, work['source_id']))
                           for work in store.works()]
                # then the catalog's entries the export has no pages of, as the free HTML works without readings stand (O1.a);
                # an EPUB the librarian serves by section counts its sections (123.a), the others are not read yet
                epubs = {path.name: (key, path) for key, path in epub_works.epubs().items()}
                code[name] = [entry for entry in store.unread_entries() if entry.format == 'code']
                unread = [entry for entry in store.unread_entries() if entry.format != 'code']
                listed += [sources.Work(knowledge_base=name, id=entry.id, title=entry.title,
                                        page_list=store.entry_work(entry.id) is not None,
                                        **entry.model_dump(include=CATALOG_FIELDS), **unread_structure(entry, epubs))
                           for entry in unread]
                # and an EPUB the catalog does not list, by its file's stem
                listed += [sources.Work(knowledge_base=name, id=key, title=path.stem, format='epub', epub_key=key,
                                        structure=sources.SECTIONS, **epub_structure(path))
                           for path_name, (key, path) in epubs.items()
                           if not any(entry.file == path_name for entry in unread)]
        # how far each is refined (U1.a): its shelf row's levels and its read pages' states
        shelves = {name: store.shelf_data() for name, store in bases.items()}
        # every work the corpus serves stands here (line 1, 20 Nov, the operator's "alles inhaltlich drin"): a work the shelf
        # serves from the IDE's Markdown alone, its source file not held here, under the shelf's id and title, with no view
        listed += [sources.Work(knowledge_base=name, id=row['source_id'], title=row.get('title') or row['source_id'],
                                format=coverage_ladder.LEGACY_ONLY, structure_why_not=coverage_ladder.NOT_HELD)
                   for name in bases for row in (shelves[name] or {}).get('works') or []
                   if row.get('format') == coverage_ladder.LEGACY_ONLY and row.get('source_id')
                   and not any(work.knowledge_base == name and work.id in (row['source_id'], row.get('work')) for work in listed)]
        listed = with_stand_ins(listed, shelves)  # each work once, its stand-in file folded into it
        listed = with_editions(listed, shelves)  # and once over its editions, each kept one folded into the served one
        listed = with_code(listed, code, shelves)  # and its companion code folded into it (#12)
        return [work.model_copy(update={'ladder': coverage_ladder.work_ladder(
            coverage_ladder.row_for(shelves[work.knowledge_base], work.id, work.epub_key),
            work.readings.states if work.readings else None, (shelves[work.knowledge_base] or {}).get('built_at'))})
            for work in listed]

    def with_code(listed: list[sources.Work], code: dict[str, list[readings.CatalogEntry]],
                  shelves: dict[str, dict | None]) -> list[sources.Work]:
        """Each code work folded into the row of the book it accompanies (#12, line 1's ask: "the code work stands under its
        book, as a series or an edition does"), its own work in the search and never a row of its own at the top; one whose
        book is not listed here stands as its own row, its part linking to its files."""
        out = list(listed)
        for name, entries in code.items():
            rows = (shelves.get(name) or {}).get('works') or []
            for entry in entries:
                row = work_editions.row_of(entry.id, rows)
                files = row.get('pages') if row and row.get('format') == 'code' else None
                said = ('companion code' + (f': {entry.code_language}' if entry.code_language else '')
                        + (f", {files:,} {'file' if files == 1 else 'files'}" if files else ''))
                part = sources.CodePart(key=entry.id, title=entry.title, code_language=entry.code_language, files=files,
                                        said=said)
                # the book by the key the search names it by: its source id through the shelf's row or the export's work
                book_row = work_editions.row_of(entry.companion_of, rows) if entry.companion_of else None
                exported = {work['source_id'] for work in bases[name].works()
                            if entry.companion_of and work.get('work') == entry.companion_of}
                keys = {key for key in (entry.companion_of, *(work_editions.keys_of(book_row) if book_row else ()), *exported)
                        if key}
                book = next((work for work in out
                             if work.knowledge_base == name and (work.id in keys or work.epub_key in keys)), None)
                if book is not None:
                    out[out.index(book)] = book.model_copy(update={'code': part})
                else:
                    out.append(sources.Work(knowledge_base=name, id=entry.id, title=entry.title, code=part,
                                            **entry.model_dump(include=CATALOG_FIELDS)))
        return out

    def with_stand_ins(listed: list[sources.Work], shelves: dict[str, dict | None]) -> list[sources.Work]:
        """Every work once (line 1, 20 Nov: three works stood twice): a stand-in file the shelf links to the work it stands in
        for (`stand_in_of`) is folded into that work's row, named in its card, its page list reachable from there; where the
        work's own row has no title, authors, year or the like, the stand-in's catalog entry gives them."""
        out = list(listed)
        for name, built in shelves.items():
            rows = (built or {}).get('works') or []
            for row in rows:
                key = row.get('stand_in_of')
                stand = next((work for work in out if work.knowledge_base == name and work.id == row.get('source_id')), None)
                own = next((one for one in rows if one.get('work') == key and not one.get('stand_in_of')), None) if key else None
                work = next((one for one in out if own and one.knowledge_base == name and one.id == own.get('source_id')), None)
                if stand is None or work is None or stand is work:
                    continue
                said = f"stand-in file beside it: {row.get('file') or stand.id}" + (f", not served: {row['not_served']}" if row.get('not_served') else '')
                fill = {field: getattr(stand, field) for field in CATALOG_FIELDS - {'format'}
                        if not getattr(work, field) and getattr(stand, field)}
                if work.title == work.id and stand.title != stand.id:
                    fill['title'] = stand.title
                out[out.index(work)] = work.model_copy(update={**fill, 'stand_in': sources.StandIn(
                    id=stand.id, file=row.get('file'), said=said, held=row.get('held'), page_list=stand.page_list)})
                out.remove(stand)
        return out

    def with_editions(listed: list[sources.Work], shelves: dict[str, dict | None]) -> list[sources.Work]:
        """Every work once over its editions (the operator's E1.a, 20 Nov: an edition is a level under its work, never a
        group of works): a kept edition's row is folded into its served edition's, which shows its own catalog data and ladder
        and names every edition; a file that looks like another edition and is linked with none says so, a call to look."""
        out = list(listed)
        for name, built in shelves.items():
            rows = (built or {}).get('works') or []
            by_row = {id(row): work for work in out if work.knowledge_base == name
                      and (row := coverage_ladder.row_for(built, work.id, work.epub_key)) is not None}

            def title_of(key: str) -> str:
                row = work_editions.row_of(key, rows)
                work = by_row.get(id(row)) if row else None
                return work.title if work else (row or {}).get('title') or key

            for row in rows:
                said = work_editions.possible_said(row, title_of)
                work = by_row.get(id(row))
                if said and work is not None and work in out:
                    updated = work.model_copy(update={'possible_edition': said})
                    out[out.index(work)] = updated
                    by_row[id(row)] = updated
            for row in rows:
                served_key = work_editions.kept_for(row, rows)
                kept = by_row.get(id(row))
                served_row = work_editions.row_of(served_key, rows) if served_key else None
                served = by_row.get(id(served_row)) if served_row else None
                if kept is None or served is None or kept is served or served not in out:
                    continue
                editions = work_editions.editions_of(served_row, rows, served.title)
                updated = served.model_copy(update={'editions': editions})
                out[out.index(served)] = updated
                by_row[id(served_row)] = updated
                if kept in out:
                    out.remove(kept)
        return out

    def editions_of_record(knowledge_base: str, built: dict | None, row: dict | None, key: str) -> work_editions.Editions | None:
        """A record's work in its editions, this edition's own marked (E1.a): the edition bar and the trail."""
        rows = (built or {}).get('works') or []
        if row is None or work_editions.family_of(row, rows) is None:
            return None
        family = work_editions.family_of(row, rows)
        served_row = work_editions.row_of(family['serves'], rows)
        served_view, served_id = work_editions.target(served_row)
        try:
            title = title_of(knowledge_base, served_id) if served_view == 'pages' and served_id else (served_row or row).get('title')
        except HTTPException:
            title = (served_row or row).get('title')
        own = next((edition['key'] for edition in family['editions'] if edition['key'] in work_editions.keys_of(row)), key)
        return work_editions.editions_of(row, rows, title or key, current=own)

    def free_work(store: readings.Readings, work: sources.Work, html: dict) -> sources.Work:
        """A free catalog work as the Sources list shows it: its readings, its structure, and whether its pages open; a PDF
        the export has no pages of opens its page list, every page not read (8.a), as a licensed catalog entry's does."""
        summary = store.summary(work.id)
        unread = summary is None and store.entry_work(work.id) is not None
        structure = (sources.READ_PAGES if summary else sources.SECTIONS if work.format == 'html'
                     else sources.NOT_READ if unread else None)
        return work.model_copy(update={'readings': summary, **html_structure(work, html), 'structure': structure,
                                       'page_list': summary is not None or unread, **({'not_read': sources.NOT_READ} if unread else {})})

    def unread_structure(entry: readings.CatalogEntry, epubs: dict[str, tuple[str, Path]]) -> dict:
        """A catalog entry without page readings: an EPUB the librarian serves, by its sections; else not read yet."""
        served = epubs.get(entry.file or '')
        if served is None:
            return {'not_read': sources.NOT_READ, 'structure': sources.NOT_READ}
        return {'epub_key': served[0], 'structure': sources.SECTIONS, **epub_structure(served[1])}

    def epub_structure(path: Path) -> dict:
        """An EPUB's sections where it is cut already; while it is not, the list says so and the cut starts in the
        background, so the list never waits the 20 s all of them take."""
        count = epub_works.counted(path)
        if count is None:
            epub_works.warm_in_background()
            return {'structure_why_not': sources.EPUB_COUNTING}
        return {'sections': count}

    def language_of(knowledge_base: str, source_id: str) -> str | None:
        """A work's language as its catalog names it (#11): the free catalog's, or the local licensed one's by the work's id;
        None where the catalog does not list it."""
        if knowledge_base == 'free':
            return next((work.language for work in sources.works() if work.id == source_id), None)
        store = bases.get(knowledge_base)
        entry = store.catalog_entry(source_id) if store else None
        return entry.language if entry else None

    def catalog_fields(store: readings.Readings, source_id: str) -> dict:
        """The licensed catalog's fields of a work the sources view shows, {} where the catalog does not list it."""
        entry = store.catalog_entry(source_id)
        return entry.model_dump(include=CATALOG_FIELDS) if entry else {}

    def html_structure(work: sources.Work, html: dict[str, html_works.HtmlCounts] | None) -> dict:
        """An HTML work's sections and chunks as the index records them, or why they are not known here."""
        if work.format != 'html':
            return {}
        if html is None:
            return {'structure_why_not': html_works.NOT_BUILT}
        counted = html.get(work.id)
        return {'sections': counted.sections, 'chunks': counted.chunks} if counted else {}

    def html_title(knowledge_base: str, source_id: str) -> str:
        """The catalog's title of an HTML work; only the free knowledge base has HTML works."""
        listed = next((work for work in sources.works() if work.id == source_id), None) if knowledge_base == 'free' else None
        if listed is None or listed.format != 'html':
            raise HTTPException(404, f'no HTML work {source_id!r} in the {knowledge_base} knowledge base')
        return listed.title

    @app.get('/api/{knowledge_base}/html/{source_id}')
    def html_work(knowledge_base: readings.KnowledgeBase, source_id: str) -> html_works.HtmlWork:
        """An HTML work (the operator's 6.a): its outline by heading and its sections, from the search index; where the index is
        not built, the work says so and names the command."""
        found = html_works.work(source_id, html_title(knowledge_base, source_id))
        if found is None:
            raise HTTPException(404, f'the search index holds no HTML work {source_id!r}')
        return found.model_copy(update={'language': language_of(knowledge_base, source_id)})

    @app.get('/api/{knowledge_base}/html/{source_id}/sections/{label}')
    def html_section(knowledge_base: readings.KnowledgeBase, source_id: str, label: str) -> html_works.HtmlSection:
        """One section of an HTML work as indexed, its chunks in order with where each stands in the section's text."""
        found = html_works.section(source_id, label, html_title(knowledge_base, source_id))
        if found is None:
            raise HTTPException(404, html_works.NOT_BUILT if not html_works.DATABASE.is_file()
                                else f'no section {label!r} of {source_id!r} in the search index')
        return found

    @app.get('/api/{knowledge_base}/html/{source_id}/articles/{label}')
    def html_article(knowledge_base: readings.KnowledgeBase, source_id: str, label: str) -> html_works.HtmlArticle:
        """The article, chapter or other top unit that holds a section, whole: every section with its original and its
        chunks, its dropped headings at their place, in the work's order."""
        found = html_works.article(source_id, label, html_title(knowledge_base, source_id))
        if found is None:
            raise HTTPException(404, html_works.NOT_BUILT if not html_works.DATABASE.is_file()
                                else f'no section {label!r} of {source_id!r} in the search index')
        # each section's own ladder (V2.a): the search names a free HTML work by its catalog id, a section by its label; a
        # heading dropped as noise has no text served, and none; set on a copy, so no cached article keeps an old ladder
        found = found.model_copy(deep=True)
        for entry in found.entries:
            if entry.section is not None and entry.label and not entry.section.dropped:
                entry.section.ladder = page_ladder.section_ladder(knowledge_base, entry.label, len(entry.section.chunks), source_id,
                                                                  search.ready())
        return found

    def epub_entry(knowledge_base: str, source_id: str) -> tuple[str, str | None]:
        """The title and licence of a licensed EPUB work, from the local licensed catalog by its file, as the sources list
        shows them, else its file's stem and no licence; 404 for any other knowledge base, and before anything is read where
        the licensed one is not served (--public-only, 81.a)."""
        if knowledge_base != 'licensed' or 'licensed' not in bases:
            raise HTTPException(404, f'no EPUB work in the {knowledge_base} knowledge base here')
        path = epub_works.epubs().get(source_id)
        if path is None:
            raise HTTPException(404, f'no EPUB work {source_id!r} in the licensed knowledge base')
        entry = bases['licensed'].catalog_entry_of_file(path.name)
        return (entry.title, entry.licence) if entry else (path.stem, None)

    def epub_of(knowledge_base: str, source_id: str) -> str:
        return epub_entry(knowledge_base, source_id)[0]

    @app.get('/api/{knowledge_base}/epub/{source_id}')
    def epub_work(knowledge_base: readings.KnowledgeBase, source_id: str) -> epub_works.EpubWork:
        """A licensed EPUB work (123.a, the operator's P1.a): its outline by heading and its sections, as the librarian
        serves them, each with the count of its images."""
        title, licence = epub_entry(knowledge_base, source_id)
        found = epub_works.work(source_id, title)
        if found is None:
            raise HTTPException(404, f'no EPUB work {source_id!r}')
        # its ladder and its editions (E1.a): a kept edition's record says so in neutral words, and names every edition
        built = store_of(knowledge_base).shelf_data()
        row = coverage_ladder.row_for(built, source_id, source_id)
        entry = bases['licensed'].catalog_entry_of_file(epub_works.epubs()[source_id].name)
        return found.model_copy(update={'licence': licence, 'language': entry.language if entry else None,
                                        'editions': editions_of_record(knowledge_base, built, row, source_id),
                                        'ladder': coverage_ladder.work_ladder(row, None, (built or {}).get('built_at'))})

    @app.get('/api/{knowledge_base}/epub/{source_id}/sections/{label}')
    def epub_section(knowledge_base: readings.KnowledgeBase, source_id: str, label: str) -> epub_works.EpubSection:
        """One section of a licensed EPUB work: its text in runs, each image where its mark stands, and its neighbours."""
        found = epub_works.section(source_id, label, epub_of(knowledge_base, source_id))
        if found is None:
            raise HTTPException(404, f'no section {label!r} of {source_id!r}')
        # its own ladder (V2.a): the librarian serves a licensed EPUB under the key this route takes, by section label
        _, held = page_ladder.held_of(store_of(knowledge_base), source_id)
        kept = page_ladder.kept_of(store_of(knowledge_base), source_id)  # a kept edition's section says so (E1.a)
        return found.model_copy(update={'ladder': page_ladder.section_ladder(knowledge_base, label, None, source_id, search.ready(),
                                                                             held, kept)})

    @app.get('/api/{knowledge_base}/epub/{source_id}/image', response_class=Response,
             responses={200: {'content': {'image/png': {}, 'image/jpeg': {}, 'image/gif': {}}}})
    def epub_image(knowledge_base: readings.KnowledgeBase, source_id: str, href: str) -> Response:
        """An image of a licensed EPUB work by its path inside the EPUB, read from its zip, never extracted; only one its
        sections name."""
        epub_of(knowledge_base, source_id)
        found = epub_works.image(source_id, href)
        if found is None:
            raise HTTPException(404, f'no image {href!r} in {source_id!r}')
        data, media_type = found
        return Response(content=data, media_type=media_type)

    def code_service(knowledge_base: str) -> Any:
        """The search service a code work is read from (#12), the librarian's own pages; 404 before anything is read or built
        for a knowledge base this app does not serve (--public-only, 81.a)."""
        if knowledge_base not in bases:
            raise HTTPException(404, f'no code work in the {knowledge_base} knowledge base here')
        return search.service()

    @app.get('/api/{knowledge_base}/code/{work}')
    def code_work(knowledge_base: readings.KnowledgeBase, work: str) -> code_works.CodeWork:
        """A book's companion code (#12): its folders and files, each file with the core's catalog entry, and the core's
        count of its units by category."""
        found = code_works.code_work(code_service(knowledge_base), knowledge_base, work, store_of(knowledge_base).shelf_data())
        if found is None:
            raise HTTPException(404, f'no code work {work!r} in the {knowledge_base} knowledge base')
        return found

    @app.get('/api/{knowledge_base}/code/{work}/files/{label:path}')
    def code_file(knowledge_base: readings.KnowledgeBase, work: str, label: str) -> code_works.CodePage:
        """One file of a code work as the librarian serves it (#12): its text and lines, its catalog entry, its neighbours."""
        found = code_works.code_page(code_service(knowledge_base), knowledge_base, work, label,
                                     store_of(knowledge_base).shelf_data())
        if found is None:
            raise HTTPException(404, f'no file {label!r} in the code work {work!r}')
        return found

    @app.get('/api/{knowledge_base}/works/{source_id}/pages')
    def list_pages(knowledge_base: readings.KnowledgeBase, source_id: str) -> readings.WorkPages:
        answer = store_of(knowledge_base).pages(knowledge_base, source_id, title_of(knowledge_base, source_id))
        built = store_of(knowledge_base).shelf_data()  # how far the work is refined (U1.a), its read pages' states with it
        row = coverage_ladder.row_for(built, source_id)
        ladder = coverage_ladder.work_ladder(row, answer.summary.states if answer.summary else None, (built or {}).get('built_at'))
        return answer.model_copy(update={'ladder': coverage_ladder.with_coverage(ladder, answer.coverage),
                                         'editions': editions_of_record(knowledge_base, built, row, source_id),
                                         'language': language_of(knowledge_base, source_id)})

    @app.get('/api/{knowledge_base}/works/{source_id}/pages/{pdf_page}')
    def page_detail(knowledge_base: readings.KnowledgeBase, source_id: str, pdf_page: int) -> readings.PageDetail:
        store = store_of(knowledge_base)
        page = store.page(source_id, pdf_page, title_of(knowledge_base, source_id))
        if page is None:
            raise HTTPException(404, f'no PDF page {pdf_page} of {source_id!r} here')
        # its own ladder (V2.a): the search's page of it, never waited for, the vector index's chunks, the shelf's hold
        key, held = page_ladder.held_of(store, source_id)
        work = store.work(source_id) or store.entry_work(source_id)
        ladder = page_ladder.page_ladder(knowledge_base, source_id, pdf_page, store.any_row(source_id, pdf_page),
                                         store.pdf_of(work) if work and work.get('pdf') else None,
                                         key or (work or {}).get('work'), search.ready(), held,
                                         page_ladder.kept_of(store, source_id))  # a kept edition's page says so (E1.a)
        # its verdicts recorded and not yet exported, shown at once as waiting (E1.a)
        return page.model_copy(update={'ladder': ladder, 'waiting': judged.waiting_on(knowledge_base, source_id, pdf_page)})

    @app.get('/api/{knowledge_base}/works/{source_id}/pages/{pdf_page}/chunks')
    def page_chunk_lines(knowledge_base: readings.KnowledgeBase, source_id: str, pdf_page: int) -> page_chunks.PageChunks:
        """A read page's chunks in semantic search's index, placed in its quoted blocks by their text (the operator's W4,
        21 Nov): the page view's "as served" mode draws them, asked for only when that mode is on."""
        store = store_of(knowledge_base)
        page = store.page(source_id, pdf_page, title_of(knowledge_base, source_id))
        if page is None or page.reading is None:
            raise HTTPException(404, f'no reading of PDF page {pdf_page} of {source_id!r} here')
        key, held = page_ladder.held_of(store, source_id)
        work = store.work(source_id) or store.entry_work(source_id)
        # the index's name of the work: a free work's source id, a licensed one's work key; a file held back is never embedded
        index_source = None if held else source_id if knowledge_base == 'free' else key or (work or {}).get('work')
        kept = page_ladder.kept_of(store, source_id)
        return page_chunks.page_chunks(knowledge_base, source_id, pdf_page, page.reading.blocks, page_ladder.INDEX_DB[knowledge_base](),
                                       index_source, coverage_ladder.not_embedded(knowledge_base, held),
                                       coverage_ladder.KEPT_HELD_BACK if kept else None)

    @app.get('/api/{knowledge_base}/works/{source_id}/pages/{pdf_page}/recall')
    def page_recall(knowledge_base: readings.KnowledgeBase, source_id: str, pdf_page: int, judgement: str) -> readings.Recalled:
        """One judgement of the page shown as it judged (181.a): its reading, read-only, with its findings on the blocks.
        `judgement` is the id a page's judgement carries (`<reading key>:<version>:<again>`)."""
        recalled = store_of(knowledge_base).recall(source_id, pdf_page, judgement)
        if recalled is None:
            raise HTTPException(404, f'no judgement {judgement!r} of PDF page {pdf_page} of {source_id!r}')
        return recalled

    @app.get('/api/{knowledge_base}/works/{source_id}/pages/{pdf_page}/image.png', response_class=Response,
             responses={200: {'content': {'image/png': {}, 'image/jpeg': {}}}})
    def page_image(knowledge_base: readings.KnowledgeBase, source_id: str, pdf_page: int) -> Response:
        image, data = store_of(knowledge_base).image(source_id, pdf_page)
        if data is None:
            raise HTTPException(404, image.why_not)
        return Response(data, media_type=f'image/{image.format}')  # a scan's own JPEG as stored (V2.a), else PNG

    @app.get('/api/{knowledge_base}/works/{source_id}/pages/{pdf_page}/quoted')
    def page_quoted(knowledge_base: readings.KnowledgeBase, source_id: str, pdf_page: int) -> readings.QuotedText:
        """The text the search and the chat quote for the page. Where the export has not cut a book's quoted text on this
        machine, the core cuts it on the first call, about a minute for a large one, and keeps it."""
        quoted = store_of(knowledge_base).quoted(source_id, pdf_page)
        if quoted is None:
            raise HTTPException(404, f'no reading of PDF page {pdf_page} of {source_id!r}')
        return quoted

    @app.get('/api/runs')
    def list_runs() -> runs.RunList:
        """Every run of the pipeline, newest first, both knowledge bases together; a base not listed says why."""
        return runs.run_list(bases, public_only)

    @app.get('/api/{knowledge_base}/runs/{run_id}')
    def show_run(knowledge_base: readings.KnowledgeBase, run_id: int) -> runs.RunDetail:
        """One run whole: its code version, its cost by provider, and the pages it chose a reading for."""
        detail = runs.run_detail(store_of(knowledge_base), knowledge_base, run_id)
        if detail is None:
            raise HTTPException(404, f'no run {run_id} of the {knowledge_base} knowledge base is recorded here')
        return detail

    @app.get('/api/issues')
    def list_issues() -> readings.IssueList:
        return readings.issues(bases)

    @app.get('/api/overview')
    def show_overview() -> overview.Overview:
        """The corpus at a glance (O3.a): a headline summed over the knowledge bases served, and the latest runs."""
        return overview.overview(bases, public_only)

    @app.get('/api/pages')
    def list_pages_across(knowledge_base: readings.KnowledgeBase | None = None, state: str | None = None,
                          person: str | None = None, review: str | None = None, category: str | None = None,
                          route: str | None = None,
                          why_judged: str | None = None, verdict: str | None = None,
                          reason: str | None = None, reader: str | None = None, judge: str | None = None,
                          provider: str | None = None, integrity: str | None = None) -> overview.PageList:
        """The pages behind a figure of the overview: every page served that matches every filter given."""
        given = {'knowledge_base': knowledge_base, 'state': state, 'person': person, 'review': review, 'category': category,
                 'route': route,
                 'why_judged': why_judged, 'verdict': verdict, 'reason': reason, 'reader': reader, 'judge': judge,
                 'provider': provider, 'integrity': integrity}
        return overview.pages(bases, {name: value for name, value in given.items() if value is not None})

    @app.get('/api/shelf')
    def show_shelf() -> shelf_rows.Shelf:
        """Every work of both knowledge bases, how far it is converted and why pages did not pass, as the core counted it;
        under --public-only the licensed shelf is never read."""
        return shelf_rows.shelf_of(bases, public_only)

    @app.get('/api/error-classes')
    def list_error_classes() -> error_classes.ErrorClassList:
        """The judge's and stage 2's findings grouped by kind, block class and work, void ones apart, with their pages."""
        return error_classes.error_classes(bases)

    @app.get('/api/prompts')
    def list_prompts() -> prompts.PromptList:
        """Every version of the reader's and the judge's instructions (148.a): its state, its sha256 now and frozen, why it
        was made, its text, and its change from the version before it."""
        return prompts.prompt_list()

    @app.get('/api/calls')
    def list_calls() -> calls.CallList:
        """The search server's call log, newest first: who asked what, which pages answered, how long it took. Under
        --public-only only the calls that concern the free knowledge base alone, and how many were left out."""
        return calls.call_list(bases, public_only)

    @app.get('/api/librarian')
    def librarian_tools() -> librarian.LibrarianInfo:
        """The librarian's tools as the running server lists them (L1.a), in its staggered order, each with its description,
        a line on what it costs and takes, and its form's fields from its input schema; the page's first call opens its one
        session with the librarian. Where the librarian does not answer, it says so in words."""
        return library.info()

    @app.post('/api/librarian/call', dependencies=[Depends(local_only.guarded)])
    def librarian_call(asked: librarian.CallRequest) -> librarian.LibrarianCall:
        """One tool call over MCP to the running librarian, as an IDE session makes it, its client named "view": the answer
        as it came and its parts for the page. Local only and Origin-checked, since `semantic_search` spends a fraction of a
        cent, and a model call with the router on. 503 where the page calls nothing here or the librarian does not answer,
        404 for a tool it does not offer, 502 where the call failed on its way; a tool's own error is an answer."""
        if not library.enabled:
            raise HTTPException(503, librarian.SWITCHED_OFF)
        try:
            return library.call(asked.tool, asked.arguments)
        except librarian.UnknownTool as error:
            raise HTTPException(404, str(error)) from error
        except librarian.LibrarianDown as error:
            raise HTTPException(503, str(error)) from error
        except librarian.CallFailed as error:
            raise HTTPException(502, str(error)) from error

    @app.get('/api/verdict')
    def verdict_form() -> verdicts.VerdictForm:
        """Whether a person's verdict is taken here (the app started with --allow-verdicts), the lists its dialog offers in
        the core's words, and each knowledge base's background export, which the view follows to reload a page."""
        return judged.form()

    @app.post('/api/verdict', dependencies=[Depends(local_only.guarded)])
    def give_verdict(asked: verdicts.VerdictRequest) -> verdicts.VerdictGiven:
        """A person's verdict on the reading a page shows, the one route here that writes (213.b): recorded at once by the
        core, append-only, and the export set going in the background. 403 when the app was started without
        --allow-verdicts or the request comes from elsewhere; 422 with the core's sentence for an input it refuses."""
        try:
            return judged.give(asked)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.post('/api/verdict/propose', dependencies=[Depends(local_only.guarded)])
    def propose_correction(asked: verdicts.ProposalRequest) -> verdicts.Proposal:
        """✦ propose (W2.a): a model's correction of one block, asked of the core with the judge's findings on it, kept by
        the core and answered again from its store for free; never recorded by itself. 409 with the core's reason where it
        sends nothing; 403 unless the app was started with --allow-verdicts or where the request comes from elsewhere."""
        return judged.propose(asked)

    @app.post('/api/verdict/preview', dependencies=[Depends(local_only.guarded)])
    def preview_correction(asked: verdicts.PreviewRequest) -> verdicts.TablePreview:
        """A correction's text as the table it would be (204.a's path), for the dialog to show before it is sent; writes
        nothing."""
        return judged.preview(asked)

    # Mounted last, so every /api route is matched before it.
    if DIST.is_dir():
        app.mount('/', StaticFiles(directory=DIST, html=True), name='ui')
    if warm_search:  # once every route stands, so the warm-up calls the Sources list and the overview as a request would
        steps = warm_steps(bases, search, list_works, show_overview)
        threading.Thread(target=run_warm, args=(steps,), name='warm', daemon=True).start()
    return app


# What the tests and the schema build import, over the free knowledge base alone: importing this module never builds a
# reader of the licensed export, so serving this object by mistake (`uvicorn backend.diagnostics.app:app`) cannot give
# it out either (review, 2026-11-04). The schema does not depend on which knowledge bases are served. The start command
# builds its own app, with the switch it was given.
app = create_app(public_only=True)
