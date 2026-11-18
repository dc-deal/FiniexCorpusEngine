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
