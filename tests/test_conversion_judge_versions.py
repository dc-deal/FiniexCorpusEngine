"""The judge's versions and the rule that voids a finding naming no difference (decisions 146.a, 147.a)."""

import json

import pytest

from backend.conversion.checks import check_run
from backend.conversion.judge import page_judge
from backend.conversion.store import reading_store


def test_one_judge_version_is_active_and_judge_2_is_a_prototype_one_sentence_apart():
    assert page_judge.active_version() == 'judge/1'
    assert page_judge.state_of('judge/2') == 'prototype'
    first, second = page_judge.system_prompt('judge/1'), page_judge.system_prompt('judge/2')
    added = second.replace(first.split('NOT AN ERROR')[0], '', 1)
    assert first != second and 'A proper name, a brand or an unusual spelling' in second and 'proper name' not in first
    assert len(second) - len(first) < 200 and added  # one sentence, nothing else moved
    with pytest.raises(ValueError):
        page_judge.state_of('judge/9')


def test_every_registered_prompt_file_is_frozen_and_each_role_has_one_active_version():
    frozen = json.loads((page_judge.CONVERSION / 'frozen_contract.json').read_text(encoding='utf-8'))['sha256']
    versions = json.loads(page_judge.VERSIONS.read_text(encoding='utf-8'))['versions']
    assert all(name in frozen for version in versions for name in version['files'])
    for role in {version['role'] for version in versions}:
        assert [version['state'] for version in versions if version['role'] == role].count('active') == 1


def test_an_old_record_was_judged_by_judge_1_and_a_prototype_has_a_cell_of_its_own():
    assert page_judge.version_of({}) == 'judge/1' and page_judge.version_of({'judge_version': 'judge/2'}) == 'judge/2'
    assert page_judge.cell_of('claude-sonnet-5-5', 'judge/1') == 'JUDGE-claude-sonnet-5-5'
    assert page_judge.cell_of('claude-sonnet-5-5', 'judge/2') == 'JUDGE-claude-sonnet-5-5-judge2'


def test_asking_again_makes_a_new_key_and_asking_once_keeps_every_key_made_before():
    spec = dict(target_key='t', model='claude-sonnet-5-5', system_sha='s', image_sha='i', view_sha='v', sheet_shas=[], max_tokens=10)
    assert page_judge.judge_key(**spec) == page_judge.judge_key(**spec, again=0) != page_judge.judge_key(**spec, again=1)


CARLYSE = {'kind': 'wrong_word', 'block': 'b12', 'severity': 'major',
           'evidence': "printed 'Carlyse' is 'Carlyse'? page shows 'Carlyse'; written 'Carlyse'"}
BLOCK = 'Arthur and Carlyse Ciocca Charitable Foundation'


@pytest.mark.parametrize('finding, block, layer, void', [
    (CARLYSE, None, None, True),  # one string quoted as printed and as written (judge/1 on finance p. 5)
    ({'kind': 'omission', 'evidence': "printed 'a' written 'a' (identical)"}, None, None, True),
    ({'kind': 'wrong_word', 'evidence': "printed 'Carlyse Ciocca' wait: page prints 'Carlyse'"}, BLOCK, BLOCK, True),  # judge/2
    ({'kind': 'wrong_word', 'evidence': "printed 'Carlyse Ciocca' wait: page prints 'Carlyse'"}, BLOCK, 'Carlyle Ciocca', False),
    ({'kind': 'wrong_word', 'evidence': "printed 'Carlyle', written 'Carlyse'"}, BLOCK, BLOCK, False),  # a real wrong word
    ({'kind': 'wrong_value', 'evidence': "printed 'a share at $2,467.'; written '$2,467.48'"}, 'a share at $2,467.48', 'x', False),
    ({'kind': 'wrong_word', 'evidence': "printed 'Carlyse Ciocca'"}, BLOCK, BLOCK, False),  # one quote: no pair to compare
    ({'kind': 'omission', 'evidence': "printed 'Carlyse Ciocca', written 'Carlyse'"}, BLOCK, BLOCK, False),
])
def test_a_finding_is_void_only_where_it_names_no_difference(finding, block, layer, void):
    assert page_judge.contradicts_itself(finding, block, layer) == void


def test_a_bad_verdict_whose_every_major_finding_is_void_comes_out_ok_and_keeps_the_judge_s_own():
    verdict = page_judge.with_void({'verdict': 'bad', 'outcome': 'issue', 'findings': [CARLYSE]})
    assert (verdict['outcome'], verdict['judge_outcome'], verdict['void'], verdict['findings'][0]['void']) == ('ok', 'issue', 1, True)
    real = {'kind': 'wrong_word', 'block': 'b01', 'severity': 'major', 'evidence': "printed 'Carlyle', written 'Carlyse'"}
    assert page_judge.with_void({'verdict': 'bad', 'outcome': 'issue', 'findings': [CARLYSE, real]})['outcome'] == 'issue'
    untouched = {'verdict': 'bad', 'outcome': 'issue', 'findings': [real]}
    assert page_judge.with_void(untouched) is untouched


def judge_record(key: str, target: str, **fields) -> dict:
    return {'kind': 'judge', 'model': check_run.JUDGE_MODEL, 'reading_key': key, 'target_key': target, 'planted': None,
            'verdict': {'verdict': 'ok', 'outcome': 'ok', 'findings': []}, **fields}


def test_a_prototype_s_verdict_or_one_asked_again_never_counts_but_stays_in_the_history(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    store.save_reading('aa' * 32, judge_record('aa' * 32, 'r1', stored_at='1'), '{}')
    bad = {'verdict': 'bad', 'outcome': 'issue', 'findings': [{'kind': 'invented', 'block': 'b01', 'severity': 'major', 'evidence': 'x'}]}
    store.save_reading('bb' * 32, judge_record('bb' * 32, 'r1', judge_version='judge/2', verdict=bad, stored_at='2'), '{}')
    store.save_reading('cc' * 32, judge_record('cc' * 32, 'r1', replicate=1, verdict=bad, stored_at='3'), '{}')
    store.save_reading('dd' * 32, judge_record('dd' * 32, 'r2', judge_version='judge/2', stored_at='4'), '{}')
    counted = check_run.verdicts_by_target(store)
    assert set(counted) == {'r1'} and counted['r1']['reading_key'] == 'aa' * 32
    history = check_run.judgements_by_target(store)['r1']
    assert [(item['version'], item['again'], item['counts']) for item in history] == [('judge/1', 0, True), ('judge/2', 0, False),
                                                                                     ('judge/1', 1, False)]


def test_a_verdict_written_before_decision_97_a_reads_in_today_s_words_in_the_history(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    old = {'verdict': 'bad', 'outcome': 'bin', 'findings': [{'kind': 'invented', 'block': 'b01', 'severity': 'major', 'evidence': 'x'}]}
    store.save_reading('aa' * 32, judge_record('aa' * 32, 'r1', verdict=old), '{}')
    assert check_run.judgements_by_target(store)['r1'][0]['outcome'] == 'issue'


def test_a_version_that_proposes_reader_rules_has_its_schema_model_and_bigger_budget_and_the_others_keep_theirs():
    # decision 197.a: judge/4 runs on Opus and proposes rules for the reader; every key made before stays the same
    from backend.conversion.judge import page_judge

    assert page_judge.model_of('judge/4') == 'claude-opus-5-5' and page_judge.model_of('judge/2') == 'claude-sonnet-5-5'
    assert page_judge.schema_of('judge/4') is page_judge.VERDICT_SCHEMA_WITH_RULES
    assert page_judge.schema_of('judge/1') is page_judge.VERDICT_SCHEMA and page_judge.schema_of(None) is page_judge.VERDICT_SCHEMA
    same = dict(target_key='t', model='claude-sonnet-5-5', system_sha='s', image_sha='i', view_sha='v', sheet_shas=[], max_tokens=2000)
    assert page_judge.judge_key(**same) == page_judge.judge_key(**same, schema=page_judge.VERDICT_SCHEMA)
    assert page_judge.judge_key(**same) != page_judge.judge_key(**same, schema=page_judge.VERDICT_SCHEMA_WITH_RULES)
    answer = ('{"verdict": "bad", "findings": [], "reader_rules": [{"kind": "format_rule", "block": "b03", "rule": "Write a '
              'T-account as a table.", "class": "", "attribute": "", "value": ""}, {"kind": "guess", "block": "b01", "rule": "x", '
              '"class": "", "attribute": "", "value": ""}]}')
    verdict = page_judge.parse_verdict(answer)
    assert [rule['kind'] for rule in verdict.reader_rules] == ['format_rule']  # a kind outside the list is dropped
    assert verdict.as_dict()['reader_rules'][0]['block'] == 'b03'
    assert 'reader_rules' not in page_judge.parse_verdict('{"verdict": "ok", "findings": []}').as_dict()


def test_proposals_that_say_the_same_merge_into_one_rule():
    from backend.conversion.checks import check_run

    one = {'kind': 'format_rule', 'rule': 'Write each T-account as a table, debit and credit as columns.'}
    two = {'kind': 'format_rule', 'rule': 'write T-account as table with debit and credit columns'}
    assert check_run.rule_key(one) == check_run.rule_key(two)
    assert check_run.rule_key({'kind': 'class', 'class': 'Decoration', 'value': 'chapter_art'}) == \
        check_run.rule_key({'kind': 'class', 'class': 'decoration', 'value': 'Chapter_Art '})
    assert check_run.rule_key(one) != check_run.rule_key({'kind': 'format_rule', 'rule': 'Never mark a readable box unreadable.'})


def test_a_judge_s_rules_for_the_reader_stand_beside_its_findings_in_the_history(tmp_path):
    # decision 202.a: line 2 shows judge/4's proposals read-only; a version without them has an empty list
    store = reading_store.Store(tmp_path / 'vision')
    rule = {'kind': 'format_rule', 'block': 'b07', 'rule': 'Give each row the table width.', 'class': '', 'attribute': '', 'value': ''}
    store.save_reading('aa' * 32, judge_record('aa' * 32, 'r1', judge_version='judge/4', stored_at='1',
                                               verdict={'verdict': 'ok', 'outcome': 'ok', 'findings': [], 'reader_rules': [rule]}), '{}')
    store.save_reading('bb' * 32, judge_record('bb' * 32, 'r1', stored_at='2'), '{}')
    history = check_run.judgements_by_target(store)['r1']
    assert [item['reader_rules'] for item in history] == [[rule], []]
