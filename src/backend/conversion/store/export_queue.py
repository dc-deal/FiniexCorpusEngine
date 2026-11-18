"""The export run behind a person's verdict from the page view (decision 213.b, the operator, 12 Nov, the last feature before the
freeze). The verdict is recorded at once in the pipeline database; the export that shows it in every view follows in a
thread of the view's own process, one at a time, and a request while one runs makes exactly one more run after it, so the
last verdict given is always in the last export. A failed export is said in the status, never hidden: the verdict stays
recorded whatever the export does.

Built here rather than taken from a task queue (Celery, RQ, `concurrent.futures`): one process, one job kind and the rule
"at most one more after the running one" are twenty lines; a queue library would add a broker or keep every request.
"""

import threading
from collections.abc import Callable
from datetime import datetime, timezone

from backend.conversion.store import pipeline_db, reading_export


def _export(base: reading_export.KnowledgeBase) -> None:
    with pipeline_db.run([base.name], f'backend.diagnostics: the {base.name} export after a verdict from the page view'):
        reading_export.export(base)


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

    def request(self) -> dict:
        """Start an export, or mark one more after the running one; never two at once, never a queue of them."""
        with self._lock:
            if self._running:
                self._pending = True
            else:
                self._running = True
                self._idle.clear()
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
                    continue
                self._running = False
                self._idle.set()
                return

    def status(self) -> dict:
        with self._lock:
            return {'knowledge_base': self.base.name, 'running': self._running, 'pending': self._pending,
                    'finished': self.finished, 'last_error': self.last_error, 'last_finished_at': self.last_finished_at}

    def wait(self, timeout: float) -> bool:
        """True once no export runs or waits (for tests and a clean shutdown)."""
        return self._idle.wait(timeout)
