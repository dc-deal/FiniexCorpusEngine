import json

import pytest

from backend.conversion.reading import rollout
from backend.search import search_server, shelf
from test_search_server import a_licensed_shelf


def licensed_shelf(tmp_path, monkeypatch) -> dict:
    a_licensed_shelf(tmp_path, monkeypatch)
    plan = tmp_path / 'rollout'
    plan.mkdir()
    order = [{'file': 'book_a.pdf', 'pdf_page': number} for number in (1, 2, 3)] + [{'file': 'book_c.pdf', 'pdf_page': 1}]
    (plan / 'plan.json').write_text(json.dumps({'order': order}), encoding='utf-8')
    monkeypatch.setattr(rollout, 'FOLDER', plan)
    pages, works = search_server.licensed_pages()
    return {row['work'] or row['file']: row for row in shelf.licensed_rows(pages, works)}


def test_a_work_counts_what_was_planned_what_passed_why_the_rest_did_not_and_what_the_search_serves(tmp_path, monkeypatch):
    row = licensed_shelf(tmp_path, monkeypatch)['key-a']
    assert (row['file'], row['pages'], row['planned'], row['read'], row['passed']) == ('book_a.pdf', 3, 3, 3, 2)
    assert row['not_passed'] == {'issue': 1} and row['share_passed'] == 0.6667
    assert row['served'] == {'pages': 3, 'searchable': 3, 'from_readings': 2, 'by_route': {'legacy markdown': 1, 'vision reading': 2}}
    assert row['unplaced'] == {} and row['held'] is None and row['not_served'] is None


def test_a_work_a_session_reads_whole_plans_every_page_of_its_file(tmp_path, monkeypatch):
    # found 19 Nov: a scan read whole in the session counted its pages as read and passed against nothing planned
    from backend.conversion.reading import reading_cells

    whole = tmp_path / 'direct_pages.json'
    # N5.a (20 Nov): the session's list names the pages it takes: a scan's every page, a born-digital work's structure pages
    listed = [{'file': 'book_c.pdf', 'pdf_page': 2}, {'file': 'book_a.pdf', 'pdf_page': 3}]  # book_a is no work taken whole
    whole.write_text(json.dumps({'added_works': ['book_c.pdf', 'gone.pdf'], 'pages': listed}), encoding='utf-8')
    monkeypatch.setattr(reading_cells, 'DIRECT_PAGES', {'licensed': whole})
    rows = licensed_shelf(tmp_path, monkeypatch)
    assert (rows['key-c']['pages'], rows['key-c']['planned']) == (2, 2)  # the plan's page 1 and the list's page 2
    assert rows['key-a']['planned'] == 3


def test_every_reason_the_serving_rule_knows_is_counted(monkeypatch):
    # 18 Nov: a fixed list of six left the pages a person or an automated review rejected out of every total
    from backend.conversion.store.served_readings import TEXT_LAYER_WHY

    monkeypatch.setattr(shelf, 'text_layer_why', lambda row: row['why'])
    counts = shelf.reading_counts({1: {'why': 'rejected_by_review'}, 2: {'why': 'rejected'}, 3: {'why': None}})
    assert counts == {'read': 3, 'passed': 1, 'not_passed': {'rejected': 1, 'rejected_by_review': 1}}
    assert set(shelf.REASONS) == set(TEXT_LAYER_WHY)


def test_a_passed_reading_the_search_cannot_serve_says_why(tmp_path, monkeypatch):
    rows = licensed_shelf(tmp_path, monkeypatch)
    assert rows['key-c']['unplaced'] == {shelf.NO_NUMBERS: 1} and rows['key-c']['served']['from_readings'] == 0
    alternate = rows['book_b__alt.pdf']
    assert alternate['work'] is None and alternate['not_served'] == shelf.BESIDE_LEGACY
    assert alternate['unplaced'] == {shelf.BESIDE_LEGACY: 1}
    assert rows['key-b']['format'] == 'legacy markdown' and rows['key-b']['served']['by_route'] == {'legacy markdown': 1}


def test_a_new_work_and_a_held_file_are_on_the_shelf_too(tmp_path, monkeypatch):
    rows = licensed_shelf(tmp_path, monkeypatch)
    assert rows['new_doc']['served']['by_route'] == {'text layer': 2} and rows['new_doc']['read'] == 0
    assert rows['new_doc']['planned'] is None and rows['new_doc']['share_passed'] is None
    assert rows['held.pdf']['held'] == shelf.HELD and rows['held.pdf']['served']['pages'] == 0


def test_the_totals_carry_their_shares_and_a_milestone_keeps_each_base_apart(tmp_path, monkeypatch):
    # X1.a (19 Nov): the shelf in the view, with percentages and a history, in place of a person's Markdown file
    from backend.configuration import data_paths

    rows = list(licensed_shelf(tmp_path, monkeypatch).values())
    total = shelf.totals(rows)
    assert total['share_passed'] == round(total['passed'] / total['planned'], 4) and total['share_read'] == round(total['read'] / total['planned'], 4)
    monkeypatch.setattr(data_paths, 'SHELF_HISTORY', tmp_path / 'history.json')
    shelves = {'licensed': {'totals': total}, 'free': {'totals': {'planned': 10, 'read': 10, 'passed': 9, 'share_passed': 0.9}}}
    shelf.add_milestone(shelves, 'a test')
    shelf.add_milestone(shelves, 'another')
    kept = shelf.history()['rows']
    assert [row['milestone'] for row in kept] == ['a test', 'another']
    assert kept[0]['bases']['free']['share_passed'] == 0.9 and kept[0]['bases']['licensed']['passed'] == total['passed']
    assert set(kept[0]['bases']['free']) == set(shelf.HISTORY_FIELDS)


def test_a_shelf_reason_is_by_construction_the_route_the_export_wrote_for_that_page():
    """Line 2 links a shelf count to its pages through each row's `route`. The export writes it from the reason the shelf counts
    (`route_of` of `text_layer_why`), so the two agree as long as the export was written by today's rule; this pins that for the
    tracked export, so a change to the rule without a new export fails here first."""
    from backend.conversion.store.served_readings import TEXT_LAYER_WHY, export_rows, route_of, text_layer_why

    rows = export_rows()
    assert rows, 'the tracked free export is missing'
    assert all(row['route'] == route_of(row) for row in rows)
    assert all(row['route'] == TEXT_LAYER_WHY[text_layer_why(row)] for row in rows if text_layer_why(row) is not None)
    assert len(set(TEXT_LAYER_WHY.values())) == len(TEXT_LAYER_WHY)  # one route per reason, so a route names its reason


def test_a_stand_in_serving_its_work_is_that_work_s_row_and_no_row_of_its_own(tmp_path, monkeypatch):
    a_licensed_shelf(tmp_path, monkeypatch)
    (tmp_path / 'stand_ins.json').write_text(json.dumps({'suffix': '__alt', 'works': ['key-b']}), encoding='utf-8')
    plan = tmp_path / 'rollout'
    plan.mkdir()
    (plan / 'plan.json').write_text(json.dumps({'order': []}), encoding='utf-8')
    monkeypatch.setattr(rollout, 'FOLDER', plan)
    pages, works = search_server.licensed_pages()
    rows = shelf.licensed_rows(pages, works)
    assert [row['file'] for row in rows if row['work'] == 'key-b'] == ['book_b__alt.pdf']
    assert [row for row in rows if row['work'] is None and row['file'] == 'book_b__alt.pdf'] == []
    assert next(row for row in rows if row['work'] == 'key-b')['served']['from_readings'] == 1


def test_a_shelf_names_the_export_it_was_built_from(tmp_path, monkeypatch):
    import hashlib

    export = tmp_path / 'readings'
    export.mkdir()
    (export / 'index.json').write_bytes(b'{"pages": []}')
    monkeypatch.setattr(search_server, 'EXPORT', export)
    monkeypatch.setattr(search_server, 'LICENSED_EXPORT', tmp_path / 'none')
    assert shelf.export_sha256('free') == hashlib.sha256(b'{"pages": []}').hexdigest()
    assert shelf.export_sha256('licensed') is None


def test_the_semantic_level_counts_each_source_s_chunks_and_the_pages_they_cover(tmp_path):
    # U1.a (20 Nov): the coverage ladder's semantic level, from the vector index's own database
    import sqlite3

    index_db = tmp_path / 'knowledge.sqlite3'
    with sqlite3.connect(index_db) as db:
        db.execute('CREATE TABLE chunks (id TEXT PRIMARY KEY, source_id TEXT, section_id TEXT, text TEXT, metadata TEXT)')
        db.executemany('INSERT INTO chunks VALUES (?, ?, ?, ?, ?)', [
            ('c1', 'book', 's1', 'a', json.dumps({'pdf_page': 3})), ('c2', 'book', 's1', 'b', json.dumps({'pdf_page': 3})),
            ('c3', 'book', 's2', 'c', json.dumps({'pdf_page': 4})), ('c4', 'site', 's9', 'd', json.dumps({}))])
    assert shelf.semantic_counts(index_db) == {'book': {'chunks': 3, 'pages': 2}, 'site': {'chunks': 1, 'pages': 0}}
    assert shelf.semantic_counts(tmp_path / 'none.sqlite3') == {}
