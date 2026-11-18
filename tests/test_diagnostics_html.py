"""The HTML works (the operator's 6.a): the outline from the heading paths (a heading without text of its own is a node without a
label, a work's only top node that is its title gives way to its children), a section's chunks found in its text with
their overlaps and a miss counted, the empty state where the index is not built, and the Sources column's structure.
An index is invented in a temporary folder over catalog ids; the real index, where this machine has one, is checked too."""

import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.diagnostics import html_works
from backend.diagnostics.app import create_app

# TestClient's own host, "testserver", is refused like any other name that is not this machine's (app.TRUSTED_HOSTS)
LOCAL = 'http://127.0.0.1'

WIKIPEDIA = 'wikipedia_trading_set'
LEFEVRE = 'lefevre_reminiscences_of_a_stock_operator'
TEXT = ' '.join(f'w{number}' for number in range(60))  # no passage repeats, as in prose


def an_index(path, sections_by_work):
    """An index in the core's schema: each work's sections in order, each section's chunks as (text) slices of it."""
    connection = sqlite3.connect(path)
    connection.executescript("""
        create table sources (id text primary key, title text, authors text, shelf text, format text, licence text,
            licence_url text, fingerprint text, indexed_at text, sections integer, chunks integer, tokens integer);
        create table sections (id text primary key, source_id text, ordinal integer, heading_path text, url text,
            anchor text, pdf_page_first integer, printed_page_first integer, text text);
        create table chunks (id text primary key, source_id text, section_id text, text text, metadata text);
    """)
    for source, sections in sections_by_work.items():
        total = 0
        for ordinal, (heading_path, text, chunk_texts) in enumerate(sections):
            section_id = f'{source}:{ordinal:04d}'
            connection.execute('insert into sections values (?, ?, ?, ?, ?, ?, null, null, ?)',
                               (section_id, source, ordinal, heading_path, f'https://example.org/{source}#{ordinal}', None, text))
            for number, chunk in enumerate(chunk_texts):
                connection.execute('insert into chunks values (?, ?, ?, ?, ?)', (f'{section_id}:{number:03d}', source, section_id,
                                                                                  chunk, json.dumps({'tokens': len(chunk) // 4})))
            total += len(chunk_texts)
        connection.execute("insert into sources values (?, ?, 'invented', 'trading_finance', 'html', 'CC BY-SA 4.0', "
                           "'https://example.org/licence', '', '', ?, ?, 0)", (source, source, len(sections), total))
    connection.commit()
    connection.close()
    return path


@pytest.fixture
def index(tmp_path, monkeypatch):
    database = an_index(tmp_path / 'knowledge.sqlite3', {
        WIKIPEDIA: [
            ('Algorithmic trading', 'An introduction.', ['An introduction.']),
            ('Algorithmic trading > History > Early developments', TEXT, [TEXT[:120], TEXT[100:]]),  # 20 characters shared
            ('Algorithmic trading > History > Recent developments', 'Later.', ['Later.', 'not in the text']),
            ('Algorithmic trading > Strategies > Pairs trading', 'Two stocks.', ['Two stocks.']),
        ],
        LEFEVRE: [
            ('REMINISCENCES OF A STOCK OPERATOR', 'Front matter.', ['Front matter.']),
            ('REMINISCENCES OF A STOCK OPERATOR > I', 'Chapter one.', ['Chapter one.']),
            ('REMINISCENCES OF A STOCK OPERATOR > II', 'Chapter two.', ['Chapter two.']),
        ],
    })
    monkeypatch.setattr(html_works, 'DATABASE', database)
    # the invented index is not what the raw files hold: no stripped original unless a test gives one
    monkeypatch.setattr(html_works, 'stripped_of', lambda source_id: None)
    return database


def stripped(sections, dropped):
    """Line 1's `strip_source` answer in its shape, invented."""
    return ([SimpleNamespace(ordinal=ordinal, html=html) for ordinal, html in sections],
            [SimpleNamespace(heading=heading, after_ordinal=after, html=html) for heading, after, html in dropped])


def test_a_section_stands_beside_its_stripped_original_and_a_dropped_heading_greyed_at_its_place(index, monkeypatch):
    monkeypatch.setattr(html_works, 'stripped_of', lambda source_id: stripped(
        [(1, '<h3 id="Early">Early developments</h3><p>w0 w1</p>')],
        [('See also', 3, '<h2 id="See_also">See also</h2><ul><li>x</li></ul>'), ('References', 3, '<h2>References</h2>')]))
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    outline = client.get(f'/api/free/html/{WIKIPEDIA}').json()['outline']
    titles = [(node['title'], node['dropped'], node['parent']) for node in outline]
    root = outline[0]['id']
    # after the section they follow (s4, Pairs trading), in document order, under the article it belongs to
    assert titles[-2:] == [('See also', 'd1', root), ('References', 'd2', root)]
    section = client.get(f'/api/free/html/{WIKIPEDIA}/sections/s2').json()
    assert section['original'].startswith('<h3 id="Early">') and section['original_why_not'] is None
    dropped = client.get(f'/api/free/html/{WIKIPEDIA}/sections/d1').json()
    assert (dropped['dropped'], dropped['chunks'], dropped['heading_path'], dropped['next']) == (True, [], 'See also', 'd2')
    assert client.get(f'/api/free/html/{WIKIPEDIA}/sections/d3').status_code == 404


def test_without_the_raw_file_a_section_says_how_to_fetch_it(index):
    section = TestClient(create_app(public_only=True), base_url=LOCAL).get(f'/api/free/html/{WIKIPEDIA}/sections/s1').json()
    assert section['original'] is None and 'backend.ingestion.acquire' in section['original_why_not']


def test_the_outline_is_built_from_the_heading_paths_a_heading_without_text_a_node_without_a_label(index):
    work = TestClient(create_app(public_only=True), base_url=LOCAL).get(f'/api/free/html/{WIKIPEDIA}').json()
    assert (work['sections'], work['chunks'], work['route']) == (4, 6, 'html, parsed by section')
    by_title = {node['title']: node for node in work['outline']}
    root, history = by_title['Algorithmic trading'], by_title['History']
    assert (root['label'], root['first'], root['last'], root['sections'], root['chunks']) == ('s1', 's1', 's4', 4, 6)
    # rule 4: History and Strategies hold no text of their own, so they carry no label, only their range and counts
    assert (history['label'], history['parent'], history['first'], history['last'], history['sections']) == (None, root['id'], 's2', 's3', 2)
    assert by_title['Strategies']['label'] is None and by_title['Pairs trading']['label'] == 's4'
    assert [node['title'] for node in work['outline']] == ['Algorithmic trading', 'History', 'Early developments',
                                                           'Recent developments', 'Strategies', 'Pairs trading']
    assert [row['label'] for row in work['rows']] == ['s1', 's2', 's3', 's4'] and work['rows'][1]['characters'] == len(TEXT)


def test_a_works_only_top_node_that_is_its_title_gives_way_to_its_children(index):
    work = TestClient(create_app(public_only=True), base_url=LOCAL).get(f'/api/free/html/{LEFEVRE}').json()
    roots = [(node['title'], node['label'], node['level']) for node in work['outline'] if node['parent'] is None]
    # the title keeps its own text as a node; the chapters stand beside it at the top
    assert roots == [('REMINISCENCES OF A STOCK OPERATOR', 's1', 1), ('I', 's2', 1), ('II', 's3', 1)]


def test_a_sections_chunks_are_found_in_its_text_their_overlap_measured_a_miss_counted(index):
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    early = client.get(f'/api/free/html/{WIKIPEDIA}/sections/s2').json()
    assert early['heading_path'] == 'Algorithmic trading > History > Early developments' and early['text'] == TEXT
    assert [(c['number'], c['start'], c['end'], c['overlap']) for c in early['chunks']] == [(1, 0, 120, 0), (2, 100, len(TEXT), 20)]
    assert (early['previous'], early['next'], early['not_found'], early['licence']) == ('s1', 's3', 0, 'CC BY-SA 4.0')
    # the splitter the overlap comes from, as the index's chunking names it, for the view's legend
    from backend.ingestion import chunking
    assert early['splitter'] == chunking.splitting_config()
    recent = client.get(f'/api/free/html/{WIKIPEDIA}/sections/s3').json()
    assert recent['not_found'] == 1 and recent['chunks'][1]['start'] is None  # shown, not hidden
    assert client.get(f'/api/free/html/{WIKIPEDIA}/sections/s9').status_code == 404
    assert client.get(f'/api/free/html/{WIKIPEDIA}/sections/x1').status_code == 404


def test_an_article_stands_whole_its_sections_and_dropped_headings_in_the_works_order(index, monkeypatch):
    monkeypatch.setattr(html_works, 'stripped_of', lambda source_id: stripped(
        [(1, '<h3 id="Early">Early developments</h3><p>w0 w1</p>')], [('See also', 3, '<h2 id="See_also">See also</h2>')]))
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    # asked by any of its sections, the article is the same: its top unit whole
    whole = client.get(f'/api/free/html/{WIKIPEDIA}/articles/s3').json()
    assert whole['title'] == 'Algorithmic trading' and whole['label'] == 's3'
    assert [(entry['label'], entry['title'], entry['level']) for entry in whole['entries']] == [
        ('s1', 'Algorithmic trading', 1), (None, 'History', 2), ('s2', 'Early developments', 3),
        ('s3', 'Recent developments', 3), (None, 'Strategies', 2), ('s4', 'Pairs trading', 3), ('d1', 'See also', 2)]
    entries = {entry['label']: entry for entry in whole['entries']}
    # each section with its chunks and its original, a heading without text of its own with nothing, a dropped one greyed
    assert [chunk['number'] for chunk in entries['s2']['section']['chunks']] == [1, 2]
    assert entries['s2']['section']['original'].startswith('<h3 id="Early">')
    assert entries[None]['section'] is None
    assert entries['d1']['section']['dropped'] is True
    assert client.get(f'/api/free/html/{WIKIPEDIA}/articles/d1').json()['entries'] == whole['entries']
    assert (whole['previous'], whole['next']) == (None, None)  # one article only in the invented index
    assert client.get(f'/api/free/html/{WIKIPEDIA}/articles/s9').status_code == 404


def test_a_book_in_one_file_opens_chapter_by_chapter_with_its_neighbours(index):
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    chapter = client.get(f'/api/free/html/{LEFEVRE}/articles/s2').json()
    assert (chapter['title'], [entry['label'] for entry in chapter['entries']]) == ('I', ['s2'])
    assert (chapter['previous'], chapter['next']) == ('s1', 's3')
    assert (chapter['previous_title'], chapter['next_title']) == ('REMINISCENCES OF A STOCK OPERATOR', 'II')
    assert chapter['licence'] == 'CC BY-SA 4.0'


def test_only_an_html_work_of_the_free_catalog_has_this_view(index):
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    assert client.get('/api/free/html/carta_conversano_kelly_criterion_2020').status_code == 404  # a PDF
    assert client.get(f'/api/licensed/html/{WIKIPEDIA}').status_code == 404


def test_without_the_index_every_html_answer_says_how_to_build_it(tmp_path, monkeypatch):
    monkeypatch.setattr(html_works, 'DATABASE', tmp_path / 'absent.sqlite3')
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    work = client.get(f'/api/free/html/{WIKIPEDIA}').json()
    assert work['why_not'] == html_works.NOT_BUILT and work['outline'] == [] and 'backend.ingestion.build' in work['why_not']
    section = client.get(f'/api/free/html/{WIKIPEDIA}/sections/s1')
    assert section.status_code == 404 and section.json()['detail'] == html_works.NOT_BUILT
    listed = {work['id']: work for work in client.get('/api/works').json()}
    assert listed[WIKIPEDIA]['structure_why_not'] == html_works.NOT_BUILT and listed[WIKIPEDIA]['sections'] is None


@pytest.mark.readings
def test_sources_give_an_html_work_its_sections_and_chunks_and_a_pdf_none(index):
    listed = {work['id']: work for work in TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/works').json()}
    assert (listed[WIKIPEDIA]['sections'], listed[WIKIPEDIA]['chunks'], listed[WIKIPEDIA]['structure_why_not']) == (4, 6, None)
    kelly = listed['carta_conversano_kelly_criterion_2020']
    assert kelly['sections'] is None and kelly['readings']['pages'] > 0


@pytest.mark.skipif(not html_works.DATABASE.is_file(), reason='no search index on this machine, as on a clone')
def test_on_the_real_index_the_verified_cases_hold_and_no_chunk_is_lost():
    from backend.diagnostics import sources
    titles = {work.id: work.title for work in sources.works() if work.format == 'html'}
    wikipedia = html_works.work(WIKIPEDIA, titles[WIKIPEDIA])
    by_id = {node.id: node for node in wikipedia.outline}
    unlabelled = {f'{by_id[node.parent].title} > {node.title}' for node in wikipedia.outline if node.label is None and node.parent}
    assert {'Algorithmic trading > History', 'Algorithmic trading > Strategies', 'Bid-ask spread > Types of spreads'} <= unlabelled
    assert len([node for node in wikipedia.outline if node.parent is None]) == 11
    lefevre = html_works.work(LEFEVRE, titles[LEFEVRE]).outline
    assert len([node for node in lefevre if node.parent is None and not node.dropped]) == 25
    # the dropped headings, greyed at their place: Wikipedia's References, See also and the like, Lefèvre's CONTENTS
    assert len([node for node in wikipedia.outline if node.dropped]) == 32 and len([node for node in lefevre if node.dropped]) == 1
    assert html_works.section(WIKIPEDIA, 's1', titles[WIKIPEDIA]).original
    missed = 0
    for source_id, title in titles.items():
        for row in html_works.work(source_id, title).rows:
            missed += html_works.section(source_id, row.label, title).not_found
    assert missed == 0  # every chunk's text stands in its section's text
