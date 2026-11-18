import pytest

from backend.ingestion import chunking
from backend.ingestion.sections import Section

SOURCE = {'id': 'book', 'title': 'A Book', 'authors': 'A. Author', 'shelf': 'trading_finance',
          'format': 'pdf', 'licence': 'CC BY 4.0', 'licence_url': 'https://example.org/licence'}


@pytest.fixture(autouse=True)
def _no_tokenizer_download(monkeypatch):
    # tiktoken fetches its vocabulary on a cold cache; the count itself is not under test here.
    monkeypatch.setattr(chunking, 'count_tokens', lambda text: len(text) // 4)


def long_section() -> Section:
    first = 'Alpha sentence number one. ' * 30   # about 810 characters, on PDF page 10
    second = 'Beta sentence number two. ' * 60   # about 1560 characters, on PDF page 11
    text = first + '\n\n' + second
    return Section('book', 3, ['Chapter 1', '1.2 Risk'], text,
                   pages=[(0, 10, 8), (len(first) + 2, 11, 9)])


def test_chunk_ids_are_stable_and_name_source_section_and_position():
    chunks = chunking.chunk_sections([long_section()], SOURCE)
    assert [c.metadata['chunk_id'] for c in chunks][:2] == ['book:0003:000', 'book:0003:001']
    assert chunks == chunking.chunk_sections([long_section()], SOURCE)


def test_every_chunk_knows_the_page_it_starts_on():
    chunks = chunking.chunk_sections([long_section()], SOURCE)
    assert chunks[0].metadata['pdf_page'] == 10 and chunks[0].metadata['printed_page'] == 8
    assert chunks[-1].metadata['pdf_page'] == 11 and chunks[-1].metadata['printed_page'] == 9


def test_chunks_respect_the_size_cap_and_carry_the_citation():
    chunks = chunking.chunk_sections([long_section()], SOURCE)
    assert all(len(c.page_content) <= chunking.CHUNK_SIZE for c in chunks)
    meta = chunks[0].metadata
    assert meta['section'] == '1.2 Risk' and meta['chapter'] == 'Chapter 1'
    assert meta['heading_path'] == 'Chapter 1 > 1.2 Risk'
    assert meta['licence'] == 'CC BY 4.0' and meta['source_title'] == 'A Book'


def test_metadata_never_holds_none_because_chroma_refuses_it():
    html_section = Section('book', 0, ['Article'], 'Short text.', url='https://example.org', anchor=None)
    meta = chunking.chunk_sections([html_section], SOURCE)[0].metadata
    assert None not in meta.values()
    assert 'anchor' not in meta and 'pdf_page' not in meta
    assert meta['url'] == 'https://example.org'


def test_the_config_hash_changes_when_the_splitting_changes(monkeypatch):
    before = chunking.config_hash()
    monkeypatch.setattr(chunking, 'CHUNK_SIZE', 500)
    assert chunking.config_hash() != before


def test_a_chunk_over_a_page_boundary_names_both_pages_and_the_route_of_each():
    first = 'Alpha sentence goes on and on' + ' and on' * 90   # one sentence stitched across the page boundary
    second = ' to its end on the next page.' + ' Beta sentence number two.' * 20
    section = Section('book', 4, ['Chapter 1'], first + second, pages=[(0, 10, 8), (len(first), 11, 9)],
                      routes={10: ('vision reading (m, page/1, validator page/1.1)', 'k10'),
                              11: ('text layer: the provider blocked the reading', None)})
    chunks = chunking.chunk_sections([section], SOURCE)
    spanning = [chunk for chunk in chunks if chunk.metadata.get('pdf_page_end') == 11]
    assert spanning and spanning[0].metadata['pdf_page'] == 10 and spanning[0].metadata['reading_key'] == 'k10'
    assert spanning[0].metadata['route_end'] == 'text layer: the provider blocked the reading'
    assert 'reading_key_end' not in spanning[0].metadata  # None is left out, as Chroma requires
    alone = [chunk for chunk in chunks if 'pdf_page_end' not in chunk.metadata]
    assert all(chunk.metadata['route'] for chunk in alone)
