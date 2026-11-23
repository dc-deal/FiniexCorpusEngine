import json

from backend.search import code_pages, page_index

INDICATOR = 'inputs: Length(14);\nvars: FastValue(0);\nFastValue = Average(Close, Length);\nPlot1(FastValue, "Fast");\n'
STRATEGY = 'if MarketPosition = 0 and Close > Close[1] then buy next bar at market;\n'


def a_code_work(root):
    """An invented code work: two folders, a file the route does not take, and an empty file."""
    folder = root / 'code' / 'invented_code'
    (folder / 'Indicators').mkdir(parents=True)
    (folder / 'Strategies').mkdir()
    (folder / 'Indicators' / 'Fast Average (I).txt').write_bytes(INDICATOR.replace('\n', '\r\n').encode('utf-8'))
    (folder / 'Strategies' / 'XYZBreakout.txt').write_bytes(STRATEGY.encode('cp1252') + 'x \xa7 y\n'.encode('cp1252'))
    (folder / 'Strategies' / 'notes.xlsx').write_bytes(b'PK\x03\x04')
    (folder / 'Strategies' / 'empty.txt').write_bytes(b'   \n')
    return folder


def test_a_source_file_is_decoded_as_utf8_else_as_the_platforms_own_encoding_without_nul_or_carriage_returns():
    assert code_pages.decode('a\r\nb\x00'.encode('utf-8')) == 'a\nb'
    assert code_pages.decode('Stop \xa7 1'.encode('cp1252')) == 'Stop \xa7 1'


def test_the_ranking_sees_each_camelcase_identifier_split_once_and_the_quote_stays_as_written():
    words = code_pages.index_words(STRATEGY + STRATEGY)
    assert words.startswith(STRATEGY + STRATEGY)
    assert words.count('market position') == 1 and 'close' not in words.split('\n', 2)[-1]  # a plain word is not repeated


def test_a_files_name_is_a_word_too_with_the_publishers_prefix_split_off():
    assert code_pages.name_words('XYZBreakout', 'XYZ').split() == ['xyzbreakout', 'breakout']
    assert code_pages.name_words('Fast Average (I)').split() == ['fast', 'average', 'i']
    assert 'bollinger' in code_pages.name_words('BollingerBands').split()


def test_each_source_file_is_one_page_with_its_path_as_label_its_folder_as_section_and_every_line(tmp_path):
    pages = code_pages.code_pages('invented_code', a_code_work(tmp_path), prefix='XYZ')
    assert [page.page for page in pages] == ['Indicators/Fast Average (I).txt', 'Strategies/XYZBreakout.txt']
    first, second = pages
    assert first.section == 'Indicators' and (first.line, first.line_end) == (1, 5) and first.text == INDICATOR
    assert first.route == code_pages.CODE_ROUTE and first.searchable and first.knowledge_base == 'licensed'
    assert 'fast value' in first.words and 'breakout' in second.words.split()
    assert page_index.is_structural(first.text)  # short for prose, yet a code page stays in the ranking


def test_a_units_kind_comes_from_its_folder_and_the_contents_list_folders_then_files(tmp_path):
    pages = code_pages.code_pages('invented_code', a_code_work(tmp_path))
    assert [code_pages.unit_kind(page.page) for page in pages] == ['indicator', 'strategy']
    assert code_pages.contents(pages) == [
        {'level': 1, 'title': 'Indicators', 'page': None},
        {'level': 2, 'title': 'Fast Average (I)', 'page': 'Indicators/Fast Average (I).txt'},
        {'level': 1, 'title': 'Strategies', 'page': None},
        {'level': 2, 'title': 'XYZBreakout', 'page': 'Strategies/XYZBreakout.txt'}]


def test_the_local_catalog_names_a_code_work_by_its_folder(tmp_path):
    a_code_work(tmp_path)
    catalog = tmp_path / 'catalog.json'
    entries = [{'id': 'invented_code', 'file': 'code/invented_code', 'format': 'code', 'code_language': 'EasyLanguage'},
               {'id': 'gone', 'file': 'code/gone', 'format': 'code'}, {'id': 'a_book', 'file': 'a_book.pdf', 'format': 'pdf'}]
    catalog.write_text(json.dumps({'sources': entries}), encoding='utf-8')
    found = code_pages.licensed_code(catalog, tmp_path)
    assert list(found) == ['invented_code'] and found['invented_code'][1]['code_language'] == 'EasyLanguage'
    assert code_pages.licensed_code(tmp_path / 'absent.json', tmp_path) == {}
