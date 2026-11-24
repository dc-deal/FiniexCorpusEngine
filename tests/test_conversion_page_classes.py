import json

import pymupdf
import pytest

from backend.conversion.reading import page_classes

PLAIN = {'text_chars': 2000, 'figure_images': 0, 'drawn_glyphs': 0, 'drawn_clusters': 0, 'ruled_tables': 0, 'aligned_cells': 0,
         'math_lines': 0, 'mono_run': 0}


def signals(**changes) -> dict:
    return {**PLAIN, **changes}


def test_a_page_of_plain_prose_needs_no_reader():
    assert page_classes.decide(signals()) == set()


@pytest.mark.parametrize('changes, expected', [
    ({'figure_images': 1}, {'figure'}),
    ({'drawn_glyphs': page_classes.DRAWN_GLYPHS}, {'formula'}),
    ({'math_lines': 1}, {'formula'}),
    ({'drawn_clusters': 1, 'ruled_tables': 1}, {'table'}),
    ({'drawn_clusters': 1}, {'figure'}),
    ({'mono_run': page_classes.CODE_LINES}, {'code'}),
])
def test_each_signal_adds_its_class(changes, expected):
    assert page_classes.decide(signals(**changes)) == expected


def test_one_monospaced_identifier_or_a_few_drawn_marks_stay_prose():
    assert page_classes.decide(signals(mono_run=page_classes.CODE_LINES - 1, drawn_glyphs=page_classes.DRAWN_GLYPHS - 1)) == set()


def test_tables_from_text_alignment_alone_are_off_by_default_and_can_be_tried():
    page = signals(aligned_cells=50)
    assert page_classes.decide(page) == set()
    assert page_classes.decide(page, {'aligned_tables': 36}) == {'table'}


def test_a_scan_is_its_own_route_and_never_a_reader_page():
    assert page_classes.decide(signals(text_chars=10, figure_images=1)) == set()


def test_the_score_counts_found_missed_and_false_alarms():
    rows = [{'truth': ['table'], 'signals': signals(drawn_clusters=1, ruled_tables=1)},
            {'truth': ['formula'], 'signals': signals()},
            {'truth': [], 'signals': signals(figure_images=1)},
            {'truth': [], 'signals': signals()}]
    assert page_classes.score(rows, {}) == {'recall': 0.5, 'missed': 1, 'false_alarms': 1, 'text_only': 2}


def test_measure_reads_a_real_page_and_finds_a_monospaced_listing(tmp_path):
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        page.insert_text((72, 72), 'An ordinary sentence of prose that is long enough to count as a text layer here.')
        for number in range(4):
            page.insert_text((72, 120 + 14 * number), f'x_{number} = compute({number})', fontname='cour')
        signals_found = page_classes.measure(page)
    assert signals_found['mono_run'] >= page_classes.CODE_LINES and signals_found['text_chars'] > page_classes.TEXT_LAYER_CHARS
    assert 'code' in page_classes.decide(signals_found)


def test_files_names_a_pdf_by_its_name_or_stem_and_none_means_every_file():
    rows = [{'file': 'a_book.pdf', 'pdf_page': 1}, {'file': 'b_paper.pdf', 'pdf_page': 1}]
    assert page_classes.files_named(rows, None) is None and page_classes.files_named(rows, []) is None
    assert page_classes.files_named(rows, ['a_book', 'b_paper.pdf']) == {'a_book.pdf', 'b_paper.pdf'}
    with pytest.raises(SystemExit, match=r"\['held_book'\] not among"):
        page_classes.files_named(rows, ['a_book', 'held_book'])


class ReportStore:
    """The licensed store as `sample_plan` reads and writes it."""

    def __init__(self, folder, rows):
        (folder / 'rows.json').write_text(json.dumps({'rows': rows}), encoding='utf-8')
        self.folder, self.reports = folder, {}

    def path(self, *parts):
        return self.folder / 'rows.json'

    def write_report(self, name, report):
        self.reports[name] = report


def test_a_cascade_plan_named_by_its_files_plans_only_their_text_only_pages_and_an_unknown_name_writes_nothing(tmp_path,
                                                                                                              monkeypatch):
    from types import SimpleNamespace

    from backend.conversion.reading import page_class_check, page_render
    from backend.conversion.store import reading_store

    rows = [{'file': name, 'pdf_page': 1, 'signals': PLAIN} for name in ('new_paper.pdf', 'waiting_book.pdf')]
    store = ReportStore(tmp_path, rows)
    monkeypatch.setattr(reading_store, 'open_store', lambda mirror: store)
    monkeypatch.setattr(pymupdf, 'open', lambda path: [object()])
    monkeypatch.setattr(page_render, 'render', lambda page, size: None)
    monkeypatch.setattr(page_class_check, 'entry_for', lambda **asked: {'file': asked['file_name'], 'estimate_usd': 0.001})
    page_classes.sample_plan(SimpleNamespace(plan='cascade', size=200, files=['new_paper']))
    assert [entry['file'] for entry in store.reports['page_classes_cascade_plan.json']['entries']] == ['new_paper.pdf']
    page_classes.sample_plan(SimpleNamespace(plan='cascade', size=200, files=None))  # without a name: every file, as before
    assert [entry['file'] for entry in store.reports['page_classes_cascade_plan.json']['entries']] == ['new_paper.pdf',
                                                                                                         'waiting_book.pdf']
    store.reports.clear()
    with pytest.raises(SystemExit, match='nothing written'):
        page_classes.sample_plan(SimpleNamespace(plan='cascade', size=200, files=['no_such_paper']))
    assert store.reports == {}


def test_estimate_with_files_measures_those_alone_and_keeps_every_other_file_s_rows(tmp_path, monkeypatch):
    # 24 Nov: a new book's intake, where measuring every PDF again takes two hours
    import argparse

    from backend.conversion.reading import reading_cells
    from backend.conversion.store import reading_store

    for name in ('new.pdf', 'old.pdf'):
        document = pymupdf.open()
        document.new_page().insert_text((72, 72), 'An invented page of prose for the measure. ' * 5)
        document.save(tmp_path / name)

    class Store:
        def path(self, *parts):
            return tmp_path.joinpath(*parts)

        def write_report(self, name, data):
            (tmp_path / 'reports').mkdir(exist_ok=True)
            (tmp_path / 'reports' / name).write_text(json.dumps(data), encoding='utf-8')

    monkeypatch.setattr(reading_cells, 'LICENSED_ARCHIVE', tmp_path)
    monkeypatch.setattr(reading_cells, 'may_send', lambda name: True)
    monkeypatch.setattr(reading_store, 'open_store', lambda name: Store())
    page_classes.estimate(argparse.Namespace(files=None, usd_per_page=0.01))  # every file, as before
    report = tmp_path / 'reports' / 'page_classes_licensed_rows.json'
    rows = json.loads(report.read_text(encoding='utf-8'))['rows']
    for row in rows:
        row['signals']['marked'] = row['file']  # a stored row that a new measure would not carry
    report.write_text(json.dumps({'rows': rows}), encoding='utf-8')
    page_classes.estimate(argparse.Namespace(files=['new'], usd_per_page=0.01))
    rows = {row['file']: row for row in json.loads(report.read_text(encoding='utf-8'))['rows']}
    assert rows['old.pdf']['signals']['marked'] == 'old.pdf' and 'marked' not in rows['new.pdf']['signals']
    with pytest.raises(SystemExit, match='not among'):
        page_classes.estimate(argparse.Namespace(files=['absent'], usd_per_page=0.01))
