import subprocess
from pathlib import Path

import pytest

from backend.conversion.store import reading_store


def test_a_root_inside_the_repository_that_git_would_track_is_refused():
    with pytest.raises(reading_store.UnsafeRootError, match='not git-ignored'):
        reading_store.Store(reading_store.REPO / 'src' / 'readings_here')


def test_the_mirror_roots_are_ignored_where_they_really_lie():
    for root in reading_store.ROOTS.values():
        assert reading_store.refusal(root.resolve()) is None


def test_a_root_inside_another_git_work_tree_is_refused(tmp_path):
    (tmp_path / '.git').mkdir()
    with pytest.raises(reading_store.UnsafeRootError, match='another git work tree'):
        reading_store.Store(tmp_path / 'vision')


def git(*args: str, cwd: Path) -> None:
    subprocess.run(['git', '-c', 'user.name=test', '-c', 'user.email=test@example.com', '-c', 'commit.gpgsign=false', *args],
                   cwd=cwd, check=True, capture_output=True)


def test_a_linked_worktree_counts_as_this_repository_and_another_repository_does_not(tmp_path):
    main, linked, other = tmp_path / 'main', tmp_path / 'linked', tmp_path / 'other'
    for folder in (main, other):
        folder.mkdir()
        git('init', '--quiet', cwd=folder)
    (main / '.gitignore').write_text('/_*/\n', encoding='utf-8')
    git('add', '.gitignore', cwd=main)
    git('commit', '--quiet', '-m', 'ignore rule', cwd=main)
    git('worktree', 'add', '--quiet', str(linked), cwd=main)
    # Seen from the linked worktree, as through its junction: the data lies in the main tree.
    assert reading_store.refusal((main / '_sources' / 'vision').resolve(), repo=linked) is None
    assert 'not git-ignored' in reading_store.refusal((main / 'src' / 'vision').resolve(), repo=linked)
    assert 'another git work tree' in reading_store.refusal((other / '_sources' / 'vision').resolve(), repo=linked)


def test_no_path_can_leave_the_root(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    with pytest.raises(reading_store.UnsafeRootError, match='outside'):
        store.path('..', 'escaped.txt')


def test_inputs_are_stored_once_by_hash_and_readings_round_trip(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    digest = store.put_input(b'png bytes', '.png')
    assert digest == store.put_input(b'png bytes', '.png') and store.get_input(digest, '.png') == b'png bytes'
    store.save_reading('ab' * 32, {'result_class': 'ok'}, 'text')
    assert store.has_ok_reading('ab' * 32) and not store.has_ok_reading('cd' * 32)


def test_a_prompt_comes_back_byte_for_byte_by_its_hash(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    text = 'line one\nline two with a backslash \\frac and a bullet •\n'
    digest = store.put_prompt(text)
    assert digest == store.put_prompt(text) and store.get_prompt(digest) == text


def test_all_records_can_be_read_back_without_the_texts_or_a_half_written_file(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    assert store.readings() == []
    store.save_reading('ab' * 32, {'result_class': 'ok'}, 'the page text')
    store.save_reading('cd' * 32, {'result_class': 'errored'}, None)
    store.path('readings', 'ab', 'x.json.part').write_bytes(b'{half')
    assert sorted(record['result_class'] for record in store.readings()) == ['errored', 'ok']


def flaky_replace(monkeypatch, refusals: int) -> list:
    """os.replace that Windows refuses `refusals` times, as when a scanner holds the file; no real waiting."""
    calls, real = [], reading_store.os.replace

    def replace(source, target):
        calls.append(target)
        if len(calls) <= refusals:
            raise PermissionError(5, 'Access is denied')
        real(source, target)
    monkeypatch.setattr(reading_store.os, 'replace', replace)
    monkeypatch.setattr(reading_store.time, 'sleep', lambda seconds: None)
    return calls


def test_a_rename_windows_refuses_for_a_moment_is_tried_again(tmp_path, monkeypatch):
    store = reading_store.Store(tmp_path / 'vision')
    calls = flaky_replace(monkeypatch, refusals=2)
    store.save_manifest({'local_id': 'one', 'status': 'collected'})
    assert len(calls) == 3 and store.manifests() == [{'local_id': 'one', 'status': 'collected'}]


def test_a_rename_windows_keeps_refusing_still_fails(tmp_path, monkeypatch):
    store = reading_store.Store(tmp_path / 'vision')
    calls = flaky_replace(monkeypatch, refusals=99)
    with pytest.raises(PermissionError):
        store.save_manifest({'local_id': 'one', 'status': 'collected'})
    assert len(calls) == len(reading_store.REPLACE_WAITS) + 1


def test_the_ledger_sums_what_was_spent(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    for cost in (0.25, 0.5):
        store.append_ledger({'cost_usd': cost})
    assert store.spent_usd() == pytest.approx(0.75)


def test_a_manifest_round_trips(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    assert store.manifests() == []
    store.save_manifest({'local_id': 'one', 'status': 'submitted'})
    store.save_manifest({'local_id': 'one', 'status': 'collected'})
    assert store.manifests() == [{'local_id': 'one', 'status': 'collected'}]
