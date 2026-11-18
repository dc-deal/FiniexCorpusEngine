"""The chat as an MCP client of the search server: every tool of the server, called the way an IDE session calls it (98.c)."""

import pytest

from backend.chat import mcp_client
from backend.search import search_server
from test_search_semantic import plan, searching
from test_search_server import a_scan, service


@pytest.fixture
def client(tmp_path):
    a_scan(tmp_path / 'scan.pdf')
    base = service()
    served = search_server.SearchService(
        {'free': ([*base.by_page.values()][:2], {'free-book': base.works['free-book']})},
        images={'free-book': {'pdf': tmp_path / 'scan.pdf'}}, semantic=searching(plan()))
    connected = mcp_client.SearchClient(search_server.build_server(served, None))  # in-process, as the SDK allows in tests
    yield connected
    connected.close()


def test_the_client_sees_every_tool_the_server_offers(client):
    assert sorted(tool.name for tool in client.tools()) == ['open_page', 'page_image', 'search', 'search_works', 'semantic_search',
                                                             'toc', 'works']  # the chat's agent takes five of them (124.a)


def test_a_call_returns_the_server_s_json_and_an_image_as_its_artifact(client):
    assert client.call('search', {'query': 'circuit breaker trial', 'corpus': 'free'})['hits'][0]['work'] == 'free-book'
    image = client.call('page_image', {'work': 'free-book', 'page': '1'})
    assert image['state'] == 'found' and mcp_client.image_bytes(image).startswith(b'\x89PNG')
    assert image['image']['kind'] == 'native' and image['image']['sent_as'] == 'png'  # the server's description is kept


def test_a_tool_gives_the_model_text_and_keeps_the_image_for_the_interface(client):
    tool = next(tool for tool in client.tools() if tool.name == 'page_image')
    message = tool.invoke({'type': 'tool_call', 'id': 'c1', 'name': 'page_image', 'args': {'work': 'free-book', 'page': '1'}})
    assert 'sent_image' not in message.content and message.artifact['sent_image']['mime_type'] == 'image/png'
    assert '"kind": "native"' in message.content  # the server's description of the image reaches the model


def test_the_semantic_search_reaches_the_chat_with_its_passages(client):
    answer = client.call('semantic_search', {'question': 'what does the sharpe ratio measure?'})
    assert answer['state'] == 'found' and answer['hits'][0]['text'].startswith('The Sharpe ratio')


def test_the_chat_names_itself_to_the_server(client, capsys):
    # Decision 99.a: the server's console and call log tell the chat's calls from an IDE session's.
    client.call('works', {})
    assert f"  + chat {mcp_client.client_info().version}" in capsys.readouterr().err


def test_an_evaluation_run_names_itself_apart_from_the_chat(tmp_path, capsys):
    # An evaluation's questions must never be taken for a user's in the call log or the console (6 Nov).
    a_scan(tmp_path / 'scan.pdf')
    base = service()
    served = search_server.SearchService({'free': ([*base.by_page.values()][:2], {'free-book': base.works['free-book']})})
    evaluating = mcp_client.SearchClient(search_server.build_server(served, None), client_name='evaluation')
    try:
        evaluating.call('works', {})
    finally:
        evaluating.close()
    assert '  + evaluation ' in capsys.readouterr().err


def test_a_list_the_server_returns_arrives_whole(client):
    assert [work['work'] for work in client.call('works', {})['result']] == ['free-book']
