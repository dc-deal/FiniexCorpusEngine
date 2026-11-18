"""The chat's retrieval chain as a server tool: routed, searched by meaning and keywords, hits shaped like `search` (98.c)."""

import asyncio
import json

import pytest

from backend.chat import app_config
from backend.search import search_server, semantic_search
from test_chat_turn import METADATA, PASSAGE, Store, chain, keywords, plan
from test_search_server import service

SOURCES = {'openstax_principles_of_finance_2e': {'work': 'openstax-finance-2e', 'path': 'corpus/raw/openstax_principles_of_finance_2e.pdf'}}


def searching(router_plan) -> semantic_search.SemanticSearch:
    return semantic_search.SemanticSearch(SOURCES, app_config.load(), chain(router_plan), Store(), keywords())


def test_a_hit_has_the_search_fields_and_the_full_passage_an_answer_needs():
    answer = searching(plan()).search('what does the sharpe ratio measure?')
    (hit,) = answer['hits']
    assert answer['state'] == 'found' and answer['plan']['search_query'] == 'Sharpe ratio definition'
    assert (hit['knowledge_base'], hit['work'], hit['page']) == ('free', 'openstax-finance-2e', {'label': '470', 'pdf': '470', 'printed': '456'})
    assert hit['where'] == 'corpus/raw/openstax_principles_of_finance_2e.pdf#page=470' and hit['text'] == PASSAGE
    assert hit['section'] == METADATA['section'] and hit['citation']['source_title'] == 'Principles of Finance 2e'
    assert 'Sharpe' in hit['snippet'] and hit['similarity'] == hit['score']


def test_an_html_passage_is_named_by_the_page_label_search_and_open_page_use():
    # Found live on 2026-11-05: the label was the anchor ('Definition'), so "open source 1" asked open_page for no page.
    citation = {'source_id': 'wikipedia_trading_set', 'anchor': 'Definition', 'url': 'https://en.wikipedia.org/wiki/Sharpe_ratio#Definition'}
    assert semantic_search.page_of(citation, 'wikipedia_trading_set:0008:000') == {'label': 's9', 'pdf': None, 'printed': None}
    assert semantic_search.page_of({'pdf_page': 470, 'printed_page': 456}, 'book:0012:001')['label'] == '470'


@pytest.mark.corpus
def test_every_html_passage_of_the_index_names_a_page_the_server_opens():
    import sqlite3

    from backend.search import retrieval
    if not retrieval.DATABASE.exists():
        pytest.skip('no index yet - run python -m backend.ingestion.build')
    pages, _ = search_server.free_html_pages()
    served = {(page.work, page.page) for page in pages}
    with sqlite3.connect(retrieval.DATABASE) as connection:
        chunks = connection.execute("SELECT c.id, c.source_id FROM chunks c JOIN sources s ON s.id = c.source_id "
                                    "WHERE s.format = 'html'").fetchall()
    labels = {(source, semantic_search.page_of({}, chunk)['label']) for chunk, source in chunks}
    assert chunks and labels <= served, sorted(labels - served)[:5]


def test_a_frozen_plan_is_searched_without_calling_the_router(monkeypatch):
    # Phase 6: a comparison run searches with the baseline's own plans, so a difference is the change's, not the router's.
    from backend.search import query_routing

    def no_router(chain, question):
        raise AssertionError('the router was called')
    monkeypatch.setattr(query_routing, 'plan_query', no_router)
    frozen = {'what does the sharpe ratio measure?': {**plan().model_dump(), 'fell_back': False}}
    engine = semantic_search.SemanticSearch(SOURCES, app_config.load(), chain(None), Store(), keywords(), frozen_plans=frozen)
    answer = engine.search('what does the sharpe ratio measure?')
    assert answer['state'] == 'found' and answer['plan']['search_query'] == 'Sharpe ratio definition'
    assert answer['usage']['router']['input_tokens'] == 0


def test_an_answer_record_gives_its_plans_by_question(tmp_path, monkeypatch):
    from backend.evaluation import answer_eval

    monkeypatch.setattr(answer_eval, 'RESULTS', tmp_path)
    record = tmp_path / 'answers_base.json'
    record.write_text(json.dumps({'label': 'base', 'questions': [
        {'question': 'what is a sharpe ratio', 'turn': {'plan': {'route': 'search', 'search_query': 'Sharpe ratio'}}},
        {'question': 'invalid', 'turn': {'plan': None}}]}), encoding='utf-8')
    plans = json.loads(answer_eval.frozen_plans_of(record).read_text(encoding='utf-8'))
    assert plans == {'what is a sharpe ratio': {'route': 'search', 'search_query': 'Sharpe ratio'}}


def test_a_question_the_router_declines_is_not_searched():
    answer = searching(plan(route='off_topic')).search('write me a poem')
    assert answer['state'] == 'declined' and answer['hits'] == [] and answer['behaviour'] == 'decline_off_topic'


def test_an_empty_or_overlong_question_is_an_error_before_any_model():
    long = 'x' * (app_config.load()['answer']['max_question_characters'] + 1)
    for question in ('', '   ', long):
        assert semantic_search.SemanticSearch(SOURCES, app_config.load(), chain(None), Store(), keywords()).search(question)['state'] == 'error'


def test_the_server_offers_it_as_a_tool_and_logs_the_call_without_text(tmp_path):
    base = service()
    served = search_server.SearchService({'free': ([*base.by_page.values()][:2], {'free-book': base.works['free-book']})},
                                         semantic=searching(plan()))
    log_path = tmp_path / 'calls.jsonl'
    server = search_server.build_server(served, log_path)
    assert 'semantic_search' in [tool.name for tool in asyncio.run(server.list_tools())]
    result = asyncio.run(server.call_tool('semantic_search', {'question': 'what does the sharpe ratio measure?'}))
    payload = json.loads(result.content[0].text)
    assert payload['state'] == 'found' and payload['hits'][0]['text'] == PASSAGE
    (record,) = [json.loads(line) for line in log_path.read_text(encoding='utf-8').splitlines()]
    assert record['tool'] == 'semantic_search' and record['answered'][0]['pdf'] == '470' and PASSAGE[:30] not in log_path.read_text(encoding='utf-8')


def test_a_caller_s_own_translation_is_searched_without_the_router(monkeypatch):
    # 279.a: a calling session is a model already; its search query, concept and keywords replace the router's
    from backend.search import query_routing

    def no_router(chain, question):
        raise AssertionError('the router was called')
    monkeypatch.setattr(query_routing, 'plan_query', no_router)
    answer = searching(plan()).search('how good is my fund per unit of risk?', search_query='Sharpe ratio definition',
                                      concept_query='risk-adjusted return', keywords=['Sharpe ratio'])
    assert answer['state'] == 'found' and answer['plan']['translated_by'] == 'the caller'
    assert (answer['plan']['search_query'], answer['plan']['concept_query'], answer['plan']['keywords']) == \
        ('Sharpe ratio definition', 'risk-adjusted return', ['Sharpe ratio'])
    assert answer['usage']['router']['model'] is None and answer['behaviour'] == 'answer'


def test_with_the_router_switched_off_the_question_searches_as_it_stands():
    config = {**app_config.load()}
    config['router'] = {**config['router'], 'enabled': False}
    answer = semantic_search.SemanticSearch(SOURCES, config, None, Store(), keywords()).search('what does the sharpe ratio measure?')
    assert answer['plan']['translated_by'] == 'nobody: the router is off'
    assert answer['plan']['search_query'] == 'what does the sharpe ratio measure?' and answer['usage']['router']['model'] is None
