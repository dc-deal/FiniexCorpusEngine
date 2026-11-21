"""A person's verdict from the page view (decision 213.b): the one write route, off unless the app was started with
--allow-verdicts, local only, Origin-checked. The core's `from_view` is replaced here, and the export a verdict sets going
runs nothing, so no test writes the pipeline database or the export; the core's own tests cover `from_view`."""

import pytest
from fastapi.testclient import TestClient

from backend.diagnostics import readings, verdicts
from backend.diagnostics.app import create_app

FINANCE = 'openstax_principles_of_finance_2e'
LOCAL = {'host': '127.0.0.1:8001'}


def a_verdict(**changed) -> dict:
    return {'knowledge_base': 'free', 'work': FINANCE, 'pdf_page': 94, 'verdict': 'note', 'reason': 'reading_wrong',
            'block': 'b05', **changed}


@pytest.fixture
def given(monkeypatch):
    """The app with verdicts on, its exports running nothing, and the core's function replaced by one that records what it
    was asked and asks the queue, as the core's does."""
    asked = []

    def from_view(base, queue, work, pdf_page, verdict, reason, block=None, note=None, correction=None, judge_assessment=None):
        asked.append({'base': base.name, 'work': work, 'pdf_page': pdf_page, 'verdict': verdict, 'reason': reason, 'block': block,
                      'note': note, 'correction': correction, 'judge_assessment': judge_assessment})
        if reason == 'other' and not note:
            raise ValueError('the reason other needs a note')
        return {'verdict_id': 41, 'reading_key': 'k' * 64, 'file': 'f.pdf', 'route_before': 'vision reading', 'export': queue.request()}

    monkeypatch.setattr(verdicts.human_verdict, 'from_view', from_view)
    client = TestClient(create_app(public_only=True, allow_verdicts=True, export_run=lambda: None), base_url='http://127.0.0.1:8001')
    return client, asked


def test_without_the_switch_the_app_takes_no_verdict_and_says_why():
    client = TestClient(create_app(public_only=True), base_url='http://127.0.0.1:8001')
    form = client.get('/api/verdict').json()
    assert form['enabled'] is False and '--allow-verdicts' in form['why_not'] and form['exports'] == []
    refused = client.post('/api/verdict', json=a_verdict(), headers=LOCAL)
    assert refused.status_code == 403 and '--allow-verdicts' in refused.json()['detail']
    assert client.post('/api/verdict/preview', json={'text': '<table><tr><td>1</td></tr></table>'}, headers=LOCAL).status_code == 403


def test_the_form_offers_the_cores_lists_and_each_served_bases_export(given):
    client, _ = given
    form = client.get('/api/verdict').json()
    assert form['enabled'] is True and form['why_not'] is None
    assert [option['value'] for option in form['verdicts']] == ['accept', 'reject', 'note']
    assert {'value': 'other', 'label': 'another reason, said in the note'} in form['reasons']
    assert 'false_alarm' in [option['value'] for option in form['assessments']]
    # under --public-only the free base alone, its export idle
    assert [(status['knowledge_base'], status['running'], status['finished']) for status in form['exports']] == [('free', False, 0)]


@pytest.mark.readings
def test_a_verdict_goes_to_the_core_by_the_exports_work_and_sets_the_export_going(given):
    client, asked = given
    answer = client.post('/api/verdict', json=a_verdict(note='the lines cross about 2012', judge_assessment='right'), headers=LOCAL)
    assert answer.status_code == 200
    body = answer.json()
    assert body['verdict_id'] == 41 and body['route_before'] == 'vision reading' and body['export']['knowledge_base'] == 'free'
    # the view addresses a work by its id; the core takes the export's own name for it
    row = readings.Readings().row(FINANCE, 94)
    assert asked == [{'base': 'free', 'work': row['work'], 'pdf_page': 94, 'verdict': 'note', 'reason': 'reading_wrong', 'block': 'b05',
                      'note': 'the lines cross about 2012', 'correction': None, 'judge_assessment': 'right'}]
    assert row['work'] != FINANCE


@pytest.mark.readings
def test_an_input_the_core_refuses_is_said_in_its_words_and_a_page_not_served_is_not_found(given):
    client, asked = given
    refused = client.post('/api/verdict', json=a_verdict(reason='other'), headers=LOCAL)
    assert refused.status_code == 422 and refused.json()['detail'] == 'the reason other needs a note'
    assert client.post('/api/verdict', json=a_verdict(pdf_page=99999), headers=LOCAL).status_code == 404
    # under --public-only the licensed knowledge base is not served: no verdict reaches it
    assert client.post('/api/verdict', json=a_verdict(knowledge_base='licensed'), headers=LOCAL).status_code == 404
    assert len(asked) == 1  # only the one the core was asked about and refused


@pytest.mark.readings
def test_only_this_machines_own_pages_can_send_a_verdict(given):
    client, asked = given
    # a foreign name is refused by the app before the route (app.TRUSTED_HOSTS); the route's own check stays behind it
    assert client.post('/api/verdict', json=a_verdict(), headers={'host': 'example.org'}).status_code == 400
    assert client.post('/api/verdict', json=a_verdict(), headers={**LOCAL, 'origin': 'https://example.org'}).status_code == 403
    assert client.post('/api/verdict', json=a_verdict(), headers={**LOCAL, 'origin': 'http://127.0.0.1:8001'}).status_code == 200
    assert client.post('/api/verdict', json=a_verdict(), headers={**LOCAL, 'origin': 'http://localhost:5173'}).status_code == 200
    assert len(asked) == 2


def test_a_correction_is_previewed_as_the_table_it_would_be_and_text_as_none(given):
    client, _ = given
    table = client.post('/api/verdict/preview', json={'text': '<table><tr><th>Cash</th><td>150</td></tr></table>'}, headers=LOCAL).json()
    assert [[(cell['header'], ''.join(segment['content'] for segment in cell['segments'])) for cell in row] for row in table['rows']] == [
        [(True, 'Cash'), (False, '150')]]
    assert client.post('/api/verdict/preview', json={'text': 'the crossing around 2012'}, headers=LOCAL).json()['rows'] is None


@pytest.mark.readings
def test_a_block_carries_its_body_for_the_correction_to_start_from():
    page = readings.Readings().page(FINANCE, 94, 'Finance')
    b05 = next(block for block in page.reading.blocks if block.id == 'b05')
    assert b05.body and b05.body.strip() in page.raw


def test_the_form_says_whether_a_correction_can_be_proposed_and_why_not(given, monkeypatch):
    # W2.a, 21 Nov: no version of the role is active until a person makes one so after its gate
    client, _ = given
    monkeypatch.setattr(verdicts.correction_proposal, 'active_version', lambda: None)
    assert client.get('/api/verdict').json()['propose'] == {'available': False, 'why_not': 'no active correction version'}
    monkeypatch.setattr(verdicts.correction_proposal, 'active_version', lambda: 'correction/2')
    assert client.get('/api/verdict').json()['propose'] == {'available': True, 'why_not': None}
    off = TestClient(create_app(public_only=True), base_url='http://127.0.0.1:8001')
    assert off.get('/api/verdict').json()['propose']['available'] is False


def a_finding_block(client) -> tuple[int, dict]:
    """A free page of finance with a block the judge found something on, from the API, and that block."""
    for row in readings.Readings().rows_of(FINANCE):
        detail = client.get(f"/api/free/works/{FINANCE}/pages/{row['pdf_page']}").json()
        for block in (detail['reading'] or {}).get('blocks', []):
            if any(not finding['void'] for finding in block['findings']):
                return row['pdf_page'], block
    pytest.skip('no page of finance holds a block with a finding today')


@pytest.mark.readings
def test_a_proposal_is_asked_of_the_core_with_the_block_s_findings_and_never_recorded(given, monkeypatch):
    client, recorded = given
    pdf_page, block = a_finding_block(client)
    asked = []

    def propose(knowledge_base, reading_key, block_id, findings, **kwargs):
        asked.append((knowledge_base, block_id, findings))
        # invented: a proposal that keeps the block's words and adds a few
        return {'state': 'proposed', 'agrees_with_judge': 'partly', 'image_shows': 'an invented reading of the image',
                'correction': f"{block['body']} and an invented end", 'flags': ['large change'], 'cost_usd': 0.0123,
                'version': 'correction/2', 'model': 'an-invented-model',
                'prefill': {'verdict': 'reject', 'reason': 'reading_wrong', 'block': block_id, 'judge_assessment': 'right_for_a_wrong_reason',
                            'note': 'an invented reading of the image', 'correction': f"{block['body']} and an invented end",
                            'said': 'filled by an invented model; nothing is recorded until a person records it'}}

    monkeypatch.setattr(verdicts.correction_proposal, 'propose', propose)
    answer = client.post('/api/verdict/propose', json={'knowledge_base': 'free', 'work': FINANCE, 'pdf_page': pdf_page,
                                                       'block': block['id']}, headers=LOCAL)
    assert answer.status_code == 200
    proposal = answer.json()
    assert (proposal['state'], proposal['agrees_said'], proposal['flags'], proposal['cost_usd']) == (
        'proposed', 'partly agrees with the judge', ['large change'], 0.0123)
    # the judge's findings on the block, from the page's own data, void ones left out, never from the browser
    assert asked == [('free', block['id'], [{'kind': finding['kind'], 'severity': finding['severity'], 'evidence': finding['evidence']}
                                            for finding in block['findings'] if not finding['void']])]
    # the block's current text against the proposal, word by word: what it keeps, then what it adds
    assert proposal['diff'][-1] == {'kind': 'added', 'text': ' and an invented end'}
    assert ''.join(part['text'] for part in proposal['diff'] if part['kind'] != 'added') == (block['correction'] or {}).get('text', block['body'])
    # the whole verdict as the proposal fills it (F1.a), passed on as the core gave it
    assert proposal['prefill'] == {'verdict': 'reject', 'reason': 'reading_wrong', 'block': block['id'],
                                   'judge_assessment': 'right_for_a_wrong_reason', 'note': 'an invented reading of the image',
                                   'correction': f"{block['body']} and an invented end",
                                   'said': 'filled by an invented model; nothing is recorded until a person records it'}
    assert recorded == []  # nothing recorded by a proposal


@pytest.mark.readings
def test_a_proposal_the_core_refuses_says_its_reason_and_one_from_elsewhere_is_refused(given, monkeypatch):
    client, _ = given
    pdf_page, block = a_finding_block(client)

    def refuse(*args, **kwargs):
        raise verdicts.correction_proposal.Refused('no active correction version: a person makes one active after its gate')

    monkeypatch.setattr(verdicts.correction_proposal, 'propose', refuse)
    asked = {'knowledge_base': 'free', 'work': FINANCE, 'pdf_page': pdf_page, 'block': block['id']}
    refused = client.post('/api/verdict/propose', json=asked, headers=LOCAL)
    assert refused.status_code == 409 and refused.json()['detail'].startswith('no active correction version')
    assert client.post('/api/verdict/propose', json={**asked, 'block': 'b999'}, headers=LOCAL).status_code == 404
    elsewhere = client.post('/api/verdict/propose', json=asked, headers={**LOCAL, 'origin': 'https://elsewhere.example'})
    assert elsewhere.status_code == 403
    off = TestClient(create_app(public_only=True), base_url='http://127.0.0.1:8001')
    assert off.post('/api/verdict/propose', json=asked, headers=LOCAL).status_code == 403


def test_a_diff_keeps_what_both_hold_and_marks_what_is_taken_out_and_put_in():
    parts = verdicts.word_diff('The rate is 1.043 per year.', 'The rate is 1.034 per year.')
    assert [(part.kind, part.text) for part in parts] == [('same', 'The rate is '), ('removed', '1.043'), ('added', '1.034'),
                                                          ('same', ' per year.')]


def test_a_verdict_the_export_does_not_hold_yet_waits_and_one_it_holds_does_not(monkeypatch):
    # invented: two verdicts on one page in the pipeline database, the older one already in the export (E1.a)
    from types import SimpleNamespace

    new = {'given_at': '2026-11-21T16:02:00+00:00', 'verdict': 'accept', 'block': 'b05', 'given_by': 'maintainer'}
    old = {**new, 'given_at': '2026-11-20T10:00:00+00:00', 'verdict': 'note'}
    monkeypatch.setattr(verdicts.pipeline_db, 'human_verdicts', lambda name: {('a.pdf', 7): [old, new]})
    store = SimpleNamespace(rows=lambda: [{'file': 'a.pdf', 'pdf_page': 7, 'source_id': 'a_work', 'human': [old]}])
    waiting = verdicts.waiting_in('free', store)
    assert [(one.source_id, one.pdf_page, one.block, one.verdict, one.given_at, one.by_a_person) for one in waiting] == [
        ('a_work', 7, 'b05', 'accept', '2026-11-21T16:02:00+00:00', True)]
    # once the export holds it too, nothing waits
    store = SimpleNamespace(rows=lambda: [{'file': 'a.pdf', 'pdf_page': 7, 'source_id': 'a_work', 'human': [old, new]}])
    assert verdicts.waiting_in('free', store) == []


def test_an_export_says_since_when_it_runs_how_long_one_takes_and_what_waits_for_it(given, monkeypatch):
    client, _ = given
    status = client.get('/api/verdict').json()['exports'][0]
    assert {'started_at', 'expected_seconds', 'waiting'} <= set(status)
    assert (status['started_at'], status['expected_seconds']) == (None, None)  # idle: no start, no estimate asked


@pytest.mark.readings
def test_a_page_shows_its_verdicts_that_wait_for_the_export(monkeypatch):
    store = readings.knowledge_bases(public_only=True)['free']
    row = next(row for row in store.rows() if row.get('file') and row.get('source_id'))
    waiting = {'given_at': '2099-01-01T00:00:00+00:00', 'verdict': 'accept', 'block': 'b01', 'given_by': 'maintainer'}
    monkeypatch.setattr(verdicts.pipeline_db, 'human_verdicts', lambda name: {(row['file'], row['pdf_page']): [waiting]})
    client = TestClient(create_app(public_only=True), base_url='http://127.0.0.1:8001')
    page = client.get(f"/api/free/works/{row['source_id']}/pages/{row['pdf_page']}").json()
    assert [(one['verdict'], one['block'], one['given_at']) for one in page['waiting']] == [('accept', 'b01', '2099-01-01T00:00:00+00:00')]
