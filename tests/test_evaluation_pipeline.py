from backend.evaluation import pipeline_eval
from backend.search.query_routing import QueryPlan


def plan(**overrides) -> dict:
    fields = {'route': 'search', 'needs_clarification': False, 'shelf': 'both', 'search_query': 'q', 'concept_query': None, 'keywords': [],
              'is_broad': False}
    return {'plan': QueryPlan(**{**fields, **overrides}), 'fell_back': False, 'seconds': 1.0}


QUESTIONS = [
    {'id': 'a', 'behaviour': 'answer_direct'},
    {'id': 'b', 'behaviour': 'answer_broad'},
    {'id': 'c', 'behaviour': 'clarify'},
    {'id': 'd', 'behaviour': 'decline_harmful'},
    {'id': 'e', 'behaviour': 'answer_not_found'},
]


def test_every_answer_behaviour_is_one_coarse_class():
    assert {pipeline_eval.expected_class(b) for b in
            ('answer_direct', 'answer_broad', 'answer_general', 'answer_partial', 'answer_not_found')} == {'answer'}
    assert pipeline_eval.expected_class('decline_harmful') == 'decline_harmful'


def test_behaviour_is_scored_on_coarse_classes_and_broad_separately():
    plans = {'a': plan(is_broad=True), 'b': plan(is_broad=True), 'c': plan(needs_clarification=True),
             'd': plan(route='off_topic'), 'e': plan()}
    scored = pipeline_eval.score_behaviour(QUESTIONS, plans)
    assert scored['correct'] == 4 and scored['misses'] == ['d: decline_harmful → decline_off_topic']
    assert (scored['broad_found'], scored['broad_expected'], scored['broad_false']) == (1, 1, 1)


def test_the_cache_gives_one_vector_per_text_and_asks_once():
    class Counting:
        calls = []

        def embed_documents(self, texts):
            self.calls.append(list(texts))
            return [[float(len(t))] for t in texts]

    inner = Counting()
    cached = pipeline_eval.CachedEmbeddings(inner)
    assert cached.embed_query('ab') == cached.embed_documents(['ab', 'abc'])[0] == [2.0]
    assert inner.calls == [['ab'], ['abc']]


def test_a_model_spec_carries_its_reasoning_effort():
    assert pipeline_eval.parse_model('openai/gpt-5-mini@low') == ('openai/gpt-5-mini', 'low')
    assert pipeline_eval.parse_model('openai/gpt-4.1-mini') == ('openai/gpt-4.1-mini', None)


def test_the_report_shows_each_question_with_its_queries_and_results():
    citation = {'source_id': 'wikipedia_trading_set', 'url': 'https://x/w/index.php?title=Kelly_criterion&oldid=1',
                'anchor': None, 'source_title': 'Wikipedia'}
    judged = [{'rank': 1, 'chunk_id': 'c', 'similarity': 0.66, 'citation': citation,
               'matched': {'document': [0], 'section': [0]}}]
    metrics = {'section': {'at_k': {5: {'hit': 1, 'recall': 1.0}}}}
    entry = {'id': 'q1', 'judged': judged, 'metrics': metrics}
    run = {'plans': {'q1': plan(search_query='position sizing with the Kelly criterion',
                                concept_query='what is the Kelly criterion')},
           'configs': {name: {'per_question': [entry]} for name in ('plain', 'rewrite')},
           'behaviour': {'broad_expected': 0}}
    spread = pipeline_eval.spread([1.0])
    models = {'openai/gpt-5-mini@low': {'runs': [run], 'aggregate': {
        'configs': {name: {k: spread for k in ('section_hit5', 'section_recall5', 'section_precision5',
                                               'section_mrr', 'document_hit5')} for name in ('plain', 'rewrite')},
        'behaviour_correct': spread, 'broad_found': spread, 'broad_false': spread,
        'router_seconds_median': 1.0, 'router_seconds_max': 1.0}}}
    questions = [{'id': 'q1', 'question': 'how big should my position be?', 'behaviour': 'answer_direct',
                  'expected_sources': [{'source': 'wikipedia_trading_set', 'article': 'Kelly_criterion', 'anchor': None}]}]
    report = pipeline_eval.markdown_report('t', models, questions, ['plain', 'rewrite'],
                                           {'estimated': 0.01, 'measured': None})
    assert '### q1 · how big should my position be?' in report
    assert 'what is the Kelly criterion' in report and '0.660 ✓ Kelly criterion' in report
    assert 'text-embedding-3-small' in report  # the embedding model is named, not confused with the router


def test_runs_that_agree_print_one_number_and_runs_that_differ_a_range():
    assert pipeline_eval.fmt(pipeline_eval.spread([0.25, 0.25])) == '0.25'
    assert pipeline_eval.fmt(pipeline_eval.spread([0.2, 0.3])) == '0.25 (0.20–0.30)'
