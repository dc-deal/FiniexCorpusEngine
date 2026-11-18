"""The held-out set is read once: a mechanism, not a sentence. Each evaluation command claims it in the ledger first."""

import json

import pytest

from backend.evaluation import answer_eval, pipeline_eval, retrieval_eval


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / 'holdout_ledger.json'
    path.write_text(json.dumps({'_about': [], 'runs': []}), encoding='utf-8')
    held_out = tmp_path / 'held_out.json'
    held_out.write_text(json.dumps({'questions': []}), encoding='utf-8')
    return path, held_out


def test_the_first_reading_is_written_before_anything_is_measured(ledger):
    path, held_out = ledger
    assert retrieval_eval.claim_holdout('pipeline_eval --holdout', path=held_out, ledger=path) == held_out
    (run,) = json.loads(path.read_text(encoding='utf-8'))['runs']
    assert run['file'] == held_out.as_posix() and run['command'] == 'pipeline_eval --holdout' and run['again'] is None
    assert run['at'] and run['commit']


def test_a_second_reading_is_refused_unless_it_says_why(ledger):
    path, held_out = ledger
    retrieval_eval.claim_holdout('pipeline_eval --holdout', path=held_out, ledger=path)
    with pytest.raises(retrieval_eval.HeldOutSpent, match='a second reading needs --again'):
        retrieval_eval.claim_holdout('answer_eval --holdout', path=held_out, ledger=path)
    retrieval_eval.claim_holdout('answer_eval --holdout', 'the first run crashed before any answer', path=held_out, ledger=path)
    runs = json.loads(path.read_text(encoding='utf-8'))['runs']
    assert [run['again'] for run in runs] == [None, 'the first run crashed before any answer']


@pytest.mark.parametrize('command', [retrieval_eval.main, pipeline_eval.main, answer_eval.main])
def test_every_evaluation_command_refuses_a_spent_held_out_set_before_it_spends(command, monkeypatch):
    # The refusal comes first: no model, no embedding, no key is touched (the offline guard would fail the test otherwise).
    def spent(command_line, again=None):
        raise retrieval_eval.HeldOutSpent('evaluation/held_out.json was read on 2026-11-12')
    monkeypatch.setattr(retrieval_eval, 'claim_holdout', spent)
    assert command(['--holdout']) == 2


def test_the_evaluation_reads_the_fresh_held_out_set_and_the_ledger_knows_the_spent_one():
    assert retrieval_eval.HOLDOUT.name == 'eval_questions_holdout_2026-11-06.json'
    runs = json.loads(retrieval_eval.HOLDOUT_LEDGER.read_text(encoding='utf-8'))['runs']
    assert runs[0]['file'] == 'evaluation/eval_questions_holdout.json'
