"""A book's companion code in the view (issue #12, the operator's 3.a, 23 Nov): its folders and files with the core's catalog,
one file numbered, the code work folded into its book's row in Sources, and the Librarian page's code answers. Every file,
unit and title here is invented, so no licensed code or title can stand in a tracked file; the service is the core's own,
built over the invented pages, and no test calls the real librarian or builds the real index."""

import json
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from backend.diagnostics import code_works, epub_works, librarian, readings, search_hits
from backend.diagnostics.app import create_app
from backend.ingestion import code_catalog
from backend.search import code_pages, page_index, search_server

LOCAL = 'http://127.0.0.1'
CODE, BOOK = 'an_invented_code', 'an_invented_book'
FILES = {
    'Functions/Invented Average.txt': '{ Invented Average, from an invented book }\ninputs: Price(Close), Length(10);\n'
                                      'InventedAverage = Average(Price, Length);\n',
    'Indicators/Invented Band (I).txt': 'inputs: Length(20);\nvars: Middle(0);\nMiddle = InventedAverage(Close, Length);\n'
                                        'Plot1(Middle, "Middle");\n',
    'Strategies/Invented Cross (S).txt': 'if Close crosses over InventedAverage(Close, 10) then Buy next bar at market;\n',
}
UNITS = {
    'Functions/Invented Average.txt': {'name': 'Invented Average', 'unit': 'function', 'category': 'trend',
                                       'aliases': ['an invented mean'], 'summary': 'An invented sentence about an average.',
                                       'summary_is': 'derived (an invented model)',
                                       'inputs': [{'name': 'Price', 'default': 'Close'}, {'name': 'Length', 'default': '10'}],
                                       'source_named': 'Invented Average, from an invented book'},
    'Indicators/Invented Band (I).txt': {'name': 'Invented Band', 'unit': 'indicator', 'category': 'volatility', 'aliases': [],
                                         'summary': 'An invented sentence about a band.',
                                         'summary_is': 'derived (an invented model)',
                                         'inputs': [{'name': 'Length', 'default': '20'}], 'source_named': None},
}


def an_invented_service(tmp_path, catalogued: bool = True) -> search_server.SearchService:
    """The core's service over an invented book of one page and its invented companion code of three files, with the core's
    catalog of two of them in a file of its own."""
    folder = tmp_path / CODE
    for label, text in FILES.items():
        (folder / label).parent.mkdir(parents=True, exist_ok=True)
        (folder / label).write_text(text, encoding='utf-8')
    pages = code_pages.code_pages(CODE, folder)
    pages.append(page_index.Page(BOOK, '1', 1, 'An invented page of an invented book.', 'an_invented_book.pdf', pdf='1',
                                 knowledge_base='licensed', route='vision reading'))
    works = {CODE: search_server.Work(CODE, 'An Invented Code', 'licensed', 'an invented licence', code_pages.CODE_ROUTE,
                                      len(FILES), view_id=CODE, code_language='EasyLanguage', companion_of=BOOK),
             BOOK: search_server.Work(BOOK, 'An Invented Book', 'licensed', 'an invented licence', 'vision reading', 1,
                                      view_id=BOOK)}
    catalog = tmp_path / 'code_catalog.json'
    units = {f'{CODE}|{label}': {'work': CODE, 'page': label, **unit,
                                 'lines': {'first': 1, 'last': FILES[label].count('\n') + 1}}
             for label, unit in UNITS.items()} if catalogued else {}
    catalog.write_text(json.dumps({'about': 'invented', 'units': units}), encoding='utf-8')
    return search_server.SearchService({'licensed': (pages, works)})


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(code_catalog, 'CATALOG', tmp_path / 'code_catalog.json')
    return an_invented_service(tmp_path)


SHELF = {'works': [{'work': BOOK, 'source_id': 'an_invented_book_src', 'file': 'an_invented_book.pdf', 'format': 'pdf'},
                   {'work': CODE, 'source_id': CODE, 'file': None, 'format': 'code', 'pages': 3}]}


def test_a_code_work_lists_its_folders_and_files_each_with_the_core_s_catalog_entry(service):
    found = code_works.code_work(service, 'licensed', CODE, SHELF)
    assert (found.title, found.code_language, found.files, found.units) == ('An Invented Code', 'EasyLanguage', 3, 2)
    assert [folder.count for folder in found.folders] == [1, 1, 1]
    assert [(folder.title, [file.label for file in folder.files]) for folder in found.folders] == [
        ('Functions', ['Functions/Invented Average.txt']), ('Indicators', ['Indicators/Invented Band (I).txt']),
        ('Strategies', ['Strategies/Invented Cross (S).txt'])]
    average = found.folders[0].files[0]
    assert (average.name, average.unit.unit, average.unit.category, average.unit.summary_is) == (
        'Invented Average', 'function', 'trend', 'derived (an invented model)')
    assert [(one.name, one.default) for one in average.unit.inputs] == [('Price', 'Close'), ('Length', '10')]
    assert found.folders[2].files[0].unit is None  # a file the catalog has no entry of
    # the core's own count by category, the most first; the book it accompanies opens its page list
    assert [(one.category, one.units) for one in found.categories] == [('trend', 1), ('volatility', 1)]
    assert found.companion == code_works.Companion(key=BOOK, title='An Invented Book', view='pages', id='an_invented_book_src')
    assert found.catalog_said is None
    # a text work, an unknown key, another knowledge base: no code work
    assert code_works.code_work(service, 'licensed', BOOK) is None
    assert code_works.code_work(service, 'licensed', 'nothing') is None
    assert code_works.code_work(service, 'free', CODE) is None


def test_a_code_file_is_its_text_as_given_with_its_lines_its_catalog_entry_and_its_neighbours(service):
    label = 'Indicators/Invented Band (I).txt'
    page = code_works.code_page(service, 'licensed', CODE, label, SHELF)
    assert page.text == FILES[label].rstrip('\n') or page.text == FILES[label]
    assert (page.lines.first, page.lines.last) == (1, page.text.count('\n') + 1)
    assert (page.folder, page.name, page.position, page.files) == ('Indicators', 'Invented Band (I)', 2, 3)
    assert (page.previous, page.next) == ('Functions/Invented Average.txt', 'Strategies/Invented Cross (S).txt')
    assert (page.previous_name, page.next_name) == ('Invented Average', 'Invented Cross (S)')
    assert (page.unit.name, page.unit.category) == ('Invented Band', 'volatility')
    first = code_works.code_page(service, 'licensed', CODE, 'Functions/Invented Average.txt')
    last = code_works.code_page(service, 'licensed', CODE, 'Strategies/Invented Cross (S).txt')
    assert (first.previous, last.next, last.unit) == (None, None, None)
    assert code_works.code_page(service, 'licensed', CODE, 'Indicators/Nothing.txt') is None
    assert code_works.code_page(service, 'licensed', BOOK, '1') is None


def test_a_code_work_the_catalog_holds_nothing_of_says_why(tmp_path, monkeypatch):
    monkeypatch.setattr(code_catalog, 'CATALOG', tmp_path / 'code_catalog.json')
    found = code_works.code_work(an_invented_service(tmp_path, catalogued=False), 'licensed', CODE)
    assert (found.units, found.categories, found.catalog_said) == (0, [], code_works.NO_CATALOG)
    assert all(file.unit is None for folder in found.folders for file in folder.files)


def test_the_code_routes_read_the_search_service_and_never_build_it_under_public_only(service, monkeypatch, tmp_path):
    def refused(public_only):
        raise AssertionError('the search service was built for a knowledge base this app does not serve')

    monkeypatch.setattr(search_hits, 'build_service', refused)
    public = TestClient(create_app(public_only=True), base_url=LOCAL)
    assert public.get(f'/api/licensed/code/{CODE}').status_code == 404
    assert public.get(f'/api/licensed/code/{CODE}/files/{quote("Functions/Invented Average.txt", safe="")}').status_code == 404
    # with the licensed knowledge base served, the work and a file, its label one encoded segment as the librarian links it
    store = readings.Readings(tmp_path / 'export')
    monkeypatch.setattr(readings, 'licensed_readings', lambda: store)
    monkeypatch.setattr(store, 'shelf_data', lambda: SHELF)
    monkeypatch.setattr(search_hits, 'build_service', lambda public_only: service)
    both = TestClient(create_app(), base_url=LOCAL)
    work = both.get(f'/api/licensed/code/{CODE}').json()
    assert [folder['title'] for folder in work['folders']] == ['Functions', 'Indicators', 'Strategies']
    label = 'Indicators/Invented Band (I).txt'
    page = both.get(f'/api/licensed/code/{CODE}/files/{quote(label, safe="")}').json()
    assert (page['label'], page['unit']['name'], page['next']) == (label, 'Invented Band', 'Strategies/Invented Cross (S).txt')
    assert both.get(f'/api/licensed/code/{BOOK}').status_code == 404
    assert both.get(f'/api/licensed/code/{CODE}/files/{quote("Indicators/Nothing.txt", safe="")}').status_code == 404


def test_the_code_work_stands_under_its_book_in_sources_not_as_a_work_of_its_own(monkeypatch, tmp_path):
    from test_diagnostics_app import a_licensed_export

    store = a_licensed_export(tmp_path)
    store.catalog = tmp_path / 'catalog.json'
    store.catalog.write_text(json.dumps({'sources': [
        {'id': 'a-licensed-book', 'file': 'a_licensed_book.pdf', 'title': 'A Licensed Book', 'format': 'pdf'},
        {'id': CODE, 'file': CODE, 'title': 'An Invented Code', 'format': 'code', 'code_language': 'EasyLanguage',
         'companion_of': 'a-licensed-book'}]}), encoding='utf-8')  # the book by its work key, as the search names it
    monkeypatch.setattr(readings, 'licensed_readings', lambda: store)
    code_row = {'knowledge_base': 'licensed', 'work': CODE, 'source_id': CODE, 'format': 'code', 'pages': 3}
    monkeypatch.setattr(store, 'shelf_data', lambda: {'works': [code_row]})
    monkeypatch.setattr(epub_works, 'epubs', lambda: {})  # this machine's EPUBs stay out of a test of invented works
    licensed = [work for work in TestClient(create_app(), base_url=LOCAL).get('/api/works').json()
                if work['knowledge_base'] == 'licensed']
    assert [work['id'] for work in licensed] == ['a_licensed_book']
    assert licensed[0]['code'] == {'key': CODE, 'title': 'An Invented Code', 'code_language': 'EasyLanguage', 'files': 3,
                                   'said': 'companion code: EasyLanguage, 3 files'}
    # a code work whose book is not listed here stands as its own row, its part linking to its files
    store.catalog.write_text(json.dumps({'sources': [
        {'id': CODE, 'file': CODE, 'title': 'An Invented Code', 'format': 'code', 'companion_of': 'a_book_not_held'}]}),
        encoding='utf-8')
    alone = [work for work in TestClient(create_app(), base_url=LOCAL).get('/api/works').json()
             if work['knowledge_base'] == 'licensed' and work['id'] == CODE]
    assert len(alone) == 1 and alone[0]['code']['key'] == CODE and alone[0]['code']['said'] == 'companion code, 3 files'


def test_the_librarian_page_draws_the_code_catalog_s_units_and_a_code_file_numbered(service):
    assert librarian.TOOL_ORDER.index('code_catalog') == librarian.TOOL_ORDER.index('search_works') + 1
    answer = service.code_catalog(work=CODE)
    call = librarian.shaped('code_catalog', {'work': CODE}, answer, 0.01)
    assert call.head.count == '2 units' and call.catalog.total == 2
    assert [(unit.page, unit.unit.name, unit.unit.summary_is) for unit in call.catalog.units] == [
        ('Functions/Invented Average.txt', 'Invented Average', 'derived (an invented model)'),
        ('Indicators/Invented Band (I).txt', 'Invented Band', 'derived (an invented model)')]
    opened = librarian.shaped('open_page', {'work': CODE, 'page': 'Strategies/Invented Cross (S).txt'},
                              service.open_page(CODE, 'Strategies/Invented Cross (S).txt'), 0.01)
    assert (opened.page.kind, opened.page.code_language, opened.page.lines.first) == ('code', 'EasyLanguage', 1)
    # a hit's view of a code file opens here, with the lines it names
    assert librarian.view_of('http://127.0.0.1:8021/#/licensed/code/x/Indicators%2FA.txt?lines=2-9') == \
        '/licensed/code/x/Indicators%2FA.txt?lines=2-9'
    assert librarian.view_of('http://127.0.0.1:8021/#/licensed/code/x/A.txt?other=1') is None
