import json
import sqlite3
from pathlib import Path

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding

from backend.configuration import data_paths
from backend.evaluation import retrieval_eval as ev
from backend.ingestion import index_store
from backend.search.retrieval import retrieve

ROOT = Path(__file__).resolve().parent.parent

WIKI = 'https://en.wikipedia.org/w/index.php?title=Double-entry_bookkeeping&oldid=1'


def cite(source, section=None, anchor=None, url=None, pdf_page=None):
    citation = {'source_id': source, 'source_title': source}
    for key, value in (('section', section), ('anchor', anchor), ('url', url), ('pdf_page', pdf_page)):
        if value is not None:
            citation[key] = value
    return citation


def result(citation, n):
    return {'chunk_id': f'c{n}', 'similarity': 1 - n / 100, 'citation': citation, 'text': ''}


# The worked example from the chat: q02 with four expected sources.
EXPECTED = [
    {'source': 'acc', 'section': '3.5 Journal Entries'},
    {'source': 'acc', 'section': '3.6 Trial Balance'},
    {'source': 'klep', 'section': 'Accounting for Computer Scientists'},
    {'source': 'wiki', 'article': 'Double-entry_bookkeeping', 'anchor': None},
]
RESULTS = [
    result(cite('wiki', section='Debits and credits', anchor='Debits_and_credits', url=WIKI + '#Debits_and_credits'), 1),
    result(cite('acc', section='4.3 Adjusting Entries', pdf_page=227), 2),
    result(cite('acc', section='3.5 Journal Entries', pdf_page=137), 3),
    result(cite('sre', section='Monitoring', anchor='x', url='https://sre.google/x/#x'), 4),
    result(cite('klep', section='Accounting for Computer Scientists', url='https://k/'), 5),
]


def test_a_wikipedia_chunk_belongs_to_its_article_and_its_lead_has_no_anchor():
    lead = cite('wiki', section='Double-entry bookkeeping', url=WIKI)
    assert ev.chunk_document(lead) == ('wiki', 'Double-entry_bookkeeping')
    assert ev.matches(lead, EXPECTED[3], 'section')
    assert not ev.matches(RESULTS[0]['citation'], EXPECTED[3], 'section')  # another section
    assert ev.matches(RESULTS[0]['citation'], EXPECTED[3], 'document')     # same article


def test_the_worked_example_gives_the_numbers_from_the_explanation():
    metrics = ev.question_metrics(ev.judge(RESULTS, EXPECTED), len(EXPECTED), k_max=5)
    section, document = metrics['section']['at_k'], metrics['document']['at_k']
    assert section[5]['precision'] == 2 / 5 and section[5]['recall'] == 2 / 4 and section[5]['hit'] == 1
    assert section[3]['precision'] == 1 / 3 and section[3]['recall'] == 1 / 4
    assert document[5]['precision'] == 4 / 5 and document[5]['recall'] == 4 / 4
    assert metrics['section']['first_hit_rank'] == 3 and metrics['section']['reciprocal_rank'] == 1 / 3


def test_a_question_without_any_hit_scores_zero_not_an_error():
    metrics = ev.question_metrics(ev.judge(RESULTS[3:4], EXPECTED), len(EXPECTED), k_max=10)
    assert metrics['section']['at_k'][10] == {'precision': 0.0, 'recall': 0.0, 'hit': 0}
    assert metrics['section']['reciprocal_rank'] == 0.0 and metrics['section']['first_hit_rank'] is None


def test_questions_without_expected_sources_are_left_to_the_routing_measurement():
    questions = [{'id': 'q', 'question': 'x', 'behaviour': 'answer_direct', 'expected_sources': EXPECTED},
                 {'id': 'off', 'question': 'car', 'behaviour': 'decline_off_topic', 'expected_sources': []}]
    evaluated = ev.evaluate(questions, k_max=5, search=lambda query, k: RESULTS[:k])
    assert [e['id'] for e in evaluated] == ['q']
    assert ev.summarise(evaluated)['section']['5']['hits'] == 1


def test_retrieve_returns_cited_chunks_best_first(tmp_path):
    store = index_store.chroma(tmp_path / 'chroma', DeterministicFakeEmbedding(size=8), 'fake/embedding')
    store.add_documents(
        [Document(page_content=f'text {n}', metadata={'chunk_id': f'c{n}', 'source_id': 's', 'section': f'S{n}'})
         for n in range(3)], ids=['c0', 'c1', 'c2'])
    hits = retrieve('text 1', k=2, store=store)
    assert len(hits) == 2
    assert hits[0]['similarity'] >= hits[1]['similarity']
    assert set(hits[0]['citation']) == {'source_id', 'section'}


def test_retrieve_refuses_an_empty_query():
    with pytest.raises(ValueError):
        retrieve('   ', store=object())


@pytest.mark.corpus
@pytest.mark.parametrize('dataset', ['eval_questions.json', 'eval_questions_holdout.json'])
def test_every_expected_source_exists_as_a_section_in_the_index(dataset):
    # A typo in the dataset would otherwise read as "retrieval cannot find it".
    database = data_paths.INDEX / 'knowledge.sqlite3'
    if not database.exists():
        pytest.skip('no index yet - run python -m backend.ingestion.build')
    rows = sqlite3.connect(database).execute('SELECT source_id, heading_path, url, anchor FROM sections').fetchall()
    missing = []
    for question in json.loads((ROOT / 'evaluation' / dataset).read_text(encoding='utf-8'))['questions']:
        for expected in question['expected_sources']:
            found = any(
                source == expected['source']
                and ('article' not in expected or f"title={expected['article']}&" in (url or ''))
                and (anchor == expected['anchor'] if 'anchor' in expected
                     else heading_path.split(' > ')[-1] == expected['section'])
                for source, heading_path, url, anchor in rows)
            if not found:
                missing.append((question['id'], ev.describe_expected(expected)))
    assert missing == []
