"""The exported page readings, shaped for the views: read-only, from tracked data, the model's text never as markup."""

import copy
import hashlib
import json
import os
import shutil

import pytest

from backend.conversion.store import served_readings
from backend.diagnostics import readings

KELLY = 'carta_conversano_kelly_criterion_2020'  # a free paper of 15 pages whose PDF is tracked
store = readings.Readings()


def kelly_rows():
    return store.rows_of(KELLY)


def a_blocked_row() -> dict:
    """A Kelly page as the export writes one the provider blocked, invented from a page it read: the second reader fills the
    blocked pages one by one (18 Nov: p. 360 of accounting), and a test that needs one must not wait for one to remain."""
    row = copy.deepcopy(next(row for row in kelly_rows() if row.get('text_file') and row['check']['state'] == 'ok'))
    row.update(text_file=None, text_sha256=None, route=served_readings.TEXT_LAYER_WHY['blocked'], route_level='fallback',
               class_when_collected='errored', class_now='errored', error_type='invalid_request_error',
               error_message='Output blocked by content filtering policy', attempts=[], chosen=None,
               check={'state': 'blocked', 'reasons': ['errored'], 'judged': False, 'verdict': None, 'judge': None,
                      'why_judged': 'not judged: the reading failed'})
    return row


def a_live_row(matches, what: str) -> dict:
    """A free page in the state a test needs, from the export as it stands; the test skips where none is left, as the
    corpus improves (18 Nov: the free export's last blocked and malformed pages are being read again)."""
    found = next((row for row in store.rows() if matches(row)), None)
    if found is None:
        pytest.skip(f'the free export holds no {what} today')
    return found


def a_corpus(tmp_path, rows, knowledge_base='free', **work_fields):
    """An export of the given rows in a folder of its own, with Kelly's work entry (and any further fields of it, such as an
    outline) and the rows' texts copied beside them. Its repository root is `tmp_path`, where no PDF lies: that stands for
    a PDF that is not on this machine. The real work's outline is never copied: a test gives the one it means, so it holds
    whatever the tracked export carries today."""
    export = tmp_path / 'readings'
    export.mkdir(parents=True)
    for row in rows:
        if row.get('text_file'):
            (export / row['text_file']).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(readings.FREE_EXPORT / row['text_file'], export / row['text_file'])
    work = {name: value for name, value in copy.deepcopy(store.work(KELLY)).items() if name != 'outline'}
    work.update(knowledge_base=knowledge_base, **work_fields)
    (export / 'index.json').write_text(json.dumps({'knowledge_base': knowledge_base, 'works': [work], 'pages': rows}),
                                       encoding='utf-8')
    return readings.Readings(export, root=tmp_path)


@pytest.mark.readings
def test_every_row_and_work_of_the_free_export_names_the_free_knowledge_base():
    assert {row['knowledge_base'] for row in store.rows()} == {'free'}
    assert {work['knowledge_base'] for work in store.works()} == {'free'}


@pytest.mark.readings
def test_a_work_summary_counts_every_page_once():
    summary = store.summary(KELLY)
    assert summary.pages == len(kelly_rows())
    assert sum(count.count for count in summary.states) == summary.pages
    assert sum(count.count for count in summary.routes) == summary.pages


def test_a_work_without_page_readings_has_no_summary():
    assert store.summary('wikipedia_trading_set') is None


def test_pages_come_in_pdf_page_order_with_their_summary():
    pages = store.pages('free', KELLY, 'Kelly')
    numbers = [page.pdf_page for page in pages.pages]
    assert numbers == sorted(numbers) and len(numbers) == len(kelly_rows())
    assert pages.summary == store.summary(KELLY)
    assert pages.knowledge_base == 'free'


@pytest.mark.readings
def test_a_works_page_list_names_the_knowledge_base_its_export_entry_gives(tmp_path):
    licensed = a_corpus(tmp_path, [copy.deepcopy(kelly_rows()[0])], knowledge_base='licensed')
    # the export's own word wins over the address it was asked under
    assert licensed.pages('free', KELLY, 'Kelly').knowledge_base == 'licensed'
    # a catalog work no export lists, not read page by page, keeps the one it was asked under
    assert store.pages('free', 'wikipedia_trading_set', 'Wikipedia').knowledge_base == 'free'


@pytest.mark.readings
def test_a_page_served_from_its_text_layer_is_marked_by_the_cores_own_routes(tmp_path):
    from backend.conversion.store import served_readings

    for page in store.pages('free', KELLY, 'Kelly').pages:
        assert page.from_fallback == (page.route in served_readings.TEXT_LAYER_WHY.values())
        # a page to look at is served from its text layer; a page that is ok, judged or not, from its reading
        assert page.from_fallback == (page.check.state in readings.LISTED_AS_ISSUE)
    # a page the reader declined has no sentence of the provider's, and is still listed as served from its text layer;
    # invented, since the free export may hold no such page (a second reader may stand for it)
    row = copy.deepcopy(kelly_rows()[0])
    row.update(class_now='refused', route=served_readings.TEXT_LAYER_WHY['refused'], error_message=None,
               check={**(row.get('check') or {}), 'state': 'blocked'})
    listed = readings.issues({'free': a_corpus(tmp_path, [row])}).rows
    assert [(page.from_fallback, page.error_message) for page in listed] == [(True, None)]


def test_a_route_is_parted_where_the_cores_own_route_strings_part_it():
    from backend.conversion.store import served_readings

    reading = {'text_file': 'p1.md', 'class_now': 'ok', 'check': {'state': 'ok'}, 'model': 'claude-sonnet-5-5',
               'contract': 'page/1', 'validator': 'page/1.2'}
    checked = served_readings.route_of(reading)
    second = served_readings.route_of({**reading, 'deviation': 'the default model declined the page'})
    void = served_readings.route_of({**reading, 'check': {'state': 'ok', 'verdict': {'void': 1}}})
    assert readings.route_parts(checked) == ('vision reading', 'claude-sonnet-5-5, page/1, validator page/1.2', None)
    assert readings.route_parts(second) == ('second reader', 'claude-sonnet-5-5, page/1, validator page/1.2',
                                            'the default model declined the page')
    assert readings.route_parts(void)[2] == "the judge's findings contradict their own evidence"
    assert readings.route_parts(served_readings.TEXT_LAYER_WHY['refused']) == ('text layer', None, 'the reader declined the page')
    # a licensed work's legacy Markdown in the reading's place names itself as the source (H2.a)
    assert readings.route_parts(served_readings.LEGACY_WHY['refused']) == ('legacy markdown', None, 'the reader declined the page')


@pytest.mark.readings
def test_a_works_routes_stand_once_each_checked_first_and_fallback_last_with_the_cores_legend(tmp_path):
    from backend.conversion.store import served_readings

    pages = store.pages('free', KELLY, 'Kelly')
    assert sum(route.pages for route in pages.routes) == len(pages.pages)
    assert {route.route for route in pages.routes} == {page.route for page in pages.pages}
    assert [(one.level, one.says) for one in pages.route_levels] == list(served_readings.ROUTE_LEVELS.items())
    # each level's pages are its routes' pages, every page in one level where the export gives one
    assert sum(one.pages for one in pages.route_levels) == sum(route.pages for route in pages.routes if route.level)
    # every page carries its route's level and why, as its route's row in the table has them
    by_route = {route.route: route for route in pages.routes}
    assert all((page.route_level, page.route_why) == (by_route[page.route].level, by_route[page.route].why) for page in pages.pages)
    # invented levels over three pages: a fallback of two pages still stands after a checked route of one
    rows = [copy.deepcopy(row) for row in kelly_rows()[:3]]
    for row, (route, level) in zip(rows, [(served_readings.TEXT_LAYER_WHY['blocked'], 'fallback'),
                                          (served_readings.TEXT_LAYER_WHY['blocked'], 'fallback'),
                                          ('vision reading (m, page/1, validator page/1.2)', 'checked')]):
        row.update(route=route, route_level=level)
    invented = a_corpus(tmp_path, rows).pages('free', KELLY, 'Kelly')
    assert [(route.level, route.source, route.pages) for route in invented.routes] == [('checked', 'vision reading', 1), ('fallback', 'text layer', 2)]
    assert [(one.level, one.pages) for one in invented.route_levels] == [('checked', 1), ('noted', 0), ('fallback', 2)]


def a_unit(unit_id, parent, first, last, indexed=True):
    return {'id': unit_id, 'level': 1 if parent is None else 2, 'title': f'unit {unit_id}', 'parent': parent,
            'first_page': first, 'last_page': last, 'indexed': indexed}


@pytest.mark.readings
def test_a_unit_counts_every_page_of_its_subtree_once_and_the_pages_outside_stand_apart(tmp_path):
    rows = [copy.deepcopy(row) for row in kelly_rows()[:5]]  # PDF pages 1 to 5; 2 and 3 were blocked by the provider
    # an invented order: page 1 lies outside, page 3 lies in u2 and in its child u3, back matter u4 at the end
    for row, units in zip(rows, ([], ['u1'], ['u2', 'u3'], ['u3'], ['u4'])):
        row['units'] = units
    outline = [a_unit('u1', None, 2, 2), a_unit('u2', None, 3, 4), a_unit('u3', 'u2', 3, 4), a_unit('u4', None, 5, 5, False)]
    pages = a_corpus(tmp_path, rows, outline=outline).pages('free', KELLY, 'Kelly')
    units = {unit.id: unit for unit in pages.outline}
    assert [(unit_id, units[unit_id].pages) for unit_id in ('u1', 'u2', 'u3', 'u4')] == [('u1', 1), ('u2', 2), ('u3', 2), ('u4', 1)]
    # u2 holds page 3 itself and pages 3 and 4 through u3: page 3 once
    assert [(count.value, count.count) for count in units['u2'].states] == [('ok', 1), ('blocked', 1)]
    # its own pages, its block's caption (161.a): u2's text lies on page 3 alone; u3's on pages 3 and 4
    assert [(unit_id, units[unit_id].own_pages) for unit_id in ('u1', 'u2', 'u3', 'u4')] == [('u1', 1), ('u2', 1), ('u3', 2), ('u4', 1)]
    assert units['u4'].indexed is False and units['u3'].parent == 'u2'
    assert pages.outside_outline.pages == 1
    assert [page.units for page in pages.pages] == [[], ['u1'], ['u2', 'u3'], ['u3'], ['u4']]


@pytest.mark.readings
def test_an_outline_is_unknown_where_the_export_has_none_and_empty_where_the_pdf_has_no_bookmarks(tmp_path):
    row = copy.deepcopy(kelly_rows()[0])
    row.pop('units', None)
    unexported = a_corpus(tmp_path / 'a', [row]).pages('free', KELLY, 'Kelly')
    assert unexported.outline is None and unexported.outside_outline is None and unexported.pages[0].units is None
    assert a_corpus(tmp_path / 'b', [row], outline=None).pages('free', KELLY, 'Kelly').outline is None
    assert a_corpus(tmp_path / 'c', [row], outline=[]).pages('free', KELLY, 'Kelly').outline == []


@pytest.mark.readings
def test_an_issue_is_listed_and_states_stand_in_one_order(tmp_path):
    rows = [copy.deepcopy(row) for row in kelly_rows()[:4]]
    rows[0]['check'] = {**rows[0]['check'], 'state': 'issue'}  # the core's word since 97.a
    rows[1]['check'] = {**rows[1]['check'], 'state': 'blocked'}
    rows[2]['check'] = {**rows[2]['check'], 'state': 'ok'}
    rows[3]['check'] = None
    corpus = a_corpus(tmp_path, rows)
    listed = readings.issues({'free': corpus}).rows
    assert sorted(row.check.state for row in listed) == ['blocked', 'issue']
    assert [count.value for count in corpus.summary(KELLY).states] == ['ok', 'not_yet_checked', 'blocked', 'issue']
    # each listed page carries its route's level and why, as a work's page row has them (159.a)
    assert all((row.route_level, row.route_why) == (source.get('route_level'), readings.route_parts(source['route'])[2])
               for row, source in zip(sorted(listed, key=lambda one: one.pdf_page), sorted(rows[:2], key=lambda one: one['pdf_page'])))


@pytest.mark.readings
def test_a_page_no_check_has_reached_is_said_not_yet_checked_and_is_no_issue(tmp_path):
    rows = [copy.deepcopy(row) for row in kelly_rows()[:2]]
    rows[0]['check'] = None  # read, but not yet reached by a check run, as in a licensed round before its check
    corpus = a_corpus(tmp_path, rows)
    page = corpus.page(KELLY, rows[0]['pdf_page'], 'Kelly')
    assert (page.check.state, page.check.judged, page.check.verdict) == ('not_yet_checked', False, None)
    assert 'not checked yet' in page.check.why_judged
    assert page.said is None  # its state says all there is
    assert 'not_yet_checked' in [count.value for count in corpus.summary(KELLY).states]
    assert all(row.check.state != 'not_yet_checked' for row in readings.issues({'free': corpus}).rows)


@pytest.mark.readings
def test_a_reason_given_per_finding_is_counted_once():
    row = copy.deepcopy(kelly_rows()[0])
    row['check']['reasons'] = ['judge: bad', 'omission', 'omission', 'omission']
    check = readings.check_of(row)
    assert [(reason.value, reason.count) for reason in check.reasons] == [('judge: bad', 1), ('omission', 3)]


@pytest.mark.readings
def test_a_formula_arrives_as_latex_and_a_table_as_cells():
    formulas = [block for block in store.page(KELLY, 4, 'Kelly').reading.blocks if block.block_class == 'formula']
    tables = [block for block in store.page(KELLY, 7, 'Kelly').reading.blocks if block.block_class == 'table']
    assert formulas and all(block.latex and block.segments is None for block in formulas)
    assert tables and all(block.rows and block.rows[0][0].segments for block in tables)


@pytest.mark.readings
def test_the_model_text_reaches_the_view_only_as_segments_cells_latex_code_or_plain_text():
    for block in store.page(KELLY, 7, 'Kelly').reading.blocks:
        # `body` is the block's text as written, a table's HTML too: the verdict dialog's correction starts from it, and the
        # view shows it only as a text field's value, never as markup (213.b; the dialog's unit test holds that)
        # `correction`: a person's correction that stands for the block (229.a), drawn as text or as cells, never as markup
        # `served`: the block as the search quotes it (21 Nov), drawn as text in the page view's "as served" mode, never as markup
        assert set(block.model_dump()) == {'id', 'block_class', 'group', 'content', 'attrs', 'bbox', 'segments', 'latex',
                                           'rows', 'code', 'text', 'findings', 'people', 'decorative', 'body', 'correction', 'served'}
        for segment in block.segments or []:
            assert segment.kind in ('text', 'math', 'code')


@pytest.mark.readings
def test_a_description_is_marked_derived_by_the_contract():
    blocks = [block for page in (1, 4, 7) for block in store.page(KELLY, page, 'Kelly').reading.blocks]
    assert {block.content for block in blocks if block.block_class == 'description'} <= {'D'}


@pytest.mark.readings
def test_a_finding_stands_with_the_block_it_names_and_the_rest_with_the_page(tmp_path):
    row = copy.deepcopy(store.row(KELLY, 1))
    first = store.page(KELLY, 1, 'Kelly').reading.blocks[0].id
    row['check']['verdict'] = {'verdict': 'bad', 'outcome': 'issue', 'findings': [
        {'kind': 'wrong_value', 'block': first, 'severity': 'major', 'evidence': 'a figure misread'},
        {'kind': 'omission', 'block': None, 'severity': 'minor', 'evidence': None},
        {'kind': 'structure', 'block': 'b99', 'severity': 'minor', 'evidence': None}]}
    page = a_corpus(tmp_path, [row]).page(KELLY, 1, 'Kelly')
    named = {block.id: [finding.kind for finding in block.findings] for block in page.reading.blocks}
    assert named.pop(first) == ['wrong_value']
    assert not any(named.values())
    # one names no block, one a block the reading does not have: both belong to the page
    assert [finding.kind for finding in page.page_findings] == ['omission', 'structure']


@pytest.mark.readings
def test_a_page_without_a_reading_keeps_all_its_findings_on_the_page(tmp_path):
    blocked = a_blocked_row()
    blocked['check']['verdict'] = {'verdict': 'bad', 'outcome': 'issue', 'findings': [
        {'kind': 'omission', 'block': 'b01', 'severity': 'major', 'evidence': None}]}
    page = a_corpus(tmp_path, [blocked]).page(KELLY, blocked['pdf_page'], 'Kelly')
    assert page.reading is None and [finding.block for finding in page.page_findings] == ['b01']


@pytest.mark.readings
def test_a_page_carries_its_printed_label_and_the_providers_sentence(tmp_path):
    blocked = a_blocked_row()
    page = a_corpus(tmp_path, [blocked]).page(KELLY, blocked['pdf_page'], 'Kelly')
    assert page.trace.error_message and page.trace.error_message == blocked['error_message']
    assert store.page(KELLY, 7, 'Kelly').printed_label == store.row(KELLY, 7)['printed_label']


@pytest.mark.corpus
@pytest.mark.readings
def test_the_original_is_byte_for_byte_the_image_the_reader_saw():
    image, png = store.image(KELLY, 1)
    row = store.row(KELLY, 1)
    assert image.available and image.same_as_read
    assert hashlib.sha256(png).hexdigest() == row['image_sha256']
    assert [image.width, image.height] == row['image_size']


@pytest.mark.readings
def test_a_page_lists_every_reading_bought_for_it_and_why_its_own_was_chosen(tmp_path):
    row = copy.deepcopy(store.row(KELLY, 1))
    first = {'reading_key': 'aaaa1111', 'model': 'claude-sonnet-5-5', 'mode': 'batch', 'attempt': 0,
             'class_now': 'malformed', 'stored_at': '2026-11-02T14:48:03+00:00', 'deviation': None}
    second = {**first, 'reading_key': row['reading_key'], 'mode': 'standard', 'attempt': 1, 'class_now': 'ok',
              'stored_at': '2026-11-04T09:12:00+00:00'}
    row.update(attempts=[first, second], chosen={'why': 're-read after the format retry', 'run_id': 7,
                                                 'chosen_at': '2026-11-04T09:13:00+00:00'})
    page = a_corpus(tmp_path, [row]).page(KELLY, 1, 'Kelly')
    assert [(attempt.attempt, attempt.class_now, attempt.shown) for attempt in page.attempts] == [(0, 'malformed', False),
                                                                                                  (1, 'ok', True)]
    assert (page.chosen.why, page.chosen.run_id) == ('re-read after the format retry', '7')


@pytest.mark.readings
def test_a_pages_readings_are_numbered_across_readers_each_in_the_cores_words_and_a_re_read_names_its_reading(tmp_path):
    row = copy.deepcopy(store.row(KELLY, 1))
    first = {'reading_key': 'aaaa1111', 'model': 'claude-sonnet-5-5', 'mode': 'batch', 'attempt': 0, 'class_now': 'ok',
             'stored_at': '2026-11-02T14:48:03+00:00', 'deviation': None, 'purpose': 'first reading', 'cell': 'FREE-SM',
             'retry_of': None}
    other = {**first, 'reading_key': 'bbbb2222', 'model': 'openai/gpt-6.1-terra', 'purpose': 'second reader',
             'deviation': 'anthropic blocked the page (content filter)', 'stored_at': '2026-11-05T08:44:33+00:00'}
    again = {**first, 'reading_key': row['reading_key'], 'attempt': 1, 'retry_of': 'aaaa1111',
             'purpose': "read again with the judge's findings as a hint", 'stored_at': '2026-11-09T09:21:52+00:00'}
    row['attempts'] = [first, other, again]
    attempts = a_corpus(tmp_path, [row]).page(KELLY, 1, 'Kelly').attempts
    assert [(one.number, one.attempt, one.purpose, one.retry_of_number) for one in attempts] == [
        (1, 0, 'first reading', None), (2, 0, 'second reader', None), (3, 1, "read again with the judge's findings as a hint", 1)]


def test_every_reading_of_the_free_export_is_numbered_and_says_what_it_was():
    for row in store.rows():
        attempts = readings.attempts_of(row)
        assert [one.number for one in attempts] == list(range(1, len(attempts) + 1))
        assert all(one.purpose for one in attempts), (row['source_id'], row['pdf_page'])


def test_the_format_checks_faults_are_said_by_their_blocks():
    assert readings.faults_said(['block b12 (line 57): empty body (use status=unreadable)',
                                 'block b15 (line 67): empty body (use status=unreadable)']) == '2 blocks left empty (b12, b15)'
    assert readings.faults_said(['block b09 (line 40): empty body (use status=unreadable)',
                                 "block b04 (line 12): .footnote requires 'marker' unless it continues (cont=prev)",
                                 "block b04 (line 12): in= must point to a box or a list item, not .glossary_entry",
                                 'line 80: attributes not parseable: Unexpected character']) == (
        '1 block left empty (b09), 1 block not in the format (b04) and 1 fault outside a block')
    assert readings.faults_said([]) is None


def a_row(state, reasons, route, level, attempts=()):
    return {'check': {'state': state, 'reasons': reasons}, 'route': route, 'route_level': level,
            'attempts': [{'class_now': one} for one in attempts]}


def test_a_page_not_plainly_ok_says_in_one_sentence_whether_its_reading_is_served_why_and_what_stands_instead():
    malformed = 'text layer: the reading stayed malformed after its one format retry'
    empty = ['block b12 (line 57): empty body (use status=unreadable)', 'block b15 (line 67): empty body (use status=unreadable)']
    four = a_row('issue', ['format: malformed'], malformed, 'fallback', ['malformed'] * 4)
    assert readings.said_of(four, empty) == ('Not served: 4 readings failed the format check, the one shown here with 2 blocks '
                                             "left empty (b12, b15); the PDF's text layer is served instead.")
    # under today's validator a first reading may pass that failed when it was retried: counted as it reads today
    partly = a_row('issue', ['format: malformed'], malformed, 'fallback', ['ok', 'malformed'])
    assert readings.said_of(partly, empty[:1]).startswith('Not served: 1 of 2 readings fails the format check today, the one '
                                                          'shown here with 1 block left empty (b12)')
    blocked = a_row('blocked', ['errored'], 'text layer: the provider blocked the reading', 'fallback', ['errored'])
    assert readings.said_of(blocked, []) == "Not served: the provider blocked the reading; the PDF's text layer is served instead."
    noted = a_row('issue', ['judge: bad', 'omission'], "vision reading (claude-sonnet-5-5, page/1, validator page/1.2): the "
                  "judge's findings lie on blocks never quoted", 'noted', ['ok'])
    assert readings.said_of(noted, []) == "Served despite the judge's findings: the judge's findings lie on blocks never quoted."
    assert readings.said_of(a_row('ok', [], 'vision reading (claude-sonnet-5-5, page/1, validator page/1.2)', 'checked'), []) is None
    # the sentence in the Check line's words, after the state and its reasons (H1.a): no sentence of its own above the record
    assert readings.check_words(readings.said_of(noted, [])) == "served all the same: the judge's findings lie on blocks never quoted"
    assert readings.check_words(readings.said_of(blocked, [])) == (
        "not served: the provider blocked the reading; the PDF's text layer is served instead")
    assert readings.check_words(None) is None
    # a page a person settled: the verdict's mark in the same line says it, so the words say nothing again
    assert readings.check_words('Served: a person accepted the reading.') is None


def test_a_page_not_served_names_the_fallback_the_export_names_and_an_older_export_the_text_layer():
    # H2.a (the operator, 19 Nov): a licensed work with page-numbered legacy Markdown falls back to it, never to its PDF's
    # text layer; invented rows, one per fallback, and one of an export written before the field
    legacy = {**a_row('issue', ['judge: bad'], served_readings.LEGACY_WHY['issue'], 'fallback', ['ok']),
              'fallback': served_readings.LEGACY_ROUTE}
    layer = {**a_row('issue', ['judge: bad'], served_readings.TEXT_LAYER_WHY['issue'], 'fallback', ['ok']),
             'fallback': served_readings.TEXT_LAYER}
    older = a_row('issue', ['judge: bad'], served_readings.TEXT_LAYER_WHY['issue'], 'fallback', ['ok'])
    assert readings.said_of(legacy, []) == ('Not served: the judge found the reading bad, a person looks at it; '
                                            "the IDE's legacy Markdown is served instead.")
    for row in (layer, older):
        assert readings.said_of(row, []) == ('Not served: the judge found the reading bad, a person looks at it; '
                                             "the PDF's text layer is served instead.")
    assert [readings.fallback_of(row) for row in (legacy, layer, older)] == ['legacy markdown', 'text layer', 'text layer']
    served = {**a_row('ok', [], 'vision reading (claude-sonnet-5-5, page/1, validator page/1.2)', 'checked'), 'fallback': None}
    assert readings.fallback_of(served) is None
    assert readings.fallback_of({'route': 'vision reading (claude-sonnet-5-5, page/1, validator page/1.2)'}) is None
    # where nothing above says it, the findings' outcome names the same fallback
    assert readings.findings_outcome(legacy, None) == "the page serves the IDE's legacy Markdown"
    assert readings.findings_outcome(layer, None) == 'the page serves its text layer'
    assert readings.findings_outcome(served, None) == 'the reading is served'
    # and a page the legacy Markdown serves is no reading served: a state's count of served pages leaves it out
    counted = {count.value: count.served for count in readings.counted_states([legacy, layer, {**legacy, 'route': 'vision reading (claude-sonnet-5-5, page/1, validator page/1.2): the judge\'s findings lie on blocks never quoted', 'fallback': None}])}
    assert counted['issue'] == 1


@pytest.mark.readings
def test_every_page_of_the_free_export_not_plainly_ok_says_so_in_a_sentence_and_no_ok_page_does():
    for row in store.rows():
        said = readings.said_of(row, [])
        plainly_ok = row['check']['state'] in ('ok', 'ok_unjudged')
        assert (said is None) == plainly_ok, (row['source_id'], row['pdf_page'], said)
        if said and row['route_level'] == 'fallback':
            assert said.startswith('Not served: ') and said.endswith("the PDF's text layer is served instead.")
    # and the page view carries it, with the faults of the reading shown, for a page that stayed malformed
    malformed = a_live_row(lambda row: 'format: malformed' in row['check']['reasons'] and row.get('text_file'),
                           'page that stayed malformed')
    page = store.page(malformed['source_id'], malformed['pdf_page'], 'a work')
    assert page.said == readings.said_of(malformed, page.reading.errors) and 'the one shown here with' in page.said
    assert page.check_said == readings.check_words(page.said) and page.check_said.startswith('not served: ')


@pytest.mark.readings
def test_a_page_whose_export_lists_no_attempts_says_none_rather_than_none_bought(tmp_path):
    row = copy.deepcopy(store.row(KELLY, 1))
    row.pop('attempts', None)
    row.pop('chosen', None)
    page = a_corpus(tmp_path, [row]).page(KELLY, 1, 'Kelly')
    assert page.attempts is None and page.chosen is None


@pytest.mark.readings
def test_a_page_says_whether_its_text_layer_is_served_instead_of_its_reading(tmp_path):
    blocked = a_blocked_row()
    served = next(row for row in kelly_rows() if row['check']['state'] in ('ok', 'ok_unjudged'))
    assert a_corpus(tmp_path, [blocked]).page(KELLY, blocked['pdf_page'], 'Kelly').from_fallback is True
    assert store.page(KELLY, served['pdf_page'], 'Kelly').from_fallback is False  # its reading is what is quoted


@pytest.mark.corpus
@pytest.mark.readings
def test_a_blocked_page_has_its_original_but_no_reading():
    blocked = a_live_row(lambda row: row['check']['state'] == 'blocked', 'blocked page')
    page = store.page(blocked['source_id'], blocked['pdf_page'], 'a work')
    assert page.reading is None and page.raw is None
    assert page.image.available


@pytest.mark.readings
def test_a_free_pdf_that_is_not_downloaded_says_how_to_get_it(tmp_path):
    corpus = a_corpus(tmp_path, [copy.deepcopy(kelly_rows()[0])])
    image, png = corpus.image(KELLY, 1)
    assert png is None and not image.available
    assert 'python -m backend.ingestion.acquire' in image.why_not


@pytest.mark.readings
def test_a_licensed_pdf_that_is_missing_is_not_sent_to_the_download(tmp_path):
    row = {**copy.deepcopy(kelly_rows()[0]), 'knowledge_base': 'licensed'}
    image, png = a_corpus(tmp_path, [row], knowledge_base='licensed').image(KELLY, 1)
    assert png is None and 'not on this machine' in image.why_not and 'acquire' not in image.why_not


@pytest.mark.readings
def test_neighbours_are_the_previous_and_next_read_pages():
    numbers = [row['pdf_page'] for row in kelly_rows()]
    first, second = store.page(KELLY, numbers[0], 'Kelly'), store.page(KELLY, numbers[1], 'Kelly')
    assert first.previous_page is None and first.next_page == numbers[1]
    assert second.previous_page == numbers[0]
    assert store.page(KELLY, numbers[-1], 'Kelly').next_page is None


def test_a_page_without_a_row_is_none():
    assert store.page(KELLY, 999, 'Kelly') is None


@pytest.mark.readings
def test_the_issues_list_exactly_the_pages_a_person_should_look_at():
    listed = readings.issues({'free': store})
    expected = [row for row in store.rows() if row['check']['state'] in readings.LISTED_AS_ISSUE]
    assert len(listed.rows) == len(expected)
    assert {row.check.state for row in listed.rows} <= set(readings.LISTED_AS_ISSUE)
    assert sum(count.count for count in listed.states) == len(listed.rows)
    assert listed.knowledge_bases == [readings.Count(value='free', count=len(listed.rows))]


@pytest.mark.readings
def test_the_issues_of_two_knowledge_bases_are_ordered_by_base_and_each_names_its_own(tmp_path):
    blocked = a_blocked_row()
    licensed = a_corpus(tmp_path, [{**copy.deepcopy(blocked), 'knowledge_base': 'licensed'}], knowledge_base='licensed')
    listed = readings.issues({'licensed': licensed, 'free': store})
    # by base within the content and within the pages apart from it, which follow (172.a)
    content = [row.knowledge_base for row in listed.rows if row.category in (None, 'content')]
    apart = [row.knowledge_base for row in listed.rows if row.category not in (None, 'content')]
    assert content == sorted(content) and content[-1] == 'licensed' and apart == sorted(apart)
    assert [(count.value, count.count) for count in listed.knowledge_bases][-1] == ('licensed', 1)


def test_a_finding_names_its_block_and_severity():
    findings = [finding for row in store.rows() for finding in ((row['check'].get('verdict') or {}).get('findings') or [])]
    if not findings:
        pytest.skip('no judged finding in the current export')
    shaped = readings.Finding.model_validate(findings[0])
    assert shaped.kind and shaped.severity in ('major', 'minor')


@pytest.mark.readings
def test_a_rewritten_index_is_read_again(tmp_path):
    first = copy.deepcopy(kelly_rows()[0])
    corpus = a_corpus(tmp_path, [first])
    assert len(corpus.rows()) == 1
    index = corpus.index
    data = json.loads(index.read_text(encoding='utf-8'))
    index.write_text(json.dumps({**data, 'pages': [first, {**first, 'pdf_page': 2}]}), encoding='utf-8')
    later = index.stat().st_mtime_ns + 1_000_000_000
    os.utime(index, ns=(later, later))
    assert len(corpus.rows()) == 2


def test_the_public_knowledge_bases_are_the_free_one_alone(monkeypatch):
    def refuse():
        raise AssertionError('the licensed knowledge base was read')

    monkeypatch.setattr(readings, 'licensed_readings', refuse)
    assert set(readings.knowledge_bases(public_only=True)) == {'free'}


def test_a_licensed_export_joins_the_knowledge_bases_by_default(monkeypatch, tmp_path):
    licensed = readings.Readings(tmp_path)
    monkeypatch.setattr(readings, 'licensed_readings', lambda: licensed)
    assert readings.knowledge_bases()['licensed'] is licensed


def test_the_licensed_export_is_read_only_where_it_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(readings, 'LICENSED_EXPORT', tmp_path / 'readings')
    assert readings.licensed_readings() is None
    (tmp_path / 'readings').mkdir()
    (tmp_path / 'readings' / 'index.json').write_text('{}', encoding='utf-8')
    assert readings.licensed_readings().index == tmp_path / 'readings' / 'index.json'


def test_no_index_means_no_readings(tmp_path):
    assert readings.Readings(tmp_path).rows() == [] and readings.Readings(tmp_path).works() == []


@pytest.mark.readings
def test_a_reading_file_changed_after_its_check_is_marked_tampered_and_a_gone_one_missing(tmp_path):
    rows = [copy.deepcopy(row) for row in kelly_rows() if row.get('text_file')][:3]
    corpus = a_corpus(tmp_path, rows)
    tampered, gone, whole = rows
    (corpus.export / tampered['text_file']).write_text('a number changed by hand\n', encoding='utf-8')
    (corpus.export / gone['text_file']).unlink()
    shown = corpus.page(KELLY, tampered['pdf_page'], 'Kelly')
    # a tampered file is still shown as it now reads, and marked: it is not what the checks saw
    assert shown.integrity == 'tampered' and shown.raw == 'a number changed by hand\n'
    missing = corpus.page(KELLY, gone['pdf_page'], 'Kelly')
    assert missing.integrity == 'missing' and missing.reading is None and missing.raw is None
    assert corpus.page(KELLY, whole['pdf_page'], 'Kelly').integrity == 'whole'


@pytest.mark.readings
def test_each_reading_of_a_page_carries_what_its_check_made_of_it(tmp_path):
    row = copy.deepcopy(next(row for row in kelly_rows() if row.get('attempts')))
    first = {**row['attempts'][0], 'reading_key': 'aaaa1111', 'attempt': 0, 'check': {'state': 'issue', 'verdict': 'bad',
                                                                                     'outcome': 'issue'}}
    unchecked = {**row['attempts'][0], 'reading_key': 'bbbb2222', 'attempt': 1, 'check': None}
    row['attempts'] = [first, unchecked, *row['attempts']]
    attempts = a_corpus(tmp_path, [row]).page(KELLY, row['pdf_page'], 'Kelly').attempts
    assert attempts[0].check.model_dump() == {'state': 'issue', 'verdict': 'bad', 'outcome': 'issue', 'reasons': [],
                                              'came_from': None}
    assert attempts[1].check is None
    assert [attempt.shown for attempt in attempts] == [False, False, True]


@pytest.mark.readings
def test_each_reading_says_why_it_stands_and_what_it_cost_a_session_reading_none(tmp_path):
    # invented after licensed pages line 1 named (18 Nov): a first reading the validator refused, which no check reached; its
    # format retry, refused again and checked; and the reading shown, read in a Claude Code session (280.a), which no API
    # ledger prices. The page's row still writes 0.0 in an export of before 18 Nov, so the shown attempt's own field counts
    row = copy.deepcopy(next(row for row in kelly_rows() if row.get('attempts')))
    malformed = ['block b04 (line 26): LaTeX command outside math: \\HL']
    shown = {**row['attempts'][-1], 'mode': 'session', 'cost_usd': None, 'format_errors': [],
             'check': {'state': 'ok', 'verdict': 'ok', 'outcome': 'ok', 'reasons': []}}
    first = {**shown, 'reading_key': 'aaaa1111', 'mode': 'batch', 'cost_usd': 0.0094749, 'format_errors': malformed, 'check': None}
    retry = {**first, 'reading_key': 'bbbb2222', 'attempt': 1,
             'check': {'state': 'issue', 'verdict': None, 'outcome': None, 'reasons': ['format: malformed']}}
    row.update(attempts=[first, retry, shown], cost_usd=0.0)
    corpus = a_corpus(tmp_path, [row])
    page = corpus.page(KELLY, row['pdf_page'], 'Kelly')
    assert [(one.format_errors, one.check.reasons if one.check else None) for one in page.attempts] == [
        (malformed, None), (malformed, ['format: malformed']), ([], [])]
    assert [one.cost_usd for one in page.attempts] == [0.0094749, 0.0094749, None]
    assert page.trace.cost_usd is None
    assert next(one for one in corpus.pages('free', KELLY, 'Kelly').pages if one.pdf_page == row['pdf_page']).cost_usd is None
    # an export that lists no attempt's cost keeps the row's own
    del row['attempts'][-1]['cost_usd']
    assert a_corpus(tmp_path / 'older', [row]).page(KELLY, row['pdf_page'], 'Kelly').trace.cost_usd == 0.0


@pytest.mark.readings
def test_an_automated_reviews_verdict_is_never_a_persons_and_settles_a_page_in_a_bucket_of_its_own(tmp_path):
    # the operator's 2.a and 3.a (18 Nov): "a person is always manual". A verdict a session gave on the operator's delegation
    # names the session; the core serves the page by it but never protects it, and the view never calls it a person's
    row = copy.deepcopy(next(row for row in kelly_rows() if row.get('attempts')))
    row['check'] = {**row['check'], 'state': 'issue', 'reasons': ['judge: bad']}
    row.update(route='vision reading (claude-sonnet-5-5, page/1, validator page/1.4): an automated review (delegated by the '
                     "operator) accepted the reading: the judge's finding contradicts its own evidence",
               route_level='noted', protected=False)
    review = {'reading_key': row['reading_key'], 'applies': True, 'block': None, 'verdict': 'accept',
              'reason': 'judge_contradicts_itself', 'given_by': 'claude-opus-5-5 session, delegated by the operator (17 Nov)',
              'given_at': '2026-11-17T20:00:00+00:00'}
    row['human'] = [review]  # as an export of before 18 Nov writes it: no `by_a_person`, the giver says it
    corpus = a_corpus(tmp_path, [row])
    page = corpus.page(KELLY, row['pdf_page'], 'Kelly')
    assert page.person.by_a_person is False and page.human[0].by_a_person is False
    assert page.listed_state == readings.DECIDED_BY_REVIEW and page.protected is False
    assert page.said == 'Served: an automated review (delegated by the operator) accepted the reading.'
    summary = corpus.pages('free', KELLY, 'Kelly').summary
    assert [(count.value, count.count) for count in summary.reviews] == [('accepted', 1)] and summary.people == []
    bucket = next(count for count in summary.states if count.value == readings.DECIDED_BY_REVIEW)
    assert (bucket.count, bucket.accepted) == (1, 0)
    issues = readings.issues({'free': corpus})
    assert [(count.value, count.count) for count in issues.reviews] == [('accepted', 1)] and issues.people == []
    # the same verdict given by a person stands as a person's, and the export says it protects the page
    row['human'] = [{**review, 'given_by': 'maintainer', 'by_a_person': True}]
    row['protected'] = True
    page = a_corpus(tmp_path / 'person', [row]).page(KELLY, row['pdf_page'], 'Kelly')
    assert page.person.by_a_person and page.listed_state == readings.DECIDED and page.protected is True


@pytest.mark.readings
def test_a_page_carries_its_three_stages_its_judgements_and_a_persons_verdict(tmp_path):
    """146.a, 147.a: stage 2's report and the judge with its version on the page alone; a void finding marked and the
    judge's own outcome beside the one that counts; each reading's judgements, a prototype's and one asked again among
    them; a check that comes from earlier says so; a person's verdict at the page and at the block it names."""
    row = copy.deepcopy(next(row for row in kelly_rows() if row.get('attempts')))
    block = store.page(KELLY, row['pdf_page'], 'Kelly').reading.blocks[0].id
    row['check'] = {**row['check'], 'stage2': {'suspicious': False, 'has_layer': True, 'recall': 1.0, 'precision': 0.99,
                                               'findings': [{'kind': 'text_drawn'}], 'unverifiable': [{'why': 'figure_text'}]},
                    'judge': {'model': 'claude-sonnet-5-5', 'mode': 'batch', 'cost_usd': 0.007, 'version': 'judge/1'},
                    'verdict': {'verdict': 'bad', 'outcome': 'ok', 'judge_outcome': 'issue', 'void': 1, 'findings': [
                        {'kind': 'wrong_word', 'block': block, 'severity': 'major', 'evidence': "'a' is 'a'", 'void': True}]}}
    row['attempts'][-1] = {**row['attempts'][-1], 'check': {'state': 'ok', 'verdict': 'bad', 'outcome': 'ok', 'from': 'an earlier check'},
                           'judgements': [{'version': 'judge/1', 'version_state': 'active', 'again': 0, 'counts': True},
                                          {'version': 'judge/1', 'version_state': 'active', 'again': 1, 'counts': False},
                                          {'version': 'judge/2', 'version_state': 'prototype', 'again': 0, 'counts': False}]}
    row['human'] = [{'reading_key': row['reading_key'], 'applies': True, 'block': block, 'verdict': 'accept', 'reason_text': 'identical'},
                    {'reading_key': 'older', 'applies': False, 'block': None, 'verdict': 'note'}]
    corpus = a_corpus(tmp_path, [row])
    page = corpus.page(KELLY, row['pdf_page'], 'Kelly')
    assert page.check.stage2.recall == 1.0 and page.check.stage2.findings[0].kind == 'text_drawn' and page.check.judge.version == 'judge/1'
    assert (page.check.verdict.outcome, page.check.verdict.judge_outcome, page.check.verdict.void) == ('ok', 'issue', 1)
    first = page.reading.blocks[0]
    assert first.findings[0].void is True and [person.verdict for person in first.people] == ['accept']
    assert [(person.verdict, person.applies) for person in page.human] == [('accept', True), ('note', False)]
    shown = page.attempts[-1]
    assert shown.check.came_from == 'an earlier check'
    assert [(j.version, j.version_state, j.again, j.counts) for j in shown.judgements] == [
        ('judge/1', 'active', 0, True), ('judge/1', 'active', 1, False), ('judge/2', 'prototype', 0, False)]
    # a list of pages carries neither stage 2 nor the judge: only the page's own view shows them
    listed = corpus.pages('free', KELLY, 'Kelly').pages[0].check
    assert listed.stage2 is None and listed.judge is None


def a_verdict(verdict, applies=True, **fields):
    return {'reading_key': 'r1', 'applies': applies, 'verdict': verdict, 'given_by': 'maintainer',
            'given_at': '2026-11-10T10:26:29+00:00', **fields}


def test_a_persons_latest_accept_or_reject_that_applies_stands_beside_the_state_and_a_note_never_changes_it():
    row = {'human': [a_verdict('note', note='three boxes read as unreadable'),
                     a_verdict('accept', reason='judge_wrong', reason_text='the judge miscounted')]}
    mark = readings.person_mark(row)
    assert (mark.standing, mark.reason, mark.note) == ('accepted', 'the judge miscounted', None)
    # a note after the accept leaves it standing, as the core decides what is served (served_readings.human_standing)
    row['human'].append(a_verdict('note', note='checked again'))
    assert readings.person_mark(row).standing == 'accepted'
    row['human'].append(a_verdict('reject', reason='wrong_value'))
    assert readings.person_mark(row).standing == 'rejected'
    # only a note: noted; a verdict on an earlier reading does not carry over; nothing: no mark
    assert readings.person_mark({'human': [a_verdict('note', note='lost boxes')]}).model_dump()['standing'] == 'noted'
    assert readings.person_mark({'human': [a_verdict('accept', applies=False)]}) is None
    assert readings.person_mark({'human': []}) is None and readings.person_mark({}) is None


def test_a_states_count_says_how_many_of_its_pages_a_person_accepted_or_rejected():
    check = {'state': 'issue', 'reasons': []}
    rows = [{'check': check, 'human': [a_verdict('accept')]}, {'check': check, 'human': [a_verdict('note')]},
            {'check': check}, {'check': {'state': 'ok', 'reasons': []}, 'human': [a_verdict('reject')]}]
    # an issue a person accepted or noted is settled, counted in its own bucket (211.a); a verdict on an ok page leaves it ok
    counts = {count.value: (count.count, count.accepted, count.rejected, count.noted) for count in readings.counted_states(rows)}
    assert counts == {readings.DECIDED: (2, 1, 0, 1), 'issue': (1, 0, 0, 0), 'ok': (1, 0, 1, 0)}
    assert [(count.value, count.count) for count in readings.counted_people(rows)] == [
        ('accepted', 1), ('rejected', 1), ('noted', 1)]


ACCOUNTING = 'openstax_principles_of_accounting_v1'


@pytest.mark.readings
def test_the_free_exports_judged_pages_carry_their_persons_mark_in_every_list_and_in_the_page():
    accepted = store.row(ACCOUNTING, 635)
    noted = store.row(ACCOUNTING, 524)
    assert readings.person_mark(accepted).standing == 'accepted' and readings.person_mark(noted).standing == 'noted'
    rows = {row.pdf_page: row for row in store.pages('free', ACCOUNTING, 'Accounting').pages}
    assert (rows[635].person.standing, rows[524].person.standing) == ('accepted', 'noted')
    listed = {(row.source_id, row.pdf_page): row for row in readings.issues({'free': store}).rows}
    assert listed[(ACCOUNTING, 524)].person.standing == 'noted'
    listed_in = next(count for count in store.summary(ACCOUNTING).states if count.value == readings.listed_state(accepted))
    assert listed_in.accepted >= 1


@pytest.mark.readings
def test_a_pages_category_stands_in_every_list_and_the_pages_that_are_not_content_are_counted_and_listed_last():
    rows = store.rows()
    assert {row.category for row in store.pages('free', ACCOUNTING, 'Accounting').pages} >= {'content', 'exercise', 'index'}
    # counted with content first and the pages no reading named last
    categories = [count.value for count in readings.counted_categories(rows)]
    assert categories[0] == 'content' and set(categories) == {readings.category_of(row) for row in rows}
    if readings.NOT_NAMED in categories:
        assert categories[-1] == readings.NOT_NAMED
    # the Issues: every page that is not content after every page that is, each carrying its category
    listed = readings.issues({'free': store})
    apart = [row.category not in (None, 'content') for row in listed.rows]
    assert apart == sorted(apart) and any(apart) and not all(apart)
    assert sum(count.count for count in listed.categories) == len(listed.rows)


@pytest.mark.readings
def test_a_page_says_what_kind_of_page_it_is_where_a_reading_named_it():
    row = next(row for row in store.rows_of(ACCOUNTING) if row.get('category') == 'index')
    page = store.page(ACCOUNTING, row['pdf_page'], 'Accounting')
    assert (page.category, page.page_kind) == ('index', 'index')


@pytest.mark.readings
def test_every_category_the_core_can_give_but_content_is_said_in_a_line_for_its_hover():
    from backend.conversion.store.reading_export import CATEGORY_OF_KIND
    given = (set(CATEGORY_OF_KIND.values()) | {'exercise'}) - {'content'}
    assert set(readings.CATEGORY_SAID) == given and all(readings.CATEGORY_SAID.values())
    rows = {row.pdf_page: row for row in store.pages('free', ACCOUNTING, 'Accounting').pages}
    index = next(row for row in rows.values() if row.category == 'index')
    assert index.category_said == readings.CATEGORY_SAID['index']
    assert all(row.category_said is None for row in rows.values() if row.category in (None, 'content'))


FINANCE = 'openstax_principles_of_finance_2e'


@pytest.mark.readings
def test_a_judgement_is_recalled_on_the_reading_it_judged_with_its_own_findings_on_the_blocks():
    page = store.page(FINANCE, 5, 'Finance')
    shown = next(attempt for attempt in page.attempts if attempt.shown)
    by_version = {judgement.version: judgement.recall for judgement in shown.judgements if not judgement.again}
    found = store.recall(FINANCE, 5, by_version['judge/2'])
    assert found.said == f'judge/2 (prototype) on reading {shown.number}, never served'
    b12 = next(block for block in found.reading.blocks if block.id == 'b12')
    assert [(finding.kind, finding.void) for finding in b12.findings] == [('wrong_word', True)]
    none = store.recall(FINANCE, 5, by_version['judge/3'])
    assert all(not block.findings for block in none.reading.blocks) and not none.page_findings
    # a recall names its judgement, so the page view's link can be sent
    assert found.recall == by_version['judge/2'] and found.reading_key == shown.reading_key


@pytest.mark.readings
def test_an_older_reading_is_read_from_the_cores_store_where_this_machine_has_it_and_says_so_where_not(tmp_path, monkeypatch):
    row = store.row(FINANCE, 5)
    older = next(attempt for attempt in row['attempts'] if attempt['reading_key'] != row['reading_key'])
    recall = readings.recall_id(older['reading_key'], older['judgements'][0])
    monkeypatch.setitem(readings.reading_store.ROOTS, 'free', tmp_path / 'vision')
    missing = store.recall(FINANCE, 5, recall)
    assert missing.reading is None and missing.raw is None and 'not on this machine' in missing.why_not
    folder = tmp_path / 'vision' / 'readings' / older['reading_key'][:2]
    folder.mkdir(parents=True)
    shutil.copyfile(readings.FREE_EXPORT / row['text_file'], folder / f"{older['reading_key']}.md")
    found = store.recall(FINANCE, 5, recall)
    assert found.reading is not None and found.why_not is None and found.reading_number == 1


@pytest.mark.readings
def test_a_recall_by_an_id_the_page_does_not_have_finds_nothing_and_never_leaves_the_store():
    row = store.row(FINANCE, 5)
    assert store.recall(FINANCE, 5, f"{row['reading_key']}:judge/9:0") is None
    assert store.recall(FINANCE, 5, '../../../etc/passwd:judge/1:0') is None
    assert store.recall(FINANCE, 999, f"{row['reading_key']}:judge/1:0") is None


@pytest.mark.readings
def test_a_persons_correction_and_assessment_of_the_judge_reach_the_block_they_name():
    page = store.page(FINANCE, 94, 'Finance')
    b05 = next(block for block in page.reading.blocks if block.id == 'b05')
    person = next(one for one in b05.people if one.correction)
    assert person.applies and person.judge_assessment == 'right_for_a_wrong_reason'
    assert person.judge_assessment_text and 'ends higher' in person.correction


def test_a_persons_assessment_names_the_judge_that_counted_when_they_gave_it_never_a_prototype():
    # invented: judge/1 counted on reading r1, a person rated its finding, and judge/4 judged the reading afterwards
    judge1 = {'version': 'judge/1', 'counts': True, 'stored_at': '2026-11-09T10:00:00+00:00'}
    judge4 = {'version': 'judge/4', 'version_state': 'prototype', 'counts': False, 'stored_at': '2026-11-10T22:46:58+00:00'}
    later = {'version': 'judge/5', 'counts': True, 'stored_at': '2026-11-12T08:00:00+00:00'}
    attempts = [{'reading_key': 'r0', 'judgements': [{**judge1, 'version': 'judge/0'}]},
                {'reading_key': 'r1', 'judgements': [judge1, judge4, later]}]
    person = {'reading_key': 'r1', 'judge_assessment': 'false_alarm', 'given_at': '2026-11-10T20:41:16.123456+00:00'}
    assert readings.assessed_judge(person, attempts) == 'judge/1'
    # a judge that counted only after the person spoke is not the one they rated, nor one on another reading
    assert readings.assessed_judge({**person, 'given_at': '2026-11-13T00:00:00+00:00'}, attempts) == 'judge/5'
    assert readings.assessed_judge({**person, 'reading_key': 'r0'}, attempts) == 'judge/0'
    # no assessment, or no judgement that counted: nothing is named
    assert readings.assessed_judge({**person, 'judge_assessment': None}, attempts) is None
    assert readings.assessed_judge(person, [{'reading_key': 'r1', 'judgements': [judge4]}]) is None


@pytest.mark.readings
def test_a_recalled_prototype_keeps_a_persons_assessment_of_the_judge_that_counted(tmp_path):
    # invented over Kelly: a person rated judge/1's finding on b02 a false alarm, and judge/4 judged the reading after them
    row = copy.deepcopy(next(row for row in kelly_rows() if row.get('text_file') and row['check']['state'] == 'ok'))
    finding = {'kind': 'structure', 'block': 'b02', 'severity': 'major', 'evidence': 'a column short', 'void': False}
    judge1 = {'version': 'judge/1', 'version_state': 'active', 'counts': True, 'again': 0, 'stored_at': '2026-11-09T10:00:00+00:00',
              'verdict': 'bad', 'outcome': 'issue', 'findings': [finding]}
    judge4 = {**judge1, 'version': 'judge/4', 'version_state': 'prototype', 'counts': False, 'stored_at': '2026-11-10T22:46:58+00:00',
              'verdict': 'ok', 'outcome': 'ok', 'findings': [{**finding, 'kind': 'other', 'severity': 'minor'}]}
    row['attempts'] = [{'reading_key': row['reading_key'], 'model': 'claude-sonnet-5-5', 'mode': 'batch', 'attempt': 0,
                        'class_now': 'ok', 'stored_at': '2026-11-09T09:00:00+00:00', 'judgements': [judge1, judge4]}]
    row['human'] = [{'reading_key': row['reading_key'], 'applies': True, 'block': 'b02', 'verdict': 'accept', 'reason': 'other',
                     'note': 'the grid is right', 'given_at': '2026-11-10T20:41:16+00:00', 'judge_assessment': 'false_alarm'}]
    corpus = a_corpus(tmp_path, [row])
    page = corpus.page(KELLY, row['pdf_page'], 'Kelly')
    assert [person.assessed for person in page.human] == ['judge/1']
    recalled = corpus.recall(KELLY, row['pdf_page'], readings.recall_id(row['reading_key'], judge4))
    b02 = next(block for block in recalled.reading.blocks if block.id == 'b02')
    assert [(one.kind, one.severity) for one in b02.findings] == [('other', 'minor')]
    assert [(person.verdict, person.assessed) for person in b02.people] == [('accept', 'judge/1')]


@pytest.mark.readings
def test_a_pages_head_says_its_route_in_parts_and_what_its_findings_come_to_and_where_it_opens(tmp_path):
    page = store.page(FINANCE, 5, 'Finance')
    from backend.conversion.store import reading_export  # the validator this export was written with, not a pinned version (212.a)

    assert (page.route_level, page.route_source, page.route_reader) == (
        'noted', 'vision reading', ['claude-sonnet-5-5', 'page/1', f"validator {reading_export.FROZEN['validator']}"])
    assert [(one.block, one.said, one.severity) for one in page.findings_at] == [('b12', 'void by code', None)]
    # a person's line says what the findings come to, so the findings line does not say it again (the operator, 11 Nov)
    assert page.findings_outcome is None and page.focus == 'b12'
    # a standing finding on a page served from its text layer, invented, since a person's walk changes the real pages:
    # its head says it stands and the text layer is served, and the Issues' link opens on its first block in reading order
    row = copy.deepcopy(next(row for row in kelly_rows() if row.get('text_file') and row['check']['state'] == 'ok'))
    standing = {'kind': 'wrong_value', 'severity': 'major', 'evidence': '1.034 read as 1.043', 'void': False}
    row['check'] = {**row['check'], 'state': 'issue', 'reasons': ['judge: bad'],
                    'verdict': {'verdict': 'bad', 'outcome': 'issue', 'findings': [{**standing, 'block': 'b03'}, {**standing, 'block': 'b02'}]}}
    row.update(route=sorted(served_readings.TEXT_LAYER_WHY.values())[0], route_level='fallback', human=[])
    corpus = a_corpus(tmp_path, [row])
    bad = corpus.page(KELLY, row['pdf_page'], 'Kelly')
    assert [(one.block, one.said, one.severity) for one in bad.findings_at] == [('b02', 'stands', 'major'), ('b03', 'stands', 'major')]
    # the sentence above the record says the text layer is served, so neither the findings line nor "Why:" says it again
    assert bad.said.startswith('Not served: ') and bad.findings_outcome is None and bad.why_line is None
    assert bad.focus == 'b02'
    assert [listed.focus for listed in readings.issues({'free': corpus}).rows] == ['b02']
    # an ok page without findings says nothing of them and opens at its top
    plain = next(row for row in store.rows_of(FINANCE) if row['check']['state'] == 'ok' and not (row['check'].get('verdict') or {}).get('findings'))
    page = store.page(FINANCE, plain['pdf_page'], 'Finance')
    assert page.findings_at is None and page.findings_outcome is None and page.focus is None


@pytest.mark.readings
def test_the_head_says_each_thing_once_the_why_only_where_nothing_else_on_the_page_says_it(tmp_path):
    # invented over Kelly, since a person's walk changes the real pages
    base = copy.deepcopy(next(row for row in kelly_rows() if row.get('text_file') and row['check']['state'] == 'ok'))
    route = f"{base['route'].split(': ')[0]}"
    void = {'kind': 'wrong_word', 'block': 'b02', 'severity': 'major', 'evidence': "'a' is 'a'", 'void': True}
    # an ok page with a void finding and no person: nothing above says what it comes to, so the findings line does
    quiet = {**copy.deepcopy(base), 'human': [], 'route': route,
             'check': {**base['check'], 'verdict': {'verdict': 'bad', 'outcome': 'ok', 'findings': [void]}}}
    page = a_corpus(tmp_path / 'quiet', [quiet]).page(KELLY, base['pdf_page'], 'Kelly')
    assert (page.said, page.why_line, page.findings_outcome) == (None, None, 'the reading is served')
    # a second reader's why on an ok page: no sentence says it, so "Why:" does
    second = {**quiet, 'route': f'{route}: anthropic blocked the page (content filter)'}
    page = a_corpus(tmp_path / 'second', [second]).page(KELLY, base['pdf_page'], 'Kelly')
    assert page.why_line == 'anthropic blocked the page (content filter)'
    # a person's accept on the page as a whole, where no block has a finding: their note stands nowhere else, so "Why:"
    # keeps it, and only it, as the person's line says the accept
    accept = {'reading_key': base['reading_key'], 'applies': True, 'block': None, 'verdict': 'accept', 'reason': 'other',
              'note': 'every value checked by hand', 'given_by': 'maintainer', 'given_at': '2026-11-10T20:00:00+00:00'}
    alone = {**copy.deepcopy(base), 'human': [accept], 'route': f'{route}: a person accepted the reading: every value checked by hand'}
    page = a_corpus(tmp_path / 'alone', [alone]).page(KELLY, base['pdf_page'], 'Kelly')
    assert page.why_line == 'every value checked by hand' and page.findings_outcome is None
    # the same accept on a block: it stands beneath that block, so the head does not say it again
    on_block = {**alone, 'human': [{**accept, 'block': 'b02'}]}
    page = a_corpus(tmp_path / 'block', [on_block]).page(KELLY, base['pdf_page'], 'Kelly')
    assert page.why_line is None and [one.note for one in page.reading.blocks[1].people] == ['every value checked by hand']


def settled_corpus(tmp_path):
    """Invented over Kelly (211.a): four pages the check found an issue on, settled by a person's accept, by a note, and by
    an accept a reset archived, and one left alone; and an ok page a person accepted."""
    base = [row for row in kelly_rows() if row.get('text_file') and row['check']['state'] == 'ok'][:5]
    verdict = {'applies': True, 'archived': False, 'block': None, 'reason': 'other', 'note': 'looked at by hand',
               'given_by': 'maintainer', 'given_at': '2026-11-10T20:00:00+00:00'}
    rows = []
    for row, (state, human) in zip(copy.deepcopy(base), [
            ('issue', [{**verdict, 'verdict': 'accept'}]),
            ('issue', [{**verdict, 'verdict': 'note'}]),
            ('issue', [{**verdict, 'verdict': 'accept', 'applies': False, 'archived': True}]),
            ('issue', []),
            ('ok', [{**verdict, 'verdict': 'accept'}])]):
        row['check'] = {**row['check'], 'state': state, 'reasons': ['judge: bad'] if state == 'issue' else []}
        row['human'] = [{**one, 'reading_key': row['reading_key']} for one in human]
        rows.append(row)
    return a_corpus(tmp_path, rows), [row['pdf_page'] for row in rows]


@pytest.mark.readings
def test_a_page_a_person_settled_leaves_the_issues_for_a_bucket_of_its_own_split_by_the_verdict(tmp_path):
    corpus, (accepted, noted, archived, untouched, passed) = settled_corpus(tmp_path)
    rows = {row['pdf_page']: row for row in corpus.rows_of(KELLY)}
    # an accept and a note settle a page the check listed; a verdict a reset archived settles nothing, so that page is an
    # issue again; a page a person did not judge stays an issue, and an ok page a person accepted stays ok
    assert {page: readings.listed_state(rows[page]) for page in (accepted, noted, archived, untouched, passed)} == {
        accepted: readings.DECIDED, noted: readings.DECIDED, archived: 'issue', untouched: 'issue', passed: 'ok'}
    states = {count.value: count for count in corpus.summary(KELLY).states}
    assert (states[readings.DECIDED].count, states[readings.DECIDED].accepted, states[readings.DECIDED].noted) == (2, 1, 1)
    assert states['issue'].count == 2 and (states['ok'].accepted, states['ok'].noted) == (1, 0)
    # the bucket stands between what is not known and what to look at
    order = [count.value for count in corpus.summary(KELLY).states]
    assert order.index(readings.DECIDED) < order.index('issue')
    # every list carries it: the work's rows, the page, and the Issues, which keep the settled pages as a record
    listed = {row.pdf_page: row.listed_state for row in corpus.pages('free', KELLY, 'Kelly').pages}
    assert listed[accepted] == readings.DECIDED and listed[archived] == 'issue'
    assert corpus.page(KELLY, noted, 'Kelly').listed_state == readings.DECIDED
    issues = readings.issues({'free': corpus})
    assert sorted((row.pdf_page, row.listed_state) for row in issues.rows if row.source_id == KELLY and row.pdf_page in rows) == sorted(
        [(accepted, readings.DECIDED), (noted, readings.DECIDED), (archived, 'issue'), (untouched, 'issue')])
    decided = next(count for count in issues.states if count.value == readings.DECIDED)
    assert (decided.count, decided.accepted, decided.noted, decided.rejected) == (2, 1, 1, 0)


def a_block(id_: str, block_class: str, segments=None, rows=None, **attrs) -> readings.Block:
    return readings.Block(id=id_, block_class=block_class, group='content', content='V', attrs=attrs, bbox=None,
                          segments=segments, latex=None, rows=rows, code=None, text=None, findings=[])


def test_a_note_marker_links_the_footnote_on_its_page_and_a_marker_without_one_stands_alone():
    # invented: "processes.[4]{.fn}" in a paragraph and a table cell, its note as a block, a superscript and a subscript
    text, fn = (lambda content: readings.Segment(kind='text', content=content)), (lambda mark: readings.Segment(kind='fn', content=mark))
    prose = a_block('b02', 'paragraph', [text('processes.'), fn('4'), text(' and '), fn('7'),
                                          readings.Segment(kind='sup', content='2'), readings.Segment(kind='sub', content='t')])
    cell = readings.Cell(segments=[text('12.5'), fn('4')], header=False, rowspan=1, colspan=1)
    table = a_block('b03', 'table', rows=[[cell]])
    note = a_block('b09', 'footnote', [text('The source of the figures.')], marker='4')
    second = a_block('b10', 'footnote', [text('A second note with the same marker.')], marker='4')
    readings.with_notes([prose, table, note, second])
    linked = [(segment.kind, segment.content, segment.note, segment.note_text) for segment in prose.segments]
    assert linked[1] == ('fn', '4', 'b09', 'The source of the figures.')  # the first note with the marker stands
    assert linked[3] == ('fn', '7', None, None)  # no note carries 7: the marker stands alone
    assert [(kind, note_id) for kind, _, note_id, _ in linked[4:]] == [('sup', None), ('sub', None)]
    assert (cell.segments[1].note, cell.segments[1].note_text) == ('b09', 'The source of the figures.')
    # a page without a note leaves its markers as they are
    alone = a_block('b01', 'paragraph', [fn('1')])
    assert readings.with_notes([alone])[0].segments[0].note is None


def test_a_persons_correction_of_a_table_is_given_as_its_cells_and_any_other_correction_stays_text():
    # invented: a table block corrected with a grid of its own, a paragraph corrected in words, and a table corrected with
    # text that is no table
    grid = '<table><tr><th colspan="2">Assets</th></tr><tr><td>Debit<br>Increase</td><td>Credit<br>Decrease</td></tr></table>'
    person = lambda block, correction: readings.PersonVerdict(reading_key='r1', block=block, verdict='accept', correction=correction)
    table = a_block('b03', 'table', rows=[[readings.Cell(segments=[], header=False, rowspan=1, colspan=1)]])
    table.people = [person('b03', grid)]
    words = a_block('b05', 'paragraph', [readings.Segment(kind='text', content='the crossing in 2000')])
    words.people = [person('b05', 'the crossing around 2012')]
    plain = a_block('b07', 'table', rows=[[readings.Cell(segments=[], header=False, rowspan=1, colspan=1)]])
    plain.people = [person('b07', 'the second column is Credit')]
    # a table the reader marked unreadable has no cells of its own, and its correction is still a table (accounting p. 524)
    unreadable = a_block('b11', 'table')
    unreadable.people = [person('b11', '<table><tbody><tr><td>Petty Cash</td><td>150</td></tr></tbody></table>')]
    readings.with_corrections([table, words, plain, unreadable])
    rows = table.people[0].correction_rows
    assert [[(cell.header, cell.colspan, ''.join(segment.content for segment in cell.segments)) for cell in line] for line in rows] == [
        [(True, 2, 'Assets')], [(False, 1, 'Debit\nIncrease'), (False, 1, 'Credit\nDecrease')]]  # a break a line, as printed
    assert words.people[0].correction_rows is None and plain.people[0].correction_rows is None
    assert unreadable.rows is None
    assert [[''.join(segment.content for segment in cell.segments) for cell in line] for line in unreadable.people[0].correction_rows] == [
        ['Petty Cash', '150']]
    # the correction's text itself is kept as given, beside its cells
    assert table.people[0].correction == grid


@pytest.mark.readings
def test_a_line_break_in_a_table_cell_reaches_the_view_as_a_break_and_a_table_without_one_as_before():
    # accounting p. 398's journal entry, as the reader wrote it (page/1 allows <br> in a cell): the credit account and its
    # amount a line below the debit's; the core's own parse reads each break as a space, which its quoted text needs
    entry = ('<table>\n<tbody>\n<tr><td>Accounts Payable<br>      Merchandise Inventory</td><td>600</td><td><br>600</td></tr>\n'
             '</tbody>\n</table>')
    rows, problems, _ = readings.page_contract.parse_table(entry)
    assert not problems and rows[0][0].text == 'Accounts Payable       Merchandise Inventory'
    said = lambda cells: [[[(segment.kind, segment.content) for segment in cell.segments] for cell in line] for line in cells]
    assert said(readings.table_cells(entry, rows)) == [[
        [('text', 'Accounts Payable'), ('br', '\n'), ('text', 'Merchandise Inventory')], [('text', '600')], [('br', '\n'), ('text', '600')]]]
    # a self-closing break is the same break
    closed = '<table><tr><td>a<br/>b</td></tr></table>'
    assert said(readings.table_cells(closed, readings.page_contract.parse_table(closed)[0])) == [[[('text', 'a'), ('br', '\n'), ('text', 'b')]]]
    # a table without a break is given exactly as the core's parse gives it: nothing else changes (Kelly p. 7's tables)
    for block in store.page(KELLY, 7, 'Kelly').reading.blocks:
        if block.rows:
            assert all(segment.kind != 'br' for line in block.rows for cell in line for segment in cell.segments)
    plain = '<table><tr><th>p</th><td>0.6  and  more</td></tr></table>'
    plain_rows = readings.page_contract.parse_table(plain)[0]
    assert said(readings.table_cells(plain, plain_rows)) == [[[(kind, content) for kind, content in cell.inline['segments']]
                                                              for cell in line] for line in plain_rows]


def test_the_correction_that_stands_for_a_block_is_the_latest_that_applies_to_the_reading_shown():
    # invented, after accounting p. 398 (b04, a list item corrected to its marker "A.") and p. 524 (a table over a table
    # the reader marked unreadable): what stands is drawn first in the view (229.a); one on an earlier reading, or archived
    # by a reset, never stands
    person = lambda correction, at, **more: readings.PersonVerdict(reading_key='r1', block='b04', verdict='note', correction=correction,
                                                                   given_by='maintainer', given_at=at, **more)
    item = a_block('b04', 'list_item', [readings.Segment(kind='text', content='A. <table>...</table>')])
    item.people = [person('A', '2026-11-12T18:00:00+00:00'), person('A.', '2026-11-12T18:10:20+00:00'),
                   person('on another reading', '2026-11-12T19:00:00+00:00', applies=False),
                   person('before a reset', '2026-11-12T19:30:00+00:00', archived=True), person(None, '2026-11-12T20:00:00+00:00')]
    table = a_block('b11', 'table')
    table.people = [person('<table><tr><td>Petty Cash</td><td>150</td></tr></table>', '2026-11-12T11:48:40+00:00')]
    untouched = a_block('b05', 'paragraph', [readings.Segment(kind='text', content='as read')])
    untouched.people = [person(None, '2026-11-12T18:10:20+00:00')]
    readings.with_corrections([item, table, untouched])
    assert (item.correction.text, item.correction.rows, item.correction.given_by, item.correction.given_at) == (
        'A.', None, 'maintainer', '2026-11-12T18:10:20+00:00')
    assert table.correction.text.startswith('<table>')
    assert [[''.join(segment.content for segment in cell.segments) for cell in line] for line in table.correction.rows] == [['Petty Cash', '150']]
    assert untouched.correction is None
    # the reading is never changed by it: the block's own text stays the reader's
    assert item.segments[0].content == 'A. <table>...</table>'


@pytest.mark.readings
def test_a_reader_prototypes_reading_is_an_attempt_of_its_own_and_a_recall_names_the_reader(tmp_path):
    # invented over Kelly (210.a): a reading by the reader prototype page/2 beside the served one, judged by judge/4
    row = copy.deepcopy(next(row for row in kelly_rows() if row.get('text_file') and row['check']['state'] == 'ok'))
    judge4 = {'version': 'judge/4', 'version_state': 'prototype', 'counts': False, 'again': 0, 'stored_at': '2026-11-11T09:00:00+00:00',
              'verdict': 'ok', 'outcome': 'ok', 'findings': []}
    served = {'reading_key': row['reading_key'], 'model': 'claude-sonnet-5-5', 'mode': 'batch', 'attempt': 0, 'class_now': 'ok',
              'stored_at': '2026-11-02T09:00:00+00:00', 'reader_version': 'page/1', 'judgements': []}
    prototype = {**served, 'reading_key': 'ab' * 32, 'cell': 'P2-WALK-SM', 'reader_version': 'page/2', 'prototype': True,
                 'purpose': 'a reader prototype (page/2), never served', 'stored_at': '2026-11-11T08:00:00+00:00', 'judgements': [judge4]}
    row['attempts'] = [served, prototype]
    corpus = a_corpus(tmp_path, [row])
    attempts = corpus.page(KELLY, row['pdf_page'], 'Kelly').attempts
    assert [(one.number, one.reader_version, bool(one.prototype), one.shown) for one in attempts] == [
        (1, 'page/1', False, True), (2, 'page/2', True, False)]
    recalled = corpus.recall(KELLY, row['pdf_page'], readings.recall_id('ab' * 32, judge4))
    assert recalled.said == 'judge/4 (prototype) on reading 2, read by page/2 (prototype), never served'
    # a judgement that counts, on the pipeline's own reading, says nothing of a reader
    assert readings.recall_said({'version': 'judge/1', 'version_state': 'active', 'counts': True}, 1, served) == 'judge/1 (active) on reading 1, counts'


@pytest.mark.readings
def test_a_judges_rules_for_the_reader_reach_the_page_with_a_field_not_set_said_as_none(tmp_path):
    # invented (202.a): judge/4 proposing a format rule and an attribute, the export's '' for what a rule does not name
    row = copy.deepcopy(next(row for row in kelly_rows() if row.get('text_file') and row['check']['state'] == 'ok'))
    rules = [{'kind': 'format_rule', 'block': 'b03', 'rule': 'Give each account header a colspan of two.', 'class': '', 'attribute': '', 'value': ''},
             {'kind': 'attribute', 'block': 'b09', 'rule': 'Invent no bullet marker.', 'class': 'list_item', 'attribute': 'marker', 'value': ''}]
    judge4 = {'version': 'judge/4', 'version_state': 'prototype', 'counts': False, 'again': 0, 'stored_at': '2026-11-11T09:00:00+00:00',
              'verdict': 'bad', 'outcome': 'issue', 'findings': [], 'reader_rules': rules}
    row['attempts'] = [{'reading_key': row['reading_key'], 'model': 'claude-sonnet-5-5', 'mode': 'batch', 'attempt': 0, 'class_now': 'ok',
                        'stored_at': '2026-11-02T09:00:00+00:00', 'judgements': [judge4, {**judge4, 'version': 'judge/1', 'reader_rules': []}]}]
    judgements = a_corpus(tmp_path, [row]).page(KELLY, row['pdf_page'], 'Kelly').attempts[0].judgements
    assert [rule.model_dump() for rule in judgements[0].reader_rules] == [
        {'kind': 'format_rule', 'block': 'b03', 'rule': 'Give each account header a colspan of two.', 'block_class': None, 'attribute': None, 'value': None},
        {'kind': 'attribute', 'block': 'b09', 'rule': 'Invent no bullet marker.', 'block_class': 'list_item', 'attribute': 'marker', 'value': None}]
    assert judgements[1].reader_rules == []


def test_the_head_names_a_blocks_gravest_standing_severity_and_none_where_code_voided_all():
    # invented findings (the operator, 12 Nov, on accounting p. 524: the head's findings in a finding's own look)
    finding = lambda severity, void=False: readings.Finding(kind='wrong_value', block='b01', severity=severity, evidence=None, void=void)
    assert readings.gravest([finding('minor'), finding('major')]) == 'major'
    assert readings.gravest([finding('minor'), finding('major', void=True)]) == 'minor'  # a void major counts for nothing
    assert readings.gravest([finding('major', void=True)]) is None
    assert readings.gravest([finding('note'), finding('minor')]) == 'minor'  # a severity it does not know after those it does


@pytest.mark.readings
def test_a_photo_on_a_chapter_opener_is_marked_as_chapter_art_and_nothing_else_is():
    page = store.page(FINANCE, 387, 'Finance')
    assert page.page_kind == 'chapter_opener'
    marked = [(block.id, block.decorative) for block in page.reading.blocks if block.decorative]
    assert marked == [('b01', readings.CHAPTER_ART)]
    # a photo on any other page is a photo
    other = store.page(FINANCE, 5, 'Finance')
    assert not any(block.decorative for block in other.reading.blocks)


@pytest.mark.readings
def test_a_finding_no_verdict_names_takes_the_page_verdict_and_the_head_says_a_persons_accept_once():
    page = store.page(FINANCE, 408, 'Finance')
    people = {block.id: [(one.verdict, one.block) for one in block.people] for block in page.reading.blocks if block.findings}
    assert people['b05'] == [('accept', 'b05')] and people['b10'] == [('accept', None)]
    # the sentence says the accept short; its note stands once, beneath the blocks the verdicts name, so the head has no
    # "Why:" line (the operator, 11 Nov), while the route's card keeps the whole why
    assert page.said == 'Served: a person accepted the reading.' and page.route_why.startswith('a person accepted the reading: ')
    assert page.why_line is None
    # the reason `other` reads as the start of the note, not its placeholder
    assert page.person.reason.startswith('All 100 portfolio values') and 'another reason' not in page.person.reason
    assert page.protected is True and page.reset is None


@pytest.mark.readings
def test_a_reset_page_says_its_reset_and_its_earlier_verdicts_stand_archived(tmp_path):
    row = copy.deepcopy(next(row for row in kelly_rows() if row.get('text_file')))
    reset = {'reason': 'the reading lost a table', 'given_by': 'maintainer', 'given_at': '2026-11-11T09:00:00+00:00'}
    row.update(reset=reset, human=[{'reading_key': row['reading_key'], 'applies': False, 'archived': True, 'block': None,
                                    'verdict': 'accept', 'reason': 'judge_wrong', 'given_at': '2026-11-10T09:00:00+00:00'}])
    page = a_corpus(tmp_path, [row]).page(KELLY, row['pdf_page'], 'Kelly')
    assert page.reset.reason == 'the reading lost a table'
    assert [(one.archived, one.archived_at) for one in page.human] == [(True, '2026-11-11T09:00:00+00:00')]
    assert page.person is None  # an archived verdict never applies


def test_a_validator_error_is_parted_into_its_block_and_line_and_says_whether_a_person_has_looked():
    # invented, in the validator's own wording (accounting p. 398 and p. 338, 228.a): an error on a block a person noted and
    # corrected, one that names a line only, one on a block nobody looked at, one the parser could not place, and one with
    # no place at all
    errors = ['block b04 (line 26): HTML in prose (use the inline marks: [8]{.sup}, **bold**)',
              'line 86: attributes not parseable: Unexpected character whilst scanning quoted value: } at position 75',
              'block b13 (line 101): empty body (use status=unreadable)', 'block ? (line 12): a block without an id',
              'front matter: image_size missing']
    person = lambda block, verdict, at, **more: readings.PersonVerdict(reading_key='r1', block=block, verdict=verdict, given_at=at, **more)
    noted = person('b04', 'note', '2026-11-12T18:10:20+00:00', correction='A.')
    b04 = a_block('b04', 'list_item', [readings.Segment(kind='text', content='A. <table>')])
    b04.people = [noted]
    blocks = readings.with_corrections([b04, a_block('b13', 'table')])
    people = [noted, person('b13', 'accept', '2026-11-12T19:00:00+00:00', applies=False),
              person('b13', 'reject', '2026-11-12T19:30:00+00:00', archived=True)]
    placed = readings.errors_placed(errors, blocks, people)
    assert [(one.block, one.line, one.looked, one.looked_at, one.corrected) for one in placed] == [
        ('b04', 26, 'note', 'block', True), (None, 86, None, None, False), ('b13', 101, None, None, False),
        (None, 12, None, None, False), (None, None, None, None, False)]
    assert placed[0].message == 'HTML in prose (use the inline marks: [8]{.sup}, **bold**)' and placed[0].said == errors[0]
    assert placed[1].message.startswith('attributes not parseable') and placed[4].message == 'front matter: image_size missing'
    # a person's verdict on the page as a whole speaks for every error a block-level one does not
    page_wide = person(None, 'accept', '2026-11-12T20:00:00+00:00')
    looked = readings.errors_placed(errors[:3], blocks, [*people, page_wide])
    assert [(one.looked, one.looked_at) for one in looked] == [('note', 'block'), ('accept', 'page'), ('accept', 'page')]


def test_an_error_on_a_block_carries_the_blocks_lines_from_its_opening_fence_to_its_closing_one():
    # invented: the validator names the line a block opens on (26 in a real error of 18 Nov), while what it found may stand
    # lines below, so the raw view marks the whole block; an unclosed block runs to the line before the next one
    raw = '\n'.join(['---', 'work: x', '---', '::: {#b01 .paragraph}', 'one', 'two \\HL', ':::', '::: {#b02 .paragraph}',
                     'left open', '::: {#b03 .paragraph}', 'last', ':::'])
    assert readings.block_lines(raw, 4) == [4, 7]
    assert readings.block_lines(raw, 8) == [8, 9]
    assert readings.block_lines(raw, 10) == [10, 12]
    placed = readings.errors_placed(['block b01 (line 4): LaTeX command outside math: \\HL', 'line 2: attributes not parseable',
                                     'front matter: image_size missing'], [], [], raw)
    assert [one.lines for one in placed] == [[4, 7], None, None]
    # without the raw text no span is claimed
    assert readings.errors_placed(['block b01 (line 4): x'], [], [])[0].lines is None
    # page/1.4 names the fault's own line after the problem's name; an error without one keeps None
    exact = readings.errors_placed(['block b01 (line 4): LaTeX command outside math on line 6: \\HL',
                                    'block b01 (line 4): HTML in prose on line 5 (use the inline marks: [8]{.sup})',
                                    'line 2: attributes not parseable'], [], [], raw)
    assert [(one.line, one.lines, one.at_line) for one in exact] == [(4, [4, 7], 6), (4, [4, 7], 5), (2, None, None)]


@pytest.mark.readings
def test_a_page_gives_its_errors_parted_and_the_raw_lines_they_name(tmp_path):
    # invented over a free page's reading, so no re-read of a real page moves it (accounting p. 338, pinned here until 18 Nov,
    # got a valid direct reading that day): a line of text outside any block, which names a line alone, and a table block
    # with no box and no body, whose errors name the block and the line it opens on
    row = copy.deepcopy(next(row for row in kelly_rows() if row.get('text_file')))
    corpus = a_corpus(tmp_path, [row])
    stored = tmp_path / 'readings' / row['text_file']
    text = stored.read_bytes().decode('utf-8').rstrip('\n')
    stored.write_bytes(f'{text}\nwritten outside any block\n::: {{#b99 .table}}\n:::\n'.encode('utf-8'))
    page = corpus.page(KELLY, row['pdf_page'], 'Kelly')
    lines = page.raw.split('\n')
    outside, opens = lines.index('written outside any block') + 1, lines.index('::: {#b99 .table}') + 1
    placed = {(one.line, one.block) for one in page.reading.error_places}
    assert (outside, None) in placed and (opens, 'b99') in placed
    # b99's errors mark b99 whole in the raw view: from its opening fence to its closing one
    spans = {tuple(one.lines) for one in page.reading.error_places if one.block == 'b99'}
    assert spans == {(opens, opens + 1)} and lines[opens].strip() == ':::'
    assert [one.lines for one in page.reading.error_places if one.block is None and one.line] == [None]
    assert [one.said for one in page.reading.error_places] == page.reading.errors


@pytest.mark.readings
def test_a_state_to_look_at_counts_the_pages_the_core_serves_all_the_same(tmp_path):
    # the operator, 18 Nov: "issue 9" read as nine pages held back, where the core served all nine (findings on blocks never
    # quoted, 133.b). Invented: an issue served from its reading, and a page the provider blocked, served from its text layer
    served = copy.deepcopy(next(row for row in kelly_rows() if row.get('text_file') and row['check']['state'] == 'ok'))
    served.update(route="vision reading (claude-sonnet-5-5, page/1, validator page/1.4): the judge's findings lie on blocks never "
                        'quoted', route_level='noted', check={**served['check'], 'state': 'issue', 'reasons': ['judge: bad']})
    blocked = {**a_blocked_row(), 'pdf_page': served['pdf_page'] + 1}
    states = {count.value: count for count in a_corpus(tmp_path, [served, blocked]).summary(KELLY).states}
    assert (states['issue'].count, states['issue'].served) == (1, 1)
    assert (states['blocked'].count, states['blocked'].served) == (1, None)


@pytest.mark.readings
def test_a_chapters_count_to_look_at_carries_its_pages_and_a_fine_count_none():
    # 225.a on accounting, as tracked: every count a chapter opens has exactly as many pages as it counts, in the state it
    # counts them, and only the states a person should look at, or decided, open anything
    work = store.pages('free', 'openstax_principles_of_accounting_v1', 'Accounting')
    for unit in work.outline:
        counts = {count.value: count.count for count in unit.states}
        assert all(state.value in readings.OPENED_BY_A_COUNT and len(state.pages) == counts[state.value] for state in unit.state_pages)
        assert {state.value for state in unit.state_pages} == {value for value in counts if value in readings.OPENED_BY_A_COUNT}
        assert all(state.pages == sorted(state.pages) for state in unit.state_pages)
    # and each page a count opens is in the state the count names, as the page list says it (p. 360 of chapter 6, pinned
    # here as blocked until 18 Nov, was read by the second reader that night)
    listed = {row.pdf_page: row.listed_state for row in work.pages}
    opened = [(state.value, page) for unit in work.outline for state in unit.state_pages for page in state.pages]
    assert all(listed[page] == value for value, page in opened)
    assert any(not unit.state_pages for unit in work.outline if unit.level == 1)


def test_an_image_written_with_other_png_bytes_but_the_same_pixels_is_the_image_read(monkeypatch):
    # 18 Nov: in the Docker container every page said "image differs from the one read", its pixels identical
    import io

    from PIL import Image

    from backend.diagnostics import readings as view

    def png(colour, level):
        out = io.BytesIO()
        Image.new('RGB', (4, 3), colour).save(out, format='PNG', compress_level=level)
        return out.getvalue()

    sent = png('white', 9)

    asked = []

    class Store:
        def get_input(self, digest, suffix):
            asked.append(digest)
            if digest == 'gone':
                raise FileNotFoundError(digest)
            return sent

    monkeypatch.setattr(view, 'store_of', lambda knowledge_base: Store())
    monkeypatch.setattr(view, '_ALIKE', {})
    row = {'knowledge_base': 'free', 'image_sha256': 'kept'}
    assert png('white', 1) != sent and view.same_pixels(row, png('white', 1))
    assert not view.same_pixels(row, png('black', 9))
    assert not view.same_pixels({**row, 'image_sha256': 'gone'}, png('white', 1))
    # compared once per pair of images (line 1, 20 Nov: the page view compared them again on every call)
    asked.clear()
    assert view.same_pixels(row, png('white', 1)) and not view.same_pixels(row, png('black', 9))
    assert asked == []
