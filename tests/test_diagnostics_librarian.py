"""The Librarian page's API (the operator's L1.a, 21 Nov): each tool's form from its input schema, each answer shaped for its
renderer beside the answer as it came, one session with the librarian opened on the first call, a librarian that does not
answer said in words, and the call guarded. Never the real librarian: a fake client, its tools, schemas and answers invented."""

import base64
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from backend.diagnostics import app as app_module
from backend.diagnostics import librarian, local_only
from backend.diagnostics.app import create_app

LOCAL = 'http://127.0.0.1'
PNG = base64.b64encode(b'\x89PNG invented pixels').decode()

# an invented schema of every kind a form draws, as the SDK derives one from a tool's signature
SCHEMA = {'type': 'object', 'required': ['question'], 'properties': {
    'question': {'title': 'Question', 'type': 'string'},
    'hits': {'default': 10, 'title': 'Hits', 'type': 'integer', 'minimum': 1, 'maximum': 50},
    'search_query': {'anyOf': [{'type': 'string'}, {'type': 'null'}], 'default': None},
    'keywords': {'anyOf': [{'items': {'type': 'string'}, 'type': 'array'}, {'type': 'null'}], 'default': None},
    'router': {'default': True, 'type': 'boolean'},
    'corpus': {'default': 'all', 'enum': ['all', 'free', 'licensed'], 'type': 'string'},
    'diagnostics': {'default': False, 'type': 'boolean'},
}}


def a_tool(name: str, description: str = 'Invented: local, no model, milliseconds, free.', schema: dict | None = None):
    return SimpleNamespace(name=name, description=description, input_schema=schema or {'type': 'object', 'properties': {}})


class FakeClient:
    """A session with an invented librarian: its tools, and an answer per tool; every call it gets, as it got it."""

    def __init__(self, answers: dict, tools: list | None = None, fails: Exception | None = None):
        self.server_tools = tools or [a_tool(name) for name in answers]
        self.answers = answers
        self.calls: list[tuple[str, dict]] = []
        self.fails = fails
        self.closed = False

    def call(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, arguments))
        if self.fails:
            raise self.fails
        return self.answers[name]

    def close(self) -> None:
        self.closed = True


class Factory:
    """Opens a fake session, counting how often it was asked to."""

    def __init__(self, client=None, error: Exception | None = None):
        self.client, self.error, self.opened = client, error, 0

    def __call__(self):
        self.opened += 1
        if self.error:
            raise self.error
        return self.client


def test_each_tool_s_form_comes_from_its_input_schema_and_the_view_keeps_the_router_off():
    tool = librarian.tool_of(a_tool('semantic_search', 'Invented: about two seconds, through a paid API.', SCHEMA))
    fields = {field.name: field for field in tool.fields}
    assert [(name, field.kind, field.required) for name, field in fields.items()] == [
        ('question', 'text', True), ('hits', 'integer', False), ('search_query', 'text', False), ('keywords', 'list', False),
        ('router', 'boolean', False), ('corpus', 'choice', False), ('diagnostics', 'boolean', False)]
    assert (fields['hits'].default, fields['hits'].minimum, fields['hits'].maximum) == (10, 1, 50)
    assert fields['corpus'].choices == ['all', 'free', 'licensed']
    # the operator wants the bare semantic search: the router off in the form, the server's own default kept beside it
    assert (fields['router'].default, fields['router'].server_default) == (False, True)
    # and its full answer, which the cards' snippets need (#14): ticked, the server's compact default beside it
    assert (fields['diagnostics'].default, fields['diagnostics'].server_default) == (True, False)
    # a caller's own translation folded under a title of its own
    assert [name for name, field in fields.items() if field.folded] == ['search_query', 'keywords']
    assert tool.folded_title == 'your own translation, which spares the router'
    # another tool keeps the server's defaults and folds nothing
    other = librarian.tool_of(a_tool('search', schema=SCHEMA))
    assert next(field for field in other.fields if field.name == 'router').default is True and other.folded_title is None
    assert next(field for field in other.fields if field.name == 'diagnostics').default is False


def test_a_kept_edition_in_the_works_says_its_own_pages(tmp_path):
    kept = {'work': 'an-invented-first', 'title': 'An Invented Book', 'kept_for': 'an-invented-second', 'pages_kept': 312,
            'pages': 0}
    served = {'work': 'an-invented-second', 'title': 'An Invented Book', 'pages': 340, 'kept_editions': ['an-invented-first']}
    answer = {'result': [kept, served]}
    works = librarian.shaped('works', {}, answer, 0.01).works
    assert [(work.work, work.kept_for, work.pages_kept) for work in works] == [
        ('an-invented-first', 'an-invented-second', 312), ('an-invented-second', None, None)]


def test_the_tools_stand_in_the_server_s_staggered_order_and_a_new_one_after_them():
    listed = [a_tool(name) for name in ('page_image', 'a_new_tool', 'search', 'works', 'toc', 'semantic_search', 'open_page',
                                        'code_catalog', 'search_works')]
    assert [tool.name for tool in librarian.in_order(listed)] == [*librarian.TOOL_ORDER, 'a_new_tool']
    # the two search tools by the view's names, every other by its own (the standing rule); the code catalog after the works
    # it lists (#12)
    assert [librarian.tool_of(tool).label for tool in librarian.in_order(listed)] == [
        'works', 'search_works', 'code_catalog', 'search (BM25)', 'semantic (hybrid)', 'toc', 'open_page', 'page_image',
        'a_new_tool']


def test_a_line_on_cost_and_time_comes_from_the_description_s_own_words():
    assert librarian.cost_of('Search the books by keywords (BM25 over pages): local, no model, milliseconds, free.') == (
        'local · no model · milliseconds · free')
    assert librarian.cost_of('Search by meaning, the licensed one beside the free one where it is given out. About two seconds; '
                             'the question is embedded through a paid API (a fraction of a cent).') == (
        'about two seconds · a paid API · a fraction of a cent')
    assert librarian.cost_of('A tool that says nothing of it.') is None


SEARCH = {'state': 'found', 'query': 'kelly', 'corpus': 'all', 'hits': [
    {'score': 9.1, 'knowledge_base': 'free', 'work': 'a-work', 'title': 'An Invented Paper', 'edition': None, 'year': 2020,
     'page': {'label': '44', 'pdf': '44', 'printed': '27'}, 'section': '2 The model', 'snippet': 'the fraction',
     'licence': 'CC BY', 'route': 'vision reading', 'terms_missing': ['odds'],
     'view_url': 'http://127.0.0.1:8021/#/free/sources/an_invented_paper/page/44'},
    {'score': 3.2, 'knowledge_base': 'free', 'work': 'a-site', 'title': 'An Invented Site', 'page': {'label': 's3', 'pdf': None},
     'snippet': 'a bet', 'view_url': 'javascript:alert(1)'}]}


def test_hits_are_cards_in_rank_with_both_page_numbers_and_their_page_in_this_view():
    call = librarian.shaped('search', {'query': 'kelly'}, SEARCH, 0.0123)
    first, second = call.hits
    assert (first.rank, first.page, first.page_said, first.edition_said, first.terms_missing) == (
        1, '44', 'p. 27 (PDF p. 44)', '2020', ['odds'])
    # the page in this view, whatever address the server links; a link that is no route of this view is none
    assert (first.view, second.view, second.page_said) == ('/free/sources/an_invented_paper/page/44', None, 's3')
    assert (call.head.state, call.head.count, call.head.model_said, call.head.seconds) == ('found', '2 hits', 'no model', 0.012)
    assert call.answer == SEARCH  # the answer as it came, one click away


def test_a_semantic_answer_says_its_relevance_against_its_floor_and_whether_a_model_ran():
    below = {'state': 'found', 'relevance': 0.41, 'relevance_floor': 0.45, 'below_floor': True, 'behaviour': 'answer',
             'plan': {'search_query': 'kelly sizing', 'concept_query': 'bet sizing', 'keywords': ['kelly'], 'fell_back': False,
                      'translated_by': 'the router'},
             'usage': {'router': {'model': 'an-invented-model', 'input_tokens': 120}},
             'hits': [{'title': 'A', 'page': {'label': '3', 'pdf': '3'}, 'text': 'the whole chunk', 'snippet': 'chunk'}]}
    call = librarian.shaped('semantic_search', {'question': 'how big a bet?', 'router': True}, below, 2.0)
    assert call.head.floor_said == 'below the floor (0.410 < 0.450): the books likely say nothing on this'
    assert (call.head.model_ran, call.head.model_said) == (True, 'a model ran: an-invented-model')
    assert (call.plan.search_query, call.plan.keywords, call.hits[0].text) == ('kelly sizing', ['kelly'], 'the whole chunk')
    # the router kept out: no plan of its own to show, no model ran, and a relevance above the floor said so
    bare = {**below, 'relevance': 0.6, 'below_floor': False, 'usage': {'router': {'model': None}},
            'plan': {**below['plan'], 'translated_by': 'nobody: the caller asked for none'}}
    call = librarian.shaped('semantic_search', {'question': 'how big a bet?', 'router': False}, bare, 2.0)
    assert (call.plan, call.head.model_said, call.head.floor_said) == (None, 'no model ran', 'above the floor (0.600 ≥ 0.450)')


def test_works_search_works_toc_and_an_opened_page_each_have_their_parts():
    works = librarian.shaped('works', {}, {'result': [{'work': 'a-work', 'title': 'An Invented Book', 'edition': '2nd',
                                                       'year': 2001, 'pages': 12, 'kept_editions': ['a-work-1st']}]}, 0.01)
    assert (works.head.state, works.head.count, works.works[0].edition_said, works.works[0].kept_editions) == (
        'found', '1 work', '2nd edition, 2001', ['a-work-1st'])
    found = librarian.shaped('search_works', {'query': 'bond'}, {'state': 'found', 'works': [
        {'work': 'a-work', 'title': 'An Invented Book', 'score': 12.5, 'pages_matching': 9, 'pages_with_every_term': 2,
         'best_sections': [{'section': '4 Bonds', 'page': {'label': '88', 'pdf': '88', 'printed': '80'}, 'score': 4.0}]}]}, 0.01)
    assert (found.found_works[0].rank, found.found_works[0].best_sections[0].page_said) == (1, 'p. 80 (PDF p. 88)')
    toc = librarian.shaped('toc', {'work': 'a-work'}, {'state': 'found', 'work': 'a-work', 'source': 'pdf bookmarks', 'left_out': 3,
                                                       'entries': [{'level': 1, 'title': 'One', 'page': '5'},
                                                                   {'level': 2, 'title': 'One point one', 'page': None}]}, 0.01)
    assert [(entry.level, entry.title, entry.page) for entry in toc.contents.entries] == [(1, 'One', '5'), (2, 'One point one', None)]
    assert (toc.contents.left_out, toc.head.count) == (3, '2 entries')
    opened = librarian.shaped('open_page', {'work': 'a-work', 'page': '5'}, {
        'state': 'found', 'work': 'a-work', 'title': 'An Invented Book', 'page': {'label': '5', 'pdf': '5'}, 'route': 'text layer',
        'text': 'The page, word for word.', 'view_url': 'http://127.0.0.1:8021/#/free/sources/a_work/page/5'}, 0.01)
    assert (opened.page.text, opened.page.route, opened.page.view) == ('The page, word for word.', 'text layer', '/free/sources/a_work/page/5')
    # nothing found is an answer, in the server's own words
    missing = librarian.shaped('open_page', {}, {'state': 'nothing found', 'work': 'a-work', 'page': '999'}, 0.01)
    assert (missing.page, missing.head.state) == (None, 'nothing found')


def test_a_page_image_is_drawn_from_png_or_jpeg_alone_and_its_pixels_stay_out_of_the_raw_answer():
    sent = {'state': 'found', 'page': {'label': '5', 'pdf': '5'}, 'image': {'what': 'a render at 150 dpi', 'pixels': '1275 × 1650'},
            'sent_image': {'mime_type': 'image/png', 'data': PNG}}
    call = librarian.shaped('page_image', {'work': 'a-work', 'page': '5'}, sent, 0.2)
    assert call.image.src == f'data:image/png;base64,{PNG}'
    assert call.image.described == [('what', 'a render at 150 dpi'), ('pixels', '1275 × 1650')]
    assert call.answer['sent_image'] == {'mime_type': 'image/png', 'data': f'<{len(PNG):,} base64 characters, shown as the image>'}
    for image in ({'mime_type': 'image/svg+xml', 'data': PNG}, {'mime_type': 'image/png', 'data': 'not base64 "><script>'}):
        assert librarian.shaped('page_image', {}, {**sent, 'sent_image': image}, 0.2).image is None


def test_one_session_is_opened_on_the_first_call_kept_and_named_view(monkeypatch):
    client = FakeClient({'works': {'result': []}, 'search': SEARCH})
    factory = Factory(client)
    service = librarian.LibrarianService(factory, url=lambda: 'http://librarian:8765/mcp')
    assert factory.opened == 0  # nothing opened before the page asks
    service.info()
    service.call('search', {'query': 'kelly'})
    service.call('works', {})
    assert factory.opened == 1 and client.calls == [('search', {'query': 'kelly'}), ('works', {})]
    service.close()
    assert client.closed
    # the default session: the running librarian over HTTP, its calls named "view" in the call log
    from backend.chat import mcp_client

    opened = {}
    monkeypatch.setattr(mcp_client, 'http_server', lambda: 'the http transport')
    monkeypatch.setattr(mcp_client, 'SearchClient', lambda server, client_name: opened.update(server=server, name=client_name))
    librarian.default_client()
    assert opened == {'server': 'the http transport', 'name': 'view'}


def test_a_librarian_that_does_not_answer_is_said_in_words_and_asked_again_after_a_while():
    now = [100.0]
    factory = Factory(error=ExceptionGroup('unhandled errors in a TaskGroup', [ConnectionRefusedError('connection refused')]))
    service = librarian.LibrarianService(factory, url=lambda: 'http://librarian:8765/mcp', clock=lambda: now[0])
    info = service.info()
    assert info.tools == [] and info.why_not == (
        'The librarian does not answer at http://librarian:8765/mcp: ConnectionRefusedError: connection refused')
    with pytest.raises(librarian.LibrarianDown):
        service.call('search', {'query': 'kelly'})
    assert factory.opened == 1  # asked again no sooner than a few seconds on
    now[0] += librarian.DOWN_AGAIN_SECONDS
    factory.error, factory.client = None, FakeClient({'search': SEARCH})
    assert service.call('search', {'query': 'kelly'}).head.state == 'found' and factory.opened == 2


def test_a_call_that_fails_on_its_way_closes_the_session_so_the_next_opens_it_anew():
    broken = FakeClient({'search': SEARCH}, fails=TimeoutError('no answer in 180 s'))
    factory = Factory(broken)
    service = librarian.LibrarianService(factory)
    with pytest.raises(librarian.CallFailed, match='TimeoutError: no answer in 180 s'):
        service.call('search', {'query': 'kelly'})
    assert broken.closed
    factory.client = FakeClient({'search': SEARCH})
    service.call('search', {'query': 'kelly'})
    assert factory.opened == 2


def an_app(factory=None) -> TestClient:
    return TestClient(create_app(public_only=True, librarian_client=factory), base_url=LOCAL)


def test_the_routes_list_the_tools_and_pass_a_call_s_arguments_through_as_given():
    client = FakeClient({'semantic_search': {'state': 'nothing found', 'hits': []}},
                        tools=[a_tool('semantic_search', schema=SCHEMA)])
    app = an_app(Factory(client))
    tools = app.get('/api/librarian').json()
    assert tools['enabled'] and [tool['name'] for tool in tools['tools']] == ['semantic_search']
    asked = {'question': 'what is a bond discount?', 'router': False, 'keywords': ['bond', 'discount']}
    answer = app.post('/api/librarian/call', json={'tool': 'semantic_search', 'arguments': asked})
    assert answer.status_code == 200 and answer.json()['head']['state'] == 'nothing found'
    assert client.calls == [('semantic_search', asked)]  # the router's false reaches the librarian as given
    assert app.post('/api/librarian/call', json={'tool': 'rm_rf', 'arguments': {}}).status_code == 404
    assert app.post('/api/librarian/call', json={'tool': 'works', 'arguments': {}, 'more': 1}).status_code == 422


def test_a_librarian_down_or_switched_off_answers_in_words_and_the_session_ends_with_the_app():
    down = an_app(Factory(error=ConnectionError('connection refused')))
    refused = down.post('/api/librarian/call', json={'tool': 'works', 'arguments': {}})
    assert refused.status_code == 503 and 'does not answer' in refused.json()['detail']
    off = an_app()
    assert off.get('/api/librarian').json() == {'enabled': False, 'url': None, 'why_not': librarian.SWITCHED_OFF, 'tools': []}
    assert off.post('/api/librarian/call', json={'tool': 'works', 'arguments': {}}).status_code == 503
    client = FakeClient({'works': {'result': []}})
    with TestClient(create_app(public_only=True, librarian_client=Factory(client)), base_url=LOCAL) as running:
        running.post('/api/librarian/call', json={'tool': 'works', 'arguments': {}})
    assert client.closed


def test_the_call_is_guarded_by_host_and_origin_as_the_verdicts_are():
    client = FakeClient({'works': {'result': []}})
    app = an_app(Factory(client))
    foreign = app.post('/api/librarian/call', json={'tool': 'works', 'arguments': {}}, headers={'origin': 'https://elsewhere.example'})
    assert foreign.status_code == 403 and client.calls == []
    assert app.post('/api/librarian/call', json={'tool': 'works', 'arguments': {}},
                    headers={'origin': 'http://127.0.0.1:8021'}).status_code == 200
    # the second wall, behind app.TRUSTED_HOSTS: the route's own host check refuses a foreign name
    for host in ('attacker.example', '127.0.0.1.attacker.example', 'testserver'):
        with pytest.raises(HTTPException) as refused:
            local_only.local_host_only(Request({'type': 'http', 'headers': [(b'host', host.encode())]}))
        assert refused.value.status_code == 403, host
    for host in ('127.0.0.1:8001', 'localhost', '[::1]:8001'):
        local_only.local_host_only(Request({'type': 'http', 'headers': [(b'host', host.encode())]}))


def test_the_app_the_tests_and_the_schema_import_calls_no_librarian():
    assert TestClient(app_module.app, base_url=LOCAL).get('/api/librarian').json()['enabled'] is False
