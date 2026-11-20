"""A work's editions in the view (the operator's E1.a, 20 Nov): an edition is a level under its work, never a group of works;
one edition served, the others kept with all they have. Every work, title and key here is invented (251.a): the private
collection's families exist only in its local data."""

import json

import pytest

from backend.diagnostics import chat, coverage_ladder, readings, search_hits, work_editions
from backend.diagnostics.ladder_types import Rung
from test_diagnostics_app import licensed_with_a_catalog

FAMILY = {'work': 'a_licensed_book', 'serves': 'a_licensed_book', 'chosen': '2026-11-20', 'why': 'an invented reason to serve it',
          'editions': [{'key': 'a_licensed_book', 'label': '2nd edition, 2001', 'year': 2001, 'format': 'pdf', 'served': True},
                       {'key': 'an_invented_third', 'label': '3rd edition, 2009', 'year': 2009, 'format': 'pdf', 'served': False}]}
SERVED = {'knowledge_base': 'licensed', 'work': 'a-licensed-book', 'source_id': 'a_licensed_book', 'title': 'a_licensed_book',
          'format': 'pdf', 'file': 'a_licensed_book.pdf', 'pages': 2, 'served': {'pages': 2, 'searchable': 2}, 'editions': FAMILY}
KEPT = {'knowledge_base': 'licensed', 'work': None, 'source_id': 'an_invented_third', 'title': 'an_invented_third', 'format': 'pdf',
        'file': 'an_invented_third.pdf', 'pages': 3, 'served': {'pages': 3, 'searchable': 0}, 'editions': FAMILY,
        'kept_for': 'a_licensed_book', 'semantic': {'chunks': 12, 'pages': 3}}
LOOKALIKE = {'knowledge_base': 'licensed', 'work': None, 'source_id': 'an_invented_lookalike', 'title': 'an_invented_lookalike',
             'format': 'pdf', 'file': 'an_invented_lookalike.pdf', 'pages': 5, 'served': {'pages': 5, 'searchable': 5},
             'possible_edition_of': ['a_licensed_book']}
CATALOG = [{'id': 'a-licensed-book', 'title': 'An Invented Book', 'edition': '2nd', 'year': 2001, 'format': 'pdf'},
           {'id': 'an_invented_third', 'file': 'an_invented_third.pdf', 'title': 'An Invented Book', 'edition': '3rd', 'year': 2009,
            'format': 'pdf'},
           {'id': 'an_invented_lookalike', 'file': 'an_invented_lookalike.pdf', 'title': 'An Invented Book, Revisited', 'format': 'pdf'}]


def test_an_edition_is_named_as_a_citation_and_a_sentence_name_it():
    assert work_editions.words('2nd', 2003) == '2nd edition, 2003'
    assert (work_editions.words(None, 2017), work_editions.words('3rd', None), work_editions.words(None, None)) == ('2017', '3rd edition', None)
    assert [work_editions.named(label) for label in ('2nd edition, 2003', '2017', work_editions.UNKNOWN)] == [
        '2nd edition, 2003', '2017 edition', 'edition of unknown date']


def test_a_family_is_found_from_any_of_its_rows_and_each_edition_opens_its_own_record():
    epub = {**KEPT, 'format': 'epub', 'file': 'an_invented_third.epub', 'work': 'an_invented_third'}
    legacy = {'work': 'a-legacy-key', 'source_id': 'a_legacy_work', 'format': 'legacy markdown'}
    assert work_editions.target(KEPT) == ('pages', 'an_invented_third')
    assert work_editions.target(epub) == ('epub', 'an_invented_third')
    assert work_editions.target(legacy) == (None, None)
    # a served row the core did not name the family on (its work key a legacy work's): found by the kept row's family
    bare = {key: value for key, value in SERVED.items() if key != 'editions'}
    rows = [bare, KEPT]
    editions = work_editions.editions_of(bare, rows, 'An Invented Book')
    assert editions.said == '2 editions · serves the 2nd edition, 2001'
    assert [(edition.key, edition.served, edition.view, edition.id) for edition in editions.editions] == [
        ('a_licensed_book', True, 'pages', 'a_licensed_book'), ('an_invented_third', False, 'pages', 'an_invented_third')]
    assert (work_editions.kept_for(bare, rows), work_editions.kept_for(KEPT, rows)) == (None, 'a_licensed_book')
    assert work_editions.editions_of(LOOKALIKE, rows, 'a title') is None


def test_a_kept_edition_s_levels_say_so_in_neutral_words_never_the_warning_role():
    rungs = [Rung(level='text served', count=0, of=3, said='0 of 3 PDF pages', warn=True),
             Rung(level='keyword search', count=0, of=3, said='0 of 3 PDF pages'),
             Rung(level='semantic search', count=3, of=3, said='12 chunks over 3 of 3 PDF pages')]
    kept = coverage_ladder.kept_words(KEPT, rungs)
    assert [rung.said for rung in kept] == ['kept: the 2nd edition, 2001 is served; opens by its own key', 'kept: not searched',
                                            '12 chunks over 3 of 3 PDF pages, held back from the search']
    assert not any(rung.warn for rung in kept)
    # never embedded: its own words stand; a served edition's levels as they are
    never = coverage_ladder.kept_words(KEPT, [rungs[2].model_copy(update={'count': None, 'said': 'held back: never embedded'})])
    assert never[0].said == 'held back: never embedded'
    assert coverage_ladder.kept_words(SERVED, rungs) == rungs


def test_a_hit_and_an_opened_page_name_their_edition_beside_the_title():
    hit = search_hits.SearchHit(score=1.0, knowledge_base='licensed', work='a-licensed-book', title='An Invented Book',
                                page={'label': '27', 'pdf': '44', 'printed': '27'}, section=None, where='x', snippet='', terms_found=[],
                                terms_missing=[], licence='private copy', route='vision reading', reading_key=None, view=None,
                                edition='2nd', year=2003)
    assert hit.edition_said == '2nd edition, 2003'
    assert chat.Hit.model_validate({'title': 'An Invented Report', 'year': 2017}).model_dump()['edition_said'] == '2017'
    assert chat.ServerAnswer.model_validate({'state': 'found', 'title': 'A free work'}).edition_said is None


@pytest.mark.corpus
@pytest.mark.readings
def test_a_kept_edition_folds_into_its_served_edition_s_row_and_its_record_names_every_edition(monkeypatch, tmp_path):
    client = licensed_with_a_catalog(monkeypatch, tmp_path / 'editions', json.dumps({'sources': CATALOG}))
    store = readings.licensed_readings()
    store.shelf = lambda: {'works': [SERVED, KEPT, LOOKALIKE]}
    licensed = {work['id']: work for work in client.get('/api/works').json() if work['knowledge_base'] == 'licensed'}
    # one row for the work: the kept edition folded into the served one's, which keeps its own catalog data and ladder
    assert 'an_invented_third' not in licensed and {'a_licensed_book', 'an_invented_lookalike'} <= set(licensed)
    work = licensed['a_licensed_book']
    assert (work['title'], work['edition'], work['ladder']['rungs'][0]['said']) == ('An Invented Book', '2nd', '2 of 2 PDF pages')
    assert work['editions']['said'] == '2 editions · serves the 2nd edition, 2001'
    assert (work['editions']['chosen'], work['editions']['why']) == ('2026-11-20', 'an invented reason to serve it')
    assert [(edition['named'], edition['view'], edition['id']) for edition in work['editions']['editions'] if not edition['served']] == [
        ('3rd edition, 2009', 'pages', 'an_invented_third')]
    # a file that looks like another edition, linked with none: a call to look, in the API's words
    assert licensed['an_invented_lookalike']['possible_edition'] == (
        'possible edition of An Invented Book: not linked; the operator decides')
    assert work['possible_edition'] is None
    # the kept edition's own record: it opens, names every edition with its own marked, and says it is kept, never warned
    kept = client.get('/api/licensed/works/an_invented_third/pages').json()
    assert (kept['editions']['current'], kept['editions']['title']) == ('an_invented_third', 'An Invented Book')
    assert [rung['said'] for rung in kept['ladder']['rungs'][:2]] == [
        'kept: the 2nd edition, 2001 is served; opens by its own key', 'kept: not searched']
    assert not any(rung['warn'] for rung in kept['ladder']['rungs'])
    served = client.get('/api/licensed/works/a_licensed_book/pages').json()
    assert served['editions']['current'] == 'a_licensed_book' and served['ladder']['rungs'][0]['said'] == '2 of 2 PDF pages'
