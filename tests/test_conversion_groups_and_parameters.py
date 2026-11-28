"""Reading groups (52.a) and the registry of models and parameters (53.a), first part: groups are append-only and a reading in
none is the root's; a parameter set must be registered before a reading names it, and an older reading gets its set by its
cell, marked derived."""

import sqlite3

import pytest

from backend.conversion.reading import parameter_sets
from backend.conversion.store import pipeline_db


def test_a_group_is_made_once_filled_without_doubles_and_never_changed(tmp_path):
    db = tmp_path / 'pipeline.sqlite'
    pipeline_db.create_group('free', 'night-2026-11-26', 'Night of 26 Nov', 'four local readers', 'line 1', path=db)
    with pytest.raises(ValueError):
        pipeline_db.create_group('free', 'night-2026-11-26', 'again', 'again', 'line 1', path=db)
    with pytest.raises(ValueError):
        pipeline_db.create_group('free', 'Not A Slug', 'x', 'y', 'line 1', path=db)
    assert pipeline_db.add_to_group('free', 'night-2026-11-26', ['a', 'b', 'a'], path=db) == 2
    assert pipeline_db.add_to_group('free', 'night-2026-11-26', ['b', 'c'], path=db) == 1
    assert pipeline_db.reading_groups('free', path=db)[0]['readings'] == 3
    assert pipeline_db.groups_of_readings('free', path=db) == {'a': ['night-2026-11-26'], 'b': ['night-2026-11-26'],
                                                               'c': ['night-2026-11-26']}
    with pytest.raises(ValueError):
        pipeline_db.add_to_group('free', 'no-such-group', ['a'], path=db)
    with pipeline_db.connect('free', db) as connection, pytest.raises(sqlite3.DatabaseError):
        connection.execute("UPDATE reading_groups SET name = 'x'")
    with pipeline_db.connect('free', db) as connection, pytest.raises(sqlite3.DatabaseError):
        connection.execute('DELETE FROM reading_group_members')


def test_no_group_is_an_empty_root(tmp_path):
    assert pipeline_db.reading_groups('free', path=tmp_path / 'none.sqlite') == []
    assert pipeline_db.groups_of_readings('free', path=tmp_path / 'none.sqlite') == {}


def test_an_unregistered_parameter_set_is_refused_and_a_registered_one_is_named_with_its_hash():
    with pytest.raises(ValueError):
        parameter_sets.require('no-such-set/1')
    named = parameter_sets.require('paddleocr-vl-pipeline/1')
    assert named['version'] == 'paddleocr-vl-pipeline/1' and len(named['sha256']) == 64


def test_every_set_names_a_registered_model_and_host_and_a_known_state():
    for version, entry in parameter_sets.sets().items():
        parameter_sets.require(version)
        assert entry['state'] in parameter_sets.STATES, version


def test_an_older_reading_gets_its_set_by_its_cell_marked_derived_and_a_named_one_wins():
    derived = parameter_sets.of_record({'cell': 'LAB-PADDLE-MP'})
    assert derived['version'] == 'paddleocr-vl-page/1' and derived['derived'] == 'by its cell'
    named = {'version': 'paddleocr-vl-pipeline/1', 'sha256': 'a' * 64}
    assert parameter_sets.of_record({'cell': 'LAB-PADDLE-MP', 'parameter_set': named}) == named
    assert parameter_sets.of_record({'cell': 'MP-SM'}) is None  # the pipeline's sets follow in the issue's second part


def test_a_retired_set_says_its_known_limits():
    assert parameter_sets.sets()['paddleocr-vl-page/1']['limits']
