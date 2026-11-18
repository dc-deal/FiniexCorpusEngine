"""A person's verdict from the page view (decision 213.b, the operator, 12 Nov: "this really is the last proper feature before the freeze"): the one route of this API that writes, there only when the app was started with `--allow-verdicts`
(223.a), so a reviewer's clone stays read-only. A verdict is recorded at once by the core (`human_verdict.from_view`, a
run of its own, append-only, by "maintainer" as from the command line), and the export that shows it in every view runs
in this process's background (`export_queue.ExportQueue`, one per knowledge base served); the view follows its status and
reloads the page when it has finished.

The route answers only a request addressed to this machine by name (as the chat's does) and, where a browser says where
the request comes from (`Origin`), only one from this machine's own pages: a page elsewhere can neither reach it nor make
a browser send it. Under `--public-only` the licensed knowledge base is not served, so no verdict can be given on it.
"""

from collections.abc import Callable
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from pydantic import BaseModel

from backend.conversion.checks import human_verdict
from backend.conversion.store import export_queue, pipeline_db, reading_export
from backend.diagnostics.chat import LOCAL_HOSTS, local_host_only
from backend.diagnostics.readings import Cell, KnowledgeBase, Readings, table_correction

SWITCHED_OFF = 'Verdicts are given here only when the app was started with --allow-verdicts; it is read-only now.'


class VerdictRequest(BaseModel):
    """A verdict on the reading a page shows: the page by its work's id and PDF page, as the views address it."""

    knowledge_base: KnowledgeBase
    work: str  # the work's id (`source_id`), as in the page view's address
    pdf_page: int
    verdict: str  # accept, reject or note
    reason: str  # a key of the reasons' list
    block: str | None = None  # a block of the reading, as bNN; None for the page as a whole
    note: str | None = None  # required for the reason `other`
    correction: str | None = None  # the block's text as it should read (188.a), only with a block
    judge_assessment: str | None = None  # a key of the assessments' list


class Option(BaseModel):
    value: str
    label: str


class ExportStatus(BaseModel):
    """The background export of one knowledge base: whether one runs or waits, how many have finished (a view reloads its
    data when this number moves), and the last one's error, said rather than hidden."""

    knowledge_base: str
    running: bool
    pending: bool
    finished: int
    last_error: str | None = None
    last_finished_at: str | None = None


class VerdictForm(BaseModel):
    """What the page view's dialog offers: whether verdicts are given here at all, and if not why, the lists it chooses
    from in the core's own words, and each served knowledge base's export."""

    enabled: bool
    why_not: str | None = None
    verdicts: list[Option]
    reasons: list[Option]
    assessments: list[Option]
    exports: list[ExportStatus]


class VerdictGiven(BaseModel):
    """A recorded verdict: its id, the reading it judged, the page's route before it, and the export it set going."""

    verdict_id: int
    reading_key: str
    route_before: str | None = None
    export: ExportStatus


class PreviewRequest(BaseModel):
    text: str


class TablePreview(BaseModel):
    """A correction's text as the table it would be, read by the core's table parser as a reading's table is (204.a);
    None where it is no table, or not a clean one."""

    rows: list[list[Cell]] | None = None


def local_origin_only(request: Request) -> None:
    """Refuses a request a browser sent from a page elsewhere: where it names its origin, that origin must be this
    machine's own. A request with no origin (a command line on this machine) passes, as the host check has passed."""
    origin = request.headers.get('origin')
    if origin is None:
        return
    host = urlsplit(origin).hostname or ''
    if host not in LOCAL_HOSTS:
        raise HTTPException(403, 'A verdict is taken only from this machine\'s own pages.')


def guarded(request: Request) -> None:
    """The write route's guard: addressed to this machine, and sent from its own pages."""
    local_host_only(request)
    local_origin_only(request)


class VerdictService:
    """The verdicts of one app: switched on or off at its start, one export queue per knowledge base it serves. `run`
    replaces the export a queue runs, for the tests, so no test writes the real export."""

    def __init__(self, enabled: bool, bases: dict[str, Readings], run: Callable[[], None] | None = None):
        self.enabled = enabled
        self.bases = bases
        self.queues = {name: export_queue.ExportQueue(reading_export.BASES[name], run=run) for name in bases} if enabled else {}

    def form(self) -> VerdictForm:
        return VerdictForm(
            enabled=self.enabled, why_not=None if self.enabled else SWITCHED_OFF,
            verdicts=[Option(value=verdict, label=verdict) for verdict in pipeline_db.HUMAN_VERDICTS],
            reasons=[Option(value=key, label=label) for key, label in pipeline_db.HUMAN_REASONS.items()],
            assessments=[Option(value=key, label=label) for key, label in pipeline_db.JUDGE_ASSESSMENTS.items()],
            exports=[ExportStatus(**queue.status()) for queue in self.queues.values()])

    def give(self, asked: VerdictRequest) -> VerdictGiven:
        """Records the verdict and asks for the export. Raises HTTPException 403 when switched off, 404 for a knowledge base
        or page not served here, and ValueError with the core's own sentence for an input it refuses."""
        if not self.enabled:
            raise HTTPException(403, SWITCHED_OFF)
        store = self.bases.get(asked.knowledge_base)
        if store is None:
            raise HTTPException(404, f'no knowledge base {asked.knowledge_base!r} is served here')
        row = store.row(asked.work, asked.pdf_page)
        if row is None:
            raise HTTPException(404, f'{asked.work} has no page {asked.pdf_page} here')
        made = human_verdict.from_view(reading_export.BASES[asked.knowledge_base], self.queues[asked.knowledge_base], row['work'],
                                       asked.pdf_page, asked.verdict, asked.reason, block=asked.block or None,
                                       note=asked.note or None, correction=asked.correction or None,
                                       judge_assessment=asked.judge_assessment or None)
        return VerdictGiven(verdict_id=made['verdict_id'], reading_key=made['reading_key'], route_before=made.get('route_before'),
                            export=ExportStatus(**made['export']))

    def preview(self, asked: PreviewRequest) -> TablePreview:
        if not self.enabled:
            raise HTTPException(403, SWITCHED_OFF)
        return TablePreview(rows=table_correction(asked.text))
