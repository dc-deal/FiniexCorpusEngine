"""Every work names its language (issue #11, line 1, 23 Nov): the view shows it where the work stands and filters by it. Every
work and catalog here is invented, in two languages, so the facet's filtering is held now and not first when a second
language comes; no licensed title or text stands in a tracked file."""

import json

from fastapi.testclient import TestClient

from backend.diagnostics import epub_works, readings, sources
from backend.diagnostics.app import create_app

LOCAL = 'http://127.0.0.1'
ENTRY = {'authors': 'An Invented Author', 'publisher': 'An Invented Press', 'year': 2024, 'licence': 'CC BY 4.0',
         'format': 'html', 'shelf': 'trading_finance'}


def a_free_catalog(tmp_path):
    """An invented free catalog of two works, one in English and one in German, and one that names no language."""
    path = tmp_path / 'catalog.json'
    path.write_text(json.dumps({'sources': [
        {**ENTRY, 'id': 'an_invented_english_work', 'title': 'An Invented Work', 'language': 'en',
         'files': [{'path': 'corpus/raw/an_invented_english_work.html'}]},
        {**ENTRY, 'id': 'an_invented_german_work', 'title': 'Ein erfundenes Werk', 'language': 'de',
         'files': [{'path': 'corpus/raw/an_invented_german_work.html'}]},
        {**ENTRY, 'id': 'an_invented_unsaid_work', 'title': 'An Unsaid Work',
         'files': [{'path': 'corpus/raw/an_invented_unsaid_work.html'}]}]}), encoding='utf-8')
    return path


def test_the_free_catalog_s_works_carry_the_language_each_entry_names(tmp_path):
    assert [(work.id, work.language) for work in sources.works(a_free_catalog(tmp_path))] == [
        ('an_invented_english_work', 'en'), ('an_invented_german_work', 'de'), ('an_invented_unsaid_work', None)]


def test_every_row_of_the_sources_list_and_a_work_s_head_name_the_language_its_catalog_names(monkeypatch, tmp_path):
    from test_diagnostics_app import a_licensed_export

    catalog = a_free_catalog(tmp_path)
    real = sources.works
    monkeypatch.setattr(sources, 'works', lambda catalog_path=None: real(catalog_path or catalog))
    (tmp_path / 'licensed').mkdir()
    store = a_licensed_export(tmp_path / 'licensed')
    store.catalog = tmp_path / 'licensed_catalog.json'
    # by its work key, as the store joins a catalog entry to its export's work
    book = {'id': 'a-licensed-book', 'file': 'a_licensed_book.pdf', 'title': 'A Licensed Book', 'format': 'pdf',
            'language': 'de'}
    store.catalog.write_text(json.dumps({'sources': [book]}), encoding='utf-8')
    monkeypatch.setattr(readings, 'licensed_readings', lambda: store)
    monkeypatch.setattr(epub_works, 'epubs', lambda: {})  # this machine's EPUBs stay out of a test of invented works
    client = TestClient(create_app(), base_url=LOCAL)
    languages = {work['id']: work['language'] for work in client.get('/api/works').json()}
    expected = {'an_invented_english_work': 'en', 'an_invented_german_work': 'de', 'an_invented_unsaid_work': None,
                'a_licensed_book': 'de'}
    assert {key: languages[key] for key in expected} == expected
    # a work's head, its page list here, says it as its row does
    assert client.get('/api/licensed/works/a_licensed_book/pages').json()['language'] == 'de'
