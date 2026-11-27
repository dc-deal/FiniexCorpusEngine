"""What the view's Verdicts tab reads from the export (#17, #18): which verdict stands, which judgement a person's verdict
answered, and a short label beside every reason."""

from backend.conversion.store import pipeline_db, reading_export


def judgement(key, at, counts=True, version='judge/1'):
    return {'judgement_key': key, 'stored_at': at, 'counts': counts, 'version': version, 'model': 'claude-sonnet-5-5',
            'mode': 'batch', 'verdict': 'bad'}


def test_only_the_latest_counting_judgement_of_the_served_reading_stands():
    listed = [judgement('a', '2026-11-05T09:00:00+00:00'), judgement('b', '2026-11-11T09:00:00+00:00', counts=False,
                                                                      version='judge/4'),
              judgement('c', '2026-11-12T09:00:00+00:00')]
    assert [one['standing'] for one in reading_export.judgements_with_standing(listed, served=True)] == [False, False, True]
    assert not any(one['standing'] for one in reading_export.judgements_with_standing(listed, served=False))  # a Lab reading's
    lab = reading_export.judgements_with_standing(listed, served=False, lab=True)
    assert not any(one['counts'] for one in lab)  # never served unless promoted, so nothing of it counts


def test_a_verdict_answers_the_judgement_it_names_else_the_one_that_counted_when_it_was_given():
    judgements = {'r': [judgement('a', '2026-11-05T09:00:00+00:00'), judgement('c', '2026-11-12T09:00:00+00:00')]}
    named = {'reading_key': 'r', 'answers_judgement': 'a', 'given_at': '2026-11-20T10:00:00.123456+00:00'}
    assert reading_export.answered_judgement(named, judgements) == ({**reading_export._judgement_summary(
        judgements['r'][0])}, False)
    between = {'reading_key': 'r', 'given_at': '2026-11-10T10:00:00.5+00:00'}
    answers, derived = reading_export.answered_judgement(between, judgements)
    assert answers['judgement_key'] == 'a' and derived  # c came later: the person saw a
    early = {'reading_key': 'r', 'given_at': '2026-11-01T10:00:00+00:00'}
    assert reading_export.answered_judgement(early, judgements) == (None, True)
    naive = {'reading_key': 'r', 'given_at': '2026-11-10T10:00:00'}  # a stamp without a zone is read as UTC, never a crash
    assert reading_export.answered_judgement(naive, judgements)[0]['judgement_key'] == 'a'


def test_of_a_person_s_verdicts_the_one_the_page_is_served_by_stands_and_each_has_its_short_label():
    def given(block, at, reason='judge_false_alarm', key='r', verdict='accept'):
        return {'reading_key': key, 'block': block, 'verdict': verdict, 'reason': reason, 'tag': None, 'note': None,
                'given_by': 'the operator', 'given_at': at, 'correction': None, 'judge_assessment': 'false_alarm'}
    verdicts = [given('b03', '2026-11-10T10:00:00+00:00'), given(None, '2026-11-11T10:00:00+00:00', 'other'),
                given('b03', '2026-11-12T10:00:00+00:00'), given('b05', '2026-11-12T11:00:00+00:00', verdict='note'),
                given(None, '2026-11-13T10:00:00+00:00', key='old')]
    shown = reading_export.human_of(verdicts, 'r', [], {})
    # the latest accept or reject that applies, as served_readings.human_standing serves by; a note never stands (review, 27 Nov)
    assert [one['standing'] for one in shown] == [False, False, True, False, False]
    assert shown[0]['reason_short'] == 'false alarm' and shown[1]['reason_short'] == 'other'
    assert shown[0]['judge_assessment_short'] == 'false alarm'
    assert set(pipeline_db.HUMAN_REASON_SHORT) == set(pipeline_db.HUMAN_REASONS)
    assert set(pipeline_db.JUDGE_ASSESSMENT_SHORT) == set(pipeline_db.JUDGE_ASSESSMENTS)


def test_a_verdict_stores_the_judgement_it_answered(tmp_path):
    path = tmp_path / 'p.sqlite'
    pipeline_db.give_verdict('free', 'w.pdf', 3, 'r', 'accept', 'judge_false_alarm', 'the operator', path=path,
                             answers_judgement='j' * 64)
    pipeline_db.give_verdict('free', 'w.pdf', 3, 'r', 'note', 'other', 'the operator', note='looked', path=path)
    stored = pipeline_db.human_verdicts('free', path)[('w.pdf', 3)]
    assert [one['answers_judgement'] for one in stored] == ['j' * 64, None]
