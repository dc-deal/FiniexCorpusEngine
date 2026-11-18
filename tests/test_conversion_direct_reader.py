"""Direct reading (280.a): the hard cases a session may read, never a page a filter or a reader turned away."""

from backend.constants.reading_constants import DIRECT_DEVIATION
from backend.conversion.reading import direct_reader
from backend.conversion.store import reading_export, served_readings
from backend.diagnostics import readings

LISTED_PAGE = {'expected_output_tokens': 1900, 'work_card': 'A book.', 'class_note': ''}


def row(page: int, why: str, **fields) -> dict:
    return {'file': 'w.pdf', 'pdf_page': page, 'why': why, 'attempts': [], **fields}


def select(rows, protected=frozenset(), may_send=lambda file_name: True):
    listed = {(r['file'], r['pdf_page']): {**LISTED_PAGE, 'file': r['file'], 'pdf_page': r['pdf_page'], 'work': 'w'}
              for r in rows}
    return direct_reader.select(rows, listed, set(protected), may_send)


def test_only_a_malformed_or_pageless_reading_is_a_hard_case_for_the_session(monkeypatch):
    monkeypatch.setattr(direct_reader.served_readings, 'text_layer_why', lambda r: r['why'])
    chosen, _ = select([row(1, 'malformed'), row(2, 'no_page'), row(3, 'issue'), row(4, None), row(5, 'unread')])
    assert [(page['pdf_page'], page['why'], page['deviation']) for page in chosen] == [
        (1, 'malformed', DIRECT_DEVIATION), (2, 'no_page', DIRECT_DEVIATION)]


def test_a_page_a_filter_or_a_reader_ever_turned_away_is_never_read_by_the_session(monkeypatch):
    # Claude through another door, around the provider's own safeguard: the filter rule, 280.a
    monkeypatch.setattr(direct_reader.served_readings, 'text_layer_why', lambda r: r['why'])
    rows = [row(1, 'malformed', attempts=[{'class_now': 'blocked'}]),
            row(2, 'malformed', attempts=[{'class_now': 'ok', 'deviation': 'the default reader declined the page'}]),
            row(3, 'no_page', error_type='invalid_request_error', class_when_collected='refused'),
            row(4, 'malformed')]
    chosen, left = select(rows)
    assert [page['pdf_page'] for page in chosen] == [4]
    assert left == {'a filter or a refusal in its history': 3}


def test_a_file_held_back_from_every_provider_and_a_page_a_person_checked_stay_out(monkeypatch):
    monkeypatch.setattr(direct_reader.served_readings, 'text_layer_why', lambda r: r['why'])
    rows = [row(1, 'malformed', file='stamped.pdf'), row(2, 'malformed'), row(3, 'malformed')]
    chosen, left = select(rows, protected={('w.pdf', 2)}, may_send=lambda file_name: file_name != 'stamped.pdf')
    assert [page['pdf_page'] for page in chosen] == [3]
    assert left == {'held back from every provider (send: false)': 1, 'a person checked it': 1}


def test_a_retry_is_a_new_attempt_with_its_own_key():
    first = direct_reader.reading_spec(image_sha='i', model='m', system_sha='s', user_sha='u', max_tokens=16000)
    retry = direct_reader.reading_spec(image_sha='i', model='m', system_sha='s', user_sha='u2', max_tokens=16000, attempt=1)
    assert first['mode'] == 'session' and retry['params']['attempt'] == 1 and first != retry


def test_a_direct_reading_is_served_under_its_own_route_and_the_view_names_it():
    served = {'model': 'claude-opus-5-5', 'contract': 'page/1', 'validator': 'page/1.3', 'deviation': DIRECT_DEVIATION,
              'text_file': 'x.md', 'class_now': 'ok', 'check': {'state': 'ok'}}
    route = served_readings.route_of(served)
    assert route.startswith('vision reading, direct reading (claude-opus-5-5') and route.endswith(DIRECT_DEVIATION)
    assert readings.route_parts(route) == ('direct reading', 'claude-opus-5-5, page/1, validator page/1.3', DIRECT_DEVIATION)


def test_a_direct_reading_and_its_retry_say_what_they_were_among_the_page_s_attempts():
    assert reading_export.purpose_of({'deviation': DIRECT_DEVIATION, 'attempt': 0}) == 'direct reading in a Claude Code session'
    assert reading_export.purpose_of({'deviation': DIRECT_DEVIATION, 'attempt': 1}).endswith('a format retry')
    assert reading_export.purpose_of({'deviation': 'anthropic blocked the page (content filter)'}) == 'second reader'


def test_a_session_reading_costs_none_not_zero_while_its_record_keeps_a_number_for_the_ledger():
    # 0.0 would claim it was free; the plan pays it, and no API measures it (the operator and line 2, 18 Nov)
    assert reading_export.cost_of({'mode': 'session', 'cost_usd': 0.0}) is None
    assert reading_export.cost_of({'mode': 'batch', 'cost_usd': 0.0115}) == 0.0115
