"""Measure phase 6: whole chat turns, from the question to the cited answer.

Every question of the dataset goes through `chat_turn.run_turn` with the configured models and
retrieval. Scored without a judge model, from what the turn returns:

- **behaviour**: the turn's outcome against the dataset, in five classes: answer (every answer_*
  except not_found), not_found, clarify, decline_off_topic, decline_harmful;
- **quotes**: how many the model proposed and how many survived the word-for-word check;
- **grounding**: whether the turn's sources, and its verified quotes, include an expected section;
- **gaps**: whether a partial answer names what is missing;
- cost and latency per turn.

The answers themselves are written to a Markdown report for reading: a model-based score
(faithfulness with RAGAS, lesson 3) would add a judge model's opinion, and reading 24 answers is
still possible by hand.

Run from the repository root (spends money, about 0.002 USD per question):
    python -m backend.evaluation.answer_eval --label phase6
    python -m backend.evaluation.answer_eval --through-server --label phase6-baseline   # the chat's own way (102.a)

With `--through-server` every question takes the chat's path since decision 98.c: the search server, started over stdio with
`--public-only`, routes and searches (`semantic_search`), and the chat answers and checks its quotes (`chat_turn.search_turn`).
Retrieval is then scored from the passages the model was given: recall@5, hit@5 and the reciprocal rank of the first
expected section, per question, and by the question's style and its expected work (decision 102.a, the operator, 2026-11-06).
"""

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.configuration import data_paths
from backend.chat import app_config, chat_turn
from backend.evaluation import retrieval_eval
from backend.ingestion import index_store
from backend.providers import chat_models, embedding_route, openrouter_client
from backend.types.config_types.app_config_types import ChatProvider
from backend.search import retrieval

RESULTS = data_paths.RESULTS
EXPECTED = {'clarify': 'clarify', 'decline_off_topic': 'decline_off_topic', 'decline_harmful': 'decline_harmful',
            'answer_not_found': 'not_found'}


def expected_outcome(behaviour: str) -> str:
    return EXPECTED.get(behaviour, 'answer')


def grounded(sources: list[dict], expected: list[dict]) -> bool:
    """Whether any of the given sources is an expected section (phase 3's section-level match)."""
    return any(retrieval_eval.matches(s['metadata'], e, 'section') for s in sources for e in expected)


def retrieval_scores(turn: dict, expected: list[dict]) -> dict | None:
    """recall@5, hit@5 and the reciprocal rank of the first expected source, by section and by document, from the passages
    the model was given, in their order; None for a question without expected sources."""
    if not expected:
        return None
    results = [{'chunk_id': passage.get('chunk_id'), 'similarity': passage.get('similarity'), 'citation': passage['metadata']}
               for passage in turn['retrieved'] or []]
    metrics = retrieval_eval.question_metrics(retrieval_eval.judge(results, expected), len(expected), 10)
    return {level: {'recall_5': metrics[level]['at_k'][5]['recall'], 'hit_5': metrics[level]['at_k'][5]['hit'],
                    'rr': metrics[level]['reciprocal_rank']} for level in retrieval_eval.LEVELS}


def score(question: dict, turn: dict) -> dict:
    expected = question['expected_sources']
    quoted = [turn['retrieved'][q['passage'] - 1] for q in turn['quotes']] if turn['retrieved'] else []
    return {
        'retrieval': retrieval_scores(turn, expected),
        'expected': expected_outcome(question['behaviour']),
        'got': turn['behaviour'],
        'correct': turn['behaviour'] == expected_outcome(question['behaviour']),
        'quotes_kept': len(turn['quotes']), 'quotes_dropped': turn['quotes_dropped'],
        'sources_grounded': grounded(turn['retrieved'], expected) if expected else None,
        'quote_grounded': grounded(quoted, expected) if expected and quoted else (False if expected else None),
        'gaps_named': bool(turn['gaps']) if question['behaviour'] == 'answer_partial' else None,
    }


def mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 3) if values else None


def retrieval_summary(rows: list[dict]) -> dict:
    """The retrieval scores averaged over the questions that have expected sources."""
    scored = [r['score']['retrieval'] for r in rows if r['score'].get('retrieval')]
    return {'questions': len(scored),
            **{f'{level}_{measure}': mean([s[level][measure] for s in scored])
               for level in retrieval_eval.LEVELS for measure in ('recall_5', 'hit_5', 'rr')}}


def breakdown(rows: list[dict], key) -> dict:
    """The retrieval summary per group, the group named by `key(row)`."""
    groups: dict = {}
    for row in rows:
        groups.setdefault(key(row), []).append(row)
    return {name: retrieval_summary(group) for name, group in sorted(groups.items(), key=lambda item: str(item[0]))}


def summarise(rows: list[dict]) -> dict:
    scored = [r for r in rows if r['score']['sources_grounded'] is not None]
    partial = [r for r in rows if r['score']['gaps_named'] is not None]
    kept = sum(r['score']['quotes_kept'] for r in rows)
    dropped = sum(r['score']['quotes_dropped'] for r in rows)
    answered = [r for r in rows if r['turn']['behaviour'] in ('answer', 'clarify')]
    return {
        'questions': len(rows),
        'behaviour_correct': sum(r['score']['correct'] for r in rows),
        'misses': [f"{r['id']}: {r['score']['expected']} → {r['score']['got']}" for r in rows if not r['score']['correct']],
        'sources_grounded': sum(r['score']['sources_grounded'] for r in scored), 'scored': len(scored),
        'quote_grounded': sum(bool(r['score']['quote_grounded']) for r in scored),
        'quotes_kept': kept, 'quotes_dropped': dropped,
        'answers_with_a_quote': sum(1 for r in answered if r['turn']['quotes']), 'answers': len(answered),
        'gaps_named': sum(r['score']['gaps_named'] for r in partial), 'partial': len(partial),
        'seconds_median': statistics.median(sum(r['turn']['seconds'].values()) for r in rows),
        'usd': sum(r['turn']['usd'] or 0 for r in rows),
        'retrieval': retrieval_summary(rows),
        'by_style': breakdown(rows, lambda r: r.get('style') or 'not labelled'),
        'by_work': breakdown(rows, lambda r: (r['question_expected'][0]['source'] if r['question_expected'] else 'none')),
    }


def markdown(label: str, summary: dict, rows: list[dict], config: dict, measured: float | None,
             k: int | None = None) -> str:
    s = summary
    lines = [
        f'# Answer measurement `{label}`', '',
        f"Router `{config['router']['model']}` (reasoning {config['router']['reasoning_effort']}), generator "
        f"`{config['generator']['model']}` (reasoning {config['generator']['reasoning_effort']}), embedding "
        f"`{openrouter_client.EMBEDDING_MODEL}`; retrieval as configured (rewrite + step-back, vector search, BM25 on "
        f"the router's keywords, top {k or config['retrieval']['k']}). One run. Cost {s['usd']:.4f} USD by token counts"
        + (f', {measured:.4f} USD measured on the key.' if measured is not None else '.'), '',
        '| Measure | Result |', '|---|---:|',
        f"| behaviour correct (answer, not found, clarify, two declines) | {s['behaviour_correct']} of {s['questions']} |",
        f"| an expected section among the sources given to the model | {s['sources_grounded']} of {s['scored']} |",
        f"| a verified quote from an expected section | {s['quote_grounded']} of {s['scored']} |",
        f"| quotes proposed → kept after the word-for-word check | {s['quotes_kept'] + s['quotes_dropped']} → {s['quotes_kept']} |",
        f"| answers with at least one verified quote | {s['answers_with_a_quote']} of {s['answers']} |",
        f"| partial answers that name what is missing | {s['gaps_named']} of {s['partial']} |",
        f"| latency per turn, median | {s['seconds_median']:.1f} s |",
        *retrieval_lines(s['retrieval']), '',
        *breakdown_lines('By the question\'s style', s['by_style']),
        *breakdown_lines('By the first expected work', s['by_work']),
        'Misses: ' + ('; '.join(s['misses']) or 'none'), '',
        '## Every answer', '',
    ]
    for r in rows:
        t, sc = r['turn'], r['score']
        lines += [f"### {r['id']} · {r['question']}", '',
                  f"Expected **{sc['expected']}** ({r['behaviour']}), got **{t['behaviour']}**"
                  + (f" · relevance {t['relevance']:.3f}{' (below the floor)' if t['below_floor'] else ''}" if t['relevance'] is not None else '')
                  + f" · {sum(t['seconds'].values()):.1f} s", '']
        if t['plan']:
            lines += [f"Router: *{t['plan']['search_query']}* · step-back *{t['plan']['concept_query'] or '—'}* · "
                      f"keywords *{', '.join(t['plan']['keywords']) or '—'}*", '']
        lines += ['> ' + t['answer'].replace('\n', '\n> '), '']
        for q in t['quotes']:
            lines.append(f"- “{q['text']}” — [{q['passage']}] {q['citation']['text']}")
        if t['quotes_dropped']:
            lines.append(f"- ({t['quotes_dropped']} proposed quote(s) dropped: not found word for word in the passage)")
        if t['gaps']:
            lines.append(f"- *Not covered:* {t['gaps']}")
        if t['follow_up']:
            lines.append(f"- *Follow-up question:* {t['follow_up']}")
        if t['retrieved']:
            lines += ['', 'Passages given to the model (✓ = an expected section):', '']
            for src in t['retrieved']:
                mark = '✓' if r['question_expected'] and grounded([src], r['question_expected']) else ' '
                link = f" · {src['citation']['link']}" if src['citation']['link'] else ''
                lines.append(f"{src['number']}. {mark} {src['citation']['text']}{link} · *{src['citation']['licence']}*")
        if t['disclaimer']:
            lines += ['', f"*{t['disclaimer']}*"]
        lines.append('')
    return '\n'.join(lines) + '\n'


def _shown(value: float | None) -> str:
    return '—' if value is None else f'{value:.2f}'


def retrieval_lines(summary: dict) -> list[str]:
    if not summary['questions']:
        return []
    return [f"| an expected section in the first 5 passages (hit@5) | {_shown(summary['section_hit_5'])} |",
            f"| recall@5, section / document | {_shown(summary['section_recall_5'])} / {_shown(summary['document_recall_5'])} |",
            f"| reciprocal rank of the first expected section (MRR) | {_shown(summary['section_rr'])} |"]


def breakdown_lines(title: str, groups: dict) -> list[str]:
    lines = [f'**{title}** (questions with expected sources):', '', '| group | questions | hit@5 | recall@5 | MRR |',
             '|---|---:|---:|---:|---:|']
    for name, s in groups.items():
        if s['questions']:
            lines.append(f"| {name} | {s['questions']} | {_shown(s['section_hit_5'])} | {_shown(s['section_recall_5'])} | "
                         f"{_shown(s['section_rr'])} |")
    return lines + ['']


def compact_turn(turn: dict) -> dict:
    """A turn as the record keeps it: no prompt and no passage text, both rebuilt from the index; each passage once, with its
    citation raw only, since the report renders it; and `sources` as the numbers of the passages shown, which are the retrieved
    ones whenever there is an answer. A record is still re-scored by `score` alone (6 Nov: the baseline's record was 2.6 MB)."""
    return {**{key: value for key, value in turn.items() if key not in ('prompt', 'sources', 'retrieved')},
            'sources': [source['number'] for source in turn.get('sources') or []],
            'retrieved': [{key: value for key, value in passage.items() if key not in ('text', 'citation')}
                          for passage in turn.get('retrieved') or []]}


CONNECTION_RETRIES = 2  # a question asked again after a dropped connection, never after an answer


def with_retries(ask, label: str, pause: float = 20.0):
    """A question's turn, asked again when the connection dropped before any answer came: on 10 Nov two runs were lost to a
    reset by the remote host, one after 25 of 61 questions. Only a connection error is retried; an answer, good or bad, is
    never asked for twice, so the run still measures what the chat does. The chat itself retries nothing (decision 95.a)."""
    import time

    import openai

    for attempt in range(CONNECTION_RETRIES + 1):
        try:
            return ask()
        except (openai.APIConnectionError, OSError) as error:
            if attempt == CONNECTION_RETRIES:
                raise
            print(f'{label}: the connection dropped ({type(error).__name__}); asked again in {pause:.0f} s', flush=True)
            time.sleep(pause)


def usage_or_none() -> float | None:
    """The key's usage before a run, or None where it cannot be read: a reset here stopped a run before its first question
    (10 Nov); the run goes on, and its cost is then not measured."""
    try:
        return openrouter_client.key_usage()
    except OSError as error:
        print(f'measured: the key could not be read before the run ({type(error).__name__}); its cost will not be measured')
        return None


def measured_or_none(usage_before: float | None, estimated: float) -> float | None:
    """The run's cost as the key booked it, or None where the key cannot be read: the results are written either way (a
    connection reset while asking the key's usage took a whole paid run with it on 9 Nov)."""
    if usage_before is None:
        return None
    try:
        return openrouter_client.measured_cost(usage_before, estimated)
    except OSError as error:
        print(f'measured: the key could not be read ({type(error).__name__}); the results are written without it')
        return None


def write(stem: Path, label: str, summary: dict, rows: list[dict], config: dict, measured: float | None,
          k: int | None = None) -> None:
    """The report (.md) and the record (.json). The record leaves out the corpus text the model saw (the
    passages, and the prompt that holds them): it can be rebuilt from the index.
    """
    stem.with_suffix('.md').write_text(markdown(label, summary, rows, config, measured, k), encoding='utf-8',
                                       newline='\n')
    stem.with_suffix('.json').write_text(json.dumps({
        'label': label, 'measured_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'config': config,
        'embedding_model': openrouter_client.EMBEDDING_MODEL, 'summary': summary, 'measured_usd': measured,
        'questions': [{**{k: v for k, v in r.items() if k not in ('turn', 'question_expected')}, 'turn': compact_turn(r['turn'])}
                      for r in rows],
    }, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')


def expected_digests(questions: list[dict], database: Path | None = None) -> dict[str, list[str | None]]:
    """Per question, a sha256 of the indexed text of each expected source, as it stands when a run starts: the chunks that
    satisfy the source at the section level, in chunk order. Two runs whose digests agree searched the same expected text, so a
    question that moved between them moved by the statistics, not the content (phase 6's gates). None where nothing matches."""
    import hashlib
    import sqlite3

    with sqlite3.connect(database or retrieval.DATABASE) as db:
        chunks = [(json.loads(meta), text) for chunk_id, meta, text in
                  db.execute('SELECT id, metadata, text FROM chunks ORDER BY id')]
    digests = {}
    for question in questions:
        found = []
        for expected in question['expected_sources']:
            texts = [text for meta, text in chunks if retrieval_eval.matches(meta, expected, 'section')]
            found.append(hashlib.sha256('\n'.join(texts).encode('utf-8')).hexdigest() if texts else None)
        digests[question['id']] = found
    return digests


def row_of(question: dict, turn: dict, digests: list[str | None] | None = None) -> dict:
    return {'id': question['id'], 'question': question['question'], 'behaviour': question['behaviour'],
            'style': question.get('style'), 'question_expected': question['expected_sources'], 'turn': turn,
            'score': score(question, turn), 'expected_digests': digests}


def frozen_plans_of(record_path: Path) -> Path:
    """The router plans an answer record holds, by question, written beside the results for the server to read: a comparison
    run then searches with exactly the baseline's queries, so a difference is the change's, not the router's (phase 6)."""
    record = json.loads(record_path.read_text(encoding='utf-8'))
    plans = {question['question']: question['turn']['plan'] for question in record['questions'] if question['turn'].get('plan')}
    target = RESULTS / f"plans_{record['label']}.json"
    target.write_text(json.dumps(plans, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    return target


def answer_through_server(question: str, client, generator, config: dict, prices: dict | None) -> dict:
    """One question the chat's way (98.c): the server routes and searches, the chat answers and checks its quotes."""
    return chat_turn.search_turn(question, searcher=lambda asked, hits: client.call('semantic_search', {'question': asked,
                                                                                      'hits': hits}),
                                 generator_chain=generator, config=config, prices=prices)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--label', default='phase6')
    parser.add_argument('--compare-k', type=int, nargs='+',
                        help='answer every routing plan once per k, so that k is the only difference')
    parser.add_argument('--holdout', action='store_true', help='the held-out set: measured once, at the end')
    parser.add_argument('--again', metavar='REASON', help='read the held-out set a second time; the ledger keeps the reason')
    parser.add_argument('--through-server', action='store_true',
                        help='answer the way the chat does, through the search server\'s semantic_search (decision 102.a)')
    parser.add_argument('--frozen-plans', type=Path, metavar='RECORD',
                        help='with --through-server: route every question by the plan an earlier answer record holds for '
                             'it, so the run differs from that one only by the change it measures (phase 6)')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')  # a redirected Windows console is cp1252, and the report has →
    if args.through_server and args.compare_k:
        print('--compare-k routes once and answers per k; through the server each k would route again, so k would not be the '
              'only difference', file=sys.stderr)
        return 2
    if args.frozen_plans and not args.through_server:
        # Found on 8 Nov: without the server the plans were ignored without a word, and two runs routed live while
        # their records claimed the comparison of phase 6's instrument
        print('--frozen-plans applies through the server only: add --through-server (decision 102.a)', file=sys.stderr)
        return 2

    config = app_config.load()
    try:  # before any model is called, so a refused reading costs nothing
        source = retrieval_eval.claim_holdout('answer_eval ' + ' '.join(argv or sys.argv[1:]), args.again) \
            if args.holdout else retrieval_eval.QUESTIONS
    except retrieval_eval.HeldOutSpent as refusal:
        print(refusal, file=sys.stderr)
        return 2
    if args.holdout:
        print('HELD-OUT SET: measured once, at the end. Its results must not steer any change.')
    questions = json.loads(source.read_text(encoding='utf-8'))['questions']
    digests = expected_digests(questions)  # the expected text as this run finds it in the index
    router, generator = chat_turn.default_chains(config)
    prices = chat_models.model_prices([config['router'], config['generator']])
    # The OpenRouter key books a run's cost only when OpenRouter serves both models (287.b); otherwise it is not measured.
    booked = all(chat_models.provider(config[part]) is ChatProvider.OPENROUTER for part in ('router', 'generator'))
    ks = args.compare_k or [config['retrieval']['k']]
    rows = {k: [] for k in ks}
    if args.through_server:
        from backend.chat import mcp_client

        plans = frozen_plans_of(args.frozen_plans) if args.frozen_plans else None
        client = mcp_client.SearchClient(mcp_client.stdio_server(public_only=True, frozen_plans=plans), client_name='evaluation')
        usage_before = usage_or_none() if booked else None
        try:
            for question in questions:
                print(f"{question['id']} ...", flush=True)
                turn = with_retries(lambda: answer_through_server(question['question'], client, generator, config, prices),
                                    question['id'])
                rows[ks[0]].append(row_of(question, turn, digests[question['id']]))
        finally:
            client.close()
    else:
        store = index_store.chroma(retrieval.CHROMA_DIRECTORY, embedding_route.embeddings(),
                                   embedding_route.INDEX_MODEL)
        keyword_index = retrieval.KeywordIndex.from_database()
        usage_before = usage_or_none() if booked else None
        for question in questions:
            print(f"{question['id']} ...", flush=True)
            routed, plan = chat_turn.route_turn(question['question'], router_chain=router, config=config, prices=prices)
            for k in ks:
                turn = routed if plan is None else chat_turn.answer_turn(
                    routed, plan, generator_chain=generator, config=config, store=store, keyword_index=keyword_index,
                    prices=prices, k=k)
                rows[k].append(row_of(question, turn, digests[question['id']]))
    summaries = {k: summarise(rows[k]) for k in ks}
    # The routing cost is counted once per question, not once per k.
    routing = sum(chat_turn._price(config['router']['model'], r['turn']['usage'].get('router', {'input_tokens': 0,
                  'output_tokens': 0}), prices) or 0 for r in rows[ks[0]]) if len(ks) > 1 else 0.0
    estimated = sum(s['usd'] for s in summaries.values()) - routing * (len(ks) - 1)
    measured = measured_or_none(usage_before, estimated)

    # Written before anything is printed: on 2026-10-01 a print to a cp1252 console failed on "→"
    # and took a paid run's results with it.
    RESULTS.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).date().isoformat()
    for k in ks:
        label = f'{args.label}-k{k}' if len(ks) > 1 else args.label
        write(RESULTS / f'answers_{label}_{date}', label, summaries[k], rows[k], config,
              measured if len(ks) == 1 else None, k=k)
        print(f'results: _data/evaluation/results/answers_{label}_{date}.json and .md')
    for k, summary in summaries.items():
        print(f'--- k={k}:', json.dumps({key: v for key, v in summary.items() if key != 'misses'}),
              '\nmisses:', summary['misses'])
    print(f'measured on the key: {measured:.4f} USD' if measured is not None else 'measured: not booked in time')
    return 0


if __name__ == '__main__':
    sys.exit(main())
