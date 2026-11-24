import asyncio
import json
import re

import pytest

from backend.configuration import data_paths
from backend.conversion.store import served_readings
from backend.search import page_index, search_server

PROSE = 'The circuit breaker opens after repeated timeouts and stays open for a while before it lets a trial request through. '


def page(work, label, text, path, **fields) -> page_index.Page:
    return page_index.Page(work, label, 1, text, path, **fields)


def service() -> search_server.SearchService:
    free = [page('free-book', '12', PROSE * 3, 'corpus/readings/free-book/p0012.md', pdf='12', printed='10', section='7.2 Breakers',
                 knowledge_base='free', route='vision reading (claude-sonnet-5-5, page/1, validator page/1.1)', reading_key='k12'),
            page('free-book', '13', 'Bond valuation discounts every coupon at the yield to maturity. ' * 5, 'corpus/raw/free.pdf#page=13',
                 pdf='13', knowledge_base='free', route=search_server.TEXT_LAYER_WHY['blocked'])]
    licensed = [page('key-a', '40', 'Retry with backoff and jitter so that clients do not stampede. ' * 5, 'legacy/a.md',
                     pdf='40', line_end=9, section='Stability patterns', knowledge_base='licensed', route='legacy markdown')]
    free_works = {'free-book': search_server.Work('free-book', 'A Free Book', 'free', 'CC BY 4.0', 'per page', 2)}
    licensed_works = {'key-a': search_server.Work('key-a', 'a', 'licensed', 'licensed, local use only', 'legacy markdown', 1)}
    return search_server.SearchService({'free': (free, free_works), 'licensed': (licensed, licensed_works)})


def test_a_hit_carries_everything_a_citation_needs():
    hit = service().search('circuit breaker trial request')['hits'][0]
    assert {key: hit[key] for key in ('knowledge_base', 'work', 'title', 'page', 'section', 'where', 'licence', 'route', 'reading_key')} == {
        'knowledge_base': 'free', 'work': 'free-book', 'title': 'A Free Book', 'page': {'label': '12', 'pdf': '12', 'printed': '10'},
        'section': '7.2 Breakers', 'where': 'corpus/readings/free-book/p0012.md', 'licence': 'CC BY 4.0',
        'route': 'vision reading (claude-sonnet-5-5, page/1, validator page/1.1)', 'reading_key': 'k12'}
    assert 'circuit' in hit['snippet'].lower() and hit['terms_found'] == ['circuit', 'breaker', 'trial', 'request']


def test_a_text_layer_page_says_why_it_is_not_a_reading():
    hit = service().search('bond valuation coupon')['hits'][0]
    assert hit['route'] == 'text layer: the provider blocked the reading' and hit['reading_key'] is None
    assert hit['where'] == 'corpus/raw/free.pdf#page=13'


def test_a_legacy_page_gives_its_line_range():
    assert service().search('backoff jitter')['hits'][0]['where'] == 'legacy/a.md:1-9'


def test_a_search_that_finds_nothing_says_so_and_a_wrong_argument_is_an_error():
    assert service().search('zzqx qqvv') == {'state': 'nothing found', 'query': 'zzqx qqvv', 'corpus': 'all', 'hits': []}
    assert service().search('retry', corpus='elsewhere')['state'] == 'error'
    assert service().search('retry', work='no-such-work')['state'] == 'error'


class NoSemanticSearch:
    """Stands in for the chat's retrieval chain and fails if it is reached."""

    def search(self, question, hits):
        raise AssertionError(f'the semantic search was reached with hits={hits}')


def test_both_searches_take_1_to_50_hits_and_refuse_the_rest_before_any_work(tmp_path):
    # Decision 96.a: without a bound one call could ask for every page and flood the calling model's context.
    served = search_server.SearchService({'free': ([*service().by_page.values()][:2], service().works)},
                                         semantic=NoSemanticSearch())
    for hits in (0, -3, search_server.MAX_HITS + 1):
        assert served.search('circuit breaker', hits=hits) == {
            'state': 'error', 'error': f'hits must be 1 to {search_server.MAX_HITS}; got {hits}', 'hits': []}
        assert served.semantic_search('what is a circuit breaker?', hits)['state'] == 'error'  # the router is never called
    assert served.search('circuit breaker', hits=search_server.MAX_HITS)['state'] == 'found'
    # Through the server the bound holds the same way: the tool answers with its state, not a protocol error.
    server = search_server.build_server(served, tmp_path / 'calls.jsonl')
    result = asyncio.run(server.call_tool('search', {'query': 'circuit breaker', 'hits': 500}))
    assert json.loads(result.content[0].text)['state'] == 'error'
    # the bound stands on the parameter itself (#15), where a client's schema shows it
    hits_said = {tool.name: tool.input_schema['properties']['hits']['description'] for tool in asyncio.run(server.list_tools())
                 if 'hits' in tool.input_schema['properties']}
    assert all(f'1 to {search_server.MAX_HITS}' in hits_said[name] for name in ('search', 'semantic_search'))


def test_the_corpus_and_the_work_filter_one_shared_ranking():
    whole = service()
    assert {hit['knowledge_base'] for hit in whole.search('retry backoff breaker', corpus='free')['hits']} == {'free'}
    assert whole.search('retry backoff', corpus='free')['state'] == 'nothing found'
    assert [hit['work'] for hit in whole.search('retry breaker', work='key-a')['hits']] == ['key-a']
    both = {hit['work']: hit['score'] for hit in whole.search('retry breaker', hits=10)['hits']}
    alone = {hit['work']: hit['score'] for hit in whole.search('retry breaker', corpus='licensed')['hits']}
    assert alone['key-a'] == both['key-a']  # filtering a base out does not change the other's scores (decision 71.a)


def test_open_page_returns_one_page_in_full_or_says_it_is_not_there():
    found = service().open_page('free-book', '13')
    assert found['state'] == 'found' and found['text'].startswith('Bond valuation') and found['page'] == {'label': '13', 'pdf': '13', 'printed': None}
    assert service().open_page('free-book', '99')['state'] == 'nothing found'


def test_open_page_takes_the_number_printed_on_the_page_when_asked(tmp_path):
    # decision 175.a: an index entry or a "see p. 10" names the printed number; as a label it would open another page
    served = service()
    by_print = served.open_page('free-book', '10', printed=True)
    assert by_print['state'] == 'found' and by_print['page'] == {'label': '12', 'pdf': '12', 'printed': '10'}
    assert served.open_page('free-book', '10')['state'] == 'nothing found'  # as a label, 10 is no page of this book
    assert served.open_page('free-book', '77', printed=True) == {'state': 'nothing found', 'work': 'free-book', 'page': '77',
                                                                 'printed': True}
    server = search_server.build_server(served, tmp_path / 'calls.jsonl')
    result = asyncio.run(server.call_tool('open_page', {'work': 'free-book', 'page': '10', 'printed': True}))
    assert json.loads(result.content[0].text)['page']['pdf'] == '12'
    described = {tool.name: tool.description for tool in asyncio.run(server.list_tools())}
    assert 'printed=true' in described['open_page']


def test_a_page_the_ranking_leaves_out_still_opens():
    # The chat cites passages of the whole text, short sections too; open_page must open what it cites (found 2026-11-05).
    base = service()
    short = page('free-book', 's3', 'Circuit breaker. See below.', 'corpus/raw/free.html', knowledge_base='free', searchable=False)
    served = search_server.SearchService({'free': ([*base.by_page.values()][:2] + [short], {'free-book': base.works['free-book']})})
    assert served.open_page('free-book', 's3')['text'] == 'Circuit breaker. See below.'
    assert all(hit['page']['label'] != 's3' for hit in served.search('circuit breaker', corpus='free')['hits'])
    assert len(served.index.pages) == 2  # the ranking's statistics hold the searchable pages only


def test_works_lists_every_work_with_its_knowledge_base_and_licence():
    assert [(work['work'], work['knowledge_base'], work['pages']) for work in service().list_works()] == [
        ('free-book', 'free', 2), ('key-a', 'licensed', 1)]


def test_the_server_offers_exactly_its_eight_tools_and_says_to_start_with_the_shelf():
    server = search_server.build_server(service())
    assert sorted(tool.name for tool in asyncio.run(server.list_tools())) == ['code_catalog', 'open_page', 'page_image', 'search',
                                                                               'search_works', 'semantic_search', 'toc', 'works']
    assert search_server.INSTRUCTIONS.startswith('A library') and 'Start with `works`' in search_server.INSTRUCTIONS


def test_the_http_transport_refuses_a_request_without_the_one_right_token():
    import httpx

    app = search_server.http_app(search_server.build_server(service()), 'secret')

    async def ask(headers: list) -> int:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://host.docker.internal:8765') as client:
            return (await client.post('/mcp', headers=headers, json={})).status_code

    assert asyncio.run(ask([])) == 401
    assert asyncio.run(ask([('Authorization', 'Bearer wrong')])) == 401
    assert asyncio.run(ask([('Authorization', 'Bearer secret'), ('Authorization', 'Bearer secret')])) == 401
    assert 'host.docker.internal:*' in search_server.ALLOWED_HOSTS


def test_the_http_transport_refuses_another_host_even_with_the_right_token():
    """DNS rebinding: a page elsewhere that resolves its own name to 127.0.0.1 sends its own Host header, and the SDK's
    transport security refuses it before any tool runs. The check sits behind the session manager, so the app's lifespan runs."""
    from fastapi.testclient import TestClient  # starlette's own, through the pinned fastapi

    def ask(host: str, origin: str | None = None):  # a session manager runs once, so each request gets an app of its own
        app = search_server.http_app(search_server.build_server(service()), 'secret')
        headers = {'Authorization': 'Bearer secret', 'Accept': 'application/json, text/event-stream'}
        with TestClient(app, base_url=f'http://{host}') as client:
            return client.post('/mcp', headers=headers | ({'Origin': origin} if origin else {}),
                               json={'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})

    refused, allowed = ask('rebound.example:8765'), ask('127.0.0.1:8765')
    assert (refused.status_code, refused.text) == (421, 'Invalid Host header')
    assert allowed.status_code not in (401, 403, 421)  # past both gates, the protocol itself answers (a ping before initialize)
    browser = ask('127.0.0.1:8765', origin='http://some.page.example')  # no origin is allowed: no browser page asks at all
    assert (browser.status_code, browser.text) == (403, 'Invalid Origin header')


def test_a_reading_is_indexed_as_its_words_not_its_markup():
    from backend.conversion.contract.page_contract import parse
    from test_conversion_page_contract import EXPECTED, P179  # a real free page reading, used by the contract tests
    parsed = parse(P179, 'markdown', EXPECTED)
    quoted = served_readings.quotable_text(parsed)  # the one quoted text (decision 93.a); the ranking reads it without LaTeX
    words = set(page_index.tokenize(page_index.without_latex(quoted)))
    assert words and not words & {'td', 'tr', 'th', 'frac', 'text', 'term', 'fn', 'sup', 'bbox'}
    assert all(block.body not in quoted for block in parsed.blocks if block.cls in served_readings.NOT_QUOTED and block.body.strip())


@pytest.mark.parametrize('row, expected', [
    (None, 'unread'),
    ({'error_type': 'invalid_request_error', 'class_now': 'errored'}, 'blocked'),
    ({'text_file': 'w/p1.md', 'class_now': 'malformed'}, 'malformed'),
    ({'text_file': 'w/p1.md', 'class_now': 'no_page'}, 'no_page'),
    ({'text_file': 'w/p1.md', 'class_now': 'ok', 'check': {'state': 'issue'}}, 'issue'),
    ({'text_file': 'w/p1.md', 'class_now': 'ok', 'check': {'state': 'stopped'}}, 'stopped'),
    ({'text_file': 'w/p1.md', 'class_now': 'ok', 'check': {'state': 'ok_unjudged'}}, None),
])
def test_a_reading_is_served_only_when_it_passed_and_is_not_in_the_bin(row, expected):
    assert search_server.text_layer_why(row) == expected


def test_a_page_without_a_printed_number_has_none():
    from backend.conversion.contract.page_contract import parse
    from test_conversion_page_contract import P179, changed
    assert search_server.printed_of(parse(changed('printed_label: "165"', 'printed_label: none'), 'markdown')) is None
    assert search_server.printed_of(parse(P179, 'markdown')) not in (None, 'none')


def test_a_download_stamp_never_reaches_the_index():
    assert search_server.strip_stamps('Real prose.\nDownloaded from SomeSite.example\nMore prose.', ['somesite.example']) == 'Real prose.\nMore prose.'


def test_a_nul_in_a_text_layer_never_reaches_the_index_with_or_without_marks():
    # the database cannot store NUL, so the files must not serve it either (22 Nov: 315 licensed pages differed by it)
    assert search_server.strip_stamps('Brownian\x00 motion', []) == 'Brownian motion'
    assert search_server.strip_stamps('Brownian\x00 motion\nDownloaded from SomeSite.example', ['somesite.example']) == 'Brownian motion'


def test_a_legacy_page_names_its_file_as_every_route_does_never_by_this_machines_path(monkeypatch, tmp_path):
    folder = data_paths.WORKING / 'legacy_markdown'
    monkeypatch.setattr(search_server, 'LEGACY', folder)
    monkeypatch.setattr(search_server.page_index, 'load_works', lambda root, keys, stems: [
        page_index.Page('work-a', '3', 1, 'Some prose on page three.', (folder / 'work_a.md').as_posix())])
    monkeypatch.setattr(search_server, 'legacy_offsets', lambda: {})
    pages = search_server.legacy_by_work({'work-a': 'work_a'}, [])['work-a']
    assert [page.path for page in pages] == ['_work/legacy_markdown/work_a.md']
    assert data_paths.locate(pages[0].path) == folder / 'work_a.md'  # and it still finds the file


def test_the_free_pdfs_are_served_without_the_private_store(monkeypatch, tmp_path):
    monkeypatch.setattr(search_server, 'EXPORT', tmp_path / 'no_export')  # as on a fresh clone without readings
    pages, works = search_server.free_pdf_pages()
    present = [work for work in works.values() if work.pages]
    if not present:
        pytest.skip('the free PDFs are not downloaded: python -m backend.ingestion.acquire')
    assert all(page.route == search_server.TEXT_LAYER_WHY['unread'] for page in pages)


def test_every_tool_call_is_logged_without_any_page_text(tmp_path, capsys):
    log_path = tmp_path / 'calls.jsonl'
    server = search_server.build_server(service(), log_path)
    asyncio.run(server.call_tool('search', {'query': 'circuit breaker trial', 'corpus': 'free'}))
    asyncio.run(server.call_tool('open_page', {'work': 'free-book', 'page': '12'}))
    records = [json.loads(line) for line in log_path.read_text(encoding='utf-8').splitlines()]
    assert [(record['tool'], record['state']) for record in records] == [('search', 'found'), ('open_page', 'found')]
    assert records[0]['answered'] == [{'knowledge_base': 'free', 'work': 'free-book', 'label': '12', 'pdf': '12'}]
    assert records[0]['query'] == 'circuit breaker trial' and records[0]['client'] is None  # called without any client
    assert 'circuit breaker opens' not in log_path.read_text(encoding='utf-8')  # never a snippet or a page
    console = capsys.readouterr().err
    # Decision 99.a: the console shows what was asked, a question in quotes and a page by its work and label; never a page's text.
    assert '"circuit breaker trial"' in console and 'free-book 12' in console and 'circuit breaker opens' not in console


def test_a_console_line_is_one_line_with_the_question_last_and_shortened(monkeypatch):
    question = 'What is a maximum\ndrawdown,   and how is it measured over a whole trading account and its history?'
    asked = {'query': question}
    monkeypatch.setattr(search_server, 'console_width', lambda: None)  # a pipe or a file: the question at its 60 characters
    line = search_server.console_line('semantic_search', 'found', 10, 9.882, 'claude-code', asked)
    head, text = line.split('  "', 1)
    assert '\n' not in line and text.startswith('What is a maximum drawdown, and how') and text.endswith('…"')
    assert len(text) == search_server.CONSOLE_TEXT + 1 and head.endswith('claude-code  found 10         9882 ms')
    monkeypatch.setattr(search_server, 'console_width', lambda: 100)  # a terminal: the line fits it
    assert len(search_server.console_line('semantic_search', 'found', 10, 9.882, 'claude-code', asked)) <= 99
    monkeypatch.setattr(search_server, 'console_width', lambda: 60)  # too narrow for a question: the columns alone
    assert '"' not in search_server.console_line('semantic_search', 'nothing found', 0, 0.2, 'chat', asked)


def test_a_client_gets_one_line_before_its_first_call_and_its_name_in_the_log(tmp_path, capsys, monkeypatch):
    import mcp
    import mcp.types as types

    monkeypatch.setattr(search_server, 'console_width', lambda: None)
    log_path = tmp_path / 'calls.jsonl'
    server = search_server.build_server(service(), log_path)

    async def asks(name: str, *queries: str) -> None:
        async with mcp.Client(server, client_info=types.Implementation(name=name, version='2.1.4')) as client:
            for query in queries:
                await client.call_tool('search', {'query': query, 'corpus': 'free'})

    asyncio.run(asks('claude-code', 'circuit breaker', 'trial request'))
    asyncio.run(asks('chat', 'circuit breaker'))
    asyncio.run(asks('claude-code', 'bond valuation'))  # the same client again, without a session of its own: no new line
    console = capsys.readouterr().err.splitlines()
    assert [line.split('  + ', 1)[1] for line in console if '  + ' in line] == ['claude-code 2.1.4', 'chat 2.1.4']
    records = [json.loads(line) for line in log_path.read_text(encoding='utf-8').splitlines()]
    assert [(r['client'], r['client_version'], r['session']) for r in records] == [
        ('claude-code', '2.1.4', None), ('claude-code', '2.1.4', None), ('chat', '2.1.4', None), ('claude-code', '2.1.4', None)]


def test_a_session_is_a_client_of_its_own_and_a_request_without_one_is_its_name_and_version():
    from types import SimpleNamespace as Fake

    named = Fake(client_info=Fake(name='claude-code', version='2.1.4'))
    session = {'Mcp-Session-Id': '69922933b29346c6'}
    legacy = search_server.caller_of(Fake(session=Fake(client_params=named), headers=session, protocol_version='2025-11-25'))
    assert legacy == {'client': 'claude-code', 'client_version': '2.1.4', 'session': '69922933b29346c6'}
    assert search_server.client_key(legacy) == '69922933b29346c6'
    modern = search_server.caller_of(Fake(session=Fake(client_params=named), headers=None, protocol_version='2026-07-28'))
    assert search_server.client_key(modern) == ('claude-code', '2.1.4')
    # A 2026-07-28 request passes no session manager: a session header on it is the client's word, and ignored (review of 99.a).
    forged = search_server.caller_of(Fake(session=Fake(client_params=named), headers=session, protocol_version='2026-07-28'))
    assert forged['session'] is None
    anonymous = Fake(session=Fake(client_params=None), headers=None, protocol_version='2026-07-28')
    assert search_server.caller_of(anonymous) == search_server.NO_CALLER
    assert search_server.client_line('claude-code', '2.1.4', '69922933b29346c6').endswith('  + claude-code 2.1.4  session 69922933')
    assert search_server.client_line(None, None, None).endswith('  + unknown client')


def test_what_a_client_sends_reaches_the_terminal_without_a_control_character(monkeypatch):
    # A question, a client name and a session id come from outside; an escape sequence could clear or rewrite the terminal.
    monkeypatch.setattr(search_server, 'console_width', lambda: None)
    line = search_server.console_line('search', 'found', 1, 0.01, 'evil\x1b[31m', {'query': 'drawdown\x1b[2J\x07 ratio\r\nnext'})
    assert '\x1b' not in line and '\x07' not in line and '\r' not in line and line.endswith('"drawdown[2J ratio next"')
    assert '\x1b' not in search_server.client_line('claude\x1b]0;owned\x07', '2.1', 'abc\x1bdef12')


def test_a_wide_question_is_cut_by_the_columns_it_takes_not_by_its_characters(monkeypatch):
    # The review of 99.a: a CJK question counted 99 characters and took 129 columns in a 100-column terminal.
    monkeypatch.setattr(search_server, 'console_width', lambda: 100)
    line = search_server.console_line('search', 'found', 3, 0.01, '客户端程序', {'query': '最大回撤是什么意思以及如何计算它' * 4})
    assert search_server.cells(line) <= 99 and line.endswith('…"')
    head = search_server.console_line('search', 'found', 3, 0.01, '客户端程序', {})
    assert search_server.cells(head) == search_server.cells(search_server.console_line('search', 'found', 3, 0.01, 'chat', {}))
    assert search_server.cells('áb') == 2 and search_server.cells('最') == 2  # a combining accent takes no column


def test_a_client_s_odd_text_neither_fails_the_call_nor_splits_its_record(tmp_path, capsys):
    # The review of 99.a: a lone surrogate could not be written as UTF-8 and failed a search that had succeeded; U+2028 and
    # U+0085 split the record for any reader of lines. ASCII JSON writes both as escapes.
    log_path = tmp_path / 'calls.jsonl'
    odd = {'client': 'bad\ud800name', 'client_version': '1\u00852', 'session': None}
    search_server.log_call('search', {'state': 'found', 'hits': []}, 0.01, log_path, odd, query='draw down\ud800')
    (line,) = log_path.read_text(encoding='utf-8').split('\n')[:-1]
    assert line.isascii() and json.loads(line)['client'] == 'bad\ud800name' and json.loads(line)['query'] == 'draw down\ud800'
    blocked = tmp_path / 'a folder, not a file'
    blocked.mkdir()
    capsys.readouterr()
    search_server.log_call('search', {'state': 'found', 'hits': []}, 0.01, blocked, query='kept')  # a folder: must not raise
    assert 'corpus-search: the call log was not written (' in capsys.readouterr().err


def test_stderr_writes_utf8_through_a_pipe_as_an_mcp_host_reads_it():
    import subprocess
    import sys

    script = ("import sys; from backend.search import search_server; search_server.utf8_stderr(); "
              "print('Volatilität → ok …', file=sys.stderr)")
    done = subprocess.run([sys.executable, '-c', script], capture_output=True, timeout=120)
    assert done.stderr.decode('utf-8').strip() == 'Volatilität → ok …'


def test_public_only_never_reads_the_licensed_knowledge_base(monkeypatch):
    def refuse():
        raise AssertionError('the licensed knowledge base was read')
    monkeypatch.setattr(search_server, 'free_pages', lambda: ([], {}))
    monkeypatch.setattr(search_server, 'licensed_pages', refuse)
    assert list(search_server.knowledge_bases(public_only=True)) == ['free']
    with pytest.raises(AssertionError, match='licensed'):
        search_server.knowledge_bases()


def a_scan(path, size=(300, 400)) -> None:
    """A one-page PDF that is one gray image over the whole page: 300 x 400 pixels on 3 x 4 inches, so 100 dpi."""
    import io

    import pymupdf
    from PIL import Image as PILImage

    buffer = io.BytesIO()
    PILImage.new('L', size, 200).save(buffer, 'PNG')
    document = pymupdf.open()
    page = document.new_page(width=216, height=288)
    page.insert_image(page.rect, stream=buffer.getvalue())
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)


def image_service(tmp_path) -> search_server.SearchService:
    a_scan(tmp_path / 'scan.pdf')
    images = {'free-book': {'pdf': tmp_path / 'scan.pdf'}, 'key-a': {'refused': 'no page image: no file of this text is held'}}
    base = service()
    return search_server.SearchService({'free': ([*base.by_page.values()][:2], {'free-book': base.works['free-book']}),
                                        'licensed': ([*base.by_page.values()][2:], {'key-a': base.works['key-a']})}, images)


def test_a_scanned_page_comes_with_its_own_pixels_and_says_so(tmp_path):
    answer = image_service(tmp_path).page_image('free-book', '1')
    assert answer['state'] == 'found' and answer['format'] == 'png'
    assert {key: answer['image'][key] for key in ('kind', 'width', 'height', 'dpi')} == {'kind': 'native', 'width': 300, 'height': 400, 'dpi': 100}


def test_a_page_without_an_image_says_why(tmp_path):
    served = image_service(tmp_path)
    assert served.page_image('key-a', '40')['why'].startswith('no page image')
    assert served.page_image('free-book', '9')['state'] == 'nothing found'
    assert served.page_image('nobody', '1')['state'] == 'nothing found'


def test_the_tool_answers_with_a_description_and_the_image(tmp_path):
    server = search_server.build_server(image_service(tmp_path), None)
    content = asyncio.run(server.call_tool('page_image', {'work': 'free-book', 'page': '1'})).content
    assert [block.type for block in content] == ['text', 'image']
    assert json.loads(content[0].text)['image']['kind'] == 'native' and content[1].mime_type == 'image/png'


def test_the_start_says_the_version_the_address_the_bases_the_routes_and_the_tools(monkeypatch):
    from backend.conversion.store import pipeline_db

    monkeypatch.setattr(pipeline_db, 'code_version', lambda: {'code_commit': 'aaf53cd0', 'code_clean': 0, 'code_sha256': 'f' * 64})
    lines = search_server.banner(service(), ['search', 'open_page', 'works', 'page_image'], 8765, public_only=False)
    text = '\n'.join(lines)
    assert 'commit aaf53cd with uncommitted changes' in text and 'http://127.0.0.1:8765/mcp' in text
    assert 'free 2 pages in 1 works' in text and 'licensed 1 pages in 1 works' in text
    assert 'vision reading 1' in text and 'text layer 1' in text and 'legacy markdown 1' in text
    assert 'page_image' in lines[4] and search_server.route_kind('text layer: the reader declined the page') == 'text layer'


def a_pdf(path, pages) -> None:
    import pymupdf

    document = pymupdf.open()
    for number in range(1, pages + 1):
        document.new_page().insert_text((72, 72), f'page {number}')
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)


def a_licensed_shelf(tmp_path, monkeypatch):
    """A licensed shelf as `licensed_pages` reads it: legacy Markdown with numbered markers (book_a) and without (book_c), the
    stand-in of a work whose legacy text stands (book_b), a new work (new_doc), a held file, and the readings' export."""
    from backend.conversion.reading import reading_cells
    from backend.conversion.store import reading_export
    from test_conversion_page_contract import P179

    legacy, archive, export = tmp_path / 'legacy', tmp_path / 'archive', tmp_path / 'readings'
    legacy.mkdir()
    (legacy / 'keys.json').write_text(json.dumps({'keys': {'key-a': 'book_a', 'key-b': 'book_b', 'key-c': 'book_c'}}), encoding='utf-8')
    (legacy / 'book_a.md').write_text(f'# Breakers\n<!-- page 1 -->\nlegacy one {PROSE * 3}\n<!-- page 3 -->\n## Later\nlegacy three {PROSE * 3}\n',
                                      encoding='utf-8')
    (legacy / 'book_b.md').write_text(f'<!-- page 1 -->\nlegacy bee {PROSE * 3}\n', encoding='utf-8')
    (legacy / 'book_c.md').write_text(f'<!-- page None -->\nlegacy sea {PROSE * 3}\n<!-- page None -->\nlegacy sea two {PROSE * 3}\n',
                                      encoding='utf-8')
    for name, count in [('book_a', 3), ('book_b__alt', 1), ('book_c', 2), ('new_doc', 2), ('held', 1)]:
        a_pdf(archive / f'{name}.pdf', count)
    (export / 'w').mkdir(parents=True)
    (export / 'w' / 'p.md').write_text(P179, encoding='utf-8')
    reading = {'text_file': 'w/p.md', 'form': 'markdown', 'class_now': 'ok', 'model': 'claude-sonnet-5-5', 'contract': 'page/1',
               'validator': 'page/1.2'}
    rows = [{**reading, 'file': 'book_a.pdf', 'pdf_page': 1, 'reading_key': 'ka1', 'check': {'state': 'ok_unjudged'}},
            {**reading, 'file': 'book_a.pdf', 'pdf_page': 2, 'reading_key': 'ka2', 'check': {'state': 'ok_judged'}},
            {**reading, 'file': 'book_a.pdf', 'pdf_page': 3, 'reading_key': 'ka3', 'check': {'state': 'issue'}},
            {**reading, 'file': 'book_c.pdf', 'pdf_page': 1, 'reading_key': 'kc1', 'check': {'state': 'ok_unjudged'}},
            {**reading, 'file': 'book_b__alt.pdf', 'pdf_page': 1, 'reading_key': 'kb1', 'check': {'state': 'ok_unjudged'}}]
    (export / 'index.json').write_text(json.dumps({'pages': rows}), encoding='utf-8')
    monkeypatch.setattr(search_server, 'REPO', tmp_path)
    monkeypatch.setattr(search_server, 'LEGACY', legacy)
    monkeypatch.setattr(search_server, 'LICENSED_ARCHIVE', archive)
    monkeypatch.setattr(search_server, 'LICENSED_EXPORT', export)
    monkeypatch.setattr(search_server, 'PROVENANCE', tmp_path / 'none.json')
    monkeypatch.setattr(search_server, 'LICENSED_SUBJECTS', tmp_path / 'subjects.json')
    monkeypatch.setattr(search_server, 'LEGACY_OFFSETS', tmp_path / 'offsets.json')
    (tmp_path / 'stand_ins.json').write_text(json.dumps({'suffix': '__alt', 'works': []}), encoding='utf-8')
    monkeypatch.setattr(search_server, 'STAND_INS', tmp_path / 'stand_ins.json')
    monkeypatch.setattr(search_server, 'LICENSED_CATALOG', tmp_path / 'catalog.json')
    monkeypatch.setattr(reading_cells, 'may_send', lambda name: name != 'held.pdf')
    monkeypatch.setattr(reading_export, 'quoted_pages', lambda base, file: {n: f'quoted {file} p{n} {PROSE * 3}' for n in range(1, 4)})


def a_licensed_rule(tmp_path) -> None:
    """Beside `a_licensed_shelf`: an invented rule page in the archive, which the local catalog describes by its layout, and an
    HTML file it names without one."""
    from test_ingestion_html_labelled_sections import BASE, RULE, TITLE

    (tmp_path / 'archive' / 'invented_rule.html').write_text(RULE, encoding='utf-8')
    (tmp_path / 'archive' / 'bare.html').write_text(RULE, encoding='utf-8')
    entries = [{'id': 'invented_rule', 'file': 'invented_rule.html', 'title': TITLE, 'format': 'html', 'url': BASE,
                'labelled_sections': {'content': '#body-text'}},
               {'id': 'bare', 'file': 'bare.html', 'title': 'Bare', 'format': 'html', 'url': BASE}]
    (tmp_path / 'catalog.json').write_text(json.dumps({'sources': entries}), encoding='utf-8')


def test_a_checked_licensed_reading_takes_the_place_of_its_legacy_page_and_the_rest_stays(tmp_path, monkeypatch):
    a_licensed_shelf(tmp_path, monkeypatch)
    pages, works = search_server.licensed_pages()
    book_a = {page.page: page for page in pages if page.work == 'key-a'}
    assert book_a['1'].reading_key == 'ka1' and book_a['1'].text.startswith('quoted book_a.pdf p1')
    assert book_a['1'].section == 'Breakers' and book_a['1'].route.startswith('vision reading (claude-sonnet-5-5')
    assert book_a['2'].reading_key == 'ka2' and book_a['2'].section == 'Breakers'  # the legacy text had no page 2: it joins
    assert book_a['3'].route == 'legacy markdown' and book_a['3'].text.startswith('## Later')  # the judge's issue: legacy stays
    assert [page.page for page in pages if page.work == 'key-a'] == ['1', '2', '3']
    assert works['key-a'].route == 'per page' and works['key-a'].pages == 3 and works['key-a'].title == 'book_a'


def test_a_legacy_text_without_pdf_page_numbers_and_a_stand_in_beside_its_legacy_text_stay_as_they_were(tmp_path, monkeypatch):
    a_licensed_shelf(tmp_path, monkeypatch)
    pages, works = search_server.licensed_pages()
    assert {page.route for page in pages if page.work in ('key-b', 'key-c')} == {'legacy markdown'}
    assert works['key-c'].route == 'legacy markdown' and 'book_b__alt' not in works


def test_a_new_licensed_work_is_served_from_its_readings_and_text_layer_and_a_held_file_without_its_images(tmp_path,
                                                                                                         monkeypatch):
    a_licensed_shelf(tmp_path, monkeypatch)
    pages, works = search_server.licensed_pages()
    new = [page for page in pages if page.work == 'new_doc']
    assert [(page.page, page.pdf, page.route) for page in new] == [('1', '1', search_server.TEXT_LAYER_WHY['unread']),
                                                                    ('2', '2', search_server.TEXT_LAYER_WHY['unread'])]
    assert new[0].path == 'archive/new_doc.pdf#page=1' and new[0].knowledge_base == 'licensed'
    assert works['new_doc'].licence == search_server.LICENSED_LICENCE
    assert search_server.image_sources()['new_doc'] == {'pdf': tmp_path / 'archive' / 'new_doc.pdf'}
    # the operator's 1.a, 24 Nov: a held file is served from its text layer, never sent to a provider as an image
    assert 'held' in works and search_server.image_sources()['held'] == {
        'refused': 'held back by the provenance list: never sent to a provider'}


def test_a_measured_offset_names_an_unnumbered_legacy_text_by_its_pdf_pages_so_its_readings_take_their_place(tmp_path, monkeypatch):
    a_licensed_shelf(tmp_path, monkeypatch)
    (tmp_path / 'offsets.json').write_text(json.dumps({'offsets': {'key-c': -1}}), encoding='utf-8')
    pages, works = search_server.licensed_pages()
    book_c = [page for page in pages if page.work == 'key-c']
    assert [(page.page, page.pdf, page.reading_key) for page in book_c] == [('1', '1', 'kc1')]  # ordinal 2 is PDF page 1
    assert works['key-c'].route == 'per page'


def test_a_stand_in_serves_a_work_whose_first_file_is_not_held(tmp_path, monkeypatch):
    a_licensed_shelf(tmp_path, monkeypatch)
    (tmp_path / 'stand_ins.json').write_text(json.dumps({'suffix': '__alt', 'works': ['key-b']}), encoding='utf-8')
    pages, works = search_server.licensed_pages()
    book_b = [page for page in pages if page.work == 'key-b']
    assert [(page.page, page.reading_key) for page in book_b] == [('1', 'kb1')] and 'legacy bee' not in book_b[0].text
    assert works['key-b'].title == 'book_b__alt' and 'book_b__alt' not in works
    assert search_server.image_sources()['key-b'] == {'pdf': tmp_path / 'archive' / 'book_b__alt.pdf'}


def test_a_stand_in_s_work_takes_its_title_and_language_from_the_stand_in_s_catalog_entry(tmp_path, monkeypatch):
    # the client's third check, 23 Nov: four works were still named by their stand-in's file ("…__replacement")
    a_licensed_shelf(tmp_path, monkeypatch)
    (tmp_path / 'stand_ins.json').write_text(json.dumps({'suffix': '__alt', 'works': ['key-b']}), encoding='utf-8')
    entry = {'id': 'book_b__alt', 'file': 'book_b__alt.pdf', 'format': 'pdf', 'title': 'Book B', 'language': 'en'}
    (tmp_path / 'catalog.json').write_text(json.dumps({'sources': [entry]}), encoding='utf-8')
    monkeypatch.setattr(search_server.data_paths, 'LICENSED_CATALOG', tmp_path / 'catalog.json')  # catalog_entries reads it there
    _, works = search_server.licensed_pages()
    assert (works['key-b'].title, works['key-b'].language) == ('Book B', 'en')


def test_a_licensed_html_source_the_catalog_describes_is_served_by_its_labelled_sections(tmp_path, monkeypatch):
    from test_ingestion_html_labelled_sections import BASE, TITLE

    a_licensed_shelf(tmp_path, monkeypatch)
    a_licensed_rule(tmp_path)
    pages, works = search_server.licensed_pages()
    rule = [page for page in pages if page.work == 'invented_rule']
    assert [page.page for page in rule] == [f's{number}' for number in range(1, 12)]
    assert {page.route for page in rule} == {search_server.HTML_ROUTE} and {page.knowledge_base for page in rule} == {'licensed'}
    assert rule[1].section == f'{TITLE} > (a) Words' and rule[1].path.startswith(f'{BASE}#:~:text=')
    assert works['invented_rule'].route == search_server.HTML_ROUTE and works['invented_rule'].view_id is None
    assert 'bare' not in works  # an HTML file the catalog names without a layout has no route yet
    assert search_server.image_sources()['invented_rule'] == {'refused': 'no PDF page: an HTML source has sections, not pages'}


@pytest.mark.corpus
@pytest.mark.readings
def test_a_free_pdf_page_is_quoted_by_the_search_exactly_as_the_chat_cuts_it(monkeypatch):
    from backend.conversion.store import reading_export
    from backend.ingestion.clean_sections import pdf_sections

    name = 'carta_conversano_kelly_criterion_2020.pdf'  # tracked and small
    chat = pdf_sections.read_pdf(data_paths.FREE_RAW / name, served_readings.served_pages(name)).pages
    assert reading_export.quoted_pages('free', name) == dict(enumerate(chat, start=1))
    monkeypatch.setattr(reading_export, 'quoted_pages', lambda base, file: {number: f'quoted {file} p{number} \frac{{a}}{{b}} ' * 40
                                                                            for number in range(1, 2000)})
    pages, _ = search_server.free_pdf_pages()
    page = next(page for page in pages if page.path.startswith('corpus') and page.work.startswith('carta'))
    assert page.text.startswith(f'quoted {name} p{page.pdf} \frac') and 'frac' not in page_index.tokenize(page.words)


def test_a_hit_links_to_its_page_in_the_diagnostics_view_where_the_view_shows_one():
    # decision 226.a (the operator, 12 Nov): a person checks a hit in the view, image, reading and checks beside it
    pages = [page('free-book', '12', PROSE * 3, 'corpus/readings/free-book/p0012.md', pdf='12', knowledge_base='free',
                  route='vision reading'),
             page('wiki', 's9', PROSE * 3, 'https://en.wikipedia.org/wiki/Sharpe_ratio', knowledge_base='free',
                  route='html, parsed by section'),
             page('key-a', '40', PROSE * 3, 'legacy/a.md', pdf='40', knowledge_base='licensed', route='legacy markdown')]
    works = {'free-book': search_server.Work('free-book', 'A Free Book', 'free', 'CC BY 4.0', 'per page', 1, view_id='free_book_v1'),
             'wiki': search_server.Work('wiki', 'Wiki', 'free', 'CC BY-SA 4.0', 'html, parsed by section', 1, view_id='wiki'),
             'key-a': search_server.Work('key-a', 'a', 'licensed', 'licensed, local use only', 'legacy markdown', 1)}
    served = search_server.SearchService({'free': (pages, works)}, view_url='http://127.0.0.1:8021/')
    assert served.open_page('free-book', '12')['view_url'] == 'http://127.0.0.1:8021/#/free/sources/free_book_v1/page/12'
    assert served.open_page('wiki', 's9')['view_url'] == 'http://127.0.0.1:8021/#/free/html/wiki/s9'
    assert served.open_page('key-a', '40')['view_url'] is None  # a legacy text without a reading: the view shows no page of it
    # an EPUB's section (decision 123.a, line 2's route of 18 Nov), its key URL-encoded
    epub = page('book a', 's12', PROSE * 3, 'book.epub/OEBPS/c1.xhtml#x', knowledge_base='licensed', route=search_server.EPUB_ROUTE)
    with_epub = search_server.SearchService({'free': (pages + [epub], {**works, 'book a': search_server.Work(
        'book a', 'book', 'licensed', 'licensed, local use only', search_server.EPUB_ROUTE, 1, view_id='book a')})},
        view_url='http://127.0.0.1:8021/')
    assert with_epub.open_page('book a', 's12')['view_url'] == 'http://127.0.0.1:8021/#/licensed/epub/book%20a/s12'
    assert all('view_url' in hit for hit in served.search('backoff jitter breakers')['hits'])
    assert search_server.SearchService({'free': (pages, works)}, view_url=None).open_page('free-book', '12')['view_url'] is None


def test_a_semantic_hit_gets_the_same_link():
    class Chain:
        def search(self, question, hits):
            return {'state': 'found', 'hits': [{'work': 'free-book', 'page': {'label': '12', 'pdf': '12', 'printed': None}}]}

    pages = [page('free-book', '12', PROSE * 3, 'p.md', pdf='12', knowledge_base='free', route='vision reading')]
    works = {'free-book': search_server.Work('free-book', 'A Free Book', 'free', 'CC BY 4.0', 'per page', 1, view_id='free_book_v1')}
    served = search_server.SearchService({'free': (pages, works)}, semantic=Chain())
    assert served.semantic_search('what is a breaker?')['hits'][0]['view_url'] == \
        'http://127.0.0.1:8001/#/free/sources/free_book_v1/page/12'


def test_the_legacy_fallback_names_the_numbered_pages_of_a_work_routed_page_by_page(tmp_path, monkeypatch):
    # H2.a: book_a's legacy text names PDF pages 1 and 3; book_c's names none, so it stands whole and falls back to nothing
    a_licensed_shelf(tmp_path, monkeypatch)
    assert search_server.legacy_fallback_pages() == {'book_a.pdf': {1, 3}}
    pages, _ = search_server.licensed_pages()
    third = next(page for page in pages if page.work == 'key-a' and page.pdf == '3')
    assert third.route == search_server.LEGACY_ROUTE  # the issue on page 3 leaves its legacy page standing, as the export says


def test_a_client_learns_what_each_tool_costs_and_takes_and_in_which_order_to_use_them():
    # T1.a (the operator, 21 Nov): the clients knew neither that search is local and free nor that semantic_search takes
    # seconds and a paid embedding, and the instructions never named semantic_search
    server = search_server.build_server(service())
    described = {tool.name: tool.description for tool in asyncio.run(server.list_tools())}
    assert all(f'`{name}`' in search_server.INSTRUCTIONS for name in described)
    assert all('free' in described[name] for name in ('search', 'search_works', 'works', 'toc', 'open_page', 'page_image'))
    assert 'milliseconds' in described['search'] and 'milliseconds' in described['search_works']
    semantic = described['semantic_search']
    assert 'two seconds' in semantic and 'paid API' in semantic and 'language model' in semantic and 'below_floor' in semantic
    assert 'free knowledge base' not in semantic  # since #8 it searches every base the server gives out


CODE_TEXT = 'inputs: Length(14);\nvars: FastValue(0);\nFastValue = Average(Close, Length);\nPlot1(FastValue, "Fast");\n'


def code_service() -> search_server.SearchService:
    """A licensed book and its companion code (#12), with invented text and code."""
    from backend.search import code_pages

    book = [page('book', '40', 'A fast average follows the price with a short length. ' * 6, 'archive/book.pdf#page=40',
                 pdf='40', knowledge_base='licensed', route='text layer: the page has no reading')]
    code = [page('book_code', 'Indicators/Fast Average (I).txt', CODE_TEXT, '_sources/licensed/code/book_code/Indicators/f.txt',
                 line_end=5, section='Indicators', knowledge_base='licensed', route=code_pages.CODE_ROUTE,
                 index_text=code_pages.index_words(CODE_TEXT) + '\nfast average'),
            page('book_code', 'Strategies/Breakout (S).txt', 'if MarketPosition = 0 then buy next bar at market;\n',
                 '_sources/licensed/code/book_code/Strategies/b.txt', line_end=2, section='Strategies',
                 knowledge_base='licensed', route=code_pages.CODE_ROUTE)]
    works = {'book': search_server.Work('book', 'A Book', 'licensed', 'licensed, local use only', 'per page', 1, language='en'),
             'book_code': search_server.Work('book_code', 'A Book: companion code', 'licensed', 'licensed, local use only',
                                             code_pages.CODE_ROUTE, 2, view_id='book_code', code_language='EasyLanguage',
                                             companion_of='book')}
    return search_server.SearchService({'licensed': (book + code, works)}, view_url='http://view')


def test_a_code_hit_names_its_kind_language_companion_and_lines_and_a_prose_hit_its_kind():
    hits = code_service().search('fast average length')['hits']
    by_work = {hit['work']: hit for hit in hits}
    assert by_work['book']['kind'] == 'text' and 'code_language' not in by_work['book']
    code = by_work['book_code']
    assert (code['kind'], code['code_language'], code['companion_of'], code['lines']) == (
        'code', 'EasyLanguage', 'book', {'first': 1, 'last': 5})
    assert code['view_url'] == 'http://view/#/licensed/code/book_code/Indicators%2FFast%20Average%20%28I%29.txt'


def test_a_search_takes_code_or_text_alone_and_refuses_another_kind():
    served = code_service()
    assert {hit['work'] for hit in served.search('fast average length', kind='code')['hits']} == {'book_code'}
    assert {hit['work'] for hit in served.search('fast average length', kind='text')['hits']} == {'book'}
    assert served.search('market position', kind='code')['hits'][0]['page']['label'] == 'Strategies/Breakout (S).txt'
    assert served.search('fast', kind='prose')['state'] == 'error'


def test_a_code_file_opens_whole_with_its_lines_and_its_work_lists_folders_then_files():
    served = code_service()
    opened = served.open_page('book_code', 'Indicators/Fast Average (I).txt')
    assert opened['text'] == CODE_TEXT and opened['kind'] == 'code' and opened['lines'] == {'first': 1, 'last': 5}
    contents = served.toc('book_code')
    assert contents['source'] == 'code folders'
    assert [entry['title'] for entry in contents['entries']] == ['Indicators', 'Fast Average (I)', 'Strategies', 'Breakout (S)']
    listed = {work['work']: work for work in served.list_works()}
    assert listed['book_code']['kind'] == 'code' and listed['book_code']['companion_of'] == 'book'
    assert listed['book']['kind'] == 'text'


def test_a_semantic_search_for_code_filters_inside_the_search_and_one_for_text_after_it():
    from backend.search import code_pages

    served, asked = code_service(), []

    class Semantic:
        def search(self, question, hits, **options):
            asked.append((hits, options))
            return {'state': 'found', 'hits': [{'work': 'book', 'page': {'label': '40'}},
                                               {'work': 'book_code', 'page': {'label': 'Strategies/Breakout (S).txt'}}]}

    served._semantic = Semantic()
    assert [hit['work'] for hit in served.semantic_search('a breakout', hits=2, kind='code')['hits']] == ['book_code']
    assert asked[-1] == (2, {'only': {'route': code_pages.CODE_ROUTE}})
    assert [hit['work'] for hit in served.semantic_search('a breakout', hits=2, kind='text')['hits']] == ['book']
    assert asked[-1] == (6, {})  # prose filtered after the fusion, from three times the hits
    both = served.semantic_search('a breakout', hits=2)['hits']
    assert [hit['kind'] for hit in both] == ['text', 'code'] and both[1]['lines'] == {'first': 1, 'last': 2}


def test_a_code_work_in_the_local_catalog_is_served_file_by_file(tmp_path, monkeypatch):
    from test_search_code_pages import a_code_work

    a_licensed_shelf(tmp_path, monkeypatch)
    a_code_work(tmp_path / 'archive')
    entry = {'id': 'invented_code', 'file': 'code/invented_code', 'format': 'code', 'title': 'Invented: companion code',
             'code_language': 'EasyLanguage', 'companion_of': 'key-a', 'name_prefix': 'XYZ'}
    (tmp_path / 'catalog.json').write_text(json.dumps({'sources': [entry]}), encoding='utf-8')
    pages, works = search_server.licensed_pages()
    work = works['invented_code']
    assert (work.kind, work.code_language, work.companion_of, work.pages, work.title) == (
        'code', 'EasyLanguage', 'key-a', 2, 'Invented: companion code')
    assert [page.page for page in pages if page.work == 'invented_code'] == ['Indicators/Fast Average (I).txt',
                                                                            'Strategies/XYZBreakout.txt']
    assert search_server.licensed_pages({'invented_code'})[1].keys() == {'invented_code'}


def test_the_code_catalog_lists_and_finds_units_by_name_first_and_filters_them(tmp_path, monkeypatch):
    from backend.ingestion import code_catalog

    units = {
        'book_code|Indicators/Fast Average (I).txt': {
            'work': 'book_code', 'page': 'Indicators/Fast Average (I).txt', 'name': 'Fast Average', 'unit': 'indicator',
            'category': 'trend', 'aliases': ['FA'], 'summary': 'A short moving average of the close.', 'summary_is': 'derived',
            'inputs': [{'name': 'Length', 'default': '14'}], 'source_named': None, 'lines': {'first': 1, 'last': 5}},
        'book_code|Strategies/Breakout (S).txt': {
            'work': 'book_code', 'page': 'Strategies/Breakout (S).txt', 'name': 'Breakout', 'unit': 'strategy',
            'category': 'breakout', 'aliases': [], 'summary': 'Buys a close above the highest high, with an average filter.',
            'summary_is': 'derived', 'inputs': [], 'source_named': 'From an invented article', 'lines': {'first': 1, 'last': 2}},
        'gone_code|Functions/X.txt': {
            'work': 'gone_code', 'page': 'Functions/X.txt', 'name': 'X', 'unit': 'function', 'category': 'utility',
            'aliases': [], 'summary': 'average', 'summary_is': 'derived', 'inputs': [], 'source_named': None, 'lines': {}}}
    path = tmp_path / 'code_catalog.json'
    path.write_text(json.dumps({'units': units}), encoding='utf-8')
    monkeypatch.setattr(code_catalog, 'CATALOG', path)
    served = code_service()
    listed = served.code_catalog()
    assert listed['total'] == 2 and [unit['name'] for unit in listed['units']] == ['Fast Average', 'Breakout']  # a work not served is left out
    assert listed['categories'] == {'trend': 1, 'breakout': 1} and listed['units'][0]['code_language'] == 'EasyLanguage'
    found = served.code_catalog('average')
    assert [unit['name'] for unit in found['units']] == ['Fast Average', 'Breakout']  # its name first, then a sentence
    assert served.code_catalog(unit='strategy')['units'][0]['source_named'] == 'From an invented article'
    assert served.code_catalog(category='volume')['state'] == 'nothing found'
    assert served.code_catalog(category='astrology')['state'] == 'error' and served.code_catalog(hits=0)['state'] == 'error'


def test_a_semantic_search_names_its_corpus_and_answers_compact_unless_asked_for_its_diagnostics():
    served, asked = code_service(), []

    class Semantic:
        def search(self, question, hits, **options):
            asked.append(options)
            return {'state': 'found', 'search': {'lists': []}, 'usage': {'embedding': {'tokens': 4, 'usd': 0.00000008}},
                    'hits': [{'work': 'book', 'page': {'label': '40'}, 'citation': {'source_id': 'book'}, 'snippet': 's',
                              'text': 'a fast average'}]}

    served._semantic = Semantic()
    full = served.semantic_search('a fast average', hits=1)  # the service's own default keeps them: the view and the chat
    assert 'search' in full and 'citation' in full['hits'][0]
    compact = served.semantic_search('a fast average', hits=1, diagnostics=False, corpus='licensed')
    assert 'search' not in compact and {'citation', 'snippet'}.isdisjoint(compact['hits'][0])
    assert compact['hits'][0]['text'] == 'a fast average' and compact['usage']['embedding']['tokens'] == 4
    assert asked[-1] == {'corpus': 'licensed'}
    assert served.semantic_search('x', corpus='free')['state'] == 'error'  # a base this server does not give out
    assert served.semantic_search('x', corpus='both')['state'] == 'error'


def test_the_mcp_tool_answers_compact_by_default():
    import inspect

    server = search_server.build_server(code_service())
    tool = {tool.name: tool for tool in asyncio.run(server.list_tools())}['semantic_search']
    assert tool.input_schema['properties']['diagnostics']['default'] is False
    assert tool.input_schema['properties']['corpus']['default'] == 'all'
    assert tool.input_schema['properties']['corpus']['enum'] == ['all', 'free', 'licensed']  # #15: the values on the parameter
    said = ' '.join(tool.description.split())
    assert 'ordered by their similarity of meaning' in said and 'about 1,500 characters a hit' in said
    assert 'fused by rank' not in said  # #15: the description's first sentence still said so
    assert inspect.signature(search_server.SearchService.semantic_search).parameters['diagnostics'].default is True


def test_works_narrow_by_corpus_and_kind_and_a_kept_edition_counts_its_own_pages():
    served = code_service()
    assert [work['work'] for work in served.list_works(kind='code')] == ['book_code']
    assert [work['work'] for work in served.list_works(corpus='free')] == []
    served.works['book_code'].kept_for, served.works['book_code'].pages = 'book', 0
    kept = {work['work']: work for work in served.list_works()}['book_code']
    assert (kept['pages'], kept['kept_for'], kept['pages_kept']) == (0, 'book', 2)


def test_a_contents_descends_into_one_entry():
    served = code_service()
    under = served.toc('book_code', depth=1, under='Strategies')
    assert under['under'] == 'Strategies' and [entry['title'] for entry in under['entries']] == ['Strategies', 'Breakout (S)']
    assert served.toc('book_code', under='Nowhere')['state'] == 'nothing found'
    # a work with neither bookmarks nor headings says so in a state of its own (a client's fourth check, 24 Nov)
    plain = search_server.SearchService({'free': ([page('plain', '1', PROSE * 3, 'plain.md', knowledge_base='free')],
                                                  {'plain': search_server.Work('plain', 'Plain', 'free', 'CC BY', 'per page', 1)})})
    assert plain.toc('plain')['state'] == 'no outline'


def test_every_answer_that_names_a_work_names_its_language():
    # #11: a quote is in that language, and the keyword search reaches a work only in its own
    served = code_service()
    assert served.search('fast average length', kind='text')['hits'][0]['language'] == 'en'
    assert served.open_page('book', '40')['language'] == 'en'
    assert {work['work']: work['language'] for work in served.list_works()}['book'] == 'en'
    assert served.search_works('fast average')['works'][0]['language'] in ('en', None)
    assert served.toc('book_code')['language'] is None  # the invented code work names none here
    assert 'language' in search_server.INSTRUCTIONS and 'lower similarity' in search_server.INSTRUCTIONS


def test_a_name_query_in_the_code_catalog_takes_the_units_holding_every_word(tmp_path, monkeypatch):
    # #15: a two-word name query answered most of the catalog, the few units it meant among them
    from backend.ingestion import code_catalog

    def unit(page, name, summary):
        return {'work': 'book_code', 'page': page, 'name': name, 'unit': 'indicator', 'category': 'volatility',
                'aliases': [], 'summary': summary, 'summary_is': 'derived', 'inputs': [], 'source_named': None, 'lines': {}}

    units = {'a': unit('Indicators/Fast Average (I).txt', 'Spike Marker', 'Marks a day whose price range is a spike.'),
             'b': unit('Strategies/Breakout (S).txt', 'Price Band', 'The highest and lowest price of n days.'),
             'c': unit('Indicators/Fast Average (I).txt', 'Intraday Spikes', 'Large intraday price moves.')}  # a plural
    path = tmp_path / 'code_catalog.json'
    path.write_text(json.dumps({'units': units}), encoding='utf-8')
    monkeypatch.setattr(code_catalog, 'CATALOG', path)
    served = code_service()
    found = served.code_catalog('price spike')
    assert [unit['name'] for unit in found['units']] == ['Spike Marker', 'Intraday Spikes'] and found['match'] == 'every word'
    partial = served.code_catalog('price volume')  # no unit holds both: those holding some, said so
    assert partial['match'] == 'some words' and {unit['name'] for unit in partial['units']} == {
        'Spike Marker', 'Price Band', 'Intraday Spikes'}
    assert 'match' not in served.code_catalog()


def test_a_contents_by_title_takes_the_shallowest_entry_and_names_the_others_and_is_read_once(monkeypatch):
    # #15: a chapter's title took a subsection of that name in a preface; the bookmarks were read on every call
    served, read = code_service(), []
    entries = [{'level': 1, 'title': 'Preface', 'page': '5'}, {'level': 2, 'title': 'Bridge Loads', 'page': '7'},
               {'level': 1, 'title': 'CHAPTER 9 Bridge Loads', 'page': '40'}, {'level': 2, 'title': 'Cables', 'page': '41'},
               {'level': 1, 'title': 'CHAPTER 24 Testing', 'page': '60'}]
    monkeypatch.setattr(served, '_read_contents', lambda work: read.append(work) or ('pdf bookmarks', entries))
    under = served.toc('book', under='bridge loads')
    assert [entry['title'] for entry in under['entries']] == ['CHAPTER 9 Bridge Loads', 'Cables']
    assert under['other_matches'] == [{'title': 'Bridge Loads', 'page': '7', 'level': 2}]
    assert 'other_matches' not in served.toc('book', under='40') and served.toc('book', depth=1)['left_out'] == 2
    assert read == ['book']  # kept until the index reloads


def test_works_brief_gives_what_a_search_is_planned_with():
    served = code_service()
    served.works['book_code'].kept_for, served.works['book_code'].kept_because = 'book', 'a reason'
    brief = {work['work']: work for work in served.list_works(brief=True)}
    assert set(brief['book']) == {'work', 'title', 'edition', 'year', 'knowledge_base', 'kind', 'language'}
    assert brief['book_code']['kept_for'] == 'book' and brief['book']['language'] == 'en'
    assert {work['work']: work for work in served.list_works()}['book_code']['kept_because'] == 'a reason'


def test_every_answer_names_the_index_generation_it_was_read_from_and_the_server_its_version(tmp_path):
    # #15: a client could not tie two runs to one index
    served = code_service()
    server = search_server.build_server(served, tmp_path / 'calls.jsonl')
    answer = json.loads(asyncio.run(server.call_tool('search', {'query': 'fast average'})).content[0].text)
    assert 'index_generation' not in answer  # built from files: no generation to name
    served.generation = 7
    answer = json.loads(asyncio.run(server.call_tool('search', {'query': 'fast average'})).content[0].text)
    assert answer['index_generation'] == 7
    listed = asyncio.run(server.call_tool('works', {}))  # a list: each work names it (the client's third check)
    assert {json.loads(block.text)['index_generation'] for block in listed.content} == {7}
    assert re.fullmatch(r'\d+\.\d+\.\d+\+(\w{7}|unknown)(\.dirty)?', server._lowlevel_server.version)


def test_a_legacy_page_names_the_printed_number_its_text_carries_where_the_work_agrees():
    # #15: "**17**" stood in the text and `printed` was null
    def legacy(pdf, top):
        return page('w', pdf, f'{top}\n\nSome text of a page in a book, long enough to stand as one.', 'w.md', pdf=pdf)

    agreeing = [legacy(str(n), f'**{n - 18}**') for n in range(30, 42)] + [legacy('42', 'A heading')]
    named = search_server.printed_in_text(agreeing)
    assert [p.printed for p in named[:2]] == ['12', '13'] and named[-1].printed is None
    few = search_server.printed_in_text(agreeing[:5])  # too few lines to tell a page number from a bold figure
    assert all(p.printed is None for p in few)
    scattered = [legacy(str(n), f'**{n * 3}**') for n in range(30, 42)]  # no one distance: bold figures, not page numbers
    assert all(p.printed is None for p in search_server.printed_in_text(scattered))


def test_a_semantic_hit_without_a_route_names_its_page_s():
    served = code_service()

    class Semantic:
        def search(self, question, hits, **options):
            return {'state': 'found', 'hits': [{'work': 'book', 'page': {'label': '40'}, 'route': None}]}

    served._semantic = Semantic()
    assert served.semantic_search('a fast average', hits=1)['hits'][0]['route'] == 'text layer: the page has no reading'


def test_each_semantic_hit_names_the_keywords_it_holds_and_the_answer_how_many_any_hit_holds():
    # #15: a neighbouring field's question passed the floor on meaning alone; its terms of art were on no hit
    served = code_service()

    class Semantic:
        def search(self, question, hits, **options):
            return {'state': 'found', 'plan': {'keywords': ['order book', 'checksum', 'WebSocket', '-']},
                    'hits': [{'work': 'book', 'page': {'label': '40'}, 'text': 'An order book holds the resting orders.'},
                             {'work': 'book', 'page': {'label': '40'}, 'text': 'The book of orders, and a check sum.'}]}

    served._semantic = Semantic()
    answer = served.semantic_search('how does the checksum work?', hits=2)
    assert [hit['keywords_found'] for hit in answer['hits']] == [['order book'], []]  # words in their order, never apart
    assert answer['keywords_covered'] == {'found': 1, 'of': 3, 'missing': ['checksum', 'WebSocket']}
    served._semantic.search = lambda question, hits, **options: {'state': 'found', 'plan': {'keywords': []}, 'hits': []}
    assert 'keywords_covered' not in served.semantic_search('x', hits=1)
