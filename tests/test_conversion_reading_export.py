"""The export of page readings: one shape for both knowledge bases, the licensed one never where git tracks it."""

import dataclasses
import json

import pymupdf
import pytest

from backend.conversion.checks import check_run
from backend.conversion.reading import vision_batches
from backend.conversion.store import reading_export, reading_store, served_readings
from backend.ingestion.clean_sections import pdf_sections
from test_conversion_served_readings import page  # a minimal valid page reading, printed label "12"

KEY_READ, KEY_BLOCKED = 'a' * 64, 'b' * 64
BLOCKED_MESSAGE = 'Output blocked by content filtering policy'


def record(key: str, **fields) -> dict:
    return {'kind': 'reading', 'reading_key': key, 'work': 'w', 'file': 'w_book.pdf', 'pdf_page': 2, 'model': 'claude-sonnet-5-5',
            'form': 'markdown', 'attempt': 0, 'cost_usd': 0.01, 'image_size': [1688, 2184], 'result_type': 'succeeded',
            'result_class': 'ok', **fields}


@pytest.fixture
def licensed(tmp_path, monkeypatch):
    """A licensed knowledge base outside the repository: one page read, one the provider blocked."""
    store = reading_store.Store(tmp_path / 'vision')
    read = record(KEY_READ)
    blocked = record(KEY_BLOCKED, pdf_page=3, result_type='errored', result_class='errored', error_type='invalid_request_error',
                     error_message=BLOCKED_MESSAGE)
    store.save_reading(KEY_READ, read, page('::: {#b01 .paragraph bbox="10 50 900 120"}\nA sentence.\n:::'))
    store.save_reading(KEY_BLOCKED, blocked, None)
    monkeypatch.setattr(vision_batches, 'readings_of', lambda cells, store: [read, blocked])
    monkeypatch.setattr(vision_batches, 'current_class', lambda record, store: record['result_class'])
    monkeypatch.setattr(reading_export, 'legacy_fallback_pages', lambda: {})  # never this machine's own cache (#5's review)
    base = reading_export.KnowledgeBase('licensed', tmp_path / 'readings', tmp_path / 'pdfs', lambda: ('LIC-R01',), tracked=False)
    return base, store


def round_row(key: str, **fields) -> dict:
    return {'key': key, 'state': 'ok_unjudged', 'reasons': [], 'in_sample': False, 'suspicious': False, **fields}


def test_every_row_names_its_knowledge_base_first_with_the_printed_label_and_the_provider_s_message(licensed):
    base, store = licensed
    index = reading_export.export(base, store)
    read, blocked = index['pages']
    assert index['knowledge_base'] == 'licensed' and all(next(iter(row)) == 'knowledge_base' for row in index['pages'])
    assert {row['knowledge_base'] for row in index['pages']} == {'licensed'}
    assert read['printed_label'] == '12' and read['error_message'] is None and (base.export / read['text_file']).exists()
    assert blocked['printed_label'] is None and blocked['error_message'] == BLOCKED_MESSAGE and 'text_file' not in blocked
    assert blocked['route'] == served_readings.TEXT_LAYER_WHY['blocked']


def test_a_licensed_work_is_named_by_its_file_and_points_at_its_pdf(licensed):
    base, store = licensed
    (work,) = reading_export.export(base, store)['works']
    assert work == {'knowledge_base': 'licensed', 'work': 'w', 'source_id': 'w_book', 'title': 'w_book', 'file': 'w_book.pdf',
                    'pdf': (base.pdfs / 'w_book.pdf').as_posix(), 'outline': None}  # no PDF there: its outline is unknown


def a_book(path) -> None:
    """A three-page PDF with its own outline: a front page, a chapter, a section."""
    document = pymupdf.open()
    for text in ('Front matter', '1 Intro\nThe chapter begins here.', '1.1 Detail\nThe section goes on.'):
        document.new_page().insert_text((72, 72), text)
    document.set_toc([[1, '1 Intro', 2], [2, '1.1 Detail', 3]])
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)


def test_a_work_carries_its_own_outline_and_each_page_the_units_on_it_computed_once(licensed, monkeypatch):
    base, store = licensed
    a_book(base.pdfs / 'w_book.pdf')
    index = reading_export.export(base, store)
    (work,) = index['works']
    chapter, detail = work['outline']
    assert (chapter['title'], chapter['level'], chapter['parent'], chapter['first_page'], chapter['last_page']) == ('1 Intro', 1, None, 2, 3)
    assert (detail['title'], detail['parent'], detail['indexed']) == ('1.1 Detail', chapter['id'], True)
    read, blocked = index['pages']
    assert (read['unit'], read['units']) == (chapter['id'], [chapter['id']])
    assert (blocked['unit'], blocked['units']) == (detail['id'], [detail['id']])
    monkeypatch.setattr(pdf_sections, 'load_pdf_outline', lambda *args: pytest.fail('cut again although nothing changed'))
    assert reading_export.export(base, store)['works'][0]['outline'] == work['outline']


def test_a_pdf_replaced_in_place_is_quoted_anew_once_its_manifest_names_the_new_bytes(licensed, monkeypatch):
    # 25 Nov 2026: a work without a chosen reading is quoted from this cache only; a destamped copy kept the old text
    base, store = licensed
    monkeypatch.setitem(reading_export.BASES, 'licensed', base)
    monkeypatch.setattr(reading_export, 'open_store', lambda name: store)
    base.export.mkdir(parents=True)
    (base.export / 'index.json').write_text(json.dumps({'pages': []}), encoding='utf-8')
    pdf, manifest = base.pdfs / 'w_book.pdf', base.pdfs / '_manifest.json'

    def a_file(words: str) -> None:
        document = pymupdf.open()
        document.new_page().insert_text((72, 72), words)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        document.save(pdf)

    def named(sha256: str) -> None:
        manifest.write_text(json.dumps({'files': {'w_book.pdf': {'sha256': sha256}}}), encoding='utf-8')

    a_file('A stamped sentence of the book.')
    named('1' * 64)
    assert 'stamped' in reading_export.quoted_pages('licensed', 'w_book.pdf')[1]
    a_file('A clean sentence of the book.')
    assert 'stamped' in reading_export.quoted_pages('licensed', 'w_book.pdf')[1]  # the manifest still names the old bytes
    named('2' * 64)
    assert 'clean' in reading_export.quoted_pages('licensed', 'w_book.pdf')[1]
    assert json.loads(reading_export.quoted_path(store, 'w_book.pdf').read_text(encoding='utf-8'))['sha256'] == '2' * 64
    free = dataclasses.replace(base, pdfs=base.pdfs / 'raw')
    (free.pdfs).mkdir()
    (free.pdfs / '_manifest.json').write_text(json.dumps({'files': {'corpus/raw/w_book.pdf': {'sha256': '3' * 64}}}),
                                              encoding='utf-8')
    assert reading_export.manifest_sha256(free, 'w_book.pdf') == '3' * 64  # the free manifest keys a file by its path
    assert reading_export.manifest_sha256(free, 'other.pdf') is None


def test_only_the_tracked_export_carries_the_licences_readme(licensed, tmp_path):
    base, store = licensed
    reading_export.export(base, store)
    free = dataclasses.replace(base, name='free', export=tmp_path / 'free', tracked=True)
    reading_export.export(free, store)
    assert not (base.export / 'README.md').exists() and (free.export / 'README.md').exists()


def test_check_states_come_from_each_cell_s_own_report_never_from_an_older_joint_one(licensed):
    _, store = licensed
    store.write_report('check_report_LIC-R01.json', {'cells': ['LIC-R01'], 'pages': [round_row(KEY_READ)]})
    store.write_report('check_report_LIC-R01_LIC-R02.json', {'cells': ['LIC-R01', 'LIC-R02'], 'pages': [round_row(KEY_READ, state='issue')]})
    store.write_report('check_report_FREE-SM.json', {'cells': ['FREE-SM'], 'pages': [round_row(KEY_BLOCKED, state='issue')]})
    states = reading_export.check_states(store, ('LIC-R01', 'LIC-R02'))
    assert set(states) == {KEY_READ} and states[KEY_READ]['state'] == 'ok_unjudged'
    assert states[KEY_READ]['why_judged'].startswith('not judged')


def test_a_stop_a_person_decided_holds_whatever_the_report_s_sample_now_says(licensed):
    # 130.a: on 18 Nov a larger sample fell under the gate; the stop a person decided holds
    _, store = licensed
    store.write_report('check_report_LIC-R01.json', {'cells': ['LIC-R01'], 'works': {'w': {'stopped': False}},
                                                     'pages': [round_row(KEY_READ, state='ok', work='w')]})
    assert reading_export.check_states(store, ('LIC-R01',))[KEY_READ]['state'] == 'ok'
    assert reading_export.stopped_works(store, ('LIC-R01',)) == set()
    store.write_report(reading_export.DECIDED_STOPS, {'stops': {'LIC-R01': ['w'], 'LIC-R02': ['other']}})
    assert reading_export.check_states(store, ('LIC-R01',))[KEY_READ]['state'] == 'stopped'
    assert reading_export.stopped_works(store, ('LIC-R01',)) == {('LIC-R01', 'w')}  # another cell's stop stays its own


def test_a_sampled_page_carries_the_judge_s_verdict(licensed):
    _, store = licensed
    store.save_reading('c' * 64, {'kind': 'judge', 'model': check_run.JUDGE_MODEL, 'target_key': KEY_READ,
                                  'verdict': {'verdict': 'ok', 'outcome': 'ok', 'findings': []}}, None)
    store.write_report('check_report_LIC-R01.json', {'cells': ['LIC-R01'], 'pages': [round_row(KEY_READ, state='ok', in_sample=True)]})
    state = reading_export.check_states(store, ('LIC-R01',))[KEY_READ]
    assert state['judged'] and state['why_judged'] == 'in the random sample' and state['verdict']['outcome'] == 'ok'


def test_each_attempt_carries_its_own_check_in_brief_or_none_where_none_ran(licensed):
    # Line 2's request (5 Nov): a page's history shows each reading's check and verdict beside it.
    base, store = licensed
    store.save_reading('c' * 64, {'kind': 'judge', 'model': check_run.JUDGE_MODEL, 'target_key': KEY_READ,
                                  'verdict': {'verdict': 'ok', 'outcome': 'ok', 'findings': []}}, None)
    store.write_report('check_report_LIC-R01.json', {'cells': ['LIC-R01'], 'pages': [round_row(KEY_READ, state='ok', in_sample=True)]})
    read, blocked = reading_export.export(base, store)['pages']
    assert read['attempts'][0]['check'] == {'state': 'ok', 'verdict': 'ok', 'outcome': 'ok', 'reasons': []}
    assert read['attempts'][0]['format_errors'] is None  # it passed: nothing to explain (18 Nov)
    assert blocked['attempts'][0]['check'] is None


def test_an_untracked_knowledge_base_is_never_exported_where_git_tracks_it(licensed):
    base, store = licensed
    tracked = reading_store.REPO / 'docs' / 'licensed_readings_probe'
    with pytest.raises(reading_store.UnsafeRootError):
        reading_export.export(dataclasses.replace(base, export=tracked), store)
    assert not tracked.exists()


def test_the_licensed_export_lies_in_a_git_ignored_folder_and_the_free_one_where_the_chat_reads():
    export = reading_export.LICENSED.export  # ignored by /_*/, or outside the repository (285.a)
    assert not export.is_relative_to(reading_store.REPO) or export.relative_to(reading_store.REPO).parts[0].startswith('_')
    assert reading_store.refusal(reading_export.LICENSED.export.resolve()) is None
    assert reading_export.FREE.export == served_readings.EXPORT and reading_export.FREE.tracked and not reading_export.LICENSED.tracked


@pytest.mark.readings
def test_the_tracked_export_holds_free_rows_only():
    index = json.loads((served_readings.EXPORT / 'index.json').read_text(encoding='utf-8'))
    assert index['knowledge_base'] == 'free'
    assert {row['knowledge_base'] for row in index['pages']} == {'free'} == {work['knowledge_base'] for work in index['works']}


def test_the_command_exports_the_free_knowledge_base_unless_told_otherwise():
    parser = reading_export.build_parser()
    assert parser.parse_args([]).knowledge_base == 'free'
    assert parser.parse_args(['--knowledge-base', 'licensed']).knowledge_base == 'licensed'


def test_a_page_judged_for_a_block_stage_2_cannot_check_says_so(licensed):
    _, store = licensed
    store.write_report('check_report_LIC-R01.json', {'cells': ['LIC-R01'], 'pages': [round_row(KEY_READ, unverifiable=True)]})
    assert reading_export.check_states(store, ('LIC-R01',))[KEY_READ]['why_judged'] == 'a block stage 2 cannot check'


def test_each_finding_of_the_judge_names_the_class_of_its_block():
    from backend.conversion.contract.page_contract import parse
    from test_conversion_served_readings import page

    parsed = parse(page('::: {#b01 .paragraph bbox="10 10 200 50"}\nA line of text.\n:::',
                        '::: {#b02 .description of=b03 bbox="10 60 200 90"}\nA chart.\n:::'), 'markdown')
    state = {'state': 'issue', 'verdict': {'verdict': 'bad', 'findings': [{'block': 'b02'}, {'block': 'b09'}, {'block': None}]}}
    found = reading_export.with_block_classes(state, parsed)['verdict']['findings']
    assert [finding['block_class'] for finding in found] == ['description', None, None]
    assert state['verdict']['findings'][0] == {'block': 'b02'}  # the state it was given is not changed


def test_an_earlier_attempt_keeps_the_verdict_it_was_judged_with_where_no_report_holds_it():
    judged = [{'counts': True, 'verdict': 'bad', 'outcome': 'issue'}, {'counts': False, 'verdict': 'ok', 'outcome': 'ok'}]
    assert reading_export.attempt_check(None, judged) == {'state': 'issue', 'verdict': 'bad', 'outcome': 'issue', 'from': 'an earlier check'}
    assert reading_export.attempt_check(None, [{'counts': False, 'verdict': 'ok', 'outcome': 'ok'}]) is None


def test_a_chosen_reading_no_report_holds_takes_its_own_verdict_and_its_cell_s_stop():
    judged = [{'counts': True, 'verdict': 'ok', 'outcome': 'ok', 'findings': [], 'model': 'm', 'mode': 'batch', 'cost_usd': 0.01,
               'version': 'judge/1'}]
    record = {'cell': 'FREE-2ND-MISTRAL', 'work': 'a_book'}
    assert reading_export.earlier_state(record, judged, set())['state'] == 'ok'
    assert reading_export.earlier_state(record, judged, {('FREE-2ND-MISTRAL', 'a_book')})['state'] == 'stopped'
    assert reading_export.earlier_state(record, [], set()) is None


def test_stage_2_comes_in_full_and_a_plan_written_before_gives_its_kinds_and_reasons():
    full = {'suspicious': False, 'findings': [{'kind': 'low_recall', 'block': 'b03', 'detail': 'd', 'severity': 'suspect'}],
            'unverifiable': [{'block': 'b05', 'cls': 'figure', 'why': 'figure_text'}]}
    assert reading_export.stage2_of(full) == full
    old = reading_export.stage2_of({'suspicious': True, 'findings': ['low_recall'], 'unverifiable': ['figure_text']})
    assert old['findings'] == [{'kind': 'low_recall'}] and old['unverifiable'] == [{'why': 'figure_text'}]


def test_a_person_s_verdicts_say_whether_they_apply_to_the_reading_that_stands():
    given = {'reading_key': 'k0', 'block': 'b12', 'verdict': 'accept', 'reason': 'judge_misread_name', 'tag': 'name_list', 'note': None,
             'given_by': 'maintainer', 'given_at': 't'}
    shown = reading_export.human_of([given, {**given, 'reading_key': 'k1'}], 'k1')
    assert [item['applies'] for item in shown] == [False, True] and shown[0]['reason_text'].startswith('the judge took a name')


def test_every_attempt_says_in_words_what_it_was():
    # line 2's finding, 10 Nov: accounting p. 524's four readings showed as "attempt 2, attempt 0, attempt 1, attempt 0"
    assert reading_export.purpose_of(record('k', cell='FREE-SM')) == 'first reading'
    assert reading_export.purpose_of(record('k', cell='FREE-SM', attempt=vision_batches.RETRY_ATTEMPT)) == 'the one format retry'
    assert reading_export.purpose_of(record('k', cell='FREE-SM', attempt=vision_batches.HINTED_AFTER_PLAIN_RETRY)) == \
        'format retry with the errors as a hint, after a plain retry'
    assert reading_export.purpose_of(record('k', cell='FREE-SM', attempt=1, retry_of='x' * 64)) == \
        "read again with the judge's findings as a hint"
    assert reading_export.purpose_of(record('k', cell='FREE-2ND-TERRA', deviation='malformed after the one format retry')) == \
        'second reader'
    assert reading_export.purpose_of(record('k', cell='REPLAY-FREE', attempt=1)) == 'read again by a replay'


def test_a_page_s_category_comes_from_its_kind_and_its_exercise_sections():
    # decision 172.a (the operator, 10 Nov): an index, a contents page or an exercise page sorts apart from the content
    exercises = {'Multiple Choice', 'Exercise Set A'}
    assert reading_export.category_of('body', ['9.2 Discuss the Role of Accounting'], exercises) == 'content'
    assert reading_export.category_of('body', ['Multiple Choice'], exercises) == 'exercise'
    assert reading_export.category_of('body', ['Summary', 'Multiple Choice'], exercises) == 'content'  # a page that starts one
    assert reading_export.category_of('index', [], exercises) == 'index'
    assert reading_export.category_of('toc', ['Contents'], exercises) == 'contents'
    assert reading_export.category_of(None, ['Multiple Choice'], exercises) is None  # no reading named the kind


def test_a_person_s_accept_pins_its_reading_and_a_reset_discards_and_archives(tmp_path, monkeypatch):
    # decision 191.a: an accepted reading stays the page's reading; a reset discards the reading and archives the verdicts
    from backend.conversion.store import pipeline_db

    monkeypatch.setattr(pipeline_db, 'PATHS', {'free': tmp_path / 'p.sqlite', 'licensed': tmp_path / 'l.sqlite'})
    store = reading_store.Store(tmp_path / 'vision')
    for key, attempt in (('a' * 64, 0), ('c' * 64, 1)):
        store.save_reading(key, record(key, attempt=attempt), page('::: {#b01 .paragraph bbox="10 50 900 120"}\nA.\n:::'))
    base = reading_export.KnowledgeBase('free', tmp_path / 'readings', tmp_path, lambda: ('FREE-SM',), tracked=True)
    newer = record('c' * 64, attempt=1)
    pipeline_db.give_verdict('free', 'w_book.pdf', 2, 'a' * 64, 'accept', 'other', 'maintainer', note='checked')
    pinned = reading_export.with_people(base, store, [newer])[0]
    assert pinned['reading_key'] == 'a' * 64 and pinned['pinned_by_a_person']
    pipeline_db.give_reset('free', 'w_book.pdf', 2, 'a' * 64, 'read it again', 'maintainer')
    after = reading_export.with_people(base, store, [newer])[0]
    assert after['reading_key'] == 'c' * 64 and 'reset' not in after  # the accept is archived; the newer reading stands
    discarded = reading_export.with_people(base, store, [record('a' * 64)])[0]
    assert discarded['reset']['reason'] == 'read it again'
    verdicts = pipeline_db.human_verdicts('free')[('w_book.pdf', 2)]
    shown = reading_export.human_of(verdicts, 'a' * 64, pipeline_db.page_resets('free')[('w_book.pdf', 2)])
    assert shown[0]['archived'] and not shown[0]['applies']


def test_a_session_s_accept_neither_pins_its_reading_nor_is_shown_as_a_person_s(tmp_path, monkeypatch):
    # the operator, 18 Nov: "a person is always manual"; only a person's signature protects a page (3.a)
    from backend.conversion.store import pipeline_db

    monkeypatch.setattr(pipeline_db, 'PATHS', {'free': tmp_path / 'p.sqlite', 'licensed': tmp_path / 'l.sqlite'})
    store = reading_store.Store(tmp_path / 'vision')
    for key, attempt in (('a' * 64, 0), ('c' * 64, 1)):
        store.save_reading(key, record(key, attempt=attempt), page('::: {#b01 .paragraph bbox="10 50 900 120"}\nA.\n:::'))
    base = reading_export.KnowledgeBase('free', tmp_path / 'readings', tmp_path, lambda: ('FREE-SM',), tracked=True)
    session = pipeline_db.delegated_giver('claude-opus-5-5', '18 Nov')
    pipeline_db.give_verdict('free', 'w_book.pdf', 2, 'a' * 64, 'accept', 'other', session, note='a false alarm')
    newer = reading_export.with_people(base, store, [record('c' * 64, attempt=1)])[0]
    assert newer['reading_key'] == 'c' * 64 and 'pinned_by_a_person' not in newer
    shown = reading_export.human_of(pipeline_db.human_verdicts('free')[('w_book.pdf', 2)], 'a' * 64)
    assert shown[0]['applies'] and shown[0]['by_a_person'] is False


def test_a_reader_prototype_s_readings_are_listed_beside_a_page_never_chosen():
    # decision 210.a: page/2's readings stand in the history as a prototype's; the base's own cells choose, as before
    from backend.conversion.reading import reading_cells

    free = reading_export.BASES['free']
    assert reading_export.prototypes_beside(free) == tuple(sorted(reading_cells.READER_PROTOTYPE_CELLS))
    assert reading_export.prototypes_beside(reading_export.BASES['licensed']) == ()
    assert not set(reading_export.prototypes_beside(free)) & set(free.cells() + reading_export.cells_beside(free))
    assert reading_export.purpose_of({'cell': 'P2-WALK-SM'}) == 'a reader prototype (page/2), never served'
    assert reading_export.purpose_of({'cell': 'FREE-SM', 'attempt': 0}) == 'first reading'


def test_an_export_without_its_store_refuses_instead_of_emptying_the_export(tmp_path):
    # a clone holds the export but not the store; run there (by hand, or after a verdict from the view) it must write nothing
    import json as json_module

    base = reading_export.KnowledgeBase('free', tmp_path, tmp_path, lambda: (), tracked=True)
    assert reading_export.too_few_to_export(base, 0) is None  # no export yet: nothing to lose
    (tmp_path / 'index.json').write_text(json_module.dumps({'pages': [{}] * 1822}), encoding='utf-8')
    assert 'clone' in reading_export.too_few_to_export(base, 0)
    assert reading_export.too_few_to_export(base, 900) is not None and reading_export.too_few_to_export(base, 1822) is None


def test_a_page_only_a_session_read_joins_the_export_and_a_page_a_default_cell_holds_keeps_its_record(licensed, monkeypatch):
    # found 19 Nov: a scan read whole in a session stood in no export, neither its served pages nor the judge's issues on it
    base, store = licensed
    alone, beside = record('d' * 64, pdf_page=7, model='claude-opus-5-5'), record('e' * 64, model='claude-opus-5-5')
    monkeypatch.setattr(reading_export, 'cells_beside', lambda base: ('LIC-2ND-X', 'LIC-DIRECT-OPUS'))
    monkeypatch.setattr(vision_batches, 'readings_of',
                        lambda cells, store: [alone, beside] if cells == ('LIC-DIRECT-OPUS',) else [])
    out = reading_export.with_session_pages(base, store, [record(KEY_READ)], valid=lambda r: True)
    assert [(row['pdf_page'], row['reading_key']) for row in out] == [(2, KEY_READ), (7, 'd' * 64)]


def test_each_row_names_what_stands_where_its_reading_is_not_served(licensed, monkeypatch):
    # H2.a: the blocked page 3 has legacy Markdown, so its route says so; a served page has no fallback
    base, store = licensed
    monkeypatch.setattr(reading_export, 'legacy_fallback_pages', lambda: {'w_book.pdf': {3}})
    monkeypatch.setattr(reading_export, 'outlines_of', lambda base, store, works, rows: {row['file']: None for row in rows})
    rows = {row['pdf_page']: row for row in reading_export.export(base, store)['pages']}
    assert rows[3]['fallback'] == served_readings.LEGACY_ROUTE and rows[3]['route'].startswith('legacy markdown: ')
    assert rows[2]['fallback'] in (None, served_readings.TEXT_LAYER)
