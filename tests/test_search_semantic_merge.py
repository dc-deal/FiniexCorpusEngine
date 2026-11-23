from backend.search import semantic_search


def hit(chunk_id, similarity):
    return {'chunk_id': chunk_id, 'similarity': similarity}


def test_two_bases_merge_each_passage_at_its_own_similarity_and_a_keyword_only_passage_after_them():
    # #14, 23 Nov: merged by rank, a weak hit of one base stood above a strong hit of the other in every call
    free = [hit('f1', 0.53), hit('f2', 0.50)]
    licensed = [hit('l1', None), hit('l2', 0.68), hit('l3', 0.60), hit('l4', 0.62)]  # l1 only the keyword search found
    merged = [result['chunk_id'] for result in semantic_search.merge_by_similarity([free, licensed])]
    assert merged == ['l2', 'l4', 'l3', 'f1', 'f2', 'l1']


def test_a_list_without_any_similarity_keeps_its_order_after_the_rest():
    merged = semantic_search.merge_by_similarity([[hit('a', 0.7), hit('b', 0.6)], [hit('k1', None), hit('k2', None)]])
    assert [result['chunk_id'] for result in merged] == ['a', 'b', 'k1', 'k2']


def test_a_passage_two_lists_hold_stands_once_at_its_better_place():
    merged = semantic_search.merge_by_similarity([[hit('a', 0.7)], [hit('a', 0.7), hit('c', 0.6)]])
    assert [result['chunk_id'] for result in merged] == ['a', 'c']
