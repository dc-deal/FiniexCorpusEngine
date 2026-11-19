"""Each knowledge base's page readings as the core exports them (decisions 72.a, 80.a), shaped for the views.

An export is a folder: `index.json` holds the works and one row per PDF page with its reading's trace and check,
`<work>/pNNNN.md` the reading itself. The free export is tracked in `corpus/readings/`, so every view works on a clone; the
licensed one lies in `_work/licensed/readings/`, git-ignored, on this machine only. Both have one shape and take one code
path, and every row names its own knowledge base. A reading is parsed by the core's own parser (`page_contract.parse`), so
a view shows what the pipeline understood, and the model's text never reaches the browser as HTML: prose arrives as text,
math and code segments, a table as its parsed cells. The original is rendered by the core's own `page_render.render`, which
gives the exact image the reader received; its sha256 is in the row, so the match is stated rather than assumed. The text
the search and the chat quote for a page comes from the core's one function for it (`reading_export.quoted_pages`).
"""

import hashlib
import json
import re
import threading
from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import pymupdf
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.configuration import data_paths
from backend.conversion.checks import integrity
from backend.conversion.contract import page_contract
from backend.conversion.reading import page_render
from backend.conversion.store import reading_export, reading_store, served_readings

FREE_EXPORT = data_paths.FREE_READINGS
LICENSED_EXPORT = data_paths.LICENSED_WORKING / 'readings'
# The knowledge bases the core exports, one index each (decision 80.a); every row carries its own.
KnowledgeBase = Literal['free', 'licensed']
# The check states a person should look at: an issue the judge or a check found, a reading the provider blocked or the reader
# declined, a work the judge stopped. Each page keeps the core's word for its state (`issue` since decision 97.a).
LISTED_AS_ISSUE = ('issue', 'blocked', 'stopped')
# The routes of a page whose reading is not served, each in the core's own words for why: its PDF's text layer serves it, or a
# licensed work's legacy Markdown where it has one (H2.a, 19 Nov). A page's route is one of them exactly when its reading is
# not served; the core decides it, this module only asks.
NOT_SERVED_ROUTES = served_readings.FALLBACK_ROUTES


class Count(BaseModel):
    value: str
    count: int


class StateCount(Count):
    """A listed state's count, and how many of its pages a person's standing verdict accepted, rejected or noted (166.a:
    "ok 399 · 1 accepted"; 211.a: "decided by a person 8 · 7 accepted · 1 noted"). `counted_states` sets them on every
    count it makes; they are optional only so a count of an older shape still reads."""

    accepted: int | None = None
    rejected: int | None = None
    noted: int | None = None
    # of a state to look at (issue, blocked, stopped), how many of its pages the core serves all the same, its reading and
    # not the text layer: an issue whose findings lie on blocks never quoted (133.b) is served (the operator, 18 Nov: "issue
    # 9" read as nine pages held back where the core held back none); None for every other state, and where none is served
    served: int | None = None


class WorkReadings(BaseModel):
    """A work's page readings in figures, each value as often as it occurs."""

    pages: int
    states: list[StateCount]
    routes: list[Count]
    people: list[Count] = []  # the pages a person's standing verdict marks, by `PersonMark.standing`
    reviews: list[Count] = []  # the pages an automated review's standing verdict marks, by its standing, never a person's
    categories: list[Count] = []  # the pages by category (172.a), content first, `NOT_NAMED` where no reading named it


class Finding(BaseModel):
    kind: str
    block: str | None  # the reading's block id; None where the judge named none
    severity: str
    evidence: str | None  # the judge's own short note, which may quote a few words of the page: shown as text
    # The core found that the finding names no difference (147.a): its evidence quotes the same text as printed and as
    # written, or every string it quotes stands in the block and in the text layer. Shown as such, never hidden.
    void: bool = False
    block_class: str | None = None


class Verdict(BaseModel):
    verdict: str
    outcome: str  # the outcome that counts
    findings: list[Finding]
    judge_outcome: str | None = None  # the judge's own outcome, where a void finding made the counting one differ
    void: int = 0  # how many of its findings are void


class Stage2Finding(BaseModel):
    """What stage 2 found comparing the reading with the PDF's text layer; an older plan gives the kind alone."""

    kind: str
    block: str | None = None
    detail: str | None = None
    severity: str | None = None


class Unverifiable(BaseModel):
    """A block stage 2 cannot check against the text layer, and why; an older plan gives the why alone."""

    why: str
    block: str | None = None
    cls: str | None = None


class Stage2(BaseModel):
    """Stage 2 of the check (146.a): the reading against the PDF's text layer, in figures and findings."""

    suspicious: bool | None = None
    has_layer: bool | None = None
    recall: float | None = None
    precision: float | None = None
    findings: list[Stage2Finding] = []
    unverifiable: list[Unverifiable] = []


class Judge(BaseModel):
    """Which judge judged the reading the page shows, and with which version of its prompt (147.a)."""

    model: str
    provider: str | None = None
    mode: str | None = None
    cost_usd: float | None = None
    version: str | None = None


class Check(BaseModel):
    state: str
    # Each reason once with how often it was given: the judge's findings repeat one reason per finding.
    reasons: list[Count]
    judged: bool
    why_judged: str
    verdict: Verdict | None
    stage2: Stage2 | None = None  # None where no stage 2 report holds this reading
    judge: Judge | None = None


class PersonVerdict(BaseModel):
    """A person's verdict on a page or one of its blocks (146.a): accept, reject or a note, with the reason given. One
    given on an earlier reading of the page does not apply to the one shown, and says so."""

    reading_key: str | None = None
    applies: bool = True
    block: str | None = None
    verdict: str
    reason: str | None = None
    reason_text: str | None = None
    tag: str | None = None
    note: str | None = None
    given_by: str | None = None
    given_at: str | None = None
    # A person's two manual parts (decision 188.a), shown as such, never served: the block's text as the person says it
    # reads, and their assessment of the judge (right, right_for_a_wrong_reason, false_alarm, missed) in their words
    correction: str | None = None
    judge_assessment: str | None = None
    judge_assessment_text: str | None = None
    # the judge whose finding the assessment rates, by its version ('judge/1'), from `assessed_judge`; None without an
    # assessment, or where no judgement counted on that reading when the person gave it
    assessed: str | None = None
    # a correction of a table block as the reading's own cells (`table_correction`, 204.a); None for any other correction,
    # which stays the text it is
    correction_rows: 'list[list[Cell]] | None' = None
    # given before the page's latest reset (191.a): shown, greyed, never applying; `archived_at` is that reset's time
    archived: bool | None = None
    archived_at: str | None = None
    # a person's own verdict, or an automated review's, given by a session on the operator's delegation (the operator,
    # 18 Nov: "a person is always manual"): the view names it so wherever it stands, and only a person's protects a page.
    # By the core's own rule (`served_readings.by_a_person`), so an export written before says it by the giver alone
    by_a_person: bool = True

    @model_validator(mode='before')
    @classmethod
    def whose(cls, given: Any) -> Any:
        if isinstance(given, dict) and given.get('by_a_person') is None:
            return {**given, 'by_a_person': served_readings.by_a_person(given)}
        return given


class PageReset(BaseModel):
    """A person's reset of a page (191.a): the reading discarded, the text layer served until a new reading is due."""

    reason: str | None = None
    given_by: str | None = None
    given_at: str | None = None


def person_reason(verdict: dict) -> str | None:
    """A verdict's reason in words; for the reason `other`, whose words are a placeholder, the start of the person's note,
    cut at about 60 characters, as the core's route says it (the operator on finance p. 387)."""
    note = verdict.get('note') or ''
    if verdict.get('reason') == 'other' and note:
        return note if len(note) <= 60 else f"{note[:60].rsplit(' ', 1)[0]} …"
    return verdict.get('reason_text') or verdict.get('reason')


class PersonMark(BaseModel):
    """A person's standing verdict on the reading a page shows, beside the judge's state wherever a page's state stands
    (decision 166.a): accepted or rejected by the latest accept or reject that applies, as the core decides what is served
    (`served_readings.human_standing`); noted where only a note applies, which never changes what is served. Its reason
    and note go in the hover."""

    standing: Literal['accepted', 'rejected', 'noted']
    reason: str | None = None
    note: str | None = None
    given_by: str | None = None
    given_at: str | None = None
    by_a_person: bool = True  # False for an automated review's verdict (`PersonVerdict.by_a_person`)


def person_mark(row: dict) -> PersonMark | None:
    """A page's person mark, or None where no verdict applies to its reading. It stands for an automated review's verdict
    too, as the core serves by it, and says whose it is (`by_a_person`)."""
    verdict = served_readings.human_standing(row)
    if verdict is not None:
        standing = 'accepted' if verdict['verdict'] == 'accept' else 'rejected'
    else:
        notes = [one for one in row.get('human') or [] if one.get('applies') and one.get('verdict') == 'note']
        if not notes:
            return None
        verdict, standing = notes[-1], 'noted'
    return PersonMark(standing=standing, reason=person_reason(verdict), note=verdict.get('note'),
                      given_by=verdict.get('given_by'), given_at=verdict.get('given_at'),
                      by_a_person=served_readings.by_a_person(verdict))


class StatePages(BaseModel):
    """The pages behind one count of a unit (decision 225.a): what the count opens, in a state a person should look at or
    one a person decided (`OPENED_BY_A_COUNT`)."""

    value: str
    pages: list[int]  # PDF pages, ascending


class OutlineUnit(BaseModel):
    """One unit of a work's own order as the core cut it (decision 84.a), with its whole subtree's pages in figures."""

    id: str  # numbered per work in reading order, and renumbered when the outline changes: never kept in a link or setting
    level: int
    title: str
    parent: str | None  # the enclosing unit; None at the top
    first_page: int  # where its heading is
    last_page: int  # where its own text, or its last sub-unit's, ends
    indexed: bool  # False for back matter, which the chat's index leaves out
    # The pages whose text lies in this unit or in one beneath it, each once (the operator's 7.a: a chapter shows what is inside)
    pages: int
    # the pages whose text is the unit's own, outside every unit beneath it: the caption of its block of pages (161.a)
    own_pages: int = 0
    states: list[StateCount]
    # the pages behind each count that opens them (225.a): a state to look at, or one a person decided; none for ok
    state_pages: list[StatePages] = []


class PageRow(BaseModel):
    pdf_page: int
    printed_label: str | None  # the number printed on the page, from its reading; None where it has none
    # The units whose text lies on this page, in reading order: [] for a page outside every unit (before the first, or a
    # contents page), None where the export carries no outline for its work
    units: list[str] | None
    route: str
    check: Check
    class_when_collected: str
    class_now: str
    attempt: int
    cost_usd: float | None  # None for a reading read in a Claude Code session (280.a): see `reading_cost`
    error_message: str | None  # the provider's own sentence where a reading failed, e.g. its content filter's
    # The page's text comes from its PDF's text layer, and its route says why: the view's answer where the provider gave
    # no sentence, as for a page the reader declined (line 1, 2026-11-04).
    # Since H2.a it means "served by a fallback", a licensed work's legacy Markdown too; renamed in stage D
    from_text_layer: bool
    # the route's level as the export gives it, and its words after the first ': ', as the route table parts them (159.a):
    # a page list says the why in its own column and keeps the whole route for the hover
    route_level: str | None = None
    route_why: str | None = None
    person: PersonMark | None = None  # a person's standing verdict beside the state (166.a)
    # what kind of page it is (decision 172.a): the reader's `page_kind`, and the export's category from it (content,
    # exercise, index, contents, front matter, back matter, cover, blank, advertisement); None where no reading named it
    category: str | None = None
    page_kind: str | None = None
    category_said: str | None = None  # what the category means, for its hover (177.a); None for content
    # the state a list counts and narrows it by (`listed_state`, 211.a): its check's, or `DECIDED` where a person settled it
    listed_state: str | None = None


class RouteRow(BaseModel):
    """One route a work's pages are served by, as a person reads the routes (the operator, 10 Nov: "is this route a faulty one?"): how good it is, where the text comes from, by which reader, why, and on how many pages."""

    route: str  # the route as the export writes it: the key the page list filters by
    level: str | None  # checked, noted or fallback, the export's `route_level`; None in an export written before it
    source: str  # vision reading, second reader or text layer
    reader: str | None  # model, contract and validator of a reading; None for the text layer
    why: str | None  # the route's words after its first ': '; None for a reading served as checked
    pages: int


class RouteLevel(BaseModel):
    """A route level, what it means in the core's words (`served_readings.ROUTE_LEVELS`), and how many of the work's pages
    are served at it: the routes' one line, and their legend."""

    level: str
    says: str
    pages: int = 0


class WorkPages(BaseModel):
    knowledge_base: KnowledgeBase
    source_id: str
    title: str
    summary: WorkReadings | None
    # Each route once, checked first, then noted, then fallback, each by its pages; the legend beside it
    routes: list[RouteRow] = []
    route_levels: list[RouteLevel] = []
    # The work's own order: None where the export carries none (not exported yet, or its PDF was missing at export), []
    # where the PDF has no bookmarks. The pages lying in no unit are summed apart.
    outline: list[OutlineUnit] | None
    outside_outline: WorkReadings | None
    pages: list[PageRow]


class Trace(BaseModel):
    """Where a reading came from: everything the export records about it except its check."""

    reading_key: str
    model: str
    form: str
    contract: str
    validator: str
    attempt: int
    cost_usd: float | None  # None for a reading read in a Claude Code session (280.a): see `reading_cost`
    stored_at: str
    class_when_collected: str
    class_now: str
    error_type: str | None
    error_message: str | None
    text_sha256: str | None
    image_sha256: str
    image_size: list[int]
    resolution: str


class Segment(BaseModel):
    """A piece of prose as the core parsed it: text, math, code, or an inline mark of its own (decision 206.a): a note's
    marker (`fn`, "[4]{.fn}"), a superscript (`sup`) or a subscript (`sub`). A marker names the footnote on the same page
    whose `marker` is its content (`with_notes`), and carries that note's text, so the view links the two; both None where
    the page has no such note."""

    # `br`: a line break inside a table cell, as the reader wrote it with <br> (page/1 allows it there); its content "\n"
    kind: Literal['text', 'math', 'code', 'fn', 'sup', 'sub', 'br']
    content: str
    note: str | None = None  # the footnote block's id
    note_text: str | None = None  # its text, as the view's card shows it


class Cell(BaseModel):
    segments: list[Segment]
    header: bool
    rowspan: int
    colspan: int


class StandingCorrection(BaseModel):
    """The correction that stands for a block (decision 229.a, the operator: "what you really want to see first is the correction"): the
    latest a person gave that applies to the reading shown, drawn first as the block's content, the reader's text muted
    beneath it. Never served: the search and the chat quote the reading or the text layer, and the reading is unchanged."""

    text: str
    rows: list[list[Cell]] | None = None  # a table block's correction as cells (204.a); None for any other
    given_by: str | None = None
    given_at: str | None = None
    by_a_person: bool = True  # False where an automated review gave it (`PersonVerdict.by_a_person`)


class Block(BaseModel):
    """One block of a reading, in the form the view draws it; which of the body fields is set depends on the class."""

    id: str
    block_class: str
    group: str  # the contract's group: content, structure, apparatus, navigation, furniture, non_verbatim
    content: str  # the contract's content kind: V verbatim, V* verbatim encoding, D derived (never quoted), - no body
    attrs: dict[str, str]
    bbox: list[int] | None
    segments: list[Segment] | None  # prose, with math and code taken out
    latex: str | None  # a formula
    rows: list[list[Cell]] | None  # a table
    code: str | None  # a listing
    text: str | None  # any other body, as written
    findings: list[Finding]  # the judge's findings that name this block, shown beside what they are about
    people: list[PersonVerdict] = []  # a person's verdicts that name this block
    # why the block is decoration, not content (decision 194.a, the operator: "just a decorative image, not a real photo"): a photo on a
    # chapter opener is chapter art. The view shows it quietly, folded, its findings after the rest; None for any other block
    decorative: str | None = None
    # its body as the reader wrote it, a table's as its HTML: what a person's correction starts from in the page view's
    # verdict dialog (213.b); the reading's own text, which the page already serves as `raw`
    body: str | None = None
    # a person's correction that stands for this block on the reading shown (229.a), None where there is none
    correction: StandingCorrection | None = None


class ReadingError(BaseModel):
    """A validator error on the reading, parted into what it names (decision 228.a, the operator on accounting p. 398: "then the only thing that still confuses me is that the error stands at the top, although I entered a correction"): the block and the line, where it
    names them, so the view marks the error on its block and opens the raw text at its line. `looked` is the verdict of
    the latest person's verdict that applies to the block, else to the page as a whole (`looked_at`), and `corrected`
    whether a person's correction stands for the block: the view then mutes the error and says so, never hides it, as the
    error is the validator's verdict on the reading, which a person's verdict does not change."""

    said: str  # the error as the validator wrote it
    message: str  # what it says, without its place
    block: str | None = None
    line: int | None = None  # counted as the validator counts: line 1 is the front matter's first `---`
    # the first and last line of the block it names, from its opening fence to its closing one (`block_lines`); None for
    # an error that names a line alone, or no place
    lines: list[int] | None = None
    # the page line the fault itself stands on, where the validator names it in its message (page/1.4: "LaTeX command
    # outside math on line 28: …" in a block that opens on line 26); None where it names only the block's place
    at_line: int | None = None
    looked: str | None = None
    looked_at: Literal['block', 'page'] | None = None
    # whether the verdict that looked is a person's own or an automated review's (`PersonVerdict.by_a_person`)
    looked_by_a_person: bool | None = None
    corrected: bool = False


class Reading(BaseModel):
    front: dict[str, str]
    blocks: list[Block]
    errors: list[str]
    warnings: list[str]
    # the same errors, parted and with whether a person has looked (228.a)
    error_places: list[ReadingError] = []


class AttemptCheck(BaseModel):
    """What the check made of one reading: its state, the judge's verdict where it judged, and the check's outcome."""

    state: str
    verdict: str | None = None
    outcome: str | None = None
    # why the check gave its state, in the core's words ("format: malformed", "judge: bad"); [] where nothing is wrong
    reasons: list[str] = []
    # where the check comes from, where it is not the latest run's: "an earlier check" for a reading checked before
    came_from: str | None = Field(default=None, validation_alias='from')

    @field_validator('reasons', mode='before')
    @classmethod
    def none_is_empty(cls, given: list[str] | None) -> list[str]:
        """An export written before the reasons were exported has none: null reads as nothing said."""
        return given or []


class ReaderRule(BaseModel):
    """A rule a judge proposed for the reader (decisions 195.a, 197.a: judge/4), shown read-only beneath its judgement and
    never applied (202.a): its kind (a format rule, a class or an attribute of the vocabulary), the block that asked for it,
    the rule in the judge's words, and the class, attribute and value it names, where it names one. The export writes ''
    for a field not set; here it is None."""

    kind: str
    block: str | None = None
    rule: str | None = None
    block_class: str | None = Field(default=None, validation_alias='class')
    attribute: str | None = None
    value: str | None = None

    @field_validator('block', 'rule', 'block_class', 'attribute', 'value', mode='before')
    @classmethod
    def unset(cls, given: str | None) -> str | None:
        return given or None


class Judgement(BaseModel):
    """One judge's judgement of one reading (147.a), oldest first: by which version of the judge's prompt, in which state
    that version is (a prototype, the active one, retired), whether the judge was asked again, and whether it counts."""

    version: str | None = None
    version_state: str | None = None
    model: str | None = None
    mode: str | None = None
    again: int = 0
    stored_at: str | None = None
    verdict: str | None = None
    outcome: str | None = None
    judge_outcome: str | None = None
    findings: list[Finding] = []
    # the rules it proposed for the reader (202.a), judge/4's alone; None where the export names none
    reader_rules: list[ReaderRule] | None = None
    cost_usd: float | None = None
    counts: bool = True
    # how to show it on the page (181.a): '<reading key>:<version>:<again>', the value of the page view's `?judgement=`
    recall: str | None = None


class Attempt(BaseModel):
    """One reading ever bought for a page, as the export lists them, oldest first. Its text stays in the private store;
    only the reading the page shows is exported, so the others are shown by their record alone."""

    reading_key: str
    # Its place among all the page's readings, every reader's, from 1 for the oldest (the operator on accounting p. 524: "reading 1
    # ... 4"); `attempt` is its own reader's count, from 0
    number: int
    # What it was, in the core's words (86efdb2): "first reading", "the one format retry", "format retry with the errors
    # as a hint, after a plain retry" (113.a), "read again with the judge's findings as a hint", "second reader", "read
    # again by a replay". None in an export written before the core said it.
    purpose: str | None = None
    cell: str | None = None  # the reading cell that bought it
    # the version of the reader's instructions it was read with ("page/1"), and whether that version is a prototype read
    # beside the pipeline (decision 210.a): such a reading is never served, chosen or checked, and the view keeps it in the Lab
    reader_version: str | None = None
    prototype: bool | None = None
    retry_of: str | None = None  # the reading a re-read with the judge's findings re-read, by its key
    retry_of_number: int | None = None  # and by its number among the page's readings
    model: str
    mode: str | None  # how it was asked: a batch, a standard call, another reader
    attempt: int
    class_now: str  # its class under today's validator
    stored_at: str
    deviation: str | None = None  # why a reading is off the default reader, where it is (63.a)
    # what the reading cost; None for one read in a Claude Code session (280.a), whose cost no API ledger holds
    cost_usd: float | None = None
    # the validator's messages where the reading failed its format check, as the core wrote them, at most 8; [] otherwise.
    # They say why a reading is malformed where no check ran on it, as on a reading its one format retry replaced
    format_errors: list[str] = []
    check: AttemptCheck | None = None  # None where no check ran on this reading
    judgements: list[Judgement] = []  # every judgement of this reading, oldest first
    shown: bool  # the reading this page shows and serves

    @field_validator('format_errors', mode='before')
    @classmethod
    def none_is_empty(cls, given: list[str] | None) -> list[str]:
        """The export writes null for a reading that passed its format check."""
        return given or []


class Chosen(BaseModel):
    """Why the page's reading was chosen over its others, by which run and when (the pipeline database, 51.a)."""

    why: str
    run_id: str
    chosen_at: str


class PageImage(BaseModel):
    available: bool
    why_not: str | None
    width: int | None
    height: int | None
    # The rendered image's sha256 equals the one the reader received; None when nothing could be rendered.
    same_as_read: bool | None


class PageDetail(BaseModel):
    knowledge_base: KnowledgeBase
    source_id: str
    title: str
    pdf_page: int
    printed_label: str | None
    previous_page: int | None
    next_page: int | None
    route: str
    # The page's text is served from its PDF's text layer: whatever reading is shown is not what the search and the chat
    # quote, and the view says so (a reading the judge found bad, one that stayed malformed, a page the reader declined)
    # Since H2.a it means "served by a fallback", a licensed work's legacy Markdown too; renamed in stage D
    from_text_layer: bool
    # A page that is not plainly ok says so in one sentence before its chips (`said_of`); None for an ok page
    said: str | None = None
    person: PersonMark | None = None  # a person's standing verdict beside the state (166.a)
    # what kind of page it is (decision 172.a): the reader's `page_kind`, and the export's category from it (content,
    # exercise, index, contents, front matter, back matter, cover, blank, advertisement); None where no reading named it
    category: str | None = None
    page_kind: str | None = None
    category_said: str | None = None  # what the category means, for its hover (177.a); None for content
    # the route in its parts, for the page head's labelled lines (184): its level, source, reader and why
    route_level: str | None = None
    route_source: str | None = None
    route_reader: list[str] | None = None
    route_why: str | None = None
    # the head's own "Why:" line (`why_line`): the route's why where nothing else on the page says it; None where the
    # sentence above does, or where it is a person's verdict that stands beneath a block of the reading
    why_line: str | None = None
    # what the findings come to (184, the operator: "what does 'findings at b12' mean when the page is accepted?"): each block
    # with findings, in reading order, and whether they stand or code voided them, then what that means for the page
    findings_at: list['FindingsAt'] | None = None
    findings_outcome: str | None = None
    # the block a page opens on (186): the first in reading order that a finding names; None for a page without one
    focus: str | None = None
    # a person checked the page and no re-read happens without a reason, and a person's reset of it (both 191.a)
    protected: bool | None = None
    reset: PageReset | None = None
    # the state the lists count it by (`listed_state`, 211.a): its check's, or `DECIDED` where a person settled it
    listed_state: str | None = None
    trace: Trace
    check: Check
    # The judge's findings that name no block of the reading: about the page as a whole, or about a block it does not have.
    page_findings: list[Finding]
    reading: Reading | None  # None where the provider blocked the reading and no text came back, or its file is gone
    raw: str | None  # the reading exactly as stored, shown escaped
    # Is the reading file still what was checked, in the core's words (69.a): `whole`, `tampered` (it differs from the
    # checked text), `missing` (it is gone) or `no reading` (a row without one). Asked on every visit, so a change shows.
    integrity: str
    image: PageImage
    # Every reading bought for the page, oldest first; None where the export lists none yet. Without a choice recorded, the
    # latest attempt stands.
    attempts: list[Attempt] | None
    chosen: Chosen | None
    human: list[PersonVerdict] = []  # a person's verdicts on this page and its blocks (146.a)


class QuotedText(BaseModel):
    """The text the search and the chat quote for a page (decision 93.a), from the core's one function for it: the served
    reading as quotable text, or the cleaned text layer where the reading is not served."""

    knowledge_base: KnowledgeBase
    source_id: str
    pdf_page: int
    text: str | None  # None where the core holds no quoted text for this page


class FindingsAt(BaseModel):
    block: str
    said: str  # 'void by code' where code voided every finding on it, else 'stands'
    # the gravest severity among its findings that stand, as the head shows it with a finding's own look (the operator, 12 Nov, on
    # accounting p. 524); None where code voided them all
    severity: str | None = None


# A finding's severities, gravest first: the head's line takes the first a block's standing findings carry
SEVERITY_ORDER = ('major', 'minor')


def gravest(findings: 'list[Finding]') -> str | None:
    """The gravest severity among the findings that stand, by `SEVERITY_ORDER`; one it does not know after those it does."""
    standing = [finding.severity for finding in findings if not finding.void]
    if not standing:
        return None
    rank = {severity: at for at, severity in enumerate(SEVERITY_ORDER)}
    return min(standing, key=lambda severity: rank.get(severity, len(rank)))


class IssueRow(BaseModel):
    knowledge_base: KnowledgeBase
    source_id: str
    title: str
    pdf_page: int
    route: str
    check: Check
    error_message: str | None
    # served by a fallback, the text layer or a licensed work's legacy Markdown (H2.a); renamed in stage D
    from_text_layer: bool
    # as a work's page row has them (159.a): the route's level and why, the whole route kept for the hover
    route_level: str | None = None
    route_why: str | None = None
    person: PersonMark | None = None  # a person's standing verdict beside the state (166.a)
    # what kind of page it is (decision 172.a): the reader's `page_kind`, and the export's category from it (content,
    # exercise, index, contents, front matter, back matter, cover, blank, advertisement); None where no reading named it
    category: str | None = None
    page_kind: str | None = None
    category_said: str | None = None  # what the category means, for its hover (177.a); None for content
    # not content (`apart`): the Issues list it after the rest, under a heading of its own, as noted rather than repaired
    apart: bool = False
    # the block a link to the page opens on (186): its first finding's block in reading order, None without one
    focus: str | None = None
    # the state the lists count it by (`listed_state`, 211.a): its check's, or `DECIDED`, which the Issues fold apart
    listed_state: str | None = None


class IssueList(BaseModel):
    knowledge_bases: list[Count]
    states: list[StateCount]
    people: list[Count] = []  # the listed pages a person's standing verdict marks, by its standing
    reviews: list[Count] = []  # the listed pages an automated review's standing verdict marks, by its standing
    categories: list[Count] = []  # the listed pages by category (172.a)
    rows: list[IssueRow]


def counted(values: list[str]) -> list[Count]:
    """Each value once with its count, in the order of first appearance."""
    return [Count(value=value, count=count) for value, count in Counter(values).items()]


# A page read but not yet reached by a check run: its row's `check` is null (a licensed rollout round before its check, seen
# 2026-11-05). It is said as such, in line 1's words, never counted as fine, and not listed as an issue: nothing has been
# found wrong with it.
UNCHECKED = 'not_yet_checked'


# A page the check lists as one to look at, on which a person's verdict stands (decision 211.a, the operator: "I would like to take pages judged by a person out of the issues"): it is counted and listed in a bucket of its own, no longer as an issue,
# as the served route and the core's shelf already follow the person. Its check state stays in its record, never hidden.
DECIDED = 'decided_by_a_person'
# The same where an automated review's verdict stands (Q.a, 18 Nov, on the operator's 2.a: "a person is always manual"): the
# core serves the page by it, so it leaves the open Issues, but it is counted and folded apart, never as a person's.
DECIDED_BY_REVIEW = 'decided_by_an_automated_review'


# The order states are counted in wherever they stand side by side, so a column of chapter heads reads alike: fine first,
# then what is not known, then what a person settled, then what a review settled, then what to look at. A state the core
# adds later follows, in the order it appears.
STATE_ORDER = ('ok', 'ok_unjudged', UNCHECKED, DECIDED, DECIDED_BY_REVIEW, 'blocked', 'issue', 'stopped')

# The counts of a chapter that open their pages (225.a): what a person should look at, and what a person decided, whose
# verdict is worth seeing again (accounting p. 398 left the issues for this bucket on 12 Nov); a fine count, and one not
# yet checked, stay figures
OPENED_BY_A_COUNT = (DECIDED, DECIDED_BY_REVIEW, *LISTED_AS_ISSUE)


def state_of(row: dict) -> str:
    return row['check']['state'] if row.get('check') else UNCHECKED


def listed_state(row: dict) -> str:
    """The state a list counts and narrows a page by (211.a): its check's state, or `DECIDED` where that state is one to look
    at and a person's verdict stands on the reading shown. "Stands" as the page's person mark says it, by the core's own
    rule (`served_readings.human_standing`, else an applying note): a verdict a reset archived, or one given on another
    reading, applies to none, so such a page is an issue again. Where the verdict is an automated review's, the bucket is
    `DECIDED_BY_REVIEW`."""
    state = state_of(row)
    mark = person_mark(row) if state in LISTED_AS_ISSUE else None
    return state if mark is None else DECIDED if mark.by_a_person else DECIDED_BY_REVIEW


def counted_states(rows: list[dict]) -> list[StateCount]:
    """Each listed state of the rows once with its count, in `STATE_ORDER`, and how many of its pages a person's standing
    verdict accepted, rejected or noted (166.a, 211.a); an automated review's never counts as a person's."""
    rank = {state: at for at, state in enumerate(STATE_ORDER)}
    standings = Counter((listed_state(row), mark.standing) for row in rows
                        if (mark := person_mark(row)) is not None and mark.by_a_person)
    served = Counter(state for row in rows if (state := listed_state(row)) in LISTED_AS_ISSUE
                     and row.get('route') and row['route'] not in NOT_SERVED_ROUTES)
    return sorted((StateCount(value=count.value, count=count.count, accepted=standings[(count.value, 'accepted')],
                              rejected=standings[(count.value, 'rejected')], noted=standings[(count.value, 'noted')],
                              served=served[count.value] or None)
                   for count in counted([listed_state(row) for row in rows])),
                  key=lambda count: rank.get(count.value, len(rank)))


def counted_people(rows: list[dict], by_a_person: bool = True) -> list[Count]:
    """The rows a person's standing verdict marks, by its standing: accepted, rejected, noted, in that order; with
    `by_a_person` False, the rows an automated review's marks."""
    standings = Counter(mark.standing for row in rows
                        if (mark := person_mark(row)) is not None and mark.by_a_person == by_a_person)
    return [Count(value=standing, count=standings[standing]) for standing in ('accepted', 'rejected', 'noted') if standings[standing]]


# A page no reading named the kind of (decision 172.a): a blocked page, or one read before the reader said it. It counts
# with the content, since nothing says it is not.
NOT_NAMED = 'not named'
CONTENT = 'content'


# What each category but content means, in one line for its hover (decision 177.a, the operator): the term stays as it is, the
# line says what it holds. Every category the core can give (`reading_export.CATEGORY_OF_KIND`, and exercise) has one.
CATEGORY_SAID = {
    'exercise': 'questions and problems: a page whose every section is an exercise section, which the search ranks below the '
                'text that explains',
    'index': 'the alphabetical list of terms at the end of the book, each with the pages it stands on',
    'contents': 'the table of contents: the chapters and sections with the pages they begin on',
    'front matter': 'before the main text: title pages, copyright, preface, acknowledgements, supporters',
    'back matter': 'after the main text: appendix, answers, glossary, references, index',
    'cover': 'the front or back cover of the book',
    'blank': 'a page with no text of its own, or none but its number',
    'advertisement': "a page advertising the publisher's other titles or services",
}


def category_said(row: dict) -> str | None:
    return CATEGORY_SAID.get(row.get('category') or '')


def category_of(row: dict) -> str:
    return row.get('category') or NOT_NAMED


def apart(row: dict) -> bool:
    """A page that is not content (172.a): an exercise, an index, contents, front or back matter, a cover, a blank page or
    an advertisement. An issue on it is noted, not repaired (169.a), so the Issues list it after the rest."""
    return category_of(row) not in (CONTENT, NOT_NAMED)


def counted_categories(rows: list[dict]) -> list[Count]:
    """The rows by category: content first, then the others by how many, the pages no reading named last."""
    found = Counter(category_of(row) for row in rows)
    order = sorted(found, key=lambda category: (category != CONTENT, category == NOT_NAMED, -found[category], category))
    return [Count(value=category, count=found[category]) for category in order]


def readings_of(rows: list[dict]) -> WorkReadings | None:
    """Rows in figures: how many, and each state and route as often as it occurs; None for no rows."""
    if not rows:
        return None
    return WorkReadings(pages=len(rows), states=counted_states(rows), routes=counted([row['route'] for row in rows]),
                        people=counted_people(rows), reviews=counted_people(rows, by_a_person=False),
                        categories=counted_categories(rows))


SECOND_READER = f'{served_readings.READING_ROUTE}, second reader'
DIRECT_READING = f'{served_readings.READING_ROUTE}, {served_readings.DIRECT_ROUTE_KIND}'  # 280.a


def route_parts(route: str) -> tuple[str, str | None, str | None]:
    """A route in the words a person reads it by: its source, its reader and why, split where the core's route strings
    part them (`served_readings.route_of`): 'text layer: why', or 'vision reading (reader): why', the why left out for a
    reading served as checked, and 'vision reading, second reader (reader): why' for a reading off the default. A route that
    serves no reading names its fallback as its source, the text layer or 'legacy markdown' (H2.a)."""
    head, _, why = route.partition(': ')
    if route in NOT_SERVED_ROUTES:
        return head, None, why or None
    kind, _, reader = head.partition(' (')
    source = {SECOND_READER: 'second reader', DIRECT_READING: served_readings.DIRECT_ROUTE_KIND}.get(kind, kind)
    return source, reader.removesuffix(')') or None, why or None


def attempts_of(row: dict) -> 'list[Attempt] | None':
    """Every reading bought for a page, in the export's order, oldest first, each numbered from 1 across its readers, and
    a re-read pointing to the number of the reading it re-read."""
    attempts = row.get('attempts')
    if attempts is None:
        return None
    numbers = {attempt['reading_key']: at + 1 for at, attempt in enumerate(attempts)}
    return [Attempt.model_validate({**attempt, 'number': at + 1, 'retry_of_number': numbers.get(attempt.get('retry_of')),
                                    'shown': attempt['reading_key'] == row['reading_key'],
                                    'judgements': [{**judgement, 'recall': recall_id(attempt['reading_key'], judgement)}
                                                   for judgement in attempt.get('judgements') or []]})
            for at, attempt in enumerate(attempts)]


def reading_cost(row: dict) -> float | None:
    """What the reading a page shows cost, as its own attempt records it: None for a reading read in a Claude Code
    session (280.a), whose cost no API ledger holds, so the view never says 0 for it. The page's row writes 0.0 there, so
    the shown attempt's own field counts where the export lists it; an export without it keeps the row's."""
    shown = next((attempt for attempt in row.get('attempts') or [] if attempt.get('reading_key') == row.get('reading_key')),
                 None)
    return shown['cost_usd'] if shown is not None and 'cost_usd' in shown else row.get('cost_usd')


def assessed_judge(person: dict, attempts: list[dict]) -> str | None:
    """The judge a person's assessment rates, by its version: the core records none (`human_verdict --judge-assessment`
    rates "the judge's finding on the block"), and the finding a person saw is the one of the judgement that counted on the
    reading they judged, the latest stored before they gave it. A prototype's judgement never counts, so beside judge/4's
    finding an assessment given on judge/1's says it is judge/1's (line 1's check-along on finance pp. 94 and 119)."""
    if not person.get('judge_assessment'):
        return None
    given = person.get('given_at')
    judgements = next((attempt.get('judgements') or [] for attempt in attempts
                       if attempt['reading_key'] == person.get('reading_key')), [])
    counted = [judgement for judgement in judgements if judgement.get('counts', True) and judgement.get('version')
               and (not given or not judgement.get('stored_at')
                    or datetime.fromisoformat(judgement['stored_at']) <= datetime.fromisoformat(given))]
    return counted[-1]['version'] if counted else None


def recall_id(reading_key: str, judgement: dict) -> str:
    """A judgement by its reading, its prompt's version and whether the judge was asked again: what the page view's
    `?judgement=` names (181.a), so a person can send it."""
    return f"{reading_key}:{judgement.get('version') or ''}:{judgement.get('again') or 0}"


def in_lab(judgement: dict) -> bool:
    """Tried beside the pipeline (150.a): a prototype's judgement or a judge asked again, never one that counts."""
    return not judgement.get('counts', True) and bool(judgement.get('again') or judgement.get('version_state') == 'prototype')


def recall_said(judgement: dict, number: int, attempt: dict | None = None) -> str:
    """What a recalled judgement is, in one line: 'judge/3 (prototype) on reading 2, never served', and for a reading a
    reader prototype made (210.a) 'judge/4 (prototype) on reading 2, read by page/2 (prototype), never served'."""
    name = judgement.get('version') or 'judge'
    if judgement.get('version_state'):
        name += f" ({judgement['version_state']})"
    if judgement.get('again'):
        name += ', asked again'
    on = f'reading {number}'
    if (attempt or {}).get('prototype'):
        on += f", read by {attempt.get('reader_version') or 'a reader'} (prototype)"
    role = 'counts' if judgement.get('counts', True) else 'never served' if in_lab(judgement) or (attempt or {}).get('prototype') else 'not counted'
    return f'{name} on {on}, {role}'


class Recalled(BaseModel):
    """One judgement shown on the page as it judged it (decision 181.a, the operator: "you see what the old judge looked like, applied to the page"): the reading it judged, read-only, its findings on that reading's blocks, and what is shown in
    one line. Never the standing view, and the view marks it so."""

    recall: str  # its id, as `Judgement.recall`
    reading_key: str
    reading_number: int
    version: str | None
    version_state: str | None
    again: int
    counts: bool
    said: str
    # the reading it judged, as the core parses it, with this judgement's findings on its blocks and a person's verdicts
    # on that reading; None where the reading's text is not on this machine, and `why_not` says so
    reading: Reading | None
    raw: str | None
    why_not: str | None = None
    page_findings: list[Finding] = []  # its findings that name no block of that reading
    image_size: list[int] | None  # the image that reading was read from, which its block frames are placed on


READING_KEY = re.compile(r'^[0-9a-f]{16,128}$')


def counted_as(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def listed(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


# The format check names a block's fault as 'block b12 (line 57): empty body (use status=unreadable)' (`page_contract`)
BLOCK_FAULT = re.compile(r'^block (b\d+) \(line \d+\): (.+)$')
EMPTY_BODY = 'empty body (use status=unreadable)'


def faults_said(errors: list[str]) -> str | None:
    """The format check's faults of one reading in a person's words: '2 blocks left empty (b12, b15)', the blocks with any
    other fault together, and faults outside a block counted. The check's own messages stand in the reading's details."""
    empty: list[str] = []
    other: list[str] = []
    outside = 0
    for error in errors:
        found = BLOCK_FAULT.match(error)
        if not found:
            outside += 1
        elif found[2] == EMPTY_BODY:
            empty.append(found[1])
        else:
            other.append(found[1])
    parts = [f"{counted_as(len(blocks), 'block')} {words} ({', '.join(blocks)})"
             for blocks, words in ((list(dict.fromkeys(empty)), 'left empty'), (list(dict.fromkeys(other)), 'not in the format'))
             if blocks]
    if outside:
        parts.append(f"{counted_as(outside, 'fault')} outside a block")
    return listed(parts) if parts else None


def fallback_of(row: dict) -> str | None:
    """What serves a page whose reading is not served, in the core's word (H2.a, 19 Nov): the row's `fallback`, 'legacy
    markdown' where a licensed work's legacy Markdown serves it and 'text layer' where its PDF's text layer does, None where
    the reading is served. An export written before the field: the text layer for every route that serves no reading."""
    if 'fallback' in row:
        return row['fallback']
    return served_readings.TEXT_LAYER if row.get('route') in NOT_SERVED_ROUTES else None


# what serves a page in a reading's place, by `fallback_of`: the sentence of a page not served, and its findings' outcome
SERVED_INSTEAD = {served_readings.LEGACY_ROUTE: "the IDE's legacy Markdown is served instead",
                  served_readings.TEXT_LAYER: "the PDF's text layer is served instead"}
SERVES = {served_readings.LEGACY_ROUTE: "the page serves the IDE's legacy Markdown",
          served_readings.TEXT_LAYER: 'the page serves its text layer'}


def said_of(row: dict, errors: list[str]) -> str | None:
    """A page that is not plainly ok in one plain sentence (the operator on accounting p. 524: the head "reads as code"): whether
    its reading is served, why, from the route's own why or, for a reading that failed the format check, from how many of
    the page's readings failed it and what the one shown left wrong, and what is served instead. None for an ok page, and
    for one no check has reached yet, whose state says all there is."""
    check = row.get('check')
    if not check or check['state'] in ('ok', 'ok_unjudged'):
        return None
    why = route_parts(row['route'])[2] or row['route']
    if 'format: malformed' in check['reasons']:
        attempts = row.get('attempts') or []
        failed = sum(1 for attempt in attempts if attempt.get('class_now') == 'malformed') or 1
        # under today's validator: a reading that failed when it was retried may pass today, and is then not counted
        why = (f"{counted_as(failed, 'reading')} failed the format check" if failed >= len(attempts)
               else f"{failed} of {len(attempts)} readings {'fails' if failed == 1 else 'fail'} the format check today")
        faults = faults_said(errors)
        if faults:
            why += f", the one shown here with {faults}" if len(attempts) > 1 else f", with {faults}"
    if row.get('route_level') != 'fallback':
        if why.startswith(('a person ', 'an automated review ')):
            return f"Served: {why.split(':', 1)[0]}."
        judged = any(reason.startswith('judge:') for reason in check['reasons'])
        return f"Served despite the judge's findings: {why}." if judged else f'Served with a note: {why}.'
    instead = SERVED_INSTEAD.get(fallback_of(row), 'nothing is served in its place')
    return f'Not served: {why}; {instead}.'


# The order a person reads the levels in: the checked reading first, the one that stands with a note, then the fallback
LEVEL_ORDER = tuple(served_readings.ROUTE_LEVELS)


def routes_of(rows: list[dict]) -> list[RouteRow]:
    """Each route of the rows once, with its level from the export and its pages; checked first, then noted, then
    fallback, then a route an older export gave no level, each group by its pages, most first."""
    pages = Counter(row['route'] for row in rows)
    levels: dict[str, str | None] = {}
    for row in rows:
        levels.setdefault(row['route'], row.get('route_level'))
    rank = {level: at for at, level in enumerate(LEVEL_ORDER)}
    found = [RouteRow(route=route, level=levels[route], source=source, reader=reader, why=why, pages=count)
             for route, count in pages.items() for source, reader, why in [route_parts(route)]]
    return sorted(found, key=lambda one: (rank.get(one.level, len(rank)), -one.pages, one.route))


def levels_of(routes: list[RouteRow]) -> list[RouteLevel]:
    """Each level in the core's order, with its words and the pages its routes serve."""
    return [RouteLevel(level=level, says=says, pages=sum(route.pages for route in routes if route.level == level))
            for level, says in served_readings.ROUTE_LEVELS.items()]


UNIT_FIELDS = ('id', 'level', 'title', 'parent', 'first_page', 'last_page', 'indexed')


def outline_of(work: dict | None, rows: list[dict]) -> list[OutlineUnit] | None:
    """A work's outline as the export carries it, each unit with the pages of its whole subtree counted once. The export
    lists a parent before its children, so a walk from the end folds each subtree into its parent before that parent is
    folded further up."""
    outline = (work or {}).get('outline')
    if outline is None:
        return None
    by_page = {row['pdf_page']: row for row in rows}
    pages: dict[str, set[int]] = {unit['id']: set() for unit in outline}
    for row in rows:
        for unit_id in row.get('units') or []:
            if unit_id in pages:
                pages[unit_id].add(row['pdf_page'])
    own = {unit_id: len(found) for unit_id, found in pages.items()}  # before the subtrees are folded in
    for unit in reversed(outline):
        if unit['parent'] in pages:
            pages[unit['parent']] |= pages[unit['id']]
    return [OutlineUnit(**{name: unit[name] for name in UNIT_FIELDS}, pages=len(pages[unit['id']]), own_pages=own[unit['id']],
                        states=counted_states([by_page[page] for page in sorted(pages[unit['id']])]),
                        state_pages=pages_by_state([by_page[page] for page in sorted(pages[unit['id']])])) for unit in outline]


def pages_by_state(rows: list[dict]) -> list[StatePages]:
    """The rows' pages in each listed state a count opens (`OPENED_BY_A_COUNT`), in `STATE_ORDER`, each as the count beside
    it counts it (`listed_state`), so a count and the pages it opens never differ (225.a)."""
    found: dict[str, list[int]] = {}
    for row in rows:
        if (state := listed_state(row)) in OPENED_BY_A_COUNT:
            found.setdefault(state, []).append(row['pdf_page'])
    rank = {state: at for at, state in enumerate(STATE_ORDER)}
    return [StatePages(value=state, pages=sorted(found[state])) for state in sorted(found, key=lambda state: rank.get(state, len(rank)))]


def check_of(row: dict, stages: bool = False) -> Check:
    """The row's check; with `stages`, stage 2's report and the judge as well, which only a page's own view shows (a list
    of a thousand pages would carry them for nothing)."""
    check = row.get('check')
    if not check:
        return Check(state=UNCHECKED, reasons=[], judged=False, why_judged='not checked yet: no check run has reached this page',
                     verdict=None)
    verdict = check.get('verdict')
    return Check(state=check['state'], reasons=counted(check.get('reasons') or []), judged=check['judged'],
                 why_judged=check['why_judged'], verdict=Verdict.model_validate(verdict) if verdict else None,
                 stage2=Stage2.model_validate(check['stage2']) if stages and check.get('stage2') else None,
                 judge=Judge.model_validate(check['judge']) if stages and check.get('judge') else None)


def segments_of(inline: dict | None, fallback: str) -> list[Segment]:
    pairs = (inline or {}).get('segments') or [('text', fallback)]
    return [Segment(kind=kind, content=content) for kind, content in pairs]


# A line break inside a table cell (page/1: "<br> may stand inside a cell"). The core's table parser reads it as a space,
# which its quoted text needs, a table quoted as one line a row. Drawn, the break is the print's line: a journal entry's
# credit account and its amount stand one line below the debit (line 1 on accounting p. 398, 12 Nov). So the view's cells
# are read again by the same parser with each break held by a character no reading writes, a private-use one, and parted
# there; the reading's own parse, its problems and everything served stay as they are.
CELL_BREAK = re.compile(r'<br\s*/?>', re.I)
HELD_BREAK = ''


def broken(segments: list[Segment]) -> list[Segment]:
    """The segments with each held break made a `br` segment, the spaces around a break dropped as the print has none
    there; a break inside any other kind of segment, which a reading has no reason to write, is read as a space."""
    parted: list[Segment] = []
    for segment in segments:
        if HELD_BREAK not in segment.content:
            parted.append(segment)
        elif segment.kind != 'text':
            parted.append(segment.model_copy(update={'content': segment.content.replace(HELD_BREAK, ' ')}))
        else:
            pieces = segment.content.split(HELD_BREAK)
            for at, piece in enumerate(pieces):
                piece = piece.lstrip() if at > 0 else piece
                piece = piece.rstrip() if at < len(pieces) - 1 else piece
                if at > 0:
                    parted.append(Segment(kind='br', content='\n'))
                if piece:
                    parted.append(Segment(kind='text', content=piece))
    return parted


def cells_of(rows: list[list[page_contract.Cell]]) -> list[list[Cell]]:
    return [[Cell(segments=broken(segments_of(cell.inline, cell.text)), header=cell.header, rowspan=cell.rowspan,
                  colspan=cell.colspan) for cell in line] for line in rows]


def table_cells(body: str, rows: list[list[page_contract.Cell]]) -> list[list[Cell]]:
    """A table's cells as the view draws them: the parser's own, with the line breaks a cell holds (`CELL_BREAK`). Where the
    body holds no break, or the second reading of it does not give the same grid, the first stands unchanged."""
    if CELL_BREAK.search(body):
        held, _, _ = page_contract.parse_table(CELL_BREAK.sub(HELD_BREAK, body))
        if [len(line) for line in held] == [len(line) for line in rows]:
            return cells_of(held)
    return cells_of(rows)


# A photo on a page the reader called a chapter opener is chapter art (194.a): the rule from data, no model
CHAPTER_ART = 'a photo on a chapter opener'


def decorative_why(block: page_contract.Block, page_kind: str | None) -> str | None:
    return CHAPTER_ART if page_kind == 'chapter_opener' and block.cls == 'figure' and block.attrs.get('kind') == 'photo' else None


def block_of(block: page_contract.Block, findings: list[Finding], people: list[PersonVerdict] = (),
             page_kind: str | None = None) -> Block:
    vocab = page_contract.VOCAB['classes'].get(block.cls, {})
    fields = {'segments': None, 'latex': None, 'rows': None, 'code': None, 'text': None}
    if block.rows is not None:
        fields['rows'] = table_cells(block.body, block.rows)
    elif block.cls == 'formula':
        fields['latex'] = block.body
    elif block.cls == 'code':
        fields['code'] = block.code if block.code is not None else block.body
    elif block.inline is not None:
        fields['segments'] = segments_of(block.inline, block.body)
    elif block.body:
        fields['text'] = block.body
    return Block(id=block.id, block_class=block.cls, group=vocab.get('group', 'unknown'), content=vocab.get('content', '?'),
                 attrs={name: str(value) for name, value in block.attrs.items()},
                 bbox=list(block.bbox) if block.bbox else None,
                 findings=[finding for finding in findings if finding.block == block.id],
                 people=[person for person in people if person.block == block.id],
                 decorative=decorative_why(block, page_kind), body=block.body, **fields)


def table_correction(correction: str | None) -> list[list[Cell]] | None:
    """A person's correction of a table block as cells (decision 204.a, the operator on finance p. 119: the correction showed as its
    HTML source): read by the core's own table parser, as a reading's table is, so it is drawn as a table and never reaches
    the page as markup. None where it parses to no row or with a problem; the view then shows it as the text it is."""
    if not correction:
        return None
    rows, problems, _ = page_contract.parse_table(correction)
    if not rows or problems:
        return None
    return table_cells(correction, rows)


def with_corrections(blocks: list[Block]) -> list[Block]:
    """A person's correction of a table block given as cells (204.a); any other correction stays text. In place. A table
    the reader marked unreadable has no cells of its own and is still a table: its correction is the one that matters most
    (accounting p. 524, b11, 12 Nov: shown as its HTML source while the rule asked the block for cells). And the correction
    that stands for each block (229.a): the latest given that applies to the reading shown, and not archived by a reset."""
    for block in blocks:
        if block.block_class == 'table':
            for person in block.people:
                if person.correction and person.correction_rows is None:
                    person.correction_rows = table_correction(person.correction)
        person = latest_standing(block.people, lambda one: bool(one.correction))
        if person:
            block.correction = StandingCorrection(text=person.correction, rows=person.correction_rows,
                                                  given_by=person.given_by, given_at=person.given_at,
                                                  by_a_person=person.by_a_person)
    return blocks


def latest_standing(people: list[PersonVerdict], chosen=lambda person: True) -> PersonVerdict | None:
    """The latest person's verdict that applies to the reading shown and was not archived by a reset, among those chosen;
    by its time, then by its place in the list. None where there is none."""
    standing = [(person.given_at or '', at, person) for at, person in enumerate(people)
                if person.applies and not person.archived and chosen(person)]
    return max(standing, key=lambda one: one[:2])[2] if standing else None


# "block b04 (line 26): HTML in prose ..." or "line 86: attributes not parseable: ...", as page_contract writes its errors
ERROR_PLACE = re.compile(r'(?:block (?P<block>\S+) \(line (?P<line>\d+)\)|line (?P<only>\d+)): (?P<message>.*)', re.S)
# the fault's own line in the message, as page/1.4 names it: "LaTeX command outside math on line 28: \HL"
AT_LINE = re.compile(r'\bon line (\d+)\b')


def block_lines(raw: str, line: int) -> list[int]:
    """The first and last line of the block that opens at `line` in the raw text, counted as the validator counts them:
    from its opening fence to its closing `:::` (the core's `page_contract.CLOSER`), or to the line before the next block
    where it was left open. The validator names the line a block opens on, while what it found wrong may stand lines below
    (found 18 Nov: line 26 named, the offending text on line 28), so the raw view marks the whole block."""
    lines = raw.split('\n')
    for at in range(line, len(lines)):  # `line` counts from 1, so lines[line] is the line after the opening fence
        if page_contract.CLOSER.match(lines[at]):
            return [line, at + 1]
        if page_contract.OPENER_IN_BODY.match(lines[at]):
            return [line, at]
    return [line, len(lines)]


def errors_placed(errors: list[str], blocks: list[Block], people: list[PersonVerdict], raw: str = '') -> list[ReadingError]:
    """The validator's errors, each parted into the block and the line it names (228.a), and whether a person has looked: the
    latest verdict that applies to the block, else to the page as a whole, and whether a correction stands for the block.
    An error that names no place is kept whole, its message the error itself. An error on a block carries the block's
    lines in the raw text, so the raw view marks them as a compiler marks an error, and the fault's own line where the
    validator names it (page/1.4)."""
    corrected = {block.id for block in blocks if block.correction}
    whole = latest_standing(people, lambda person: person.block is None)
    placed = []
    for error in errors:
        found = ERROR_PLACE.fullmatch(error)
        block = found['block'] if found and found['block'] != '?' else None
        line = int(found['line'] or found['only']) if found else None
        at_line = AT_LINE.search(found['message'] if found else error)
        on_block = latest_standing(people, lambda person: person.block == block) if block else None
        looked = on_block or whole
        placed.append(ReadingError(said=error, message=found['message'] if found else error, block=block, line=line,
                                   lines=block_lines(raw, line) if found and found['line'] and raw else None,
                                   at_line=int(at_line[1]) if at_line else None,
                                   looked=looked.verdict if looked else None,
                                   looked_by_a_person=looked.by_a_person if looked else None,
                                   looked_at=('block' if on_block else 'page') if looked else None,
                                   corrected=block in corrected))
    return placed


def note_text_of(block: Block) -> str:
    """A footnote's text as one line: its prose's pieces joined, a formula as its LaTeX, else its body as written."""
    if block.segments is not None:
        return ''.join(segment.content for segment in block.segments).strip()
    return (block.text or '').strip()


def with_notes(blocks: list[Block]) -> list[Block]:
    """Each note marker (`fn`) linked to the footnote on the same page whose `marker` is its content (206.a): the reader
    writes "[4]{.fn}" in the prose and the note as a block "{.footnote marker="4"}". Where two notes share a marker the
    first stands; a marker no note carries stays unlinked, shown alone. The blocks are changed in place and returned."""
    notes: dict[str, Block] = {}
    for block in blocks:
        marker = block.attrs.get('marker', '').strip()
        if block.block_class == 'footnote' and marker:
            notes.setdefault(marker, block)
    if not notes:
        return blocks
    for block in blocks:
        pieces = [*(block.segments or []), *(segment for line in block.rows or [] for cell in line for segment in cell.segments)]
        for segment in pieces:
            note = notes.get(segment.content.strip()) if segment.kind == 'fn' else None
            if note is not None:
                segment.note, segment.note_text = note.id, note_text_of(note)
    return blocks


# One lock per PDF: where the export has not cut a PDF's quoted text on this machine, the core cuts it on the first call
# (about a minute for a large book) and keeps it; two pages of the same book asked at once must not both cut it.
_CUTTING: dict[tuple[str, str], threading.Lock] = {}
_CUTTING_GUARD = threading.Lock()


def quoted_text(knowledge_base: KnowledgeBase, file_name: str) -> dict[int, str]:
    """PDF page -> the text the search and the chat quote, by the core's one function for it; nothing of it is cut here."""
    with _CUTTING_GUARD:
        lock = _CUTTING.setdefault((knowledge_base, file_name), threading.Lock())
    with lock:
        return reading_export.quoted_pages(knowledge_base, file_name)


def same_pixels(row: dict, png: bytes) -> bool:
    """Whether a fresh render shows the pixels the reader was sent, where the bytes differ. The same pixels can be written
    as other PNG bytes by another build of zlib: in the Docker container (Linux) every page read under Windows showed
    "image differs from the one read" (18 Nov), its pixels identical. False where the store keeps no copy of the image sent
    (a clone has none), so the view says no more than the bytes can."""
    import io

    from PIL import Image

    try:
        sent = reading_store.open_store(row['knowledge_base']).get_input(row['image_sha256'], '.png')
    except (OSError, KeyError, ValueError):
        return False
    with Image.open(io.BytesIO(sent)) as before, Image.open(io.BytesIO(png)) as now:
        return before.size == now.size and before.mode == now.mode and before.tobytes() == now.tobytes()


@lru_cache(maxsize=16)
def _render(pdf: Path, pdf_page: int, resolution: str, modified: int) -> page_render.PageImage:
    """One page as the reader received it; `modified` makes a changed PDF a new cache entry."""
    with pymupdf.open(pdf) as document:
        return page_render.render(document[pdf_page - 1], resolution)


def licensed_readings() -> 'Readings | None':
    """The licensed knowledge base's export (decision 80.a), git-ignored and on this machine only, so a clone has none.
    This is the one place that reads it, and the one that hands it the licensed catalog (N1.a): never under --public-only."""
    return Readings(LICENSED_EXPORT, catalog=data_paths.LICENSED_CATALOG) if (LICENSED_EXPORT / 'index.json').exists() else None


class CatalogEntry(BaseModel):
    """A licensed work as the local licensed catalog lists it (`data_paths.LICENSED_CATALOG`, the operator's N1.a, 18 Nov):
    git-ignored and on this machine only, read for the licensed knowledge base alone, so no licensed title reaches a public
    view. Its shape follows `corpus/catalog.json`; the free catalog's links and subject have no counterpart here."""

    id: str  # the export's work key for a work it has pages of, else the file's stem
    file: str | None = None
    title: str
    authors: str | None = None
    publisher: str | None = None
    year: int | None = None
    edition: str | None = None  # "3rd", where the copy names one
    format: str | None = None
    shelf: str | None = None
    licence: str | None = None
    notes: str | None = None  # a few words: "stand-in file", "re-typeset copy; printed pages differ"


def catalog_entries(path: Path) -> list[CatalogEntry]:
    """The licensed catalog's entries, each that reads as one; [] where the file is missing or unreadable, so the view
    shows what it showed without it, with no error and no warning (N1.a)."""
    try:
        sources = json.loads(path.read_text(encoding='utf-8')).get('sources') or []
    except (OSError, ValueError, AttributeError):
        return []
    entries = []
    for source in sources if isinstance(sources, list) else []:
        try:
            entries.append(CatalogEntry.model_validate(source))
        except ValueError:  # pydantic's ValidationError is one: an entry that does not read is left out, the rest stand
            continue
    return entries


def knowledge_bases(public_only: bool = False) -> dict[str, 'Readings']:
    """The knowledge bases the views give out, by name. With `public_only` the licensed one is never read, so no licensed
    title, page or count can appear: a recorded review is safe by construction, not by care (decision 81.a)."""
    bases = {'free': Readings()}
    if not public_only:
        licensed = licensed_readings()
        if licensed is not None:
            bases['licensed'] = licensed
    return bases


def issues(bases: dict[str, 'Readings']) -> IssueList:
    """The pages a person should look at, over every work of every knowledge base served, by base, work and page; the
    pages that are not content after the rest (172.a), as their issues are noted, not repaired. A page a person settled
    stays in the list, its `listed_state` `DECIDED` and counted so (211.a), and the view folds it apart from the open
    ones: the list keeps what a person decided on, as a record, beside what still waits for one."""
    listed = sorted(((store, row) for store in bases.values() for row in store.rows()
                     if state_of(row) in LISTED_AS_ISSUE),
                    key=lambda pair: (apart(pair[1]), pair[1]['knowledge_base'], pair[1]['source_id'], pair[1]['pdf_page']))
    return IssueList(
        knowledge_bases=counted([row['knowledge_base'] for _, row in listed]),
        states=counted_states([row for _, row in listed]),
        people=counted_people([row for _, row in listed]),
        reviews=counted_people([row for _, row in listed], by_a_person=False),
        categories=counted_categories([row for _, row in listed]),
        rows=[issue_row(store, row) for store, row in listed])


def issue_row(store: 'Readings', row: dict) -> IssueRow:
    """A page as a list across works shows it: its work by title, its state and reasons, and why a fallback serves it."""
    return IssueRow(knowledge_base=row['knowledge_base'], source_id=row['source_id'], title=store.title(row['source_id']),
                    pdf_page=row['pdf_page'], route=row['route'], check=check_of(row), error_message=row.get('error_message'),
                    from_text_layer=row['route'] in NOT_SERVED_ROUTES, route_level=row.get('route_level'),
                    route_why=route_parts(row['route'])[2], person=person_mark(row), category=row.get('category'),
                    page_kind=row.get('page_kind'), category_said=category_said(row), apart=apart(row),
                    focus=first_finding_block(row), listed_state=listed_state(row))


def block_number(block: str) -> int:
    return int(block[1:]) if block[1:].isdigit() else 1 << 30


def first_finding_block(row: dict) -> str | None:
    """The block a page opens on (186): the first in reading order that one of its standing judgement's findings names."""
    blocks = [finding['block'] for finding in ((row.get('check') or {}).get('verdict') or {}).get('findings') or []
              if finding.get('block')]
    return min(blocks, key=block_number) if blocks else None


def findings_outcome(row: dict, said: str | None) -> str | None:
    """What a page's findings come to, in a few words, where nothing above says it already (the operator, 11 Nov, the head said "a
    person accepted the reading" four times): the sentence above the record says it for a page that is not plainly ok,
    and a person's line for a page a person judged; else whether the reading is served or which fallback (H2.a)."""
    if said is not None or person_mark(row) is not None:
        return None
    return SERVES.get(fallback_of(row), 'the reading is served')


def why_line(row: dict, said: str | None, blocks: 'list[Block]') -> str | None:
    """The head's "Why:" line, said once (the operator, 11 Nov): the route's why where nothing else on the page says it. The
    sentence above is built from the same why (`said_of`), so a page that has one needs no line. A person's why is "a
    person accepted the reading: <their note>": the sentence and the person's line say the first part, and the verdict
    with its note stands beneath its block when it names one or a block has findings, so the line keeps the note alone,
    and only where the reading shows it nowhere."""
    why = route_parts(row['route'])[2]
    if not why:
        return None
    if why.startswith('a person '):
        standing = served_readings.human_standing(row) or {}
        shown = (standing.get('reading_key'), standing.get('block'), standing.get('verdict'), standing.get('given_at'))
        beneath = any((person.reading_key, person.block, person.verdict, person.given_at) == shown
                      for block in blocks for person in block.people)
        return None if beneath else why.partition(': ')[2] or None
    return None if said is not None else why


class Readings:
    """One knowledge base's export; its index is read again whenever the file changes."""

    def __init__(self, export: Path = FREE_EXPORT, root: Path | None = None, catalog: Path | None = None):
        self.export = export
        self.root = root  # what a work's `pdf` path is relative to; None: the repository's layout, the data in _data/
        self.index = export / 'index.json'
        # the licensed catalog, handed in by `licensed_readings` alone (N1.a); None for the free knowledge base, whose
        # catalog the sources view reads itself
        self.catalog = catalog
        self._data: dict = {}
        self._read_at: int | None = None
        self._catalog_at: int | None = None
        self._works_at: tuple[int | None, int | None] | None = None
        self._works: list[dict] = []
        self._entries: dict[str, CatalogEntry] = {}
        self._unread: list[CatalogEntry] = []

    def _index(self) -> dict:
        if not self.index.exists():
            return {}
        modified = self.index.stat().st_mtime_ns
        if modified != self._read_at:
            self._data = json.loads(self.index.read_text(encoding='utf-8'))
            self._read_at = modified
        return self._data

    def rows(self) -> list[dict]:
        return self._index().get('pages', [])

    def works(self) -> list[dict]:
        """The works the export has pages of, each with its id, title and PDF; a licensed work's id and title are its file's
        stem, as on the search server, unless the licensed catalog lists it: then its title is the catalog's (N1.a), matched
        by the export's work key, else by its file. Built again whenever the export or the catalog changes."""
        works = self._index().get('works', [])
        stamp = None
        if self.catalog is not None:
            try:
                stamp = self.catalog.stat().st_mtime_ns
            except OSError:
                stamp = None
        if (self._read_at, stamp) != self._works_at:
            entries = catalog_entries(self.catalog) if stamp is not None else []
            by_id = {entry.id: entry for entry in entries}
            by_file = {entry.file: entry for entry in entries if entry.file}
            self._entries = {work['source_id']: entry for work in works
                             if (entry := by_id.get(work.get('work')) or by_file.get(work.get('file')))}
            self._works = [{**work, 'title': self._entries[work['source_id']].title} if work['source_id'] in self._entries
                           else work for work in works]
            matched = {id(entry) for entry in self._entries.values()}
            self._unread = [entry for entry in entries if id(entry) not in matched]
            self._works_at = (self._read_at, stamp)
        return self._works

    def catalog_entry(self, source_id: str) -> CatalogEntry | None:
        """The licensed catalog's entry of a work, None where there is no catalog or it does not list the work."""
        self.works()
        return self._entries.get(source_id)

    def catalog_entry_of_file(self, file_name: str) -> CatalogEntry | None:
        """The licensed catalog's entry of a file, read or not: how an EPUB the librarian serves finds its title."""
        self.works()
        return next((entry for entry in [*self._entries.values(), *self._unread] if entry.file == file_name), None)

    def unread_entries(self) -> list[CatalogEntry]:
        """The licensed catalog's entries the export has no pages of, in the catalog's order (the operator's O1.a, 18 Nov):
        the EPUBs and the files not read yet. [] without a catalog."""
        self.works()
        return self._unread

    def work(self, source_id: str) -> dict | None:
        return next((work for work in self.works() if work['source_id'] == source_id), None)

    def title(self, source_id: str) -> str:
        work = self.work(source_id)
        return work['title'] if work else source_id

    def rows_of(self, source_id: str) -> list[dict]:
        return sorted((row for row in self.rows() if row['source_id'] == source_id), key=lambda row: row['pdf_page'])

    def row(self, source_id: str, pdf_page: int) -> dict | None:
        return next((row for row in self.rows_of(source_id) if row['pdf_page'] == pdf_page), None)

    def summary(self, source_id: str) -> WorkReadings | None:
        return readings_of(self.rows_of(source_id))

    def pages(self, knowledge_base: KnowledgeBase, source_id: str, title: str) -> WorkPages:
        """A work's pages under the knowledge base its export entry names; only a catalog work that no export lists, one
        not read page by page and so without pages, keeps the one it was asked under."""
        work = self.work(source_id)
        rows = self.rows_of(source_id)
        routes = routes_of(rows)
        return WorkPages(knowledge_base=work['knowledge_base'] if work else knowledge_base, source_id=source_id,
                         title=title, summary=readings_of(rows), routes=routes, route_levels=levels_of(routes),
                         outline=outline_of(work, rows),
                         outside_outline=readings_of([row for row in rows if row.get('units') == []]),
                         pages=[PageRow(pdf_page=row['pdf_page'], printed_label=row.get('printed_label'),
                                        units=row.get('units'), route=row['route'],
                                        check=check_of(row), class_when_collected=row['class_when_collected'],
                                        class_now=row['class_now'], attempt=row['attempt'], cost_usd=reading_cost(row),
                                        error_message=row.get('error_message'),
                                        from_text_layer=row['route'] in NOT_SERVED_ROUTES,
                                        route_level=row.get('route_level'), route_why=route_parts(row['route'])[2],
                                        person=person_mark(row), category=row.get('category'),
                                        page_kind=row.get('page_kind'), category_said=category_said(row),
                                        listed_state=listed_state(row))
                                for row in rows])

    def image(self, source_id: str, pdf_page: int) -> tuple[PageImage, bytes | None]:
        row = self.row(source_id, pdf_page)
        if row is None:
            return PageImage(available=False, why_not='no reading of this page', width=None, height=None,
                             same_as_read=None), None
        work = self.work(source_id)
        if work is None:
            return PageImage(available=False, why_not='the export names no PDF for this work', width=None, height=None,
                             same_as_read=None), None
        pdf = self.root / work['pdf'] if self.root else data_paths.locate(work['pdf'])  # a free PDF in _data/, a licensed one in _sources/
        if not pdf.exists():
            # a free PDF can be fetched again; a licensed one exists only on the machine it was bought for
            why_not = (f"{work['pdf']} is not downloaded: run python -m backend.ingestion.acquire"
                       if row['knowledge_base'] == 'free' else f"{work['pdf']} is not on this machine")
            return PageImage(available=False, why_not=why_not, width=None, height=None, same_as_read=None), None
        try:
            image = _render(pdf, pdf_page, row['resolution'], pdf.stat().st_mtime_ns)
        except (page_render.RenderSizeError, ValueError, IndexError) as error:
            return PageImage(available=False, why_not=f'the page could not be rendered: {error}', width=None, height=None,
                             same_as_read=None), None
        same = hashlib.sha256(image.png).hexdigest() == row['image_sha256'] or same_pixels(row, image.png)
        return PageImage(available=True, why_not=None, width=image.width, height=image.height, same_as_read=same), image.png

    def quoted(self, source_id: str, pdf_page: int) -> QuotedText | None:
        row = self.row(source_id, pdf_page)
        if row is None:
            return None
        return QuotedText(knowledge_base=row['knowledge_base'], source_id=source_id, pdf_page=pdf_page,
                          text=quoted_text(row['knowledge_base'], row['file']).get(pdf_page))

    def page(self, source_id: str, pdf_page: int, title: str) -> PageDetail | None:
        rows = self.rows_of(source_id)
        position = next((at for at, row in enumerate(rows) if row['pdf_page'] == pdf_page), None)
        if position is None:
            return None
        row = rows[position]
        check = check_of(row, stages=True)
        findings = check.verdict.findings if check.verdict else []
        reset = row.get('reset') or None
        # a verdict given before the page's latest reset is archived (191.a): it carries that reset's time
        people = [PersonVerdict.model_validate({**person, 'archived_at': (reset or {}).get('given_at') if person.get('archived') else None,
                                                'assessed': assessed_judge(person, row.get('attempts') or [])})
                  for person in row.get('human') or []]
        raw = reading = None
        errors: list[str] = []
        placed: set[str] = set()
        state = integrity.page_state(self.export, row)
        if state in ('whole', 'tampered'):  # a tampered file is shown as it now reads: the mark says it is not what was checked
            raw = (self.export / row['text_file']).read_text(encoding='utf-8')
            parsed = page_contract.parse(raw, row['form'])
            blocks = with_corrections(with_notes([block_of(block, findings, people, row.get('page_kind')) for block in parsed.blocks]))
            # a finding whose block no verdict names takes the latest page-level verdict that applies, with its assessment
            # of the judge (the operator on finance p. 408): a person who rated every finding of the page rated this one too
            whole = [person for person in people if person.applies and not person.archived and person.block is None]
            for block in blocks:
                if whole and block.findings and not any(person.applies for person in block.people):
                    block.people = [*block.people, whole[-1]]
            placed = {block.id for block in blocks}
            errors = parsed.errors
            reading = Reading(front={name: str(value) for name, value in parsed.front.items()}, blocks=blocks,
                              errors=parsed.errors, warnings=parsed.warnings,
                              error_places=errors_placed(parsed.errors, blocks, people, raw))
        chosen = row.get('chosen')
        source, reader, why = route_parts(row['route'])
        # the blocks with findings in reading order, a decorative one after the rest (194.a), so the page opens on content
        named = sorted((block for block in (reading.blocks if reading else []) if block.findings),
                       key=lambda block: block.decorative is not None)
        said = said_of(row, errors)
        return PageDetail(
            attempts=attempts_of(row), said=said, person=person_mark(row), category=row.get('category'),
            page_kind=row.get('page_kind'), category_said=category_said(row),
            route_level=row.get('route_level'), route_source=source, route_reader=reader.split(', ') if reader else None,
            route_why=why, why_line=why_line(row, said, reading.blocks if reading else []),
            focus=named[0].id if named else None, protected=row.get('protected'), listed_state=listed_state(row),
            reset=PageReset.model_validate(reset) if reset else None,
            findings_at=[FindingsAt(block=block.id, said='void by code' if all(finding.void for finding in block.findings)
                                    else 'stands', severity=gravest(block.findings)) for block in named] or None,
            findings_outcome=findings_outcome(row, said) if named or findings else None,
            chosen=Chosen(why=chosen['why'], run_id=str(chosen['run_id']), chosen_at=chosen['chosen_at']) if chosen else None,
            knowledge_base=row['knowledge_base'], source_id=source_id, title=title, pdf_page=pdf_page,
            printed_label=row.get('printed_label'),
            previous_page=rows[position - 1]['pdf_page'] if position > 0 else None,
            next_page=rows[position + 1]['pdf_page'] if position + 1 < len(rows) else None,
            route=row['route'], from_text_layer=row['route'] in NOT_SERVED_ROUTES, check=check, reading=reading, raw=raw,
            integrity=state, image=self.image(source_id, pdf_page)[0],
            page_findings=[finding for finding in findings if finding.block not in placed], human=people,
            trace=Trace(**{**{name: row.get(name) for name in Trace.model_fields}, 'cost_usd': reading_cost(row)}))

    def stored_reading(self, row: dict, reading_key: str) -> tuple[str | None, str]:
        """A reading's text and form: the export's for the reading the page shows, else the core's reading store on this
        machine (git-ignored, so a clone has none: None). Read only, by its key, which must be one of the page's own."""
        if reading_key == row['reading_key'] and integrity.page_state(self.export, row) in ('whole', 'tampered'):
            return (self.export / row['text_file']).read_text(encoding='utf-8'), row['form']
        folder = reading_store.ROOTS[row['knowledge_base']] / 'readings' / reading_key[:2]
        text, record = folder / f'{reading_key}.md', folder / f'{reading_key}.json'
        if not READING_KEY.match(reading_key) or not text.is_file():
            return None, row['form']
        form = json.loads(record.read_text(encoding='utf-8')).get('form', row['form']) if record.is_file() else row['form']
        return text.read_text(encoding='utf-8'), form

    def recall(self, source_id: str, pdf_page: int, recall: str) -> Recalled | None:
        """One judgement of the page shown as it judged (181.a): None where the page has no judgement by that id."""
        row = self.row(source_id, pdf_page)
        reading_key, _, rest = recall.partition(':')
        version, _, again = rest.rpartition(':')
        attempts = (row or {}).get('attempts') or []
        number, attempt = next(((at + 1, one) for at, one in enumerate(attempts) if one['reading_key'] == reading_key),
                               (None, None))
        found = [judgement for judgement in (attempt or {}).get('judgements') or []
                 if recall_id(reading_key, judgement) == f'{reading_key}:{version}:{again}']
        if row is None or attempt is None or not found:
            return None
        judgement = found[-1]
        findings = [Finding.model_validate(finding) for finding in judgement.get('findings') or []]
        # a person's verdicts on that reading apply to it, whichever reading the page shows now
        people = [PersonVerdict.model_validate({**person, 'applies': True, 'assessed': assessed_judge(person, attempts)})
                  for person in row.get('human') or [] if person.get('reading_key') == reading_key]
        text, form = self.stored_reading(row, reading_key)
        reading, size, placed = None, row.get('image_size'), set()
        if text is not None:
            parsed = page_contract.parse(text, form)
            blocks = with_corrections(with_notes([block_of(block, findings, people, row.get('page_kind')) for block in parsed.blocks]))
            placed = {block.id for block in blocks}
            reading = Reading(front={name: str(value) for name, value in parsed.front.items()}, blocks=blocks,
                              errors=parsed.errors, warnings=parsed.warnings,
                              error_places=errors_placed(parsed.errors, blocks, people, text))
            width, _, height = str(parsed.front.get('image_size', '')).partition('x')
            if width.isdigit() and height.isdigit():
                size = [int(width), int(height)]
        return Recalled(recall=recall_id(reading_key, judgement), reading_key=reading_key, reading_number=number,
                        version=judgement.get('version'), version_state=judgement.get('version_state'),
                        again=judgement.get('again') or 0, counts=judgement.get('counts', True),
                        said=recall_said(judgement, number, attempt), reading=reading, raw=text,
                        why_not=None if text is not None else
                        f"reading {number}'s text is not on this machine: only the reading a page shows is exported",
                        page_findings=[finding for finding in findings if finding.block not in placed], image_size=size)
