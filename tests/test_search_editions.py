"""A work's editions (E1.a, E2.a, the operator, 20 Nov 2026): one edition served, the others kept, chosen by a command."""

import pytest

from backend.search import editions, search_server, shelf
from backend.search.page_index import Page

TODAY = '2026-11-20'
LICENCE = 'licensed, local use only'


def a_family() -> dict:
    return editions.link({}, ['old', 'new'], serves='old', why='the newer one has its formulas as pictures', today=TODAY)


def test_a_family_serves_one_edition_and_keeps_the_others():
    families = a_family()
    assert families == {'old': {'editions': ['old', 'new'], 'serves': 'old', 'chosen': TODAY,
                                'why': 'the newer one has its formulas as pictures'}}
    assert editions.kept(families) == {'new': 'old'} and editions.family_of('new', families) == 'old'
    assert editions.family_of('alone', families) is None


def test_the_operator_s_choice_switches_the_served_edition_and_says_when_and_why():
    switched = editions.serve(a_family(), 'new', why='its formulas are read now', today='2026-12-01')
    assert switched['old']['serves'] == 'new' and editions.kept(switched) == {'old': 'new'}
    assert (switched['old']['chosen'], switched['old']['why']) == ('2026-12-01', 'its formulas are read now')


@pytest.mark.parametrize('keys, serves, refused', [
    (['old'], 'old', 'two editions or more'),
    (['old', 'new'], 'other', 'not among'),
])
def test_a_family_that_cannot_stand_is_refused(keys, serves, refused):
    with pytest.raises(ValueError, match=refused):
        editions.link({}, keys, serves, 'why', TODAY)


def test_an_edition_joins_one_family_only_and_only_a_linked_one_is_served():
    with pytest.raises(ValueError, match='already in a family'):
        editions.link(a_family(), ['new', 'third'], 'third', 'why', TODAY)
    with pytest.raises(ValueError, match='in no family'):
        editions.serve(a_family(), 'third', 'why', TODAY)


def test_an_edition_is_named_as_a_person_names_it():
    assert editions.label({'edition': '2nd', 'year': 2005}) == '2nd edition, 2005'
    assert editions.label({'edition': None, 'year': 2018}) == '2018' and editions.label(None) == 'edition unknown'


def test_the_list_is_never_written_where_git_would_track_it(tmp_path):
    # it names private works (251.a): beside the stand-ins' list in the ignored working folder, never in the repository
    tracked = search_server.REPO / 'corpus' / 'editions.json'
    with pytest.raises(ValueError, match='never written there'):
        editions.write(a_family(), tracked)
    assert not tracked.exists()
    written = editions.write(a_family(), tmp_path / 'editions.json')
    assert editions.load(written) == a_family()


def test_a_file_that_looks_like_another_edition_is_flagged_until_it_is_linked():
    entries = [{'id': 'old', 'title': 'Building Bridges: A Course', 'authors': 'A. Writer'},
               {'id': 'new', 'title': 'Building Bridges', 'authors': 'A. Writer, B. Helper'},
               {'id': 'other', 'title': 'Building Bridges', 'authors': 'C. Someone'},  # another author: another work
               {'id': 'deck', 'title': 'Building Bridges: Lecture 1', 'authors': 'A. Writer', 'series': {'id': 'lectures'}}]
    assert editions.possible_editions(entries, {}) == {'old': ['new'], 'new': ['old']}
    assert editions.possible_editions(entries, a_family()) == {}


def two_editions(monkeypatch) -> tuple[list, dict]:
    from backend.ingestion import licensed_index

    monkeypatch.setattr(licensed_index, 'catalog_entries', lambda keys: {'old': {'edition': '2nd', 'year': 2005},
                                                                         'new': {'edition': '3rd', 'year': 2010}})
    pages = [Page('old', '1', 1, 'The Sharpe ratio of a strategy measured over years.', 'old.pdf', pdf='1', knowledge_base='licensed'),
             Page('new', 's1', 1, 'The Sharpe ratio of a strategy measured over months.', 'new.epub', knowledge_base='licensed')]
    works = {'old': search_server.Work('old', 'A Book', 'licensed', LICENCE, 'per page', pages=1),
             'new': search_server.Work('new', 'A Book', 'licensed', LICENCE, 'epub, parsed by section', pages=1)}
    return search_server.with_editions(pages, works, {}, a_family())


def test_the_keyword_search_skips_a_kept_edition_which_still_opens_by_its_own_key(monkeypatch):
    pages, works = two_editions(monkeypatch)
    service = search_server.SearchService({'licensed': (pages, works)}, view_url=None)
    found = service.search('sharpe ratio strategy')
    assert [hit['work'] for hit in found['hits']] == ['old']
    assert (found['hits'][0]['edition'], found['hits'][0]['year']) == ('2nd', 2005)  # a citation names its edition
    opened = service.open_page('new', 's1')
    assert opened['state'] == 'found' and opened['kept_for'] == 'old' and opened['edition'] == '3rd'
    listed = {work['work']: work for work in service.list_works()}
    assert listed['new']['kept_for'] == 'old' and listed['new']['pages'] == 0 and listed['old']['kept_editions'] == ['new']


def test_a_kept_edition_keeps_its_place_route_and_text_so_its_chunks_are_not_embedded_again(monkeypatch):
    from backend.ingestion import licensed_index

    pages, _ = two_editions(monkeypatch)
    kept = [page for page in pages if page.work == 'new']
    unchanged = [Page('new', 's1', 1, 'The Sharpe ratio of a strategy measured over months.', 'new.epub', knowledge_base='licensed')]
    assert licensed_index.fingerprint(kept) == licensed_index.fingerprint(unchanged) and not kept[0].searchable


def test_the_semantic_search_drops_a_kept_edition_s_chunks_from_the_private_results():
    from langchain_core.documents import Document

    from backend.chat import app_config
    from backend.search import semantic_search
    from backend.search.retrieval import KeywordIndex
    from test_chat_turn import Store, chain, keywords, plan
    from test_search_semantic import SOURCES

    text = 'The Sharpe ratio of a strategy, measured before costs, overstates what a trader keeps.'
    chunks = [{'chunk_id': f'{key}:0003:000', 'source_id': key, 'source_title': 'A Book', 'licence': LICENCE, 'pdf_page': 41,
               'route': 'vision reading (m)', 'knowledge_base': 'licensed'} for key in ('old', 'new')]

    class PrivateStore:
        def similarity_search_with_score(self, query, k, filter=None):
            return [(Document(page_content=text, metadata=meta), 0.2) for meta in reversed(chunks)]

    engine = semantic_search.SemanticSearch(SOURCES, app_config.load(), chain(plan()), Store(), keywords(), private=True,
                                            private_store=PrivateStore(),
                                            private_keywords=KeywordIndex([(meta['chunk_id'], text, meta) for meta in chunks]),
                                            kept=frozenset({'new'}))
    private = [hit['work'] for hit in engine.search('what does the sharpe ratio measure?', hits=5)['hits']
               if hit['knowledge_base'] == 'licensed']
    assert private == ['old']


def test_every_row_of_a_family_carries_it_and_a_kept_one_names_the_served_edition():
    entries = [{'id': 'old', 'title': 'A Book', 'authors': 'A. Writer', 'edition': '2nd', 'year': 2005, 'format': 'pdf'},
               {'id': 'new', 'title': 'A Book', 'authors': 'A. Writer', 'edition': '3rd', 'year': 2010, 'format': 'epub'},
               {'id': 'stray', 'title': 'Another Book', 'authors': 'B. Writer', 'year': 2001},
               {'id': 'stray_copy', 'title': 'Another Book', 'authors': 'B. Writer', 'year': 2003}]
    rows = [{'work': 'old', 'file': 'old.pdf'}, {'work': 'new', 'file': 'new.epub'}, {'work': None, 'file': 'stray.pdf'},
            {'work': 'stray_copy', 'file': 'stray_copy.pdf'}]
    marked = {row['file']: row for row in shelf.with_editions(rows, a_family(), entries)}
    family = marked['new.epub']['editions']
    assert marked['new.epub']['kept_for'] == 'old' and 'kept_for' not in marked['old.pdf']
    assert marked['old.pdf']['editions'] == family and (family['serves'], family['chosen']) == ('old', TODAY)
    assert [(edition['key'], edition['label'], edition['served']) for edition in family['editions']] == \
        [('old', '2nd edition, 2005', True), ('new', '3rd edition, 2010', False)]
    assert marked['stray.pdf']['possible_edition_of'] == ['stray_copy'] and 'editions' not in marked['stray.pdf']
    assert shelf.totals([{**row, 'planned': None, 'read': 0, 'passed': 0, 'served': {'pages': 0, 'from_readings': 0},
                          'not_passed': {}, 'unplaced': {}} for row in marked.values()])['kept_editions'] == 1


def test_an_edition_named_by_its_file_s_stem_finds_a_legacy_work_keyed_otherwise(monkeypatch):
    # found by line 2, 20 Nov: the served lecture is a legacy work, keyed by its citation key, while the list and the catalog
    # name it by its file's stem; its shelf row carried no family
    from backend.ingestion import licensed_index

    monkeypatch.setattr(licensed_index, 'catalog_entries', lambda keys: {})
    families = editions.link({}, ['old_stem', 'new'], serves='new', why='why', today=TODAY)
    pages = [Page('legacy-old', '1', 1, 'The Sharpe ratio of a strategy.', 'old.md', pdf='1', knowledge_base='licensed')]
    works = {'legacy-old': search_server.Work('legacy-old', 'A Book', 'licensed', LICENCE, 'legacy markdown', pages=1)}
    pages, works = search_server.with_editions(pages, works, {'legacy-old': 'old_stem'}, families)
    assert works['legacy-old'].kept_for == 'new' and not pages[0].searchable
    rows = shelf.with_editions([{'work': 'legacy-old', 'file': 'old_stem.pdf'}], families, [])
    assert rows[0]['kept_for'] == 'new' and rows[0]['editions']['serves'] == 'new'
