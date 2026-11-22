"""Every PDF page of a work in its page list, a page no reader has read in a state of its own (the operator's V1.b, 20 Nov), and
one line above the list saying how many are read and what serves the rest. Every work, page and PDF here is invented over
the free paper's export, so no licensed title or text can stand in a tracked file."""

import json

import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend.conversion.store import served_readings
from backend.diagnostics import readings, unread_pages
from backend.diagnostics.app import create_app
from backend.diagnostics.unread_pages import UnreadPart
from test_diagnostics_readings import KELLY, a_corpus, kelly_rows

LOCAL = 'http://127.0.0.1'


def a_pdf(path, pages: int, blank: tuple[int, ...] = ()) -> None:
    """An invented PDF: each page says its number in its text layer, except the blank ones, which have none (a scan)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    for number in range(1, pages + 1):
        page = document.new_page()
        if number not in blank:
            page.insert_text((72, 72), f'invented page {number}')
    document.save(path)
    document.close()


def a_work(tmp_path, read: int = 3, pages: int = 6, blank: tuple[int, ...] = (6,), knowledge_base: str = 'free', **fields):
    """Kelly's first `read` rows as a work's export, its PDF invented with `pages` pages."""
    rows = [{**row, 'knowledge_base': knowledge_base} for row in kelly_rows()[:read]]
    corpus = a_corpus(tmp_path, rows, knowledge_base=knowledge_base, **fields)
    a_pdf(tmp_path / corpus.work(KELLY)['pdf'], pages, blank)
    return corpus


@pytest.mark.readings
def test_the_warm_up_builds_every_work_s_pages_without_a_reading_ahead_of_its_list(tmp_path, monkeypatch):
    # line 1, 20 Nov: a work's first page list took 1.3 s in the container once everything shared was warm
    corpus = a_work(tmp_path)
    built = []
    real = unread_pages.unread_rows
    monkeypatch.setattr(unread_pages, 'unread_rows', lambda work, *args, **kwargs: built.append(work['source_id']) or real(
        work, *args, **kwargs))
    corpus.warm_unread()
    assert built == [KELLY]
    assert [page.pdf_page for page in corpus.pages('free', KELLY, 'Kelly').pages] == [1, 2, 3, 4, 5, 6]
    assert built == [KELLY]  # the list's first call finds them built


@pytest.mark.readings
def test_every_pdf_page_stands_one_without_a_reading_served_by_its_text_layer_where_it_has_text(tmp_path):
    answer = a_work(tmp_path).pages('free', KELLY, 'Kelly')
    assert [page.pdf_page for page in answer.pages] == [1, 2, 3, 4, 5, 6]
    read, unread = answer.pages[:3], answer.pages[3:]
    assert all(page.read and page.planned is None for page in read)
    assert all(not page.read and page.check.state == 'not_read' and page.listed_state == 'not_read' for page in unread)
    # a free PDF is read whole, so each of its pages is planned (the shelf's count)
    assert all(page.planned for page in unread)
    assert [page.route for page in unread] == [served_readings.TEXT_LAYER_WHY['unread']] * 2 + [unread_pages.NOTHING_ROUTE]
    assert [page.route_why for page in unread] == ["served from the PDF's text layer"] * 2 + ['nothing served: the page has no text layer']
    assert [page.from_fallback for page in unread] == [True, True, False]
    assert all(page.route_level == 'not read' and page.cost_usd is None and page.check.reasons == [] for page in unread)
    # counted as every page is: the summary, the states in their order, the routes and their levels
    assert answer.summary.pages == 6
    assert answer.summary.states[-1].value == 'not_read' and answer.summary.states[-1].count == 3
    assert answer.route_levels[-1].level == 'not read' and answer.route_levels[-1].pages == 3
    assert {route.route: route.pages for route in answer.routes if route.level == 'not read'} == {
        served_readings.TEXT_LAYER_WHY['unread']: 2, unread_pages.NOTHING_ROUTE: 1}
    assert answer.coverage.model_dump() == {
        'pdf_pages': 6, 'read': 3, 'planned': 3,
        'unread': [{'served_by': 'text layer', 'pages': 2}, {'served_by': 'nothing', 'pages': 1}],
        'said': "3 of 6 PDF pages read; of the other 3, 2 are served from the PDF's text layer; nothing serves 1; "
                'every one of them is planned'}


@pytest.mark.readings
def test_a_work_with_legacy_markdown_is_served_by_it_where_it_has_the_page_and_by_nothing_elsewhere(tmp_path):
    # the librarian's rule (`with_readings`): a legacy work never falls back to its PDF's text layer, though page 5 has text
    corpus = a_work(tmp_path, knowledge_base='licensed')
    file = corpus.work(KELLY)['file']
    corpus.legacy = lambda: {file: {1, 4}}  # as `licensed_readings` hands them in
    corpus.planned = lambda: {(file, 5), ('another.pdf', 4)}
    answer = corpus.pages('licensed', KELLY, 'Kelly')
    unread = answer.pages[3:]
    assert [(page.pdf_page, page.route, page.route_why, page.planned) for page in unread] == [
        (4, served_readings.LEGACY_WHY['unread'], "served from the IDE's Markdown", False),
        (5, unread_pages.NOTHING_ROUTE, "nothing served: the IDE's Markdown has no such page", True),
        (6, unread_pages.NOTHING_ROUTE, "nothing served: the IDE's Markdown has no such page", False)]
    assert answer.coverage.said == ("3 of 6 PDF pages read; of the other 3, 1 is served from the IDE's Markdown; nothing serves 2; "
                                    '1 of them is planned')


@pytest.mark.readings
def test_a_page_without_a_reading_lies_in_the_deepest_units_whose_pages_hold_it_and_each_chapter_counts_it(tmp_path):
    outline = [{'id': 'u001', 'level': 1, 'title': 'One', 'parent': None, 'first_page': 2, 'last_page': 6, 'indexed': True},
               {'id': 'u002', 'level': 2, 'title': 'One.a', 'parent': 'u001', 'first_page': 2, 'last_page': 4, 'indexed': True},
               {'id': 'u003', 'level': 2, 'title': 'One.b', 'parent': 'u001', 'first_page': 4, 'last_page': 6, 'indexed': True}]
    assert unread_pages.units_at(outline, 1) == []  # before the first unit
    assert unread_pages.units_at(outline, 3) == ['u002']
    assert unread_pages.units_at(outline, 4) == ['u002', 'u003']  # where one ends and the next begins
    assert unread_pages.units_at(None, 4) is None  # no outline exported
    rows = [{**row, 'units': units} for row, units in zip(kelly_rows()[:3], ([], ['u002'], ['u002']), strict=True)]
    corpus = a_corpus(tmp_path, rows, outline=outline)
    a_pdf(tmp_path / corpus.work(KELLY)['pdf'], 6)
    answer = corpus.pages('free', KELLY, 'Kelly')
    units = {unit.id: unit for unit in answer.outline}
    assert (units['u001'].pages, units['u002'].pages, units['u003'].pages) == (5, 3, 3)
    assert [(count.value, count.count) for count in units['u003'].states] == [('not_read', 3)]
    # the two read pages in whatever state the free export holds them today, the page without a reading last
    assert units['u002'].states[-1].model_dump(include={'value', 'count'}) == {'value': 'not_read', 'count': 1}
    assert sum(count.count for count in units['u002'].states) == 3


@pytest.mark.readings
def test_a_work_whose_pdf_is_not_on_this_machine_lists_its_read_pages_alone_without_a_coverage(tmp_path):
    corpus = a_corpus(tmp_path, kelly_rows()[:3])
    answer = corpus.pages('free', KELLY, 'Kelly')
    assert answer.coverage is None and [page.pdf_page for page in answer.pages] == [1, 2, 3]
    assert all(page.read for page in answer.pages)


@pytest.mark.readings
def test_the_pages_without_a_reading_are_built_once_per_state_of_the_export(tmp_path, monkeypatch):
    corpus = a_work(tmp_path)
    built = []
    real = unread_pages.unread_rows
    monkeypatch.setattr(unread_pages, 'unread_rows', lambda *args: built.append(1) or real(*args))
    corpus.pages('free', KELLY, 'Kelly')
    corpus.pages('free', KELLY, 'Kelly')
    assert len(built) == 1
    index = json.loads(corpus.index.read_text(encoding='utf-8'))
    index['pages'] = index['pages'][:2]
    corpus.index.write_text(json.dumps(index), encoding='utf-8')
    answer = corpus.pages('free', KELLY, 'Kelly')
    assert len(built) == 2 and answer.coverage.read == 2 and not answer.pages[2].read


def test_the_coverage_line_says_what_serves_the_unread_pages_in_one_line():
    said = unread_pages.coverage_said
    assert said(300, 300, [], 0) == '300 of 300 PDF pages read'
    assert said(300, 120, [UnreadPart(served_by='legacy markdown', pages=180)], 0) == (
        "120 of 300 PDF pages read; the other 180 are served from the IDE's Markdown")
    assert said(2, 1, [UnreadPart(served_by='text layer', pages=1)], 1) == (
        "1 of 2 PDF pages read; the other one is served from the PDF's text layer; it is planned")
    assert said(10, 2, [UnreadPart(served_by='nothing', pages=8)], 0) == '2 of 10 PDF pages read; nothing serves the other 8'
    assert said(1500, 100, [UnreadPart(served_by='legacy markdown', pages=1300), UnreadPart(served_by='text layer', pages=100)], 26) == (
        "100 of 1,500 PDF pages read; of the other 1,400, 1,300 are served from the IDE's Markdown and 100 from the PDF's text "
        'layer; 26 of them are planned')


@pytest.mark.readings
def test_the_api_counts_every_pdf_page_and_never_asks_for_a_licensed_one_under_public_only(monkeypatch):
    def refused():
        raise AssertionError('the licensed legacy pages were asked for under --public-only')

    monkeypatch.setattr(unread_pages, 'legacy_pages', refused)
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    answer = client.get(f'/api/free/works/{KELLY}/pages').json()
    pdf_pages = answer['coverage']['pdf_pages']
    assert len(answer['pages']) == pdf_pages == answer['summary']['pages']
    assert answer['coverage']['said'].startswith(f"{answer['coverage']['read']} of {pdf_pages} PDF pages read")
    # a page without a reading has no page of its own to open
    unread = [page['pdf_page'] for page in answer['pages'] if not page['read']]
    for pdf_page in unread[:1]:
        assert client.get(f'/api/free/works/{KELLY}/pages/{pdf_page}').status_code == 404


def test_the_state_and_level_of_a_page_without_a_reading_follow_every_other():
    assert readings.STATE_ORDER[-1] == unread_pages.UNREAD and readings.LEVEL_ORDER[-1] == unread_pages.UNREAD_LEVEL
    # the core's own words for a page without a reading, so a search hit and the page list name its route alike
    assert unread_pages.ROUTES['text layer'] == served_readings.route_of(None)


def a_free_catalog(tmp_path, shelf: dict | None = None) -> readings.Readings:
    """An invented free knowledge base whose export holds no page: its catalog names a PDF of two pages, the second without a
    text layer, and an HTML work, which is cut by section and never listed by page (8.a)."""
    export = tmp_path / 'export'
    export.mkdir()
    (export / 'index.json').write_text(json.dumps({'works': [], 'pages': []}), encoding='utf-8')
    entry = {'title': 'An Invented Specification', 'authors': 'A Committee', 'publisher': 'A Committee', 'year': 2024,
             'licence': 'CC BY-ND 4.0', 'shelf': 'trading_finance'}
    catalog = tmp_path / 'catalog.json'
    catalog.write_text(json.dumps({'sources': [
        {**entry, 'id': 'an_invented_spec', 'format': 'pdf', 'files': [{'path': 'corpus/raw/an_invented_spec.pdf'}]},
        {**entry, 'id': 'an_invented_site', 'format': 'html', 'files': [{'path': 'corpus/raw/an_invented_site.html'}]}]}),
        encoding='utf-8')
    a_pdf(tmp_path / 'corpus' / 'raw' / 'an_invented_spec.pdf', 2, blank=(2,))
    return readings.Readings(export=export, root=tmp_path, free_catalog=catalog, shelf=(lambda: shelf) if shelf else None)


def test_a_free_catalog_pdf_without_readings_lists_every_page_unread_served_from_its_text_layer(tmp_path):
    # its key in the search the shelf's, where the shelf names one
    store = a_free_catalog(tmp_path, {'works': [{'source_id': 'an_invented_spec', 'work': 'an-invented-spec'}]})
    # the PDF the export has no pages of, the HTML work not among them; the licensed store, without the free catalog, has none
    assert [entry['id'] for entry in store.free_entries()] == ['an_invented_spec']
    assert readings.Readings(export=tmp_path / 'export', root=tmp_path).free_entries() == []
    assert store.entry_work('an_invented_spec') == {'knowledge_base': 'free', 'source_id': 'an_invented_spec', 'work': 'an-invented-spec',
                                                     'title': 'An Invented Specification', 'file': 'an_invented_spec.pdf',
                                                     'pdf': 'corpus/raw/an_invented_spec.pdf', 'outline': None}
    assert store.entry_work('an_invented_site') is None
    # every page listed, none read, each served from its text layer where it has one
    pages = store.pages('free', 'an_invented_spec', 'An Invented Specification').pages
    assert [(page.pdf_page, page.read, page.route_why) for page in pages] == [
        (1, False, "served from the PDF's text layer"), (2, False, 'nothing served: the page has no text layer')]
    page = store.unread_page('an_invented_spec', 1, 'An Invented Specification')
    assert (page.read, page.route_why, page.check.state) == (False, "served from the PDF's text layer", unread_pages.UNREAD)


def test_the_free_plan_is_asked_once_per_state_of_the_corpus_cell_s_page_list_and_the_session_s(tmp_path, monkeypatch):
    # line 1's FIX note (22 Nov): the free plan is the core's, kept until either list it is built from is written again
    import dataclasses

    from backend.conversion.reading import reading_cells

    source, direct = tmp_path / 'pages.json', tmp_path / 'direct.json'
    source.write_text('{"pages": []}', encoding='utf-8')
    cell = dataclasses.replace(reading_cells.CORPUS_CELLS['FREE-SM'], page_source=source)
    monkeypatch.setitem(reading_cells.CORPUS_CELLS, 'FREE-SM', cell)
    monkeypatch.setitem(reading_cells.DIRECT_PAGES, 'free', direct)
    monkeypatch.setattr(unread_pages, '_FREE_PLANNED', {})
    asked = []
    monkeypatch.setattr(reading_cells, 'free_planned_pages', lambda: asked.append(1) or {('a_work.pdf', len(asked))})
    assert unread_pages.free_planned_pages() == unread_pages.free_planned_pages() == {('a_work.pdf', 1)}
    direct.write_text('{"pages": []}', encoding='utf-8')  # a session lists pages to read
    assert unread_pages.free_planned_pages() == {('a_work.pdf', 2)}


def test_a_free_pdf_no_plan_holds_has_no_page_planned_and_a_work_read_whole_keeps_its_pages_planned(tmp_path):
    # a NoDerivatives specification is never read (72.a); a work the corpus cell reads whole is planned page by page, so a
    # page of it without a reading stays planned
    whole = a_work(tmp_path / 'whole')
    file = whole.work(KELLY)['file']
    plan = {(file, number) for number in range(1, 7)}
    whole.planned = lambda: plan
    covered = whole.pages('free', KELLY, 'Kelly').coverage
    assert (covered.planned, covered.said.endswith('every one of them is planned')) == (3, True)
    (tmp_path / 'spec').mkdir()
    spec = a_free_catalog(tmp_path / 'spec')
    spec.planned = lambda: plan
    covered = spec.pages('free', 'an_invented_spec', 'An Invented Specification').coverage
    assert covered.planned == 0 and 'planned' not in covered.said
    assert not any(page.planned for page in spec.pages('free', 'an_invented_spec', 'An Invented Specification').pages)


@pytest.mark.corpus
@pytest.mark.readings
def test_no_page_of_a_fix_volume_is_planned_and_every_page_of_a_work_read_whole_is():
    # the real free data: the FIX specification is CC BY-ND and never read; OpenStax is read whole, so a page of it without a
    # reading would stay planned (today every page of it has one)
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    answer = client.get('/api/free/works/fix_latest_ep284_trade/pages').json()
    assert answer['coverage']['planned'] == 0 and 'planned' not in answer['coverage']['said']
    assert not any(page['planned'] for page in answer['pages'])
    planned = unread_pages.free_planned_pages()
    assert ('openstax_principles_of_finance_2e.pdf', 1) in planned
    assert not any(file.startswith('fix_') for file, _ in planned)


def test_which_pages_have_a_text_layer_is_kept_on_disk_by_the_pdf_s_stamp_and_asked_again_only_where_unknown(tmp_path,
                                                                                                               monkeypatch):
    # line 1's 1.d (22 Nov): a restart opens only a new or changed PDF
    pdf, kept = tmp_path / 'a_work.pdf', tmp_path / 'layers' / 'text_layers.json'
    a_pdf(pdf, 4, blank=(4,))
    assert unread_pages.TextLayers(kept).pages(pdf, 'a_work.pdf', {1}, needs_text=True) == (4, {2, 3})
    assert set(json.loads(kept.read_text(encoding='utf-8'))['pdfs']) == {'a_work.pdf'}
    real = unread_pages.pymupdf.open

    def refused(*args, **kwargs):
        raise AssertionError('a PDF whose pages are known was opened')

    monkeypatch.setattr(unread_pages.pymupdf, 'open', refused)
    again = unread_pages.TextLayers(kept)  # as after a restart
    assert again.pages(pdf, 'a_work.pdf', {1}, needs_text=True) == (4, {2, 3})
    assert again.pages(pdf, 'a_work.pdf', {1, 2}, needs_text=True) == (4, {3})
    assert again.pages(pdf, 'a_work.pdf', set(), needs_text=False) == (4, set())  # the count alone
    # a page no question asked before is asked of the PDF, and what was known stays
    monkeypatch.setattr(unread_pages.pymupdf, 'open', real)
    assert again.pages(pdf, 'a_work.pdf', set(), needs_text=True) == (4, {1, 2, 3})
    # a changed PDF is asked anew, its old answers dropped
    a_pdf(pdf, 5, blank=(1,))
    assert unread_pages.TextLayers(kept).pages(pdf, 'a_work.pdf', set(), needs_text=True) == (5, {2, 3, 4, 5})
    # a damaged file is built anew
    kept.write_text('{"pdfs": [', encoding='utf-8')
    assert unread_pages.TextLayers(kept).pages(pdf, 'a_work.pdf', set(), needs_text=True) == (5, {2, 3, 4, 5})


def test_a_work_s_pages_without_a_reading_are_the_same_from_kept_text_layers_as_from_the_pdf(tmp_path, monkeypatch):
    corpus = a_work(tmp_path)
    work, rows = corpus.work(KELLY), corpus.rows_of(KELLY)
    pdf = corpus.pdf_of(work)
    asked = unread_pages.unread_rows(work, rows, pdf, None, None)
    kept = tmp_path / 'text_layers.json'
    assert unread_pages.unread_rows(work, rows, pdf, None, None, layers=unread_pages.TextLayers(kept)) == asked

    def refused(*args, **kwargs):
        raise AssertionError('a PDF whose pages are known was opened')

    monkeypatch.setattr(unread_pages.pymupdf, 'open', refused)
    assert unread_pages.unread_rows(work, rows, pdf, None, None, layers=unread_pages.TextLayers(kept)) == asked


def test_only_the_start_command_s_app_keeps_the_text_layers_on_disk(monkeypatch):
    from backend.configuration import data_paths

    def refused():
        raise AssertionError('the licensed knowledge base was read')

    monkeypatch.setattr(readings, 'licensed_readings', refused)
    assert readings.knowledge_bases(public_only=True)['free'].text_layers is None
    kept = readings.knowledge_bases(public_only=True, keep_text_layers=True)['free'].text_layers
    assert kept.path == unread_pages.text_layers_file('free') and kept.path.is_relative_to(data_paths.FREE_WORKING)
    assert unread_pages.text_layers_file('licensed').is_relative_to(data_paths.LICENSED_WORKING)


def test_the_sources_list_opens_a_free_catalog_pdf_without_readings_and_its_pages(tmp_path, monkeypatch):
    from backend.diagnostics import sources

    store = a_free_catalog(tmp_path)
    monkeypatch.setattr(readings, 'knowledge_bases', lambda public_only=False, keep_text_layers=False: {'free': store})
    real = sources.works
    monkeypatch.setattr(sources, 'works', lambda catalog=None: real(catalog or store.free_catalog))
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    works = {work['id']: work for work in client.get('/api/works').json()}
    assert (works['an_invented_spec']['page_list'], works['an_invented_spec']['structure']) == (True, 'not read page by page')
    assert works['an_invented_site']['page_list'] is False
    listed = client.get('/api/free/works/an_invented_spec/pages').json()
    assert [(page['pdf_page'], page['read']) for page in listed['pages']] == [(1, False), (2, False)]
    assert client.get('/api/free/works/an_invented_spec/pages/1').json()['route_why'] == "served from the PDF's text layer"
