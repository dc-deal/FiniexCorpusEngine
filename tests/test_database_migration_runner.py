"""The index database's migration runner (issue #10, part A): files checked before the schema is touched, each applied
once, in its own transaction, under a lock, and an edited applied file refused as drift."""
import shutil
import uuid
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from backend.database import migration_runner
from backend.database.migration_runner import MigrationError, MigrationFileError, MigrationRunner


def folder_with(tmp_path, files: dict[str, str]):
    folder = tmp_path / 'migrations'
    folder.mkdir()
    for name, body in files.items():
        (folder / name).write_bytes(body.encode('utf-8'))
    return folder


def test_the_files_are_found_in_version_order_and_anything_else_is_ignored(tmp_path):
    folder = folder_with(tmp_path, {'002_second.sql': 'SELECT 2;', '001_first.sql': 'SELECT 1;', 'notes.md': 'x',
                                    '3_short.sql': 'SELECT 3;'})
    found = MigrationRunner('unused', folder).discover()
    assert [(m.version, m.name, m.transactional) for m in found] == [('001', 'first', True), ('002', 'second', True)]


def test_a_version_used_twice_is_refused(tmp_path):
    folder = folder_with(tmp_path, {'001_a.sql': 'SELECT 1;', '001_b.sql': 'SELECT 2;'})
    with pytest.raises(MigrationFileError, match='used twice'):
        MigrationRunner('unused', folder).discover()


def test_a_no_transaction_file_holds_exactly_one_statement(tmp_path):
    one = folder_with(tmp_path, {'001_index.sql': '-- finiex:no-transaction\r\nCREATE INDEX CONCURRENTLY i ON t (x);'})
    assert MigrationRunner('unused', one).discover()[0].transactional is False
    shutil.rmtree(one)
    two = folder_with(tmp_path, {'001_index.sql': '-- finiex:no-transaction\nCREATE INDEX i ON t (x); SELECT 1;'})
    with pytest.raises(MigrationFileError, match='one statement'):
        MigrationRunner('unused', two).discover()


def test_a_missing_folder_is_refused(tmp_path):
    with pytest.raises(MigrationFileError, match='not found'):
        MigrationRunner('unused', tmp_path / 'none').discover()


def test_the_checksum_ignores_line_endings_but_not_an_edit():
    assert migration_runner.checksum('SELECT 1;\nSELECT 2;\n') == migration_runner.checksum('SELECT 1;\r\nSELECT 2;\r\n')
    assert migration_runner.checksum('SELECT 1;\n') != migration_runner.checksum('SELECT 1; \n')


def test_the_shipped_migrations_parse_and_count_up_from_001():
    found = MigrationRunner('unused').discover()
    assert [m.version for m in found] == [f'{number:03d}' for number in range(1, len(found) + 1)]


@pytest.fixture
def scratch_database():
    """A database of its own on the running server, dropped after: the real index is never touched."""
    from backend.database.database_url import database_url

    url = database_url()
    name = f'corpus_test_{uuid.uuid4().hex[:12]}'
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE {name}')
    parts = urlsplit(url)
    yield urlunsplit(parts._replace(path=f'/{name}'))
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS {name} WITH (FORCE)')


@pytest.mark.database
def test_the_shipped_migrations_apply_once_and_a_second_run_does_nothing(scratch_database):
    runner = MigrationRunner(scratch_database)
    assert [run.version for run in runner.apply()] == [m.version for m in runner.discover()]
    assert runner.apply() == [] and runner.status().pending == []
    with psycopg.connect(scratch_database) as connection:
        assert connection.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone() == (1,)


@pytest.mark.database
def test_a_failing_migration_leaves_nothing_behind(tmp_path, scratch_database):
    folder = folder_with(tmp_path, {'001_ok.sql': 'CREATE TABLE kept (x int);',
                                    '002_fails.sql': 'CREATE TABLE half (x int); SELECT 1 / 0;'})
    with pytest.raises(MigrationError, match='rolled back'):
        MigrationRunner(scratch_database, folder).apply()
    with psycopg.connect(scratch_database) as connection:
        assert connection.execute("SELECT to_regclass('kept') IS NOT NULL, to_regclass('half') IS NULL").fetchone() == (True, True)
        assert connection.execute('SELECT version FROM schema_migrations').fetchall() == [('001',)]


@pytest.mark.database
def test_an_applied_file_edited_afterwards_is_drift_and_refused(tmp_path, scratch_database):
    folder = folder_with(tmp_path, {'001_table.sql': 'CREATE TABLE t (x int);'})
    MigrationRunner(scratch_database, folder).apply()
    (folder / '001_table.sql').write_bytes(b'CREATE TABLE t (x bigint);')
    runner = MigrationRunner(scratch_database, folder)
    assert [m.version for m in runner.status().drifted] == ['001']
    with pytest.raises(MigrationFileError, match='changed after being applied'):
        runner.apply()


@pytest.mark.database
def test_a_no_transaction_migration_runs_outside_a_transaction(tmp_path, scratch_database):
    folder = folder_with(tmp_path, {'001_table.sql': 'CREATE TABLE t (x int);',
                                    '002_index.sql': '-- finiex:no-transaction\nCREATE INDEX CONCURRENTLY t_x ON t (x);'})
    assert [run.version for run in MigrationRunner(scratch_database, folder).apply()] == ['001', '002']
