"""The pipeline database: runs measured from the stores, choices appended and never changed (decisions 51.a, 47.a)."""

import sqlite3

import pytest

from backend.conversion.store import pipeline_db, reading_export, reading_store


@pytest.fixture
def paths(tmp_path, monkeypatch):
    """Both databases outside the repository; the stores' spend and manifests stand still unless a test moves them."""
    spent = {'free': {'anthropic': 1.0, 'openrouter': 0.0}, 'licensed': {'anthropic': 2.0, 'openrouter': 0.0}}
    batches = {'msgbatch_old'}
    monkeypatch.setattr(pipeline_db, 'PATHS', {base: tmp_path / base / 'pipeline.sqlite' for base in ('free', 'licensed')})
    monkeypatch.setattr(pipeline_db, '_spent', lambda base: dict(spent[base]))
    monkeypatch.setattr(pipeline_db, '_batch_ids', lambda: set(batches))
    return spent, batches


def test_a_run_records_its_cost_its_batches_and_the_code_that_ran(paths):
    spent, batches = paths
    with pipeline_db.run(['free'], 'check_run submit --cells FREE-SM') as run:
        spent['free']['anthropic'] += 0.25
        batches.add('msgbatch_new')
    (row,) = pipeline_db.runs('free')
    assert row['run_id'] == run.run_id and row['outcome'] == 'ok' and row['cost_usd'] == pytest.approx(0.25)
    assert row['batch_ids'] == '["msgbatch_new"]' and len(row['code_sha256']) == 64 and row['code_commit']
    assert row['ended_at'] >= row['started_at']


def test_a_failed_run_is_recorded_as_failed_and_its_error_still_raised(paths):
    with pytest.raises(ValueError):
        with pipeline_db.run(['licensed'], 'rollout gates --round 4'):
            raise ValueError('a gate file is missing')
    (row,) = pipeline_db.runs('licensed')
    assert row['outcome'] == 'failed: ValueError' and row['ended_at']


def test_a_run_over_both_knowledge_bases_has_a_row_in_each_with_its_own_cost(paths):
    spent, _ = paths
    with pipeline_db.run(['free', 'licensed'], 'vision_batches collect --delete') as run:
        spent['licensed']['anthropic'] += 1.5
        spent['free']['openrouter'] += 0.1
    assert set(run.run_ids) == {'free', 'licensed'} and run.run_id is None
    (free,), (licensed,) = pipeline_db.runs('free'), pipeline_db.runs('licensed')
    assert free['cost_usd'] == pytest.approx(0.1) and licensed['cost_usd'] == pytest.approx(1.5)
    assert '"openrouter": 0.1' in free['cost_by_provider']


def test_a_choice_is_appended_and_the_latest_stands_while_the_history_stays(paths):
    pipeline_db.choose('free', 'a.pdf', 19, 'k1', why='second reader: anthropic blocked the page')
    pipeline_db.choose('free', 'a.pdf', 19, 'k2', why='replay --reread')
    assert pipeline_db.chosen('free')[('a.pdf', 19)]['reading_key'] == 'k2'
    assert [row['reading_key'] for row in pipeline_db.history('free', 'a.pdf', 19)] == ['k1', 'k2']
    assert pipeline_db.chosen('licensed') == {}


def test_a_run_s_choices_are_the_pages_that_run_chose_and_no_other(paths):
    # Line 2's request (5 Nov): a run's page in the runs view lists the pages it chose.
    with pipeline_db.run(['free'], 'replay reread --cap 0.10') as run:
        pipeline_db.choose('free', 'a.pdf', 19, 'k2', why='replay --reread', run_id=run.run_id)
        pipeline_db.choose('free', 'a.pdf', 20, 'k3', why='replay --reread', run_id=run.run_id)
    pipeline_db.choose('free', 'b.pdf', 4, 'k9', why='second reader: anthropic blocked the page')
    chosen = pipeline_db.choices('free', run.run_id)
    assert [(row['file'], row['pdf_page'], row['reading_key']) for row in chosen] == [('a.pdf', 19, 'k2'), ('a.pdf', 20, 'k3')]
    assert pipeline_db.choices('licensed', run.run_id) == []  # a knowledge base without a database yet


@pytest.fixture
def cells(monkeypatch):
    """One licensed round and the free corpus's cell, as the runner knows them; no private file is read."""
    from backend.conversion.reading import reading_cells

    known = {'LIC-R05': reading_cells.Cell('LIC-R05', 'm', 'hi', 'markdown', reading_cells.ROLLOUT / 'round_05.json'),
             'FREE-SM': reading_cells.Cell('FREE-SM', 'm', 'hi', 'markdown', reading_cells.MINI_PILOT)}
    monkeypatch.setattr(reading_cells, 'known_cells', lambda: known)
    return known


def test_a_batch_run_is_recorded_in_the_knowledge_bases_its_cells_read(cells):
    # Found by line 2 (5 Nov): every batch run went into both databases, so the free one listed licensed rounds.
    from argparse import Namespace

    from backend.conversion.reading import vision_batches

    assert vision_batches.run_bases(Namespace(command='submit', cells='LIC-R05')) == ['licensed']
    assert vision_batches.run_bases(Namespace(command='submit', cells='FREE-SM,LIC-R05')) == ['free', 'licensed']
    assert vision_batches.run_bases(Namespace(command='recheck', cells='FREE-SM')) == ['free']
    assert vision_batches.run_bases(Namespace(command='smoke')) == ['free']
    assert vision_batches.run_bases(Namespace(command='collect', delete=True)) == ['free', 'licensed']  # stores both mirrors
    assert vision_batches.run_bases(Namespace(command='submit', cells='NO-SUCH')) == ['free', 'licensed']


def test_a_run_recorded_before_the_fix_in_the_other_base_is_left_out_of_its_list(paths, cells):
    # The database is append-only, so the old rows stay; reading the runs leaves out those of the other knowledge base.
    for command in ('vision_batches submit --cells LIC-R05 --cap 95', 'vision_batches collect --delete', 'reading_export'):
        with pipeline_db.run(['free', 'licensed'], command):
            pass
    assert [row['command'] for row in pipeline_db.runs('free')] == ['vision_batches collect --delete', 'reading_export']
    assert len(pipeline_db.runs('licensed')) == 3


def test_the_database_itself_refuses_to_change_or_delete_a_choice(paths):
    pipeline_db.choose('free', 'a.pdf', 19, 'k1', why='replay --reread')
    db = pipeline_db.connect('free')
    with pytest.raises(sqlite3.IntegrityError, match='append-only'):
        db.execute("UPDATE chosen_readings SET reading_key = 'forged'")
    with pytest.raises(sqlite3.IntegrityError, match='append-only'):
        db.execute('DELETE FROM chosen_readings')
    db.close()


def test_the_database_is_never_made_where_git_tracks_it():
    with pytest.raises(reading_store.UnsafeRootError):
        pipeline_db.connect('free', reading_store.REPO / 'docs' / 'pipeline_probe.sqlite')
    assert not (reading_store.REPO / 'docs' / 'pipeline_probe.sqlite').exists()
    for path in pipeline_db.PATHS.values():  # a top-level folder git ignores (/_*/), or outside the repository (285.a)
        assert not path.is_relative_to(reading_store.REPO) or path.relative_to(reading_store.REPO).parts[0].startswith('_')


def test_the_export_serves_the_chosen_reading_and_says_why(paths, tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    latest = {'reading_key': 'k1', 'file': 'a.pdf', 'pdf_page': 19, 'model': 'claude-sonnet-5-5'}
    second = {'reading_key': 'k2', 'file': 'a.pdf', 'pdf_page': 19, 'model': 'openai/gpt-6.1-terra',
              'deviation': 'anthropic blocked the page (content filter)'}
    store.save_reading('k2', second, 'text')
    other = {'reading_key': 'k3', 'file': 'a.pdf', 'pdf_page': 20, 'model': 'claude-sonnet-5-5'}
    pipeline_db.choose('free', 'a.pdf', 19, 'k2', why='second reader: anthropic blocked the page')
    served = reading_export.with_choices(reading_export.FREE, store, [latest, other])
    assert served[0]['reading_key'] == 'k2' and served[0]['chosen']['why'].startswith('second reader')
    assert served[1] is other


def test_a_person_s_verdict_is_appended_checked_against_its_lists_and_never_changed(paths):
    first = pipeline_db.give_verdict('free', 'a.pdf', 5, 'k1', 'accept', 'judge_misread_name', 'maintainer', block='b12',
                                     tag='name_list')
    pipeline_db.give_verdict('free', 'a.pdf', 5, 'k1', 'note', 'other', 'maintainer', note='a list of sponsors')
    rows = pipeline_db.human_verdicts('free')[('a.pdf', 5)]
    assert [(row['verdict'], row['block'], row['tag']) for row in rows] == [('accept', 'b12', 'name_list'), ('note', None, None)]
    for verdict, reason, note in (('approve', 'other', 'x'), ('accept', 'because', None), ('reject', 'other', '  ')):
        with pytest.raises(ValueError):
            pipeline_db.give_verdict('free', 'a.pdf', 5, 'k1', verdict, reason, 'maintainer', note=note)
    with pipeline_db.connect('free') as db:
        for statement in ('UPDATE human_verdicts SET verdict = ? WHERE verdict_id = ?', 'DELETE FROM human_verdicts WHERE verdict_id = ?'):
            with pytest.raises(sqlite3.DatabaseError):
                db.execute(statement, ('reject', first) if 'UPDATE' in statement else (first,))


def test_a_person_s_correction_and_rating_of_the_judge_stand_beside_the_reading(paths):
    # decision 188.a (the operator, 10 Nov, finance p. 94): the description said "around 2000", the judge "2006-2007", the chart 2012
    pipeline_db.give_verdict('free', 'f.pdf', 94, 'k94', 'note', 'reading_wrong', 'maintainer', block='b05',
                             correction='… the blue line overtakes the red one around 2012 and ends higher …',
                             judge_assessment='right_for_a_wrong_reason')
    row = pipeline_db.human_verdicts('free')[('f.pdf', 94)][0]
    assert row['correction'].startswith('… the blue line') and row['judge_assessment'] == 'right_for_a_wrong_reason'
    bad = ({'judge_assessment': 'half right', 'block': 'b05'}, {'correction': 'text', 'block': None},
           {'correction': '  ', 'block': 'b05'})
    # a page-level assessment rates every finding of the page (finance p. 408: findings on b05 and b10)
    pipeline_db.give_verdict('free', 'f.pdf', 94, 'k94', 'accept', 'other', 'maintainer', note='all findings', judge_assessment='false_alarm')
    for fields in bad:
        with pytest.raises(ValueError):
            pipeline_db.give_verdict('free', 'f.pdf', 94, 'k94', 'note', 'reading_wrong', 'maintainer', **fields)


def test_a_database_made_before_the_manual_parts_gains_their_columns_and_keeps_its_rows(tmp_path):
    path = tmp_path / 'old.sqlite3'
    old = sqlite3.connect(path)
    old.executescript(pipeline_db.SCHEMA.replace(',\n    correction TEXT,\n    judge_assessment TEXT\n', '\n'))
    old.execute("INSERT INTO human_verdicts (knowledge_base, file, pdf_page, reading_key, verdict, reason, given_by, given_at) "
                "VALUES ('free', 'a.pdf', 5, 'k1', 'accept', 'judge_misread_name', 'maintainer', '2026-11-09')")
    old.commit()
    old.close()
    rows = pipeline_db.human_verdicts('free', path)[('a.pdf', 5)]
    assert rows[0]['verdict'] == 'accept' and rows[0]['correction'] is None and rows[0]['judge_assessment'] is None


def test_a_page_a_person_checked_is_protected_until_a_person_resets_it_with_a_reason(paths):
    # decision 191.a (the operator, 10 Nov): "pages a human corrected … are valuable"; a reset "always with a reason"
    pipeline_db.give_verdict('free', 'f.pdf', 94, 'k94', 'note', 'reading_wrong', 'maintainer', block='b05')
    assert ('f.pdf', 94) in pipeline_db.protected_pages('free')
    assert 'over-a-person' in pipeline_db.refused_over_a_person('free', 'f.pdf', 94, None)
    assert pipeline_db.refused_over_a_person('free', 'f.pdf', 94, 'the reader prompt changed for charts') is None
    assert pipeline_db.refused_over_a_person('free', 'f.pdf', 95, None) is None  # nobody checked p. 95
    with pytest.raises(ValueError):
        pipeline_db.give_reset('free', 'f.pdf', 94, 'k94', '   ', 'maintainer')
    pipeline_db.give_reset('free', 'f.pdf', 94, 'k94', 'read the chart again with its data', 'maintainer')
    assert ('f.pdf', 94) not in pipeline_db.protected_pages('free')
    pipeline_db.give_verdict('free', 'f.pdf', 94, 'k95', 'accept', 'other', 'maintainer', note='the new reading is right')
    assert pipeline_db.protected_pages('free')[('f.pdf', 94)]['reading_key'] == 'k95'  # a verdict after the reset protects again
    with pipeline_db.connect('free') as db:
        with pytest.raises(sqlite3.DatabaseError):
            db.execute('DELETE FROM page_resets')
