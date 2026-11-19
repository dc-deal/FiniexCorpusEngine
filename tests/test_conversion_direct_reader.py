"""Direct reading (280.a): the hard cases a session may read, never a page a filter or a reader turned away."""
import pytest

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


def test_only_a_malformed_reading_is_a_hard_case_for_the_session(monkeypatch):
    monkeypatch.setattr(direct_reader.served_readings, 'text_layer_why', lambda r: r['why'])
    chosen, left = select([row(1, 'malformed'), row(2, 'no_page'), row(3, 'issue'), row(4, None), row(5, 'unread')])
    assert [(page['pdf_page'], page['why'], page['deviation']) for page in chosen] == [(1, 'malformed', DIRECT_DEVIATION)]
    assert left == {direct_reader.SOFT_REFUSAL: 1}


def test_a_page_the_session_read_stays_in_the_cell_whatever_came_of_it(monkeypatch):
    # 18 Nov: a served page that left the list took its check out of the next report, and the export would have served its
    # text layer; an issue would have lost its judge's finding the same way
    monkeypatch.setattr(direct_reader.served_readings, 'text_layer_why', lambda r: r['why'])
    read = [{'deviation': DIRECT_DEVIATION, 'class_now': 'ok'}]
    rows = [row(1, None, deviation=DIRECT_DEVIATION, attempts=read), row(2, 'issue', attempts=read), row(3, 'malformed', attempts=read),
            row(4, None, attempts=read)]
    chosen, left = select(rows, protected={('w.pdf', 4)})
    assert [(page['pdf_page'], page['why'], page['read']) for page in chosen] == [
        (1, 'served', True), (2, 'issue', True), (3, 'malformed', True), (4, 'served', True)]
    assert chosen[3]['protected'] and not left


def test_a_page_a_reader_once_found_no_page_on_is_a_soft_refusal_and_stays_out(monkeypatch):
    # 18 Nov: all five no_page answers of the licensed run declined the page in prose ("I can't write this page out ...")
    monkeypatch.setattr(direct_reader.served_readings, 'text_layer_why', lambda r: r['why'])
    chosen, left = select([row(1, 'malformed', attempts=[{'class_now': 'no_page'}, {'class_now': 'malformed'}]), row(2, 'malformed')])
    assert [page['pdf_page'] for page in chosen] == [2]
    assert left == {'a filter or a refusal in its history': 1}


def test_a_page_a_filter_or_a_reader_ever_turned_away_is_never_read_by_the_session(monkeypatch):
    # Claude through another door, around the provider's own safeguard: the filter rule, 280.a
    monkeypatch.setattr(direct_reader.served_readings, 'text_layer_why', lambda r: r['why'])
    rows = [row(1, 'malformed', attempts=[{'class_now': 'blocked'}]),
            row(2, 'malformed', attempts=[{'class_now': 'ok', 'deviation': 'the default reader declined the page'}]),
            row(3, 'malformed', error_type='invalid_request_error', class_when_collected='refused'),
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


def test_a_whole_unread_work_joins_the_cell_without_its_read_or_filtered_pages(tmp_path, monkeypatch):
    # the operator's experiment of 18 Nov night: a scanned book no batch round took, read whole in the session
    import pymupdf
    from types import SimpleNamespace

    document = pymupdf.open()
    for _ in range(4):
        document.new_page()  # no text: a scan as far as the text layer can tell
    document.save(tmp_path / 'scan.pdf')
    monkeypatch.setattr(direct_reader.data_paths, 'LICENSED_ARCHIVE', tmp_path)
    monkeypatch.setattr(direct_reader.reading_cells, 'may_send', lambda name: name != 'held.pdf')
    rows = [{'file': 'scan.pdf', 'pdf_page': 2, 'attempts': []},
            {'file': 'scan.pdf', 'pdf_page': 3, 'attempts': [{'class_now': 'blocked'}]}]
    pages = direct_reader.whole_work(SimpleNamespace(name='licensed'), 'scan.pdf', rows)
    assert [(page['pdf_page'], page['why'], page['deviation']) for page in pages] == [(1, 'unread', DIRECT_DEVIATION), (4, 'unread', DIRECT_DEVIATION)]
    assert pages[0]['work'] == 'scan' and pages[0]['work_card'].endswith(direct_reader.SCAN_NOTE)
    with pytest.raises(SystemExit):
        direct_reader.whole_work(SimpleNamespace(name='licensed'), 'held.pdf', [])


def test_a_page_outside_a_passed_sample_is_chosen_and_an_issue_or_an_unchecked_page_is_not(monkeypatch):
    # the operator's V1.b (19 Nov): a work read whole is judged by a sample, and the rest is served unjudged once it passed
    from types import SimpleNamespace

    from backend.conversion.checks import check_run
    from backend.conversion.store import pipeline_db

    records = [{'file': 'scan.pdf', 'pdf_page': page, 'reading_key': key, 'model': 'claude-opus-5-5', 'deviation': DIRECT_DEVIATION}
               for page, key in ((1, 'k1'), (2, 'k2'), (3, 'k3'), (4, 'k4'))]
    states = {'k1': {'state': 'ok'}, 'k2': {'state': 'ok_unjudged'}, 'k3': {'state': 'issue'}}
    chosen = []
    monkeypatch.setattr(direct_reader, 'open_store', lambda name: None)
    monkeypatch.setattr(direct_reader.vision_batches, 'readings_of', lambda cells, store: records)
    monkeypatch.setattr(check_run, 'latest_per_page', lambda readings: readings)
    monkeypatch.setattr(reading_export, 'check_states', lambda store, cells: states)
    monkeypatch.setattr(pipeline_db, 'chosen', lambda base: {})
    monkeypatch.setattr(pipeline_db, 'choose', lambda base, file, page, key, why: chosen.append(page))
    outcome = direct_reader.choose(SimpleNamespace(knowledge_base='licensed'))
    assert chosen == [1, 2]
    assert outcome == {'chosen': 2, 'not chosen: issue': 1, 'not chosen: not checked': 1}


def test_a_whole_work_keeps_the_pages_the_session_read_and_leaves_out_those_another_reader_read(tmp_path, monkeypatch):
    # found 19 Nov: the page list written anew after the night dropped every read page, and with them the work's readings
    # from the cell, so the next export would have lost the whole work
    import pymupdf
    from types import SimpleNamespace

    document = pymupdf.open()
    for _ in range(3):
        document.new_page()
    document.save(tmp_path / 'scan.pdf')
    monkeypatch.setattr(direct_reader.data_paths, 'LICENSED_ARCHIVE', tmp_path)
    monkeypatch.setattr(direct_reader.reading_cells, 'may_send', lambda name: True)
    rows = [{'file': 'scan.pdf', 'pdf_page': 1, 'attempts': [{'mode': 'session', 'class_now': 'ok'}]},
            {'file': 'scan.pdf', 'pdf_page': 2, 'attempts': [{'mode': 'batch', 'class_now': 'ok'}]}]
    pages = direct_reader.whole_work(SimpleNamespace(name='licensed'), 'scan.pdf', rows)
    assert [(page['pdf_page'], page['why']) for page in pages] == [(1, direct_reader.READ_IN_SESSION), (3, 'unread')]
