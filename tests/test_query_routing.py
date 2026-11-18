from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from backend.search import query_routing
from backend.search.query_routing import QueryPlan


def plan(**overrides) -> QueryPlan:
    fields = {'route': 'search', 'needs_clarification': False, 'shelf': 'trading_finance',
              'search_query': 'backtesting a trading strategy', 'concept_query': None, 'keywords': [], 'is_broad': False}
    return QueryPlan(**{**fields, **overrides})


def fake_chain(parsed, finish_reason='stop', error=None):
    raw = AIMessage(content='', response_metadata={'finish_reason': finish_reason},
                    usage_metadata={'input_tokens': 400, 'output_tokens': 60, 'total_tokens': 460,
                                    'output_token_details': {'reasoning': 32}})
    return RunnableLambda(lambda inputs: {'raw': raw, 'parsed': parsed, 'parsing_error': error})


def test_each_route_leads_to_its_behaviour():
    assert query_routing.behaviour(plan(route='off_topic')) == 'decline_off_topic'
    assert query_routing.behaviour(plan(route='harmful')) == 'decline_harmful'
    assert query_routing.behaviour(plan(needs_clarification=True)) == 'clarify'
    assert query_routing.behaviour(plan()) == 'answer'


def test_a_decline_wins_over_a_clarification():
    assert query_routing.behaviour(plan(route='harmful', needs_clarification=True)) == 'decline_harmful'


def test_the_shelf_becomes_a_metadata_filter_and_both_searches_everything():
    assert query_routing.shelf_filter(plan(shelf='architecture')) == {'shelf': 'architecture'}
    assert query_routing.shelf_filter(plan(shelf='both')) is None


def test_a_parsed_plan_comes_back_with_its_token_counts():
    result = query_routing.plan_query(fake_chain(plan()), 'how do i check a strategy')
    assert result['plan'] == plan() and not result['fell_back'] and result['error'] is None
    assert (result['input_tokens'], result['output_tokens'], result['reasoning_tokens']) == (400, 60, 32)


def test_content_null_falls_back_to_the_plain_search_and_says_why():
    # A reasoning model out of budget: no content, finish_reason 'length', no exception.
    result = query_routing.plan_query(fake_chain(None, finish_reason='length'), 'waht is a spread')
    assert result['fell_back']
    assert 'finish_reason=length' in result['error']
    assert result['plan'] == query_routing.fallback_plan('waht is a spread')
    assert query_routing.behaviour(result['plan']) == 'answer'


def test_multi_query_keeps_only_non_empty_versions():
    parsed = query_routing.SearchQueries(queries=['double-entry ledger', '  ', 'journal entries'])
    result = query_routing.expand_query(fake_chain(parsed), 'ledger design', versions=3)
    assert result['queries'] == ['double-entry ledger', 'journal entries']


class FakeStore:
    """Returns a fixed list per query and records the filter it was given."""

    def __init__(self, lists):
        self.lists, self.filters = lists, []

    def similarity_search_with_score(self, query, k, filter=None):
        from langchain_core.documents import Document
        self.filters.append(filter)
        return [(Document(page_content=cid, metadata={'chunk_id': cid, 'source_id': 's'}), 0.5)
                for cid in self.lists[query][:k]]


def test_a_decline_searches_nothing():
    assert query_routing.search(plan(route='off_topic'), k=5, use_shelf_filter=True, store=object()) == []


def test_the_shelf_filter_is_applied_only_when_switched_on():
    store = FakeStore({'backtesting a trading strategy': ['a', 'b']})
    query_routing.search(plan(), k=5, use_shelf_filter=False, store=store)
    query_routing.search(plan(), k=5, use_shelf_filter=True, store=store)
    assert store.filters == [None, {'shelf': 'trading_finance'}]


def test_the_step_back_query_is_searched_only_when_switched_on_and_present():
    store = FakeStore({'backtesting a trading strategy': ['a', 'b'], 'what is a backtest': ['b', 'c']})
    with_concept = plan(concept_query='what is a backtest')
    assert [r['chunk_id'] for r in query_routing.search(with_concept, k=3, use_shelf_filter=False, store=store)] \
        == ['a', 'b']
    fused = query_routing.search(with_concept, k=3, use_shelf_filter=False, use_concept_query=True, store=store)
    assert [r['chunk_id'] for r in fused] == ['b', 'a', 'c']
    # No step-back query (a question that already asks what a concept is): one search, as before.
    assert [r['chunk_id'] for r in query_routing.search(plan(concept_query=None), k=3, use_shelf_filter=False,
                                                        use_concept_query=True, store=store)] == ['a', 'b']


def test_extra_queries_are_fused_by_rank():
    store = FakeStore({'backtesting a trading strategy': ['a', 'b'], 'walk-forward validation': ['b', 'c']})
    fused = query_routing.search(plan(), k=2, use_shelf_filter=False,
                                 extra_queries=['walk-forward validation'], store=store)
    assert [r['chunk_id'] for r in fused] == ['b', 'a']
