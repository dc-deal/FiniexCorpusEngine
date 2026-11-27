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
    assert (form.readings_count, form.lab_count, form.verdicts_count) == (1, 2, 3)
    assert form.shown_judgement == 'j1'
    reading = form.readings[0]
    # the row says its kind, its result in words, and folds open to its verdicts, a person's among them, in time order
    assert (reading.kind_said, reading.result_state, reading.result_said, reading.shown, reading.recall) == ('reading', 'ok', 'ok',
                                                                                                             True, None)
    assert [(one.kind_said, one.version_said, one.verdict_said) for one in reading.verdicts] == [
        ('judge', 'counts', 'ok'), ('person', 'verdict', 'accept · false alarm')]
    # the keys stand in the hover alone
    assert {'reading key', 'cell', "the reader's attempt"} <= {row.label for row in reading.hover}
    # the Lab: newest first; a test reading named as one, its class its result; a prototype's judge never counts there
    assert [(one.key, one.result_said, one.test_reading, one.promotable) for one in form.lab] == [
        ('k3', 'malformed', True, True), ('k2', 'ok', False, False)]
    assert form.lab[1].verdicts[0].version_said == 'prototype' and form.lab[0].recall == 'k3'
    # every verdict in time order, the standing one marked, a person's with the judgement it answered
    assert [(row.kind_said, row.standing_said, row.about, row.in_lab) for row in form.verdicts] == [
        ('judge', 'standing', 'the page', False), ('judge', 'history', 'the page', True), ('person', 'standing', 'the page', False)]
    assert (form.verdicts[2].answered.version, form.verdicts[2].reason, form.verdicts[2].who_said) == (
        'judge/1', 'false alarm', 'a person')


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
