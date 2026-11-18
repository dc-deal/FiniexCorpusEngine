import pytest

from backend.search import retrieval
from backend.search.retrieval import KeywordIndex, reciprocal_rank_fusion, tokenize


def hit(chunk_id: str, similarity: float = 0.5) -> dict:
    return {'chunk_id': chunk_id, 'similarity': similarity, 'text': chunk_id, 'citation': {}}


def test_rrf_uses_the_course_formula_with_ranks_from_zero():
    fused = reciprocal_rank_fusion([[hit('a'), hit('b')], [hit('b'), hit('c')]])
    scores = {r['chunk_id']: r['fused_score'] for r in fused}
    assert scores['b'] == pytest.approx(1 / 61 + 1 / 60)
    assert scores['a'] == pytest.approx(1 / 60)
    assert scores['c'] == pytest.approx(1 / 61)
    assert [r['chunk_id'] for r in fused] == ['b', 'a', 'c']


def test_a_chunk_found_twice_appears_once_with_its_best_similarity():
    fused = reciprocal_rank_fusion([[hit('a', 0.4)], [hit('a', 0.7)]])
    assert len(fused) == 1 and fused[0]['similarity'] == 0.7


def test_a_chunk_found_only_by_keyword_keeps_no_invented_similarity():
    keyword_only = {**hit('k'), 'similarity': None, 'bm25': 7.5}
    fused = reciprocal_rank_fusion([[hit('a', 0.6)], [keyword_only]])
    assert {r['chunk_id']: r['similarity'] for r in fused} == {'a': 0.6, 'k': None}
    assert next(r for r in fused if r['chunk_id'] == 'k')['bm25'] == 7.5


def test_tokens_keep_joined_terms_whole_and_drop_function_words():
    assert tokenize('What is P&L?') == ['p&l']
    assert tokenize('Walk-forward testing of a tom-next swap') == ['walk-forward', 'testing', 'tom-next', 'swap']


def keyword_index() -> KeywordIndex:
    rows = [
        ('a:0', 'The profit and loss statement, or P&L, shows income and expenses.', {'chunk_id': 'a:0', 'source_id': 'a', 'shelf': 'trading_finance'}),
        ('b:0', 'Tom-next swaps roll a currency position to the next day.', {'chunk_id': 'b:0', 'source_id': 'b', 'shelf': 'trading_finance'}),
        ('c:0', 'Service level objectives define reliability targets.', {'chunk_id': 'c:0', 'source_id': 'c', 'shelf': 'architecture'}),
        ('d:0', 'A ledger records every transaction twice.', {'chunk_id': 'd:0', 'source_id': 'd', 'shelf': 'architecture'}),
    ]
    return KeywordIndex(rows)


def test_bm25_finds_the_exact_term_and_leaves_out_chunks_without_it():
    results = keyword_index().search('what is P&L', k=5)
    assert [r['chunk_id'] for r in results] == ['a:0']
    assert results[0]['similarity'] is None and results[0]['bm25'] > 0
    assert results[0]['citation']['source_id'] == 'a'


def test_bm25_respects_the_shelf_filter():
    index = keyword_index()
    assert [r['chunk_id'] for r in index.search('tom-next swap', k=5)] == ['b:0']
    assert index.search('tom-next swap', k=5, filters={'shelf': 'architecture'}) == []


def test_a_listed_section_yields_its_rank_before_the_cut_so_an_explanation_can_take_its_place(monkeypatch):
    # Phase 6's first hypothesis: exercise pages repeat a chapter's words and outranked its explanation.
    def section(chunk_id, title):
        return {**hit(chunk_id), 'citation': {'section': title}}
    exercises = [section('e1', 'Multiple Choice'), section('e2', 'Problem Set A')]
    monkeypatch.setattr(retrieval, 'retrieve', lambda query, k, filters=None, store=None:
                        [*exercises, section('x1', '15.4 Applications in Performance Measurement'), section('x2', 'Key Terms')])
    unrelated = keyword_index()  # holds no word of the query, so only the vector list counts
    plain = retrieval.hybrid_retrieve(['sharpe ratio'], k=2, keyword_index=unrelated)
    demoted = retrieval.hybrid_retrieve(['sharpe ratio'], k=2, keyword_index=unrelated,
                                        demote_sections=frozenset({'Multiple Choice', 'Problem Set A'}))
    assert [r['chunk_id'] for r in plain] == ['e1', 'e2']
    assert [r['chunk_id'] for r in demoted] == ['x1', 'x2']  # from below the cut, not a reordering of the two
    assert [r['chunk_id'] for r in retrieval.demoted(exercises, frozenset({'Multiple Choice'}))] == ['e2', 'e1']
    assert retrieval.demoted(exercises, frozenset()) == exercises


def test_hybrid_search_fuses_vector_and_keyword_lists(monkeypatch):
    monkeypatch.setattr(retrieval, 'retrieve', lambda query, k, filters=None, store=None: [hit('d:0', 0.5)])
    fused = retrieval.hybrid_retrieve(['tom-next swap'], k=5, keyword_index=keyword_index())
    assert [r['chunk_id'] for r in fused] == ['d:0', 'b:0']  # a tie in RRF keeps the first list's order


@pytest.mark.corpus
def test_the_real_keyword_index_finds_tom_next_in_the_fx_swap_article():
    if not retrieval.DATABASE.exists():
        pytest.skip('no index yet - run python -m backend.ingestion.build')
    results = KeywordIndex.from_database().search('tom-next', k=3)
    assert results and results[0]['citation'].get('anchor') == 'Uses'


def test_hybrid_search_can_run_bm25_on_other_text_than_the_vector_search(monkeypatch):
    # The keyword field: the vector search gets the sentence, BM25 only the terms of art.
    monkeypatch.setattr(retrieval, 'retrieve', lambda query, k, filters=None, store=None: [])
    index = keyword_index()
    sentence = retrieval.hybrid_retrieve(['what is the definition of a ledger'], k=5, keyword_index=index)
    terms = retrieval.hybrid_retrieve(['what is the definition of a ledger'], k=5, keyword_index=index,
                                      keyword_queries=['tom-next'])
    assert [r['chunk_id'] for r in sentence] == ['d:0']
    assert [r['chunk_id'] for r in terms] == ['b:0']


def test_the_trace_keeps_every_list_before_fusion_and_where_each_fused_chunk_came_from(monkeypatch):
    # Phase 10's Search tab: c.1 the vector list, c.2 the BM25 list, then what RRF made of them.
    monkeypatch.setattr(retrieval, 'retrieve', lambda query, k, filters=None, store=None: [hit('d:0', 0.5)])
    trace = {}
    fused = retrieval.hybrid_retrieve(['ledger'], k=5, keyword_index=keyword_index(),
                                      keyword_queries=['tom-next ledger'], trace=trace)
    assert [(entry['kind'], entry['query']) for entry in trace['lists']] == [('vector', 'ledger'),
                                                                             ('bm25', 'tom-next ledger')]
    assert trace['lists'][0]['hits'][0] == {'rank': 1, 'chunk_id': 'd:0', 'source': None, 'section': None,
                                            'score': 0.5}
    assert [entry['chunk_id'] for entry in trace['fused']] == [r['chunk_id'] for r in fused]
    bm25_rank = next(h['rank'] for h in trace['lists'][1]['hits'] if h['chunk_id'] == 'd:0')
    assert next(e for e in trace['fused'] if e['chunk_id'] == 'd:0')['from'] == ['list 1 #1', f'list 2 #{bm25_rank}']


def test_the_trace_changes_nothing_in_the_result(monkeypatch):
    monkeypatch.setattr(retrieval, 'retrieve', lambda query, k, filters=None, store=None: [hit('d:0', 0.5)])
    plain = retrieval.hybrid_retrieve(['tom-next swap'], k=5, keyword_index=keyword_index())
    traced = retrieval.hybrid_retrieve(['tom-next swap'], k=5, keyword_index=keyword_index(), trace={})
    assert plain == traced
