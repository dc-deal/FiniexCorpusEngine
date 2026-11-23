import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from backend.chat import app_config, chat_turn
from backend.chat.chat_turn import Answer, Quote
from backend.search.query_routing import QueryPlan
from backend.search.retrieval import KeywordIndex

PASSAGE = ('The Sharpe ratio measures the excess return of a portfolio per unit of risk. '
           'It divides the excess return by the standard deviation of returns.')
METADATA = {'chunk_id': 'fin:0217:000', 'source_id': 'openstax_principles_of_finance_2e',
            'source_title': 'Principles of Finance 2e', 'authors': 'Julie Dahlquist, Rainford Knight',
            'licence': 'CC BY-NC-SA 4.0', 'licence_url': 'https://openstax.org/licence',
            'chapter': 'Chapter 15 How to Think about Investing', 'section': '15.4 Applications in Performance Measurement',
            'pdf_page': 470, 'printed_page': 456, 'shelf': 'trading_finance'}


def plan(**overrides) -> QueryPlan:
    fields = {'route': 'search', 'needs_clarification': False, 'shelf': 'trading_finance',
              'search_query': 'Sharpe ratio definition', 'concept_query': 'what the Sharpe ratio measures',
              'keywords': ['Sharpe ratio'], 'is_broad': False}
    return QueryPlan(**{**fields, **overrides})


def chain(parsed, finish_reason='stop', seen=None):
    raw = AIMessage(content='', response_metadata={'finish_reason': finish_reason},
                    usage_metadata={'input_tokens': 1000, 'output_tokens': 200, 'total_tokens': 1200,
                                    'output_token_details': {'reasoning': 50}})

    def respond(inputs):
        if seen is not None:
            seen.append(inputs)
        return {'raw': raw, 'parsed': parsed, 'parsing_error': None}
    return RunnableLambda(respond)


def refusing_chain():
    def refuse(inputs):
        raise AssertionError('this chain must not be called')
    return RunnableLambda(refuse)


class Store:
    """One chunk, at a fixed cosine distance."""

    def __init__(self, distance=0.3):
        self.distance = distance

    def similarity_search_with_score(self, query, k, filter=None):
        return [(Document(page_content=PASSAGE, metadata=METADATA), self.distance)]


def keywords() -> KeywordIndex:
    return KeywordIndex([(METADATA['chunk_id'], PASSAGE, METADATA)])


def answer(**overrides) -> Answer:
    fields = {'found': True, 'answer': 'The Sharpe ratio is excess return per unit of risk [1].',
              'quotes': [Quote(passage=1, text='It divides the excess return by the standard deviation of returns.')],
              'gaps': None, 'follow_up': None}
    return Answer(**{**fields, **overrides})


def turn(router_plan, generated, store=None, seen=None, prices=None):
    return chat_turn.run_turn('show me how a sharpe works', router_chain=chain(router_plan),
                              generator_chain=chain(generated, seen=seen) if generated is not ... else refusing_chain(),
                              store=store or Store(), keyword_index=keywords(), prices=prices)


def test_an_empty_or_overlong_question_is_refused_before_any_model():
    assert chat_turn.run_turn('   ', router_chain=refusing_chain(), generator_chain=refusing_chain())['behaviour'] == 'invalid'
    with pytest.raises(chat_turn.InvalidQuestion, match='at most 10'):
        chat_turn.validate_question('x' * 11, max_characters=10)


def test_a_decline_retrieves_and_generates_nothing():
    result = chat_turn.run_turn('why does my car not start', router_chain=chain(plan(route='off_topic')),
                                generator_chain=refusing_chain(), store=object(), keyword_index=object())
    assert result['behaviour'] == 'decline_off_topic' and result['sources'] == [] and result['disclaimer'] is None
    harmful = chat_turn.run_turn('x', router_chain=chain(plan(route='harmful')), generator_chain=refusing_chain(),
                                 store=object(), keyword_index=object())
    assert harmful['answer'] == chat_turn.HARMFUL_TEXT


def test_an_answer_shows_only_verbatim_quotes_with_rendered_citations_and_the_disclaimer():
    reworded = Quote(passage=1, text='The Sharpe ratio is return divided by risk.')
    wrong_number = Quote(passage=7, text='It divides the excess return by the standard deviation of returns.')
    result = turn(plan(), answer(quotes=[*answer().quotes, reworded, wrong_number]),
                  prices={app_config.load()['generator']['model']: {'input': 0.25, 'output': 2.0}})
    assert result['behaviour'] == 'answer'
    assert [q['text'] for q in result['quotes']] == ['It divides the excess return by the standard deviation of returns.']
    assert result['quotes_dropped'] == 2
    assert result['quotes'][0]['citation']['where'].endswith('p. 456 (PDF p. 470)')
    assert result['sources'][0]['citation']['licence'] == 'CC BY-NC-SA 4.0'
    assert result['disclaimer'] == app_config.load()['answer']['disclaimer']
    assert result['relevance'] == pytest.approx(0.7) and result['below_floor'] is False
    assert result['usd'] == pytest.approx(2 * (1000 * 0.25 + 200 * 2.0) / 1e6)


def test_whitespace_and_quotation_glyphs_do_not_count_as_rewording():
    kept, dropped = chat_turn.verify_quotes(
        [Quote(passage=1, text='“It divides the excess return  by the\nstandard deviation of returns.”')],
        [{'text': PASSAGE}])
    assert len(kept) == 1 and dropped == 0


def test_nothing_found_shows_no_sources_no_quotes_and_no_disclaimer():
    result = turn(plan(), answer(found=False, answer='The knowledge base has nothing on this topic.'))
    assert result['behaviour'] == 'not_found'
    assert result['sources'] == [] and result['quotes'] == [] and result['disclaimer'] is None
    assert len(result['retrieved']) == 1  # kept for diagnosis, not shown


def test_a_low_relevance_is_passed_to_the_model_as_a_hint_not_applied_as_a_stop():
    seen = []
    result = turn(plan(), answer(), store=Store(distance=0.6), seen=seen)  # similarity 0.4 < floor
    assert result['below_floor'] is True and result['behaviour'] == 'answer'
    assert 'Relevance note' in seen[0]['notes']


def test_a_clarify_route_that_gets_a_follow_up_question_is_a_clarify_turn():
    result = turn(plan(needs_clarification=True), answer(follow_up='Which market do you trade?'))
    assert result['behaviour'] == 'clarify' and result['follow_up'] == 'Which market do you trade?'


def test_content_null_from_the_generator_is_reported_not_shown_as_an_empty_answer():
    result = turn(plan(), None)
    assert result['behaviour'] == 'error' and 'could not be generated' in result['answer']


def test_citations_name_both_pages_for_a_pdf_and_the_anchor_link_for_html():
    assert chat_turn.render_citation(METADATA)['text'] == (
        'Principles of Finance 2e, Julie Dahlquist, Rainford Knight · Chapter 15 How to Think about Investing'
        ' · 15.4 Applications in Performance Measurement · p. 456 (PDF p. 470)')
    wiki = chat_turn.render_citation({'source_id': 'wikipedia_trading_set', 'source_title': 'Wikipedia articles',
                                      'authors': 'Wikipedia contributors', 'chapter': 'Sharpe ratio',
                                      'section': 'Definition', 'licence': 'CC BY-SA 4.0',
                                      'url': 'https://en.wikipedia.org/w/index.php?title=Sharpe_ratio&oldid=1#Definition'})
    assert wiki['title'] == 'Sharpe ratio (Wikipedia)' and wiki['where'] == 'Definition'
    assert wiki['link'].endswith('#Definition')
    paper = chat_turn.render_citation({**METADATA, 'printed_page': 3, 'pdf_page': 3})
    assert paper['where'].endswith('p. 3')


def test_one_plan_can_be_answered_with_another_k_without_changing_the_routed_turn():
    routed, routed_plan = chat_turn.route_turn('show me how a sharpe works', router_chain=chain(plan()))
    assert routed_plan is not None and routed['behaviour'] is None
    first = chat_turn.answer_turn(routed, routed_plan, generator_chain=chain(answer()), store=Store(),
                                  keyword_index=keywords(), k=1)
    second = chat_turn.answer_turn(routed, routed_plan, generator_chain=chain(answer()), store=Store(),
                                   keyword_index=keywords(), k=10)
    assert first['behaviour'] == second['behaviour'] == 'answer'
    assert routed['retrieved'] == [] and 'generate' not in routed['seconds']  # the routed turn is untouched


def test_the_turn_records_the_exact_prompt_the_search_lists_and_every_proposed_quote():
    # Phase 10: what the interface's tabs show must be what happened, not a reconstruction.
    seen = []
    proposed = [Quote(passage=1, text='"It divides the excess return by the standard deviation of returns."'),
                Quote(passage=1, text='The Sharpe ratio always beats the market.')]
    result = turn(plan(), answer(quotes=proposed), seen=seen)
    assert result['prompt'] == chat_turn.GENERATOR_PROMPT.format_messages(**seen[0])[-1].content
    assert PASSAGE in result['prompt'] and result['prompt'].startswith('Question: show me how a sharpe works')
    assert [entry['kind'] for entry in result['search']['lists']] == ['vector', 'vector', 'bm25']
    assert [entry['role'] for entry in result['search']['lists']] == ['search_query', 'concept_query', 'keywords']
    assert [q['kept'] for q in result['quotes_proposed']] == [True, False]
    assert result['relevance_floor'] == app_config.load()['retrieval']['relevance_floor']


def test_a_generator_stopped_by_its_token_budget_gives_an_error_turn_not_a_crash():
    # Found 2026-10-01: OpenAI's parse() raises on finish_reason 'length' instead of returning null.
    import openai
    from openai.types.chat import ChatCompletion
    stopped = ChatCompletion.model_validate({
        'id': 'x', 'created': 0, 'model': 'openai/gpt-5-mini', 'object': 'chat.completion',
        'choices': [{'index': 0, 'finish_reason': 'length', 'message': {'role': 'assistant', 'content': 'a' * 900}}],
        'usage': {'prompt_tokens': 2966, 'completion_tokens': 6000, 'total_tokens': 8966}})

    def run_out(inputs):
        raise openai.LengthFinishReasonError(completion=stopped)
    result = chat_turn.run_turn('tell me more about drawdowns', router_chain=chain(plan()),
                                generator_chain=RunnableLambda(run_out), store=Store(), keyword_index=keywords())
    assert result['behaviour'] == 'error' and 'could not be generated' in result['answer']
    assert 'LengthFinishReasonError' in result['error'] and '900 characters' in result['error']
    assert result['usage']['generator']['output_tokens'] == 6000


def server_searcher(router_plan):
    """The search server's semantic_search over the same fakes, as the chat reaches it through MCP (98.c)."""
    from test_search_semantic import searching

    engine = searching(router_plan)
    return lambda question, k: engine.search(question, k)


def test_a_turn_answers_from_the_search_server_s_passages_and_keeps_only_verbatim_quotes():
    turn = chat_turn.search_turn('show me how a sharpe works', searcher=server_searcher(plan()), generator_chain=chain(answer()))
    assert turn['behaviour'] == 'answer' and turn['retrieval'] == 'mcp semantic_search'
    assert [q['text'] for q in turn['quotes']] == ['It divides the excess return by the standard deviation of returns.']
    assert turn['sources'][0]['citation']['text'].startswith('Principles of Finance 2e')
    assert turn['usage']['router']['input_tokens'] == 1000  # the server's router, reported back (found by line 2, 5 Nov)


def test_the_turn_s_cost_counts_the_server_s_router_beside_the_generator():
    # Since 98.c the router runs in the search server; its cost had dropped out of the turn's figure.
    config = app_config.load()
    prices = {config['router']['model']: {'input': 1.0, 'output': 2.0}, config['generator']['model']: {'input': 1.0, 'output': 2.0}}
    turn = chat_turn.search_turn('show me how a sharpe works', searcher=server_searcher(plan()), generator_chain=chain(answer()),
                                 prices=prices)
    one_call = (1000 * 1.0 + 200 * 2.0) / 1e6  # what the fake chain reports for each of the two calls
    assert turn['router_model'] == config['router']['model'] and turn['usd'] == pytest.approx(2 * one_call)


def test_a_question_the_server_declines_is_not_answered():
    config = app_config.load()
    prices = {config['router']['model']: {'input': 1.0, 'output': 2.0}}
    turn = chat_turn.search_turn('write me a poem', searcher=server_searcher(plan(route='off_topic')), generator_chain=refusing_chain(),
                                 prices=prices)
    assert turn['behaviour'] == 'decline_off_topic' and turn['answer'] == chat_turn.OFF_TOPIC_TEXT
    assert turn['usd'] == pytest.approx((1000 * 1.0 + 200 * 2.0) / 1e6)  # a decline costs its routing, as before 98.c


def test_a_search_server_that_fails_gives_an_error_turn_never_an_answer_without_sources():
    def down(question, k):
        raise TimeoutError('no answer in 180 s')
    turn = chat_turn.search_turn('what is a sharpe ratio?', searcher=down, generator_chain=refusing_chain())
    assert turn['behaviour'] == 'error' and turn['answer'] == chat_turn.SEARCH_ERROR_TEXT and 'TimeoutError' in turn['error']
