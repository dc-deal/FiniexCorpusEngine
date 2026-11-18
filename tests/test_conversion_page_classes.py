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
