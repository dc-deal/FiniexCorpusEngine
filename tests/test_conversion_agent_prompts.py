"""The prompts that start a session's agents, rendered by code from a registered template (#17, 22.a), and the origin every
prompt version names."""

import json

import pytest

from backend.conversion.judge import page_judge, session_judge
from backend.conversion.reading import agent_prompts
from backend.conversion.store import reading_store

REGISTRY = json.loads(page_judge.VERSIONS.read_text(encoding='utf-8'))


def test_every_prompt_version_names_its_origin_and_an_unknown_one_says_so():
    keys = {'author_kind', 'author', 'written_on', 'source', 'evidence'}
    for entry in REGISTRY['versions']:
        assert set(entry['origin']) == keys, entry['version']
        assert entry['origin']['author_kind'] in (None, 'model', 'person', 'vendor'), entry['version']
        if entry['origin']['author'] is None:
            assert entry['origin']['evidence'], f"{entry['version']}: an unknown origin says how that is known"


def test_no_tracked_origin_names_a_model_as_an_author_and_this_machine_lays_its_own_over(tmp_path, monkeypatch):
    # the operator's 23.a: an origin naming a model as an author stays off the public repository, in a local file
    assert all(entry['origin']['author_kind'] != 'model' for entry in REGISTRY['versions'])
    local = tmp_path / 'prompt_origins.json'
    monkeypatch.setattr(page_judge, 'local_origins_path', lambda: local)
    assert page_judge.prompt_origins()['page/1']['evidence'].startswith('kept on this machine')
    local.write_text(json.dumps({'origins': {'page/1': {'author_kind': 'model', 'author': 'x', 'written_on': '2026-10-30',
                                                        'source': None, 'evidence': 'a transcript'}}}), encoding='utf-8')
    assert page_judge.prompt_origins()['page/1']['author'] == 'x'
    assert page_judge.prompt_origins()['paddleocr-vl/ocr']['author'] == 'PaddlePaddle'  # a vendor's stays tracked


def test_a_lost_prompt_has_an_entry_without_text():
    lost = {entry['version']: entry for entry in REGISTRY['versions'] if entry['version'].endswith('/unknown')}
    assert set(lost) == {'reader-agent/unknown', 'judge-agent/unknown'}
    assert all(entry['files'] == [] and entry['state'] == 'retired' for entry in lost.values())
    with pytest.raises(ValueError):
        agent_prompts.template('judge-agent/unknown')


def test_no_registered_prompt_names_this_machine():
    # a template holds placeholders only: the repository's path and a run's folders are filled in at run time; checked against
    # this machine's own home and repository, read at run time, so no name is written into the test either
    from pathlib import Path

    machine = {str(place).replace('\\', '/').lower() for place in (Path.home(), agent_prompts.REPOSITORY)}
    machine |= {Path.home().name.lower()} if len(Path.home().name) > 2 else set()
    for entry in REGISTRY['versions']:
        for path in entry['files']:
            text = (page_judge.CONVERSION / path).read_text(encoding='utf-8').replace('\\', '/').lower()
            assert not any(place in text for place in machine) and 'c:/users' not in text and '/home/' not in text, path


def test_a_template_is_filled_with_every_detail_and_nothing_else():
    assert agent_prompts.placeholders('judge-agent/1') == {'base_folder', 'folders', 'notes'}
    with pytest.raises(ValueError):
        agent_prompts.render('judge-agent/1', base_folder='b', folders='f')  # the notes are missing
    with pytest.raises(ValueError):
        agent_prompts.render('judge-agent/1', base_folder='b', folders='f', notes='', extra='x')
    plain = agent_prompts.render('judge-agent/1', base_folder='B', folders='`a`, `b`', notes='')
    noted = agent_prompts.render('judge-agent/1', base_folder='B', folders='`a`', notes='These are test readings.')
    assert 'Base folder: `B`' in plain and 'Folders: `a`, `b`' in plain and '\n\n\n' not in plain
    assert '\nThese are test readings.\n' in noted


def test_the_session_judge_hands_each_agent_its_rendered_prompt_and_the_verdict_names_it(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    root = tmp_path / 'judge_session'
    folders = []
    for name in ('w__p0001', 'w__p0002', 'w__p0003'):
        (root / name).mkdir(parents=True)
        (root / session_judge.ENTRIES).mkdir(exist_ok=True)
        (root / session_judge.ENTRIES / f'{name}.json').write_text(json.dumps({'reading_key': name}), encoding='utf-8')
        folders.append(root / name)
    written = session_judge.agent_prompts(root, folders, store, 'LAB-X_c01', per_agent=2)
    assert [path.name for path in written] == ['agent_LAB-X_c01_01.prompt.md', 'agent_LAB-X_c01_02.prompt.md']
    first = json.loads((root / session_judge.ENTRIES / 'w__p0001.json').read_text(encoding='utf-8'))
    third = json.loads((root / session_judge.ENTRIES / 'w__p0003.json').read_text(encoding='utf-8'))
    assert first['agent_prompt']['version'] == 'judge-agent/1' and first['agent_prompt']['file'] == written[0].name
    assert store.get_prompt(first['agent_prompt']['sha256']) == written[0].read_text(encoding='utf-8')
    assert '`w__p0001`, `w__p0002`' in written[0].read_text(encoding='utf-8')
    assert third['agent_prompt']['sha256'] != first['agent_prompt']['sha256']


def test_two_models_readings_of_one_page_get_judge_folders_of_their_own():
    # found 27 Nov: four test cells on the same 20 pages wrote one set of folders, and three cells' requests found it taken
    assert session_judge.folder_name({'work': 'w', 'pdf_page': 3, 'target_cell': 'LAB-A'}) == 'LAB-A__w__p0003'
    assert session_judge.folder_name({'work': 'w', 'pdf_page': 3}) == 'w__p0003'


def test_a_session_verdict_keeps_the_agent_prompt_its_request_named(monkeypatch):
    monkeypatch.setattr(page_judge, 'check_answer', lambda entry, text, stop: ('ok', {'verdict': 'ok'}))
    entry = {'request_key': 'r', 'agent_prompt': {'version': 'judge-agent/1', 'sha256': 'a' * 64, 'details': {}}}
    assert session_judge.record_for(entry, '{}')['agent_prompt']['version'] == 'judge-agent/1'
    assert 'agent_prompt' not in session_judge.record_for({'request_key': 'r'}, '{}')  # a request from before 22.a
