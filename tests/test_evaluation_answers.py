from backend.evaluation import answer_eval

KELLY = {'source_id': 'wikipedia_trading_set', 'url': 'https://x/w/index.php?title=Kelly_criterion&oldid=1',
         'anchor': None, 'section': 'Kelly criterion'}
OTHER = {'source_id': 'google_site_reliability_engineering', 'url': 'https://sre.google/x#y', 'anchor': 'y'}
EXPECTED = [{'source': 'wikipedia_trading_set', 'article': 'Kelly_criterion', 'anchor': None}]


def turn(**overrides):
    fields = {'behaviour': 'answer', 'quotes': [{'passage': 2, 'text': 't'}], 'quotes_dropped': 1, 'gaps': None,
              'retrieved': [{'metadata': OTHER}, {'metadata': KELLY}], 'seconds': {'route': 1.0}, 'usd': 0.002}
    return {**fields, **overrides}


def test_every_answer_behaviour_but_not_found_expects_an_answer():
    assert answer_eval.expected_outcome('answer_partial') == 'answer'
    assert answer_eval.expected_outcome('answer_not_found') == 'not_found'
    assert answer_eval.expected_outcome('decline_harmful') == 'decline_harmful'


def test_a_turn_is_grounded_when_a_source_and_a_quote_come_from_an_expected_section():
    scored = answer_eval.score({'behaviour': 'answer_direct', 'expected_sources': EXPECTED}, turn())
    assert scored['correct'] and scored['sources_grounded'] and scored['quote_grounded']
    assert (scored['quotes_kept'], scored['quotes_dropped']) == (1, 1)


def test_a_quote_from_another_source_is_not_grounded():
    scored = answer_eval.score({'behaviour': 'answer_direct', 'expected_sources': EXPECTED},
                               turn(quotes=[{'passage': 1, 'text': 't'}]))
    assert scored['sources_grounded'] and not scored['quote_grounded']


def test_retrieval_is_scored_from_the_passages_the_model_was_given_in_their_order():
    # Decision 102.a: through the chat, retrieval is what reached the model; here the expected article comes second.
    scores = answer_eval.retrieval_scores(turn(), EXPECTED)
    assert scores['section'] == {'recall_5': 1.0, 'hit_5': 1, 'rr': 0.5} and scores['document']['rr'] == 0.5
    assert answer_eval.retrieval_scores(turn(), []) is None  # a decline or a not-found question has nothing to retrieve


def test_the_summary_breaks_retrieval_down_by_style_and_by_the_expected_work():
    rows = [answer_eval.row_of({'id': 'a', 'question': 'kelly?', 'behaviour': 'answer_direct', 'style': 'keywords',
                                'expected_sources': EXPECTED}, turn()),
            answer_eval.row_of({'id': 'b', 'question': 'pizza?', 'behaviour': 'decline_off_topic', 'expected_sources': []},
                               turn(behaviour='decline_off_topic', quotes=[], retrieved=[]))]
    summary = answer_eval.summarise(rows)
    assert summary['retrieval'] == {'questions': 1, 'document_recall_5': 1.0, 'document_hit_5': 1.0, 'document_rr': 0.5,
                                    'section_recall_5': 1.0, 'section_hit_5': 1.0, 'section_rr': 0.5}
    assert summary['by_style']['keywords']['questions'] == 1 and summary['by_style']['not labelled']['questions'] == 0
    assert summary['by_work']['wikipedia_trading_set']['section_rr'] == 0.5
    lines = answer_eval.breakdown_lines('By style', summary['by_style'])
    assert '| keywords | 1 | 1.00 | 1.00 | 0.50 |' in lines and not any(line.startswith('| not labelled') for line in lines)


def test_a_question_answered_through_the_server_takes_the_chats_path():
    from backend.chat import app_config
    from test_chat_turn import answer, chain, plan, server_searcher

    class Client:  # the chat's MCP session, as the evaluation calls it
        def __init__(self):
            self.searcher, self.calls = server_searcher(plan()), []

        def call(self, name, arguments):
            self.calls.append(name)
            return self.searcher(arguments['question'], arguments['hits'])

    client = Client()
    answered = answer_eval.answer_through_server('show me how a sharpe works', client, chain(answer()), app_config.load(), None)
    assert client.calls == ['semantic_search'] and answered['retrieval'] == 'mcp semantic_search'
    assert answered['behaviour'] == 'answer' and answered['quotes']


def test_the_compact_record_keeps_each_passage_once_and_scores_the_same():
    full = turn(retrieved=[{'number': 1, 'chunk_id': 'c1', 'metadata': OTHER, 'citation': {'text': 'SRE'}, 'text': 'passage'},
                           {'number': 2, 'chunk_id': 'c2', 'metadata': KELLY, 'citation': {'text': 'Kelly'}, 'text': 'passage'}],
                prompt='the prompt with every passage')
    full['sources'] = full['retrieved']
    compact = answer_eval.compact_turn(full)
    assert compact['sources'] == [1, 2] and 'prompt' not in compact
    assert all('text' not in passage and 'citation' not in passage for passage in compact['retrieved'])
    question = {'behaviour': 'answer_direct', 'expected_sources': EXPECTED}
    assert answer_eval.score(question, compact) == answer_eval.score(question, full)


def test_a_question_s_expected_text_is_digested_as_the_index_holds_it(tmp_path):
    # Phase 6's gates: two runs whose digests agree searched the same expected text.
    import sqlite3

    database = tmp_path / 'knowledge.sqlite3'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE chunks (id TEXT PRIMARY KEY, source_id TEXT, section_id TEXT, text TEXT, metadata TEXT)')
        db.executemany('INSERT INTO chunks VALUES (?, ?, ?, ?, ?)', [
            ('w:0001:000', 'wikipedia_trading_set', 'w:0001', 'Kelly text one', __import__('json').dumps(KELLY)),
            ('w:0001:001', 'wikipedia_trading_set', 'w:0001', 'Kelly text two', __import__('json').dumps(KELLY)),
            ('s:0001:000', 'google_site_reliability_engineering', 's:0001', 'SRE text', __import__('json').dumps(OTHER))])
    questions = [{'id': 'a', 'expected_sources': EXPECTED}, {'id': 'b', 'expected_sources': [{'source': 'nothing', 'section': 'x'}]}]
    digests = answer_eval.expected_digests(questions, database)
    assert len(digests['a'][0]) == 64 and digests['b'] == [None]
    with sqlite3.connect(database) as db:
        db.execute("UPDATE chunks SET text = 'Kelly text, changed' WHERE id = 'w:0001:001'")
    assert answer_eval.expected_digests(questions, database)['a'] != digests['a']


def test_comparing_k_through_the_server_is_refused_before_anything_is_spent():
    assert answer_eval.main(['--through-server', '--compare-k', '5', '10']) == 2


def test_frozen_plans_without_the_server_are_refused_before_anything_is_spent(tmp_path):
    # without the server the plans were ignored without a word (8 Nov), and the run routed live
    assert answer_eval.main(['--frozen-plans', str(tmp_path / 'record.json')]) == 2


def test_a_partial_answer_is_checked_for_naming_its_gaps_and_a_decline_for_nothing_else():
    assert answer_eval.score({'behaviour': 'answer_partial', 'expected_sources': EXPECTED},
                             turn(gaps='booking is not covered'))['gaps_named'] is True
    declined = answer_eval.score({'behaviour': 'decline_off_topic', 'expected_sources': []},
                                 turn(behaviour='decline_off_topic', quotes=[], retrieved=[]))
    assert declined['correct'] and declined['sources_grounded'] is None and declined['gaps_named'] is None


def test_a_key_that_cannot_be_read_at_the_end_never_takes_the_paid_run_s_results_with_it(monkeypatch):
    import urllib.error

    from backend.providers import openrouter_client

    def reset(usage_before, estimated):
        raise urllib.error.URLError('connection reset by the remote host')

    monkeypatch.setattr(openrouter_client, 'measured_cost', reset)
    assert answer_eval.measured_or_none(1.0, 0.1) is None
    monkeypatch.setattr(openrouter_client, 'measured_cost', lambda usage_before, estimated: 0.12)
    assert answer_eval.measured_or_none(1.0, 0.1) == 0.12


def test_a_dropped_connection_asks_the_question_again_and_nothing_else_does():
    import httpx
    import openai
    import pytest

    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise openai.APIConnectionError(request=httpx.Request('POST', 'https://openrouter.ai/api/v1/chat/completions'))
        return {'answer': 'ok'}

    assert answer_eval.with_retries(flaky, 'q01', pause=0) == {'answer': 'ok'} and len(calls) == 2

    def wrong():
        calls.append(1)
        raise ValueError('a bad answer is an answer: never asked again')

    calls.clear()
    with pytest.raises(ValueError):
        answer_eval.with_retries(wrong, 'q02', pause=0)
    assert len(calls) == 1


def test_a_key_that_cannot_be_read_before_the_run_does_not_stop_it(monkeypatch):
    import urllib.error

    from backend.providers import openrouter_client

    def reset():
        raise urllib.error.URLError('connection reset by the remote host')

    monkeypatch.setattr(openrouter_client, 'key_usage', reset)
    assert answer_eval.usage_or_none() is None
    assert answer_eval.measured_or_none(None, 0.1) is None  # no reading before, so no measured cost after
