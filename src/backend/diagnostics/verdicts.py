"""A person's verdict from the page view (decision 213.b, the operator, 12 Nov: "this really is the last proper feature before the freeze"): the one route of this API that writes, there only when the app was started with `--allow-verdicts`
(223.a), so a reviewer's clone stays read-only. A verdict is recorded at once by the core (`human_verdict.from_view`, a
run of its own, append-only, by "maintainer" as from the command line), and the export that shows it in every view runs
in this process's background (`export_queue.ExportQueue`, one per knowledge base served); the view follows its status and
reloads the page when it has finished.

The route answers only a request addressed to this machine by name and, where a browser says where the request comes
from (`Origin`), only one from this machine's own pages (`local_only.guarded`): a page elsewhere can neither reach it nor
make a browser send it. Under `--public-only` the licensed knowledge base is not served, so no verdict can be given on it.
"""

import difflib
import re
from collections.abc import Callable
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.conversion.checks import human_verdict
from backend.conversion.judge import correction_proposal
from backend.conversion.store import export_queue, pipeline_db, reading_export
from backend.diagnostics.readings import Cell, KnowledgeBase, Readings, WaitingVerdict, table_correction

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
    # the key of the judgement the page showed the person (#17), which the verdict answers; None where it showed none
    answers_judgement: str | None = Field(default=None, max_length=128)


class PromoteRequest(BaseModel):
    """A person's promotion of a Lab reading to the page's reading (#18): the page, the reading by its key, the reason."""

    knowledge_base: KnowledgeBase
    work: str
    pdf_page: int
    reading_key: str = Field(max_length=128)
    reason: str  # a key of the promotion reasons' list
    note: str | None = None  # required for the reason `other`


class Option(BaseModel):
    value: str
    label: str  # the sentence
    short: str | None = None  # its short label, for a compact column and the dialog's "short — sentence" (#18)


class ExportStatus(BaseModel):
    """The background export of one knowledge base: whether one runs or waits, how many have finished (a view reloads its
    data when this number moves), and the last one's error, said rather than hidden."""

    knowledge_base: str
    running: bool
    pending: bool
    finished: int
    last_error: str | None = None
    last_finished_at: str | None = None
    # since when the running export runs, and how long one of this base usually takes, the median of the last finished
    # (the core's `expected_seconds`); None while none runs or none finished yet (the operator's E1.a, 21 Nov)
    started_at: str | None = None
    expected_seconds: float | None = None
    # the verdicts recorded and not yet in the export: what it serves once it is done
    waiting: list[WaitingVerdict] = []


class ProposeState(BaseModel):
    """Whether a model's correction can be proposed here (W2.a): only where verdicts are taken and a version of the role is
    active, which a person makes so after its gate; why not, in words, where it cannot."""

    available: bool
    why_not: str | None = None


NO_ACTIVE_VERSION = 'no active correction version'


class VerdictForm(BaseModel):
    """What the page view's verdict panel offers: whether verdicts are given here at all, and if not why, the lists it
    chooses from in the core's own words, each served knowledge base's export, and whether a correction can be proposed."""

    enabled: bool
    why_not: str | None = None
    verdicts: list[Option]
    reasons: list[Option]
    assessments: list[Option]
    exports: list[ExportStatus]
    propose: ProposeState = ProposeState(available=False, why_not=SWITCHED_OFF)
    promote_reasons: list[Option] | None = None  # why a person promotes a Lab reading (#18)


class VerdictGiven(BaseModel):
    """A recorded verdict: its id, the reading it judged, the page's route before it, and the export it set going."""

    verdict_id: int
    reading_key: str
    route_before: str | None = None
    export: ExportStatus


class PromoteGiven(BaseModel):
    """A recorded promotion: the reading it promoted and the export it set going."""

    reading_key: str
    export: ExportStatus


class PreviewRequest(BaseModel):
    text: str


class ProposalRequest(BaseModel):
    """A proposed correction of one block of the reading a page shows: the page by its work's id and PDF page, the block by
    its id. The judge's findings on it are taken here from the page's own data, never from the browser."""

    knowledge_base: KnowledgeBase
    work: str
    pdf_page: int
    block: str


class DiffPart(BaseModel):
    kind: Literal['same', 'added', 'removed']
    text: str


class Prefill(BaseModel):
    """The verdict as a proposal fills it (the operator's F1.a, 21 Nov: "fill with AI" fills the whole form): the model gives
    only what needs the image, the core's fixed rules the rest (`correction_proposal.prefill`); every field stays a person's
    to change, and nothing is recorded until a person records it, which `said` says beneath the form."""

    verdict: str
    reason: str
    block: str
    judge_assessment: str | None = None
    note: str = ''
    correction: str | None = None  # None where the block is left as it was
    said: str


AGREES_SAID = {'yes': 'agrees with the judge', 'partly': 'partly agrees with the judge', 'no': 'does not agree with the judge'}


class Proposal(BaseModel):
    """A model's proposed correction of one block (W2.a), as the core gives it and keeps it, or why it gave none, and the
    whole verdict it fills (F1.a); never recorded by itself: a person changes what they will and records it. `diff` is the block's current text against it,
    word by word; `cost_usd` what it cost when it was asked, nothing again when the core answers from its store."""

    state: Literal['proposed', 'no proposal']
    agrees_with_judge: Literal['yes', 'partly', 'no'] | None = None
    agrees_said: str | None = None
    image_shows: str | None = None
    correction: str | None = None
    flags: list[str] = []
    diff: list[DiffPart] = []
    why: str | None = None
    cost_usd: float | None = None
    version: str | None = None
    model: str | None = None
    prefill: Prefill | None = None  # the whole form as the proposal fills it; None where there is no proposal


TOKEN = re.compile(r'\s+|[^\s]+')


def word_diff(before: str, after: str) -> list[DiffPart]:
    """Two texts word by word, each run kept, added or removed; difflib's matcher over words and the spaces between them."""
    old, new = TOKEN.findall(before), TOKEN.findall(after)
    parts: list[DiffPart] = []

    def add(kind: str, text: str) -> None:
        if not text:
            return
        if parts and parts[-1].kind == kind:
            parts[-1] = DiffPart(kind=kind, text=parts[-1].text + text)
        else:
            parts.append(DiffPart(kind=kind, text=text))

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag == 'equal':
            add('same', ''.join(old[i1:i2]))
        else:
            add('removed', ''.join(old[i1:i2]))
            add('added', ''.join(new[j1:j2]))
    return parts


class TablePreview(BaseModel):
    """A correction's text as the table it would be, read by the core's table parser as a reading's table is (204.a);
    None where it is no table, or not a clean one."""

    rows: list[list[Cell]] | None = None


def waiting_in(name: str, store: Readings) -> list[WaitingVerdict]:
    """The verdicts the pipeline database holds that the base's export does not hold yet, oldest first: a verdict is
    exported with every page it is on (`reading_export.human_of`, archived ones too), so one the export lacks waits for the
    next. Told apart by page, time, verdict and block, which the export copies as the database holds them."""
    rows = store.rows()
    exported = {(row.get('file'), row.get('pdf_page'), person.get('given_at'), person.get('verdict'), person.get('block'))
                for row in rows for person in row.get('human') or []}
    sources = {(row.get('file'), row.get('pdf_page')): row.get('source_id') for row in rows}
    return [WaitingVerdict(knowledge_base=name, source_id=sources.get((file, pdf_page)), pdf_page=pdf_page, block=verdict['block'],
                           verdict=verdict['verdict'], given_at=verdict['given_at'], by_a_person=pipeline_db.by_a_person(verdict['given_by']))
            for (file, pdf_page), verdicts in pipeline_db.human_verdicts(name).items() for verdict in verdicts
            if (file, pdf_page, verdict['given_at'], verdict['verdict'], verdict['block']) not in exported]


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
            reasons=[Option(value=key, label=label, short=pipeline_db.HUMAN_REASON_SHORT.get(key))
                     for key, label in pipeline_db.HUMAN_REASONS.items()],
            assessments=[Option(value=key, label=label, short=pipeline_db.JUDGE_ASSESSMENT_SHORT.get(key))
                         for key, label in pipeline_db.JUDGE_ASSESSMENTS.items()],
            promote_reasons=[Option(value=key, label=label, short=pipeline_db.PROMOTE_REASON_SHORT.get(key))
                             for key, label in pipeline_db.PROMOTE_REASONS.items()],
            exports=[ExportStatus(**queue.status(), waiting=waiting_in(name, self.bases[name])) for name, queue in self.queues.items()],
            propose=self.propose_state())

    def waiting_on(self, knowledge_base: str, source_id: str, pdf_page: int) -> list[WaitingVerdict]:
        """A page's verdicts that wait for the export; none for a base not served here."""
        store = self.bases.get(knowledge_base)
        if store is None:
            return []
        return [one for one in waiting_in(knowledge_base, store) if one.source_id == source_id and one.pdf_page == pdf_page]

    def propose_state(self) -> ProposeState:
        if not self.enabled:
            return ProposeState(available=False, why_not=SWITCHED_OFF)
        if correction_proposal.active_version() is None:
            return ProposeState(available=False, why_not=NO_ACTIVE_VERSION)
        return ProposeState(available=True)

    def propose(self, asked: ProposalRequest) -> Proposal:
        """A proposed correction of one block, asked of the core with the judge's findings on it from the page's own data,
        void ones left out. Raises HTTPException 403 when switched off, 404 for a page or block not here, and 409 with the
        core's reason where it sends nothing (a file held back, a page a filter blocked, no active version, the spend guard)."""
        if not self.enabled:
            raise HTTPException(403, SWITCHED_OFF)
        store = self.bases.get(asked.knowledge_base)
        if store is None:
            raise HTTPException(404, f'no knowledge base {asked.knowledge_base!r} is served here')
        row = store.row(asked.work, asked.pdf_page)
        page = store.page(asked.work, asked.pdf_page, asked.work) if row is not None else None
        block = next((block for block in ((page.reading.blocks if page and page.reading else [])) if block.id == asked.block), None)
        if row is None or block is None:
            raise HTTPException(404, f'{asked.work} has no block {asked.block} on page {asked.pdf_page} here')
        findings = [{'kind': finding.kind, 'severity': finding.severity, 'evidence': finding.evidence}
                    for finding in block.findings if not finding.void]
        try:
            found = correction_proposal.propose(asked.knowledge_base, row['reading_key'], asked.block, findings)
        except correction_proposal.Refused as refused:
            raise HTTPException(409, str(refused)) from refused
        current = (block.correction.text if block.correction and block.correction.text is not None else block.body) or ''
        proposed = found.get('state') == 'proposed'
        return Proposal(state=found.get('state', 'no proposal'), agrees_with_judge=found.get('agrees_with_judge'),
                        agrees_said=AGREES_SAID.get(found.get('agrees_with_judge') or ''), image_shows=found.get('image_shows'),
                        correction=found.get('correction'), flags=found.get('flags') or [],
                        diff=word_diff(current, found['correction']) if proposed else [], why=found.get('why'),
                        cost_usd=found.get('cost_usd'), version=found.get('version'), model=found.get('model'),
                        prefill=Prefill(**found['prefill']) if found.get('prefill') else None)

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
                                       judge_assessment=asked.judge_assessment or None,
                                       answers_judgement=asked.answers_judgement or None)
        return VerdictGiven(verdict_id=made['verdict_id'], reading_key=made['reading_key'], route_before=made.get('route_before'),
                            export=ExportStatus(**made['export']))

    def promote(self, asked: PromoteRequest) -> PromoteGiven:
        """Records a person's promotion of a Lab reading and asks for the export (#18). Raises HTTPException 403 when switched
        off, 404 for a knowledge base or page not served here, and ValueError with the core's own sentence for anything but a
        valid page/1 Lab reading of that page."""
        if not self.enabled:
            raise HTTPException(403, SWITCHED_OFF)
        store = self.bases.get(asked.knowledge_base)
        if store is None:
            raise HTTPException(404, f'no knowledge base {asked.knowledge_base!r} is served here')
        row = store.row(asked.work, asked.pdf_page)
        if row is None:
            raise HTTPException(404, f'{asked.work} has no page {asked.pdf_page} here')
        made = human_verdict.promote_from_view(reading_export.BASES[asked.knowledge_base], self.queues[asked.knowledge_base],
                                               row['work'], asked.pdf_page, asked.reading_key, asked.reason,
                                               note=asked.note or None)
        return PromoteGiven(reading_key=made.get('reading_key', asked.reading_key), export=ExportStatus(**made['export']))

    def preview(self, asked: PreviewRequest) -> TablePreview:
        if not self.enabled:
            raise HTTPException(403, SWITCHED_OFF)
        return TablePreview(rows=table_correction(asked.text))
