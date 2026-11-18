import pytest

from backend.conversion.store import served_readings
from backend.conversion.contract.page_contract import parse
from test_conversion_page_contract import EXPECTED, P179, changed  # a real free page reading, used by the contract tests

FRONT = '---\ncontract: page/1\nwork: w\npdf_page: "2"\nimage_size: "1688x2184"\nprinted_label: "12"\nlabel_position: header\npage_kind: body\ncolumns: 1\nrotation: 0\nlanguage: en\n---\n\n'


def page(*blocks: str) -> str:
    return FRONT + '\n\n'.join(blocks) + '\n'


def test_a_reading_reads_as_its_words_formulas_tables_and_code_without_furniture():
    text = served_readings.quotable_text(parse(page(
        '::: {#b01 .page_header bbox="10 10 300 40"}\nChapter 3\n:::',
        '::: {#b02 .paragraph cont=prev bbox="10 50 900 120"}\nthe holding return \\(r = P_1 / P_0\\) ignores dividends.\n:::',
        '::: {#b03 .formula label="3.2" bbox="10 130 900 200"}\nR = \\frac{a}{b}\n:::',
        '::: {#b04 .table bbox="10 210 900 400"}\n<table><tr><td>Year</td><td>Return</td></tr><tr><td>1</td><td>5%</td></tr></table>\n:::',
        '::: {#b05 .description of=b04 form=prose bbox="10 410 900 450"}\nA table of returns by year.\n:::'), 'markdown'))
    assert 'Chapter 3' not in text and 'A table of returns' not in text
    assert 'the holding return \\(r = P_1 / P_0\\) ignores dividends.' in text
    assert '\\[ R = \\frac{a}{b} \\] (3.2)' in text and 'Year | Return\n1 | 5%' in text


def test_a_glossary_entry_reads_with_the_term_it_defines():
    # decision 190.a: the term stood in the attribute only, so 934 definitions reached the index without their words
    text = served_readings.quotable_text(parse(page(
        '::: {#b01 .glossary_entry term="accrual-basis accounting" bbox="10 10 900 60"}\nan accounting system in which revenue is '
        'recorded when earned\n:::',
        '::: {#b02 .glossary_entry term="debit" bbox="10 70 900 100"}\ndebit: a record on the left side\n:::'), 'markdown'))
    assert text == 'accrual-basis accounting: an accounting system in which revenue is recorded when earned\n\ndebit: a record on the left side'


def test_a_figure_s_text_keeps_its_lines_and_its_groups_apart():
    # decision 156.a: accounting p. 305's eleven T-accounts read "… Bal. 5,500 Common Stock 70,000 …" as one run
    text = served_readings.quotable_text(parse(page(
        '::: {#b01 .figure kind=diagram grouped=1 bbox="10 10 900 600"}\nAccounts Payable\nAug. 19 2,000\n7,500 Aug. 3\n'
        'Bal. 5,500\n\nCommon Stock\n70,000 Aug. 1\nBal. 70,000\n:::'), 'markdown'))
    assert text == 'Accounts Payable\nAug. 19 2,000\n7,500 Aug. 3\nBal. 5,500\n\nCommon Stock\n70,000 Aug. 1\nBal. 70,000'


def test_the_reader_s_continuation_mark_is_read_from_the_first_quotable_block():
    marked = parse(page('::: {#b01 .page_number bbox="10 10 50 40"}\n12\n:::',
                        '::: {#b02 .paragraph cont=prev bbox="10 50 900 120"}\nof the period.\n:::'), 'markdown')
    plain = parse(page('::: {#b01 .paragraph bbox="10 50 900 120"}\nA new paragraph.\n:::'), 'markdown')
    assert served_readings.continues_previous(marked) and not served_readings.continues_previous(plain)


def test_a_real_reading_keeps_its_formulas_as_latex():
    text = served_readings.quotable_text(parse(P179, 'markdown', EXPECTED))
    assert '\\(' in text or '\\[' in text


@pytest.mark.parametrize('row, served', [
    ({'text_file': 'w/p1.md', 'class_now': 'ok', 'check': {'state': 'ok_unjudged'}, 'model': 'm', 'contract': 'page/1',
      'validator': 'page/1.1'}, True),
    ({'text_file': 'w/p1.md', 'class_now': 'ok', 'check': {'state': 'issue'}}, False),
    ({'text_file': 'w/p1.md', 'class_now': 'refused'}, False),
])
def test_a_route_says_whether_the_reading_is_served_and_why_not(row, served):
    route = served_readings.route_of(row)
    assert route.startswith(served_readings.READING_ROUTE) == served
    assert served or route in served_readings.TEXT_LAYER_WHY.values()


def test_the_readings_fingerprint_follows_a_page_s_text(monkeypatch):
    rows = [{'file': 'a.pdf', 'pdf_page': 1, 'text_file': 'w/p1.md', 'class_now': 'ok', 'check': None, 'model': 'm',
             'contract': 'page/1', 'validator': 'page/1.1', 'text_sha256': 'x'}]
    monkeypatch.setattr(served_readings, 'export_rows', lambda name=None: rows)
    before = served_readings.readings_fingerprint('a.pdf')
    rows[0]['text_sha256'] = 'y'
    assert served_readings.readings_fingerprint('a.pdf') != before


def test_a_second_reader_s_reading_says_so_and_why_in_its_route():
    row = {'text_file': 'w/p1.md', 'class_now': 'ok', 'check': {'state': 'ok'}, 'model': 'openai/gpt-6.1-terra',
           'contract': 'page/1', 'validator': 'page/1.1', 'deviation': 'anthropic blocked the page (content filter)'}
    assert served_readings.route_of(row) == ('vision reading, second reader (openai/gpt-6.1-terra, page/1, validator page/1.1): '
                                             'anthropic blocked the page (content filter)')


def an_issue(*classes) -> dict:
    """An export row the judge found bad, its findings on blocks of these classes (None: the page as a whole)."""
    return {'text_file': 'w/p0001.md', 'class_now': 'ok', 'model': 'claude-sonnet-5-5', 'contract': 'page/1', 'validator': 'page/1.2',
            'check': {'state': 'issue', 'verdict': {'findings': [{'block': 'b01', 'kind': 'invented', 'block_class': cls}
                                                                for cls in classes]}}}


def test_a_reading_the_judge_faulted_only_on_blocks_never_quoted_is_served_and_its_route_says_so():
    row = an_issue('description', 'page_footer')
    assert served_readings.text_layer_why(row) is None
    assert served_readings.route_of(row).endswith("the judge's findings lie on blocks never quoted")


@pytest.mark.parametrize('classes', [('description', 'paragraph'), (None,), ()])
def test_a_finding_on_a_quoted_block_on_the_whole_page_or_no_finding_keeps_the_text_layer(classes):
    assert served_readings.text_layer_why(an_issue(*classes)) == 'issue'


def test_a_stopped_work_stays_stopped_whatever_its_findings():
    row = an_issue('description')
    row['check']['state'] = 'stopped'
    assert served_readings.text_layer_why(row) == 'stopped'


def a_person(verdict: str, applies: bool = True) -> dict:
    return {'verdict': verdict, 'applies': applies, 'reason': 'judge_misread_name',
            'reason_text': 'the judge took a name or a term for a wrong word'}


def test_a_person_s_accept_serves_the_reading_over_the_judge_and_a_reject_its_text_layer():
    accepted = {**an_issue('list_item'), 'human': [a_person('accept')]}
    assert served_readings.text_layer_why(accepted) is None
    assert served_readings.route_of(accepted).endswith('a person accepted the reading: the judge took a name or a term for a wrong word')
    rejected = {**an_issue(), 'check': {'state': 'ok'}, 'human': [a_person('reject')]}
    assert served_readings.route_of(rejected) == 'text layer: a person rejected the reading'


def test_a_session_s_verdict_on_the_operator_s_delegation_is_never_called_a_person_s():
    """The operator, 18 Nov: "a person is always manual". A delegated review decides as a person's verdict does, and says
    what it is; an export written before carries the giver alone."""
    delegated = {**a_person('accept'), 'given_by': 'claude-opus-5-5 session, delegated by the operator (17 Nov)'}
    accepted = {**an_issue('list_item'), 'human': [delegated]}
    assert served_readings.text_layer_why(accepted) is None
    assert served_readings.route_of(accepted).endswith(
        'an automated review (delegated by the operator) accepted the reading: the judge took a name or a term for a wrong word')
    rejected = {**an_issue(), 'check': {'state': 'ok'}, 'human': [{**delegated, 'verdict': 'reject', 'by_a_person': False}]}
    assert served_readings.text_layer_why(rejected) == 'rejected_by_review'
    assert served_readings.route_of(rejected) == 'text layer: an automated review (delegated by the operator) rejected the reading'
    by_the_operator = {**an_issue('list_item'), 'human': [{**a_person('accept'), 'given_by': 'maintainer', 'by_a_person': True}]}
    assert ': a person accepted the reading' in served_readings.route_of(by_the_operator)


def test_an_accept_for_another_reason_names_the_person_s_note_in_the_route():
    # "another reason, said in the note" told a reader of the route nothing (the operator, 10 Nov, accounting p. 305)
    other = {**a_person('accept'), 'reason': 'other', 'reason_text': 'another reason, said in the note',
             'note': 'the judge miscounted: the figure holds eleven T-accounts'}
    row = {**an_issue('description'), 'human': [other]}
    assert served_readings.route_of(row).endswith('a person accepted the reading: the judge miscounted: the figure holds eleven T-accounts')


def test_a_note_or_a_verdict_on_an_earlier_reading_changes_nothing_and_the_latest_verdict_stands():
    assert served_readings.text_layer_why({**an_issue('list_item'), 'human': [a_person('note')]}) == 'issue'
    assert served_readings.text_layer_why({**an_issue('list_item'), 'human': [a_person('accept', applies=False)]}) == 'issue'
    assert served_readings.text_layer_why({**an_issue('list_item'), 'human': [a_person('accept'), a_person('reject')]}) == 'rejected'


def test_a_reading_no_check_has_reached_is_never_served():
    row = {'text_file': 'w/p1.md', 'class_now': 'ok', 'check': None, 'model': 'mistralai/mistral-large-4-0', 'contract': 'page/1',
           'validator': 'page/1.2', 'deviation': 'anthropic blocked the page (content filter)'}
    assert served_readings.route_of(row) == 'text layer: the reading has not been checked yet'


def test_a_reading_served_because_the_judge_s_findings_were_void_says_so():
    row = {**an_issue('list_item'), 'check': {'state': 'ok', 'verdict': {'verdict': 'bad', 'outcome': 'ok', 'void': 1, 'findings': []}}}
    assert served_readings.route_of(row).endswith("the judge's findings contradict their own evidence")


def test_a_route_says_how_good_it_is_checked_noted_or_a_fallback():
    plain = {'text_file': 'w/p1.md', 'class_now': 'ok', 'check': {'state': 'ok'}, 'model': 'm', 'contract': 'page/1',
             'validator': 'page/1.2'}
    assert served_readings.route_level(plain) == 'checked'
    assert served_readings.route_level(an_issue('description')) == 'noted'  # a finding on a block never quoted
    assert served_readings.route_level({**plain, 'deviation': 'anthropic blocked the page (content filter)'}) == 'noted'
    assert served_readings.route_level(an_issue('paragraph')) == 'fallback'
    assert set(served_readings.ROUTE_LEVELS) == {'checked', 'noted', 'fallback'}


def test_a_reading_a_person_reset_is_never_served():
    row = {'text_file': 'w/p1.md', 'class_now': 'ok', 'check': {'state': 'ok'}, 'model': 'm', 'contract': 'page/1',
           'validator': 'page/1.2', 'reset': {'reason': 'read it again', 'given_by': 'maintainer', 'given_at': '2026-11-10'}}
    assert served_readings.route_of(row) == 'text layer: a person reset the page; a new reading is due'


def test_a_footnote_marker_and_a_superscript_never_run_into_the_number_before_them():
    # decision 205.a: "1947–2020[2]{.fn}" read "1947–20202" in the index, "12.5[2]{.sup}" read "12.52"
    reading = parse(page('::: {#b01 .paragraph bbox="1 1 9 9"}\nConsumer Price Index, 1947–2020[2]{.fn}; the variance is '
                         '12.5[2]{.sup}, ranked 2[nd]{.sup}, H[2]{.sub}O.\n:::',
                         '::: {#b02 .table kind=data bbox="1 10 9 19"}\n<table><tbody><tr><td>22%[*]{.fn}</td></tr></tbody></table>\n:::'),
                    'markdown')
    assert reading.valid, reading.errors
    assert [kind for kind, _ in reading.blocks[0].inline['segments'] if kind != 'text'] == ['fn', 'sup', 'sup', 'sub']
    assert served_readings.quotable_text(reading).split('\n\n') == [
        'Consumer Price Index, 1947–2020[2]; the variance is 12.5^2, ranked 2nd, H2O.', '22%[*]']
