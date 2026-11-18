"""Decisions kept internal stay out of what git would commit.

One decision about the private knowledge base is internal by the operator's word: no tracked file names it, and none claims
the opposite. Four places did, in comments and a protocol, until 2026-11-09 (decision 128.a). The code that lets each
knowledge base say for which reasons a second reader may read its pages is generic and stays.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Spelled in pieces, so this file does not name what it guards against
PATTERNS = [re.compile(r'\b' + '86' + r'\.c\b'), re.compile('licensed ' + 'second reader', re.IGNORECASE),
            re.compile('second reader ' + 'for licensed', re.IGNORECASE)]
TEXT = {'.py', '.md', '.json', '.txt', '.toml', '.ini', '.ts', '.vue', '.yml', '.yaml', '.html', '.css', '.js'}


def committed_text_files() -> list[Path]:
    listed = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.splitlines()
    return [ROOT / name for name in listed if Path(name).suffix in TEXT and (ROOT / name).exists() and 'dist/' not in name]


def test_no_file_git_would_commit_names_the_internal_decision():
    found = []
    for path in committed_text_files():
        text = path.read_text(encoding='utf-8', errors='replace')
        found += [f'{path.relative_to(ROOT).as_posix()}: {pattern.pattern}' for pattern in PATTERNS if pattern.search(text)]
    assert found == []
