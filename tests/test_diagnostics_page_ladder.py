"""Every page of every work reachable, read or not, and each page's and section's own ladder (the operator's V2.a, 20 Nov: "the
work, then the page, then the image; the detail view says that nothing was read, nothing extracted"). Every work and PDF
here is invented over the free paper's export, so no licensed title or text can stand in a tracked file."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.diagnostics import coverage_ladder, page_ladder, unread_pages
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
    # each base's index, invented: the free one by the work's source id, the private one (#8) by its work key
    detail = {'free': {KELLY: {'pages': {4: 3}, 'sections': {}}}, 'licensed': {'kelly-key': {'pages': {1: 2}, 'sections': {}}}}
    monkeypatch.setattr(page_ladder, 'semantic_detail', lambda knowledge_base: detail[knowledge_base])
    monkeypatch.setattr(coverage_ladder, 'licensed_index_built', lambda: True)
    service = a_service(a_page('prose ' * 60, work='kelly-key'))
    ladder = page_ladder.page_ladder('free', KELLY, 4, unread, pdf, 'kelly-key', service, None)
    assert [(rung.level, rung.reached) for rung in ladder.rungs] == [
        ('text layer', True), ('text served', True), ('keyword search', True), ('semantic search', True), ('reading and check', False)]
    assert [rung.said for rung in ladder.rungs][3:] == ['3 chunks', 'no reading; planned']
    assert ladder.served_text == 'prose ' * 60
    # the blank sixth page: no text layer, nothing served, not in the search, no chunk
    blank = page_ladder.page_ladder('free', KELLY, 6, corpus.any_row(KELLY, 6), pdf, 'kelly-key', service, None)
    assert [(rung.reached, rung.said) for rung in blank.rungs][:4] == [
        (False, 'none: a scan, or a page without text'), (False, 'nothing served: the page has no text layer'),
        (False, 'not in search (BM25): nothing is served for it'), (False, 'no chunk of this page')]
    # a read page says its reading and its state; a licensed one its chunks in the private index, by its work key (#8)
    read = page_ladder.page_ladder('licensed', KELLY, 1, corpus.any_row(KELLY, 1), pdf, 'kelly-key', None, None)
    assert (read.rungs[3].said, read.rungs[3].reached) == ('2 chunks', True)
    assert read.rungs[4].said.startswith('reading ') and read.rungs[1].reached is True
    # a work held back is never embedded; a machine without the private index says so, never 0 of N
    held = page_ladder.page_ladder('licensed', KELLY, 1, corpus.any_row(KELLY, 1), pdf, 'a-held-key', None, 'held back by the list')
    assert (held.rungs[3].said, held.rungs[3].reached, held.held) == ('held back: never embedded', None, 'held back by the list')
    # a clone: no private index, so nothing in it to find
    monkeypatch.setattr(coverage_ladder, 'licensed_index_built', lambda: False)
    monkeypatch.setattr(page_ladder, 'semantic_detail', lambda knowledge_base: {})
    clone = page_ladder.page_ladder('licensed', KELLY, 1, corpus.any_row(KELLY, 1), pdf, 'kelly-key', None, None)
    assert (clone.rungs[3].said, clone.rungs[3].reached) == ('not vectorised yet (#8)', None)


def test_a_page_s_text_layer_is_counted_once_and_its_pdf_opened_once_for_all_its_pages(tmp_path, monkeypatch):
    # line 1, 20 Nov: each page's view opened the whole PDF again (0.37 s through the container's mount) to count one page.
    # Invented: a PDF of three pages, the second blank. Counted, never timed
    import os

    import pymupdf

    pdf = tmp_path / 'invented.pdf'
    document = pymupdf.open()
    for text in ('one', '', 'three'):
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    document.save(pdf)
    document.close()
    opened = []
    real = pymupdf.open
    monkeypatch.setattr(pymupdf, 'open', lambda *args, **kwargs: opened.append(1) or real(*args, **kwargs))
    page_ladder.characters_of.cache_clear()
    said = [page_ladder.text_layer(pdf, page).said for page in (1, 2, 3, 1, 9)]
    assert said == ['3 characters', 'none: a scan, or a page without text', '5 characters', '3 characters', 'the PDF has 3 pages']
    assert len(opened) == 1
    # the file rewritten: its stamp moved on, so it is opened and counted again
    found = pdf.stat()
    os.utime(pdf, ns=(found.st_atime_ns, found.st_mtime_ns + 1_000_000_000))
    assert page_ladder.text_layer(pdf, 1).said == '3 characters' and len(opened) == 2


def test_a_section_is_born_digital_its_chunks_its_own_and_a_licensed_one_s_in_the_private_index(monkeypatch):
    # the private index (#8), invented: an EPUB section by `<work key>:<ordinal>`, its position from 0 in four figures
    monkeypatch.setattr(page_ladder, 'semantic_detail', lambda knowledge_base: {'an-epub': {'pages': {}, 'sections': {'an-epub:0002': 4}}})
    monkeypatch.setattr(coverage_ladder, 'licensed_index_built', lambda: True)
    service = a_service(a_page('prose ' * 60, work='an-html-work', pdf=None, page='s3'))
    html = page_ladder.section_ladder('free', 's3', 2, 'an-html-work', service)
    assert [(rung.level, rung.reached, rung.said) for rung in html.rungs] == [
        ('text layer', None, 'not needed: born digital'), ('text served', True, 'its own text, parsed by section'),
        ('keyword search', True, 'in search (BM25)'), ('semantic search', True, '2 chunks'),
        ('reading and check', None, 'not needed: born digital')]
    epub = page_ladder.section_ladder('licensed', 's3', None, 'an-epub', None)
    assert epub.rungs[3].said == '4 chunks' and epub.rungs[2].said == page_ladder.NOT_BUILT
    assert page_ladder.section_ladder('licensed', 's9', None, 'an-epub', None).rungs[3].said == 'no chunk of this section'
    monkeypatch.setattr(coverage_ladder, 'licensed_index_built', lambda: False)
    assert page_ladder.section_ladder('licensed', 's3', None, 'a-held-epub', None, 'held').rungs[3].said == 'not vectorised yet (#8)'


@pytest.mark.readings
def test_the_page_route_carries_the_page_s_ladder_and_never_waits_for_the_search():
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    pdf_page = kelly_rows()[0]['pdf_page']
    answer = client.get(f'/api/free/works/{KELLY}/pages/{pdf_page}').json()
    assert [rung['level'] for rung in answer['ladder']['rungs']] == ['text layer', 'text served', 'keyword search', 'semantic search',
                                                                    'reading and check']
    # the tests never build the search: the level says so, and the served text waits for it
    assert answer['ladder']['rungs'][2]['said'] == page_ladder.NOT_BUILT and answer['ladder']['served_text'] is None
    image = client.get(f'/api/free/works/{KELLY}/pages/{pdf_page}/image.png')
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png'
    assert client.get(f'/api/free/works/{KELLY}/pages/9999').status_code == 404


def test_a_kept_edition_s_page_and_section_say_kept_at_their_keyword_level_their_text_shown_all_the_same():
    # line 1, 20 Nov (E1.a): a kept edition's pages and sections are never searched, built or not, as its record says
    served = page_ladder.PageRung(level='text served', reached=True, said='its own text')
    rung, text, _ = page_ladder.keyword(a_page('prose ' * 60, searchable=False), served, True, '2nd edition, 2001')
    assert (rung.said, rung.reached, text) == ('kept: not searched; the 2nd edition, 2001 is served', False, 'prose ' * 60)
    assert page_ladder.keyword(None, served, False, '2nd edition, 2001')[0].said == 'kept: not searched; the 2nd edition, 2001 is served'
    section = page_ladder.section_ladder('free', 's1', 3, 'a-work', None, None, '2017 edition')
    assert [rung.said for rung in section.rungs][1:4] == ['its own text, parsed by section',
                                                          'kept: not searched; the 2017 edition is served', '3 chunks']
    # which work is kept, from its base's shelf: the served edition in a sentence's words; None for any other work
    family = {'serves': 'a_served', 'chosen': '2026-11-02', 'why': 'invented', 'editions': [
        {'key': 'a_served', 'label': '2nd edition, 2001', 'served': True}, {'key': 'a_kept', 'label': '2017', 'served': False}]}
    store = SimpleNamespace(shelf_data=lambda: {'works': [{'source_id': 'a_served', 'editions': family},
                                                          {'source_id': 'a_kept', 'editions': family, 'kept_for': 'a_served'}]})
    assert (page_ladder.kept_of(store, 'a_kept'), page_ladder.kept_of(store, 'a_served'), page_ladder.kept_of(store, 'other')) == (
        '2nd edition, 2001', None, None)
