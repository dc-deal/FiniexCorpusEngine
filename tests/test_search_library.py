"""The library tools of decision 124.a: which works hold a subject, a work's contents, and what each work is for."""
import json

from backend.search import page_index, search_server
from test_search_server import a_licensed_shelf, a_pdf

FILLER = 'The chapter goes on with other matters of the trade, its people and its tools, as books on markets tend to do. '


def page(work, label, text, **fields) -> page_index.Page:
    return page_index.Page(work, label, 1, text, f'{work}.md', **fields)


def library() -> search_server.SearchService:
    """A book about composites over five pages, a glossary whose one page names them often, and a free book about bonds."""
    book = [page('book', str(n), f'A composite return links the portfolios of one strategy. {FILLER * 3}', pdf=str(n),
                 section=f'Chapter {1 + n // 3}', knowledge_base='licensed', route='legacy markdown') for n in range(1, 6)]
    glossary = [page('glossary', '9', 'Composite: composite, composite, composite. ' + FILLER * 3, pdf='9', section='Glossary',
                     knowledge_base='licensed', route='legacy markdown')]
    bonds = [page('bonds', '3', 'Bond valuation discounts every coupon at the yield. ' + FILLER * 3, pdf='3', section='Bonds',
                  knowledge_base='free', route='vision reading')]
    works = {'book': search_server.Work('book', 'The Book', 'licensed', 'licensed, local use only', 'legacy markdown', 5,
                                        subject='Composite returns, as the standard defines them.'),
             'glossary': search_server.Work('glossary', 'A Glossary', 'licensed', 'licensed, local use only', 'legacy markdown', 1),
             'bonds': search_server.Work('bonds', 'Bonds', 'free', 'CC BY 4.0', 'per page', 1)}
    return search_server.SearchService({'free': (bonds, {'bonds': works['bonds']}),
                                        'licensed': (book + glossary, {key: works[key] for key in ('book', 'glossary')})})


def test_a_work_about_the_subject_outranks_one_strong_page_elsewhere():
    assert library().search('composite', hits=1)['hits'][0]['work'] == 'glossary'  # the best passage is the glossary's
    assert [item['work'] for item in library().search_works('composite')['works']] == ['book', 'glossary']  # the shelf: the book
    found = library().search_works('composite return')
    assert found['state'] == 'found' and [item['work'] for item in found['works']] == ['book', 'glossary']
    first = found['works'][0]
    assert first['subject'] == 'Composite returns, as the standard defines them.' and first['pages_matching'] == 5
    assert first['pages_with_every_term'] == 5 and found['works'][1]['pages_with_every_term'] == 0
    assert sorted(section['section'] for section in first['best_sections']) == ['Chapter 1', 'Chapter 2']  # each section once


def test_a_subject_no_page_holds_in_full_says_so_and_nothing_at_all_is_nothing_found():
    assert library().search_works('composite bond')['pages_with_every_term'] == 0
    assert library().search_works('composite', corpus='free')['state'] == 'nothing found'
    assert library().search_works('zebra')['state'] == 'nothing found'
    assert library().search_works('composite', hits=0)['state'] == 'error'
    assert library().search_works('composite', corpus='private')['state'] == 'error'


def test_the_contents_come_from_the_pdf_s_bookmarks_where_its_labels_are_pdf_pages(tmp_path):
    import pymupdf

    a_pdf(tmp_path / 'b.pdf', 4)
    with pymupdf.open(tmp_path / 'b.pdf') as document:
        document.set_toc([[1, 'Part One', 1], [2, 'A section', 2], [3, 'A detail', 3], [1, 'Part Two', 4], [2, 'Its end', 4]])
        document.saveIncr()
    pages = [page('b', str(n), PROSE_OF(n), pdf=str(n), knowledge_base='free', route='vision reading') for n in range(1, 5)]
    service = search_server.SearchService({'free': (pages, {'b': search_server.Work('b', 'B', 'free', 'CC BY 4.0', 'per page', 4)})},
                                          images={'b': {'pdf': tmp_path / 'b.pdf'}})
    toc = service.toc('b')
    assert toc['source'] == 'pdf bookmarks' and toc['left_out'] == 1
    assert toc['entries'] == [{'level': 1, 'title': 'Part One', 'page': '1'}, {'level': 2, 'title': 'A section', 'page': '2'},
                              {'level': 1, 'title': 'Part Two', 'page': '4'}, {'level': 2, 'title': 'Its end', 'page': '4'}]
    assert service.toc('b', depth=3)['left_out'] == 0
    assert service.toc('b', depth=7)['state'] == 'error' and service.toc('nobody')['state'] == 'error'


def PROSE_OF(n: int) -> str:
    return f'Page {n} speaks of breakers that open after timeouts. ' + FILLER * 3


def test_the_contents_of_a_legacy_text_are_its_headings_on_the_pages_it_labels(tmp_path):
    legacy = tmp_path / 'w.md'
    legacy.write_text(f'# The Work\n<!-- page None -->\n## One\n{PROSE_OF(1)}\n<!-- page None -->\n{PROSE_OF(2)}\n### One point one\n',
                      encoding='utf-8')
    pages = page_index.pages_of(legacy.read_text(encoding='utf-8'), 'w', legacy.as_posix())
    pages = [page_index.Page(**{**vars(each), 'knowledge_base': 'licensed', 'route': 'legacy markdown'}) for each in pages]
    service = search_server.SearchService({'licensed': (pages, {'w': search_server.Work('w', 'W', 'licensed', 'x', 'legacy markdown', 2)})},
                                          images={})
    toc = service.toc('w', depth=6)
    assert toc['source'] == 'legacy markdown headings'
    assert toc['entries'] == [{'level': 1, 'title': 'The Work', 'page': '1'}, {'level': 2, 'title': 'One', 'page': '1'},
                              {'level': 3, 'title': 'One point one', 'page': '2'}]
    assert [entry['page'] for entry in toc['entries']] == [p.page for p in pages][:1] * 2 + ['2']  # the labels open_page takes


def test_the_contents_of_an_html_source_are_its_sections():
    pages = [page('h', 's1', PROSE_OF(1), section='Intro', knowledge_base='free', route='html, parsed by section'),
             page('h', 's2', PROSE_OF(2), section='Intro > Detail', knowledge_base='free', route='html, parsed by section')]
    service = search_server.SearchService({'free': (pages, {'h': search_server.Work('h', 'H', 'free', 'CC BY 4.0', 'html', 2)})},
                                          images={})
    assert service.toc('h')['entries'] == [{'level': 1, 'title': 'Intro', 'page': 's1'}, {'level': 2, 'title': 'Detail', 'page': 's2'}]


def test_works_says_what_each_work_is_for_where_a_sentence_is_written(tmp_path, monkeypatch):
    a_licensed_shelf(tmp_path, monkeypatch)
    (tmp_path / 'subjects.json').write_text(json.dumps({'subjects': {'key-a': 'Breakers and timeouts.', 'gone': 'x'}}), encoding='utf-8')
    _, works = search_server.licensed_pages()
    assert works['key-a'].subject == 'Breakers and timeouts.' and works['new_doc'].subject is None and 'gone' not in works
    listed = library().list_works()
    assert {item['work']: item['subject'] for item in listed}['book'] == 'Composite returns, as the standard defines them.'


def test_a_work_search_is_logged_with_its_works_and_never_a_page(tmp_path):
    log_path = tmp_path / 'calls.jsonl'
    search_server.log_call('search_works', library().search_works('composite'), 0.01, log_path, query='composite')
    record = json.loads(log_path.read_text(encoding='utf-8'))
    assert record['answered'] == [] and record['answered_works'] == [{'knowledge_base': 'licensed', 'work': 'book'},
                                                                     {'knowledge_base': 'licensed', 'work': 'glossary'}]


def test_a_stub_of_bookmarks_gives_way_to_the_headings_of_the_text(tmp_path):
    import pymupdf

    a_pdf(tmp_path / 'w.pdf', 2)
    with pymupdf.open(tmp_path / 'w.pdf') as document:
        document.set_toc([[1, 'Front', 1], [1, 'Back', 2]])
        document.saveIncr()
    legacy = tmp_path / 'w.md'
    legacy.write_text(f'<!-- page 1 -->\n# A\n## B\n{PROSE_OF(1)}\n<!-- page 2 -->\n## C\n{PROSE_OF(2)}\n', encoding='utf-8')
    pages = [page_index.Page(**{**vars(each), 'knowledge_base': 'licensed', 'route': 'legacy markdown'})
             for each in page_index.pages_of(legacy.read_text(encoding='utf-8'), 'w', legacy.as_posix())]
    service = search_server.SearchService({'licensed': (pages, {'w': search_server.Work('w', 'W', 'licensed', 'x', 'legacy markdown', 2)})},
                                          images={'w': {'pdf': tmp_path / 'w.pdf'}})
    toc = service.toc('w')
    assert toc['source'] == 'legacy markdown headings' and [entry['title'] for entry in toc['entries']] == ['A', 'B', 'C']
