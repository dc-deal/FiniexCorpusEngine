"""A person promotes a Lab reading to the page's reading (#17, #18): a reason from a fixed list, appended, pinned like an
accept, the page protected, and refused for anything but a valid Lab reading of that page."""

import json
import sqlite3

import pytest

from backend.conversion.checks import human_verdict
from backend.conversion.store import pipeline_db, reading_export, reading_store, served_readings
from test_conversion_served_readings import page  # a minimal valid page reading


def record(key: str, **fields) -> dict:
    return {'kind': 'reading', 'reading_key': key, 'work': 'w', 'file': 'w_book.pdf', 'pdf_page': 2, 'model': 'claude-sonnet-5-5',
            'form': 'markdown', 'attempt': 0, 'image_size': [1688, 2184], 'result_type': 'succeeded', 'result_class': 'ok',
            **fields}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_db, 'PATHS', {'free': tmp_path / 'p.sqlite', 'licensed': tmp_path / 'l.sqlite'})
    store = reading_store.Store(tmp_path / 'vision')
    for key, cell in (('a' * 64, 'FREE-SM'), ('l' * 64, 'LAB-QWEN3VL-MP')):
        store.save_reading(key, record(key, cell=cell), page('::: {#b01 .paragraph bbox="10 50 900 120"}\nA.\n:::'))
    base = reading_export.KnowledgeBase('free', tmp_path / 'readings', tmp_path, lambda: ('FREE-SM',), tracked=True)
    return base, store


def test_a_promotion_needs_a_listed_reason_a_note_for_other_and_a_person(world):
    with pytest.raises(ValueError):
        pipeline_db.give_promotion('free', 'w_book.pdf', 2, 'l' * 64, 'feels right', 'maintainer')
    with pytest.raises(ValueError):
        pipeline_db.give_promotion('free', 'w_book.pdf', 2, 'l' * 64, 'other', 'maintainer')
    with pytest.raises(ValueError):
        pipeline_db.give_promotion('free', 'w_book.pdf', 2, 'l' * 64, 'better',
                                   pipeline_db.delegated_giver('claude-opus-5-5', '27 Nov'))
    assert set(pipeline_db.PROMOTE_REASON_SHORT) == set(pipeline_db.PROMOTE_REASONS)


def test_a_promotion_is_appended_never_changed(world):
    pipeline_db.give_promotion('free', 'w_book.pdf', 2, 'l' * 64, 'better', 'maintainer')
    with sqlite3.connect(pipeline_db.PATHS['free']) as db, pytest.raises(sqlite3.DatabaseError):
        db.execute("UPDATE promotions SET reason = 'other'")


def test_a_promoted_lab_reading_stands_until_a_later_act_of_a_person(world):
    base, store = world
    served = record('a' * 64, cell='FREE-SM')
    pipeline_db.give_promotion('free', 'w_book.pdf', 2, 'l' * 64, 'better', 'maintainer', note='reads the table')
    pinned = reading_export.with_people(base, store, [served])[0]
    assert pinned['reading_key'] == 'l' * 64 and pinned['promoted']['reason_short'] == 'better'
    assert pinned['deviation'] == reading_export.PROMOTED and pinned['pinned_by_a_person']
    pipeline_db.give_verdict('free', 'w_book.pdf', 2, 'a' * 64, 'accept', 'other', 'maintainer', note='the old one after all')
    assert reading_export.with_people(base, store, [served])[0]['reading_key'] == 'a' * 64  # the later act stands


def test_a_promoted_page_is_protected_from_being_read_again(world):
    # review, 27 Nov: the export said protected while every re-reading command read only the verdicts
    pipeline_db.give_promotion('free', 'w_book.pdf', 2, 'l' * 64, 'better', 'maintainer')
    assert pipeline_db.protected_pages('free')[('w_book.pdf', 2)]['verdict'] == 'promote'
    assert 'promote' in pipeline_db.refused_over_a_person('free', 'w_book.pdf', 2, None)
    assert pipeline_db.refused_over_a_person('free', 'w_book.pdf', 2, 'read it anew on purpose') is None


def test_an_accept_on_a_promoted_reading_keeps_it_promoted(world):
    base, store = world
    served = record('a' * 64, cell='FREE-SM')
    pipeline_db.give_promotion('free', 'w_book.pdf', 2, 'l' * 64, 'better', 'maintainer')
    pipeline_db.give_verdict('free', 'w_book.pdf', 2, 'l' * 64, 'accept', 'judge_false_alarm', 'maintainer')
    pinned = reading_export.with_people(base, store, [served])[0]
    assert pinned['reading_key'] == 'l' * 64 and pinned['promoted']['reason'] == 'better'
    assert pinned['deviation'] == reading_export.PROMOTED


def test_a_reading_promoted_again_after_a_reset_is_served_not_discarded(world):
    base, store = world
    served = record('a' * 64, cell='FREE-SM')
    pipeline_db.give_promotion('free', 'w_book.pdf', 2, 'l' * 64, 'better', 'maintainer')
    pipeline_db.give_reset('free', 'w_book.pdf', 2, 'l' * 64, 'look again', 'maintainer')
    pipeline_db.give_promotion('free', 'w_book.pdf', 2, 'l' * 64, 'served_wrong', 'maintainer')
    again = reading_export.with_people(base, store, [served])[0]
    assert again['reading_key'] == 'l' * 64 and 'reset' not in again and again['promoted']['reason'] == 'served_wrong'


def test_a_lab_reading_is_served_only_by_a_promotion_never_by_an_accept(world):
    base, _ = world
    _export_row(base, [{'reading_key': 'a' * 64, 'class_now': 'ok'},
                       {'reading_key': 'l' * 64, 'class_now': 'ok', 'prototype': True, 'test_reading': True}])
    with pytest.raises(ValueError, match='promote it'):
        human_verdict.record(base, 'w', 2, 'accept', 'judge_false_alarm', 'maintainer', reading_key='l' * 64)
    noted = human_verdict.record(base, 'w', 2, 'note', 'other', 'maintainer', note='looked at it', reading_key='l' * 64)
    assert noted['reading_key'] == 'l' * 64  # a remark on a Lab reading changes nothing and is kept


def test_the_pipeline_s_plan_refuses_test_cells():
    from types import SimpleNamespace

    from backend.conversion.checks import check_run

    with pytest.raises(SystemExit, match='judge-plan'):
        check_run.plan(SimpleNamespace(cells='LAB-QWEN3VL-MP'))


def test_a_promoted_reading_is_served_over_the_judge_and_its_route_says_so():
    row = {'text_file': 'w/p0002.md', 'class_now': 'ok', 'model': 'qwen', 'contract': 'page/1', 'validator': 'page/1.4',
           'check': {'state': 'issue'}, 'human': [],
           'promoted': {'reason': 'better', 'reason_text': pipeline_db.PROMOTE_REASONS['better'], 'note': None}}
    assert served_readings.text_layer_why(row) is None
    assert 'promoted from the Lab by a person' in served_readings.route_of(row)
    assert served_readings.text_layer_why({**row, 'class_now': 'malformed'}) == 'malformed'


def _export_row(base, attempts):
    base.export.mkdir(parents=True, exist_ok=True)
    row = {'work': 'w', 'file': 'w_book.pdf', 'pdf_page': 2, 'reading_key': 'a' * 64, 'route': 'vision reading', 'attempts': attempts}
    (base.export / 'index.json').write_text(json.dumps({'pages': [row]}), encoding='utf-8')


def test_only_a_valid_lab_reading_of_the_page_can_be_promoted(world):
    base, _ = world
    _export_row(base, [{'reading_key': 'a' * 64, 'class_now': 'ok'},
                       {'reading_key': 'l' * 64, 'class_now': 'ok', 'prototype': True, 'test_reading': True},
                       {'reading_key': 'm' * 64, 'class_now': 'malformed', 'prototype': True, 'test_reading': True}])
    with pytest.raises(ValueError, match='no Lab reading'):
        human_verdict.promote_record(base, 'w', 2, 'a' * 64, 'better', 'maintainer')  # the pipeline's own
    with pytest.raises(ValueError, match='malformed'):
        human_verdict.promote_record(base, 'w', 2, 'm' * 64, 'better', 'maintainer')
    made = human_verdict.promote_record(base, 'w', 2, 'l' * 64, 'only_one', 'maintainer')
    assert pipeline_db.promotions('free')[('w_book.pdf', 2)][0]['promotion_id'] == made['promotion_id']


def test_a_verdict_names_only_a_judgement_of_its_own_reading(world):
    base, _ = world
    _export_row(base, [{'reading_key': 'a' * 64, 'class_now': 'ok', 'judgements': [{'judgement_key': 'j' * 64}]}])
    with pytest.raises(ValueError, match='no judgement'):
        human_verdict.record(base, 'w', 2, 'accept', 'judge_false_alarm', 'maintainer', answers_judgement='x' * 64)
    made = human_verdict.record(base, 'w', 2, 'accept', 'judge_false_alarm', 'maintainer', answers_judgement='j' * 64)
    assert pipeline_db.human_verdicts('free')[('w_book.pdf', 2)][0]['answers_judgement'] == 'j' * 64 and made['verdict_id']
