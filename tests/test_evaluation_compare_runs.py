"""Two answer measurements compared question by question, as phase 6's gates ask."""

from backend.evaluation import compare_runs


def question(qid, recall, rr, got='answer', expected='answer', quotes=True, digests=('d1',), passages=('c1',)):
    retrieval = None if recall is None else {'section': {'recall_5': recall, 'hit_5': int(recall > 0), 'rr': rr},
                                             'document': {'recall_5': recall, 'hit_5': int(recall > 0), 'rr': rr}}
    return {'id': qid, 'question': f'question {qid}', 'expected_digests': list(digests) if digests else None,
            'score': {'retrieval': retrieval, 'correct': got == expected, 'got': got, 'expected': expected},
            'turn': {'behaviour': got, 'quotes': [{'passage': 1}] if quotes else [],
                     'retrieved': [{'number': n, 'chunk_id': chunk} for n, chunk in enumerate(passages, 1)]}}


def record(label, *questions):
    return {'label': label, 'questions': list(questions)}


def test_a_change_that_helps_without_harm_is_an_improvement_and_lists_what_moved():
    base = record('base', question('a', 0.0, 0.0), question('b', 0.5, 0.5), question('c', 1.0, 1.0), question('z', None, None))
    new = record('new', question('a', 1.0, 1.0), question('b', 1.0, 1.0), question('c', 1.0, 1.0), question('z', None, None))
    result = compare_runs.compare(base, new)
    assert result['scored'] == 3 and result['verdict'] in ('improvement', 'holds')
    assert result['section_recall_5']['difference'] > 0
    assert [(m['id'], m['rank_before'], m['rank_after'], m['expected_text']) for m in result['moved']] == [
        ('a', None, 1, 'unchanged'), ('b', 2, 1, 'unchanged')]


def test_a_move_with_changed_text_and_one_without_digests_are_told_apart():
    base = record('base', question('a', 0.5, 0.5, digests=('old',)), question('b', 0.5, 0.5, digests=None))
    new = record('new', question('a', 1.0, 1.0, digests=('new',)), question('b', 1.0, 1.0))
    assert [m['expected_text'] for m in compare_runs.compare(base, new)['moved']] == ['changed', 'unknown']


def test_a_change_that_costs_behaviours_or_quotes_is_dropped_even_when_recall_rises():
    base = record('base', question('a', 0.5, 0.5), question('b', 0.5, 0.5), question('c', 0.5, 0.5))
    worse_behaviour = record('new', question('a', 1.0, 1.0, got='clarify', passages=('c2',)),
                             question('b', 1.0, 1.0, got='not_found', passages=('c2',)),
                             question('c', 1.0, 1.0, got='decline_harmful', passages=('c2',)))  # three lost on altered passages
    assert compare_runs.compare(base, worse_behaviour)['verdict'] == 'dropped'
    fewer_quotes = record('new', *(question(qid, 1.0, 1.0, quotes=False, passages=('c2',)) for qid in 'abc'))
    assert compare_runs.compare(base, fewer_quotes)['verdict'] == 'dropped'


def test_two_lost_behaviours_hold_and_three_do_not():
    # The slack is the generator's noise a replay measured on identical passages: two questions (decision 106, 6 Nov).
    base = record('base', *(question(qid, 0.5, 0.5) for qid in 'abcd'))
    lost = lambda qid: question(qid, 0.5, 0.5, got='clarify', passages=('c2',))
    two = record('new', lost('a'), lost('b'), question('c', 0.5, 0.5), question('d', 0.5, 0.5))
    three = record('new', lost('a'), lost('b'), lost('c'), question('d', 0.5, 0.5))
    assert compare_runs.compare(base, two)['verdict'] == 'holds'
    assert compare_runs.compare(base, three)['verdict'] == 'dropped'


def test_what_the_generator_changes_on_identical_passages_does_not_count_against_a_change():
    # Decision 116.a (8 Nov), written before the run it first judged: on identical passages the generator alone moved two to
    # three questions in every run, and the share form dropped a change that answered one more question without a quote.
    base = record('base', *(question(qid, 0.5, 0.5) for qid in 'abc'), question('d', 0.5, 0.5, got='not_found', quotes=False))
    noise = record('new', *(question(qid, 0.5, 0.5, got='clarify', quotes=False) for qid in 'abc'),
                   question('d', 0.5, 0.5, got='not_found', quotes=False))
    result = compare_runs.compare(base, noise)
    assert result['verdict'] == 'holds' and result['altered']['questions'] == []
    answered_unquoted = record('new', *(question(qid, 0.5, 0.5) for qid in 'abc'),
                               question('d', 0.5, 0.5, got='not_found', expected='not_found', quotes=False, passages=('c2',)))
    assert compare_runs.compare(base, answered_unquoted)['verdict'] == 'holds'


def test_the_gate_names_the_questions_whose_passages_changed():
    base = record('base', question('a', 0.5, 0.5, passages=('c1', 'c2')), question('b', 0.5, 0.5, passages=('c1', 'c2')))
    new = record('new', question('a', 0.5, 0.5, passages=('c2', 'c1')), question('b', 0.5, 0.5, passages=('c1', 'c2')))
    result = compare_runs.compare(base, new)
    assert result['altered']['questions'] == ['a']  # an order of the same passages counts as altered
    assert "the gate's questions: passages altered | 1: a" in compare_runs.markdown(result)


def test_records_of_other_questions_or_without_scores_are_not_comparable():
    base = record('base', question('a', 0.5, 0.5), question('b', 0.5, 0.5))
    lost_one = record('new', question('a', 1.0, 1.0))
    other_set = record('new', question('h1', 1.0, 1.0), question('h2', 1.0, 1.0))
    unscored = record('new', question('a', None, None), question('b', None, None))
    for new in (lost_one, other_set, unscored):
        assert compare_runs.compare(base, new)['verdict'] == 'not comparable'
    assert compare_runs.compare(base, lost_one)['in_one_record_only'] == ['b']
    assert 'Questions in one record only: b.' in compare_runs.markdown(compare_runs.compare(base, lost_one))


def test_the_interval_is_reproducible_and_brackets_the_mean():
    differences = [0.0, 0.5, -0.25, 1.0, 0.0, 0.25]
    assert compare_runs.interval(differences) == compare_runs.interval(differences)
    mean, low, high = compare_runs.interval(differences)
    assert low <= mean <= high
