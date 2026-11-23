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


def test_choose_skips_every_reading_of_a_file_it_is_told_to_skip(monkeypatch):
    # line 1's 1.a (23 Nov): a file whose page images still carry a download mark keeps its readings unchosen
    from types import SimpleNamespace

    from backend.conversion.checks import check_run
    from backend.conversion.store import pipeline_db

    records = [{'file': name, 'pdf_page': 1, 'reading_key': key, 'model': 'claude-opus-5-5', 'deviation': DIRECT_DEVIATION}
               for name, key in (('marked.pdf', 'km'), ('clean.pdf', 'kc'))]
    chosen = []
    monkeypatch.setattr(direct_reader, 'open_store', lambda name: None)
    monkeypatch.setattr(direct_reader.vision_batches, 'readings_of', lambda cells, store: records)
    monkeypatch.setattr(check_run, 'latest_per_page', lambda readings: readings)
    monkeypatch.setattr(reading_export, 'check_states', lambda store, cells: {'km': {'state': 'ok'}, 'kc': {'state': 'ok'}})
    monkeypatch.setattr(pipeline_db, 'chosen', lambda base: {})
    monkeypatch.setattr(pipeline_db, 'choose', lambda base, file, page, key, why: chosen.append(file))
    outcome = direct_reader.choose(SimpleNamespace(knowledge_base='licensed', skip_file=['marked.pdf']))
    assert chosen == ['clean.pdf'] and outcome == {'chosen': 1, 'not chosen: skipped by name': 1}
    chosen.clear()
    direct_reader.choose(SimpleNamespace(knowledge_base='licensed'))  # without the option: as before
    assert chosen == ['marked.pdf', 'clean.pdf']


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


def test_a_page_the_filter_blocked_in_the_session_is_stored_as_blocked_and_never_read_again(tmp_path, monkeypatch):
    # 19 Nov night: an agent reading a licensed page was stopped by "Output blocked by content filtering policy" (280.a)
    import json as json_module
    from types import SimpleNamespace

    from backend.conversion.reading import vision_batches
    from backend.conversion.store import reading_store

    store = reading_store.Store(tmp_path / 'vision')
    folder = tmp_path / 'session' / 'w__p0041'
    folder.mkdir(parents=True)
    entry = {'reading_key': 'k' * 64, 'custom_id': 'c', 'cell': 'LIC-DIRECT-OPUS', 'page_id': 'w:p0041', 'file': 'w.pdf',
             'pdf_page': 41, 'work': 'w', 'mirror': 'licensed', 'model': 'claude-opus-5-5', 'mode': 'session',
             'deviation': DIRECT_DEVIATION}
    (folder / 'entry.json').write_text(json_module.dumps(entry), encoding='utf-8')
    (folder / direct_reader.BLOCKED_FILE).write_text(json_module.dumps(
        {'error_message': 'API Error: Output blocked by content filtering policy', 'request_id': 'req_1'}), encoding='utf-8')
    monkeypatch.setattr(direct_reader, 'session_folder', lambda base: tmp_path / 'session')
    monkeypatch.setattr(direct_reader, 'open_store', lambda mirror: store)
    assert direct_reader.store(SimpleNamespace(knowledge_base='licensed')) == {'blocked': 1}
    record = store.reading('k' * 64)
    assert vision_batches.is_block(record) and record['request_id'] == 'req_1' and record['cost_usd'] == 0.0
    assert direct_reader.touched_by_a_filter({'class_now': 'blocked', 'attempts': []})


def test_a_born_digital_work_gives_only_its_structure_pages_and_a_scan_every_page(tmp_path, monkeypatch):
    # the operator's N5.a (20 Nov): prose is served from a work's own text, and prose is what the filter blocks
    import pymupdf
    from types import SimpleNamespace

    document = pymupdf.open()
    prose = document.new_page()
    prose.insert_text((50, 80), 'A paragraph of plain prose that runs on for a good while, ' * 2, fontname='helv', fontsize=9)
    listing = document.new_page()
    listing.insert_text((50, 80), 'Some prose before the listing that explains what follows below.', fontname='helv', fontsize=9)
    for number, line in enumerate(('def test_sum():', '    assert sum([1, 2]) == 3', '    return None', 'test_sum()')):
        listing.insert_text((50, 120 + 14 * number), line, fontname='cour', fontsize=9)
    document.save(tmp_path / 'book.pdf')
    monkeypatch.setattr(direct_reader.data_paths, 'LICENSED_ARCHIVE', tmp_path)
    monkeypatch.setattr(direct_reader.reading_cells, 'may_send', lambda name: True)
    pages = direct_reader.whole_work(SimpleNamespace(name='licensed'), 'book.pdf', [])
    assert [page['pdf_page'] for page in pages] == [2] and 'code' in pages[0]['class_note']
    read = [{'file': 'book.pdf', 'pdf_page': 1, 'attempts': [{'mode': 'session', 'class_now': 'ok'}]}]
    assert [page['pdf_page'] for page in direct_reader.whole_work(SimpleNamespace(name='licensed'), 'book.pdf', read)] == [1, 2]


def a_scan(folder, pages: int, name: str = 'scan.pdf') -> None:
    import pymupdf

    document = pymupdf.open()
    for _ in range(pages):
        document.new_page()  # no text: a scan as far as the text layer can tell
    document.save(folder / name)


def test_a_page_list_adds_only_its_pages_each_checked_as_a_whole_work_s_page(tmp_path, monkeypatch):
    # 27.a (23 Nov): the weak pages of a scan whose OCR text layer is poor, not the whole work
    from types import SimpleNamespace

    a_scan(tmp_path, 5)
    monkeypatch.setattr(direct_reader.data_paths, 'LICENSED_ARCHIVE', tmp_path)
    monkeypatch.setattr(direct_reader.reading_cells, 'may_send', lambda name: name != 'held.pdf')
    rows = [{'file': 'scan.pdf', 'pdf_page': 2, 'attempts': [{'mode': 'batch', 'class_now': 'ok'}]},
            {'file': 'scan.pdf', 'pdf_page': 3, 'attempts': [{'class_now': 'blocked'}]},
            {'file': 'scan.pdf', 'pdf_page': 5, 'attempts': [{'mode': 'session', 'class_now': 'ok'}]}]
    base = SimpleNamespace(name='licensed')
    pages, left = direct_reader.named_pages(base, 'scan.pdf', {1, 2, 3, 4, 5}, rows, {('scan.pdf', 4)})
    assert [(page['pdf_page'], page['why']) for page in pages] == [(1, 'unread'), (5, direct_reader.READ_IN_SESSION)]
    assert left == {'read by another reader': 1, 'a filter or a refusal in its history': 1, 'a person checked it': 1}
    assert pages[0]['work'] == 'scan' and pages[0]['deviation'] == DIRECT_DEVIATION
    assert pages[0]['work_card'].endswith(direct_reader.SCAN_NOTE)


def test_a_page_list_naming_a_held_file_or_a_page_the_file_lacks_stops_before_anything_is_written(tmp_path, monkeypatch):
    from types import SimpleNamespace

    a_scan(tmp_path, 2)
    monkeypatch.setattr(direct_reader.data_paths, 'LICENSED_ARCHIVE', tmp_path)
    monkeypatch.setattr(direct_reader.reading_cells, 'may_send', lambda name: name != 'held.pdf')
    base = SimpleNamespace(name='licensed')
    with pytest.raises(SystemExit, match=r'no page \[9\]'):
        direct_reader.named_pages(base, 'scan.pdf', {1, 9}, [], set())
    with pytest.raises(SystemExit, match='held back'):
        direct_reader.named_pages(base, 'held.pdf', {1}, [], set())


def test_pages_takes_a_page_list_and_its_judge_share_keeps_it_on_later_runs_and_a_broken_list_writes_nothing(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    from backend.conversion.store import pipeline_db

    a_scan(tmp_path, 3)
    export, target = tmp_path / 'export', tmp_path / 'direct' / 'pages.json'
    export.mkdir()
    (export / 'index.json').write_text(json.dumps({'pages': []}), encoding='utf-8')
    monkeypatch.setattr(direct_reader.data_paths, 'LICENSED_ARCHIVE', tmp_path)
    monkeypatch.setattr(direct_reader.reading_cells, 'may_send', lambda name: True)
    monkeypatch.setattr(direct_reader.reading_cells, 'DIRECT_PAGES', {'licensed': target})
    monkeypatch.setitem(reading_export.BASES, 'licensed', SimpleNamespace(name='licensed', export=export, cells=lambda: []))
    monkeypatch.setattr(pipeline_db, 'protected_pages', lambda base: [])
    listed = tmp_path / 'weak.json'
    listed.write_text(json.dumps({'about': 'weak pages', 'pages': [{'file': 'scan.pdf', 'pdf_page': 3},
                                                                   {'file': 'scan.pdf', 'pdf_page': 1}]}), encoding='utf-8')
    direct_reader.pages(SimpleNamespace(knowledge_base='licensed', add_work=None, add_pages=str(listed), judge_share=0.6))
    kept = json.loads(target.read_text(encoding='utf-8'))
    assert [page['pdf_page'] for page in kept['pages']] == [1, 3] and kept['judge_shares'] == {'scan': 0.6}
    assert kept['added_pages'] == [{'file': 'scan.pdf', 'pdf_page': 1}, {'file': 'scan.pdf', 'pdf_page': 3}]
    assert kept['added_works'] == []  # the work is not taken whole
    direct_reader.pages(SimpleNamespace(knowledge_base='licensed', add_work=None, judge_share=None))  # a later run keeps them
    assert [page['pdf_page'] for page in json.loads(target.read_text(encoding='utf-8'))['pages']] == [1, 3]
    before = target.read_bytes()
    listed.write_text(json.dumps({'pages': [{'file': 'scan.pdf'}]}), encoding='utf-8')
    with pytest.raises(SystemExit, match='not a page list'):
        direct_reader.pages(SimpleNamespace(knowledge_base='licensed', add_work=None, add_pages=str(listed), judge_share=None))
    assert target.read_bytes() == before


def test_a_file_held_back_after_a_list_named_it_is_skipped_and_counted_and_a_new_list_naming_it_stops(tmp_path, monkeypatch):
    # line 1's 1.a (23 Nov): a reseller's stamp found in a scan after its pages were named must not block every later run
    import json
    from types import SimpleNamespace

    from backend.conversion.store import pipeline_db

    a_scan(tmp_path, 2, 'stamped.pdf')
    a_scan(tmp_path, 2, 'clean.pdf')
    export, target = tmp_path / 'export', tmp_path / 'direct' / 'pages.json'
    export.mkdir()
    (export / 'index.json').write_text(json.dumps({'pages': []}), encoding='utf-8')
    monkeypatch.setattr(direct_reader.data_paths, 'LICENSED_ARCHIVE', tmp_path)
    monkeypatch.setattr(direct_reader.reading_cells, 'DIRECT_PAGES', {'licensed': target})
    monkeypatch.setitem(reading_export.BASES, 'licensed', SimpleNamespace(name='licensed', export=export, cells=lambda: []))
    monkeypatch.setattr(pipeline_db, 'protected_pages', lambda base: [])
    listed = tmp_path / 'list.json'
    listed.write_text(json.dumps({'pages': [{'file': 'stamped.pdf', 'pdf_page': 1}, {'file': 'stamped.pdf', 'pdf_page': 2},
                                            {'file': 'clean.pdf', 'pdf_page': 1}]}), encoding='utf-8')
    monkeypatch.setattr(direct_reader.reading_cells, 'may_send', lambda name: True)
    direct_reader.pages(SimpleNamespace(knowledge_base='licensed', add_work=None, add_pages=str(listed), judge_share=None))
    monkeypatch.setattr(direct_reader.reading_cells, 'may_send', lambda name: name != 'stamped.pdf')  # the stamp is found
    outcome = direct_reader.pages(SimpleNamespace(knowledge_base='licensed', add_work=None, judge_share=None))
    kept = json.loads(target.read_text(encoding='utf-8'))
    assert [(page['file'], page['pdf_page']) for page in kept['pages']] == [('clean.pdf', 1)]
    assert outcome['left'] == {direct_reader.HELD_SINCE_NAMED: 2}
    assert {page['file'] for page in kept['added_pages']} == {'stamped.pdf', 'clean.pdf'}  # the plan's record stays whole
    with pytest.raises(SystemExit, match='held back'):
        direct_reader.pages(SimpleNamespace(knowledge_base='licensed', add_work=None, add_pages=str(listed), judge_share=None))


def test_the_works_of_a_page_list_are_judged_by_a_sample_as_works_read_whole_are(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    from backend.conversion.checks import check_run

    source = tmp_path / 'pages.json'
    source.write_text(json.dumps({'added_works': ['whole.pdf'], 'added_pages': [{'file': 'scan.pdf', 'pdf_page': 3}]}),
                      encoding='utf-8')
    monkeypatch.setattr(direct_reader.reading_cells, 'DIRECT_PAGES', {'licensed': source})
    monkeypatch.setattr(direct_reader.reading_cells, 'known_cells', lambda: {'LIC-DIRECT-OPUS': SimpleNamespace(page_source=source)})
    assert check_run.whole_works(['LIC-DIRECT-OPUS']) == {'whole', 'scan'}
