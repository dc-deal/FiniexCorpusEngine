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
