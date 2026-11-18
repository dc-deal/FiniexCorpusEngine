import json

import pytest

from backend.conversion.reading import rollout
from backend.search import search_server, shelf
from test_search_server import a_licensed_shelf


def licensed_shelf(tmp_path, monkeypatch) -> dict:
    a_licensed_shelf(tmp_path, monkeypatch)
    plan = tmp_path / 'rollout'
    plan.mkdir()
    (plan / 'plan.json').write_text(json.dumps({'order': [{'file': 'book_a.pdf'}] * 3 + [{'file': 'book_c.pdf'}]}), encoding='utf-8')
    monkeypatch.setattr(rollout, 'FOLDER', plan)
    pages, works = search_server.licensed_pages()
    return {row['work'] or row['file']: row for row in shelf.licensed_rows(pages, works)}


def test_a_work_counts_what_was_planned_what_passed_why_the_rest_did_not_and_what_the_search_serves(tmp_path, monkeypatch):
    row = licensed_shelf(tmp_path, monkeypatch)['key-a']
    assert (row['file'], row['pages'], row['planned'], row['read'], row['passed']) == ('book_a.pdf', 3, 3, 3, 2)
    assert row['not_passed'] == {'issue': 1} and row['share_passed'] == 0.6667
    assert row['served'] == {'pages': 3, 'searchable': 3, 'from_readings': 2, 'by_route': {'legacy markdown': 1, 'vision reading': 2}}
    assert row['unplaced'] == {} and row['held'] is None and row['not_served'] is None


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


def test_the_table_replaces_only_its_block_and_a_milestone_adds_one_history_line(tmp_path, monkeypatch):
    rows = list(licensed_shelf(tmp_path, monkeypatch).values())
    shelves = {'licensed': {'built_at': '2026-11-08T22:00:00+00:00', 'works': rows, 'totals': shelf.totals(rows)}}
    target = tmp_path / 'status.md'
    target.write_text(f'# Head\n\nkept\n\n{shelf.START}\nold table\n{shelf.END}\n\n## History\n\n{shelf.HISTORY}\n| old |\n',
                      encoding='utf-8')
    shelf.into_markdown(target, shelves, milestone='a test')
    text = target.read_text(encoding='utf-8')
    assert text.startswith('# Head\n\nkept\n\n') and 'old table' not in text and '| licensed | key-a | book_a.pdf | 3 | 3 | 2 | 67% |' in text
    assert text.rstrip().splitlines()[-2] == '| old |' and '| a test | 4 | 4 | 2 |' in text.rstrip().splitlines()[-1]
    shelf.into_markdown(target, shelves)
    assert target.read_text(encoding='utf-8').count('| a test |') == 1


@pytest.mark.readings
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
