"""The licensed EPUB works in the diagnostics (decision 123.a, the operator's P1.a, 18 Nov): an outline and sections as the
librarian serves them, each image where its mark stood, read from the EPUB's zip. Every test takes the invented EPUB the
core's own tests build: no licensed text, image or title stands here."""

import json

import pytest
from fastapi.testclient import TestClient
from test_diagnostics_app import LOCAL, a_licensed_export
from test_ingestion_epub_sections import an_epub

from backend.diagnostics import epub_works, readings, sources
from backend.diagnostics.app import create_app
from backend.ingestion.clean_sections.epub_sections import IMAGE_MARK
from backend.search import search_server

KEY = 'invented'


@pytest.fixture
def served(monkeypatch, tmp_path):
    """The invented EPUB as the one licensed EPUB work, beside the invented licensed export, with a catalog that lists it by
    its file; a provenance mark that strips one of its lines. Each test cuts it afresh."""
    path = an_epub(tmp_path)
    monkeypatch.setattr(epub_works, '_cut', {})
    monkeypatch.setattr(epub_works, 'epubs', lambda: {KEY: path})
    monkeypatch.setattr(search_server, 'stamps', lambda: ['a paragraph set as a div'])
    store = a_licensed_export(tmp_path / 'export')
    store.catalog = tmp_path / 'catalog.json'
    store.catalog.write_text(json.dumps({'sources': [{'id': 'invented_book', 'file': path.name, 'title': 'An Invented Book',
                                                      'format': 'epub', 'licence': 'private copy (licensed)'}]}), encoding='utf-8')
    monkeypatch.setattr(readings, 'licensed_readings', lambda: store)
    return path, TestClient(create_app(), base_url=LOCAL)


@pytest.fixture(autouse=True)
def export_folder(tmp_path):
    (tmp_path / 'export').mkdir()


@pytest.mark.corpus
@pytest.mark.readings
def test_an_epub_work_has_its_outline_and_sections_labelled_as_the_librarian_labels_them(served):
    path, client = served
    work = client.get(f'/api/licensed/epub/{KEY}').json()
    assert (work['title'], work['file'], work['route'], work['sections'], work['images'], work['licence']) == (
        'An Invented Book', path.name, 'epub, parsed by section', 3, 2, 'private copy (licensed)')
    # the labels a search hit names: the librarian's own pages of this EPUB
    pages = search_server.epub_pages(KEY, path, search_server.stamps())
    assert [row['label'] for row in work['rows']] == [page.page for page in pages] == ['s1', 's2', 's3']
    assert [(row['heading_path'], row['images']) for row in work['rows']] == [
        ('Chapter One', 2), ('Chapter One > A Subsection', 0), ('Chapter Two', 0)]
    titles = {node['title']: node for node in work['outline']}
    assert titles['A Subsection']['parent'] == titles['Chapter One']['id'] and titles['Chapter One']['last'] == 's2'


@pytest.mark.corpus
@pytest.mark.readings
def test_a_section_gives_its_text_in_runs_each_image_where_its_mark_stood(served):
    _, client = served
    section = client.get(f'/api/licensed/epub/{KEY}/sections/s1').json()
    assert (section['work_title'], section['heading_path'], section['previous'], section['next']) == (
        'An Invented Book', 'Chapter One', None, 's2')
    assert section['place'] == 'OEBPS/text/ch1.xhtml'
    kinds = [(part['kind'], (part['image'] or {}).get('inline')) for part in section['parts']]
    assert kinds == [('text', None), ('image', True), ('text', None), ('image', False)]
    text = ''.join(part['text'] for part in section['parts'] if part['kind'] == 'text')
    assert 'The return is ' in text and ' per year.' in text and IMAGE_MARK not in text
    # the line the provenance list marks is stripped, as the librarian strips it
    assert 'A paragraph set as a div.' not in text
    assert [part['image']['alt'] for part in section['parts'] if part['kind'] == 'image'] == ['eq1', '']
    assert client.get(f'/api/licensed/epub/{KEY}/sections/s3').json()['next'] is None
    assert client.get(f'/api/licensed/epub/{KEY}/sections/s9').status_code == 404


def test_a_mark_without_an_image_stays_out_rather_than_stand_as_a_broken_one():
    one = epub_works.EpubImage(href='a.png', alt='', inline=True)
    parts = epub_works.parts_of(f'a {IMAGE_MARK} b {IMAGE_MARK} c', [one])
    assert [(part.kind, part.text) for part in parts] == [('text', 'a '), ('image', None), ('text', ' b '), ('text', ' c')]


@pytest.mark.corpus
@pytest.mark.readings
def test_an_image_is_read_from_the_zip_by_a_path_its_sections_name_and_no_other_file(served):
    _, client = served
    answer = client.get(f'/api/licensed/epub/{KEY}/image', params={'href': 'OEBPS/images/eq.png'})
    assert answer.status_code == 200 and answer.content == b'\x89PNG' and answer.headers['content-type'] == 'image/png'
    for href in ('META-INF/container.xml', 'OEBPS/text/ch1.xhtml', 'OEBPS/images/none.png'):
        assert client.get(f'/api/licensed/epub/{KEY}/image', params={'href': href}).status_code == 404, href
    assert client.get('/api/licensed/epub/nothing').status_code == 404
    assert client.get(f'/api/free/epub/{KEY}').status_code == 404  # only the licensed knowledge base has EPUB works


@pytest.mark.corpus
@pytest.mark.readings
def test_the_sources_list_counts_an_epubs_sections_and_never_waits_for_the_cut(served, monkeypatch):
    path, client = served
    monkeypatch.setattr(epub_works, 'warm_in_background', lambda: None)  # the cut below, not in a thread
    def row():
        listed = [work for work in client.get('/api/works').json() if work['knowledge_base'] == 'licensed' and work['epub_key']]
        assert len(listed) == 1
        return listed[0]
    first = row()
    assert (first['title'], first['epub_key'], first['sections'], first['structure_why_not'], first['not_read']) == (
        'An Invented Book', KEY, None, sources.EPUB_COUNTING, None)
    epub_works.warm({KEY: path})
    assert (row()['sections'], row()['structure_why_not']) == (3, None)


def test_public_only_never_reaches_an_epub(monkeypatch):
    # 81.a by construction: the routes answer 404 before anything of an EPUB is read, and the list names none
    def refuse(*_):
        raise AssertionError('a public-only app reached a licensed EPUB')

    for name in ('epubs', 'cut', 'work', 'section', 'image', 'warm'):
        monkeypatch.setattr(epub_works, name, refuse)
    public = TestClient(create_app(public_only=True), base_url=LOCAL)
    for path in (f'/api/licensed/epub/{KEY}', f'/api/licensed/epub/{KEY}/sections/s1', f'/api/licensed/epub/{KEY}/image?href=x.png'):
        assert public.get(path).status_code == 404, path
    assert not any(work['epub_key'] for work in public.get('/api/works').json())
