"""A page's readings and verdicts in one form (issue #18): its tabs' rows, every word and count served, built from invented
readings and verdicts alone, so no licensed text or title stands in a tracked file."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.diagnostics import page_form, readings, verdicts
from backend.diagnostics.app import create_app

LOCAL = 'http://127.0.0.1'


def a_finding(severity='major', void=False):
    return SimpleNamespace(kind='omission', block='b03', severity=severity, evidence=None, void=void)


def a_judgement(**fields):
    given = {'version': 'judge/1', 'version_state': 'active', 'model': 'an-invented-judge', 'mode': 'batch', 'again': 0,
             'stored_at': '2026-11-05T08:29:30+00:00', 'verdict': 'ok', 'outcome': 'ok', 'judge_outcome': None, 'findings': [],
             'reader_rules': None, 'cost_usd': 0.0075, 'counts': True, 'recall': 'k1:judge/1:0', 'judgement_key': 'j1',
             'standing': True, 'agent_prompt': None}
    return SimpleNamespace(**{**given, **fields})


def an_attempt(key, **fields):
    given = {'reading_key': key, 'number': 1, 'purpose': 'first reading', 'cell': 'AN-INVENTED-CELL', 'reader_version': 'page/1',
             'prototype': None, 'test_reading': None, 'promoted': None, 'agent_prompt': None, 'retry_of': None,
             'retry_of_number': None, 'model': 'an-invented-reader', 'mode': 'batch', 'attempt': 0, 'class_now': 'ok',
             'stored_at': '2026-11-02T14:46:20+00:00', 'deviation': None, 'cost_usd': 0.016, 'format_errors': [], 'check': None,
             'judgements': [], 'shown': False}
    return SimpleNamespace(**{**given, **fields})


def a_person(**fields):
    given = {'reading_key': 'k1', 'applies': True, 'block': None, 'verdict': 'accept', 'reason': 'judge_false_alarm',
             'reason_text': 'the judge reported an error that is not there', 'reason_short': 'false alarm',
             'judge_assessment_short': None, 'judge_assessment_text': None, 'note': None, 'given_by': 'maintainer',
             'given_at': '2026-11-12T10:02:00+00:00', 'by_a_person': True, 'standing': True, 'archived': None,
             'answers': SimpleNamespace(judgement_key='j1', version='judge/1', model='an-invented-judge',
                                        stored_at='2026-11-05T08:29:30+00:00'), 'answers_derived': False}
    return SimpleNamespace(**{**given, **fields})


def test_a_page_s_form_holds_its_readings_its_lab_and_every_verdict_each_counted_and_said():
    served = an_attempt('k1', shown=True, judgements=[a_judgement()])
    prototype = an_attempt('k2', number=2, reader_version='page/2', prototype=True, stored_at='2026-11-11T08:34:52+00:00',
                           judgements=[a_judgement(version='judge/4', version_state='prototype', counts=False, standing=False,
                                                   recall='k2:judge/4:0', judgement_key='j2',
                                                   stored_at='2026-11-11T08:46:18+00:00')])
    test = an_attempt('k3', number=3, reader_version='page/1', prototype=True, test_reading=True, model='an-invented-local-model',
                      mode='local', class_now='malformed', stored_at='2026-11-27T11:28:58+00:00', cost_usd=0.0)
    form = page_form.form_of([served, prototype, test], [a_person()])
    assert (form.readings_count, form.lab_count, form.verdicts.count) == (1, 2, 2)
    assert form.shown_judgement == 'j1'
    reading = form.readings[0]
    # the row says its kind, its result in words, and folds open to its verdicts, newest first (31.a): a person's, naming the
    # judge it answers (36.a), above the judge's
    assert (reading.kind_said, reading.result_state, reading.result_said, reading.shown, reading.recall) == ('reading', 'ok', 'ok',
                                                                                                             True, None)
    assert [(one.kind_said, one.version_said, one.verdict_said) for one in reading.verdicts] == [
        ('person', 'answers judge/1', 'accept · false alarm'), ('judge', 'counts', 'ok')]
    # the judge it answers by its model and its moment in the person's card, a time the card says as a person reads it
    card = {row.label: row for row in reading.verdicts[0].hover}
    assert (card['answers'].value, card['judged'].at, 'assigned' in card) == ('judge/1 · an-invented-judge', '2026-11-05T08:29:30+00:00',
                                                                              False)
    # the keys stand in the hover alone
    assert {'reading key', 'cell', "the reader's attempt"} <= {row.label for row in reading.hover}
    # the Lab: newest first; a test reading named as one, its class its result; a prototype's judge never counts there
    assert [(one.key, one.result_said, one.test_reading, one.promotable) for one in form.lab] == [
        ('k3', 'malformed', True, True), ('k2', 'ok', False, False)]
    assert form.lab[1].verdicts[0].version_said == 'prototype' and form.lab[0].recall == 'k3'
    # the verdicts as shown (decision 26): the served reading's alone, newest first, a person's naming the judge it answers
    shown = form.verdicts
    assert (shown.said, shown.recalled, shown.why_not) == ('as shown: the verdicts on the served reading', False, None)
    assert [(row.kind_said, row.standing_said, row.about, row.recall, row.judge_said) for row in shown.rows] == [
        ('person', 'standing', 'the page', None, 'judge/1'), ('judge', 'standing', 'the page', 'k1:judge/1:0', '—')]
    assert (shown.rows[0].reason, shown.rows[0].who_said) == ('false alarm', 'a person')


def test_a_judge_s_word_is_the_result_that_counts_its_own_struck_beside_it_and_its_findings_said_short():
    struck = a_judgement(verdict='bad', outcome='ok', findings=[SimpleNamespace(kind='wrong_word', block='b12', severity='major',
                                                                                 evidence=None, void=True)])
    real = a_judgement(verdict='bad', outcome='issue', findings=[a_finding(), a_finding('minor', void=True)])
    minor = a_judgement(findings=[SimpleNamespace(kind='invented', block='b09', severity='minor', evidence=None, void=False)])
    rows = [page_form.judge_verdict(one) for one in (struck, real, minor)]
    # 32.a: "ok" where code struck what made the judge say "bad", its own word beside it to be struck; a real bad stays bad
    assert [(row.verdict_said, row.overruled, row.state) for row in rows] == [
        ('ok · 1 finding struck by code', 'bad', 'ok'), ('bad · 2 findings: 1 major, 1 struck by code', None, 'issue'),
        ('ok · 1 finding: minor', None, 'ok')]
    # 33.a: in the Verdicts tab, a finding by its kind and its severity or its striking, about the blocks it names
    tab = [page_form.judge_row(an_attempt('k1'), one) for one in (struck, real, minor, a_judgement())]
    assert [(row.verdict, row.overruled, row.reason, row.about, row.judge_said) for row in tab] == [
        ('ok', 'bad', 'wrong word, struck by code', 'b12', '—'),
        ('bad', None, '2 findings: 1 major, 1 struck by code', 'b03', '—'),
        ('ok', None, 'invented, minor', 'b09', '—'),
        ('ok', None, None, 'the page', '—')]
    # several blocks in their order, and the page where a finding names none
    many = a_judgement(findings=[SimpleNamespace(kind='omission', block='b12', severity='major', evidence=None, void=False),
                                 SimpleNamespace(kind='omission', block='b09', severity='minor', evidence=None, void=False),
                                 SimpleNamespace(kind='omission', block=None, severity='minor', evidence=None, void=False)])
    assert page_form.finding_blocks(many) == 'b09, b12, the page'


def test_the_lab_holds_the_trials_beside_the_test_readings_and_readings_only_what_counts():
    served = an_attempt('k1', number=2, shown=True, stored_at='2026-11-09T09:00:00+00:00', judgements=[
        a_judgement(stored_at='2026-11-09T10:00:00+00:00'),
        a_judgement(counts=False, standing=False, again=1, recall='k1:judge/1:1', stored_at='2026-11-09T17:00:00+00:00'),
        a_judgement(version='judge/4', version_state='prototype', counts=False, standing=False, recall='k1:judge/4:0',
                    stored_at='2026-11-10T22:00:00+00:00')])
    earlier = an_attempt('k0', stored_at='2026-11-02T09:00:00+00:00', judgements=[
        a_judgement(standing=False, recall='k0:judge/1:0', stored_at='2026-11-04T12:00:00+00:00')])
    test = an_attempt('k3', number=3, prototype=True, test_reading=True, stored_at='2026-11-20T08:00:00+00:00')
    form = page_form.form_of([earlier, served, test], [a_person(reading_key='k1', given_at='2026-11-12T09:00:00+00:00')])
    # Readings: the judgements that count and the person's verdicts, newest first
    assert [[(one.kind_said, one.version_said) for one in reading.verdicts] for reading in form.readings] == [
        [('person', 'answers judge/1'), ('judge', 'counts')], [('judge', 'counts')]]
    # the Lab: the test reading and the served reading's own row with its trials alone, newest first; counted by its trials
    assert [(one.key, one.shown, [verdict.version_said for verdict in one.verdicts]) for one in form.lab] == [
        ('k3', False, []), ('k1', True, ['prototype', 'asked again'])]
    assert (form.readings_count, form.lab_count) == (2, 3)


def test_a_recalled_trial_has_no_verdicts_and_says_why():
    served = an_attempt('k1', shown=True, judgements=[
        a_judgement(), a_judgement(version='judge/4', version_state='prototype', counts=False, standing=False, recall='k1:judge/4:0')])
    test = an_attempt('k3', number=2, prototype=True, test_reading=True)
    attempts = [served, test]
    for shown in (page_form.shown_verdicts(attempts, [a_person()], 'k1', 1, served.judgements[1]),
                  page_form.shown_verdicts(attempts, [], 'k3', 2)):
        assert (shown.count, shown.rows, shown.why_not, shown.recalled) == (None, [], page_form.TRIAL, True)


def test_the_verdicts_as_then_show_a_recall_s_moment_and_nothing_later():
    earlier = an_attempt('k0', stored_at='2026-11-02T09:00:00+00:00', judgements=[
        a_judgement(standing=False, recall='k0:judge/1:0', stored_at='2026-11-04T12:47:00+00:00')])
    served = an_attempt('k1', number=2, shown=True, stored_at='2026-11-09T09:21:00+00:00', judgements=[
        a_judgement(stored_at='2026-11-09T10:56:00+00:00'),
        a_judgement(version='judge/5', recall='k1:judge/5:0', stored_at='2026-11-15T10:00:00+00:00')])
    attempts = [earlier, served]
    people = [a_person(block='b12', given_at='2026-11-10T19:20:00+00:00'),
              a_person(block='b12', given_at='2026-11-12T11:49:00+00:00'),
              a_person(block='b03', given_at='2026-11-11T08:00:00+00:00', archived=True, archived_at='2026-11-13T00:00:00+00:00')]
    # the standing view: the newer person's verdict on b12 alone (34.a, the older one replaced), the latest counting judge
    now = page_form.form_of(attempts, [SimpleNamespace(**{**vars(people[0]), 'standing': False}), *people[1:]]).verdicts
    assert [(row.kind_said, row.time) for row in now.rows] == [('judge', '2026-11-15T10:00:00+00:00'), ('person', '2026-11-12T11:49:00+00:00')]
    # judge/1 recalled: as then, at its own moment; no person had judged yet, and judge/5 came later
    first = page_form.shown_verdicts(attempts, people, 'k1', 2, served.judgements[0])
    assert (first.said, first.said_at) == ('as then: the verdicts on reading 2 on', '2026-11-09T10:56:00+00:00')
    assert [(row.recall, row.standing_said, row.recalled) for row in first.rows] == [('k1:judge/1:0', 'recalled', True)]
    # judge/5 recalled: itself, the latest counting one; the person's latest on b12 by then, and not the verdict on b03,
    # archived before it
    late = page_form.shown_verdicts(attempts, people, 'k1', 2, served.judgements[1])
    assert [(row.kind_said, row.standing_said, row.about, row.time) for row in late.rows] == [
        ('judge', 'recalled', 'the page', '2026-11-15T10:00:00+00:00'),
        ('person', 'standing', 'b12', '2026-11-12T11:49:00+00:00')]
    # at a moment before that reset, the b03 verdict still applies: archived only after then
    middle = page_form.shown_verdicts(attempts, people, 'k1', 2, SimpleNamespace(**{**vars(served.judgements[1]),
                                                                                    'stored_at': '2026-11-12T12:00:00+00:00'}))
    assert [(row.about, row.time) for row in middle.rows if row.kind == 'person'] == [
        ('b12', '2026-11-12T11:49:00+00:00'), ('b03', '2026-11-11T08:00:00+00:00')]
    # the earlier reading recalled: as it stood until reading 2 replaced it, its judge/1 as the one that counted then
    reading = page_form.shown_verdicts(attempts, [], 'k0', 1)
    assert (reading.said, reading.said_at) == ('as then: the verdicts on reading 1 on', '2026-11-09T09:21:00+00:00')
    assert [(row.recall, row.standing_said) for row in reading.rows] == [('k0:judge/1:0', 'counted then')]
    # an older judgement recalled while a newer one counts on the same reading: the one that counted then beside it
    older = an_attempt('k1', shown=True, judgements=[
        a_judgement(recall='k1:judge/1:0', stored_at='2026-11-05T08:00:00+00:00'),
        a_judgement(version='judge/2', version_state='prototype', counts=True, recall='k1:judge/2:0',
                    stored_at='2026-11-06T08:00:00+00:00'),
        a_judgement(version='judge/3', recall='k1:judge/3:0', stored_at='2026-11-07T08:00:00+00:00')])
    then = page_form.shown_verdicts([older], [], 'k1', 1, older.judgements[1])
    assert [(row.recall, row.standing_said) for row in then.rows] == [('k1:judge/2:0', 'recalled')]
    assert [person.given_at for person in page_form.at_then(people, page_form.moment('2026-11-12T00:00:00+00:00'))] == [
        '2026-11-10T19:20:00+00:00', '2026-11-11T08:00:00+00:00']
    assert page_form.at_then(people, page_form.moment('2026-11-14T00:00:00+00:00'))[-1].given_at == '2026-11-12T11:49:00+00:00'


def test_a_judgement_s_findings_set_its_result_and_its_show_and_an_ok_with_minor_ones_stays_an_ok():
    major = an_attempt('k1', shown=True, judgements=[a_judgement(verdict='bad', outcome='issue', findings=[a_finding(), a_finding()])])
    minor = an_attempt('k2', shown=True, judgements=[a_judgement(findings=[a_finding('minor')])])
    clean = an_attempt('k3', shown=True, judgements=[a_judgement()])
    none = an_attempt('k4', shown=True)
    said = [(row.readings[0].result_state, row.readings[0].result_said) for row in
            (page_form.form_of([one], []) for one in (major, minor, clean, none))]
    assert said == [('issue', '2 issues'), ('ok', 'ok · 1 finding'), ('ok', 'ok'), ('none', 'no judge')]
    # decision 25: a judgement that found nothing shows nothing more than its reading: its show greyed, saying why
    assert page_form.form_of([clean], []).readings[0].verdicts[0].show_why_not == page_form.NOTHING_TO_SHOW
    assert page_form.form_of([major], []).readings[0].verdicts[0].show_why_not is None
    # a void finding is drawn beneath its block when recalled, so it changes what the page shows (178.a)
    voided = an_attempt('k5', shown=True, judgements=[a_judgement(findings=[a_finding(void=True)])])
    assert page_form.form_of([voided], []).readings[0].verdicts[0].show_why_not is None
    assert page_form.form_of([minor], []).readings[0].verdicts[0].verdict_said == 'ok · 1 finding: minor'


def test_a_reading_has_one_active_way_in_its_own_show_greyed_where_a_judge_beneath_it_shows_its_findings():
    struck = SimpleNamespace(kind='wrong_word', block='b12', severity='major', evidence=None, void=True)
    served = an_attempt('k1', number=3, shown=True, stored_at='2026-11-09T09:00:00+00:00', judgements=[a_judgement()])
    found = an_attempt('k0', stored_at='2026-11-02T09:00:00+00:00',
                       judgements=[a_judgement(recall='k0:judge/1:0', standing=False, findings=[struck])])
    clean = an_attempt('k2', number=2, stored_at='2026-11-05T09:00:00+00:00',
                       judgements=[a_judgement(recall='k2:judge/1:0', standing=False)])
    rows = {row.key: row for row in page_form.form_of([found, clean, served], []).readings}
    # the served one says so (41.a) and has no show of its own
    assert (rows['k1'].served_said, rows['k1'].recall, rows['k1'].show_why_not) == ('served', None, None)
    # a struck finding is drawn when recalled, so its judge's show is the way in and the reading's own is greyed (42.a)
    assert (rows['k0'].served_said, rows['k0'].show_why_not) == (None, 'show on judge/1: the same reading with its findings')
    assert rows['k0'].verdicts[0].show_why_not is None
    # a judge that found nothing: the reading's own show is the way in, the judge's greyed (decision 25), never both
    assert (rows['k2'].show_why_not, rows['k2'].verdicts[0].show_why_not) == (None, page_form.NOTHING_TO_SHOW)


def test_a_promoted_reading_stands_among_the_readings_saying_where_it_came_from():
    promoted = an_attempt('k2', prototype=True, shown=True, promoted=SimpleNamespace(reason='better', reason_short='better'))
    form = page_form.form_of([an_attempt('k1'), promoted], [])
    assert [one.key for one in form.readings] == ['k2', 'k1'] and form.lab == []
    assert (form.readings[0].promoted_said, form.readings[0].promotable) == ('promoted from the Lab: better', False)
    # a page no reader has read has no form
    assert page_form.form_of(None, []) is None


def test_a_promotion_goes_to_the_core_behind_the_verdicts_switch_and_its_refusal_is_said(monkeypatch):
    from backend.conversion.checks import human_verdict

    asked = []

    def promote_from_view(base, queue, work, pdf_page, reading_key, reason, note=None):
        asked.append((base.name, work, pdf_page, reading_key, reason, note))
        if reason == 'other' and not note:
            raise ValueError('the reason other needs a note')
        return {'reading_key': reading_key, 'export': queue.request()}

    monkeypatch.setattr(human_verdict, 'promote_from_view', promote_from_view)
    store = readings.knowledge_bases(public_only=True)['free']
    work, page = 'openstax_principles_of_finance_2e', 298
    if store.row(work, page) is None:
        return  # a clone without the free export
    off = TestClient(create_app(public_only=True), base_url=LOCAL)
    body = {'knowledge_base': 'free', 'work': work, 'pdf_page': page, 'reading_key': 'a' * 64, 'reason': 'better'}
    assert off.post('/api/verdict/promote', json=body).status_code == 403
    on = TestClient(create_app(public_only=True, allow_verdicts=True, export_run=lambda: None), base_url=LOCAL)
    answer = on.post('/api/verdict/promote', json=body)
    assert answer.status_code == 200 and answer.json()['reading_key'] == 'a' * 64
    refused = on.post('/api/verdict/promote', json={**body, 'reason': 'other'})
    assert (refused.status_code, refused.json()['detail']) == (422, 'the reason other needs a note')
    assert asked[0][1:] == ('openstax-finance-2e', 298, 'a' * 64, 'better', None) or asked[0][2:] == (298, 'a' * 64, 'better', None)
    assert verdicts.PromoteRequest.model_fields['reading_key'].metadata  # bounded, as every request's key
