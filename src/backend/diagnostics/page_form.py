"""A page's readings and verdicts in one form (issue #18, the operator's design, 27 Nov 2026): three tabs, Readings, Lab and
Verdicts, each with its count. The pattern is always the same: one reading, then any number of verdicts on it, a judge's
or a person's; a reading in the pipeline or in the Lab, the difference one flag (`prototype`, a test reading among them).

- **Readings and Lab, one row per reading:** time · model · cost · version (linked to its prompt) · result · show; a row
  folds open to its verdicts in the same columns: time · model · cost · version · verdict · show, a person's a row too,
  newest first (31.a). Readings holds the judgements that count and the person's verdicts; what was tried beside them, a
  prototype's judgement or a judge asked again, stands in the Lab beneath the same reading's own row, beside the test
  readings (37.a), and the Lab's count counts those trials.
- **A judge's word is the result that counts** (32.a): "ok" where code struck the findings that made the judge say "bad",
  its own word beside it, struck (`overruled`); a finding code struck is said "struck by code", never "void".
- **Verdicts: the verdicts as shown** (decision 26, the operator: earlier ones hidden, since "a whole list can come together
  when real people judge and type in every verdict bit by bit"): only those that apply now to the reading the analysis
  shows, the served reading's, or after a recall the recalled reading's (`Recalled.verdicts`): its standing judgement (its
  latest counting one; a Lab reading's latest, not counted) and the person's verdicts on it not archived by a reset, in time
  order: standing · time · verdict · reason · about · the judgement it answered · person or machine, newest first. A
  person's verdict a later one on the same block replaced is left out (34.a), as it is in focus. A recalled trial has no
  verdicts at all (38.a). A recalled pipeline judgement or reading shows the verdicts as then (29.d): at the moment it was
  judged, or for a reading the moment the next pipeline reading replaced it, nothing later. The rest stays a click away.

Every word and count a row shows is said here, so the view computes nothing; the keys and a reading's own bookkeeping (its
reading key, the reader's attempt, its cell, a judgement's key) stand in a row's hover, never in a column. Built from the
page's own parsed readings and verdicts (`readings.attempts_of`, `PersonVerdict`), read by their fields alone, so this
module needs nothing of `readings` and `readings` can name its model.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel


class HoverRow(BaseModel):
    label: str
    value: str
    at: str | None = None  # a time the card says in a person's words (its ISO 8601 stamp, as every file keeps it)


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
    version_said: str | None = None  # "counts", "prototype", "asked again", "not counted"; a person's "answers judge/1"
    verdict_said: str  # "ok · 1 finding struck by code", "bad · 2 findings: 1 major, 1 minor", "accept · false alarm"
    # the judge's own word where it is not the result that counts, code having struck its findings (32.a): shown struck
    overruled: str | None = None
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
    # its mark, in the head's word (41.a): "served", where "shown" read wrong while another reading or a judge is recalled
    served_said: str | None = None
    test_reading: bool = False  # a local model's test reading (#17), the Lab's
    promoted_said: str | None = None  # "promoted from the Lab: better", where a person made it the page's reading (#18)
    promotable: bool = False  # a page/1 Lab reading nobody promoted: the one kind the core promotes
    recall: str | None = None  # its own "show": the reading alone on the page, by its key; None for the reading shown
    # where a judge beneath it in the same tab shows the same reading with its findings (42.a), that way in, in words: its own
    # show then stays in place, greyed, so a reading has exactly one active way in
    show_why_not: str | None = None
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
    """One verdict as shown, in the Verdicts tab: standing · time · verdict · reason · about · judge · person or machine."""

    kind: Literal['judge', 'person']
    kind_said: Kind
    standing: bool
    # "standing"; in focus (29.d) "recalled" for the judgement recalled, "counted then" for the one that counted at that moment
    standing_said: Literal['standing', 'recalled', 'counted then']
    recalled: bool = False  # the judgement the page shows recalled: marked ↺ and framed
    time: str | None = None
    verdict: str  # the short word, a judge's the result that counts: "ok", "bad", "accept", "reject", "note"
    overruled: str | None = None  # the judge's own word where code struck its findings (32.a): shown struck
    state: Literal['ok', 'issue', 'note']
    # the short label (33.a): a person's reason ("false alarm"), a judge's finding ("wrong word, struck by code",
    # "invented, minor") or findings ("2 findings: 1 major, 1 struck by code")
    reason: str | None = None
    about: str  # the blocks a judge's findings name ("b09, b12") or a person's verdict names; "the page" where none
    judge_said: str = '—'  # a person's: the judge it answers, in short ("judge/1"); "—" for a judge's own row
    recall: str | None = None  # a judge's: its `?judgement=`, so the row the page shows can be framed as such (27.a)
    answered: AnsweredJudgement | None = None
    who: Literal['person', 'review', 'machine']
    who_said: str  # "a person", "an automated review", "judge/1 · claude-sonnet-5-5"
    hover: list[HoverRow] = []


class ShownVerdicts(BaseModel):
    """The Verdicts tab's rows (decision 26): the verdicts that apply to the reading the analysis shows, what that reading
    is said in a caption above them, and their count, the tab's; for a recalled trial none, and why (38.a)."""

    # "as shown: the verdicts on the served reading"; in focus "as then: the verdicts on reading 2 on", `said_at` its moment
    said: str
    said_at: str | None = None
    recalled: bool = False  # on a recalled reading: the tab is framed as the analysis is
    count: int | None  # None where no verdict applies (a trial): the tab says "–", greyed
    rows: list[VerdictRow]
    why_not: str | None = None  # why no verdict applies, in the tab's card


class PageForm(BaseModel):
    # the judgement the page shows, the served reading's standing one, by its key: what a person's verdict answers (#17)
    shown_judgement: str | None = None
    readings_count: int
    lab_count: int
    readings: list[FormReading]
    lab: list[FormReading]
    verdicts: ShownVerdicts  # in the standing view: the served reading's


def counted(count: int, word: str, words: str | None = None) -> str:
    return f"{count:,} {word if count == 1 else words or word + 's'}"


def standing_findings(judgement: Any) -> list[Any]:
    return [finding for finding in judgement.findings or [] if not finding.void]


STRUCK = 'struck by code'  # a finding the core voided as naming no difference (146.a), in the view's words (32.a)


def findings_said(judgement: Any) -> str | None:
    """A judgement's findings in a few words: "1 finding: minor", "2 findings: 1 major, 1 minor", "1 finding struck by
    code", "2 findings: 1 major, 1 struck by code"."""
    every = judgement.findings or []
    if not every:
        return None
    standing = standing_findings(judgement)
    if len(every) == 1 and not standing:
        return f'1 finding {STRUCK}'
    severities: dict[str, int] = {}
    for finding in standing:
        severities[finding.severity or 'unrated'] = severities.get(finding.severity or 'unrated', 0) + 1
    struck = len(every) - len(standing)
    parts = [(severity if len(every) == 1 else f'{count} {severity}') for severity, count in severities.items()]
    if struck:
        parts.append(f'{struck} {STRUCK}')
    return f"{counted(len(every), 'finding')}: {', '.join(parts)}"


def finding_reason(judgement: Any) -> str | None:
    """A judge's findings as the Verdicts tab's reason (33.a): one by its kind and its severity, or as struck by code
    ("wrong word, struck by code", "invented, minor"); several as `findings_said` says them; None where it found nothing."""
    every = judgement.findings or []
    if len(every) != 1:
        return findings_said(judgement)
    finding = every[0]
    kind = (finding.kind or 'a finding').replace('_', ' ')
    return f'{kind}, {STRUCK if finding.void else finding.severity or "unrated"}'


def finding_blocks(judgement: Any) -> str:
    """What a judge's findings are about (33.a): the blocks they name ("b09, b12"), the page where one names none;
    "the page" where it found nothing."""
    every = judgement.findings or []
    blocks = sorted({finding.block for finding in every if finding.block})
    if any(not finding.block for finding in every) or not blocks:
        blocks.append('the page')
    return ', '.join(blocks)


def judge_word(judgement: Any) -> tuple[str, str | None]:
    """A judgement's word, the result that counts (32.a): "ok" where its outcome is, else its own verdict; and its own
    word beside it where that differs, code having struck the findings it rested on."""
    own = judgement.verdict or judgement.outcome or 'judged'
    word = 'ok' if judgement.outcome == 'ok' else own
    return word, own if own != word else None


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
    word, overruled = judge_word(judgement)
    return FormVerdict(kind='judge', kind_said='judge', time=judgement.stored_at, model=judgement.model or 'a judge', cost_usd=judgement.cost_usd,
                       version=judgement.version, version_said=judge_role(judgement),
                       verdict_said=' · '.join(part for part in (word, said) if part), overruled=overruled,
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
    """A person's verdict under the pointer: who gave it and why, and the judge it answers by its model and its moment,
    "assigned by time" where the core tied it so rather than recorded it (36.a)."""
    answered = person.answers
    rows = [HoverRow(label=label, value=value) for label, value in [
        ('given by', person.given_by), ('reason', person.reason_text),
        ('judge assessment', ' — '.join(part for part in (person.judge_assessment_short, person.judge_assessment_text) if part)
         or None),
        ('answers', ' · '.join(part for part in (answered.version, answered.model) if part) or None if answered else None)] if value]
    if answered and answered.stored_at:
        rows.append(HoverRow(label='judged', value=answered.stored_at, at=answered.stored_at))
    rows += [HoverRow(label=label, value=value) for label, value in [
        ('assigned', 'by time, not recorded' if answered and person.answers_derived else None),
        ('judgement key', answered.judgement_key if answered else None),
        ('note', person.note), ('applies', None if person.applies else 'not to the reading shown'),
        ('archived', 'given before the page was reset' if person.archived else None)] if value]
    return rows


def answers_said(person: Any) -> str | None:
    """The judge a person's verdict answers, in short: "judge/1"; None where it answers none."""
    return person.answers.version if person.answers and person.answers.version else None


def person_verdict(person: Any) -> FormVerdict:
    who, said = who_of(person)
    reason = person_reason(person)
    answers = answers_said(person)
    return FormVerdict(kind='person', kind_said=who, time=person.given_at, model=said,
                       version_said=f'answers {answers}' if answers else 'verdict',
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


def reading_row(attempt: Any, people: list[Any], chosen: Any = None, trials: bool = False) -> FormReading:
    """A reading's row and its verdicts, newest first (31.a): a pipeline reading's judgements that count and the person's
    verdicts in Readings; in the Lab its trials alone (`trials`, 37.a); a Lab reading's every judgement and verdict."""
    prototype = bool(attempt.prototype)
    state, said = result_of(attempt, prototype)
    judgements = attempt.judgements or []
    if trials:
        judgements = [judgement for judgement in judgements if not judgement.counts]
    elif not in_lab(attempt):
        judgements = [judgement for judgement in judgements if judgement.counts]
    verdicts = [judge_verdict(judgement) for judgement in judgements]
    if not trials:
        verdicts += [person_verdict(person) for person in people if person.reading_key == attempt.reading_key]
    verdicts.sort(key=lambda one: moment(one.time) or EARLIEST, reverse=True)
    return FormReading(key=attempt.reading_key, time=attempt.stored_at, model=attempt.model, cost_usd=attempt.cost_usd,
                       version=attempt.reader_version, result_state=state, result_said=said, shown=bool(attempt.shown),
                       test_reading=bool(getattr(attempt, 'test_reading', False)),
                       promoted_said=promoted_said(attempt),
                       promotable=prototype and attempt.reader_version == 'page/1' and not getattr(attempt, 'promoted', None),
                       recall=None if attempt.shown else attempt.reading_key,
                       served_said='served' if attempt.shown else None,
                       show_why_not=reading_why_not(verdicts) if not attempt.shown else None,
                       verdicts=verdicts,
                       hover=reading_hover(attempt, chosen))


def reading_why_not(verdicts: list[FormVerdict]) -> str | None:
    """Why a reading's own show is greyed (42.a): a judge beneath it whose show is active, its findings drawn on the same
    reading (a finding struck by code among them, 178.a), named by its version; None where no judge beneath it has one, so
    the judges' shows are the greyed ones (decision 25) and never both."""
    active = next((verdict for verdict in verdicts if verdict.kind == 'judge' and verdict.recall and not verdict.show_why_not), None)
    return f"show on {active.version or 'its judge'}: the same reading with its findings" if active else None


def in_lab(attempt: Any) -> bool:
    return bool(attempt.prototype) and not getattr(attempt, 'promoted', None)


EARLIEST = datetime.min.replace(tzinfo=timezone.utc)
TRIAL = 'a trial in the Lab: no verdict applies to it; a person judges only what counts'


def moment(text: str | None) -> datetime | None:
    """An ISO 8601 stamp as a moment, a date alone or a stamp without its zone taken as UTC; None where there is none."""
    if not text:
        return None
    try:
        at = datetime.fromisoformat(text)
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def superseded_at(attempts: list[Any], attempt: Any) -> datetime | None:
    """When a pipeline reading was replaced (29.d): the moment the next pipeline reading was read; None for the latest."""
    own = moment(attempt.stored_at)
    later = sorted(at for at in (moment(one.stored_at) for one in attempts if not in_lab(one) and one is not attempt)
                   if at and own and at > own)
    return later[0] if later else None


def then_of(attempts: list[Any], attempt: Any, judgement: Any = None) -> datetime | None:
    """The moment a recall shows (29.d, 39.a): a judgement's own, a reading's until the next pipeline reading replaced
    it; None for now."""
    return moment(judgement.stored_at) if judgement is not None else superseded_at(attempts, attempt)


def at_then(people: list[Any], then: datetime | None) -> list[Any]:
    """The person's verdicts as they stood at a moment (29.d, 39.a): given by then, and not archived by a reset by then;
    every one not archived where the moment is now."""
    if then is None:
        return [person for person in people if not person.archived]
    return [person for person in people if (moment(person.given_at) or EARLIEST) <= then
            and not (person.archived and (moment(getattr(person, 'archived_at', None)) or EARLIEST) <= then)]


def latest_per_block(people: list[Any]) -> list[Any]:
    """Of a reading's verdicts, the latest per block, or per page where the block is none: the ones that stand (#17)."""
    ordered = sorted(enumerate(people), key=lambda one: (moment(one[1].given_at) or EARLIEST, one[0]))
    latest = {person.block: person for _, person in ordered}
    return [person for _, person in ordered if latest[person.block] is person]


def judgement_standing_for(attempt: Any) -> Any:
    """The judgement that stands for a reading (decision 26): the core's standing one on the served reading, else its
    latest counting one; on a Lab reading, whose judgements never count, its latest. None where none judged it."""
    judgements = sorted(attempt.judgements or [], key=lambda one: one.stored_at or '')
    if in_lab(attempt):
        return judgements[-1] if judgements else None
    standing = [judgement for judgement in judgements if judgement.standing]
    counting = [judgement for judgement in judgements if judgement.counts]
    return (standing or counting or [None])[-1]


def judge_row(attempt: Any, judgement: Any, standing_said: Literal['standing', 'recalled', 'counted then'] = 'standing') -> VerdictRow:
    said = findings_said(judgement)
    word, overruled = judge_word(judgement)
    return VerdictRow(kind='judge', kind_said='judge', standing=True, standing_said=standing_said,
                      recalled=standing_said == 'recalled', time=judgement.stored_at, verdict=word, overruled=overruled,
                      state=judge_state(judgement), reason=finding_reason(judgement), about=finding_blocks(judgement),
                      recall=judgement.recall, who='machine',
                      who_said=' · '.join(part for part in (judgement.version, judgement.model) if part) or 'a judge',
                      hover=[HoverRow(label='reading key', value=attempt.reading_key), *judge_hover(judgement),
                             *([HoverRow(label='all findings', value=said)] if said else [])])


def person_row(person: Any) -> VerdictRow:
    who, said = who_of(person)
    answered = person.answers
    return VerdictRow(kind='person', kind_said=who, standing=True, standing_said='standing',
                      time=person.given_at, verdict=person.verdict, state=person_state(person), reason=person_reason(person),
                      about=person.block or 'the page', judge_said=answers_said(person) or '—',
                      answered=AnsweredJudgement(version=answered.version, model=answered.model, stored_at=answered.stored_at,
                                                 derived=bool(person.answers_derived)) if answered else None,
                      who=who, who_said=said, hover=person_hover(person))


def shown_verdicts(attempts: list[Any], people: list[Any], reading_key: str | None, number: int | None = None,
                   judgement: Any = None) -> ShownVerdicts:
    """The verdicts as shown (decision 26), newest first (31.a). On the served reading (no `number`): the judgement that
    stands for it and the person's verdicts on it that stand now (a replaced one left out, 34.a). On a recalled trial, a
    Lab reading or a judgement that does not count: none, and why (38.a). On a recalled pipeline judgement or reading, the
    verdicts as then (29.d): the judgement recalled, the one that counted at that moment where another, and the person's
    verdicts given by then and not archived by then, the latest per block."""
    attempt = next((one for one in attempts if one.reading_key == reading_key), None)
    if attempt is None:
        return ShownVerdicts(said='as shown: no reading is served, so no verdict applies', count=0, rows=[])
    mine = [person for person in people if person.reading_key in (reading_key, None)]
    if number is None:
        standing = judgement_standing_for(attempt)
        rows = [judge_row(attempt, standing)] if standing is not None else []
        rows += [person_row(person) for person in mine if person.applies and not person.archived and person.standing]
        said, said_at = 'as shown: the verdicts on the served reading', None
    elif in_lab(attempt) or (judgement is not None and not judgement.counts):
        return ShownVerdicts(said='in the Lab: no verdict applies', recalled=True, count=None, rows=[], why_not=TRIAL)
    else:
        then = then_of(attempts, attempt, judgement)
        counting = sorted((one for one in attempt.judgements or [] if one.counts
                           and (then is None or (moment(one.stored_at) or EARLIEST) <= then)),
                          key=lambda one: moment(one.stored_at) or EARLIEST)
        rows = [judge_row(attempt, judgement, 'recalled')] if judgement is not None else []
        if counting and (judgement is None or counting[-1].recall != judgement.recall):
            rows.append(judge_row(attempt, counting[-1], 'counted then'))
        rows += [person_row(person) for person in latest_per_block(at_then(mine, then))]
        said = (f'as then: the verdicts on reading {number} on' if then is not None
                else f'as shown: the verdicts on reading {number} (recalled)')
        said_at = then.isoformat() if then is not None else None
    rows.sort(key=lambda one: moment(one.time) or EARLIEST, reverse=True)
    return ShownVerdicts(said=said, said_at=said_at, recalled=number is not None, count=len(rows), rows=rows)


def form_of(attempts: list[Any] | None, people: list[Any], chosen: Any = None) -> PageForm | None:
    """A read page's form: its pipeline readings (the one shown first, the earlier ones newest first), the Lab (its test
    readings and the trials on pipeline readings, newest first, counted by its trials) and the verdicts on the served
    reading as shown; None for a page no reader has read."""
    if attempts is None:
        return None
    pipeline = [attempt for attempt in attempts if not attempt.prototype or getattr(attempt, 'promoted', None)]
    pipeline = [*[attempt for attempt in pipeline if attempt.shown], *reversed([attempt for attempt in pipeline if not attempt.shown])]
    lab = sorted((attempt for attempt in attempts if attempt.prototype and not getattr(attempt, 'promoted', None)),
                 key=lambda one: one.stored_at or '', reverse=True)
    readings = [reading_row(attempt, people, chosen) for attempt in pipeline]
    # the Lab (37.a): the test readings, and beside them each pipeline reading's own row holding what was tried on it
    tried = [(attempt, reading_row(attempt, people)) for attempt in lab]
    tried += [(attempt, reading_row(attempt, people, chosen, trials=True)) for attempt in pipeline
              if any(not judgement.counts for judgement in attempt.judgements or [])]
    trials = len(lab) + sum(1 for attempt in pipeline for judgement in attempt.judgements or [] if not judgement.counts)

    def latest(row: FormReading) -> datetime:
        return max([moment(row.time) or EARLIEST, *(moment(verdict.time) or EARLIEST for verdict in row.verdicts)])

    served = next((attempt for attempt in attempts if attempt.shown), None)
    standing = [judgement for judgement in (served.judgements or [] if served else []) if judgement.standing]
    return PageForm(shown_judgement=standing[-1].judgement_key if standing else None,
                    readings_count=len(readings), lab_count=trials, readings=readings,
                    lab=sorted((row for _, row in tried), key=latest, reverse=True),
                    verdicts=shown_verdicts(attempts, people, served.reading_key if served else None))
