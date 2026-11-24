import json

import pytest

from backend.conversion.reading import reading_cells, rollout
from backend.conversion.store import reading_store

PLAIN = {'text_chars': 2000, 'figure_images': 0, 'drawn_glyphs': 0, 'drawn_clusters': 0, 'ruled_tables': 0, 'aligned_cells': 0,
         'math_lines': 0, 'mono_run': 0}


def test_rounds_grow_from_50_by_three_then_two_of_1000_and_stop_at_the_cap():
    assert rollout.round_sizes(6420) == [50, 150, 450, 1350, 1000, 1000, 2000, 420]
    assert rollout.round_sizes(120) == [50, 70]
    assert rollout.round_sizes(0) == []


class Manifests:
    def __init__(self, *cells):
        self.cells = cells

    def manifests(self):
        return [{'cells': [cell]} for cell in self.cells] + [{'cells': ['FREE-SM']}]


def a_stored_plan(tmp_path, monkeypatch, count=20):
    """A plan of `count` pages cut with rounds of 2 and 4, then at most 8, as it lay before a split."""
    monkeypatch.setattr(rollout, 'FOLDER', tmp_path)
    monkeypatch.setattr(rollout, 'ROUND_SIZES', (2, 4))
    monkeypatch.setattr(rollout, 'ROUND_CAP', 8)
    pages = [{'file': 'w.pdf', 'pdf_page': n, 'work': 'w', 'rule_classes': ['formula'], 'haiku_classes': [], 'difficulty': 50 - n}
             for n in range(1, count + 1)]
    rollout.write_plan(pages, *rollout.cut_rounds(pages))
    monkeypatch.setattr(rollout, 'ROUND_SIZES', (2, 4, 4, 4))  # the third round of 8 split in two


def test_a_resplit_cuts_the_rounds_not_yet_sent_and_keeps_the_sent_ones_byte_for_byte(tmp_path, monkeypatch):
    a_stored_plan(tmp_path, monkeypatch)
    before = {number: (tmp_path / f'round_{number:02d}.json').read_bytes() for number in (1, 2)}
    monkeypatch.setattr(reading_store, 'open_store', lambda mirror: Manifests('LIC-R01', 'LIC-R02'))
    result = rollout.resplit()
    assert [item['pages'] for item in result['rounds']] == [2, 4, 4, 4, 6]
    assert {number: (tmp_path / f'round_{number:02d}.json').read_bytes() for number in (1, 2)} == before
    assert sorted(path.name for path in tmp_path.glob('round_*.json')) == [f'round_{n:02d}.json' for n in range(1, 6)]
    assert [page['pdf_page'] for page in json.loads((tmp_path / 'round_05.json').read_text(encoding='utf-8'))['pages']] == list(range(15, 21))


def test_a_resplit_that_would_change_a_sent_round_writes_nothing(tmp_path, monkeypatch):
    a_stored_plan(tmp_path, monkeypatch)
    plan_before = (tmp_path / 'plan.json').read_bytes()
    monkeypatch.setattr(reading_store, 'open_store', lambda mirror: Manifests('LIC-R03'))
    with pytest.raises(SystemExit, match=r'\[3\]'):
        rollout.resplit()
    assert (tmp_path / 'plan.json').read_bytes() == plan_before and not (tmp_path / 'round_05.json').exists()


class Store:
    """The licensed store as `append` reads it: the page-class rows and Haiku's class checks."""
    def __init__(self, folder, rows, checks):
        (folder / 'rows.json').write_text(json.dumps({'rows': rows}), encoding='utf-8')
        self.folder, self.checks = folder, checks

    def path(self, *parts):
        return self.folder / 'rows.json'

    def readings(self):
        return self.checks


def rows_of(name, count, signals=None):
    return [{'file': f'{name}.pdf', 'pdf_page': n, 'signals': signals or {**PLAIN, 'math_lines': n}} for n in range(1, count + 1)]


def appending(tmp_path, monkeypatch, rows, checks=()):
    from backend.conversion.reading import page_classes

    a_stored_plan(tmp_path, monkeypatch)
    monkeypatch.setattr(reading_cells, 'may_send', lambda file: file != 'held.pdf')
    monkeypatch.setattr(page_classes, 'decide', lambda signals: {'formula'} if signals['math_lines'] else set())
    store = tmp_path / 'store'
    store.mkdir()
    monkeypatch.setattr(reading_store, 'open_store', lambda mirror: Store(store, rows, list(checks)))


def test_an_append_plans_only_the_new_works_after_the_last_round_and_leaves_every_round_file_as_it_was(tmp_path, monkeypatch):
    appending(tmp_path, monkeypatch, rows_of('w', 20) + rows_of('new', 11) + rows_of('held', 3))
    before = {path.name: path.read_bytes() for path in tmp_path.glob('round_*.json')}
    result = rollout.append()
    assert {name: (tmp_path / name).read_bytes() for name in before} == before
    assert [item['round'] for item in result['rounds']] == [1, 2, 3, 4, 5, 6]  # 20 pages were 2, 4, 8, 6; 11 new at most 8 a round
    assert [item['pages'] for item in result['rounds'][4:]] == [8, 3]
    new = json.loads((tmp_path / 'round_05.json').read_text(encoding='utf-8'))['pages']
    assert {page['file'] for page in new} == {'new.pdf'} and new[0]['pdf_page'] == 11  # hardest first
    assert result['pages'] == 31 and [page['round'] for page in result['order'][20:]] == [5] * 8 + [6] * 3


def test_an_append_waits_for_haiku_on_the_new_works_text_only_pages_and_writes_nothing(tmp_path, monkeypatch):
    appending(tmp_path, monkeypatch, rows_of('w', 20) + rows_of('new', 2) + rows_of('new2', 1, signals=PLAIN))
    plan_before = (tmp_path / 'plan.json').read_bytes()
    with pytest.raises(SystemExit, match='1 text-only pages'):
        rollout.append()
    assert (tmp_path / 'plan.json').read_bytes() == plan_before and not (tmp_path / 'round_05.json').exists()


def test_an_append_takes_haiku_s_structure_on_a_page_the_rules_call_text_only(tmp_path, monkeypatch):
    checks = [{'kind': 'classcheck', 'file': 'new.pdf', 'pdf_page': 1, 'answer': {'classes': ['table']}},
              {'kind': 'classcheck', 'file': 'new.pdf', 'pdf_page': 2, 'answer': {'classes': []}}]
    appending(tmp_path, monkeypatch, rows_of('w', 20) + rows_of('new', 2, signals=PLAIN), checks)
    result = rollout.append()
    assert [(page['pdf_page'], page['haiku_classes']) for page in result['order'][20:]] == [(1, ['table'])]


def test_an_append_with_nothing_new_writes_no_round(tmp_path, monkeypatch):
    appending(tmp_path, monkeypatch, rows_of('w', 20))
    result = rollout.append()
    assert len(result['rounds']) == 4 and not (tmp_path / 'round_05.json').exists()


def test_more_kinds_of_structure_and_stronger_signals_are_harder():
    plain_formula = rollout.difficulty({**PLAIN, 'math_lines': 1}, {'formula'})
    formula_and_code = rollout.difficulty({**PLAIN, 'math_lines': 1, 'mono_run': 6}, {'formula', 'code'})
    dense_formula = rollout.difficulty({**PLAIN, 'math_lines': 15}, {'formula'})
    assert formula_and_code > dense_formula > plain_formula


def test_the_hardest_come_first_and_equally_hard_works_take_turns():
    pages = [{'file': f'{work}.pdf', 'pdf_page': n, 'difficulty': difficulty}
             for work, n, difficulty in [('a', 1, 30), ('a', 2, 31), ('a', 3, 32), ('b', 1, 31), ('b', 2, 30), ('c', 1, 10)]]
    order = [(page['file'], page['pdf_page']) for page in rollout.ordered(pages)]
    assert order[-1] == ('c.pdf', 1)
    assert [name for name, _ in order[:4]] == ['a.pdf', 'b.pdf', 'a.pdf', 'b.pdf']


def test_the_reader_gets_the_rules_or_haiku_s_structure_never_a_scan_or_plain_prose():
    rows = [{'file': 'w.pdf', 'pdf_page': 1, 'signals': {**PLAIN, 'math_lines': 2}},
            {'file': 'w.pdf', 'pdf_page': 2, 'signals': PLAIN},
            {'file': 'w.pdf', 'pdf_page': 3, 'signals': PLAIN},
            {'file': 'w.pdf', 'pdf_page': 4, 'signals': {**PLAIN, 'text_chars': 10, 'figure_images': 1}}]
    decide = lambda signals: {'formula'} if signals['math_lines'] else set()
    chosen = rollout.select(rows, {('w.pdf', 3): ['table']}, decide, scan_chars=50)
    assert [(page['pdf_page'], page['rule_classes'], page['haiku_classes']) for page in chosen] == [(1, ['formula'], []), (3, [], ['table'])]


def test_each_round_file_becomes_a_cell_of_its_own(tmp_path, monkeypatch):
    monkeypatch.setattr(reading_cells, 'ROLLOUT', tmp_path)
    (tmp_path / 'round_01.json').write_text(json.dumps({'work_cards': {}, 'pages': []}), encoding='utf-8')
    (tmp_path / 'round_02.json').write_text(json.dumps({'work_cards': {}, 'pages': []}), encoding='utf-8')
    cells = reading_cells.rollout_cells()
    assert sorted(cells) == ['LIC-R01', 'LIC-R02'] and cells['LIC-R01'].model == reading_cells.SONNET
    assert {'LIC-R01', 'LIC-R02'} <= set(reading_cells.submittable())


def report_of(*rows, works=None) -> dict:
    pages = [{'key': f'k{n}', 'work': work, 'state': state, 'reasons': reasons, 'in_sample': sample, 'suspicious': False}
             for n, (work, state, reasons, sample) in enumerate(rows)]
    return {'pages': pages, 'works': works or {'w': {'stopped': False}}}


def test_a_round_passes_when_every_gate_holds():
    report = report_of(*[('w', 'ok', [], True)] * 19, ('w', 'issue', ['judge: bad'], True), ('w', 'blocked', ['errored'], False))
    result = rollout.gates_of(report, [{'estimate_usd': 1.0, 'cost_usd': 1.2}], previous_issue_share=0.1)
    assert result['passed'] and result['gates']['valid'] == {'passed': True, 'valid': 20, 'of': 20}


@pytest.mark.parametrize('rows, manifests, previous, failed', [
    ([('w', 'ok', [], True)] * 18 + [('w', 'issue', ['format: malformed'], False)] * 2, [{'estimate_usd': 1, 'cost_usd': 1}], None, 'valid'),
    ([('w', 'ok', [], True)] * 16 + [('w', 'issue', ['judge: bad'], True)] * 4, [{'estimate_usd': 1, 'cost_usd': 1}], None, 'judge_sample'),
    ([('w', 'ok', [], True)] * 20, [{'estimate_usd': 1, 'cost_usd': 1.4}], None, 'cost'),
    ([('w', 'ok', [], True)] * 19 + [('w', 'issue', ['judge: bad'], False)], [{'estimate_usd': 1, 'cost_usd': 1}], 0.01, 'issue_share'),
])
def test_each_gate_can_fail_on_its_own(rows, manifests, previous, failed):
    result = rollout.gates_of(report_of(*rows), manifests, previous)
    assert not result['passed'] and [name for name, gate in result['gates'].items() if not gate['passed']] == [failed]


def test_the_issue_share_may_rise_by_one_standard_error_and_no_further():
    # Round 5a's numbers (decision 109.a): 4.71 % of 913 unblocked pages after 4.47 % is noise; 5.26 % is not.
    def round_with(issues):
        rows = [('w', 'ok', [], True)] * 20 + [('w', 'ok', [], False)] * (893 - issues) + [('w', 'issue', ['judge: bad'], False)] * issues
        return rollout.gates_of(report_of(*rows), [{'estimate_usd': 1, 'cost_usd': 1}], 0.0447)['gates']['issue_share']
    assert round(rollout.issue_band(0.0447, 913), 4) == 0.0068
    assert round_with(43)['passed'] and round_with(43)['allowed'] == 0.0515
    assert not round_with(48)['passed']


def test_a_stopped_work_fails_the_judge_gate():
    report = report_of(('w', 'ok', [], True), works={'w': {'stopped': True}})
    assert rollout.gates_of(report, [], None)['gates']['judge_sample']['stopped_works'] == ['w']


def test_an_append_named_by_its_files_plans_only_those_new_works_and_the_others_wait(tmp_path, monkeypatch):
    from types import SimpleNamespace

    # the waiting work's text-only page has no Haiku check: it would stop an append of every new work, not this one
    appending(tmp_path, monkeypatch, rows_of('w', 20) + rows_of('new', 3) + rows_of('waiting', 2) + rows_of('later', 1, signals=PLAIN))
    result = rollout.append(SimpleNamespace(files=['new']))
    assert {page['file'] for page in result['order'][20:]} == {'new.pdf'} and result['pages'] == 23
    assert {page['file'] for page in json.loads((tmp_path / 'round_05.json').read_text(encoding='utf-8'))['pages']} == {'new.pdf'}


def test_an_append_without_files_plans_every_new_work_as_before(tmp_path, monkeypatch):
    from types import SimpleNamespace

    appending(tmp_path, monkeypatch, rows_of('w', 20) + rows_of('new', 3) + rows_of('waiting', 2))
    result = rollout.append(SimpleNamespace(files=None))
    assert {page['file'] for page in result['order'][20:]} == {'new.pdf', 'waiting.pdf'}


@pytest.mark.parametrize('names, refusal', [(['no_such_work'], 'not among'), (['w'], 'in a round already'),
                                            (['held'], 'not among')])
def test_an_append_named_by_an_unknown_held_or_planned_file_writes_nothing(tmp_path, monkeypatch, names, refusal):
    from types import SimpleNamespace

    appending(tmp_path, monkeypatch, rows_of('w', 20) + rows_of('new', 3))  # a held file is never measured: no row
    plan_before = (tmp_path / 'plan.json').read_bytes()
    with pytest.raises(SystemExit, match=refusal):
        rollout.append(SimpleNamespace(files=names))
    assert (tmp_path / 'plan.json').read_bytes() == plan_before and not (tmp_path / 'round_05.json').exists()


def test_an_append_takes_a_page_range_of_one_work_and_leaves_its_other_pages_for_later():
    # 24 Nov: a chapter of a long book read first, where its whole reading would pass the spend cap
    from backend.conversion.reading import rollout

    rows = [{'file': 'book.pdf', 'pdf_page': n} for n in range(1, 11)] + [{'file': 'other.pdf', 'pdf_page': 1}]
    order = [{'file': 'book.pdf', 'pdf_page': 4}]  # one page of the range is in a round already
    planned = rollout.rows_to_plan(rows, order, {'book.pdf'}, '3-6')
    assert [row['pdf_page'] for row in planned] == [3, 5, 6]
    with pytest.raises(SystemExit, match='one work'):
        rollout.rows_to_plan(rows, order, None, '3-6')
    with pytest.raises(SystemExit, match='FROM-TO'):
        rollout.rows_to_plan(rows, order, {'book.pdf'}, '6-3')
    with pytest.raises(SystemExit, match='no page'):
        rollout.rows_to_plan(rows, order, {'book.pdf'}, '4-4')
    # without a range, as before: a work a round holds any page of is not a new work
    assert [row['file'] for row in rollout.rows_to_plan(rows, order, None, None)] == ['other.pdf']
    with pytest.raises(SystemExit, match='in a round already'):
        rollout.rows_to_plan(rows, order, {'book.pdf'}, None)
