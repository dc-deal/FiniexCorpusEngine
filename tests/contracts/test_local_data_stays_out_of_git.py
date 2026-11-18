"""Local data never reaches git: top-level folders whose name starts with an underscore, and keys.

`_sources/licensed` holds commercial books, `_work/licensed` everything read from them, `_internal_archive` the
internal documents. A single wrong ignore rule would publish them with the next push, so the rule is a test.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def ignored(path: str) -> bool:
    # --no-index: judge the rules alone, also for a path that happens to be tracked.
    return subprocess.run(['git', 'check-ignore', '--quiet', '--no-index', path], cwd=ROOT).returncode == 0


def test_every_top_level_underscore_folder_is_ignored():
    for probe in ['_sources/licensed/work/page.md', '_sources/free/page.md', '_INTERNAL/archive/note.md',
                  '_course_resources/keys/provided.key',                   '_a_folder_added_later/file.txt']:
        assert ignored(probe), f'{probe} is not git-ignored'


def test_nothing_under_an_underscore_folder_is_tracked():
    tracked = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.splitlines()
    assert [path for path in tracked if path.startswith('_')] == []


def test_key_files_are_ignored_and_the_template_is_not():
    for probe in ['.env', '.env.local', 'claude-key.json', 'openai-key.json', 'server.key']:
        assert ignored(probe), f'{probe} is not git-ignored'
    assert not ignored('.env.example'), '.env.example is the tracked template'


def test_the_data_and_its_old_places_are_ignored_so_a_stray_write_is_never_published():
    # 264.a, 282: the data lives in _data/, a local folder in no repository; where it lay before stays ignored.
    for probe in ['_data/corpus/readings/w/p0001.md', '_sources/licensed/a.pdf', '_sources/free_candidates/b.pdf', '_work/licensed/vision/x.json', 'corpus/raw/x.pdf', 'corpus/readings/w/p0001.md',
                  'evaluation/results/answers.json', 'src/backend/_scratch/note.md']:
        assert ignored(probe), f'{probe} is not git-ignored'
    assert not ignored('corpus/catalog.json') and not ignored('evaluation/eval_questions.json'), 'the catalog and the questions are public'


def test_drafts_the_bus_registration_credentials_and_local_databases_are_ignored():
    for probe in ['ISSUE_roadmap.md', 'SESSION_HANDOFF_x.md', 'SUMMARY_2026-11-16.md', '.mcp.json', '.claude.json',
                  'keys/provided.txt', 'configs/app_config.local.json', 'server.pem', 'id_rsa', '.envrc', 'corpus/index/knowledge.sqlite3', 'local.db']:
        assert ignored(probe), f'{probe} is not git-ignored'
