"""The export run behind a person's verdict from the page view (decision 213.b, the operator, 12 Nov, the last feature before the
freeze). The verdict is recorded at once in the pipeline database; the export that shows it in every view follows in a
thread of the view's own process, one at a time, and a request while one runs makes exactly one more run after it, so the
last verdict given is always in the last export. A failed export is said in the status, never hidden: the verdict stays
recorded whatever the export does.

Built here rather than taken from a task queue (Celery, RQ, `concurrent.futures`): one process, one job kind and the rule
"at most one more after the running one" are twenty lines; a queue library would add a broker or keep every request.
"""

import statistics
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from backend.conversion.store import pipeline_db, reading_export


VIEW_COMMAND = 'backend.diagnostics: the {} export after a verdict from the page view'
RECENT_RUNS = 5  # the expected time is the median of this many finished exports


def _export(base: reading_export.KnowledgeBase) -> None:
    with pipeline_db.run([base.name], VIEW_COMMAND.format(base.name)):
        reading_export.export(base)


def expected_seconds(knowledge_base: str, path=None) -> float | None:
    """How long an export of this knowledge base takes, from the runs the pipeline database recorded (the operator's E1.a,
    21 Nov: a person who records a verdict is told how long it waits): the median of the last finished exports the view
    ran, else of any export of the base, since one run in the view's container through its mounted folder takes longer
    than one on the machine itself. None where no export finished yet."""
    with pipeline_db.connect(knowledge_base, path) as db:
        rows = db.execute("SELECT command, started_at, ended_at FROM runs WHERE outcome = 'ok' AND ended_at IS NOT NULL "
                          "AND (command = ? OR command LIKE ?) ORDER BY started_at DESC",
                          (VIEW_COMMAND.format(knowledge_base), f'%reading_export%{knowledge_base}%')).fetchall()
    took = lambda rows: [(datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()  # noqa: E731
                         for _, start, end in rows[:RECENT_RUNS]]
    own = [row for row in rows if row[0] == VIEW_COMMAND.format(knowledge_base)]
    seconds = took(own) or took(rows)
    return round(statistics.median(seconds)) if seconds else None


class ExportQueue:
    """One knowledge base's export, run in the background on request. `finished` grows with every export that ends, so a
    view reloads its data when it sees the number move."""

    def __init__(self, base: reading_export.KnowledgeBase, run: Callable[[], None] | None = None):
        self.base = base
        self._run = run or (lambda: _export(base))
        self._lock = threading.Lock()
        self._running = False
        self._pending = False
        self._idle = threading.Event()
        self._idle.set()
        self.finished = 0
        self.last_error: str | None = None
        self.last_finished_at: str | None = None
        self.started_at: str | None = None  # the running export's start, for the view's clock (E1.a)

    def request(self) -> dict:
        """Start an export, or mark one more after the running one; never two at once, never a queue of them."""
        with self._lock:
            if self._running:
                self._pending = True
            else:
                self._running = True
                self.started_at = datetime.now(timezone.utc).isoformat(timespec='seconds')  # set before the thread, so a
                self._idle.clear()                                                           # status read at once has it
                threading.Thread(target=self._loop, name=f'export-{self.base.name}', daemon=True).start()
        return self.status()

    def _loop(self) -> None:
        while True:
            try:
                self._run()
                error = None
            except Exception as failure:  # the verdict is recorded; a failed export is reported, never raised into the view
                error = f'{type(failure).__name__}: {failure}'
            with self._lock:
                self.finished += 1
                self.last_error = error
                self.last_finished_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
                if self._pending:
                    self._pending = False
                    self.started_at = datetime.now(timezone.utc).isoformat(timespec='seconds')
                    continue
                self._running = False
                self.started_at = None
                self._idle.set()
                return

    def status(self) -> dict:
        """Whether an export runs or waits, since when, and how long one usually takes (E1.a); `expected_seconds` is read
        from the pipeline database only while one runs, so an idle view asks nothing of it."""
        with self._lock:
            found = {'knowledge_base': self.base.name, 'running': self._running, 'pending': self._pending,
                     'finished': self.finished, 'last_error': self.last_error, 'last_finished_at': self.last_finished_at,
                     'started_at': self.started_at}
        try:
            found['expected_seconds'] = expected_seconds(self.base.name) if found['running'] else None
        except Exception:  # a database that cannot be read yet gives no estimate, never a failed status
            found['expected_seconds'] = None
        return found

    def wait(self, timeout: float) -> bool:
        """True once no export runs or waits (for tests and a clean shutdown)."""
        return self._idle.wait(timeout)
