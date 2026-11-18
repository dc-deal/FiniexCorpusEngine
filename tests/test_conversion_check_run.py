from backend.conversion.checks import check_flow, check_run


def record(page: int, attempt: int = 0, work: str = 'w', key: str | None = None) -> dict:
    return {'file': 'w.pdf', 'pdf_page': page, 'work': work, 'attempt': attempt, 'reading_key': key or f'k{page}a{attempt}'}


def test_a_page_is_represented_by_its_latest_attempt():
    latest = check_run.latest_per_page([record(1), record(1, attempt=1), record(2), record(3, attempt=1), record(3)])
    assert [row['reading_key'] for row in latest] == ['k1a1', 'k2a0', 'k3a1']


def test_a_later_reading_that_fails_the_validator_never_displaces_one_that_passes():
    # decision 174.a: finance p. 229's judge-hinted re-read came back malformed and displaced a first reading that passes
    malformed = {'k1a1', 'k2a1', 'k2a0'}
    latest = check_run.latest_per_page([record(1), record(1, attempt=1), record(2), record(2, attempt=1), record(3),
                                        record(3, attempt=1)], valid=lambda row: row['reading_key'] not in malformed)
    assert [row['reading_key'] for row in latest] == ['k1a0', 'k2a1', 'k3a1']  # both failing: the latest stays, as before


def test_the_flow_gets_today_s_class_and_stage_2_s_suspicion():
    rows = [record(1), record(2), record(3)]
    classes = {'k1a0': 'ok', 'k2a0': 'errored', 'k3a0': 'ok'}
    checks = {'k1a0': {'suspicious': True, 'unverifiable': []},
              'k3a0': {'suspicious': False, 'unverifiable': [{'block': 'b07', 'cls': 'table', 'why': 'raster_table'}]}}
    assert check_run.flow_pages(rows, classes, checks) == [
        {'key': 'k1a0', 'work': 'w', 'result_class': 'ok', 'suspicious': True, 'unverifiable': False},
        {'key': 'k2a0', 'work': 'w', 'result_class': 'errored', 'suspicious': False, 'unverifiable': False},
        {'key': 'k3a0', 'work': 'w', 'result_class': 'ok', 'suspicious': False, 'unverifiable': True}]


def test_a_later_plan_keeps_the_pages_with_a_block_stage_2_cannot_check():
    pages = [{'key': f'a{n}', 'work': 'a', 'result_class': 'ok', 'suspicious': False, 'unverifiable': n % 2 == 0} for n in range(30)]
    first = check_flow.select_for_judge(pages)
    kept = check_run.keep_sample(check_flow.select_for_judge(pages), pages, sorted(first.sampled))
    assert kept.unverifiable == {f'a{n}' for n in range(0, 30, 2)} and kept.unverifiable <= kept.keys


def test_a_blocked_page_is_never_sent_to_the_judge_and_ends_blocked():
    pages = check_run.flow_pages([record(1), record(2)], {'k1a0': 'errored', 'k2a0': 'ok'}, {})
    selection = check_flow.select_for_judge(pages)
    assert selection.keys == {'k2a0'}
    states = {row['key']: row['state'] for row in check_flow.outcomes(pages, {}, selection)['pages']}
    assert states == {'k1a0': 'blocked', 'k2a0': 'ok_unjudged'}


def test_a_later_plan_keeps_the_sample_it_drew_first_and_samples_only_a_new_work():
    pages = [{'key': f'a{n}', 'work': 'a', 'result_class': 'ok', 'suspicious': False} for n in range(30)]
    first = check_flow.select_for_judge(pages)
    grown = pages + [{'key': f'a{n}', 'work': 'a', 'result_class': 'ok', 'suspicious': False} for n in range(30, 60)] \
        + [{'key': f'b{n}', 'work': 'b', 'result_class': 'ok', 'suspicious': False} for n in range(5)]
    kept = check_run.keep_sample(check_flow.select_for_judge(grown), grown, sorted(first.sampled))
    assert {key for key in kept.sampled if key.startswith('a')} == first.sampled
    assert {key for key in kept.sampled if key.startswith('b')} == {f'b{n}' for n in range(5)}


def test_a_kept_sample_drops_a_page_that_is_no_longer_usable():
    pages = [{'key': 'a1', 'work': 'a', 'result_class': 'ok', 'suspicious': False},
             {'key': 'a2', 'work': 'a', 'result_class': 'malformed', 'suspicious': False}]
    kept = check_run.keep_sample(check_flow.select_for_judge(pages), pages, ['a1', 'a2'])
    assert kept.sampled == {'a1'}


def test_the_judge_is_the_frozen_contract_s():
    assert check_run.JUDGE_MODEL == 'claude-sonnet-5-5'


def test_every_command_takes_cells_and_only_submit_spends():
    parser = check_run.build_parser()
    for command in ('plan', 'report'):
        assert not hasattr(parser.parse_args([command, '--cells', 'FREE-SM']), 'cap')
    args = parser.parse_args(['submit', '--cells', 'FREE-SM', '--dry-run'])
    assert args.dry_run and args.cap == 5.0


def test_the_earlier_sample_comes_from_its_own_file_or_from_the_plans_before_it(tmp_path):
    from backend.conversion.store import reading_store
    store = reading_store.Store(tmp_path / 'vision')
    assert check_run.earlier_sample(store) == []
    store.write_report('check_plan_A.json', {'sampled': ['k2', 'k1']})
    store.write_report('check_plan_A_B.json', {'sampled': ['k3']})
    assert check_run.earlier_sample(store) == ['k1', 'k2', 'k3']
    store.write_report(check_run.SAMPLE_FILE, {'sampled': ['k9']})
    assert check_run.earlier_sample(store) == ['k9']


def test_a_reading_judged_once_is_judged_whatever_the_sheet_and_a_planted_copy_never_counts(tmp_path):
    from backend.conversion.store import reading_store
    store = reading_store.Store(tmp_path / 'vision')
    judge = {'kind': 'judge', 'model': check_run.JUDGE_MODEL, 'verdict': {'verdict': 'ok', 'outcome': 'ok', 'findings': []}}
    store.save_reading('aa' * 32, {**judge, 'reading_key': 'aa' * 32, 'target_key': 'r1', 'planted': None}, '{}')
    store.save_reading('bb' * 32, {**judge, 'reading_key': 'bb' * 32, 'target_key': 'r2', 'planted': 'swap_digits'}, '{}')
    store.save_reading('cc' * 32, {**judge, 'reading_key': 'cc' * 32, 'target_key': 'r3', 'model': 'another-model'}, '{}')
    assert set(check_run.verdicts_by_target(store)) == {'r1'}


def test_the_licensed_mirror_samples_twice_as_many_pages_with_the_same_stopping_share(tmp_path, monkeypatch):
    from backend.conversion.store import reading_store
    for mirror in ('free', 'licensed'):
        monkeypatch.setitem(reading_store.ROOTS, mirror, tmp_path / mirror)
    free, licensed = check_run.policy_of(reading_store.open_store('free')), check_run.policy_of(reading_store.open_store('licensed'))
    assert licensed.sample_per_work == 2 * free.sample_per_work
    assert licensed.stop_above / licensed.sample_per_work == free.stop_above / free.sample_per_work
