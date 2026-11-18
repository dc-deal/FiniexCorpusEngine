"""The turn log holds every question, prompt and passage of every turn: it must never be committed."""

import subprocess
from pathlib import Path

from backend.chat import turn_log

ROOT = Path(__file__).resolve().parent.parent.parent


def never_committed(path: Path) -> bool:
    """Whether git can never commit the path: it lies outside the repository (configs/app_config.local.json may lay the logs
    in another tree, 285.a: line 2's worktree names the main tree's), or git ignores it."""
    if not path.resolve().is_relative_to(ROOT):
        return True
    relative = path.resolve().relative_to(ROOT).as_posix()
    return subprocess.run(['git', 'check-ignore', '--quiet', relative], cwd=ROOT).returncode == 0


def test_the_turn_log_is_ignored_by_git():
    path = turn_log.conversation_log('0123456789abcdef')
    assert never_committed(path), f'{path} is not git-ignored'


def test_the_search_servers_call_log_is_ignored_by_git():
    # Every question any client asked, with its client and session: never committed (pinned after the review of 99.a).
    from backend.search import search_server

    assert never_committed(search_server.CALL_LOG), f'{search_server.CALL_LOG} is not git-ignored'
