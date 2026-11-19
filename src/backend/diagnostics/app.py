"""The diagnostics UI's server: a read-only JSON API under /api, the chat's one route, and the built UI at /.

The UI is a Vue app whose build is committed in `src/frontend/diagnostics/dist/`, so a reviewer needs no Node: this one
process serves both. During development Vite serves the UI instead and forwards /api here.

A work is addressed within its knowledge base, `/api/<knowledge base>/works/<id>/...`, because an id alone is not a key
(decision 80.a); the lists of works and of issues span every knowledge base served, each row marked with its own. The
chat (decision 100.a) is the one route that spends; see `chat`. The app is read-only unless started with --allow-verdicts;
then one write route, a person's verdict from the page view, local only, Origin-checked, append-only; see `verdicts`.
Every route answers only a request addressed to this machine by name; see `TRUSTED_HOSTS`.
"""

import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.chat import app_config
from backend.diagnostics import (calls, chat, epub_works, error_classes, html_works, overview, page_integrity, prompts,
                                 readings, runs, search_hits, shelf_rows, sources, verdicts)
from backend.search.search_server import MAX_HITS

DIST = sources.ROOT / 'src' / 'frontend' / 'diagnostics' / 'dist'
# the licensed catalog's fields the sources view shows beside a work's title (N1.a)
CATALOG_FIELDS = {'authors', 'publisher', 'year', 'edition', 'format', 'shelf', 'licence', 'notes', 'series'}

# The names a request may address this server by: a page elsewhere can point a domain of its own at 127.0.0.1 (DNS
# rebinding) and read what the GET routes serve, licensed pages and the coding sessions' questions among them, so any
# other Host is refused with 400 before a route runs. Starlette's TrustedHostMiddleware does the check; the chat's and
# the verdict route's own Host and Origin checks stay as a second wall. An IPv6 address keeps its brackets, as the
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


def warm(bases: dict[str, readings.Readings], search: search_hits.Search) -> None:
    """What the first requests after a start would otherwise wait for, one after the other so they do not contend for the
    disk: every reading file's integrity and every export's counts, which the overview, the landing page, needs (line 1,
    10 Nov: 22 s on the operator's first load), then the search index, 20 s free and 50 s with both bases, which only a search needs."""
    page_integrity.warm((store.export, store.rows()) for store in bases.values())
    for store in bases.values():
        overview.counted(store)
    overview.pages(bases, {})  # the Pages view's one load (P1.a), 1.9 s natively when cold
    search.service()
    if 'licensed' in bases:  # the licensed EPUBs cut ahead, so the sources list counts their sections (123.a)
        epub_works.warm()


def create_app(public_only: bool = False, warm_search: bool = False, chat_agent: Callable[[], Any] | None = None,
               allow_verdicts: bool = False, export_run: Callable[[], None] | None = None) -> FastAPI:
    """The app over the knowledge bases it may give out. With `public_only` the licensed one is never read (decision 81.a),
    so a recorded review cannot show a licensed title, page or count. `warm_search` reads every reading file and builds the
    search index while the app comes up, as the start command does; the tests leave it off. `chat_agent` builds the chat's
    agent on its first message; without it the chat is switched off, as in every test, so no test can reach a model.
    `allow_verdicts` opens the one write route, a person's verdict from the page view (213.b, 223.a); off, the app is
    read-only. `export_run` replaces the export a verdict sets going, for the tests, so none writes the real export."""
    bases = readings.knowledge_bases(public_only)
    search = search_hits.Search(public_only)
    if warm_search:
        threading.Thread(target=warm, args=(bases, search), name='warm', daemon=True).start()
    talk = chat.ChatService(chat_agent, bases)
    judged = verdicts.VerdictService(allow_verdicts, bases, run=export_run)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        talk.close()  # the agent's search server is a subprocess: it ends with the app

    app = FastAPI(title='Diagnostics', version='0.8.0', generate_unique_id_function=operation_id, lifespan=lifespan,
                  summary='Read-only views of the knowledge bases: where every source and reading came from.')
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)

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
        for name, store in bases.items():
            if name == 'free':
                html = html_works.counts()
                listed += [work.model_copy(update={'readings': (summary := store.summary(work.id)), **html_structure(work, html),
                                                   'structure': sources.READ_PAGES if summary else sources.SECTIONS if work.format == 'html' else None})
                           for work in sources.works()]
            else:
                # a licensed work's title, authors and the rest from the local licensed catalog, where this machine has one
                # (N1.a); its store reads it, which no --public-only app has
                listed += [sources.Work(knowledge_base=work['knowledge_base'], id=work['source_id'], title=work['title'],
                                        readings=store.summary(work['source_id']), structure=sources.READ_PAGES,
                                        **catalog_fields(store, work['source_id']))
                           for work in store.works()]
                # then the catalog's entries the export has no pages of, as the free HTML works without readings stand (O1.a);
                # an EPUB the librarian serves by section counts its sections (123.a), the others are not read yet
                epubs = {path.name: (key, path) for key, path in epub_works.epubs().items()}
                unread = store.unread_entries()
                listed += [sources.Work(knowledge_base=name, id=entry.id, title=entry.title,
                                        **entry.model_dump(include=CATALOG_FIELDS), **unread_structure(entry, epubs))
                           for entry in unread]
                # and an EPUB the catalog does not list, by its file's stem
                listed += [sources.Work(knowledge_base=name, id=key, title=path.stem, format='epub', epub_key=key,
                                        structure=sources.SECTIONS, **epub_structure(path))
                           for path_name, (key, path) in epubs.items()
                           if not any(entry.file == path_name for entry in unread)]
        return listed

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
        return found

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
        return found.model_copy(update={'licence': licence})

    @app.get('/api/{knowledge_base}/epub/{source_id}/sections/{label}')
    def epub_section(knowledge_base: readings.KnowledgeBase, source_id: str, label: str) -> epub_works.EpubSection:
        """One section of a licensed EPUB work: its text in runs, each image where its mark stands, and its neighbours."""
        found = epub_works.section(source_id, label, epub_of(knowledge_base, source_id))
        if found is None:
            raise HTTPException(404, f'no section {label!r} of {source_id!r}')
        return found

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

    @app.get('/api/{knowledge_base}/works/{source_id}/pages')
    def list_pages(knowledge_base: readings.KnowledgeBase, source_id: str) -> readings.WorkPages:
        return store_of(knowledge_base).pages(knowledge_base, source_id, title_of(knowledge_base, source_id))

    @app.get('/api/{knowledge_base}/works/{source_id}/pages/{pdf_page}')
    def page_detail(knowledge_base: readings.KnowledgeBase, source_id: str, pdf_page: int) -> readings.PageDetail:
        page = store_of(knowledge_base).page(source_id, pdf_page, title_of(knowledge_base, source_id))
        if page is None:
            raise HTTPException(404, f'no reading of PDF page {pdf_page} of {source_id!r}')
        return page

    @app.get('/api/{knowledge_base}/works/{source_id}/pages/{pdf_page}/recall')
    def page_recall(knowledge_base: readings.KnowledgeBase, source_id: str, pdf_page: int, judgement: str) -> readings.Recalled:
        """One judgement of the page shown as it judged (181.a): its reading, read-only, with its findings on the blocks.
        `judgement` is the id a page's judgement carries (`<reading key>:<version>:<again>`)."""
        recalled = store_of(knowledge_base).recall(source_id, pdf_page, judgement)
        if recalled is None:
            raise HTTPException(404, f'no judgement {judgement!r} of PDF page {pdf_page} of {source_id!r}')
        return recalled

    @app.get('/api/{knowledge_base}/works/{source_id}/pages/{pdf_page}/image.png', response_class=Response,
             responses={200: {'content': {'image/png': {}}}})
    def page_image(knowledge_base: readings.KnowledgeBase, source_id: str, pdf_page: int) -> Response:
        image, png = store_of(knowledge_base).image(source_id, pdf_page)
        if png is None:
            raise HTTPException(404, image.why_not)
        return Response(png, media_type='image/png')

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

    @app.get('/api/chat')
    def chat_info() -> chat.ChatInfo:
        """Whether the chat answers here, and its example questions."""
        return talk.info()

    @app.post('/api/chat', dependencies=[Depends(chat.local_host_only)])
    def chat_turn(asked: chat.ChatRequest) -> chat.ChatResult:
        """One turn of the chat, the one route here that spends money: the core's chat agent answers, the turn goes to
        its conversation's log, and the turn comes back as the log keeps it, without the agent's own words."""
        if not talk.enabled:
            raise HTTPException(503, chat.SWITCHED_OFF)
        try:
            return talk.ask(asked.message, str(asked.thread_id))
        except chat.ChatUnavailable as error:
            raise HTTPException(503, str(error)) from error
        except Exception as error:  # a provider or the search server failed: said in one sentence, never as a trace
            raise HTTPException(502, chat.failed(error)) from error

    @app.get('/api/search')
    def search_pages(q: str = '', corpus: search_hits.Corpus = 'all',
                     hits: Annotated[int, Query(ge=1, le=MAX_HITS)] = 10) -> search_hits.SearchAnswer:
        """The search the MCP server answers with, over the knowledge bases given out; "nothing found" is an answer."""
        return search.answer(q, corpus, hits, bases)

    @app.get('/api/verdict')
    def verdict_form() -> verdicts.VerdictForm:
        """Whether a person's verdict is taken here (the app started with --allow-verdicts), the lists its dialog offers in
        the core's words, and each knowledge base's background export, which the view follows to reload a page."""
        return judged.form()

    @app.post('/api/verdict', dependencies=[Depends(verdicts.guarded)])
    def give_verdict(asked: verdicts.VerdictRequest) -> verdicts.VerdictGiven:
        """A person's verdict on the reading a page shows, the one route here that writes (213.b): recorded at once by the
        core, append-only, and the export set going in the background. 403 when the app was started without
        --allow-verdicts or the request comes from elsewhere; 422 with the core's sentence for an input it refuses."""
        try:
            return judged.give(asked)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.post('/api/verdict/preview', dependencies=[Depends(verdicts.guarded)])
    def preview_correction(asked: verdicts.PreviewRequest) -> verdicts.TablePreview:
        """A correction's text as the table it would be (204.a's path), for the dialog to show before it is sent; writes
        nothing."""
        return judged.preview(asked)

    # Mounted last, so every /api route is matched before it.
    if DIST.is_dir():
        app.mount('/', StaticFiles(directory=DIST, html=True), name='ui')
    return app


# What the tests and the schema build import, over the free knowledge base alone: importing this module never builds a
# reader of the licensed export, so serving this object by mistake (`uvicorn backend.diagnostics.app:app`) cannot give
# it out either (review, 2026-11-04). The schema does not depend on which knowledge bases are served. The start command
# builds its own app, with the switch it was given.
app = create_app(public_only=True)
