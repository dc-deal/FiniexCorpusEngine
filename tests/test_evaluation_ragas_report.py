"""The RAGAS report's own parts that need no RAGAS: which questions become samples, and how scores are summed up (136.a)."""
import json
import sqlite3

from backend.evaluation import ragas_report


def index_with(tmp_path, chunks: dict) -> object:
    path = tmp_path / 'knowledge.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE chunks (id TEXT PRIMARY KEY, source_id TEXT, section_id TEXT, text TEXT, metadata TEXT)')
        connection.executemany('INSERT INTO chunks VALUES (?, ?, ?, ?, ?)', [(key, 's', 's:0', text, '{}') for key, text in chunks.items()])
    return path


def question(qid, behaviour, answer='An answer.', chunks=('c1',)):
    return {'id': qid, 'question': f'question {qid}?',
            'turn': {'behaviour': behaviour, 'answer': answer, 'retrieved': [{'chunk_id': chunk} for chunk in chunks]}}


def test_only_answers_drawn_from_passages_become_samples_with_the_passages_full_text(tmp_path):
    database = index_with(tmp_path, {'c1': 'The first passage.', 'c2': 'The second passage.'})
    record = {'questions': [question('q1', 'answer', chunks=('c1', 'c2')), question('q2', 'not_found', answer=''),
                            question('q3', 'answer', answer='  '), question('q4', 'answer', chunks=()),
                            question('q5', 'answer', chunks=('c9',)), question('q6', 'decline_off_topic')]}
    rows, left_out = ragas_report.samples(record, {'q1': 'The expected answer.'}, database)
    assert rows == [{'id': 'q1', 'user_input': 'question q1?', 'response': 'An answer.',
                     'retrieved_contexts': ['The first passage.', 'The second passage.'], 'reference': 'The expected answer.'}]
    assert left_out == {'not answered from passages': 2, 'no answer text': 1, 'no passages': 1, 'passages missing from the index': 1}


def test_the_expected_answers_come_from_every_question_set(tmp_path):
    first, second = tmp_path / 'a.json', tmp_path / 'b.json'
    first.write_text(json.dumps({'questions': [{'id': 'q1', 'expected_answer': 'one'}, {'id': 'q2'}]}), encoding='utf-8')
    second.write_text(json.dumps({'questions': [{'id': 'h1', 'expected_answer': 'two'}]}), encoding='utf-8')
    assert ragas_report.expected_answers((first, second, tmp_path / 'missing.json')) == {'q1': 'one', 'h1': 'two'}


def test_a_metric_is_averaged_over_the_samples_it_could_score_and_shown_against_the_course_s_mark():
    scores = [{'id': 'q1', 'faithfulness': 0.9, 'answer_relevancy': 0.8, 'llm_context_precision_with_reference': None,
               'context_recall': 1.0},
              {'id': 'q2', 'faithfulness': 0.5, 'answer_relevancy': None, 'llm_context_precision_with_reference': None,
               'context_recall': 0.0}]
    summed = ragas_report.summary(scores)
    assert summed['faithfulness'] == {'mean': 0.7, 'scored': 2, 'target': 0.8}
    assert summed['llm_context_precision_with_reference'] == {'mean': None, 'scored': 0, 'target': 0.7}
    report = {'record': 'answers_x.json', 'samples': 2, 'judge': ragas_report.JUDGE_MODEL, 'embeddings': 'e', 'ragas': '0.4.3',
              'date': '2026-11-09', 'left_out': {}, 'cost_usd': None, 'summary': summed, 'scores': scores}
    text = ragas_report.markdown(report)
    assert '| faithfulness | 0.700 | 2 | 0.8 |' in text and 'not booked' in text and '| q2 | 0.50 | – | – | 0.00 |' in text


def test_the_judge_is_not_the_model_that_wrote_the_answers():
    config = json.loads((ragas_report.ROOT / 'configs' / 'app_config.json').read_text(encoding='utf-8'))
    assert ragas_report.JUDGE_MODEL != config['generator']['model']
