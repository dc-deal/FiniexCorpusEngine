"""The pipeline database: what cannot be rebuilt, one SQLite file per knowledge base (decisions 51.a, 47.a).

Readings, their texts and their images stay files in the reading store, and the index stays derived and is rebuilt freely. This
file holds the three things neither can tell afterwards (the third since decision 146.a, 9 Nov):

- `runs`: every command that read, checked, judged, exported or built: when, with what outcome, what it cost and which batches
  it sent, both measured from the stores themselves (the ledger and the manifests before and after), and the code that ran it
  (the commit, whether the tree was clean, and a hash of `src/backend` as it was).
- `chosen_readings`: which reading stands for a page and why, appended and never changed: the database itself refuses an update
  or a delete. A page without a row is represented by its latest attempt, as before; a replay or a second reader appends one.
- `human_verdicts`: a person's verdict on one reading of a page (accept, reject, note), with a reason from a fixed list, the
  block, a tag and a note; appended and never changed, like the choices. The export carries them, so a clone serves alike.
  Since decision 188.a (10 Nov) a verdict may carry two manual parts, marked as a person's: a correction of the block's text
  (the reading itself is never edited: its hash would no longer match, and the integrity check would call it tampering) and
  an assessment of the judge's finding (`JUDGE_ASSESSMENTS`).
- `page_resets` (decision 191.a, 10 Nov): a person's reset of a page they or another person had checked, with its reason. It
  archives the page's earlier verdicts (they stay, and no longer apply), discards the reading that stood (the page serves its
  text layer until a new reading stands) and lifts the page's protection, so a person may have it read and judged again. A
  page a person checked is protected otherwise: no command reads it again without `--over-a-person "<reason>"`.

    with pipeline_db.run(['free'], 'check_run report --cells FREE-SM') as run:
        ...                                                   # cost and batch ids are measured when the block ends
    pipeline_db.choose('free', 'a.pdf', 19, key, why='replay --reread', run_id=run.run_id)
    pipeline_db.chosen('free')                                # {(file, pdf_page): the latest choice}

Built on `sqlite3` from the standard library: two small tables need no ORM. The file lies in the knowledge base's git-ignored
folder, refused anywhere git would track it, so a clone has none and every page there stands by its latest attempt.
"""

import hashlib
import json
import re
import sqlite3
import subprocess
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from backend.configuration import data_paths
from backend.constants.reading_constants import DELEGATED_MARK
from backend.conversion.store import reading_store
from backend.conversion.store.reading_store import REPO

PATHS = {'free': data_paths.FREE_WORKING / 'pipeline.sqlite',
         'licensed': data_paths.LICENSED_WORKING / 'pipeline.sqlite'}
CODE = REPO / 'src' / 'backend'
SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY,
    knowledge_base TEXT NOT NULL,
    command TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    outcome TEXT,
    code_commit TEXT,
    code_clean INTEGER,
    code_sha256 TEXT,
    cost_usd REAL,
    cost_by_provider TEXT,
    batch_ids TEXT,
    note TEXT
);
CREATE TABLE IF NOT EXISTS chosen_readings (
    choice_id INTEGER PRIMARY KEY,
    knowledge_base TEXT NOT NULL,
    file TEXT NOT NULL,
    pdf_page INTEGER NOT NULL,
    reading_key TEXT NOT NULL,
    why TEXT NOT NULL,
    run_id INTEGER REFERENCES runs (run_id),
    chosen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chosen_by_page ON chosen_readings (file, pdf_page, choice_id);
CREATE TRIGGER IF NOT EXISTS chosen_readings_no_update BEFORE UPDATE ON chosen_readings
    BEGIN SELECT RAISE(ABORT, 'chosen_readings is append-only: choose again instead'); END;
CREATE TRIGGER IF NOT EXISTS chosen_readings_no_delete BEFORE DELETE ON chosen_readings
    BEGIN SELECT RAISE(ABORT, 'chosen_readings is append-only: choose again instead'); END;
CREATE TABLE IF NOT EXISTS human_verdicts (
    verdict_id INTEGER PRIMARY KEY,
    knowledge_base TEXT NOT NULL,
    file TEXT NOT NULL,
    pdf_page INTEGER NOT NULL,
    reading_key TEXT NOT NULL,
    block TEXT,
    verdict TEXT NOT NULL CHECK (verdict IN ('accept', 'reject', 'note')),
    reason TEXT NOT NULL,
    tag TEXT,
    note TEXT,
    given_by TEXT NOT NULL,
    given_at TEXT NOT NULL,
    run_id INTEGER REFERENCES runs (run_id),
    correction TEXT,
    judge_assessment TEXT
);
CREATE INDEX IF NOT EXISTS human_by_page ON human_verdicts (file, pdf_page, verdict_id);
CREATE TRIGGER IF NOT EXISTS human_verdicts_no_update BEFORE UPDATE ON human_verdicts
    BEGIN SELECT RAISE(ABORT, 'human_verdicts is append-only: give a new verdict instead'); END;
CREATE TRIGGER IF NOT EXISTS human_verdicts_no_delete BEFORE DELETE ON human_verdicts
    BEGIN SELECT RAISE(ABORT, 'human_verdicts is append-only: give a new verdict instead'); END;
CREATE TABLE IF NOT EXISTS page_resets (
    reset_id INTEGER PRIMARY KEY,
    knowledge_base TEXT NOT NULL,
    file TEXT NOT NULL,
    pdf_page INTEGER NOT NULL,
    reading_key TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    given_by TEXT NOT NULL,
    given_at TEXT NOT NULL,
    run_id INTEGER REFERENCES runs (run_id)
);
CREATE INDEX IF NOT EXISTS resets_by_page ON page_resets (file, pdf_page, reset_id);
CREATE TRIGGER IF NOT EXISTS page_resets_no_update BEFORE UPDATE ON page_resets
    BEGIN SELECT RAISE(ABORT, 'page_resets is append-only'); END;
CREATE TRIGGER IF NOT EXISTS page_resets_no_delete BEFORE DELETE ON page_resets
    BEGIN SELECT RAISE(ABORT, 'page_resets is append-only'); END;
"""
# What a person may give (decision 146.a): accept, the reading is right and a finding of the judge is not; reject, the reading is
# wrong and the page serves its text layer; note, a remark that changes nothing. A reason from this list; `other` needs a note.
HUMAN_VERDICTS = ('accept', 'reject', 'note')
HUMAN_REASONS = {
    'judge_contradicts_itself': "the judge's finding contradicts its own evidence",
    'judge_misread_name': 'the judge took a name or a term for a wrong word',
    'finding_on_unquoted_block': "the judge's finding lies on a block never quoted",
    'reading_wrong': 'the reading does not say what the page prints',
    'not_worth_reading': 'a page with nothing to quote: blank, a cover, a list of sponsors',
    'other': 'another reason, said in the note',
}
# How a person rates the judge's finding on the block (decision 188.a, the operator, 10 Nov, finance p. 94: the judge found the reader's
# "around 2000" wrong, but read the chart's crossing as 2006-2007 where it is 2012, so its verdict was right for a wrong reason)
JUDGE_ASSESSMENTS = {
    'right': "the judge's finding is right",
    'right_for_a_wrong_reason': "the judge's verdict is right, but its own evidence is not",
    'false_alarm': 'the judge reported an error that is not there',
    'missed': 'the judge passed an error that is there',
}
ADDED_COLUMNS = {'human_verdicts': ('correction TEXT', 'judge_assessment TEXT')}  # columns a database made before them lacks
PROVIDERS = ('anthropic', 'openrouter')


def now() -> str:
    from backend.conversion.reading import vision_batches

    return vision_batches.now()


def precise_now() -> str:
    """A person's act to the microsecond: a verdict given in the same second as a reset must still sort after it (decision
    191.a). An older stamp without its fraction sorts before every one with it in the same second, as it should."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def connect(knowledge_base: str, path: Path | None = None) -> sqlite3.Connection:
    """The knowledge base's database, its tables created on first use.

    Raises:
        reading_store.UnsafeRootError: When the file would lie where git tracks it.
    """
    path = Path(path or PATHS[knowledge_base]).resolve()
    reason = reading_store.refusal(path.parent)
    if reason:
        raise reading_store.UnsafeRootError(f'no pipeline database there: {reason}')
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    for table, columns in ADDED_COLUMNS.items():  # adding a column changes no row, so the append-only triggers stay intact
        present = {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
        for column in columns:
            if column.split()[0] not in present:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {column}')
    return db


def code_version() -> dict:
    """The code that runs: the commit, whether the work tree is clean, and a hash of every file under `src/backend` as it is now,
    so a run made with uncommitted changes is still told apart."""
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO, capture_output=True, text=True).stdout.strip() or None
    status = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=REPO, capture_output=True, text=True)
    digest = hashlib.sha256()
    for path in sorted(CODE.rglob('*.py')):
        if '__pycache__' not in path.parts:
            digest.update(path.relative_to(REPO).as_posix().encode('utf-8') + b'\0' + path.read_bytes() + b'\0')
    return {'code_commit': commit, 'code_clean': int(status.returncode == 0 and not status.stdout.strip()),
            'code_sha256': digest.hexdigest()}


def _spent(knowledge_base: str) -> dict[str, float]:
    store = reading_store.open_store(knowledge_base)
    return {provider: store.spent_usd(provider) for provider in PROVIDERS}


def _batch_ids() -> set[str]:
    return {manifest.get('batch_id') for manifest in reading_store.open_store('licensed').manifests() if manifest.get('batch_id')}


@dataclass
class Run:
    """One command's row in each knowledge base it touched; `note` may be set inside the block."""
    command: str
    run_ids: dict[str, int] = field(default_factory=dict)  # knowledge base -> its row
    note: str | None = None

    @property
    def run_id(self) -> int | None:
        """The row's id where the run touched one knowledge base."""
        return next(iter(self.run_ids.values())) if len(self.run_ids) == 1 else None


@contextmanager
def run(knowledge_bases: list[str], command: str, paths: dict[str, Path] | None = None):
    """Record one command: a row per knowledge base when it starts, finished with its outcome, its cost per provider (the
    ledger's growth) and the batches it sent (the manifests' growth) when it ends, whether it ended well or not."""
    paths = paths or {}
    code, spent, batches = code_version(), {base: _spent(base) for base in knowledge_bases}, _batch_ids()
    record = Run(command)
    for base in knowledge_bases:
        with closing(connect(base, paths.get(base))) as db, db:
            cursor = db.execute('INSERT INTO runs (knowledge_base, command, started_at, code_commit, code_clean, code_sha256) '
                                'VALUES (?, ?, ?, ?, ?, ?)', (base, command, now(), code['code_commit'], code['code_clean'],
                                                              code['code_sha256']))
            record.run_ids[base] = cursor.lastrowid
    outcome = 'ok'
    try:
        yield record
    except BaseException as error:
        outcome = f'failed: {type(error).__name__}'
        raise
    finally:
        new_batches = sorted(_batch_ids() - batches)
        for base, run_id in record.run_ids.items():
            after = _spent(base)
            by_provider = {provider: round(after[provider] - spent[base][provider], 6) for provider in PROVIDERS}
            with closing(connect(base, paths.get(base))) as db, db:
                db.execute('UPDATE runs SET ended_at = ?, outcome = ?, cost_usd = ?, cost_by_provider = ?, batch_ids = ?, note = ? '
                           'WHERE run_id = ?', (now(), outcome, round(sum(by_provider.values()), 6), json.dumps(by_provider),
                                                json.dumps(new_batches), record.note, run_id))


def command_line(module: str) -> str:
    """How a command was started, as a person would type it."""
    import sys

    return ' '.join([f'python -m {module}', *sys.argv[1:]])


def choose(knowledge_base: str, file: str, pdf_page: int, reading_key: str, why: str, run_id: int | None = None,
           path: Path | None = None) -> int:
    """Append the reading that now stands for a page, and why; the earlier choices stay as the page's history."""
    with closing(connect(knowledge_base, path)) as db, db:
        cursor = db.execute('INSERT INTO chosen_readings (knowledge_base, file, pdf_page, reading_key, why, run_id, chosen_at) '
                            'VALUES (?, ?, ?, ?, ?, ?, ?)', (knowledge_base, file, pdf_page, reading_key, why, run_id, now()))
        return cursor.lastrowid


def chosen(knowledge_base: str, path: Path | None = None) -> dict[tuple[str, int], dict]:
    """The latest choice per page; a page without one is not listed. Empty where the database does not exist yet."""
    target = Path(path or PATHS[knowledge_base])
    if not target.exists():
        return {}
    with closing(connect(knowledge_base, target)) as db:
        rows = db.execute('SELECT * FROM chosen_readings ORDER BY choice_id').fetchall()
    return {(row['file'], row['pdf_page']): dict(row) for row in rows}


def history(knowledge_base: str, file: str, pdf_page: int, path: Path | None = None) -> list[dict]:
    """Every choice ever made for one page, oldest first."""
    target = Path(path or PATHS[knowledge_base])
    if not target.exists():
        return []
    with closing(connect(knowledge_base, target)) as db:
        return [dict(row) for row in db.execute('SELECT * FROM chosen_readings WHERE file = ? AND pdf_page = ? ORDER BY choice_id',
                                                (file, pdf_page))]


def give_verdict(knowledge_base: str, file: str, pdf_page: int, reading_key: str, verdict: str, reason: str, given_by: str,
                 block: str | None = None, tag: str | None = None, note: str | None = None, run_id: int | None = None,
                 path: Path | None = None, correction: str | None = None, judge_assessment: str | None = None) -> int:
    """Append a person's verdict on one reading of a page (decision 146.a); earlier verdicts stay as the page's history. A
    correction is the block's text as the person says it reads, beside the reading, never in it (188.a).

    Raises:
        ValueError: For a verdict, reason or assessment outside the lists, `other` without a note, or a correction without
            the block it is about (an assessment without a block rates every finding of the page).
    """
    if verdict not in HUMAN_VERDICTS:
        raise ValueError(f'a verdict is one of {HUMAN_VERDICTS}, not {verdict!r}')
    if reason not in HUMAN_REASONS:
        raise ValueError(f'a reason is one of {sorted(HUMAN_REASONS)}, not {reason!r}')
    if reason == 'other' and not (note or '').strip():
        raise ValueError('the reason other needs a note that says it')
    if judge_assessment is not None and judge_assessment not in JUDGE_ASSESSMENTS:
        raise ValueError(f'an assessment of the judge is one of {sorted(JUDGE_ASSESSMENTS)}, not {judge_assessment!r}')
    if correction is not None and not block:  # an assessment without a block rates every finding of the page
        raise ValueError('a correction names the block it is about')
    if correction is not None and not correction.strip():
        raise ValueError('a correction is the text the block should read, never empty')
    with closing(connect(knowledge_base, path)) as db, db:
        cursor = db.execute('INSERT INTO human_verdicts (knowledge_base, file, pdf_page, reading_key, block, verdict, reason, tag, note, '
                            'given_by, given_at, run_id, correction, judge_assessment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                            (knowledge_base, file, pdf_page, reading_key, block, verdict, reason, tag, note, given_by, precise_now(),
                             run_id, correction, judge_assessment))
        return cursor.lastrowid


def human_verdicts(knowledge_base: str, path: Path | None = None) -> dict[tuple[str, int], list[dict]]:
    """Every person's verdict per page, oldest first; empty where the database does not exist yet (a clone: the export carries them)."""
    target = Path(path or PATHS[knowledge_base])
    if not target.exists():
        return {}
    with closing(connect(knowledge_base, target)) as db:
        rows = db.execute('SELECT * FROM human_verdicts ORDER BY verdict_id').fetchall()
    found: dict[tuple[str, int], list[dict]] = {}
    for row in rows:
        found.setdefault((row['file'], row['pdf_page']), []).append(dict(row))
    return found


def give_reset(knowledge_base: str, file: str, pdf_page: int, reading_key: str, reason: str, given_by: str,
               run_id: int | None = None, path: Path | None = None) -> int:
    """Append a person's reset of one page (decision 191.a): the reading named is discarded, the earlier verdicts archived.

    Raises:
        ValueError: Without a reason: a reset always says why (the operator: "always with a reason").
    """
    if not (reason or '').strip():
        raise ValueError('a reset says why: give a reason')
    with closing(connect(knowledge_base, path)) as db, db:
        cursor = db.execute('INSERT INTO page_resets (knowledge_base, file, pdf_page, reading_key, reason, given_by, given_at, run_id) '
                            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (knowledge_base, file, pdf_page, reading_key, reason.strip(), given_by,
                                                               precise_now(), run_id))
        return cursor.lastrowid


def page_resets(knowledge_base: str, path: Path | None = None) -> dict[tuple[str, int], list[dict]]:
    """Every reset per page, oldest first; empty where the database does not exist yet."""
    target = Path(path or PATHS[knowledge_base])
    if not target.exists():
        return {}
    with closing(connect(knowledge_base, target)) as db:
        rows = db.execute('SELECT * FROM page_resets ORDER BY reset_id').fetchall()
    found: dict[tuple[str, int], list[dict]] = {}
    for row in rows:
        found.setdefault((row['file'], row['pdf_page']), []).append(dict(row))
    return found


def since_last_reset(verdicts: list[dict], resets: list[dict]) -> list[dict]:
    """A page's verdicts given after its latest reset: the ones that still count (the rest are archived)."""
    cut = resets[-1]['given_at'] if resets else ''
    return [verdict for verdict in verdicts if verdict['given_at'] > cut]


def by_a_person(given_by: str | None) -> bool:
    """Whether a verdict was given by a person, not by a session on the operator's delegation (`DELEGATED_MARK`)."""
    return DELEGATED_MARK not in (given_by or '')


def delegated_giver(model: str, day: str) -> str:
    """The giver a session's verdicts name, '<model> session, delegated by the operator (<day>)', which `by_a_person` tells apart."""
    return f'{model} {DELEGATED_MARK} ({day})'


def protected_pages(knowledge_base: str, path: Path | None = None) -> dict[tuple[str, int], dict]:
    """(file, PDF page) -> the latest verdict of a person that still counts: a page a person checked is not read again
    without a reason (decision 191.a, the operator: "pages a human corrected … are valuable, a human has looked them over").
    Only a person's verdict protects (the operator, 18 Nov: a person who signs takes the responsibility, as with a contract);
    a session's verdict on the operator's delegation does not."""
    verdicts, resets = human_verdicts(knowledge_base, path), page_resets(knowledge_base, path)
    found = {}
    for page, given in verdicts.items():
        standing = [verdict for verdict in since_last_reset(given, resets.get(page, [])) if by_a_person(verdict['given_by'])]
        if standing:
            found[page] = standing[-1]
    return found


def refused_over_a_person(knowledge_base: str, file: str, pdf_page: int, over_a_person: str | None,
                          path: Path | None = None) -> str | None:
    """Why a command must not read this page again, or None: a person checked it, and no reason to go over them was given."""
    checked = protected_pages(knowledge_base, path).get((file, pdf_page))
    if checked is None or (over_a_person or '').strip():
        return None
    return (f"a person checked p. {pdf_page} ({checked['verdict']}, {checked['given_at'][:10]}): it is not read again without "
            '--over-a-person "<reason>", or a reset of the page by a person first')


def choices(knowledge_base: str, run_id: int, path: Path | None = None) -> list[dict]:
    """Every page one run chose a reading for, oldest first: what a run did, for the runs view (line 2's request, 5 Nov)."""
    target = Path(path or PATHS[knowledge_base])
    if not target.exists():
        return []
    with closing(connect(knowledge_base, target)) as db:
        return [dict(row) for row in db.execute('SELECT * FROM chosen_readings WHERE run_id = ? ORDER BY choice_id', (run_id,))]


def runs(knowledge_base: str, path: Path | None = None) -> list[dict]:
    """Every run of one knowledge base, oldest first.

    Until 5 Nov a batch run went into both databases even when it named only the other base's cells, so the free one
    listed licensed rounds (found by line 2). The database is append-only, so those rows stay as they were written; they
    are left out here, and the batch runner records each run in its own bases since."""
    target = Path(path or PATHS[knowledge_base])
    if not target.exists():
        return []
    with closing(connect(knowledge_base, target)) as db:
        rows = [dict(row) for row in db.execute('SELECT * FROM runs ORDER BY run_id')]
    return [row for row in rows if not _of_the_other_base(row, knowledge_base)]


CELLS_ARGUMENT = re.compile(r'--cells[ =](\S+)')


def _of_the_other_base(row: dict, knowledge_base: str) -> bool:
    """Whether a run named cells and every one of them reads the other knowledge base."""
    named = CELLS_ARGUMENT.search(row.get('command') or '')
    if named is None:
        return False
    from backend.conversion.reading import reading_cells

    bases = reading_cells.knowledge_bases_of([name for name in named.group(1).split(',') if name])
    return bases is not None and knowledge_base not in bases
