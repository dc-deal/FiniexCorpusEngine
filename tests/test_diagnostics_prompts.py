"""The prompts tab (148.a): every version of the reader's and the judge's instructions in the registry's order, each file's
sha256 now beside the frozen one, and each judge version's change from the one before as a line diff."""

import json

from fastapi.testclient import TestClient

from backend.diagnostics import prompts
from backend.diagnostics.app import create_app

# TestClient's own host, "testserver", is refused like any other name that is not this machine's (app.TRUSTED_HOSTS)
LOCAL = 'http://127.0.0.1'


def test_every_version_stands_with_its_state_its_text_and_its_frozen_hash():
    answer = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/prompts').json()
    registry = json.loads(prompts.VERSIONS.read_text(encoding='utf-8'))['versions']
    assert [(v['role'], v['version'], v['state']) for v in answer['versions']] == [
        (v['role'], v['version'], v['state']) for v in registry]
    for version in answer['versions']:
        for prompt_file in version['files']:
            # a test of the core holds every prompt to its frozen hash; the view sets the two side by side
            assert prompt_file['sha256'] == prompt_file['frozen_sha256'] and prompt_file['text']


def test_a_version_shows_its_change_from_the_one_before_it_in_its_role():
    versions = {version.version: version for version in prompts.prompt_list().versions}
    assert versions['page/1'].previous is None and versions['page/1'].files[0].diff is None
    assert versions['judge/1'].previous is None  # the first judge version: no reader version stands before it
    second = versions['judge/2']
    assert second.previous == 'judge/1'
    changed = [line for line in second.files[0].diff if line.kind != 'same']
    assert changed and len(changed) <= 6  # one sentence apart, as the registry says
    # every line of the new text stands in the diff, in order
    assert '\n'.join(line.text for line in second.files[0].diff if line.kind != 'removed') == '\n'.join(second.files[0].text.splitlines())


def test_the_parts_are_the_registrys_tabs_and_every_file_names_its_part():
    registry = json.loads(prompts.VERSIONS.read_text(encoding='utf-8'))
    answer = prompts.prompt_list()
    assert [part.key for part in answer.parts] == list(registry['parts'])
    # the name before the colon, the rest beside it, as the registry words them
    judge = next(part for part in answer.parts if part.key == 'judge')
    assert f'{judge.label}: {judge.about}' == registry['parts']['judge']
    for entry, version in zip(registry['versions'], answer.versions):
        assert (version.title, version.model) == (entry.get('title'), entry.get('model'))
        assert [prompt_file.part for prompt_file in version.files] == [entry['parts'][path] for path in entry['files']]


def test_a_version_is_compared_with_the_file_of_the_same_part_before_it():
    before = {'files': ['format.txt', 'rules.txt'], 'parts': {'format.txt': 'format', 'rules.txt': 'rules'}}
    assert prompts.earlier_file(before, 0, 'rules') == 'rules.txt'  # by its part, wherever it stands
    assert prompts.earlier_file(before, 1, None) == 'rules.txt'  # a file without a part, by its place
    assert prompts.earlier_file(None, 0, 'rules') is None


def test_the_diff_keeps_every_line_of_both_texts():
    lines = prompts.diff_of('a\nb\nc', 'a\nB\nc\nd')
    assert [(line.kind, line.text) for line in lines] == [('same', 'a'), ('removed', 'b'), ('added', 'B'), ('same', 'c'), ('added', 'd')]


def test_a_sentence_added_to_a_long_line_is_marked_word_by_word():
    before = 'Check every word against the page.'
    removed, added = prompts.diff_of(before, f'{before} A proper name is not a wrong word.')
    assert ''.join(part.text for part in added.parts) == added.text
    assert [part.text for part in added.parts if part.changed] == [' A proper name is not a wrong word.']
    assert not any(part.changed for part in removed.parts)
