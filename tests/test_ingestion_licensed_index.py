"""The private base's vector index (#8): the librarian's own pages, chunked as the free index is, held works left out."""
from types import SimpleNamespace

from backend.ingestion import licensed_index
from backend.search import page_index

PROSE = 'A sentence of plain prose about position sizing and the risk of ruin. ' * 30


def page(work: str, pdf: str | None, route: str = 'vision reading (m)', knowledge_base: str = 'licensed', **fields):
    return page_index.Page(work=work, page=pdf or 's1', line=1, text=PROSE, path='x', pdf=pdf, section='Chapter 2',
                           knowledge_base=knowledge_base, route=route, reading_key='k' * 64 if pdf else None, **fields)


def work(key: str) -> SimpleNamespace:
    return SimpleNamespace(key=key, title=key.title(), licence='licensed, local use only', route='per page', subject=None)


def test_each_served_page_becomes_cited_chunks_and_a_held_work_stays_out():
    pages = [page('book', '7', printed='5'), page('book', '8'), page('held', '1'), page('free_one', '3', knowledge_base='free')]
    planned, left_out = licensed_index.plans(pages, {'book': work('book'), 'held': work('held')}, held={'held'})
    assert [plan['source']['id'] for plan in planned] == ['book'] and left_out == {'held back by the provenance list': 1}
    chunk = planned[0]['chunks'][0]
    assert chunk.metadata['knowledge_base'] == 'licensed' and chunk.metadata['pdf_page'] == 7
    assert chunk.metadata['printed_page'] == '5' and chunk.metadata['route'] == 'vision reading (m)'
    assert chunk.metadata['chunk_id'].startswith('book:0000:') and chunk.metadata['heading_path'] == 'Chapter 2'
    assert planned[0]['pages'] == 2 and planned[0]['tokens'] > 0


def test_a_work_whose_pages_did_not_change_keeps_its_fingerprint():
    first = [page('book', '7'), page('book', '8')]
    assert licensed_index.fingerprint(first) == licensed_index.fingerprint([page('book', '7'), page('book', '8')])
    assert licensed_index.fingerprint(first) != licensed_index.fingerprint([page('book', '7'), page('book', '8', route='legacy markdown')])


def test_a_dry_run_reads_the_stored_fingerprints_without_writing(tmp_path):
    # found 22 Nov: a dry run without the index's facts counted every work as changed and overstated the estimate
    import sqlite3

    import pytest

    from backend.ingestion import index_store

    path = tmp_path / 'knowledge.sqlite3'
    assert licensed_index.index_connection(path, dry_run=True) is None and not path.exists()
    with index_store.connect(path) as written:
        written.execute("INSERT INTO sources (id, fingerprint) VALUES ('book', 'f1')")
    connection = licensed_index.index_connection(path, dry_run=True)
    assert index_store.stored_fingerprint(connection, 'book') == 'f1'
    with pytest.raises(sqlite3.OperationalError):
        connection.execute("INSERT INTO sources (id, fingerprint) VALUES ('other', 'f2')")
    connection.close()


def test_an_epub_section_without_a_pdf_page_cites_its_section():
    planned, _ = licensed_index.plans([page('epub_work', None)], {'epub_work': work('epub_work')}, held=set())
    assert 'pdf_page' not in planned[0]['chunks'][0].metadata and planned[0]['sections'][0].pages == []


def test_the_private_index_lies_where_git_never_tracks_it():
    from backend.configuration import data_paths
    from backend.conversion.store import reading_store

    assert data_paths.LICENSED_INDEX.is_relative_to(data_paths.LICENSED_WORKING)
    assert reading_store.refusal(data_paths.ROOT / 'corpus' / 'index_private') is not None  # a tracked path is refused


def test_a_chunk_carries_the_catalog_s_shelf_and_authors_which_the_shelf_filter_matches():
    entry = {'title': 'Book, the catalog title', 'authors': 'A. Author', 'shelf': 'trading_finance', 'format': 'pdf'}
    planned, _ = licensed_index.plans([page('book', '7')], {'book': work('book')}, held=set(), catalog={'book': entry})
    metadata = planned[0]['chunks'][0].metadata
    assert (metadata['shelf'], metadata['authors'], metadata['source_title']) == ('trading_finance', 'A. Author', 'Book, the catalog title')
    bare, _ = licensed_index.plans([page('book', '7')], {'book': work('book')}, held=set())
    assert bare[0]['chunks'][0].metadata['source_title'] == 'Book'


def test_a_licensed_html_source_the_provenance_list_holds_back_stays_out(tmp_path, monkeypatch):
    from backend.conversion.reading import reading_cells
    from backend.search import search_server
    from test_search_server import a_licensed_rule, a_licensed_shelf

    a_licensed_shelf(tmp_path, monkeypatch)
    a_licensed_rule(tmp_path)
    assert licensed_index.held_works(search_server.legacy_keys()) == set()
    monkeypatch.setattr(reading_cells, 'may_send', lambda name: name != 'invented_rule.html')
    assert licensed_index.held_works(search_server.legacy_keys()) == {'invented_rule'}


def test_a_code_work_is_embedded_a_file_a_chunk_under_a_header_that_names_it():
    # #12: never cut, so a unit of code reaches the embedding whole, and its page label rides along to open the file
    code = 'inputs: Length(14);\nPlot1(Average(Close, Length));\n'
    pages = [page_index.Page('book_code', 'Indicators/Fast (I).txt', 1, code, 'p', section='Indicators', route='source code')]
    source = {'id': 'book_code', 'title': 'A Book: companion code', 'authors': 'A. Author', 'shelf': 'trading_finance',
              'format': 'code', 'licence': 'licensed', 'licence_url': ''}
    [chunk] = licensed_index.code_chunks(pages, source, 'EasyLanguage')
    assert chunk.page_content == 'A Book: companion code · Indicators/Fast (I).txt · EasyLanguage\n\n' + code
    assert chunk.metadata['page_label'] == 'Indicators/Fast (I).txt' and chunk.metadata['chunk_id'] == 'book_code:0000:000'
    assert chunk.metadata['section_id'] == 'book_code:0000' and chunk.metadata['route'] == 'source code'


def test_a_hit_from_a_code_chunk_opens_its_file():
    from backend.search import semantic_search

    assert semantic_search.page_of({'page_label': 'Indicators/Fast (I).txt'}, 'book_code:0000:000') == {
        'label': 'Indicators/Fast (I).txt', 'pdf': None, 'printed': None}
