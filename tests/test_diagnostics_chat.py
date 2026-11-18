"""The chat route (decision 100.a): the core's turn comes back as the log keeps it, without the agent's own words, its
cited pages linked; one agent per process, built on the first message and closed with the app; one log per conversation;
every refusal said. No test here builds the real agent: each one hands the app a fake."""

import json
import uuid

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from backend.chat import turn_log
from backend.diagnostics import app as app_module
from backend.diagnostics import chat
from backend.diagnostics.app import create_app
from test_diagnostics_readings import KELLY, kelly_rows

LOCAL = 'http://127.0.0.1'
THREAD = str(uuid.UUID('12345678-1234-4234-8234-123456789abc'))


class FakeAgent:
    """Answers with the turns it was given, in order; an exception given is raised instead."""

    def __init__(self, *results):
        self.results = list(results)
        self.asked = []
        self.closed = False

    def ask(self, message, thread_id):
        self.asked.append((message, thread_id))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        self.closed = True


def a_knowledge_turn(**overrides):
    """A turn in the core's shape; its passage cites a real free page, its words are invented."""
    row = kelly_rows()[2]
    citation = {'title': 'Kelly paper', 'authors': None, 'where': f"p. {row['pdf_page']}", 'link': None, 'licence': 'CC BY 4.0',
                'licence_url': None, 'text': f"Kelly paper · p. {row['pdf_page']}"}
    turn = {'question': 'What is the Kelly criterion?', 'behaviour': 'answer', 'answer': 'It sizes a bet [1].',
            'quotes': [{'passage': 1, 'text': 'The Kelly criterion sizes a bet.', 'citation': citation}],
            'sources': [{'number': 1, 'chunk_id': 'c1', 'similarity': 0.8, 'text': 'The Kelly criterion sizes a bet.',
                         'citation': citation, 'metadata': {}, 'work': row['work'],
                         'page': {'label': str(row['pdf_page']), 'pdf': str(row['pdf_page']), 'printed': None}}],
            'gaps': None, 'follow_up': None, 'disclaimer': 'Not trading advice. For educational purposes only.'}
    result = {'kind': 'knowledge', 'turn_id': 'a1b2c3d4', 'question': 'What is the Kelly criterion?', 'text': '', 'turn': turn,
              'section': None, 'server': None,
              'tool_calls': [{'id': 't1', 'name': 'search_knowledge_base', 'args': {},
                              'result': {'name': 'search_knowledge_base', 'content': '{}', 'artifact': turn, 'status': 'success'}}],
              'usage': {'input_tokens': 10, 'output_tokens': 5}, 'usd': 0.0021, 'seconds': 9.4, 'model_calls': 2,
              'call_limit_reached': None, 'agent_text': 'never shown', 'discarded_text': 'never shown either',
              'security': [{'check': 'input', 'name': 'Input check', 'status': 'passed', 'detail': '27 characters'}]}
    return {**result, **overrides}


@pytest.fixture
def logs(monkeypatch, tmp_path):
    monkeypatch.setattr(turn_log, 'LOG_DIR', tmp_path / 'logs')
    return tmp_path / 'logs'


def client_with(agent, built=None):
    def factory():
        if built is not None:
            built.append(1)
        return agent
    return TestClient(create_app(public_only=True, chat_agent=factory), base_url=LOCAL)


@pytest.mark.readings
def test_a_turn_comes_back_as_the_log_keeps_it_with_its_pages_linked_and_without_the_agents_words(logs):
    agent = FakeAgent(a_knowledge_turn())
    answer = client_with(agent).post('/api/chat', json={'message': 'What is the Kelly criterion?', 'thread_id': THREAD})
    assert answer.status_code == 200
    shown = answer.json()
    assert agent.asked == [('What is the Kelly criterion?', THREAD)]
    assert 'agent_text' not in shown and 'discarded_text' not in shown
    row = kelly_rows()[2]
    link = {'knowledge_base': 'free', 'source_id': KELLY, 'pdf_page': row['pdf_page']}
    assert shown['turn']['sources'][0]['view'] == link and shown['turn']['quotes'][0]['view'] == link
    # the knowledge turn travels once: the tool call's copy is the log's marker, as `turn_log.stored` writes it
    assert isinstance(shown['tool_calls'][0]['result']['artifact'], str)
    [log] = logs.iterdir()
    [record] = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert record['thread_id'] == THREAD and record['agent_text'] == 'never shown' and shown['logged'] is True
    # a PDF page has its page view and no article
    assert shown['turn']['sources'][0]['article'] is None and shown['turn']['quotes'][0]['article'] is None


@pytest.mark.readings
def test_an_html_section_the_chat_cites_opens_its_article_and_a_quote_from_it_too(logs):
    """Decision 164.a: a source whose work is an HTML work of the free catalog carries its article link, and so does a
    quote from its passage; a work the catalog does not hold as HTML carries none."""
    turn = a_knowledge_turn()
    section = {**turn['turn']['sources'][0], 'number': 2, 'work': 'wikipedia_trading_set', 'page': {'label': 's5', 'pdf': None, 'printed': None}}
    stray = {**section, 'number': 3, 'work': 'no_such_work'}
    quote = {**turn['turn']['quotes'][0], 'passage': 2}
    turn['turn'] = {**turn['turn'], 'sources': [*turn['turn']['sources'], section, stray], 'quotes': [*turn['turn']['quotes'], quote]}
    shown = client_with(FakeAgent(turn)).post('/api/chat', json={'message': 'Sharpe?', 'thread_id': THREAD}).json()
    article = {'knowledge_base': 'free', 'source_id': 'wikipedia_trading_set', 'label': 's5'}
    sources = {source['number']: source for source in shown['turn']['sources']}
    assert (sources[2]['article'], sources[2]['view']) == (article, None)
    assert sources[3]['article'] is None
    assert shown['turn']['quotes'][1]['article'] == article


@pytest.mark.corpus
def test_the_search_names_every_html_work_by_its_catalog_id_and_its_sections_as_the_article_view_does():
    """164.a's mapping rests on this: no article link may lead nowhere. Every HTML work the search serves is keyed by its
    catalog id, its sections labelled `s` and their position from 1, and the article API opens each work's first and
    last section where the index is built on this machine."""
    from backend.diagnostics import html_works, sources
    from backend.diagnostics.search_hits import article_links
    from backend.search import search_server

    pages, works = search_server.free_html_pages()
    catalog = {work.id for work in sources.works() if work.format == 'html'}
    assert set(works) <= catalog and works, 'every HTML work the search serves is a catalog HTML work, by its id'
    article_of = article_links()
    for key in works:
        labels = [page.page for page in pages if page.work == key]  # the label a hit's `page.label` carries
        assert labels and all(article_of('free', key, label) is not None for label in labels), key
        if html_works.DATABASE.is_file():
            title = next(work.title for work in sources.works() if work.id == key)
            for label in (labels[0], labels[-1]):
                assert html_works.article(key, label, title) is not None, (key, label)


@pytest.mark.readings
def test_one_conversation_keeps_one_log_and_another_gets_its_own(logs):
    client = client_with(FakeAgent(a_knowledge_turn(), a_knowledge_turn(), a_knowledge_turn()))
    for thread in (THREAD, THREAD, str(uuid.uuid4())):
        assert client.post('/api/chat', json={'message': 'Kelly?', 'thread_id': thread}).status_code == 200
    lengths = sorted(len(log.read_text(encoding='utf-8').splitlines()) for log in logs.iterdir())
    assert lengths == [1, 2]


@pytest.mark.readings
def test_the_agent_is_built_once_on_the_first_message_and_closed_with_the_app(logs):
    agent, built = FakeAgent(a_knowledge_turn(), a_knowledge_turn()), []
    with client_with(agent, built) as client:
        assert client.get('/api/chat').json()['enabled'] is True and built == []
        for _ in range(2):
            client.post('/api/chat', json={'message': 'Kelly?', 'thread_id': THREAD})
        assert built == [1] and not agent.closed
    assert agent.closed


def test_a_missing_key_is_said_in_the_cores_words_and_tried_again_next_time(logs):
    attempts = []

    def no_key():
        attempts.append(1)
        raise chat.ChatUnavailable('OPENROUTER_API_KEY is not set. Copy .env.example to .env and put the key in it.')

    client = TestClient(create_app(public_only=True, chat_agent=no_key), base_url=LOCAL)
    for _ in range(2):
        answer = client.post('/api/chat', json={'message': 'Kelly?', 'thread_id': THREAD})
        assert answer.status_code == 503 and 'OPENROUTER_API_KEY is not set' in answer.json()['detail']
    assert attempts == [1, 1]


@pytest.mark.readings
def test_a_failed_turn_says_why_in_one_sentence_and_a_stuck_server_is_replaced(logs):
    first, second, built = FakeAgent(TimeoutError('no answer from the search server in 180 s')), FakeAgent(a_knowledge_turn()), []
    agents = [first, second]

    def factory():
        built.append(1)
        return agents.pop(0)

    client = TestClient(create_app(public_only=True, chat_agent=factory), base_url=LOCAL)
    failed = client.post('/api/chat', json={'message': 'Kelly?', 'thread_id': THREAD})
    assert failed.status_code == 502
    assert failed.json()['detail'] == 'The turn failed: TimeoutError: no answer from the search server in 180 s'
    assert first.closed
    assert client.post('/api/chat', json={'message': 'Kelly?', 'thread_id': THREAD}).status_code == 200 and len(built) == 2


@pytest.mark.readings
def test_a_page_image_comes_as_one_data_address_png_or_jpeg_only(logs):
    def server_turn(mime):
        return a_knowledge_turn(kind='server', turn=None, tool_calls=[], server={
            'tool': 'page_image', 'args': {'work': 'kelly', 'page': '3'},
            'answer': {'state': 'found', 'work': 'kelly', 'page': {'label': '3', 'pdf': '3', 'printed': None},
                       'image': {'kind': 'rendered'}, 'sent_image': {'mime_type': mime, 'data': 'iVBORw0KGgo='}}})

    client = client_with(FakeAgent(server_turn('image/png'), server_turn('image/svg+xml')))
    png = client.post('/api/chat', json={'message': 'Show page 3', 'thread_id': THREAD}).json()['server']
    assert png['image_src'] == 'data:image/png;base64,iVBORw0KGgo=' and 'sent_image' not in png['answer']
    svg = client.post('/api/chat', json={'message': 'Show page 3', 'thread_id': THREAD}).json()['server']
    assert svg['image_src'] is None


def test_the_route_refuses_what_it_must(logs):
    switched_off = TestClient(create_app(public_only=True), base_url=LOCAL)
    info = switched_off.get('/api/chat').json()
    assert info['enabled'] is False and info['why_not'] == chat.SWITCHED_OFF and len(info['examples']) >= 3
    assert switched_off.post('/api/chat', json={'message': 'Kelly?', 'thread_id': THREAD}).status_code == 503
    # a page elsewhere that reaches this machine under its own name is refused before anything is asked, by the app's
    # host check (app.TRUSTED_HOSTS) before the route's own
    elsewhere = TestClient(create_app(public_only=True, chat_agent=FakeAgent), base_url='http://attacker.example')
    assert elsewhere.post('/api/chat', json={'message': 'Kelly?', 'thread_id': THREAD}).status_code == 400
    client = client_with(FakeAgent())
    assert client.post('/api/chat', json={'message': 'Kelly?', 'thread_id': '../../x'}).status_code == 422
    assert client.post('/api/chat', json={'message': 'x' * (chat.MESSAGE_LIMIT + 1), 'thread_id': THREAD}).status_code == 422
    # a form post from another site cannot send JSON without a preflight: a plain-text body is no request here
    plain = client.post('/api/chat', content=json.dumps({'message': 'Kelly?', 'thread_id': THREAD}),
                        headers={'content-type': 'text/plain'})
    assert plain.status_code == 422


def test_the_routes_own_host_check_holds_where_the_apps_is_not_in_front_of_it():
    # the second wall, behind app.TRUSTED_HOSTS: the chat's and the verdict route's own check refuses a foreign name
    for host in ('attacker.example', '127.0.0.1.attacker.example', 'testserver'):
        with pytest.raises(HTTPException) as refused:
            chat.local_host_only(Request({'type': 'http', 'headers': [(b'host', host.encode())]}))
        assert refused.value.status_code == 403, host
    for host in ('127.0.0.1:8001', 'localhost', '[::1]:8001'):
        chat.local_host_only(Request({'type': 'http', 'headers': [(b'host', host.encode())]}))


def test_the_app_the_tests_and_the_schema_import_has_the_chat_switched_off():
    assert TestClient(app_module.app, base_url=LOCAL).get('/api/chat').json()['enabled'] is False
