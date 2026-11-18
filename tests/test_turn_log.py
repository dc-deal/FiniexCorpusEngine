import json

import pytest

from backend.chat import turn_log

PLAN = {'route': 'search', 'search_query': 'Sharpe ratio definition', 'concept_query': None, 'keywords': ['Sharpe']}


def knowledge(**turn_overrides) -> dict:
    turn = {'behaviour': 'answer', 'plan': PLAN, 'prompt': 'Question: …', 'relevance': 0.66,
            'relevance_floor': 0.495, 'below_floor': False, 'quotes': [{'passage': 1, 'text': 'q'}],
            'quotes_dropped': 0, 'disclaimer': 'Not trading advice.'}
    return {'kind': 'knowledge', 'question': 'what is a sharpe ratio', 'turn': {**turn, **turn_overrides},
            'tool_calls': [{'name': 'search_knowledge_base', 'args': {}, 'result': {'status': 'success'}}]}


def calculation(*statuses) -> dict:
    calls = [{'name': 'position_size', 'args': {}, 'result': {'status': s, 'content': 'risk_percent must be > 0'}}
             for s in statuses]
    return {'kind': 'calculation', 'question': 'kelly?', 'turn': None, 'tool_calls': calls,
            'disclaimer': 'Not trading advice.'}


def outcomes(result: dict) -> dict:
    return {c['check']: c['status'] for c in turn_log.security_checks(result)}


PATHS = {
    'invalid': {'kind': 'invalid', 'question': '', 'text': 'Please type a question.', 'tool_calls': []},
    'answer': knowledge(),
    'declined': knowledge(behaviour='decline_harmful', plan=None, prompt=None, disclaimer=None),
    'not found': knowledge(behaviour='not_found', quotes=[], quotes_dropped=2, disclaimer=None),
    'calculation': calculation('success'),
    'section': {'kind': 'section', 'question': 'open source 1', 'turn': None,  # a turn logged before 98.c
                'tool_calls': [{'name': 'open_section', 'args': {}, 'result': {'status': 'success'}}]},
    'server': {'kind': 'server', 'question': 'open page 19 of the accounting book', 'turn': None, 'model_calls': 1,
               'tool_calls': [{'name': 'open_page', 'args': {'work': 'acc', 'page': '19'},
                               'result': {'status': 'success', 'artifact': {'state': 'found'}}}]},
}


@pytest.mark.parametrize('path', PATHS)
def test_every_check_appears_exactly_once_and_in_order_on_every_path(path):
    checks = turn_log.security_checks(PATHS[path])
    assert [c['check'] for c in checks] == list(turn_log.CHECKS)
    assert all(c['status'] in turn_log.STATUSES for c in checks)


def test_a_refused_input_is_blocked_and_nothing_after_it_is_reached():
    result = outcomes(PATHS['invalid'])
    assert result['input'] == 'blocked'
    assert set(result.values()) == {'blocked', 'not reached'}


def test_a_sourced_answer_passes_every_check_it_reaches():
    result = outcomes(PATHS['answer'])
    assert result == {'input': 'passed', 'agent_tool': 'passed', 'call_limit': 'passed', 'tool_input': 'not reached',
                      'route': 'passed', 'passages_as_data': 'applied', 'relevance': 'passed', 'quotes': 'passed',
                      'disclaimer': 'passed', 'no_html': 'applied'}


def test_a_run_ended_by_its_cap_is_blocked_in_the_cap_s_own_words():
    # Decision 94.a: the middleware ends the run; the check shows what it wrote and how many calls there were.
    result = {**calculation('success'), 'model_calls': 5, 'call_limit_reached': 'Model call limits exceeded: run limit (5/5)'}
    check = {c['check']: c for c in turn_log.security_checks(result)}['call_limit']
    assert check['status'] == 'blocked' and check['detail'] == 'Model call limits exceeded: run limit (5/5) (5 model and 1 tool calls)'


def test_a_server_tool_that_answers_error_is_a_refused_input():
    result = {**PATHS['server'], 'tool_calls': [{'name': 'search', 'args': {'corpus': 'nope'},
                                                 'result': {'status': 'success', 'artifact': {'state': 'error'}}}]}
    assert outcomes(result)['tool_input'] == 'blocked'
    assert outcomes(PATHS['server'])['tool_input'] == 'passed'


def test_a_router_decline_is_blocked_and_the_search_steps_are_not_reached():
    result = outcomes(PATHS['declined'])
    assert result['route'] == 'blocked'
    assert {result[c] for c in ('passages_as_data', 'relevance', 'quotes', 'disclaimer')} == {'not reached'}


def test_dropped_quotes_a_low_relevance_and_the_agent_fallback_are_warnings():
    result = knowledge(quotes_dropped=2, below_floor=True, relevance=0.41)
    result['fallback'] = True
    checks = {c['check']: c for c in turn_log.security_checks(result)}
    assert checks['agent_tool']['status'] == checks['relevance']['status'] == checks['quotes']['status'] == 'warning'
    assert '0.410 below 0.495' in checks['relevance']['detail']
    assert '1 kept, 2 dropped' in checks['quotes']['detail']


def test_nothing_found_passes_the_quote_check_because_no_quote_is_shown():
    assert outcomes(PATHS['not found'])['quotes'] == 'passed'


def test_a_refused_tool_input_is_blocked_and_one_the_agent_corrected_is_a_warning():
    assert outcomes(calculation('error'))['tool_input'] == 'blocked'
    assert outcomes(calculation('error', 'success'))['tool_input'] == 'warning'
    assert outcomes(calculation('success'))['tool_input'] == 'passed'


def test_write_appends_one_json_line_per_turn_and_the_summary_counts_them(tmp_path):
    log = tmp_path / 'logs' / 'turns.jsonl'
    for result in (PATHS['answer'], PATHS['invalid']):
        turn_log.write({**result, 'security': turn_log.security_checks(result), 'seconds': 2.0, 'usd': 0.003},
                       'thread-1', log)
    lines = log.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 2 and json.loads(lines[0])['thread_id'] == 'thread-1'
    summary = turn_log.summary(log)
    assert summary['turns'] == 2 and summary['outcomes'] == {'answer': 1, 'invalid': 1}
    assert summary['checks']['input'] == {'passed': 1, 'blocked': 1}
    assert summary['seconds_median'] == 2.0 and summary['usd_total'] == pytest.approx(0.006)


def test_the_summary_survives_an_unreadable_line_and_a_missing_log(tmp_path):
    assert turn_log.summary(tmp_path / 'none.jsonl') is None
    log = tmp_path / 'turns.jsonl'
    log.write_text('{"kind": "invalid"}\nnot json\n', encoding='utf-8')
    assert turn_log.summary(log)['unreadable_lines'] == 1


def test_a_tool_artifact_that_is_the_turn_is_written_once(tmp_path):
    result = knowledge()
    result['tool_calls'][0]['result']['artifact'] = result['turn']
    turn_log.write(result, 't', tmp_path / 'turns.jsonl')
    record = json.loads((tmp_path / 'turns.jsonl').read_text(encoding='utf-8'))
    assert record['turn']['plan'] == PLAN
    assert record['tool_calls'][0]['result']['artifact'] == 'the turn, section or server answer of this record'
    assert result['tool_calls'][0]['result']['artifact'] is result['turn']  # the live result is untouched


def test_a_page_image_is_logged_by_its_type_and_size_not_its_pixels(tmp_path):
    answer = {'state': 'found', 'image': {'kind': 'native', 'dpi': 300}, 'sent_image': {'mime_type': 'image/png', 'data': 'QUJD' * 50}}
    result = {'kind': 'server', 'question': 'show me page 1', 'turn': None, 'server': {'tool': 'page_image', 'args': {}, 'answer': answer},
              'tool_calls': [{'name': 'page_image', 'args': {}, 'result': {'status': 'success', 'artifact': answer}}]}
    turn_log.write(result, 't', tmp_path / 'turns.jsonl')
    record = json.loads((tmp_path / 'turns.jsonl').read_text(encoding='utf-8'))
    assert record['server']['answer']['sent_image'] == {'mime_type': 'image/png', 'base64_characters': 200, 'not_logged': 'pixels'}
    assert record['server']['answer']['image'] == {'kind': 'native', 'dpi': 300}  # what the image is stays
    assert record['tool_calls'][0]['result']['artifact'] == 'the turn, section or server answer of this record'
    assert answer['sent_image']['data'] == 'QUJD' * 50  # the live answer keeps its pixels for the interface


def test_each_conversation_gets_a_file_named_by_its_start_and_its_id(tmp_path):
    from datetime import datetime
    path = turn_log.conversation_log('f99c2ef4-1234-5678', datetime(2026, 10, 1, 15, 12, 4), tmp_path)
    assert path == tmp_path / '2026-10-01_15-12-04_f99c2ef4.jsonl'


def test_the_summary_counts_every_conversation_file_in_the_folder_and_the_answer_lengths(tmp_path):
    from datetime import datetime

    long_answer = knowledge(answer_words=650, word_limit=600)
    file_a = turn_log.conversation_log('thread-a', datetime(2026, 11, 5, 9, 0, 0), tmp_path)
    file_b = turn_log.conversation_log('thread-b', datetime(2026, 11, 5, 9, 5, 0), tmp_path)
    for path, result, thread in ((file_a, knowledge(answer_words=170, word_limit=400), 'thread-a'),
                                 (file_b, long_answer, 'thread-b'), (file_b, PATHS['invalid'], 'thread-b')):
        turn_log.write({**result, 'security': turn_log.security_checks(result)}, thread, path)
    summary = turn_log.summary(tmp_path)
    assert (summary['turns'], summary['conversations'], summary['files']) == (3, 2, 2)
    assert (summary['answers_measured'], summary['answers_over_limit']) == (2, 1)
    assert summary['answer_words_median'] == 410


def test_the_stored_shape_keeps_each_artifact_once_and_the_pixels_only_when_asked():
    # Line 2's request 4 (5 Nov): its chat route returns what the log stores, with the pixels it shows.
    answer = {'state': 'found', 'image': {'kind': 'native'}, 'sent_image': {'mime_type': 'image/png', 'data': 'QUJD'}}
    result = {'kind': 'server', 'question': 'show me page 1', 'turn': None, 'server': {'tool': 'page_image', 'args': {}, 'answer': answer},
              'tool_calls': [{'name': 'page_image', 'args': {}, 'result': {'status': 'success', 'artifact': answer}}]}
    live = turn_log.stored(result, keep_pixels=True)
    assert live['server']['answer']['sent_image']['data'] == 'QUJD'
    assert live['tool_calls'][0]['result']['artifact'] == 'the turn, section or server answer of this record'
    assert turn_log.stored(result)['server']['answer']['sent_image'] == {'mime_type': 'image/png', 'base64_characters': 4,
                                                                         'not_logged': 'pixels'}
    assert result['tool_calls'][0]['result']['artifact'] is answer  # the result itself is untouched


@pytest.mark.parametrize('thread_id', ['../../etc', 'a b', 'C:\\temp', ''])
def test_a_conversation_id_that_could_leave_the_log_folder_is_refused(thread_id):
    # Line 2's request 7 (5 Nov), defence in depth beside its route's own UUID check.
    with pytest.raises(ValueError, match='a conversation id must begin with'):
        turn_log.conversation_log(thread_id)


def test_the_search_servers_call_log_beside_the_turns_is_no_conversation(tmp_path):
    # Found by the review of 99.a (5 Nov): the call log shares the folder; it was listed, counted, openable and deletable.
    from datetime import datetime

    conversation = turn_log.conversation_log('f99c2ef4-1234', datetime(2026, 11, 5, 15, 0, 0), tmp_path)
    turn_log.write({**PATHS['answer'], 'security': turn_log.security_checks(PATHS['answer'])}, 'f99c2ef4-1234', conversation)
    call_log = tmp_path / 'search_server.jsonl'
    call_log.write_text('{"at": "2026-11-05T14:00:00+00:00", "tool": "search", "state": "found"}\n', encoding='utf-8')
    assert [found['path'] for found in turn_log.conversations(tmp_path)] == [conversation]
    assert turn_log.summary(tmp_path)['turns'] == 1
    with pytest.raises(ValueError, match='not a conversation log'):
        turn_log.delete_conversation(call_log, tmp_path)
    assert call_log.exists()


def test_a_question_with_a_line_separator_or_a_lone_surrogate_stays_one_readable_record(tmp_path):
    # ASCII JSON (the review of 99.a): U+2028 split a record for a reader of lines, and a lone surrogate could not be written.
    path = turn_log.conversation_log('abcdef12')
    path = tmp_path / path.name
    for question in ('drawdown or ruin?', 'drawdown\ud800?', 'Wie hoch ist die Volatilität?'):
        turn_log.write({**PATHS['invalid'], 'question': question, 'text': question}, 'abcdef12', path)
    records, unreadable = turn_log._read(path)
    assert unreadable == 0 and [record['question'] for record in records] == [
        'drawdown or ruin?', 'drawdown\ud800?', 'Wie hoch ist die Volatilität?']


def _logged(tmp_path, name, *questions):
    path = tmp_path / name
    for question in questions:
        result = {**knowledge(), 'question': question, 'turn_id': 'abcd1234'}
        result['turn'] = {**result['turn'], 'answer': f'An answer to {question}.', 'disclaimer': 'Not trading advice.',
                          'quotes': [{'passage': 1, 'text': 'A quote.', 'citation': {'text': 'A Book · p. 3', 'licence': 'CC BY 4.0'}}]}
        turn_log.write(result, 'thread-' + name[:4], path)
    return path


def test_past_conversations_are_listed_newest_first_with_their_first_question(tmp_path):
    _logged(tmp_path, '2026-10-01_09-00-00_aaaa.jsonl', 'first one')
    _logged(tmp_path, '2026-10-01_15-12-04_bbbb.jsonl', 'what is a drawdown?', 'and the sharpe ratio?')
    (tmp_path / '2026-10-01_16-00-00_empty.jsonl').write_text('', encoding='utf-8')
    past = turn_log.conversations(tmp_path)
    assert [(c['started'], c['first_question'], c['turns']) for c in past] == [
        ('2026-10-01_15-12-04', 'what is a drawdown?', 2), ('2026-10-01_09-00-00', 'first one', 1)]
    assert past[0]['thread_id'] == 'thread-2026'


def test_a_conversation_is_reopened_in_the_shape_the_interface_keeps(tmp_path):
    path = _logged(tmp_path, '2026-10-01_15-12-04_bbbb.jsonl', 'what is a drawdown?', 'and the sharpe ratio?')
    shown = turn_log.messages(path)
    assert [m['role'] for m in shown] == ['user', 'assistant', 'user', 'assistant']
    assert shown[2]['content'] == 'and the sharpe ratio?'
    assert shown[1]['result']['turn']['answer'] == 'An answer to what is a drawdown?.'
    assert 'at' not in shown[1]['result'] and 'thread_id' not in shown[1]['result']


def test_only_a_conversation_log_inside_the_log_folder_can_be_deleted(tmp_path):
    path = _logged(tmp_path, '2026-10-01_15-12-04_bbbb.jsonl', 'q')
    other = tmp_path / 'notes.txt'
    other.write_text('keep me', encoding='utf-8')
    for target in (other, tmp_path.parent / path.name):
        with pytest.raises(ValueError, match='not a conversation log'):
            turn_log.delete_conversation(target, tmp_path)
    turn_log.delete_conversation(path, tmp_path)
    assert not path.exists() and other.exists()


def test_a_transcript_holds_questions_answers_quotes_and_the_disclaimer(tmp_path):
    path = _logged(tmp_path, '2026-10-01_15-12-04_bbbb.jsonl', 'what is a drawdown?')
    text = turn_log.transcript(path)
    assert text.startswith('# Conversation of 2026-10-01 15:12:04')
    for part in ('## what is a drawdown?', 'An answer to what is a drawdown?.', '> A quote.',
                 '[1] A Book · p. 3 · CC BY 4.0', '*Not trading advice.*', 'turn abcd1234'):
        assert part in text, part
