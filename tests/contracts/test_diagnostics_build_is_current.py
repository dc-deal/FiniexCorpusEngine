"""The diagnostics UI's build is committed, and it was made from the sources as they are now.

A reviewer runs the UI without Node, so `src/frontend/diagnostics/dist/` is tracked despite the global
`dist/` rule in `.gitignore`. It is only worth that if it matches its sources: the build stamps the hash
of its inputs, and this test computes it again in Python, offline and without Node.
"""

import json
import subprocess
from pathlib import Path

from backend.diagnostics import build

ROOT = Path(__file__).resolve().parents[2]


def test_the_build_is_not_ignored_by_git():
    listed = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard',
                             'src/frontend/diagnostics/dist'],
                            cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    assert {'src/frontend/diagnostics/dist/index.html', 'src/frontend/diagnostics/dist/build_stamp.json'} <= set(listed)


def test_the_build_matches_its_sources():
    stamp = json.loads(build.STAMP.read_text(encoding='utf-8'))
    assert stamp['sources_sha256'] == build.sources_sha256(), \
        'the UI changed after its last build: run python -m backend.diagnostics.build'
