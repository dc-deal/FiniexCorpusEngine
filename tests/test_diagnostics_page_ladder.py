"""Every page of every work reachable, read or not, and each page's and section's own ladder (the operator's V2.a, 20 Nov: "the
work, then the page, then the image; the detail view says that nothing was read, nothing extracted"). Every work and PDF
here is invented over the free paper's export, so no licensed title or text can stand in a tracked file."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.diagnostics import page_ladder, unread_pages
from backend.diagnostics.app import create_app
from backend.search.page_index import Page
from test_diagnostics_readings import KELLY, kelly_rows
from test_diagnostics_unread_pages import a_work

LOCAL = 'http://127.0.0.1'


@pytest.mark.readings
def test_a_page_no_reader_has_read_has_a_view_its_own_image_and_every_page_as_its_neighbour(tmp_path):
    corpus = a_work(tmp_path)  # three pages read of six, the sixth without text
    page = corpus.page(KELLY, 4, 'Kelly')
    assert page is not None and not page.read and page.trace is None and page.reading is None and page.integrity == 'no reading'
    assert page.check.state == unread_pages.UNREAD and page.said == "Not read: served from the PDF's text layer."
    assert (page.previous_page, page.next_page) == (3, 5) and corpus.page(KELLY, 6, 'Kelly').next_page is None
    # the image is the PDF's own, as the librarian gives it: a born-digital page rendered, never the reader's
    image, data = corpus.image(KELLY, 4)
    assert image.available and image.kind == 'rendered' and image.format == 'png' and image.same_as_read is None
    assert data[:8] == b'\x89PNG\r\n\x1a\n' and 'render at 150 dpi' in image.said
    # a read page steps to the unread one beside it, as the list stands every page (V2.a)
    assert corpus.page(KELLY, 3, 'Kelly').next_page == 4
    # a page the PDF does not have has no view
    assert corpus.page(KELLY, 7, 'Kelly') is None and not corpus.image(KELLY, 7)[0].available


def a_page(text: str, searchable: bool = True, work: str = 'a-work', pdf: str | None = '4', page: str = '4') -> Page:
    return Page(work=work, page=page, line=1, text=text, path='invented.md', pdf=pdf, searchable=searchable)


def a_service(*pages: Page) -> SimpleNamespace:
    """A built search's pages, as the app's search holds them once built."""
    return SimpleNamespace(by_page={(page.work, page.page): page for page in pages})


def test_whether_the_search_holds_a_page_and_why_not_and_the_text_it_serves():
    served = page_ladder.PageRung(level='text served', reached=True, said='its reading')
    # not built: never waited for, said
    rung, text, why = page_ladder.keyword(None, served, built=False)
    assert (rung.reached, rung.said, text) == (None, page_ladder.NOT_BUILT, None)
    rung, text, why = page_ladder.keyword(a_page('prose ' * 60), served, built=True)
    assert (rung.reached, rung.said, text) == (True, 'in search (BM25)', 'prose ' * 60)
    rung, _, _ = page_ladder.keyword(a_page('1 2 3 4 5 6 7 8 9 10 ' * 30 + 'index', searchable=False), served, built=True)
    # the core's own words for why the ranking leaves it out (`page_index.structural_why`), one rule for the search and the view
    assert rung.said == 'not in search (BM25): mostly figures'
    nothing = page_ladder.PageRung(level='text served', reached=False, said='nothing served')
    rung, text, why = page_ladder.keyword(None, nothing, built=True)
    assert (rung.reached, why, text) == (False, 'nothing is served for it', None)
    # a page the core would rank, left out all the same, says so without a reason it does not carry
    rung, _, _ = page_ladder.keyword(a_page('prose ' * 60, searchable=False), served, built=True)
    assert rung.said == 'not in search (BM25): left out of the ranking'


@pytest.mark.readings
def test_a_page_climbs_its_five_levels_each_said(tmp_path, monkeypatch):
    corpus = a_work(tmp_path)
    pdf = corpus.pdf_of(corpus.work(KELLY))
    unread = corpus.any_row(KELLY, 4)
    monkeypatch.setattr(page_ladder, 'semantic_detail', lambda: {KELLY: {'pages': {4: 3}, 'sections': {}}})
    service = a_service(a_page('prose ' * 60, work='kelly-key'))
    ladder = page_ladder.page_ladder('free', KELLY, 4, unread, pdf, 'kelly-key', service, None)
    assert [(rung.level, rung.reached) for rung in ladder.rungs] == [
        ('text layer', True), ('text served', True), ('keyword search', True), ('semantic chunks', True), ('reading and check', False)]
    assert [rung.said for rung in ladder.rungs][3:] == ['3 chunks', 'no reading; planned']
    assert ladder.served_text == 'prose ' * 60
    # the blank sixth page: no text layer, nothing served, not in the search, no chunk
    blank = page_ladder.page_ladder('free', KELLY, 6, corpus.any_row(KELLY, 6), pdf, 'kelly-key', service, None)
    assert [(rung.reached, rung.said) for rung in blank.rungs][:4] == [
        (False, 'none: a scan, or a page without text'), (False, 'nothing served: the page has no text layer'),
        (False, 'not in search (BM25): nothing is served for it'), (False, 'no chunk of this page')]
    # a read page says its reading and its state; a licensed one is not vectorised yet, never 0 of N
    read = page_ladder.page_ladder('licensed', KELLY, 1, corpus.any_row(KELLY, 1), pdf, None, None, 'held back by the list')
    assert read.rungs[3].said == 'not vectorised yet (#8)' and read.rungs[3].reached is None
    assert read.rungs[4].said.startswith('reading ') and read.held == 'held back by the list'
    assert read.rungs[1].reached is True  # its reading, or the text layer in its place: either way text is served


def test_a_section_is_born_digital_its_chunks_its_own_and_a_licensed_one_not_vectorised():
    service = a_service(a_page('prose ' * 60, work='an-html-work', pdf=None, page='s3'))
    html = page_ladder.section_ladder('free', 's3', 2, 'an-html-work', service)
    assert [(rung.level, rung.reached, rung.said) for rung in html.rungs] == [
        ('text layer', None, 'not needed: born digital'), ('text served', True, 'its own text, parsed by section'),
        ('keyword search', True, 'in search (BM25)'), ('semantic chunks', True, '2 chunks'),
        ('reading and check', None, 'not needed: born digital')]
    epub = page_ladder.section_ladder('licensed', 's3', None, 'an-epub', None)
    assert epub.rungs[3].said == 'not vectorised yet (#8)' and epub.rungs[2].said == page_ladder.NOT_BUILT


@pytest.mark.readings
def test_the_page_route_carries_the_page_s_ladder_and_never_waits_for_the_search():
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    pdf_page = kelly_rows()[0]['pdf_page']
    answer = client.get(f'/api/free/works/{KELLY}/pages/{pdf_page}').json()
    assert [rung['level'] for rung in answer['ladder']['rungs']] == ['text layer', 'text served', 'keyword search', 'semantic chunks',
                                                                    'reading and check']
    # the tests never build the search: the level says so, and the served text waits for it
    assert answer['ladder']['rungs'][2]['said'] == page_ladder.NOT_BUILT and answer['ladder']['served_text'] is None
    image = client.get(f'/api/free/works/{KELLY}/pages/{pdf_page}/image.png')
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png'
    assert client.get(f'/api/free/works/{KELLY}/pages/9999').status_code == 404
