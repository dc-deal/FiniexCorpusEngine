"""How far each work and the corpus is refined (the operator's U1.a, 20 Nov): five levels, the same everywhere, counted in the
API from the shelf and the export's states. Every shelf here is invented, and every licensed work, so no licensed title,
count or text can stand in a tracked file."""

import json

import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend.configuration import data_paths
from backend.diagnostics import coverage_ladder, unread_pages
from backend.diagnostics.app import create_app
from backend.diagnostics.readings import StateCount
from backend.diagnostics.unread_pages import Coverage, UnreadPart
from backend.search import shelf
from test_diagnostics_readings import KELLY, a_corpus, kelly_rows

LOCAL = 'http://127.0.0.1'


def a_row(**fields) -> dict:
    """A shelf row as the core writes one, invented: a PDF of 100 pages."""
    return {'knowledge_base': 'free', 'work': 'a-work', 'title': 'A work', 'source_id': 'a_work', 'file': 'a_work.pdf', 'format': 'pdf',
            'pages': 100, 'planned': 100, 'read': 90, 'passed': 80, 'not_passed': {}, 'share_passed': 0.8,
            'served': {'pages': 96, 'searchable': 90, 'from_readings': 80, 'by_route': {'vision reading': 80, 'text layer': 16}},
            'unplaced': {}, 'held': None, 'not_served': None, 'semantic': {'chunks': 400, 'pages': 88}, **fields}


STATES = [StateCount(value='ok', count=50), StateCount(value='ok_unjudged', count=20), StateCount(value='decided_by_a_person', count=5),
          StateCount(value='issue', count=9, served=9), StateCount(value='not_read', count=10)]


def said(ladder) -> dict[str, tuple]:
    return {rung.level: (rung.count, rung.of, rung.said) for rung in ladder.rungs}


def test_a_pdf_climbs_five_levels_each_against_its_pages_the_checked_ones_those_that_stand():
    ladder = coverage_ladder.work_ladder(a_row(), STATES)
    assert ladder.unit == 'PDF pages' and ladder.whole == 100
    assert said(ladder) == {'text served': (96, 100, '96 of 100 PDF pages'), 'keyword search': (90, 100, '90 of 100 PDF pages'),
                            'semantic chunks': (88, 100, '400 chunks over 88 of 100 PDF pages'),
                            'read': (90, 100, '90 of 100 PDF pages, 80 passed'),
                            # what the judge passed and what a person settled: never an unjudged page, nor an issue
                            'checked': (55, 100, '55 of 100 PDF pages checked by the judge or a review')}
    assert all(rung.means for rung in ladder.rungs)
    # where a look is called for (C1.b): the issues beside the checked pages; nothing to warn of where text is served
    assert [(rung.level, rung.issues, rung.warn) for rung in ladder.rungs if rung.issues or rung.warn] == [('checked', 9, False)]
    nothing = coverage_ladder.work_ladder(a_row(served={'pages': 0, 'searchable': 0, 'by_route': {}}, read=0, passed=0), [])
    assert nothing.rungs[0].warn and not any(rung.warn for rung in nothing.rungs[1:])
    # every state of the read pages for the card, an issue's served tally kept, a page not read left to its own level
    assert [(state.value, state.count, state.served) for state in ladder.states] == [
        ('ok', 50, None), ('ok_unjudged', 20, None), ('decided_by_a_person', 5, None), ('issue', 9, 9)]
    assert ladder.by_route == {'vision reading': 80, 'text layer': 16} and ladder.planned == 100 and ladder.passed == 80


def test_a_level_not_measured_says_why_never_none_of_all():
    licensed = coverage_ladder.work_ladder(a_row(knowledge_base='licensed', semantic=None), [])
    assert said(licensed)['semantic chunks'] == (None, 100, 'not vectorised yet (#8)')
    free = coverage_ladder.work_ladder(a_row(semantic=None), [])
    assert said(free)['semantic chunks'] == (None, 100, 'not in the vector index on this machine')
    unread = coverage_ladder.work_ladder(a_row(read=0, passed=0), [])
    assert said(unread)['read'] == (0, 100, 'none of 100 PDF pages read yet')


def test_an_html_work_counts_its_sections_and_is_not_read_page_by_page():
    ladder = coverage_ladder.work_ladder(a_row(format='html', pages=None, read=None, passed=None,
                                               served={'pages': 1, 'searchable': 1, 'by_route': {}},
                                               semantic={'chunks': 20, 'pages': 0}), None)
    assert ladder.unit == 'sections'
    assert said(ladder) == {'text served': (1, 1, '1 of 1 section'), 'keyword search': (1, 1, '1 of 1 section'),
                            'semantic chunks': (1, 1, '20 chunks from its sections'),
                            'read': (None, 1, coverage_ladder.BY_HEADING), 'checked': (None, 1, coverage_ladder.BY_HEADING)}


def test_no_shelf_row_no_ladder_and_a_row_is_found_by_its_id_or_its_work_key():
    assert coverage_ladder.work_ladder(None, STATES) is None
    built = {'works': [a_row(), a_row(source_id='an_epub_file', work='a-legacy-key', format='epub')]}
    assert coverage_ladder.row_for(built, 'a_work')['source_id'] == 'a_work'
    assert coverage_ladder.row_for(built, 'a_catalog_id', 'a-legacy-key')['source_id'] == 'an_epub_file'
    assert coverage_ladder.row_for(None, 'a_work') is None


def test_a_work_page_says_its_reads_in_its_own_list_s_line():
    coverage = Coverage(pdf_pages=100, read=92, unread=[UnreadPart(served_by='text layer', pages=8)], planned=0,
                        said="92 of 100 PDF pages read; the other 8 are served from the PDF's text layer")
    ladder = coverage_ladder.with_coverage(coverage_ladder.work_ladder(a_row(), STATES), coverage)
    assert said(ladder)['read'] == (92, 100, coverage.said)
    assert coverage_ladder.with_coverage(None, coverage) is None


def test_the_corpus_sums_every_level_over_the_bases_a_base_without_vectors_named_apart():
    shelves = {'free': {'works': [a_row(), a_row(format='html', pages=None, served={'pages': 10, 'searchable': 9},
                                                  semantic={'chunks': 30, 'pages': 0}, read=None, passed=None)],
                        'built_at': '2026-11-20T10:00:00+00:00'},
               'licensed': {'works': [a_row(knowledge_base='licensed', semantic=None, pages=200, served={'pages': 150, 'searchable': 140})],
                            'built_at': '2026-11-20T11:00:00+00:00'}}
    ladder = coverage_ladder.corpus_ladder(shelves, {'free': 55, 'licensed': 7}, {'free': 2, 'licensed': 1})
    assert ladder.unit == 'pages and sections' and ladder.whole == 310
    rungs = {rung.level: rung for rung in ladder.rungs}
    assert (rungs['text served'].count, rungs['text served'].by_base) == (256, {'free': 106, 'licensed': 150})
    # the vectors over the free base alone, the licensed one named as not vectorised
    assert rungs['semantic chunks'].count == 98 and rungs['semantic chunks'].of == 110
    assert rungs['semantic chunks'].said == ('430 chunks over 98 of 110 pages and sections of the free base; the licensed base not '
                                             'vectorised yet (#8)')
    # the levels the Pages view lists: every page it has for the read ones, the checked states for the checked
    assert rungs['read'].pages_filter == {} and rungs['checked'].pages_filter == {'state': list(coverage_ladder.CHECKED)}
    assert rungs['text served'].pages_filter is None and rungs['checked'].count == 62 and rungs['checked'].issues == 3
    # read and checked against the PDF pages alone: an HTML work's sections are never read page by page
    assert (rungs['read'].of, rungs['read'].said) == (300, '180 of 300 PDF pages')
    assert ladder.built_at == '2026-11-20T11:00:00+00:00'
    assert coverage_ladder.corpus_ladder({}, {}) is None


def a_shelf(rows: list[dict]):
    return lambda name: {'works': rows, 'built_at': '2026-11-20T10:00:00+00:00'} if name == 'free' else None


@pytest.mark.readings
def test_every_work_and_the_overview_carry_their_ladder_and_the_licensed_shelf_is_never_read_under_public_only(monkeypatch):
    asked = []
    rows = [a_row(source_id=KELLY, pages=15, read=15, passed=12, served={'pages': 15, 'searchable': 14, 'by_route': {}},
                  semantic={'chunks': 100, 'pages': 14})]
    monkeypatch.setattr(shelf, 'load', lambda name: asked.append(name) or a_shelf(rows)(name))
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    kelly = next(work for work in client.get('/api/works').json() if work['id'] == KELLY)
    assert kelly['page_list'] and [rung['said'] for rung in kelly['ladder']['rungs']][:3] == [
        '15 of 15 PDF pages', '14 of 15 PDF pages', '100 chunks over 14 of 15 PDF pages']
    # a work the shelf has no row of has no ladder, and says how it is cut as before
    assert any(work['ladder'] is None for work in client.get('/api/works').json())
    # a work's page list: its read level in its own list's line, from the export it stands on
    pages = client.get(f'/api/free/works/{KELLY}/pages').json()
    read = next(rung for rung in pages['ladder']['rungs'] if rung['level'] == 'read')
    assert read['said'] == pages['coverage']['said'] and read['count'] == pages['coverage']['read']
    ladder = client.get('/api/overview').json()['headline']['ladder']
    assert ladder['whole'] == 15 and [rung['level'] for rung in ladder['rungs']] == list(coverage_ladder.LEVELS)
    assert set(asked) == {'free'}


@pytest.mark.readings
def test_a_file_the_librarian_serves_not_at_all_or_whole_says_so_on_every_page(tmp_path):
    corpus = a_corpus(tmp_path / 'a', [{**row, 'knowledge_base': 'licensed'} for row in kelly_rows()[:2]], knowledge_base='licensed')
    document = pymupdf.open()
    for number in range(4):
        document.new_page().insert_text((72, 72), f'invented page {number + 1}')
    (tmp_path / 'a' / corpus.work(KELLY)['pdf']).parent.mkdir(parents=True)
    document.save(tmp_path / 'a' / corpus.work(KELLY)['pdf'])
    corpus.not_served = lambda: {KELLY: 'held back by the provenance list (send: false): never sent to a provider'}
    unread = [page for page in corpus.pages('licensed', KELLY, 'Kelly').pages if not page.read]
    assert {page.route_why for page in unread} == {'nothing served: held back by the provenance list (send: false): never sent to a provider'}
    corpus.not_served = lambda: {KELLY: unread_pages.WHOLE_LEGACY}
    unread = [page for page in corpus.pages('licensed', KELLY, 'Kelly').pages if not page.read]
    assert {page.route_why for page in unread} == {unread_pages.WHOLE_LEGACY_SAID} and all(page.from_fallback for page in unread)


@pytest.mark.readings
def test_a_licensed_pdf_the_export_has_no_pages_of_opens_every_page_unread(tmp_path):
    # U1.a: every work opens; a catalog entry with a PDF lists each of its pages, none read
    corpus = a_corpus(tmp_path, [{**row, 'knowledge_base': 'licensed'} for row in kelly_rows()[:1]], knowledge_base='licensed')
    corpus.catalog = tmp_path / 'catalog.json'
    corpus.catalog.write_text(json.dumps({'sources': [{'id': 'an_unread_pdf', 'file': 'an_unread_pdf.pdf', 'title': 'An Unread PDF'}]}),
                              encoding='utf-8')
    pdf = tmp_path / data_paths.stored(data_paths.LICENSED_ARCHIVE / 'an_unread_pdf.pdf')
    pdf.parent.mkdir(parents=True)
    document = pymupdf.open()
    for _ in range(3):
        document.new_page().insert_text((72, 72), 'invented')
    document.save(pdf)
    answer = corpus.pages('licensed', 'an_unread_pdf', 'An Unread PDF')
    assert [page.pdf_page for page in answer.pages] == [1, 2, 3] and not any(page.read for page in answer.pages)
    assert answer.knowledge_base == 'licensed' and answer.coverage.said.startswith('0 of 3 PDF pages read')
    # an entry without a PDF has no page list
    assert corpus.entry_work('a_work_the_catalog_does_not_list') is None
