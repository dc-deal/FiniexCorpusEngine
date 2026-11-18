"""Measure retrieval against the evaluation questions: precision@k, recall@k, hit@k and MRR.

Every question with expected sources is sent to `retrieve()` once. The top k_max chunks are then
compared with the operator-confirmed expected sources at two levels:

- **document**: the chunk comes from the expected book, paper or Wikipedia article;
- **section**: it also comes from the expected section (PDF: the section title; HTML: the anchor,
  where null is an article's lead).

Metrics per question, averaged over the questions (each question weighs the same):

- precision@k: share of the top k that are hits. How much of what the model would get is useful.
- recall@k:    share of the expected sources found in the top k. Whether what is needed is there.
- hit@k:       whether at least one expected source is in the top k. Counted as "n of N".
- MRR:         1 / rank of the first hit within k_max, 0 if none. Rewards finding it early.

The numbers are a lower bound: the expected sources are the ones that were found and confirmed,
not every good passage in the corpus. The comparison between phases is fair, because every phase
is measured against the same list.

Run from the repository root:
    python -m backend.evaluation.retrieval_eval --label baseline       # the 14 tuning questions
    python -m backend.evaluation.retrieval_eval --holdout --label final  # the held-out set, once, at the end
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.configuration import data_paths
from backend.ingestion import chunking
from backend.providers import openrouter_client
from backend.search.retrieval import retrieve

ROOT = Path(__file__).resolve().parents[3]
QUESTIONS = ROOT / 'evaluation' / 'eval_questions.json'
# The capstone's fresh held-out set (phase 6). The RAG sprint's, `eval_questions_holdout.json`, was read on 2026-10-01 and is
# spent: the ledger says so, and the evaluation never reads it as a held-out set again.
HOLDOUT = ROOT / 'evaluation' / 'eval_questions_holdout_2026-11-06.json'
HOLDOUT_LEDGER = ROOT / 'evaluation' / 'holdout_ledger.json'


class HeldOutSpent(RuntimeError):
    """A held-out set that was read before, asked for again without a reason."""


def claim_holdout(command: str, again: str | None = None, path: Path = HOLDOUT, ledger: Path = HOLDOUT_LEDGER) -> Path:
    """The held-out set, read once: a mechanism, not a sentence. The reading is written to the ledger before anything is
    measured, so a run that fails halfway still counts as seen; a second reading is refused unless `again` states why, and the
    ledger keeps the reason beside the first reading (a lesson of a neighbouring project's outcome harness)."""
    from backend.conversion.store import pipeline_db

    record = json.loads(ledger.read_text(encoding='utf-8'))
    name = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix()
    earlier = [run for run in record['runs'] if run['file'] == name]
    if earlier and not again:
        raise HeldOutSpent(f"{name} was read on {earlier[0]['at']} ({earlier[0]['command']}); "
                           'a second reading needs --again "the reason"')
    record['runs'].append({'file': name, 'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'command': command,
                           'commit': pipeline_db.code_version()['code_commit'], 'again': again})
    ledger.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    return path
RESULTS = data_paths.RESULTS
KS = (3, 5, 10)
LEVELS = ('document', 'section')
_ARTICLE = re.compile(r'title=([^&#]+)')


def chunk_document(citation: dict) -> tuple:
    """The document a chunk belongs to. A Wikipedia chunk belongs to its article, not to the set."""
    match = _ARTICLE.search(citation.get('url', ''))
    return (citation['source_id'], match.group(1)) if match else (citation['source_id'],)


def expected_document(expected: dict) -> tuple:
    return (expected['source'], expected['article']) if 'article' in expected else (expected['source'],)


def matches(citation: dict, expected: dict, level: str) -> bool:
    """Whether a retrieved chunk satisfies one expected source at the given level."""
    if chunk_document(citation) != expected_document(expected):
        return False
    if level == 'document':
        return True
    if 'anchor' in expected:
        return citation.get('anchor') == expected['anchor']
    return citation.get('section') == expected['section']


def judge(results: list[dict], expected: list[dict]) -> list[dict]:
    """Mark every retrieved chunk: which expected sources it satisfies, at each level."""
    judged = []
    for rank, result in enumerate(results, start=1):
        judged.append({
            'rank': rank,
            'chunk_id': result['chunk_id'],
            'similarity': result['similarity'],
            'citation': result['citation'],
            'matched': {level: [i for i, e in enumerate(expected) if matches(result['citation'], e, level)]
                        for level in LEVELS},
        })
    return judged


def question_metrics(judged: list[dict], expected_count: int, k_max: int) -> dict:
    """precision@k, recall@k, hit@k per level, and MRR within k_max."""
    metrics = {}
    for level in LEVELS:
        per_k = {}
        for k in KS:
            window = judged[:k]
            hits = sum(1 for j in window if j['matched'][level])
            found = {i for j in window for i in j['matched'][level]}
            per_k[k] = {'precision': hits / k, 'recall': len(found) / expected_count, 'hit': int(bool(found))}
        first = next((j['rank'] for j in judged[:k_max] if j['matched'][level]), None)
        metrics[level] = {'at_k': per_k, 'reciprocal_rank': 1 / first if first else 0.0, 'first_hit_rank': first}
    return metrics


def summarise(per_question: list[dict]) -> dict:
    """Averages over questions, and hit counts."""
    n = len(per_question)
    summary = {'questions': n}
    for level in LEVELS:
        summary[level] = {
            str(k): {
                'precision': sum(q['metrics'][level]['at_k'][k]['precision'] for q in per_question) / n,
                'recall': sum(q['metrics'][level]['at_k'][k]['recall'] for q in per_question) / n,
                'hits': sum(q['metrics'][level]['at_k'][k]['hit'] for q in per_question),
            } for k in KS}
        summary[level]['mrr'] = sum(q['metrics'][level]['reciprocal_rank'] for q in per_question) / n
    return summary


def describe(citation: dict) -> str:
    """A short, human-readable locator for the report."""
    title = citation.get('source_title', citation['source_id'])
    document = chunk_document(citation)
    name = document[1].replace('_', ' ') if len(document) > 1 else title
    if 'pdf_page' in citation:
        printed = citation.get('printed_page')
        page = f"p. {printed}" if printed == citation['pdf_page'] else f"p. {printed} (PDF {citation['pdf_page']})"
        return f"{name[:30]} · {citation.get('section', '')[:52]} · {page}"
    anchor = f"#{citation['anchor']}" if citation.get('anchor') else '(lead)'
    return f"{name[:30]} · {anchor[:52]}"


def describe_expected(expected: dict) -> str:
    if 'article' in expected:
        return f"{expected['article'].replace('_', ' ')} · {('#' + expected['anchor']) if expected.get('anchor') else '(lead)'}"
    if 'anchor' in expected:
        return f"{expected['source']} · #{expected['anchor']}"
    return f"{expected['source']} · {expected['section']}"


def print_question(entry: dict, show: int = 5) -> None:
    section = entry['metrics']['section']
    print(f"\n{entry['id']}  {entry['question']}")
    print(f"    section hit@5 {'✓' if section['at_k'][5]['hit'] else '✗'}   "
          f"recall@5 {len({i for j in entry['judged'][:5] for i in j['matched']['section']})}/{len(entry['expected'])}   "
          f"first section hit at rank {section['first_hit_rank'] or '–'}")
    for j in entry['judged'][:show]:
        mark = '✓' if j['matched']['section'] else '~' if j['matched']['document'] else '✗'
        print(f"    {j['rank']:>2}  {j['similarity']:.3f}  {mark}  {describe(j['citation'])}")
    found = {i for j in entry['judged'][:10] for i in j['matched']['section']}
    missing = [describe_expected(e) for i, e in enumerate(entry['expected']) if i not in found]
    print(f"    not in top 10: {'; '.join(missing) if missing else '–'}")


def print_summary(summary: dict) -> None:
    print(f"\n{summary['questions']} questions")
    print(f"{'':16}" + ''.join(f"{'k=' + str(k):^18}" for k in KS))
    print(f"{'':16}" + ''.join(f"{'document':>9}{'section':>9}" for _ in KS))
    for metric in ('precision', 'recall'):
        print(f"{metric + '@k':16}" + ''.join(
            f"{summary['document'][str(k)][metric]:>9.2f}{summary['section'][str(k)][metric]:>9.2f}" for k in KS))
    n = summary['questions']
    print(f"{'hit@k':16}" + ''.join(
        f"{str(summary['document'][str(k)]['hits']) + '/' + str(n):>9}{str(summary['section'][str(k)]['hits']) + '/' + str(n):>9}" for k in KS))
    print(f"{'MRR (k=10)':16}{summary['document']['mrr']:>9.2f}{summary['section']['mrr']:>9.2f}")


def evaluate(questions: list[dict], k_max: int = 10, search=retrieve) -> list[dict]:
    """Run every question with expected sources through the search and judge the results."""
    per_question = []
    for question in questions:
        expected = question['expected_sources']
        if not expected:
            continue
        judged = judge(search(question['question'], k=k_max), expected)
        per_question.append({'id': question['id'], 'question': question['question'],
                             'behaviour': question['behaviour'], 'expected': expected, 'judged': judged,
                             'metrics': question_metrics(judged, len(expected), k_max)})
    return per_question


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--label', default='baseline', help='name of this measurement, e.g. baseline')
    parser.add_argument('--holdout', action='store_true', help='measure the held-out set (only once, at the end)')
    parser.add_argument('--again', metavar='REASON', help='read the held-out set a second time; the ledger keeps the reason')
    parser.add_argument('--k-max', type=int, default=max(KS))
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')  # a redirected Windows console is cp1252

    try:
        source = claim_holdout('retrieval_eval ' + ' '.join(argv or sys.argv[1:]), args.again) if args.holdout else QUESTIONS
    except HeldOutSpent as refusal:
        print(refusal, file=sys.stderr)
        return 2
    if args.holdout:
        print('HELD-OUT SET: measured once, at the end. Its results must not steer any change.\n')
    questions = json.loads(source.read_text(encoding='utf-8'))['questions']
    skipped = [q['id'] for q in questions if not q['expected_sources']]

    per_question = evaluate(questions, args.k_max)
    if not per_question:
        print(f'no question in {source.name} has expected sources yet', file=sys.stderr)
        return 2
    for entry in per_question:
        print_question(entry)
    summary = summarise(per_question)
    print_summary(summary)
    print(f"\nskipped (no expected sources, scored on behaviour from phase 4): {', '.join(skipped) or '–'}")

    tokens = sum(chunking.count_tokens(q['question']) for q in questions if q['expected_sources'])
    now = datetime.now(timezone.utc)
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"retrieval_{args.label}_{now.date().isoformat()}.json"
    out.write_text(json.dumps({
        'label': args.label, 'measured_at': now.isoformat(timespec='seconds'),
        'questions_file': source.name, 'retrieval': 'vector only (Chroma, cosine)',
        'embedding_model': openrouter_client.EMBEDDING_MODEL, 'k': list(KS), 'k_max': args.k_max,
        'query_tokens': tokens,
        'estimated_usd': tokens * openrouter_client.EMBEDDING_USD_PER_MILLION_TOKENS / 1_000_000,
        'summary': summary, 'skipped': skipped,
        'questions': [{**{k: v for k, v in e.items() if k != 'judged'},
                       'results': [{**{k: v for k, v in j.items() if k != 'citation'},
                                    'where': describe(j['citation'])} for j in e['judged']]}
                      for e in per_question],
    }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(f'results: {out.relative_to(ROOT)}  ({tokens} query tokens, ≈ {tokens * 0.02 / 1e6:.6f} USD)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
