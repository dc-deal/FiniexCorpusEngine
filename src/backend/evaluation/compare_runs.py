"""Compare two answer measurements question by question, as phase 6's gates ask (docs/phase_06_retrieval_quality.md).

A change is judged against a baseline on the same questions, never on totals alone: on sixty questions one point can be one
borderline question that a shift in the statistics moved. So this reports
- the paired difference in section recall@5 and in the reciprocal rank, with a 95 % bootstrap interval over the questions;
- correct behaviours and answers with a verified quote, before and after, and which questions changed;
- every question whose first expected section moved, and whether that section's indexed text changed between the runs
  (from the digests each record keeps); a move with unchanged text is the statistics, not the content;
- the gate's verdict: kept as an improvement, kept as holding, or dropped.

    python -m backend.evaluation.compare_runs _data/evaluation/results/answers_phase6-baseline_2026-11-06.json \\
        _data/evaluation/results/answers_phase6-exercises-demoted_2026-11-06.json

No model is called; it reads two records.
"""

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

RESAMPLES = 10_000
FLOOR = -0.05  # the gate: the interval's lower bound must lie above this
# Correct behaviours may fall by at most this many questions: two since 6 Nov (one before), when a replay with the baseline's
# own plans scored retrieval identically and the generator still moved two behaviours, both on identical passages.
BEHAVIOUR_SLACK = 2
# Since 8 Nov (decision 116.a, the operator, written before the run it first judges): behaviours and verified quotes are judged only on
# the questions whose passages the change altered, and quotes by count, not share. On identical passages the generator alone
# moved two to three questions in every run, and a share fell when a question was newly answered without a quote.
QUOTE_SLACK = 2


def questions_of(record: dict) -> dict[str, dict]:
    return {question['id']: question for question in record['questions']}


def measure(question: dict, name: str, level: str = 'section') -> float | None:
    retrieval = question['score'].get('retrieval')
    return None if retrieval is None else retrieval[level][name]


def first_rank(question: dict) -> int | None:
    """The rank of the first passage from an expected section, from the reciprocal rank the record keeps."""
    rr = measure(question, 'rr')
    return round(1 / rr) if rr else None


def passages_of(question: dict) -> list[str]:
    """The passages the model was given, by chunk id and in order: what a change to retrieval can alter."""
    return [passage.get('chunk_id') for passage in question['turn'].get('retrieved') or []]


def interval(differences: list[float], seed: int = 0) -> tuple[float, float, float]:
    """The mean of paired differences and its 95 % percentile bootstrap interval; fixed seed, so a report can be rerun."""
    if not differences:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    count = len(differences)
    means = sorted(statistics.fmean(rng.choices(differences, k=count)) for _ in range(RESAMPLES))
    return statistics.fmean(differences), means[int(0.025 * RESAMPLES)], means[int(0.975 * RESAMPLES) - 1]


def compare(base: dict, new: dict) -> dict:
    """The gate's comparison. Two records that do not hold the same questions, or hold none with expected sources, are not
    comparable: a verdict over the questions they happen to share would pass a run that lost questions, or a record of
    another set altogether."""
    before, after = questions_of(base), questions_of(new)
    shared = [qid for qid in before if qid in after]
    only_one = sorted(set(before) ^ set(after))
    scored = [qid for qid in shared if measure(before[qid], 'recall_5') is not None and measure(after[qid], 'recall_5') is not None]
    recall = interval([measure(after[qid], 'recall_5') - measure(before[qid], 'recall_5') for qid in scored])
    rr = interval([measure(after[qid], 'rr') - measure(before[qid], 'rr') for qid in scored])
    correct_before = sum(before[qid]['score']['correct'] for qid in shared)
    correct_after = sum(after[qid]['score']['correct'] for qid in shared)
    quoted = lambda questions: sum(1 for qid in shared if questions[qid]['turn'].get('quotes'))
    answered = lambda questions: sum(1 for qid in shared if questions[qid]['turn'].get('behaviour') in ('answer', 'clarify'))
    moved = []
    for qid in scored:
        ranks = first_rank(before[qid]), first_rank(after[qid])
        if ranks[0] != ranks[1]:
            digests = before[qid].get('expected_digests'), after[qid].get('expected_digests')
            text = 'unknown' if None in digests else 'unchanged' if digests[0] == digests[1] else 'changed'
            moved.append({'id': qid, 'question': after[qid]['question'], 'rank_before': ranks[0], 'rank_after': ranks[1],
                          'expected_text': text})
    altered = [qid for qid in shared if passages_of(before[qid]) != passages_of(after[qid])]
    altered_correct = (sum(before[qid]['score']['correct'] for qid in altered), sum(after[qid]['score']['correct'] for qid in altered))
    altered_quoted = (sum(1 for qid in altered if before[qid]['turn'].get('quotes')),
                      sum(1 for qid in altered if after[qid]['turn'].get('quotes')))
    holds = (recall[0] >= 0 and recall[1] > FLOOR and altered_correct[1] >= altered_correct[0] - BEHAVIOUR_SLACK
             and altered_quoted[1] >= altered_quoted[0] - QUOTE_SLACK)
    verdict = ('not comparable' if only_one or not scored else
               'improvement' if holds and recall[1] > 0 else 'holds' if holds else 'dropped')
    return {
        'base': base.get('label'), 'new': new.get('label'), 'questions': len(shared), 'scored': len(scored),
        'in_one_record_only': only_one,
        'section_recall_5': {'difference': round(recall[0], 4), 'low': round(recall[1], 4), 'high': round(recall[2], 4)},
        'reciprocal_rank': {'difference': round(rr[0], 4), 'low': round(rr[1], 4), 'high': round(rr[2], 4)},
        'behaviour_correct': {'before': correct_before, 'after': correct_after,
                              'changed': [{'id': qid, 'before': before[qid]['score']['got'], 'after': after[qid]['score']['got'],
                                           'expected': after[qid]['score']['expected']}
                                          for qid in shared if before[qid]['score']['got'] != after[qid]['score']['got']]},
        'answers_with_a_verified_quote': {'before': f'{quoted(before)} of {answered(before)}',
                                          'after': f'{quoted(after)} of {answered(after)}'},
        'altered': {'questions': altered, 'behaviour_correct': {'before': altered_correct[0], 'after': altered_correct[1]},
                    'with_a_verified_quote': {'before': altered_quoted[0], 'after': altered_quoted[1]}},
        'moved': moved,
        'verdict': verdict,
    }


def markdown(result: dict) -> str:
    recall, rr, behaviour = result['section_recall_5'], result['reciprocal_rank'], result['behaviour_correct']
    lines = [f"# `{result['new']}` against `{result['base']}`", '',
             f"{result['questions']} questions, {result['scored']} with expected sources. Verdict: **{result['verdict']}**.", '',
             *([f"Questions in one record only: {', '.join(result['in_one_record_only'])}.", '']
               if result.get('in_one_record_only') else []),
             '| measure | before → after, or paired difference [95 % interval] |', '|---|---|',
             f"| section recall@5 | {recall['difference']:+.3f} [{recall['low']:+.3f}, {recall['high']:+.3f}] |",
             f"| reciprocal rank of the first expected section | {rr['difference']:+.3f} [{rr['low']:+.3f}, {rr['high']:+.3f}] |",
             f"| behaviour correct | {behaviour['before']} → {behaviour['after']} |",
             f"| answers with a verified quote | {result['answers_with_a_verified_quote']['before']} → "
             f"{result['answers_with_a_verified_quote']['after']} |",
             *([f"| the gate's questions: passages altered | {len(result['altered']['questions'])}: "
                f"{', '.join(result['altered']['questions']) or 'none'} |",
                f"| among them: behaviour correct, with a verified quote | "
                f"{result['altered']['behaviour_correct']['before']} → {result['altered']['behaviour_correct']['after']}, "
                f"{result['altered']['with_a_verified_quote']['before']} → {result['altered']['with_a_verified_quote']['after']} |"]
               if 'altered' in result else []), '',
             '**Questions whose first expected section moved** (rank before → after; whether the section\'s indexed text changed):', '']
    lines += [f"- {m['id']}: {m['rank_before'] or '—'} → {m['rank_after'] or '—'} ({m['expected_text']}) · {m['question']}"
              for m in result['moved']] or ['- none']
    lines += ['', '**Behaviours that changed:**', '']
    lines += [f"- {c['id']}: {c['before']} → {c['after']} (expected {c['expected']})" for c in behaviour['changed']] or ['- none']
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('base', type=Path)
    parser.add_argument('new', type=Path)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')
    result = compare(*(json.loads(path.read_text(encoding='utf-8')) for path in (args.base, args.new)))
    out = args.new.with_name(f"compare_{result['new']}_vs_{result['base']}")
    out.with_suffix('.json').write_text(json.dumps(result, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    out.with_suffix('.md').write_text(markdown(result), encoding='utf-8', newline='\n')
    print(markdown(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
