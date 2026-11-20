"""The diagnostics API serves the core's data read-only, and the built UI beside it."""

import copy
import importlib
import json
import sys

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.conversion.store import served_readings
from backend.diagnostics import __main__ as start
from backend.diagnostics import app as app_module
from backend.diagnostics import build, epub_works, readings, sources
from backend.diagnostics.app import app, create_app

@pytest.fixture(autouse=True)
def no_licensed_epubs(monkeypatch):
    """The licensed EPUBs of this machine stay out of every test here: an app over the invented licensed export lists no EPUB
    work (123.a), so no test reads a real licensed file. The EPUB tests hand in an invented one."""
    monkeypatch.setattr(epub_works, 'epubs', lambda: {})


# TestClient's own host, "testserver", is refused like any other name that is not this machine's (app.TRUSTED_HOSTS)
LOCAL = 'http://127.0.0.1'

# The free knowledge base alone: no test reads, or depends on, a licensed export this machine may hold.
client = TestClient(create_app(public_only=True), base_url=LOCAL)
KELLY = 'carta_conversano_kelly_criterion_2020'


def test_the_works_are_the_catalog_in_its_order():
    catalog = json.loads(sources.CATALOG.read_text(encoding='utf-8'))['sources']
    response = client.get('/api/works')
    assert response.status_code == 200
    assert [work['id'] for work in response.json()] == [source['id'] for source in catalog]


def test_every_route_answers_only_a_request_addressed_to_this_machine():
    # DNS rebinding: a page elsewhere points a name of its own at 127.0.0.1 and would read what the GET routes serve
    for host in ('attacker.example', '127.0.0.1.attacker.example', 'testserver'):
        elsewhere = TestClient(client.app, base_url=f'http://{host}:8001')
        for path in ('/api/works', f'/api/free/works/{KELLY}/pages/7', '/api/calls', '/api/issues', '/'):
            assert elsewhere.get(path).status_code == 400, (host, path)
    for local in ('http://127.0.0.1:8001', 'http://localhost:5174', 'http://[::1]:8001'):
        assert TestClient(client.app, base_url=local).get('/api/works').status_code == 200, local


def test_a_work_carries_exactly_the_fields_of_its_model_and_its_knowledge_base():
    works = client.get('/api/works').json()
    assert set(works[0]) == set(sources.Work.model_fields)
    assert {work['knowledge_base'] for work in works} == {'free'}


def test_a_catalog_entry_missing_a_shown_field_is_refused(tmp_path):
    catalog = tmp_path / 'catalog.json'
    catalog.write_text(json.dumps({'sources': [{'id': 'x', 'title': 'No authors'}]}), encoding='utf-8')
    with pytest.raises(ValidationError):
        sources.works(catalog)


@pytest.mark.readings
def test_a_work_read_page_by_page_carries_its_readings_in_figures():
    works = {work['id']: work for work in client.get('/api/works').json()}
    assert works[KELLY]['readings']['pages'] == 15
    assert works['wikipedia_trading_set']['readings'] is None


def test_the_pages_of_an_unknown_work_are_refused():
    assert client.get('/api/free/works/no_such_work/pages').status_code == 404


def test_an_unknown_knowledge_base_is_refused():
    assert client.get(f'/api/other/works/{KELLY}/pages').status_code == 422


def test_a_work_without_page_readings_lists_no_pages():
    assert client.get('/api/free/works/wikipedia_trading_set/pages').json()['pages'] == []


def test_a_work_names_its_knowledge_base_and_each_page_its_printed_label():
    listed = client.get(f'/api/free/works/{KELLY}/pages').json()
    assert listed['knowledge_base'] == 'free'
    rows = readings.Readings().rows_of(KELLY)
    assert [page['printed_label'] for page in listed['pages']] == [row['printed_label'] for row in rows]


@pytest.mark.readings
def test_a_blocked_page_says_why_in_the_providers_words():
    pages = client.get(f'/api/free/works/{KELLY}/pages').json()['pages']
    blocked = [page for page in pages if page['check']['state'] == 'blocked']
    if not blocked:
        pytest.skip('the Kelly paper has no blocked page today: the second reader reads them one by one')
    rows = {row['pdf_page']: row for row in readings.Readings().rows_of(KELLY)}
    assert all(page['error_message'] == rows[page['pdf_page']]['error_message'] for page in blocked)
    assert all(page['error_message'] for page in blocked)


@pytest.mark.corpus
@pytest.mark.readings
def test_a_page_detail_names_its_work_its_knowledge_base_and_its_neighbours():
    page = client.get(f'/api/free/works/{KELLY}/pages/7').json()
    titles = {work.id: work.title for work in sources.works()}
    assert page['title'] == titles[KELLY]
    assert page['knowledge_base'] == 'free'
    assert (page['previous_page'], page['next_page']) == (6, 8)
    assert page['image']['same_as_read'] is True


def test_a_page_that_was_not_read_is_refused():
    assert client.get(f'/api/free/works/{KELLY}/pages/999').status_code == 404


@pytest.mark.corpus
@pytest.mark.readings
def test_the_original_is_served_as_png():
    response = client.get(f'/api/free/works/{KELLY}/pages/1/image.png')
    assert response.status_code == 200 and response.headers['content-type'] == 'image/png'
    assert response.content.startswith(b'\x89PNG')


@pytest.mark.readings
def test_a_page_is_quoted_by_the_cores_one_function_for_it(monkeypatch):
    asked = []

    def quoted_pages(knowledge_base, file_name):
        asked.append((knowledge_base, file_name))
        return {3: 'The Kelly criterion sizes a bet.'}

    monkeypatch.setattr(readings.reading_export, 'quoted_pages', quoted_pages)
    row = readings.Readings().row(KELLY, 3)
    assert client.get(f'/api/free/works/{KELLY}/pages/3/quoted').json() == {
        'knowledge_base': 'free', 'source_id': KELLY, 'pdf_page': 3, 'text': 'The Kelly criterion sizes a bet.'}
    assert asked == [('free', row['file'])]
    # a page the core holds no quoted text for says so; a page never read is refused, as a licensed one is here
    assert client.get(f'/api/free/works/{KELLY}/pages/4/quoted').json()['text'] is None
    assert client.get(f'/api/free/works/{KELLY}/pages/999/quoted').status_code == 404
    assert client.get(f'/api/licensed/works/{KELLY}/pages/3/quoted').status_code == 404


@pytest.mark.readings
def test_the_issues_name_each_work_by_its_title_and_its_knowledge_base():
    titles = {work['id']: work['title'] for work in client.get('/api/works').json()}
    issues = client.get('/api/issues').json()
    assert issues['rows'] and all(row['title'] == titles[row['source_id']] for row in issues['rows'])
    assert issues['knowledge_bases'] == [{'value': 'free', 'count': len(issues['rows'])}]


@pytest.mark.readings
def test_public_only_never_reads_the_licensed_knowledge_base(monkeypatch):
    def refuse():
        raise AssertionError('the licensed knowledge base was read')

    monkeypatch.setattr(readings, 'licensed_readings', refuse)
    public = TestClient(create_app(public_only=True), base_url=LOCAL)
    for path in ('/api/works', f'/api/free/works/{KELLY}/pages', f'/api/free/works/{KELLY}/pages/7', '/api/issues'):
        assert public.get(path).status_code == 200
    assert public.get(f'/api/licensed/works/{KELLY}/pages').status_code == 404


def test_by_default_the_licensed_knowledge_base_is_asked_for(monkeypatch):
    asked = []
    monkeypatch.setattr(readings, 'licensed_readings', lambda: asked.append(True))
    create_app()
    assert asked == [True]


def test_importing_the_app_never_reaches_for_the_licensed_knowledge_base(monkeypatch):
    def refuse():
        raise AssertionError('the licensed knowledge base was reached for at import')

    monkeypatch.setattr(readings, 'licensed_readings', refuse)
    importlib.reload(app_module)
    assert app_module.app.openapi() == app.openapi()


def a_licensed_export(tmp_path) -> readings.Readings:
    """A licensed export with the real one's shape and none of its text: its one work is made of two free Kelly pages, one
    read and one blocked, so its original renders from the tracked PDF."""
    free = readings.Readings()
    work = copy.deepcopy(free.work(KELLY))
    work.update(knowledge_base='licensed', source_id='a_licensed_book', title='a_licensed_book', work='a-licensed-book')
    read, blocked = copy.deepcopy(free.row(KELLY, 1)), copy.deepcopy(free.row(KELLY, 2))
    # p. 2 as the provider blocked it, whether or not a second reader has read it since (18 Nov: they are being read)
    blocked.update(text_file=None, text_sha256=None, route=served_readings.TEXT_LAYER_WHY['blocked'], route_level='fallback',
                   class_when_collected='errored', class_now='errored', error_type='invalid_request_error',
                   error_message='Output blocked by content filtering policy', attempts=[], chosen=None,
                   check={'state': 'blocked', 'reasons': ['errored'], 'judged': False, 'verdict': None, 'judge': None,
                          'why_judged': 'not judged: the reading failed'})
    # a third page read but not yet reached by a check run: the licensed rounds have such rows
    unchecked = {**copy.deepcopy(free.row(KELLY, 4)), 'check': None}
    for row in (read, blocked, unchecked):
        row.update(knowledge_base='licensed', source_id='a_licensed_book', work='a-licensed-book')
    work.pop('outline', None)
    (tmp_path / 'a-licensed-book').mkdir()
    (tmp_path / 'a-licensed-book' / 'p0001.md').write_text(
        (readings.FREE_EXPORT / read['text_file']).read_text(encoding='utf-8'), encoding='utf-8')
    read['text_file'] = 'a-licensed-book/p0001.md'
    (tmp_path / 'a-licensed-book' / 'p0004.md').write_text(
        (readings.FREE_EXPORT / unchecked['text_file']).read_text(encoding='utf-8'), encoding='utf-8')
    unchecked['text_file'] = 'a-licensed-book/p0004.md'
    (tmp_path / 'index.json').write_text(json.dumps({'knowledge_base': 'licensed', 'works': [work],
                                                     'pages': [read, blocked, unchecked]}), encoding='utf-8')
    return readings.Readings(tmp_path)


@pytest.mark.corpus
@pytest.mark.readings
def test_a_licensed_export_is_served_beside_the_free_one_each_row_marked(monkeypatch, tmp_path):
    monkeypatch.setattr(readings, 'licensed_readings', lambda: a_licensed_export(tmp_path))
    both = TestClient(create_app(), base_url=LOCAL)
    licensed = [work for work in both.get('/api/works').json() if work['knowledge_base'] == 'licensed']
    assert [(work['id'], work['title'], work['authors'], work['readings']['pages']) for work in licensed] == \
        [('a_licensed_book', 'a_licensed_book', None, 3)]
    pages = both.get('/api/licensed/works/a_licensed_book/pages').json()
    assert pages['knowledge_base'] == 'licensed' and [page['pdf_page'] for page in pages['pages'] if page['read']] == [1, 2, 4]
    # every page of its PDF stands, those without a reading in their own state (V1.b)
    assert len(pages['pages']) == pages['coverage']['pdf_pages'] and pages['coverage']['read'] == 3
    assert {page['check']['state'] for page in pages['pages'] if not page['read']} == {'not_read'}
    assert pages['pages'][3]['check']['state'] == 'not_yet_checked'
    assert both.get('/api/licensed/works/a_licensed_book/pages/4').json()['check']['state'] == 'not_yet_checked'
    detail = both.get('/api/licensed/works/a_licensed_book/pages/1').json()
    assert detail['knowledge_base'] == 'licensed' and detail['reading'] and detail['image']['same_as_read']
    issues = both.get('/api/issues').json()
    assert {'value': 'licensed', 'count': 1} in issues['knowledge_bases']
    assert [row['source_id'] for row in issues['rows'] if row['knowledge_base'] == 'licensed'] == ['a_licensed_book']
    # the same id under the other knowledge base names another work, and there is none
    assert both.get('/api/free/works/a_licensed_book/pages').status_code == 404


# an invented entry of the local licensed catalog (N1.a): no licensed title stands in a test
ENTRY = {'id': 'a-licensed-book', 'file': None, 'title': 'An Invented Book', 'authors': 'A. Author', 'publisher': 'Invented Press',
         'year': 2001, 'edition': '2nd', 'format': 'pdf', 'shelf': 'trading_finance', 'language': 'en',
         'licence': 'private copy (licensed)', 'notes': 'stand-in file'}
SHOWN = ('title', 'authors', 'publisher', 'year', 'edition', 'format', 'shelf', 'licence', 'notes')


def licensed_with_a_catalog(monkeypatch, folder, catalog_text: str | None) -> TestClient:
    """The invented licensed export with a catalog file of the given text beside it, or none, served beside the free base."""
    folder.mkdir(parents=True, exist_ok=True)
    store = a_licensed_export(folder)
    store.catalog = folder / 'catalog.json'
    if catalog_text is not None:
        store.catalog.write_text(catalog_text, encoding='utf-8')
    monkeypatch.setattr(readings, 'licensed_readings', lambda: store)
    return TestClient(create_app(), base_url=LOCAL)


@pytest.mark.corpus
@pytest.mark.readings
def test_a_stand_in_file_folds_into_its_work_so_each_work_stands_once(monkeypatch, tmp_path):
    # line 1, 20 Nov: a work stood twice, as its legacy text and as its stand-in file; the shelf links them (`stand_in_of`).
    # Invented throughout: a legacy work without a catalog entry, and a stand-in file the catalog lists
    stand_in = {'id': 'an_invented_stand_in', 'file': 'an_invented_stand_in.pdf', 'title': 'An Invented Book', 'authors': 'A. Author',
                'year': 2001, 'format': 'pdf', 'notes': 'stand-in file'}
    client = licensed_with_a_catalog(monkeypatch, tmp_path / 'stand_in', json.dumps({'sources': [stand_in]}))
    store = readings.licensed_readings()
    beside = 'a stand-in file beside the legacy text of its work, which stands'
    store.shelf = lambda: {'works': [
        {'knowledge_base': 'licensed', 'work': 'an-invented-key', 'source_id': 'an_invented_legacy_work', 'title': 'an_invented_legacy_work',
         'format': 'legacy markdown', 'file': None, 'pages': None, 'served': {'pages': 30, 'searchable': 28, 'by_route': {'legacy markdown': 30}}},
        {'knowledge_base': 'licensed', 'work': None, 'source_id': 'an_invented_stand_in', 'title': 'an_invented_stand_in', 'format': 'pdf',
         'file': 'an_invented_stand_in.pdf', 'pages': 40, 'served': {'pages': 0, 'searchable': 0}, 'not_served': beside,
         'held': 'held back by the provenance list', 'stand_in_of': 'an-invented-key'}]}
    licensed = [work for work in client.get('/api/works').json() if work['knowledge_base'] == 'licensed']
    assert [work['id'] for work in licensed].count('an_invented_stand_in') == 0
    [work] = [work for work in licensed if work['id'] == 'an_invented_legacy_work']
    # its ladder its own legacy text; its title and fields from the stand-in's catalog entry, where it had none of its own
    assert work['ladder']['rungs'][0]['said'] == '30 of 30 Markdown pages' and work['format'] == 'legacy markdown'
    # each level its number and its share, as the API serves them (L1.a)
    assert [(rung['number'], rung['share']) for rung in work['ladder']['rungs'][:2]] == [(1, 100), (2, 93)]
    assert (work['title'], work['authors'], work['year']) == ('An Invented Book', 'A. Author', 2001)
    assert work['stand_in'] == {'id': 'an_invented_stand_in', 'file': 'an_invented_stand_in.pdf',
                                'said': f'stand-in file beside it: an_invented_stand_in.pdf, not served: {beside}',
                                'held': 'held back by the provenance list', 'page_list': True}


def licensed_work(client: TestClient) -> dict:
    [work] = [work for work in client.get('/api/works').json() if work['knowledge_base'] == 'licensed' and work['readings']]
    return {name: work[name] for name in SHOWN}


@pytest.mark.corpus
@pytest.mark.readings
def test_a_licensed_work_takes_its_title_and_fields_from_the_local_catalog(monkeypatch, tmp_path):
    # the operator's N1.a, 18 Nov: title, authors, publisher, year, edition, format, shelf, licence and notes, as the free
    # works show theirs; an entry that does not read is left out, the others stand
    both = licensed_with_a_catalog(monkeypatch, tmp_path / 'by_key', json.dumps({'_about': 'invented', 'sources': [ENTRY, {'id': 'x'}]}))
    assert licensed_work(both) == {name: ENTRY[name] for name in SHOWN}
    # the read work alone: the catalog has no other entry that reads
    assert [work['id'] for work in both.get('/api/works').json() if work['knowledge_base'] == 'licensed'] == ['a_licensed_book']
    # the work head and a page name the work by its title too
    assert both.get('/api/licensed/works/a_licensed_book/pages').json()['title'] == 'An Invented Book'
    assert both.get('/api/licensed/works/a_licensed_book/pages/1').json()['title'] == 'An Invented Book'
    # matched by its file where the catalog lists the work under another key, as it lists an unread file
    by_file = {**ENTRY, 'id': 'another_key', 'file': readings.Readings().work(KELLY)['file'], 'title': 'By Its File'}
    both = licensed_with_a_catalog(monkeypatch, tmp_path / 'by_file', json.dumps({'sources': [by_file]}))
    assert licensed_work(both)['title'] == 'By Its File'


@pytest.mark.corpus
@pytest.mark.readings
def test_a_catalog_entry_the_export_holds_no_pages_of_is_listed_after_the_read_works_as_not_read(monkeypatch, tmp_path):
    # the operator's O1.a, 18 Nov: an EPUB or a file not read yet stands in the sources list with its catalog's columns and,
    # in place of page counts, "not read page by page", as a free HTML work without readings stands
    unread = {**ENTRY, 'id': 'an_unread_book', 'file': 'an_unread_book.epub', 'title': 'An Unread Book', 'format': 'epub',
              'year': None, 'edition': None, 'notes': None}
    both = licensed_with_a_catalog(monkeypatch, tmp_path, json.dumps({'sources': [unread, ENTRY]}))
    listed = [work for work in both.get('/api/works').json() if work['knowledge_base'] == 'licensed']
    assert [(work['id'], work['not_read']) for work in listed] == [('a_licensed_book', None), ('an_unread_book', sources.NOT_READ)]
    last = listed[-1]
    assert last['readings'] is None and last['sections'] is None and last['title'] == 'An Unread Book'
    assert {name: last[name] for name in SHOWN} == {name: unread[name] for name in SHOWN}
    # it has no pages to open
    assert both.get('/api/licensed/works/an_unread_book/pages').status_code == 404


@pytest.mark.corpus
@pytest.mark.readings
def test_without_a_readable_licensed_catalog_a_licensed_work_shows_what_it_showed_and_says_nothing(monkeypatch, tmp_path):
    # N1.a: a clone has no catalog, and a broken one must not break the view: today's columns, no error, no warning
    today = {'title': 'a_licensed_book', **{name: None for name in SHOWN if name != 'title'}}
    for case, text in (('missing', None), ('not_json', '{not json'), ('not_a_catalog', '[1, 2]'), ('no_entry', '{"sources": []}')):
        both = licensed_with_a_catalog(monkeypatch, tmp_path / case, text)
        assert licensed_work(both) == today, case
        assert not any(work['not_read'] for work in both.get('/api/works').json()), case
        assert both.get('/api/licensed/works/a_licensed_book/pages').json()['title'] == 'a_licensed_book', case


def test_public_only_never_opens_the_licensed_catalog(monkeypatch):
    # 81.a by construction: the catalog is handed to the licensed store alone, which a public-only app never builds
    def refuse(*_):
        raise AssertionError('a public-only app reached the licensed catalog')

    monkeypatch.setattr(readings, 'catalog_entries', refuse)
    monkeypatch.setattr(readings, 'licensed_readings', refuse)
    public = TestClient(create_app(public_only=True), base_url=LOCAL)
    for path in ('/api/works', '/api/issues', f'/api/free/works/{KELLY}/pages'):
        assert public.get(path).status_code == 200, path
    assert [store.catalog for store in readings.knowledge_bases(public_only=True).values()] == [None]


def test_the_start_switch_reaches_the_app_and_the_search_is_warmed(monkeypatch):
    from backend.diagnostics import chat

    built, served = [], {}
    monkeypatch.setattr(start, 'create_app', lambda public_only, warm_search, chat_agent, allow_verdicts:
                        built.append((public_only, warm_search, chat_agent, allow_verdicts)) or 'the app')
    monkeypatch.setattr(start.uvicorn, 'run', lambda app, **options: served.update(app=app, **options))
    monkeypatch.setattr(sys, 'argv', ['backend.diagnostics', '--public-only'])
    start.main()
    # the start command turns the chat on; --no-chat, as the browser check gives it, leaves no way to a model
    monkeypatch.setattr(sys, 'argv', ['backend.diagnostics', '--no-chat'])
    start.main()
    # verdicts from the page view only where asked for (213.b, 223.a): read-only otherwise
    monkeypatch.setattr(sys, 'argv', ['backend.diagnostics', '--public-only', '--allow-verdicts'])
    start.main()
    assert built == [(True, True, chat.default_agent, False), (False, True, None, False), (True, True, chat.default_agent, True)]
    assert served == {'app': 'the app', 'host': '127.0.0.1', 'port': 8001}


def test_the_built_ui_is_served_at_the_root():
    response = client.get('/')
    assert response.status_code == 200
    assert '<div id="app">' in response.text


def test_an_unknown_api_path_is_not_answered_by_the_ui():
    assert client.get('/api/nothing-here').status_code == 404


def test_the_committed_schema_is_the_one_the_api_serves():
    # The UI's TypeScript types are generated from this file; a stale one means stale types.
    assert json.loads(build.SCHEMA.read_text(encoding='utf-8')) == app.openapi(), \
        'run python -m backend.diagnostics.build'


def test_the_view_takes_its_name_from_the_app_config(monkeypatch):
    """Decision 149.c: a working name, changed in the config alone; without one the view is called Diagnostics."""
    from backend.chat import app_config
    ui = app_config.load()['ui']
    assert client.get('/api/app').json() == {'title': ui['title'], 'subtitle': ui['subtitle']}
    monkeypatch.setattr(app_config, 'load', lambda: {})
    assert client.get('/api/app').json() == {'title': 'Diagnostics', 'subtitle': None}


@pytest.mark.readings
def test_a_judgement_is_recalled_on_its_page_and_an_unknown_one_is_not_found():
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    work = 'openstax_principles_of_finance_2e'
    page = client.get(f'/api/free/works/{work}/pages/5').json()
    recall = next(judgement['recall'] for attempt in page['attempts'] for judgement in attempt['judgements'])
    answer = client.get(f'/api/free/works/{work}/pages/5/recall', params={'judgement': recall})
    assert answer.status_code == 200 and answer.json()['recall'] == recall
    assert client.get(f'/api/free/works/{work}/pages/5/recall', params={'judgement': 'nothing:judge/1:0'}).status_code == 404
