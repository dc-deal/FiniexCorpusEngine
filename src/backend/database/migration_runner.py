"""Versioned schema migrations for the index database (issue #10, part A): pending SQL files applied exactly once, in order.

Ported from the RAG engine's runner (its ISSUE_14, the app park's sibling), whose design carries over unchanged:

- **Discovery:** `migrations/NNN_name.sql` beside this module, applied in version order; any other file is ignored.
- **The lock:** a session-level `pg_advisory_lock` around the whole pass, so two processes starting at once (the librarian
  and the view are separate containers) cannot apply a file twice; the second waits, then finds nothing pending.
- **One transaction per file:** PostgreSQL's DDL is transactional, so a failing migration leaves nothing half-applied;
  the file and its ledger row commit together or not at all.
- **The escape hatch:** a file with the line `-- finiex:no-transaction` runs on an autocommit connection, for the
  statements PostgreSQL refuses inside a transaction (`CREATE INDEX CONCURRENTLY`); such a file holds one statement.
- **Checksums:** an applied file that changed on disk is drift, refused loudly: an applied migration is immutable, a
  change is a new migration.

Two changes from the port: a file is read as UTF-8 bytes, and its checksum is taken with line endings as `\n`, so a
checkout that turns them into `\r\n` (Windows) is no drift; the errors are this module's own.

**Why not a maintained runner** (the project's rule: a maintained component before own code). Checked on 22 Nov 2026,
with a second opinion: **Alembic 1.20.1** (22 Oct 2026) is maintained and runs plain SQL through `op.execute`, but
brings SQLAlchemy and Mako, an `env.py`, a script template and a Python wrapper per migration, for its strengths
(migrations generated from ORM models, downgrade graphs, many dialects) that this database uses none of: raw psycopg,
forward-only, PostgreSQL alone. **yoyo-migrations 9.0.0** fits plain SQL files but has had no release since 10 Aug 2024.
Neither fails; their cost is the shortcoming, and the operator accepted that reading (decision 1.b, 22 Nov 2026).
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import psycopg

from backend.constants.database_constants import MIGRATIONS_TABLE

MIGRATIONS = Path(__file__).parent / 'migrations'
FILENAME = re.compile(r'^(\d{3})_([a-z0-9_]+)\.sql$')  # `001_extensions.sql`: version '001', name 'extensions'
LOCK_KEY = 0x46434F52  # 'FCOR': one fixed key, so every process takes the same lock; other advisory locks are unaffected
NO_TRANSACTION = re.compile(r'^[ \t]*--[ \t]*finiex:no-transaction[ \t\r]*$', re.MULTILINE)
LINE_COMMENT = re.compile(r'--[^\n]*')
BLOCK_COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
CONNECT_TIMEOUT_SECONDS = 10


class MigrationError(RuntimeError):
    """A migration could not be applied, or the database could not be reached."""


class MigrationFileError(RuntimeError):
    """The files on disk are wrong: no folder, a version twice, a no-transaction file with several statements, drift."""


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    path: Path
    checksum: str
    transactional: bool


@dataclass(frozen=True)
class AppliedMigration:
    version: str
    name: str
    applied_at: datetime
    checksum: str


@dataclass(frozen=True)
class MigrationRun:
    version: str
    name: str
    duration_ms: float


@dataclass(frozen=True)
class MigrationStatus:
    applied: list[AppliedMigration]
    pending: list[Migration]
    drifted: list[Migration]


def checksum(body: str) -> str:
    """sha256 over the body with line endings as `\\n`; any other edit, whitespace included, is drift."""
    return hashlib.sha256(body.replace('\r\n', '\n').encode('utf-8')).hexdigest()


def statement_count(body: str) -> int:
    """A rough count, comments stripped, split on `;`: no SQL parser. It guards one rule (a no-transaction file holds one
    statement), and a semicolon in a string literal over-counts, which fails loudly rather than running wrongly."""
    stripped = BLOCK_COMMENT.sub(' ', LINE_COMMENT.sub(' ', body))
    return len([statement for statement in stripped.split(';') if statement.strip()])


class MigrationRunner:
    """Finds the migration files, compares them with the ledger, applies the pending ones. Building it touches nothing:
    `status()` only reads, `apply()` is the one change."""

    def __init__(self, database_url: str, folder: Path = MIGRATIONS, table: str = MIGRATIONS_TABLE):
        self._url = database_url
        self._folder = folder
        self._table = table

    def _connect(self) -> psycopg.Connection:
        try:
            return psycopg.connect(self._url, connect_timeout=CONNECT_TIMEOUT_SECONDS)
        except psycopg.Error as error:
            raise MigrationError(f'cannot connect for migrations: {error}') from error

    def discover(self) -> list[Migration]:
        """Every `NNN_name.sql` in the folder, in version order, checked before anything touches the schema."""
        if not self._folder.is_dir():
            raise MigrationFileError(f'migrations folder not found: {self._folder}')
        found = []
        for path in sorted(self._folder.iterdir()):
            match = FILENAME.match(path.name)
            if match is None:
                continue
            body = path.read_bytes().decode('utf-8')
            transactional = NO_TRANSACTION.search(body) is None
            if not transactional and statement_count(body) > 1:
                raise MigrationFileError(
                    f'{path.name} is marked `-- finiex:no-transaction` but holds more than one statement: PostgreSQL wraps '
                    'several statements in an implicit transaction, the very thing the mark avoids. One statement per file.')
            found.append(Migration(match.group(1), match.group(2), path, checksum(body), transactional))
        versions = [migration.version for migration in found]
        twice = sorted({version for version in versions if versions.count(version) > 1})
        if twice:
            raise MigrationFileError(f'migration version(s) used twice: {twice}')
        return found

    def _ensure_ledger(self, cursor: psycopg.Cursor) -> None:
        cursor.execute(f'CREATE TABLE IF NOT EXISTS {self._table} (version TEXT PRIMARY KEY, name TEXT NOT NULL, '
                       'applied_at TIMESTAMPTZ NOT NULL, checksum TEXT NOT NULL)')

    def _applied(self, cursor: psycopg.Cursor) -> dict[str, AppliedMigration]:
        cursor.execute(f'SELECT version, name, applied_at, checksum FROM {self._table} ORDER BY version')
        return {row[0]: AppliedMigration(*row) for row in cursor.fetchall()}

    def status(self) -> MigrationStatus:
        """What is applied, pending and drifted; the ledger table is created where missing, nothing else is touched."""
        on_disk = self.discover()
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                self._ensure_ledger(cursor)
                applied = self._applied(cursor)
        except psycopg.Error as error:
            raise MigrationError(f'cannot read {self._table}: {error}') from error
        return MigrationStatus(applied=list(applied.values()),
                               pending=[m for m in on_disk if m.version not in applied],
                               drifted=[m for m in on_disk if m.version in applied and applied[m.version].checksum != m.checksum])

    def apply(self) -> list[MigrationRun]:
        """Every pending migration in order, each in its own transaction, under the lock; run again, it does nothing."""
        status = self.status()
        if status.drifted:
            names = ', '.join(f'{m.version}_{m.name}' for m in status.drifted)
            raise MigrationFileError(f'migration file(s) changed after being applied: {names}. Revert the edit, or write the '
                                     'change as a new migration: an applied migration is immutable.')
        if not status.pending:
            return []
        runs = []
        with self._connect() as lock:  # its own connection, so a migration's rollback never drops the lock mid-pass
            lock.autocommit = True
            lock.execute('SELECT pg_advisory_lock(%s)', (LOCK_KEY,))
            try:
                for migration in self.status().pending:  # read again under the lock: another process may have applied them
                    runs.append(self._apply_one(migration))
            finally:
                lock.execute('SELECT pg_advisory_unlock(%s)', (LOCK_KEY,))
        return runs

    def _record(self, cursor: psycopg.Cursor, migration: Migration) -> None:
        cursor.execute(f'INSERT INTO {self._table} (version, name, applied_at, checksum) VALUES (%s, %s, %s, %s)',
                       (migration.version, migration.name, datetime.now(timezone.utc), migration.checksum))

    def _apply_one(self, migration: Migration) -> MigrationRun:
        label = f'{migration.version}_{migration.name}'
        body = migration.path.read_bytes().decode('utf-8')
        started = perf_counter()
        if migration.transactional:
            try:
                with self._connect() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(body)
                        self._record(cursor, migration)
                    connection.commit()
            except psycopg.Error as error:
                raise MigrationError(f'migration {label} failed and was rolled back: {error}') from error
        else:
            try:
                with self._connect() as connection:
                    connection.autocommit = True  # no implicit BEGIN: the reason for the mark
                    with connection.cursor() as cursor:
                        cursor.execute(body)
                    with connection.cursor() as cursor:
                        self._record(cursor, migration)
            except psycopg.Error as error:
                raise MigrationError(
                    f'migration {label} failed and was NOT rolled back: {error}. It is marked `-- finiex:no-transaction`, '
                    'so there was no transaction to undo; a failed CREATE INDEX CONCURRENTLY leaves an INVALID index, '
                    'to be dropped before running it again.') from error
        return MigrationRun(migration.version, migration.name, (perf_counter() - started) * 1000.0)
