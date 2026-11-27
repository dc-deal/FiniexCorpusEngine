"""A page's readings and verdicts in one form (issue #18, the operator's design, 27 Nov 2026): three tabs, Readings, Lab and
Verdicts, each with its count. The pattern is always the same: one reading, then any number of verdicts on it, a judge's
or a person's; a reading in the pipeline or in the Lab, the difference one flag (`prototype`, a test reading among them).

- **Readings and Lab, one row per reading:** time · model · cost · version (linked to its prompt) · result · show; a row
  folds open to its verdicts in the same columns: time · model · cost · version · verdict · show, a person's a row too.
- **Verdicts: every verdict on the page, a judge's and a person's, in time order:** standing · time · verdict · reason ·
  about · the judgement it answered · person or machine. The standing one is marked, the others are history.

Every word and count a row shows is said here, so the view computes nothing; the keys and a reading's own bookkeeping (its
reading key, the reader's attempt, its cell, a judgement's key) stand in a row's hover, never in a column. Built from the
page's own parsed readings and verdicts (`readings.attempts_of`, `PersonVerdict`), read by their fields alone, so this
module needs nothing of `readings` and `readings` can name its model.
"""

from typing import Any, Literal

from pydantic import BaseModel


class HoverRow(BaseModel):
    label: str
    value: str


class FormRule(BaseModel):
    """A rule a judge proposed for the reader (202.a), read-only beneath its verdict, as `ReaderRuleList` shows it."""

    kind: str
    block: str | None = None
    rule: str | None = None
    block_class: str | None = None
    attribute: str | None = None
    value: str | None = None


Kind = Literal['reading', 'judge', 'person', 'review']


class FormVerdict(BaseModel):
    """One verdict on a reading, in the reading's columns: time · model · cost · version · verdict · show."""

    kind: Literal['judge', 'person']
    # what the row is, in front of it, a word and a glyph (the operator, 27 Nov: indentation alone was hard to tell apart):
    # "judge", "person", or "review" for one given by a session on the operator's delegation
    kind_said: Kind
    time: str | None = None
    model: str  # the judge's model; for a person's, "a person" or "an automated review"
    cost_usd: float | None = None
    version: str | None = None  # the judge's version, linked to its prompt; None for a person's
    version_said: str | None = None  # "counts", "prototype", "asked again", "not counted"; for a person's "verdict"
    verdict_said: str  # "ok", "issue · 2 findings: 1 major, 1 minor", "accept · false alarm"
    state: Literal['ok', 'issue', 'note']  # its look: a verdict that passes, one that finds fault, a note
    standing: bool = False
    recall: str | None = None  # a judge's: the page view's `?judgement=`, to show it on the page
    # where showing it would change nothing on the page, why, in words: its "show" stays in place, greyed (decision 25)
    show_why_not: str | None = None
    block: str | None = None  # a person's on a block: the block it names
    rules: list[FormRule] = []  # a judge's proposed rules for the reader (judge/4), beneath its row
    hover: list[HoverRow] = []


class FormReading(BaseModel):
    """One reading of the page, in the Readings or the Lab tab: time · model · cost · version · result · show."""

    kind_said: Kind = 'reading'
    key: str  # its reading key: the row's name and its hover, never a column
    time: str
    model: str
    cost_usd: float | None = None
    version: str | None = None  # the reader's version ("page/1", "paddleocr-vl/ocr"), linked to its prompt
    result_state: Literal['ok', 'none', 'issue']
    result_said: str  # "ok", "no judge", "3 issues", "malformed"
    shown: bool = False  # the reading the page shows and serves
    test_reading: bool = False  # a local model's test reading (#17), the Lab's
    promoted_said: str | None = None  # "promoted from the Lab: better", where a person made it the page's reading (#18)
    promotable: bool = False  # a page/1 Lab reading nobody promoted: the one kind the core promotes
    recall: str | None = None  # its own "show": the reading alone on the page, by its key; None for the reading shown
    verdicts: list[FormVerdict] = []
    hover: list[HoverRow] = []


class AnsweredJudgement(BaseModel):
    """The judgement a person's verdict answered (#17), by its version, model and date; `derived` where the core assigned
    it by time rather than recorded it."""

    version: str | None = None
    model: str | None = None
    stored_at: str | None = None
    derived: bool = False


class VerdictRow(BaseModel):
    """One verdict on the page, in the Verdicts tab: standing · time · verdict · reason · about · judge · person or machine."""

    kind: Literal['judge', 'person']
    kind_said: Kind
    standing: bool
    standing_said: Literal['standing', 'history']
    time: str | None = None
    verdict: str  # the short word: "ok", "bad", "accept", "reject", "note"
    state: Literal['ok', 'issue', 'note']
    reason: str | None = None  # the short label: a person's reason ("false alarm"), a judge's findings ("2 issues")
    about: str  # "the page", or the block it names
    in_lab: bool = False  # on a reading of the Lab
    answered: AnsweredJudgement | None = None
    who: Literal['person', 'review', 'machine']
    who_said: str  # "a person", "an automated review", "judge/1 · claude-sonnet-5-5"
    hover: list[HoverRow] = []


class PageForm(BaseModel):
    # the judgement the page shows, the served reading's standing one, by its key: what a person's verdict answers (#17)
    shown_judgement: str | None = None
    readings_count: int
    lab_count: int
    verdicts_count: int
    readings: list[FormReading]
    lab: list[FormReading]
    verdicts: list[VerdictRow]


def counted(count: int, word: str, words: str | None = None) -> str:
    return f"{count:,} {word if count == 1 else words or word + 's'}"


def standing_findings(judgement: Any) -> list[Any]:
    return [finding for finding in judgement.findings or [] if not finding.void]


def findings_said(judgement: Any) -> str | None:
    """A judgement's findings in a few words: "1 finding: minor", "2 findings: 1 major, 1 minor", "1 finding: void"."""
    every = judgement.findings or []
    if not every:
        return None
    standing = standing_findings(judgement)
    severities: dict[str, int] = {}
    for finding in standing:
        severities[finding.severity or 'unrated'] = severities.get(finding.severity or 'unrated', 0) + 1
    void = len(every) - len(standing)
    parts = [(severity if len(every) == 1 else f'{count} {severity}') for severity, count in severities.items()]
    if void:
        parts.append('void' if len(every) == 1 else f'{void} void')
    return f"{counted(len(every), 'finding')}: {', '.join(parts)}"


def judge_role(judgement: Any) -> str:
    """A judgement's place in a word, from the core's own fields: the one that counts, a judge asked again, a prototype's, or
    one that does not count (the core sets `counts` false on every judgement of a Lab reading nobody promoted)."""
    if judgement.counts:
        return 'counts'
    if judgement.again:
        return 'asked again'
    return 'prototype' if judgement.version_state == 'prototype' else 'not counted'


def judge_state(judgement: Any) -> Literal['ok', 'issue']:
    """A judgement's look by the outcome that counts: an ok with minor findings is an ok, its findings said beside it."""
    return 'ok' if judgement.outcome == 'ok' else 'issue'


def agent_prompt_said(prompt: Any) -> str | None:
    """A session's agent prompt in a few words: its version, the start of its hash, and how the core tied it where it did."""
    if prompt is None:
        return None
    derived = prompt.derived if isinstance(prompt.derived, str) else ('tied by its transcript' if prompt.derived else None)
    return ' · '.join(part for part in (prompt.version, prompt.sha256[:12] if prompt.sha256 else None, derived) if part) or None


def judge_hover(judgement: Any) -> list[HoverRow]:
    rows = [('judgement key', judgement.judgement_key), ('version state', judgement.version_state),
            ('mode', judgement.mode), ('asked again', str(judgement.again) if judgement.again else None),
            ('outcome', f'{judgement.verdict} → {judgement.outcome}' if judgement.verdict else judgement.outcome),
            ("the judge's own", judgement.judge_outcome if judgement.judge_outcome and judgement.judge_outcome != judgement.outcome
             else None),
            ('findings', findings_said(judgement)),
            ('agent prompt', agent_prompt_said(judgement.agent_prompt))]
    return [HoverRow(label=label, value=value) for label, value in rows if value]


NOTHING_TO_SHOW = 'no difference: this judgement found nothing; use show on its reading'


def judge_verdict(judgement: Any) -> FormVerdict:
    """A judge's verdict as its row says it; its "show" is active only where its findings change what the page shows
    (decision 25, the operator: a judgement that found nothing shows its reading alone, which the reading's own row shows).
    A void finding counts: the recall draws it beneath its block, receding (178.a)."""
    said = findings_said(judgement)
    return FormVerdict(kind='judge', kind_said='judge', time=judgement.stored_at, model=judgement.model or 'a judge', cost_usd=judgement.cost_usd,
                       version=judgement.version, version_said=judge_role(judgement),
                       verdict_said=' · '.join(part for part in (judgement.verdict or judgement.outcome or 'judged', said) if part),
                       state=judge_state(judgement), standing=bool(judgement.standing), recall=judgement.recall,
                       show_why_not=None if judgement.findings else NOTHING_TO_SHOW,
                       rules=[FormRule(kind=rule.kind, block=rule.block, rule=rule.rule, block_class=rule.block_class,
                                       attribute=rule.attribute, value=rule.value) for rule in judgement.reader_rules or []],
                       hover=judge_hover(judgement))


def who_of(person: Any) -> tuple[Literal['person', 'review'], str]:
    return ('person', 'a person') if person.by_a_person else ('review', 'an automated review')


def person_state(person: Any) -> Literal['ok', 'issue', 'note']:
    return {'accept': 'ok', 'reject': 'issue'}.get(person.verdict, 'note')


def person_reason(person: Any) -> str | None:
    return person.reason_short or person.reason


def person_hover(person: Any) -> list[HoverRow]:
    answered = person.answers
    rows = [('given by', person.given_by), ('reason', person.reason_text),
            ('judge assessment', ' — '.join(part for part in (person.judge_assessment_short, person.judge_assessment_text) if part)
             or None),
            ('answered', ('judgement ' + (answered.judgement_key or '')
                          + (' (assigned by time, not recorded)' if person.answers_derived else '')).strip() if answered else None),
            ('note', person.note), ('applies', None if person.applies else 'not to the reading shown'),
            ('archived', 'given before the page was reset' if person.archived else None)]
    return [HoverRow(label=label, value=value) for label, value in rows if value]


def person_verdict(person: Any) -> FormVerdict:
    who, said = who_of(person)
    reason = person_reason(person)
    return FormVerdict(kind='person', kind_said=who, time=person.given_at, model=said, version_said='verdict',
                       verdict_said=' · '.join(part for part in (person.verdict, reason) if part), state=person_state(person),
                       standing=bool(person.standing), block=person.block, hover=person_hover(person))


def result_of(attempt: Any, prototype: bool) -> tuple[Literal['ok', 'none', 'issue'], str]:
    """What the reading came to, in a word: its class where its format failed, "no judge" where none judged it, else the
    standing judgement's (on a Lab reading the latest one's): "ok", or how many of its findings stand."""
    if attempt.class_now and attempt.class_now != 'ok':
        return 'issue', attempt.class_now
    judgements = list(attempt.judgements or [])
    if not judgements:
        return 'none', 'no judge'
    standing = [judgement for judgement in judgements if judgement.standing]
    counting = [judgement for judgement in judgements if judgement.counts]
    latest = sorted(standing or counting or (judgements if prototype else []), key=lambda one: one.stored_at or '')
    if not latest:
        return 'none', 'no judge'
    judgement = latest[-1]
    issues = len(standing_findings(judgement))
    if judgement.outcome == 'ok':  # by the outcome that counts; minor findings under an ok are said beside it
        return 'ok', 'ok' + (f" · {counted(issues, 'finding')}" if issues else '')
    return 'issue', counted(issues, 'issue') if issues else (judgement.outcome or judgement.verdict or 'judged')


def reading_hover(attempt: Any, chosen: Any = None) -> list[HoverRow]:
    rows = [('reading key', attempt.reading_key), ("the reader's attempt", str(attempt.attempt)), ('cell', attempt.cell),
            ('purpose', attempt.purpose), ('mode', attempt.mode), ('class', attempt.class_now),
            ('re-read of', attempt.retry_of),
            ('deviation', attempt.deviation), ('why', ' · '.join(attempt.check.reasons) if attempt.check and attempt.check.reasons else None),
            ('format check', ' · '.join(attempt.format_errors) if attempt.format_errors else None),
            ('agent prompt', agent_prompt_said(getattr(attempt, 'agent_prompt', None))),
            ('chosen', f'by run {chosen.run_id}: {chosen.why}' if chosen is not None and attempt.shown else None)]
    return [HoverRow(label=label, value=value) for label, value in rows if value]


def promoted_said(attempt: Any) -> str | None:
    promoted = getattr(attempt, 'promoted', None)
    if promoted is None:
        return None
    return 'promoted from the Lab' + (f': {promoted.reason_short or promoted.reason}' if promoted.reason_short or promoted.reason else '')


def reading_row(attempt: Any, people: list[Any], chosen: Any = None) -> FormReading:
    prototype = bool(attempt.prototype)
    state, said = result_of(attempt, prototype)
    verdicts = [judge_verdict(judgement) for judgement in attempt.judgements or []]
    verdicts += [person_verdict(person) for person in people if person.reading_key == attempt.reading_key]
    verdicts.sort(key=lambda one: one.time or '')
    return FormReading(key=attempt.reading_key, time=attempt.stored_at, model=attempt.model, cost_usd=attempt.cost_usd,
                       version=attempt.reader_version, result_state=state, result_said=said, shown=bool(attempt.shown),
                       test_reading=bool(getattr(attempt, 'test_reading', False)),
                       promoted_said=promoted_said(attempt),
                       promotable=prototype and attempt.reader_version == 'page/1' and not getattr(attempt, 'promoted', None),
                       recall=None if attempt.shown else attempt.reading_key,
                       verdicts=verdicts,
                       hover=reading_hover(attempt, chosen))


def verdict_rows(attempts: list[Any], people: list[Any]) -> list[VerdictRow]:
    rows: list[VerdictRow] = []
    for attempt in attempts:
        for judgement in attempt.judgements or []:
            said = findings_said(judgement)
            issues = len(standing_findings(judgement))
            rows.append(VerdictRow(kind='judge', kind_said='judge', standing=bool(judgement.standing),
                                   standing_said='standing' if judgement.standing else 'history', time=judgement.stored_at,
                                   verdict=judgement.verdict or judgement.outcome or 'judged', state=judge_state(judgement),
                                   reason=counted(issues, 'finding') if issues else None, about='the page',
                                   in_lab=bool(attempt.prototype), who='machine',
                                   who_said=' · '.join(part for part in (judgement.version, judgement.model) if part) or 'a judge',
                                   hover=[HoverRow(label='reading key', value=attempt.reading_key), *judge_hover(judgement),
                                          *([HoverRow(label='all findings', value=said)] if said else [])]))
    in_lab = {attempt.reading_key for attempt in attempts if attempt.prototype}
    for person in people:
        who, said = who_of(person)
        answered = person.answers
        rows.append(VerdictRow(kind='person', kind_said=who, standing=bool(person.standing),
                               standing_said='standing' if person.standing else 'history', time=person.given_at,
                               verdict=person.verdict, state=person_state(person), reason=person_reason(person),
                               about=person.block or 'the page', in_lab=person.reading_key in in_lab,
                               answered=AnsweredJudgement(version=answered.version, model=answered.model,
                                                          stored_at=answered.stored_at, derived=bool(person.answers_derived))
                               if answered else None,
                               who=who, who_said=said, hover=person_hover(person)))
    rows.sort(key=lambda one: one.time or '')
    return rows


def form_of(attempts: list[Any] | None, people: list[Any], chosen: Any = None) -> PageForm | None:
    """A read page's form: its pipeline readings (the one shown first, the earlier ones newest first), the Lab's readings
    (newest first) and every verdict in time order; None for a page no reader has read."""
    if attempts is None:
        return None
    pipeline = [attempt for attempt in attempts if not attempt.prototype or getattr(attempt, 'promoted', None)]
    pipeline = [*[attempt for attempt in pipeline if attempt.shown], *reversed([attempt for attempt in pipeline if not attempt.shown])]
    lab = sorted((attempt for attempt in attempts if attempt.prototype and not getattr(attempt, 'promoted', None)),
                 key=lambda one: one.stored_at or '', reverse=True)
    readings = [reading_row(attempt, people, chosen) for attempt in pipeline]
    tried = [reading_row(attempt, people) for attempt in lab]
    verdicts = verdict_rows(attempts, people)
    served = next((attempt for attempt in attempts if attempt.shown), None)
    standing = [judgement for judgement in (served.judgements or [] if served else []) if judgement.standing]
    return PageForm(shown_judgement=standing[-1].judgement_key if standing else None,
                    readings_count=len(readings), lab_count=len(tried), verdicts_count=len(verdicts), readings=readings,
                    lab=tried, verdicts=verdicts)
