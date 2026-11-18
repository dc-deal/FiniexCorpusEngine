from backend.conversion.checks.check_flow import Policy, issue_entries, outcomes, select_for_judge


def pages_of(work, count, suspicious=0):
    return [{'key': f'{work}-{i:03d}', 'work': work, 'result_class': 'ok', 'suspicious': i < suspicious} for i in range(count)]


def ok():
    return {'verdict': 'ok', 'findings': [], 'outcome': 'ok'}


def bad():
    return {'verdict': 'bad', 'findings': [{'kind': 'wrong_value', 'severity': 'major'}], 'outcome': 'issue'}


def test_the_judge_sees_every_suspicious_page_plus_a_sample_per_work():
    pages = pages_of('a', 50, suspicious=7) + pages_of('b', 5)
    selection = select_for_judge(pages)
    assert len(selection.suspicious) == 7 and len(selection.sampled) == 20 + 5
    assert selection.suspicious.isdisjoint(selection.sampled)


def test_the_sample_is_reproducible_and_differs_by_work():
    one = select_for_judge(pages_of('a', 100))
    assert one == select_for_judge(pages_of('a', 100))
    other = select_for_judge(pages_of('b', 100))
    assert {key[2:] for key in one.sampled} != {key[2:] for key in other.sampled}


def test_a_failed_format_or_a_blocked_page_is_never_judged():
    pages = pages_of('a', 2) + [{'key': 'x', 'work': 'a', 'result_class': 'malformed'}, {'key': 'y', 'work': 'a', 'result_class': 'errored'}]
    assert not {'x', 'y'} & select_for_judge(pages).keys


def test_pages_stay_in_their_own_states():
    pages = pages_of('a', 4) + [{'key': 'blocked', 'work': 'a', 'result_class': 'errored'}, {'key': 'format', 'work': 'a', 'result_class': 'malformed'}]
    selection = select_for_judge(pages, Policy(sample_per_work=2))
    judged = sorted(selection.keys)
    result = outcomes(pages, {judged[0]: ok(), judged[1]: bad()}, selection, Policy(sample_per_work=2))
    states = {row['key']: row['state'] for row in result['pages']}
    assert states[judged[0]] == 'ok' and states[judged[1]] == 'issue'
    assert states['blocked'] == 'blocked' and states['format'] == 'issue'
    assert sorted(states.values()).count('ok_unjudged') == 2
    assert result['works']['a']['blocked'] == 1 and result['works']['a']['issues'] == 2


def test_a_work_stops_above_the_limit_on_its_sample_only():
    pages = pages_of('a', 30, suspicious=6)
    selection = select_for_judge(pages, Policy(sample_per_work=20, stop_above=3))
    suspicious_bad = {key: bad() for key in selection.suspicious}
    result = outcomes(pages, suspicious_bad, selection, Policy(sample_per_work=20, stop_above=3))
    assert not result['works']['a']['stopped'], 'suspicious pages are chosen for being doubtful: they must not stop a work'
    sample = sorted(selection.sampled)
    three = {key: bad() for key in sample[:3]}
    assert not outcomes(pages, three, selection)['works']['a']['stopped']
    four = {key: bad() for key in sample[:4]}
    stopped = outcomes(pages, four, selection)
    assert stopped['works']['a']['stopped']
    assert 'ok_unjudged' not in stopped['works']['a']['states'] and 'stopped' in stopped['works']['a']['states']


def test_the_bin_keeps_ids_and_reasons():
    pages = pages_of('a', 1)
    selection = select_for_judge(pages)
    entries = issue_entries(outcomes(pages, {'a-000': bad()}, selection))
    assert entries == [{'key': 'a-000', 'work': 'a', 'reasons': ['judge: bad', 'wrong_value']}]


def test_every_page_with_a_block_stage_2_cannot_check_is_judged_and_never_stops_a_work():
    pages = pages_of('a', 60, suspicious=2)
    for page in pages[10:40]:
        page['unverifiable'] = True
    selection = select_for_judge(pages)
    assert selection.unverifiable == {page['key'] for page in pages[10:40]} <= selection.keys
    assert selection.sampled == select_for_judge(pages_of('a', 60, suspicious=2)).sampled, 'the random sample stays the same draw'
    hard_only = selection.unverifiable - selection.sampled
    result = outcomes(pages, {key: bad() for key in hard_only}, selection)
    assert not result['works']['a']['stopped'] and result['works']['a']['sample_bad'] == 0
    assert {row['key'] for row in result['pages'] if row['unverifiable']} == selection.unverifiable


def test_where_every_page_is_judged_a_work_stops_on_the_share_not_the_count():
    pages = pages_of('a', 100)
    selection = select_for_judge(pages, Policy(sample_per_work=10 ** 6, stop_above=6, stop_share=0.15))
    eleven = {page['key']: bad() for page in pages[:11]}
    assert not outcomes(pages, eleven, selection, Policy(sample_per_work=10 ** 6, stop_above=6, stop_share=0.15))['works']['a']['stopped']
    sixteen = {page['key']: bad() for page in pages[:16]}
    assert outcomes(pages, sixteen, selection, Policy(sample_per_work=10 ** 6, stop_above=6, stop_share=0.15))['works']['a']['stopped']


def test_a_re_read_after_the_judge_s_issue_is_judged_and_marked_whatever_stage_2_says():
    from backend.conversion.checks.check_flow import Selection

    selection = Selection(frozenset(), frozenset(), frozenset(), frozenset({'w-001'}))
    assert 'w-001' in selection.keys
    rows = outcomes(pages_of('w', 2), {'w-001': ok()}, selection)['pages']
    assert [(row['key'], row['reread'], row['state']) for row in rows] == [('w-000', False, 'ok_unjudged'), ('w-001', True, 'ok')]
