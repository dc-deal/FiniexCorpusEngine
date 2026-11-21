"""A page "as served", chunk first (the operator, 21 Nov): the page as the chunks semantic search holds of it, each a group of
the quoted blocks it holds in the form the search and the chat quote, placed by their text, never by an offset. Every page,
chunk and index here is invented, the route's test excepted, which takes a free page's own served text and invents the index
around it."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.conversion.contract import page_contract
from backend.diagnostics import page_chunks, page_ladder, readings
from backend.diagnostics.app import create_app
from backend.diagnostics.readings import Block
from test_diagnostics_readings import KELLY

LOCAL = 'http://127.0.0.1'


def a_block(block_id: str, served: str | None) -> Block:
    return Block(id=block_id, block_class='paragraph', group='content', content='V', attrs={}, bbox=None, segments=None, latex=None,
                 rows=None, code=None, text=served, findings=[], served=served)


# an invented page of three quoted blocks and one never quoted
BLOCKS = [a_block('b01', 'The bet grows the bankroll.'), a_block('b02', None), a_block('b03', 'A fraction of it is staked.'),
          a_block('b04', 'The rest is held back.')]
PAGE = 'The bet grows the bankroll.\n\nA fraction of it is staked.\n\nThe rest is held back.'


def an_index(path, chunks: list[tuple[str, str, str, dict]], sections: dict[str, str]):
    """An invented index in the core's shape: its sections' texts and its chunks, each (id, section, text, metadata)."""
    with sqlite3.connect(path) as db:
        db.execute('create table sections (id text primary key, source_id text, ordinal integer, heading_path text, url text, text text)')
        db.execute('create table chunks (id text primary key, source_id text, section_id text, text text, metadata text)')
        db.executemany('insert into sections (id, source_id, text) values (?, ?, ?)', [(key, 'a_work', text) for key, text in sections.items()])
        db.executemany('insert into chunks values (?, ?, ?, ?, ?)',
                       [(chunk_id, 'a_work', section, text, json.dumps(metadata)) for chunk_id, section, text, metadata in chunks])
    return path


def test_the_page_s_quoted_text_is_its_quoted_blocks_joined_as_the_core_joins_them():
    text, places = page_chunks.page_text(BLOCKS)
    assert text == PAGE
    assert [(block, text[start:end]) for block, start, end in places] == [
        ('b01', 'The bet grows the bankroll.'), ('b03', 'A fraction of it is staked.'), ('b04', 'The rest is held back.')]


def test_a_page_is_found_in_a_section_as_a_whole_at_its_end_at_its_start_or_holding_it():
    before, after = 'The page before ends here.\n\n', '\n\nThe next page begins.'
    assert page_chunks.page_part(before + PAGE + after, PAGE) == (len(before), len(before) + len(PAGE), 0)
    # a heading starts a new section mid page: the page's beginning ends one section, and the next begins on the page
    first, second = PAGE[:30], PAGE[30:]
    assert page_chunks.page_part(before + first, PAGE) == (len(before), len(before) + len(first), 0)
    assert page_chunks.page_part(second + after, PAGE) == (0, len(second), 30)
    # a whole section on the page; and a section holding none of it
    assert page_chunks.page_part('A fraction of it is staked.', PAGE) == (0, len('A fraction of it is staked.'), 29)
    assert page_chunks.page_part('Another text altogether.', PAGE) is None


def runs_of(block: page_chunks.ChunkBlock) -> tuple:
    return block.block, block.part, [(run.text, run.shared) for run in block.runs]


def test_each_chunk_is_a_group_of_the_blocks_it_holds_a_split_block_in_both_and_their_overlap_in_both(tmp_path):
    before, after = 'The page before ends here.\n\n', '\n\nThe next page begins.'
    section = before + PAGE + after
    # A runs in from p. 6 and ends inside b01; B shares its last word and holds the rest of b01 and all of b03; C runs on to
    # p. 8; the fourth stands in no page of the section
    chunks = [('c1', 's1', 'ends here.\n\nThe bet grows', {'pdf_page': 6, 'pdf_page_end': 7, 'tokens': 6}),
              ('c2', 's1', 'grows the bankroll.\n\nA fraction of it is staked.', {'pdf_page': 7, 'tokens': 11}),
              ('c3', 's1', 'The rest is held back.\n\nThe next page', {'pdf_page': 7, 'pdf_page_end': 8, 'tokens': 8}),
              ('c4', 's1', 'A sentence no page of it holds.', {'pdf_page': 7, 'tokens': 6})]
    database = an_index(tmp_path / 'index.sqlite3', chunks, {'s1': section})
    answer = page_chunks.page_chunks('free', 'a_work', 7, BLOCKS, database, 'a_work', 'not in the index')
    assert answer.head_said == 'this page lies in 3 chunks: A runs in from p. 6; B, C begin here'
    assert [(group.letter, group.id, group.head) for group in answer.groups] == [
        ('A', 'c1', ['runs in from p. 6', '25 characters', 'pp. 6–7']),
        ('B', 'c2', ['48 characters', 'p. 7', 'shares 5 characters with A']),
        ('C', 'c3', ['37 characters', 'pp. 7–8', 'runs on to p. 8'])]
    a, b, c = answer.groups
    # the block A splits stands in both with its part, the word the two share in both and marked shared
    assert [runs_of(block) for block in a.blocks] == [('b01', True, [('The bet ', False), ('grows', True)])]
    assert [runs_of(block) for block in b.blocks] == [('b01', True, [('grows', True), (' the bankroll.', False)]),
                                                     ('b03', False, [('A fraction of it is staked.', False)])]
    assert [runs_of(block) for block in c.blocks] == [('b04', False, [('The rest is held back.', False)])]
    # the block never quoted is in no chunk and nowhere in the mode; all the quoted text is in a chunk
    assert 'b02' not in {block.block for group in answer.groups for block in group.blocks} and answer.outside == []
    assert answer.not_placed == '1 chunk of this page could not be placed in its quoted text'
    assert (a.runs_in_from, a.runs_on_to, b.shares, b.shares_with, c.runs_on_to) == (6, None, 5, 'A', 8)


def test_quoted_text_no_chunk_holds_is_listed_apart_and_a_kept_edition_s_chunks_say_they_are_held_back(tmp_path):
    database = an_index(tmp_path / 'index.sqlite3', [('c1', 's1', 'The bet grows the bankroll.', {'pdf_page': 7})], {'s1': PAGE})
    answer = page_chunks.page_chunks('free', 'a_work', 7, BLOCKS, database, 'a_work', 'not in the index',
                                     held_back='held back from the search')
    assert answer.groups[0].head == ['27 characters', 'p. 7', 'kept: held back from the search']
    assert [runs_of(block) for block in answer.outside] == [('b03', False, [('A fraction of it is staked.', False)]),
                                                           ('b04', False, [('The rest is held back.', False)])]
    assert answer.head_said == 'this page lies in 1 chunk: A begins here'


def test_a_page_with_no_chunk_or_no_index_says_why_and_still_shows_its_quoted_blocks(tmp_path):
    database = an_index(tmp_path / 'index.sqlite3', [], {})
    answer = page_chunks.page_chunks('free', 'a_work', 7, BLOCKS, database, 'a_work', 'not in the index', held_back='held back from the search')
    assert (answer.said, answer.groups, answer.head_said, answer.held_back) == (
        'no chunk of this page', [], None, 'held back from the search')
    assert [(block.block, block.part, block.runs[0].text) for block in answer.outside] == [
        (block.id, False, block.served) for block in BLOCKS if block.served]
    gone = page_chunks.page_chunks('licensed', 'a_work', 7, BLOCKS, tmp_path / 'none.sqlite3', 'a_work', 'not vectorised yet (#8)')
    assert gone.said == 'not vectorised yet (#8)'
    assert [page_chunks.letter(number) for number in (1, 26, 27, 28)] == ['A', 'Z', 'AA', 'AB']


def test_a_block_carries_the_form_the_search_and_the_chat_quote_and_a_block_never_quoted_none():
    # invented: a formula, its description, a definition and a list item, as a reader writes them
    text = ('::: {#b01 .formula label="1"}\nf^* = p - q/b\n:::\n\n::: {#b02 .description of="b01"}\nA formula giving the bet.\n:::\n\n'
            '::: {#b03 .glossary_entry term="Kelly fraction"}\nthe share of the bankroll bet.\n:::\n\n'
            '::: {#b04 .list_item marker="1."}\nStake the fraction.\n:::\n')
    parsed = page_contract.parse(text, 'markdown')
    served = {block.id: readings.block_of(block, []).served for block in parsed.blocks}
    assert served == {'b01': '\\[ f^* = p - q/b \\] (1)', 'b02': None, 'b03': 'Kelly fraction: the share of the bankroll bet.',
                      'b04': '1. Stake the fraction.'}


def test_each_page_level_has_its_shortest_words_and_a_fallback_its_name():
    served = page_ladder.PageRung(level='text served', reached=True, said='its own text')
    assert page_ladder.keyword(None, served, False)[0].short == 'BM25 being built after a start'
    assert page_ladder.chunks_said(2, 'page').short == '2 chunks' and page_ladder.chunks_said(0, 'page').short == 'no chunk'
    assert page_ladder.unknown_semantic('not vectorised yet (#8)').short == 'not vectorised'
    unread = {'unread': {'served_by': 'text layer', 'said': "served from the PDF's text layer", 'planned': True}}
    assert (page_ladder.served(unread).short, page_ladder.served_by(unread), page_ladder.reading(unread).short) == (
        'text layer', "the PDF's text layer", 'planned')


@pytest.mark.readings
def test_the_route_places_a_free_page_s_chunks_in_its_own_served_text(tmp_path, monkeypatch):
    # the page's own served text, as the API gives it, and an index invented around it: one chunk the page holds whole
    client = TestClient(create_app(public_only=True), base_url=LOCAL)
    blocks = [Block.model_validate(block) for block in client.get(f'/api/free/works/{KELLY}/pages/1').json()['reading']['blocks']]
    text, _ = page_chunks.page_text(blocks)
    chunk = text[:min(len(text), 80)]
    database = an_index(tmp_path / 'index.sqlite3', [('k1', 'k:0000', chunk, {'pdf_page': 1})], {'k:0000': text})
    with sqlite3.connect(database) as db:
        db.execute('update chunks set source_id = ?', (KELLY,))
    monkeypatch.setitem(page_ladder.INDEX_DB, 'free', lambda: database)
    answer = client.get(f'/api/free/works/{KELLY}/pages/1/chunks').json()
    assert [(one['letter'], one['characters']) for one in answer['groups']] == [('A', len(chunk))]
    assert answer['groups'][0]['blocks'][0]['block'] == next(block.id for block in blocks if block.served)
    assert client.get(f'/api/free/works/{KELLY}/pages/99999/chunks').status_code == 404
