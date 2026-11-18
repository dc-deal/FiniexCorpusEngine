"""Measure phase 4: the router's behaviour, and what each query-side technique does to retrieval.

For every router model and every run, each question is routed once. That one plan then feeds
every retrieval configuration, so the configurations differ only in what they switch on:

    plain            the question as asked (phase 3's baseline, re-measured in the same run)
    rewrite          the plan's search query
    rewrite+concept  ... plus the plan's step-back concept query, the two searches fused by RRF
    rewrite+shelf    ... restricted to the plan's shelf ('both' searches everything)
    rewrite+multi    ... plus multi-query versions for broad questions, fused by RRF

Only the chat model (the router) is varied. The embedding model is the same in every
configuration, and query embeddings are cached within the process, so a query text gets the same
vector everywhere: the embedding API returns slightly different vectors for the same text (measured
2026-09-29), and that noise must not show up as a difference between configurations.

Behaviour is scored on all questions, in four classes (decided 2026-09-29, 3.a): answer, clarify,
decline_off_topic, decline_harmful. Whether an answer is partial or 'not found' depends on what the
search finds, which is not the router's to know. Retrieval is scored as in phase 3, with
evaluation.retrieval_eval, on the questions that have expected sources.

The router samples, so every setting runs several times (4.a) and the report gives mean and range.
Next to the JSON results, a Markdown report shows every question with its queries and top 5.

Run from the repository root (spends money; the estimate is printed at the end, then measured):
    python -m backend.evaluation.pipeline_eval --label phase4 --runs 3 --models openai/gpt-5-mini@low openai/gpt-4.1-mini
    python -m backend.evaluation.pipeline_eval --label stepback --configs plain rewrite rewrite+concept
"""

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.embeddings import Embeddings

from backend.configuration import data_paths
from backend.chat import app_config
from backend.evaluation import retrieval_eval
from backend.ingestion import chunking, index_store
from backend.providers import embedding_route, openrouter_client
from backend.search import query_routing, retrieval

ROOT = Path(__file__).resolve().parents[3]
RESULTS = data_paths.RESULTS
K_MAX = 10
TOP = 5  # how many results per question the Markdown report shows

_OFF = {'rewrite': False, 'shelf': False, 'multi': False, 'concept': False, 'bm25': False, 'keywords': False}
CONFIGS = {
    'plain': {**_OFF},
    'plain+bm25': {**_OFF, 'bm25': True},
    'rewrite': {**_OFF, 'rewrite': True},
    'rewrite+concept': {**_OFF, 'rewrite': True, 'concept': True},
    'rewrite+concept+bm25': {**_OFF, 'rewrite': True, 'concept': True, 'bm25': True},
    'rewrite+concept+bm25+shelf': {**_OFF, 'rewrite': True, 'concept': True, 'bm25': True, 'shelf': True},
    'rewrite+concept+bm25kw': {**_OFF, 'rewrite': True, 'concept': True, 'bm25': True, 'keywords': True},
    'rewrite+shelf': {**_OFF, 'rewrite': True, 'shelf': True},
    'rewrite+multi': {**_OFF, 'rewrite': True, 'multi': True},
}

EMBEDS = {
    'plain': 'the question as asked',
    'plain+bm25': 'the question as asked, by vector search and by BM25, fused by RRF',
    'rewrite': "the router's search_query",
    'rewrite+concept': "search_query and the router's step-back concept_query, two searches fused by RRF",
    'rewrite+concept+bm25': 'search_query and concept_query, each by vector search and by BM25: four lists fused by RRF',
    'rewrite+concept+bm25+shelf': '... the same four lists, only on the shelf the router chose',
    'rewrite+concept+bm25kw': "search_query and concept_query by vector search, BM25 on the router's keywords instead of the sentences: three lists fused by RRF",
    'rewrite+shelf': 'search_query, only on the shelf the router chose',
    'rewrite+multi': 'search_query plus multi-query versions for broad questions, fused by RRF',
}

# The coarse classes the router can be judged on; every answer_* behaviour counts as 'answer'.
COARSE = {'clarify': 'clarify', 'decline_off_topic': 'decline_off_topic', 'decline_harmful': 'decline_harmful'}


class CachedEmbeddings(Embeddings):
    """Embeddings that return the same vector for the same text within one process."""

    def __init__(self, inner: Embeddings):
        self.inner = inner
        self.cache: dict[str, list[float]] = {}

    @property
    def model(self) -> str | None:
        """The wrapped model's name, so the index check sees through the cache."""
        return getattr(self.inner, 'model', None)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        missing = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if missing:
            self.cache.update(zip(missing, self.inner.embed_documents(missing)))
        return [self.cache[t] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def expected_class(behaviour: str) -> str:
    return COARSE.get(behaviour, 'answer')


def score_behaviour(questions: list[dict], plans: dict[str, dict]) -> dict:
    """Behaviour accuracy over all questions, the misses, and how well is_broad finds broad questions."""
    misses = []
    for q in questions:
        got = query_routing.behaviour(plans[q['id']]['plan'])
        if got != expected_class(q['behaviour']):
            misses.append(f"{q['id']}: {expected_class(q['behaviour'])} → {got}")
    answering = [q for q in questions if expected_class(q['behaviour']) == 'answer']
    broad = [q for q in answering if q['behaviour'] == 'answer_broad']
    flagged = [q for q in answering if plans[q['id']]['plan'].is_broad]
    return {
        'correct': len(questions) - len(misses), 'of': len(questions), 'misses': misses,
        'broad_found': sum(1 for q in broad if q in flagged), 'broad_expected': len(broad),
        'broad_false': sum(1 for q in flagged if q not in broad),
        'fell_back': sum(1 for p in plans.values() if p['fell_back']),
    }


def run_configs(questions: list[dict], plans: dict[str, dict], versions: dict[str, list[str]], store,
                names: list[str], keyword_index=None) -> dict:
    """Retrieval results and phase 3 metrics for the chosen configurations, from one set of plans."""
    by_text = {q['question']: q for q in questions}
    out = {}
    for name in names:
        switches = CONFIGS[name]

        def search(text, k, switches=switches):
            question = by_text[text]
            if not switches['rewrite']:
                if switches['bm25']:
                    return retrieval.hybrid_retrieve([text], k=k, store=store, keyword_index=keyword_index)
                return retrieval.retrieve(text, k=k, store=store)
            plan = plans[question['id']]['plan']
            extra = versions.get(question['id']) if switches['multi'] and plan.is_broad else None
            return query_routing.search(plan, k=k, use_shelf_filter=switches['shelf'], extra_queries=extra,
                                        use_concept_query=switches['concept'], use_keyword_search=switches['bm25'],
                                        bm25_on_keywords=switches['keywords'], store=store,
                                        keyword_index=keyword_index)
        per_question = retrieval_eval.evaluate(questions, K_MAX, search=search)
        out[name] = {'summary': retrieval_eval.summarise(per_question), 'per_question': per_question}
    return out


def floor_signals(questions: list[dict], plans: dict[str, dict], store, keyword_index) -> dict:
    """What a relevance floor could look at, for every question that reaches the search (4.a).

    Measured before a floor is set: the best cosine similarity of the vector search for the router's
    search_query and for its concept_query, the best BM25 score, and the best similarity of the
    question as asked. Questions without expected sources are included, q24 above all: a floor is
    only possible if covered questions and the question the corpus cannot answer separate.
    """
    signals = {}
    for q in questions:
        plan = plans[q['id']]['plan']
        if plan.route != 'search':
            continue
        best = lambda query: max((r['similarity'] for r in retrieval.retrieve(query, k=1, store=store)), default=None)
        keyword = keyword_index.search(plan.search_query, k=1) if keyword_index is not None else []
        signals[q['id']] = {
            'plain': best(q['question']),
            'search_query': best(plan.search_query),
            'concept_query': best(plan.concept_query) if (plan.concept_query or '').strip() else None,
            'bm25': keyword[0]['bm25'] if keyword else 0.0,
        }
    return signals


def headline(summary: dict) -> dict:
    """The numbers the report compares, from a retrieval_eval summary."""
    return {
        'section_hit5': summary['section']['5']['hits'], 'section_recall5': summary['section']['5']['recall'],
        'section_precision5': summary['section']['5']['precision'], 'section_mrr': summary['section']['mrr'],
        'document_hit5': summary['document']['5']['hits'], 'section_recall10': summary['section']['10']['recall'],
    }


def spread(values: list[float]) -> dict:
    return {'mean': statistics.fmean(values), 'min': min(values), 'max': max(values)}


def aggregate(runs: list[dict], names: list[str]) -> dict:
    """Mean and range over runs: behaviour, broad detection, latency, and each configuration's headline."""
    configs = {}
    for name in names:
        numbers = [headline(run['configs'][name]['summary']) for run in runs]
        configs[name] = {key: spread([n[key] for n in numbers]) for key in numbers[0]}
    seconds = [p['seconds'] for run in runs for p in run['plans'].values()]
    return {
        'behaviour_correct': spread([run['behaviour']['correct'] for run in runs]),
        'broad_found': spread([run['behaviour']['broad_found'] for run in runs]),
        'broad_false': spread([run['behaviour']['broad_false'] for run in runs]),
        'fell_back': sum(run['behaviour']['fell_back'] for run in runs),
        'router_seconds_median': statistics.median(seconds),
        'router_seconds_max': max(seconds),
        'configs': configs,
    }


def parse_model(spec: str) -> tuple[str, str | None]:
    """'openai/gpt-5-mini@low' → ('openai/gpt-5-mini', 'low'); no '@' means no reasoning."""
    model, _, effort = spec.partition('@')
    return model, effort or None


def usd(tokens_in: int, tokens_out: int, price: dict) -> float:
    return (tokens_in * price['input'] + tokens_out * price['output']) / 1e6


def fmt(value: dict, digits: int = 2) -> str:
    """mean (min–max), or just the value when the runs agree."""
    if abs(value['max'] - value['min']) < 1e-9:
        return f"{value['mean']:.{digits}f}"
    return f"{value['mean']:.{digits}f} ({value['min']:.{digits}f}–{value['max']:.{digits}f})"


def print_report(models: dict, questions_scored: int, questions_total: int) -> None:
    for spec, result in models.items():
        agg = result['aggregate']
        print(f"\n=== router {spec}  ({len(result['runs'])} runs; "
              f"embedding {openrouter_client.EMBEDDING_MODEL} in every configuration)")
        print(f"behaviour correct: {fmt(agg['behaviour_correct'], 1)} of {questions_total}   "
              f"broad found: {fmt(agg['broad_found'], 1)} of {result['runs'][0]['behaviour']['broad_expected']}, "
              f"falsely broad: {fmt(agg['broad_false'], 1)}   router fell back: {agg['fell_back']}   "
              f"router latency median {agg['router_seconds_median']:.2f} s, max {agg['router_seconds_max']:.2f} s")
        for run in result['runs']:
            print(f"   run {run['run']}: misses {', '.join(run['behaviour']['misses']) or '–'}")
        print(f"   {'config':16} {'sec hit@5':>18} {'sec recall@5':>20} {'sec prec@5':>20} {'sec MRR':>20} {'doc hit@5':>18}")
        for name, c in agg['configs'].items():
            print(f"   {name:16} {fmt(c['section_hit5'], 1):>18} {fmt(c['section_recall5']):>20} "
                  f"{fmt(c['section_precision5']):>20} {fmt(c['section_mrr']):>20} {fmt(c['document_hit5'], 1):>18}")
        print(f"   (hit counts are of {questions_scored} questions with expected sources)")


def _cell(judged: dict | None) -> str:
    """One result as a table cell: similarity, mark (✓ section hit, ~ right document, ✗ neither), where.

    A chunk that only BM25 found has no similarity; the cell says so instead of inventing one.
    """
    if judged is None:
        return ''
    mark = '✓' if judged['matched']['section'] else '~' if judged['matched']['document'] else '✗'
    score = f"{judged['similarity']:.3f}" if judged['similarity'] is not None else 'BM25 only'
    return f"{score} {mark} {retrieval_eval.describe(judged['citation'])}".replace('|', '/')


def markdown_report(label: str, models: dict, questions: list[dict], names: list[str], cost: dict) -> str:
    """Every question with the queries that were embedded and the top results, for reading.

    Aggregates hide which question moved and why; this shows it. Retrieval tables are from run 1 of
    each router; the hit patterns cover all runs.
    """
    specs = list(models)
    short = {spec: spec.split('/')[-1] for spec in specs}
    runs_n = len(models[specs[0]]['runs'])
    lines = [
        f'# Pipeline measurement `{label}`',
        '',
        f"Router (chat) models, varied: {', '.join(f'`{s}`' for s in specs)}. Embedding model, the same in "
        f'every configuration: `{openrouter_client.EMBEDDING_MODEL}`. {runs_n} runs per router. '
        f"Cost: {cost['estimated']:.4f} USD estimated, "
        + (f"{cost['measured']:.4f} USD measured on the key." if cost['measured'] is not None else 'not measured.'),
        '',
        'What each configuration embeds and searches:',
        '',
        *[f'- **{name}**: {EMBEDS[name]}' for name in names],
        '',
        '## Summary (section level unless noted; mean over runs, range in brackets)',
        '',
        '| Router | Configuration | hit@5 | recall@5 | precision@5 | MRR | document hit@5 |',
        '|---|---|---:|---:|---:|---:|---:|',
    ]
    scored = sum(1 for q in questions if q['expected_sources'])
    for spec in specs:
        for name, c in models[spec]['aggregate']['configs'].items():
            lines.append(f"| {short[spec]} | {name} | {fmt(c['section_hit5'], 1)}/{scored} | {fmt(c['section_recall5'])} | "
                         f"{fmt(c['section_precision5'])} | {fmt(c['section_mrr'])} | {fmt(c['document_hit5'], 1)}/{scored} |")
    lines += ['', '## Behaviour', '',
              '| Router | correct | broad found | falsely broad | router latency, median (max) |',
              '|---|---:|---:|---:|---:|']
    for spec in specs:
        a = models[spec]['aggregate']
        lines.append(f"| {short[spec]} | {fmt(a['behaviour_correct'], 1)} of {len(questions)} | "
                     f"{fmt(a['broad_found'], 1)} of {models[spec]['runs'][0]['behaviour']['broad_expected']} | "
                     f"{fmt(a['broad_false'], 1)} | {a['router_seconds_median']:.1f} s ({a['router_seconds_max']:.1f} s) |")
    lines += ['', '| Question | Expected | ' + ' | '.join(f'{short[s]}, runs 1–{runs_n}' for s in specs) + ' |',
              '|---|---|' + '---|' * len(specs)]
    for q in questions:
        got = [', '.join(query_routing.behaviour(r['plans'][q['id']]['plan']) for r in models[s]['runs']) for s in specs]
        lines.append(f"| {q['id']} {q['question']} | {expected_class(q['behaviour'])} | " + ' | '.join(got) + ' |')

    lines += ['', '## What a relevance floor could look at (mean over runs, first router)', '',
              'The best cosine similarity of a vector search, and the best BM25 score, for every question '
              'that reached the search. A floor can only be set if the questions the corpus covers and the '
              'ones it cannot answer (answer_not_found) separate.', '',
              '| Question | Expected | as asked | search_query | concept_query | BM25 (search_query) |',
              '|---|---|---:|---:|---:|---:|']
    first = models[specs[0]]['runs']
    for q in sorted(questions, key=lambda q: (q['behaviour'] != 'answer_not_found', q['id'])):
        values = [r['floor'][q['id']] for r in first if q['id'] in r.get('floor', {})]
        if not values:
            continue
        mean = lambda key: (statistics.fmean(v[key] for v in values if v[key] is not None)
                            if any(v[key] is not None for v in values) else None)
        show = lambda x, digits=3: f'{x:.{digits}f}' if x is not None else '—'
        lines.append(f"| {q['id']} {q['question']} | {q['behaviour']} | {show(mean('plain'))} | "
                     f"{show(mean('search_query'))} | {show(mean('concept_query'))} | {show(mean('bm25'), 1)} |")
    lines += ['', '## Retrieval per question', '',
              '✓ an expected section · ~ the expected document, another section · ✗ neither. '
              f'The hit pattern shows section hit@5 per run; the tables show run 1, top {TOP}. Where a '
              'configuration fuses several searches, the order is the fused rank (RRF) and the number is the '
              "chunk's best similarity, so the numbers need not fall from row to row."]
    columns = [('plain', specs[0])] + [(name, spec) for spec in specs for name in names if name != 'plain']
    for q in questions:
        if not q['expected_sources']:
            continue
        lines += ['', f"### {q['id']} · {q['question']}", '',
                  'Expected: ' + '; '.join(retrieval_eval.describe_expected(e) for e in q['expected_sources']), '']
        lines += ['| Router | ' + ' | '.join(names) + ' |', '|---|' + '---|' * len(names)]
        for spec in specs:
            cells = []
            for name in names:
                entries = [next(e for e in r['configs'][name]['per_question'] if e['id'] == q['id'])
                           for r in models[spec]['runs']]
                pattern = ''.join('✓' if e['metrics']['section']['at_k'][5]['hit'] else '✗' for e in entries)
                recall = statistics.fmean(e['metrics']['section']['at_k'][5]['recall'] for e in entries)
                cells.append(f'{pattern} recall@5 {recall:.2f}')
            lines.append(f'| {short[spec]} | ' + ' | '.join(cells) + ' |')
        lines.append('')
        for spec in specs:
            plan = models[spec]['runs'][0]['plans'][q['id']]['plan']
            lines.append(f"- **{short[spec]}**, run 1: route `{plan.route}`, search_query *\"{plan.search_query}\"*, "
                         f"concept_query *\"{plan.concept_query or '—'}\"*, keywords *{', '.join(plan.keywords) or '—'}*")
        judged = {(name, spec): next(e for e in models[spec]['runs'][0]['configs'][name]['per_question']
                                     if e['id'] == q['id'])['judged'] for name, spec in columns}
        lines += ['', '| # | ' + ' | '.join(name if name == 'plain' else f'{short[spec]} {name}' for name, spec in columns) + ' |',
                  '|---|' + '---|' * len(columns)]
        for rank in range(TOP):
            lines.append(f'| {rank + 1} | ' + ' | '.join(
                _cell(judged[key][rank] if rank < len(judged[key]) else None) for key in columns) + ' |')
    return '\n'.join(lines) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--label', default='phase4')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--models', nargs='+', help="model ids, '@effort' for reasoning; default: the configured router")
    parser.add_argument('--configs', nargs='+', choices=list(CONFIGS), default=list(CONFIGS),
                        help='which retrieval configurations to measure (default: all)')
    parser.add_argument('--holdout', action='store_true', help='the held-out set: measured once, at the end')
    parser.add_argument('--again', metavar='REASON', help='read the held-out set a second time; the ledger keeps the reason')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')  # a redirected Windows console is cp1252
    names = [name for name in CONFIGS if name in args.configs]
    try:  # before any model is called, so a refused reading costs nothing
        holdout = retrieval_eval.claim_holdout('pipeline_eval ' + ' '.join(argv or sys.argv[1:]), args.again) if args.holdout else None
    except retrieval_eval.HeldOutSpent as refusal:
        print(refusal, file=sys.stderr)
        return 2

    config = app_config.load()
    router_config = config['router']
    specs = args.models or [router_config['model'] + (f"@{router_config['reasoning_effort']}"
                                                       if router_config['reasoning_effort'] else '')]
    source = holdout or retrieval_eval.QUESTIONS
    if args.holdout:
        print('HELD-OUT SET: measured once, at the end. Its results must not steer any change.')
    questions = json.loads(source.read_text(encoding='utf-8'))['questions']
    versions_wanted = config['multi_query']['versions']
    expand = any(CONFIGS[name]['multi'] for name in names)
    prices = openrouter_client.model_prices([parse_model(s)[0] for s in specs])
    missing_prices = [s for s in specs if parse_model(s)[0] not in prices]
    if missing_prices:
        print(f'not listed on OpenRouter: {missing_prices}', file=sys.stderr)
        return 2

    cached = CachedEmbeddings(embedding_route.embeddings())
    store = index_store.chroma(retrieval.CHROMA_DIRECTORY, cached, embedding_route.INDEX_MODEL)
    keyword_index = retrieval.KeywordIndex.from_database() if any(CONFIGS[n]['bm25'] for n in names) else None
    usage_before = openrouter_client.key_usage()
    models = {}
    for spec in specs:
        model, effort = parse_model(spec)
        llm = openrouter_client.chat_model(model, reasoning_effort=effort, max_tokens=router_config['max_tokens'])
        route_chain, expand_chain = query_routing.router(llm), query_routing.expander(llm)
        runs = []
        for run in range(1, args.runs + 1):
            print(f'{spec}, run {run}: routing {len(questions)} questions ...', flush=True)
            plans = {q['id']: query_routing.plan_query(route_chain, q['question']) for q in questions}
            versions, expansions = {}, {}
            for qid, planned in plans.items():
                plan = planned['plan']
                if expand and plan.route == 'search' and plan.is_broad:
                    expansions[qid] = query_routing.expand_query(expand_chain, plan.search_query, versions_wanted)
                    versions[qid] = expansions[qid]['queries']
            calls = list(plans.values()) + list(expansions.values())
            tokens_in = sum(c['input_tokens'] for c in calls)
            tokens_out = sum(c['output_tokens'] for c in calls)
            runs.append({
                'run': run, 'plans': plans, 'expansions': expansions,
                'behaviour': score_behaviour(questions, plans),
                'configs': run_configs(questions, plans, versions, store, names, keyword_index),
                'floor': floor_signals(questions, plans, store, keyword_index),
                'tokens': {'input': tokens_in, 'output': tokens_out,
                           'reasoning': sum(c['reasoning_tokens'] for c in calls)},
                'estimated_usd': usd(tokens_in, tokens_out, prices[model]),
            })
        models[spec] = {'model': model, 'reasoning_effort': effort, 'price_per_million': prices[model],
                        'runs': runs, 'aggregate': aggregate(runs, names)}

    scored = sum(1 for q in questions if q['expected_sources'])
    print_report(models, scored, len(questions))
    embedded = list(cached.cache)
    embedding_usd = (sum(chunking.count_tokens(t) for t in embedded)
                     * openrouter_client.EMBEDDING_USD_PER_MILLION_TOKENS / 1e6)
    estimated = sum(r['estimated_usd'] for m in models.values() for r in m['runs']) + embedding_usd
    print(f'\nestimated cost: {estimated:.4f} USD (chat by token counts and current prices, '
          f'{len(embedded)} query embeddings); waiting for the booking ...', flush=True)
    measured = openrouter_client.measured_cost(usage_before, estimated)
    print(f"measured on the key: {measured:.4f} USD" if measured is not None else 'measured: not booked in time')

    now = datetime.now(timezone.utc)
    RESULTS.mkdir(parents=True, exist_ok=True)
    stem = f'pipeline_{args.label}_{now.date().isoformat()}'
    (RESULTS / f'{stem}.md').write_text(
        markdown_report(args.label, models, questions, names, {'estimated': estimated, 'measured': measured}),
        encoding='utf-8', newline='\n')
    (RESULTS / f'{stem}.json').write_text(json.dumps({
        'label': args.label, 'measured_at': now.isoformat(timespec='seconds'),
        'questions_file': source.name, 'k_max': K_MAX, 'configs': names,
        'embedding_model': openrouter_client.EMBEDDING_MODEL,
        'multi_query_versions': versions_wanted, 'estimated_usd': estimated, 'measured_usd': measured,
        'models': {spec: {
            **{k: v for k, v in m.items() if k != 'runs'},
            'runs': [{
                'run': r['run'], 'behaviour': r['behaviour'], 'tokens': r['tokens'],
                'estimated_usd': r['estimated_usd'],
                'plans': {qid: {**{k: v for k, v in p.items() if k != 'plan'}, 'plan': p['plan'].model_dump()}
                          for qid, p in r['plans'].items()},
                'expansions': r['expansions'], 'floor': r['floor'],
                'configs': {name: {
                    'summary': c['summary'],
                    'questions': {e['id']: {'metrics': e['metrics'],
                                            'results': [[j['chunk_id'], j['similarity'], j['matched']['section']]
                                                        for j in e['judged']]}
                                  for e in c['per_question']},
                } for name, c in r['configs'].items()},
            } for r in m['runs']],
        } for spec, m in models.items()},
    }, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    print(f'results: {(RESULTS / stem).relative_to(ROOT)}.json and .md')
    return 0


if __name__ == '__main__':
    sys.exit(main())
