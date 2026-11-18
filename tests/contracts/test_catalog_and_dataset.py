"""The catalog and the evaluation dataset must agree with each other and with the rules.

Both are hand-edited JSON, so a typo in a source id or a missing licence field would otherwise
surface only when the pipeline or an evaluation run trips over it.
"""

import json
from pathlib import Path

import pytest

from backend.configuration import data_paths

ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads((ROOT / 'corpus' / 'catalog.json').read_text(encoding='utf-8'))
DATASET = json.loads((ROOT / 'evaluation' / 'eval_questions.json').read_text(encoding='utf-8'))
SOURCE_IDS = {s['id'] for s in CATALOG['sources']}


@pytest.mark.parametrize('source', CATALOG['sources'], ids=lambda s: s['id'])
def test_every_source_states_its_licence_and_where_it_was_checked(source):
    for field in ('title', 'authors', 'licence', 'licence_url', 'licence_checked', 'format', 'shelf', 'language'):
        assert source.get(field), f'{source["id"]} has no {field}'
    assert source['format'] in ('pdf', 'html')
    assert source['files'], f'{source["id"]} lists no files'


def test_every_file_lands_under_corpus_raw_and_no_two_share_a_path():
    paths = [f['path'] for s in CATALOG['sources'] for f in s['files']]
    assert all(p.startswith('corpus/raw/') for p in paths)
    assert len(paths) == len(set(paths))


def test_a_file_the_catalog_marks_untracked_says_why():
    for source in CATALOG['sources']:
        for f in source['files']:
            if f.get('tracked') is False:
                assert f.get('not_tracked_because'), f'{f["path"]} says it is untracked but not why'


@pytest.mark.corpus
def test_no_tracked_raw_file_exceeds_githubs_limit():
    # GitHub refuses any single file above 100 MB; such a file has to be marked "tracked": false.
    limit = 100 * 1024 * 1024
    manifest = json.loads((data_paths.FREE_RAW / '_manifest.json').read_text(encoding='utf-8'))['files']
    untracked = {f['path'] for s in CATALOG['sources'] for f in s['files'] if f.get('tracked') is False}
    too_large = [p for p, r in manifest.items() if p not in untracked and r['bytes'] >= limit]
    assert too_large == []


@pytest.mark.corpus
def test_licences_file_is_current_with_catalog_and_manifest():
    from backend.ingestion import acquire
    manifest = json.loads((data_paths.FREE_RAW / '_manifest.json').read_text(encoding='utf-8'))
    on_disk = (data_paths.FREE_RAW / 'LICENSES.md').read_text(encoding='utf-8')
    assert on_disk == acquire.render_licences(CATALOG, manifest), \
        'LICENSES.md is stale - run python -m backend.ingestion.acquire'


def test_every_expected_source_in_the_dataset_is_in_the_catalog():
    unknown = [(q['id'], s['source']) for q in DATASET['questions']
               for s in q['expected_sources'] if s['source'] not in SOURCE_IDS]
    assert unknown == []


def test_every_question_uses_a_defined_behaviour_and_a_unique_id():
    ids = [q['id'] for q in DATASET['questions']]
    assert len(ids) == len(set(ids))
    undefined = [q['id'] for q in DATASET['questions'] if q['behaviour'] not in DATASET['behaviours']]
    assert undefined == []


def test_the_dataset_is_english():
    # The whole project is English; German letters in a question mean one slipped back in.
    german = [q['id'] for q in DATASET['questions'] if any(c in q['question'] for c in 'äöüÄÖÜß')]
    assert german == []


HOLDOUTS = {name: json.loads((ROOT / 'evaluation' / name).read_text(encoding='utf-8'))
            for name in ('eval_questions_holdout.json', 'eval_questions_holdout_2026-11-06.json')}  # the RAG sprint's, spent; the capstone's


@pytest.mark.parametrize('name', HOLDOUTS)
def test_the_held_out_set_follows_the_same_rules_and_shares_no_id(name):
    holdout = HOLDOUTS[name]
    ids = [q['id'] for q in holdout['questions']]
    assert len(ids) == len(set(ids))
    assert not set(ids) & {q['id'] for q in DATASET['questions']}
    assert [q['id'] for q in holdout['questions'] if q['behaviour'] not in DATASET['behaviours']] == []
    assert [q['id'] for q in holdout['questions'] if any(c in q['question'] for c in 'äöüÄÖÜß')] == []
    unknown = [(q['id'], s['source']) for q in holdout['questions']
               for s in q['expected_sources'] if s['source'] not in SOURCE_IDS]
    assert unknown == []


def test_the_two_held_out_sets_share_no_id_and_the_spent_one_is_in_the_ledger():
    first, fresh = ([q['id'] for q in holdout['questions']] for holdout in HOLDOUTS.values())
    assert not set(first) & set(fresh)
    ledger = json.loads((ROOT / 'evaluation' / 'holdout_ledger.json').read_text(encoding='utf-8'))
    assert all((ROOT / run['file']).exists() for run in ledger['runs'])
    assert {'file': 'evaluation/eval_questions_holdout.json', 'at': '2026-10-01'}.items() <= ledger['runs'][0].items()
