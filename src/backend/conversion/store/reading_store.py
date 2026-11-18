"""Where readings live: content-addressed files under a git-ignored root, one root per mirror.

Pages read from the licensed archive go to `_work/licensed/vision`, pages of the free corpus to
`_work/free/vision` (decided 2026-10-29: every top-level folder starting with '_' is
git-ignored). A store refuses a root inside the repository that git would track: one wrong ignore
rule has to stop the runner, not publish book text. The check follows links to where the data really
lies, and every work tree of this repository counts as its own (a linked worktree reaches the main
tree's `_work` through a junction); any other repository is refused. Every path is resolved
through the store and must lie under its root.

Layout under a root:

    inputs/<aa>/<sha256>.png      the exact bytes sent
    prompts/<sha256>.txt          each system prompt and user turn, as sent
    readings/<aa>/<key>.json      what was asked (payloads as hashes), the result, usage, cost, parse
    readings/<aa>/<key>.md        the response text as returned, whatever the form
    batches/<local_id>.json       a batch: custom_id -> reading key, status, estimate
    reports/                      free checks and smoke tests
    ledger.jsonl                  one line per result with its cost; the spend guard reads it
"""

import functools
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

from backend.configuration import data_paths

REPO = Path(__file__).resolve().parents[4]
REPLACE_WAITS = (0.2, 0.5, 1.0)  # seconds between tries of a rename Windows refuses; the last try raises
ROOTS = {'licensed': data_paths.LICENSED_WORKING / 'vision',
         'free': data_paths.FREE_WORKING / 'vision'}


class UnsafeRootError(RuntimeError):
    """A store root, or a path inside it, that could reach git or lies outside the root."""


def git_ignores(path: Path, tree: Path) -> bool:
    """Whether git ignores a file inside `path`, asked in the work tree `tree` that holds it."""
    probe = (path.relative_to(tree) / 'probe').as_posix()
    return subprocess.run(['git', 'check-ignore', '--quiet', '--no-index', probe], cwd=tree).returncode == 0


def work_tree_of(path: Path) -> Path | None:
    """The nearest folder at or above `path` with a `.git` entry: a folder in a main tree, a file in a linked worktree."""
    return next((folder for folder in [path, *path.parents] if (folder / '.git').exists()), None)


@functools.cache
def git_common_dir(tree: Path) -> Path | None:
    """The git folder a work tree shares with every other worktree of its repository; None if git does not know it."""
    result = subprocess.run(['git', 'rev-parse', '--git-common-dir'], cwd=tree, capture_output=True, text=True)
    return (tree / result.stdout.strip()).resolve() if result.returncode == 0 else None


def refusal(root: Path, repo: Path = REPO) -> str | None:
    """Why no store may live at `root`, a resolved path, or None: outside every repository, or ignored in this one."""
    tree = work_tree_of(root)
    if tree is None:
        return None
    ours = git_common_dir(repo)
    if ours is None or git_common_dir(tree) != ours:
        return f'{root} lies inside another git work tree'
    if not git_ignores(root, tree):
        return f'{root} lies in the repository and is not git-ignored'
    return None


def open_store(mirror: str) -> 'Store':
    return Store(ROOTS[mirror])


class Store:
    def __init__(self, root: Path):
        root = Path(root).resolve()
        reason = refusal(root)
        if reason:
            raise UnsafeRootError(reason)
        if 'OneDrive' in root.parts:
            raise UnsafeRootError(f'{root} lies under OneDrive, which would upload it')
        root.mkdir(parents=True, exist_ok=True)
        self.root = root

    def path(self, *parts: str) -> Path:
        path = self.root.joinpath(*parts).resolve()
        if self.root not in path.parents:
            raise UnsafeRootError(f'{path} lies outside {self.root}')
        return path

    def _write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + '.part')
        part.write_bytes(data)
        for wait in REPLACE_WAITS:
            try:
                os.replace(part, path)
                return
            except PermissionError:  # Windows: a scanner or indexer holds the file for a moment (seen 2026-11-02)
                time.sleep(wait)
        os.replace(part, path)

    def put_input(self, data: bytes, suffix: str) -> str:
        """Store an input by its sha256 (once) and return the hash."""
        digest = hashlib.sha256(data).hexdigest()
        path = self.path('inputs', digest[:2], digest + suffix)
        if not path.exists():
            self._write(path, data)
        return digest

    def get_input(self, digest: str, suffix: str) -> bytes:
        return self.path('inputs', digest[:2], digest + suffix).read_bytes()

    def put_prompt(self, text: str) -> str:
        data = text.encode('utf-8')
        digest = hashlib.sha256(data).hexdigest()
        path = self.path('prompts', digest + '.txt')
        if not path.exists():
            self._write(path, data)
        return digest

    def get_prompt(self, digest: str) -> str:
        return self.path('prompts', digest + '.txt').read_bytes().decode('utf-8')

    def _reading_paths(self, key: str) -> tuple[Path, Path]:
        return self.path('readings', key[:2], key + '.json'), self.path('readings', key[:2], key + '.md')

    def reading(self, key: str) -> dict | None:
        record_path, _ = self._reading_paths(key)
        return json.loads(record_path.read_text(encoding='utf-8')) if record_path.exists() else None

    def readings(self) -> list[dict]:
        """Every stored record. A plan reads them once per mirror: a block on a page holds for every cell."""
        folder = self.path('readings', 'x').parent
        return [json.loads(path.read_text(encoding='utf-8')) for path in sorted(folder.glob('*/*.json'))]

    def reading_text(self, key: str) -> str | None:
        _, text_path = self._reading_paths(key)
        return text_path.read_text(encoding='utf-8') if text_path.exists() else None

    def has_ok_reading(self, key: str) -> bool:
        record = self.reading(key)
        return bool(record) and record.get('result_class') == 'ok'

    def save_reading(self, key: str, record: dict, text: str | None) -> None:
        """Write the text first, then the record: a record never points to a missing text."""
        record_path, text_path = self._reading_paths(key)
        if text is not None:
            self._write(text_path, text.encode('utf-8'))
        self._write(record_path, json.dumps(record, indent=1, ensure_ascii=False, default=str).encode('utf-8'))

    def write_report(self, name: str, report: dict) -> Path:
        path = self.path('reports', name)
        self._write(path, json.dumps(report, indent=1, ensure_ascii=False, default=str).encode('utf-8'))
        return path

    def append_ledger(self, entry: dict) -> None:
        path = self.path('ledger.jsonl')
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a', encoding='utf-8', newline='\n') as ledger:
            ledger.write(json.dumps(entry, sort_keys=True) + '\n')

    def append_issue(self, entry: dict) -> None:
        """A page for a person to look at: ids, reasons and short evidence, no page text."""
        path = self.path('issues.jsonl')
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a', encoding='utf-8', newline='\n') as issues:
            issues.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + '\n')

    def ledger(self) -> list[dict]:
        path = self.path('ledger.jsonl')
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

    def spent_usd(self, provider: str = 'anthropic') -> float:
        """What one provider was paid by this ledger: the Claude credit's spend guard never counts the course key's."""
        return sum(entry.get('cost_usd', 0.0) for entry in self.ledger() if entry.get('provider', 'anthropic') == provider)

    def save_manifest(self, manifest: dict) -> None:
        self._write(self.path('batches', manifest['local_id'] + '.json'),
                    json.dumps(manifest, indent=1, ensure_ascii=False, default=str).encode('utf-8'))

    def manifests(self) -> list[dict]:
        folder = self.path('batches', 'x').parent
        if not folder.exists():
            return []
        return [json.loads(path.read_text(encoding='utf-8')) for path in sorted(folder.glob('*.json'))]
