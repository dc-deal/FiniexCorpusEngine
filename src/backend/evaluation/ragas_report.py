"""A RAGAS report on one answer record: faithfulness, answer relevancy, context precision and context recall (decision 136.a).

RAGAS is the evaluation the course teaches (sprint 3, lessons 3 and 4: faithfulness at 0.8 is the first target, context metrics
below 0.7 point at retrieval). It runs in an environment of its own, `requirements-eval.txt`: RAGAS 0.4.3 pins `openai` below 2
and pulls the archived `langchain-community`, which the app's stack (openai 3, langchain-openai 1.6) cannot take (checked on
2026-11-09 with `pip install ragas --dry-run`). So this module imports nothing of the app's: it reads the record's JSON, the
questions' expected answers and the passages' texts from the index's SQLite file.

    python -m venv .venv-eval
    .venv-eval/Scripts/python -m pip install -r requirements-eval.txt
    .venv-eval/Scripts/python -m backend.evaluation.ragas_report _data/evaluation/results/answers_<label>.json

A sample is a question the chat answered from passages: its words, the answer, the passages' full texts and, for context
recall, the expected answer. Declines, clarifications and "nothing found" have no answer to judge and are counted, not
scored. The judge is a language model, so the numbers carry its noise: they compare runs, they are not a truth.
"""

import argparse
import json
import math
import os
import sqlite3
import sys
import urllib.request
from datetime import date
from pathlib import Path

from backend.configuration import data_paths

ROOT = Path(__file__).resolve().parents[3]
BASE_URL = 'https://openrouter.ai/api/v1'
# The judge is not the generator's model (gpt-5-mini), so no model grades its own answers. gpt-4.1-mini is on the course key.
JUDGE_MODEL = 'openai/gpt-4.1-mini'
EMBEDDING_MODEL = 'openai/text-embedding-3-small'  # the index's own (for answer relevancy's similarity)
METRICS = ('faithfulness', 'answer_relevancy', 'llm_context_precision_with_reference', 'context_recall')
# The course's reading of the numbers (sprint 3, lessons 3 and 4)
TARGETS = {'faithfulness': 0.8, 'answer_relevancy': None, 'llm_context_precision_with_reference': 0.7, 'context_recall': 0.7}
DATABASE = data_paths.INDEX / 'knowledge.sqlite3'
QUESTION_SETS = (ROOT / 'evaluation' / 'eval_questions.json', ROOT / 'evaluation' / 'eval_questions_holdout_2026-11-06.json')
RESULTS = data_paths.RESULTS
SCORED = ('answer', 'answer_partial')  # behaviours with an answer drawn from passages


def expected_answers(paths=QUESTION_SETS) -> dict[str, str]:
    """Question id -> its expected answer, from every question set that exists."""
    found = {}
    for path in paths:
        if Path(path).exists():
            for question in json.loads(Path(path).read_text(encoding='utf-8'))['questions']:
                if question.get('expected_answer'):
                    found[question['id']] = question['expected_answer']
    return found


def chunk_texts(chunk_ids: list[str], database: Path = DATABASE) -> dict[str, str]:
    """Chunk id -> the text the chat was given, as the index holds it."""
    if not chunk_ids:
        return {}
    with sqlite3.connect(database) as connection:
        marks = ','.join('?' * len(chunk_ids))
        return dict(connection.execute(f'SELECT id, text FROM chunks WHERE id IN ({marks})', list(chunk_ids)))


def samples(record: dict, references: dict[str, str], database: Path = DATABASE) -> tuple[list[dict], dict[str, int]]:
    """The record's answered questions as RAGAS samples, and how many questions were left out and why."""
    out, left_out = [], {}
    for question in record['questions']:
        turn = question.get('turn') or {}
        ids = [passage['chunk_id'] for passage in turn.get('retrieved') or []]
        why = ('not answered from passages' if turn.get('behaviour') not in SCORED else
               'no answer text' if not (turn.get('answer') or '').strip() else 'no passages' if not ids else None)
        if why:
            left_out[why] = left_out.get(why, 0) + 1
            continue
        texts = chunk_texts(ids, database)
        contexts = [texts[chunk] for chunk in ids if chunk in texts]
        if len(contexts) < len(ids):
            left_out['passages missing from the index'] = left_out.get('passages missing from the index', 0) + 1
            continue
        out.append({'id': question['id'], 'user_input': question['question'], 'response': turn['answer'],
                    'retrieved_contexts': contexts, 'reference': references.get(question['id'])})
    return out, left_out


def key_usage(key: str) -> float | None:
    """What the OpenRouter key has used so far, in USD; None where the endpoint does not answer."""
    request = urllib.request.Request(f'{BASE_URL}/key', headers={'Authorization': f'Bearer {key}'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return float(json.loads(response.read())['data']['usage'])
    except (OSError, ValueError, KeyError):
        return None


def score(rows: list[dict]) -> dict:
    """RAGAS over the samples: one row of scores per sample. Imports RAGAS here, so the module loads without it."""
    os.environ.setdefault('RAGAS_DO_NOT_TRACK', 'true')  # RAGAS reports usage to its makers unless told not to
    from dotenv import load_dotenv
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall, ResponseRelevancy
    from ragas.run_config import RunConfig

    load_dotenv(ROOT / '.env')
    key = os.environ['OPENROUTER_API_KEY']  # read here, never printed
    llm = LangchainLLMWrapper(ChatOpenAI(model=JUDGE_MODEL, base_url=BASE_URL, api_key=key, temperature=0, timeout=120,
                                         max_retries=2))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model=EMBEDDING_MODEL, base_url=BASE_URL, api_key=key,
                                                             check_embedding_ctx_length=False))
    data = EvaluationDataset.from_list([{name: row[name] for name in ('user_input', 'response', 'retrieved_contexts', 'reference')}
                                        for row in rows])
    # Answer relevancy asks the judge for three questions per answer by default; OpenRouter returns one generation per call
    # (RAGAS warns and goes on with one), so one is asked for, and the report says so. RAGAS 0.4.3 calls its LangChain
    # wrappers deprecated in favour of llm_factory; they work, and they take the course's ChatOpenAI with a base_url as it is.
    metrics = [Faithfulness(), ResponseRelevancy(strictness=1), LLMContextPrecisionWithReference(), LLMContextRecall()]
    before = key_usage(key)
    result = evaluate(data, metrics=metrics, llm=llm, embeddings=embeddings, run_config=RunConfig(max_workers=4, timeout=240),
                      show_progress=False)
    after = key_usage(key)
    scores = result.to_pandas().to_dict('records')
    return {'scores': [{'id': row['id'], **{name: _number(found.get(name)) for name in METRICS}}
                       for row, found in zip(rows, scores)],
            'cost_usd': round(after - before, 4) if before is not None and after is not None else None}


def _number(value) -> float | None:
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else round(float(value), 4)


def summary(scores: list[dict]) -> dict:
    """Per metric the mean over the samples it could score, and how many that were."""
    out = {}
    for name in METRICS:
        values = [row[name] for row in scores if row[name] is not None]
        out[name] = {'mean': round(sum(values) / len(values), 4) if values else None, 'scored': len(values),
                     'target': TARGETS[name]}
    return out


def markdown(report: dict) -> str:
    lines = [f"# RAGAS on `{report['record']}`", '',
             f"{report['samples']} answered questions scored, judge `{report['judge']}`, embeddings `{report['embeddings']}`, "
             f"RAGAS {report['ragas']}, {report['date']}; left out: {report['left_out'] or 'none'}; cost "
             f"{report['cost_usd'] if report['cost_usd'] is not None else 'not booked'} USD on the key.", '',
             '| metric | mean | scored | the course\'s mark |', '|---|---:|---:|---:|']
    for name, row in report['summary'].items():
        mean = '–' if row['mean'] is None else f"{row['mean']:.3f}"
        lines.append(f"| {name} | {mean} | {row['scored']} | {row['target'] if row['target'] is not None else '–'} |")
    lines += ['', '| question | ' + ' | '.join(METRICS) + ' |', '|---|' + '---:|' * len(METRICS)]
    for row in report['scores']:
        lines.append(f"| {row['id']} | " + ' | '.join('–' if row[name] is None else f'{row[name]:.2f}' for name in METRICS) + ' |')
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('record', type=Path, help='an answer record of answer_eval, _data/evaluation/results/answers_<label>.json')
    parser.add_argument('--limit', type=int, default=0, help='score only the first N samples (a smoke run)')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')
    record = json.loads(args.record.read_text(encoding='utf-8'))
    rows, left_out = samples(record, expected_answers())
    if args.limit:
        rows = rows[:args.limit]
    import ragas

    scored = score(rows)
    report = {'record': args.record.name, 'label': record.get('label'), 'date': date.today().isoformat(), 'judge': JUDGE_MODEL,
              'embeddings': EMBEDDING_MODEL, 'ragas': ragas.__version__, 'samples': len(rows), 'left_out': left_out,
              'cost_usd': scored['cost_usd'], 'summary': summary(scored['scores']), 'scores': scored['scores']}
    stem = f"ragas_{record.get('label') or args.record.stem}{'_limit' + str(args.limit) if args.limit else ''}"
    (RESULTS / f'{stem}.json').write_bytes((json.dumps(report, indent=1, ensure_ascii=False) + '\n').encode('utf-8'))
    (RESULTS / f'{stem}.md').write_bytes(markdown(report).encode('utf-8'))  # written first, then printed (a cp1252 console)
    print(markdown(report).split('\n\n| question')[0])
    print(f'written to {RESULTS / stem}.json and .md')
    return 0


if __name__ == '__main__':
    sys.exit(main())
