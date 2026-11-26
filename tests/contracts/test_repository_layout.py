"""The repository root holds global configuration and the README; code lies in src/ and tests/.

`src/backend` holds the domains (providers, search, chat, conversion, ingestion, evaluation), `src/frontend`
the interface. Data stays outside `src/` (corpus/, configs/, evaluation/). A new file in the root has
to be added here on purpose.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROOT_FILES = {'.dockerignore', '.env.example', '.gitignore', 'Dockerfile', 'LICENSE',
              'NOTICE.md', 'README.md', 'docker-compose.yml',
              'pyproject.toml', 'pytest.ini', 'requirements.txt', 'requirements-eval.txt'}


def files_git_would_commit() -> list[str]:
    """Tracked or new, minus what is ignored."""
    listed = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.splitlines()
    return [name for name in listed if (ROOT / name).exists()]


def test_the_root_holds_only_the_files_listed_here():
    assert {name for name in files_git_would_commit() if '/' not in name} - ROOT_FILES == set()


def test_python_code_lies_only_in_src_and_tests():
    # The corpus may hold foreign code as source text, which is data here.
    assert [name for name in files_git_would_commit() if name.endswith('.py')
            and not name.startswith(('src/', 'tests/', 'corpus/'))] == []


def test_src_holds_only_the_backend_and_the_frontend():
    assert {name.split('/')[1] for name in files_git_would_commit() if name.startswith('src/')} == {'backend', 'frontend'}
