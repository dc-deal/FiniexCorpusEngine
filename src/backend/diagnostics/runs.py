"""The pipeline's runs, every one, and what one run did (21.a, the runs view for the review demo, decision 69.a).

A run is a row of the core's pipeline database (decision 51.a), read through `pipeline_db.runs`, and the pages one run chose
a reading for through `pipeline_db.choices`. Nothing is counted here: a run stands as recorded, its cost by provider as the
core summed it. A chosen page opens its page view where the export has a row for it. Under `--public-only` the licensed
base's runs are never read (81.a), and a base without a pipeline database on this machine says so, as on a clone.
"""

import json

from pydantic import BaseModel

from backend.conversion.store import pipeline_db
from backend.diagnostics.readings import KnowledgeBase, Readings

BASES: tuple[KnowledgeBase, ...] = ('free', 'licensed')
NO_DATABASE = 'No runs recorded on this machine: the pipeline database is local and not tracked.'
NOT_READ = 'not read: the app was started with --public-only'
# A run that recorded no end (line 1's word, 19 Nov): `pipeline_db.run` writes its end and outcome in its `finally`, so
# both are missing only where the process stopped before that, killed or a session's script that never left the run, or
# where it still runs; the row alone cannot tell which. Never "failed": a failed run records "failed: <error>" itself
NO_END = 'no end recorded'
NO_END_WHY = 'the command stopped before it could record an end, or it is still running'


class RunLine(BaseModel):
    """One run as a list shows it: what was run, when, how it ended, what it cost, the batches it sent."""

    knowledge_base: KnowledgeBase
    run_id: int
    command: str
    started_at: str
    ended_at: str | None
    outcome: str | None  # the run's own word, or `NO_END` for a run that recorded no end
    outcome_why: str | None = None  # what an outcome the run did not write itself means, `NO_END_WHY`
    cost_usd: float | None
    batch_ids: list[str]
    note: str | None


class RunBase(BaseModel):
    knowledge_base: KnowledgeBase
    why_not: str | None = None  # why this base's runs are not listed: not served, or no pipeline database here


class RunList(BaseModel):
    bases: list[RunBase]
    runs: list[RunLine]  # newest first, both knowledge bases together


class ChosenPage(BaseModel):
    """A page one run chose a reading for, and why."""

    file: str
    pdf_page: int
    source_id: str | None  # None where the export has no row for the page, so there is no page view to open
    title: str
    reading_key: str
    why: str
    chosen_at: str


class RunDetail(RunLine):
    code_commit: str | None
    code_clean: bool | None  # whether the code had no uncommitted change when the run started
    code_sha256: str | None
    cost_by_provider: dict[str, float] | None
    chose: list[ChosenPage]  # oldest first


def line_of(run: dict) -> RunLine:
    no_end = run['ended_at'] is None and run['outcome'] is None
    return RunLine(knowledge_base=run['knowledge_base'], run_id=run['run_id'], command=run['command'],
                   started_at=run['started_at'], ended_at=run['ended_at'], outcome=NO_END if no_end else run['outcome'],
                   outcome_why=NO_END_WHY if no_end else None, cost_usd=run['cost_usd'],
                   batch_ids=json.loads(run['batch_ids'] or '[]'), note=run['note'])


# a base's runs by the state of its database: the overview, the landing page, asked for every run on each load, 0.27 s a
# base natively and more over the container's bind mount (O3.a, 19 Nov)
_RUNS: dict[KnowledgeBase, tuple[tuple, list[dict]]] = {}


def database_state(path) -> tuple:
    """The pipeline database's time and size, and its write-ahead log's, which takes a new run before the database file
    itself changes: a new run, or its end, changes one of them."""
    return tuple((found.st_mtime_ns, found.st_size) if (found := part.stat() if part.exists() else None) else None
                 for part in (path, path.with_name(path.name + '-wal')))


def recent(knowledge_base: KnowledgeBase, shown: int) -> list[RunLine] | None:
    """A base's latest runs, newest first; None where this machine keeps no pipeline database. Read again only when the
    database changed (`database_state`)."""
    path = pipeline_db.PATHS[knowledge_base]
    if not path.exists():
        return None
    state = (path, database_state(path))
    known = _RUNS.get(knowledge_base)
    if known is None or known[0] != state:
        known = (state, pipeline_db.runs(knowledge_base))
        _RUNS[knowledge_base] = known
    return [line_of(run) for run in reversed(known[1][-shown:])]


def run_list(bases: dict[str, Readings], public_only: bool) -> RunList:
    listed, lines = [], []
    for name in BASES:
        if name not in bases:
            listed.append(RunBase(knowledge_base=name, why_not=NOT_READ if public_only else 'no export of it on this machine'))
        elif not pipeline_db.PATHS[name].exists():
            listed.append(RunBase(knowledge_base=name, why_not=NO_DATABASE))
        else:
            listed.append(RunBase(knowledge_base=name))
            lines += [line_of(run) for run in pipeline_db.runs(name)]
    return RunList(bases=listed, runs=sorted(lines, key=lambda line: (line.started_at, line.run_id), reverse=True))


def run_detail(store: Readings, knowledge_base: KnowledgeBase, run_id: int) -> RunDetail | None:
    """One run whole: its code version, its cost by provider, and the pages it chose, each with its page view where the
    export has one."""
    if not pipeline_db.PATHS[knowledge_base].exists():
        return None
    run = next((run for run in pipeline_db.runs(knowledge_base) if run['run_id'] == run_id), None)
    if run is None:
        return None
    rows = {(row['file'], row['pdf_page']): row for row in store.rows()}
    chose = []
    for choice in pipeline_db.choices(knowledge_base, run_id):
        row = rows.get((choice['file'], choice['pdf_page']))
        chose.append(ChosenPage(file=choice['file'], pdf_page=choice['pdf_page'], source_id=row['source_id'] if row else None,
                                title=store.title(row['source_id']) if row else choice['file'],
                                reading_key=choice['reading_key'], why=choice['why'], chosen_at=choice['chosen_at']))
    return RunDetail(**line_of(run).model_dump(), code_commit=run['code_commit'],
                     code_clean=None if run['code_clean'] is None else bool(run['code_clean']),
                     code_sha256=run['code_sha256'],
                     cost_by_provider=json.loads(run['cost_by_provider']) if run['cost_by_provider'] else None, chose=chose)
