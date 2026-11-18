"""No tracked file names a licensed work or a private name, or holds a key.

The names of the Finiex apps and of their bus may appear in tracked files (decision 251.a). What stays out for good, and
since the repository is public (263.a) also what the private collection holds: a licensed work by any name the local lists
give it (its file's stem, its citation key, its subject key), and the remaining private names. Both lists live only on the
machine that holds the archive, git-ignored, so this test spells none of them; a clone without them has nothing to compare
with. Anything shaped like a key stays out everywhere.
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from backend.configuration import data_paths

ROOT = Path(__file__).resolve().parent.parent.parent
TEXT_SUFFIXES = {'.py', '.md', '.json', '.txt', '.toml', '.ini', '.yml', '.yaml', '.cfg', '.example',
                 '.code-workspace', '.gitignore', '.js', '.mjs', '.ts', '.vue', '.css', '.html', '.svg'}  # the built UI too
TOKEN = re.compile(r'[a-z0-9_]+')
KEY_SHAPE = re.compile(r'sk-(?:ant|or|proj)-[A-Za-z0-9_-]{20,}')
LICENSED = data_paths.LICENSED_WORKING
# SHA-256 of private names, kept beside the archive rather than here, where a dictionary would reverse them.
PRIVATE_NAMES = data_paths.WORKING / 'private_names.json'
CATALOG = ROOT / 'corpus' / 'catalog.json'


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def tracked_text_files() -> list[Path]:
    """Every text file git would commit: tracked or new, minus what is ignored."""
    listed = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.splitlines()
    paths = [ROOT / name for name in listed]
    return [path for path in paths if path.exists() and (path.suffix in TEXT_SUFFIXES or path.name in TEXT_SUFFIXES)]


def free_names() -> set[str]:
    """The free works' own names: a licensed copy of a free book (the SRE book) shares them and is no leak."""
    sources = json.loads(CATALOG.read_text(encoding='utf-8'))['sources']
    return {source['id'] for source in sources} | {Path(f['path']).stem.lower() for s in sources for f in s['files']}


def licensed_names() -> set[str]:
    """Every name the local lists give a licensed work, lower case; empty on a machine without the archive."""
    def read_json(path: Path):
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None

    def read(relative: str):
        return read_json(LICENSED / relative)

    names: set[str] = set()
    for listed in (read_json(data_paths.LICENSED_ARCHIVE / '_manifest.json'), read('provenance.json')):
        if listed is not None:
            names |= {Path(name).stem.lower() for name in listed['files']}
    if (keys := read('legacy_markdown/keys.json')) is not None:
        names |= {key.lower() for key in keys['keys']} | {Path(value).stem.lower() for value in keys['keys'].values()}
    if (subjects := read('subjects.json')) is not None:
        names |= {key.lower() for key in subjects['subjects']}
    # A name of three letters or fewer reads as an ordinary word (a citation key that is a surname like 'few', a subject
    # like 'law') and is not compared; every longer one is.
    return {name for name in names - free_names() if len(name) > 3}


def test_no_tracked_file_holds_a_private_name():
    if not PRIVATE_NAMES.exists():
        pytest.skip('the list of private names lives beside the archive, on its machine only')
    private = set(json.loads(PRIVATE_NAMES.read_text(encoding='utf-8'))['sha256'])
    found = [path.relative_to(ROOT).as_posix() for path in tracked_text_files()
             if any(digest(token) in private for token in TOKEN.findall(path.read_text(encoding='utf-8', errors='ignore').lower()))]
    assert found == [], f'private names in: {sorted(found)}'


def test_no_tracked_file_names_a_licensed_work():
    names = licensed_names()
    if not names:
        pytest.skip('a clone without the archive has nothing to compare with')
    plain = {name for name in names if TOKEN.fullmatch(name)}
    spelled = [re.compile(rf'(?<![a-z0-9_-]){re.escape(name)}(?![a-z0-9_-])') for name in names - plain]  # e.g. a-b-key
    found = {}
    for path in tracked_text_files():
        text = path.read_text(encoding='utf-8', errors='ignore').lower()
        hits = len(plain & set(TOKEN.findall(text))) + sum(bool(pattern.search(text)) for pattern in spelled)
        if hits:
            found[path.relative_to(ROOT).as_posix()] = hits
    assert found == {}, f'names of licensed works in: {found}'


def test_no_tracked_file_holds_a_key():
    found = [path.relative_to(ROOT).as_posix() for path in tracked_text_files()
             if KEY_SHAPE.search(path.read_text(encoding='utf-8', errors='ignore'))]
    assert found == [], f'key-shaped strings in: {found}'
