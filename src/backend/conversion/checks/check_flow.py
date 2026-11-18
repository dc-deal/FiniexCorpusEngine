"""The check flow's decisions: which readings the judge sees, and what becomes of each page (decision OC-5.a).

Stage 1 is `page_contract`, stage 2 `page_checks`, stage 3 `page_judge`; this module holds what lies between them. The judge sees every
suspicious reading, every reading with a block stage 2 cannot check (a table printed as an image, text inside a figure, a formula drawn
as paths: decision 83.a, so no quoted block goes without a second witness), and a random sample per work. The issues are the early warning:
how many there are tells whether a technique must change. A work is stopped by its random sample only, because suspicious pages are chosen
for being doubtful, and pages with such a block for being hard, and either would overstate the rate.

States of a page, kept apart so nobody reads one as another:

    ok            judged, and the judge found nothing major
    ok_unjudged   passed stages 1 and 2, not in the sample: unchecked by a model, which is not the same as checked
    issue         a person looks at it: the judge's bad or unsure, or a format failure after the retry (called the bin
                  until decision 97.a; reports written before it say 'bin', which `current_state` reads as an issue)
    blocked       refused or blocked by the provider: not bad, it keeps its local conversion
    stopped       its work is stopped until a person has looked
"""

import random
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    """Starting values, to be calibrated on publisher gold in the mini pilot."""
    sample_per_work: int = 20
    stop_above: int = 3
    # Where every page is judged, the stop is a share of the judged pages, the one stop_above is of a full sample (decision
    # 74.a: 6 of 40 is 3 of 20); a count meant for a sample of 40 would stop a work of 100 pages at 7 bad, 7 %.
    stop_share: float | None = None


@dataclass(frozen=True)
class Selection:
    suspicious: frozenset
    sampled: frozenset
    unverifiable: frozenset = frozenset()  # not suspicious, but holding a block stage 2 cannot check; may overlap the sample
    reread: frozenset = frozenset()  # a re-read after the judge's issue (133.b): judged again, whatever stage 2 says

    @property
    def keys(self) -> frozenset:
        return self.suspicious | self.sampled | self.unverifiable | self.reread


def select_for_judge(pages: list[dict], policy: Policy = Policy()) -> Selection:
    """Every suspicious reading, every reading with a block stage 2 cannot check, and a sample of the rest per work, reproducible:
    seeded by the work's key. The sample is drawn from every page that is not suspicious, those with such a block included, so it
    stays a random sample of the work. A page: {'key', 'work', 'result_class', 'suspicious', 'unverifiable'}. Only readings that
    passed stage 1 can be judged."""
    usable = [page for page in pages if page['result_class'] == 'ok']
    suspicious = frozenset(page['key'] for page in usable if page.get('suspicious'))
    unverifiable = frozenset(page['key'] for page in usable if page.get('unverifiable') and page['key'] not in suspicious)
    sampled = set()
    for work in sorted({page['work'] for page in usable}):
        rest = sorted(page['key'] for page in usable if page['work'] == work and page['key'] not in suspicious)
        sampled.update(random.Random(work).sample(rest, min(policy.sample_per_work, len(rest))))
    return Selection(suspicious, frozenset(sampled), unverifiable)


def current_state(state: str | None) -> str | None:
    """A state as it is called today: 'bin', from a report written before decision 97.a, is an issue."""
    return 'issue' if state == 'bin' else state


def state_of(result_class: str, verdict: dict | None) -> tuple[str, list]:
    """One reading's state and reasons from its class and the judge's verdict, as `outcomes` gives it within a run."""
    return _state({'result_class': result_class}, verdict)


def _state(page: dict, verdict: dict | None) -> tuple[str, list]:
    if page['result_class'] in ('refused', 'errored', 'blocked'):
        return 'blocked', [page['result_class']]
    if page['result_class'] != 'ok':
        return 'issue', [f"format: {page['result_class']}"]
    if verdict is None:
        return 'ok_unjudged', []
    if verdict['outcome'] == 'ok':
        return 'ok', []
    return 'issue', [f"judge: {verdict['verdict']}"] + [finding.get('kind', 'other') for finding in verdict.get('findings', [])]


def outcomes(pages: list[dict], verdicts: dict, selection: Selection, policy: Policy = Policy()) -> dict:
    """Per page its state and reasons; per work the sample's bad count, whether it stopped, and how many issues it has."""
    rows, works = [], {}
    for page in pages:
        state, reasons = _state(page, verdicts.get(page['key']))
        rows.append({'key': page['key'], 'work': page['work'], 'state': state, 'reasons': reasons,
                     'in_sample': page['key'] in selection.sampled, 'suspicious': page['key'] in selection.suspicious,
                     'unverifiable': page['key'] in selection.unverifiable, 'reread': page['key'] in selection.reread})
    for work in sorted({row['work'] for row in rows}):
        own = [row for row in rows if row['work'] == work]
        sample_bad = sum(1 for row in own if row['in_sample'] and row['state'] == 'issue')
        limit = policy.stop_share * sum(1 for row in own if row['in_sample']) if policy.stop_share is not None else policy.stop_above
        stopped = sample_bad > limit
        if stopped:
            for row in own:
                if row['state'] in ('ok', 'ok_unjudged'):
                    row['state'] = 'stopped'
        works[work] = {'pages': len(own), 'sample_size': sum(1 for row in own if row['in_sample']), 'sample_bad': sample_bad, 'stopped': stopped,
                       'issues': sum(1 for row in own if row['state'] == 'issue'), 'blocked': sum(1 for row in own if row['state'] == 'blocked'),
                       'states': dict(Counter(row['state'] for row in own))}
    return {'pages': rows, 'works': works, 'finding_kinds': dict(Counter(reason for row in rows for reason in row['reasons']))}


def issue_entries(result: dict) -> list[dict]:
    """The issues a person should look at: ids and reasons, no page text."""
    return [{'key': row['key'], 'work': row['work'], 'reasons': row['reasons']} for row in result['pages'] if row['state'] == 'issue']
