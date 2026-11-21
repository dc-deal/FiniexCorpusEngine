"""Where readings live: content-addressed files under a git-ignored root, one root per mirror.

Pages read from the licensed archive go to `_work/licensed/vision`, pages of the free corpus to
`_work/free/vision` (decided 2026-10-29: every top-level folder starting with '_' is
git-ignored). A store refuses a root inside the repository that git would track: one wrong ignore
rule has to stop the runner, not publish book text. The check follows links to where the data really
lies, and every work tree of this repository counts as its own (a linked worktree reaches the main
tree's `_work` through a junction); any other repository is refused. A path inside the store must lie
under its root: one of plain name parts (a key, a hash, a file name) is joined as it stands, since no
such part can leave the root, and any other is resolved and checked (issue #5: resolving every path cost
an export 154,000 system calls, the most of its 32 minutes in the view's container).

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
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from backend.configuration import data_paths

REPO = Path(__file__).resolve().parents[4]
REPLACE_WAITS = (0.2, 0.5, 1.0)  # seconds between tries of a rename Windows refuses; the last try raises
ROOTS = {'licensed': data_paths.LICENSED_WORKING / 'vision',
         'free': data_paths.FREE_WORKING / 'vision'}


class UnsafeRootError(RuntimeError):
    """A store root, or a path inside it, that could reach git or lies outside the root."""


# a part of a path that cannot leave its folder: no separator, no drive, not '.' or '..', starting with a letter or digit
PLAIN_PART = re.compile(r'[A-Za-z0-9][A-Za-z0-9._+-]*')


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
        # a plain path is joined, never resolved (issue #5), so no folder of the store may be a link out of it
        for child in root.iterdir():
            if child.is_symlink() or child.is_junction():
                raise UnsafeRootError(f'{child} is a link: a store holds its own folders')
        self.root = root

    def path(self, *parts: str) -> Path:
        if parts and all(PLAIN_PART.fullmatch(part) for part in parts):
            return self.root.joinpath(*parts)
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


class Snapshot:
    """One store as one export reads it (issue #5): every record read once, each text at most once, and the classes the
    validator gave kept across runs by everything they depend on (`ClassCache`). Everything else is the store's own; nothing is
    written through it that the store would not write. An export ran over all records five times and over every text twice."""

    def __init__(self, store: 'Store'):
        self._store = store
        self._records: list[dict] | None = None
        self._by_key: dict[str, dict] | None = None
        self._texts: dict[str, str | None] = {}
        self._text_keys: set[str] | None = None
        self.class_cache = ClassCache(store, self.has_text)

    def __getattr__(self, name):
        return getattr(self._store, name)

    def readings(self) -> list[dict]:
        if self._records is None:
            self._records = self._store.readings()
        return list(self._records)

    def reading(self, key: str) -> dict | None:
        if self._by_key is None:
            self._by_key = {record['reading_key']: record for record in self.readings() if record.get('reading_key')}
        return self._by_key.get(key) or self._store.reading(key)

    def reading_text(self, key: str) -> str | None:
        if key not in self._texts:
            self._texts[key] = self._store.reading_text(key)
        return self._texts[key]

    def has_text(self, key: str) -> bool:
        """Whether the store holds this reading's text, from one walk of its folder: a cache keyed by the text's hash the
        record holds must not answer for a text that is gone (the review of #5: a missing text was masked, or crashed it)."""
        if self._text_keys is None:
            folder = self._store.path('readings', 'x').parent
            self._text_keys = {path.stem for path in folder.glob('*/*.md')} if folder.exists() else set()
        return key in self._text_keys


class ClassCache:
    """A stored reading's class under today's validator and the format check's errors, kept between runs (issue #5: the
    validator ran over every reading on every export, twice, 71 and 52 of its seconds). Kept by everything the class depends on: the reading's own fields the check
    reads, its text's sha256 as its record holds it (a stored reading is never rewritten) and a hash of the validator's code;
    another validator starts the cache anew."""

    NAME = 'classes.json'

    def __init__(self, store: 'Store', has_text=lambda key: True):
        self._path = store.path('cache', self.NAME)
        self._code = validator_code_hash() + ':class-and-errors'
        self._has_text = has_text
        saved = read_cache(self._path)
        self._classes: dict[str, list] = saved.get('classes', {}) if saved.get('code') == self._code else {}
        self._changed = False

    def key(self, record: dict) -> str | None:
        if not record.get('text_sha256') or not self._has_text(record.get('reading_key')):
            return None
        return '|'.join(str(part) for part in (record.get('form'), record.get('work'), record.get('pdf_page'),
                                                tuple(record.get('image_size') or ()), record.get('stop_reason'),
                                                record['text_sha256']))

    def get(self, record: dict) -> str | None:
        """The class, or None where the cache does not hold this reading."""
        key = self.key(record)
        return self._classes[key][0] if key and key in self._classes else None

    def errors(self, record: dict) -> list[str] | None:
        """The format check's errors, or None where the cache does not hold this reading."""
        key = self.key(record)
        return list(self._classes[key][1]) if key and key in self._classes else None

    def put(self, record: dict, result_class: str, errors: list[str]) -> None:
        key = self.key(record)
        if key and self._classes.get(key) != [result_class, list(errors)]:
            self._classes[key] = [result_class, list(errors)]
            self._changed = True

    def save(self) -> None:
        if self._changed:
            write_cache(self._path, {'code': self._code, 'classes': self._classes})
            self._changed = False


def read_cache(path: Path) -> dict:
    """A cache file's content, or an empty cache where it is missing or cannot be read (the review of #5: a half-written
    file must cost speed, never block every later export)."""
    try:
        found = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def write_cache(path: Path, content: dict) -> bool:
    """Write a cache whole, under a name of its own writer, so two writers (the view's export and one from the command
    line) never share a temporary file. A cache that cannot be written is said and skipped: it only costs speed."""
    part = path.with_name(f'.{path.name}.{os.getpid()}.{threading.get_ident()}.part')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        part.write_text(json.dumps(content), encoding='utf-8')
        for wait in (*REPLACE_WAITS, None):
            try:
                os.replace(part, path)
                return True
            except PermissionError:
                if wait is None:
                    raise
                time.sleep(wait)
    except OSError as error:
        print(f'the cache {path.name} was not written ({type(error).__name__}); the next run computes it again', file=sys.stderr)
        part.unlink(missing_ok=True)
    return False


def loaded_code_hash(*items) -> str:
    """A hash of code as this process loaded it, not as its file reads now (the review of #5: a running view whose code was
    edited on disk would keep old answers under the new code's name). A module counts its own functions and classes, a class
    its methods, a function its bytecode, names and constants; any other value its repr. File names and line numbers are left
    out, so the view's container and this machine share their caches."""
    import types

    digest = hashlib.sha256()

    def stable(const) -> str:
        # a set's order changes with every start of Python (string hashing is salted), so its members are sorted
        if isinstance(const, (set, frozenset)):
            return 'set(' + ','.join(sorted(stable(member) for member in const)) + ')'
        if isinstance(const, tuple):
            return 'tuple(' + ','.join(stable(member) for member in const) + ')'
        return repr(const)

    def code(value) -> None:
        digest.update(value.co_code)
        digest.update(repr((value.co_names, value.co_varnames)).encode('utf-8'))
        for const in value.co_consts:
            code(const) if isinstance(const, types.CodeType) else digest.update(stable(const).encode('utf-8'))

    def visit(item) -> None:
        if isinstance(item, types.ModuleType):
            for name in sorted(vars(item)):
                value = vars(item)[name]
                if getattr(value, '__module__', None) == item.__name__ and isinstance(value, (type, types.FunctionType)):
                    visit(value)
        elif isinstance(item, type):
            digest.update(item.__qualname__.encode('utf-8'))
            for name in sorted(vars(item)):
                value = vars(item)[name]
                function = getattr(value, '__func__', None) or getattr(value, 'fget', None) or value
                if isinstance(function, types.FunctionType):
                    visit(function)
        elif isinstance(item, types.FunctionType):
            digest.update(item.__qualname__.encode('utf-8'))
            code(item.__code__)
        else:
            digest.update(stable(item).encode('utf-8'))

    for item in items:
        visit(item)
    return digest.hexdigest()


@functools.cache
def validator_code_hash() -> str:
    """The validator as this process runs it: the contract's parser and checks, its vocabulary, and the reading check that
    classifies; a change to any of them is another validator."""
    from backend.conversion.contract import page_contract
    from backend.conversion.reading import vision_batches

    return loaded_code_hash(page_contract, json.dumps(page_contract.VOCAB, sort_keys=True), vision_batches._check_reading,
                            vision_batches.check_reading, vision_batches.DECLINED.pattern)
