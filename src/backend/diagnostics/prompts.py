"""The prompts tab (the operator's 148.a): every version of the reader's and the judge's instructions, as the core keeps them.

Read, never written, from the core's own files: `prompt_versions.json` (each version's role, files, state, the day it was
frozen and why), the prompt files beside it, and `frozen_contract.json`, whose sha256 of each file is what a test in the
core holds them to. Each file's sha256 is taken now and set beside the frozen one, so a file changed since shows. A
version's change from the one before it in its role is a line diff (`difflib`, the standard library), so judge/1, judge/2 and
judge/3, one sentence apart each, show that sentence plainly; the view computes nothing.
"""

import difflib
import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel

from backend.conversion.judge import page_judge

CONVERSION = page_judge.CONVERSION
VERSIONS = page_judge.VERSIONS
FROZEN = CONVERSION / 'frozen_contract.json'


class DiffPart(BaseModel):
    text: str
    changed: bool


class DiffLine(BaseModel):
    kind: Literal['same', 'added', 'removed']
    text: str
    # where a line was replaced by another, its words, the changed ones marked: a sentence added to a long paragraph line
    # is then the sentence alone, not the whole line twice
    parts: list[DiffPart] | None = None


class PromptFile(BaseModel):
    path: str  # as the registry names it, relative to the conversion package
    part: str | None = None  # what the file is, a key of the registry's `parts`: rules, format, judge or classcheck
    text: str
    sha256: str  # of the file as it is now
    frozen_sha256: str | None  # as the frozen contract holds it; None for a file it does not list
    # the change from the previous version's file at the same place; None for a role's first version
    diff: list[DiffLine] | None


class PromptOrigin(BaseModel):
    """Who wrote a version and when, where it came from and how that is known (#18, the registry's `origin`)."""

    author_kind: str | None = None  # model, person or vendor; None where nobody knows
    author: str | None = None
    written_on: str | None = None
    source: str | None = None
    evidence: str | None = None


class PromptVersion(BaseModel):
    role: str  # reader, judge, classcheck, correction, reader-agent, judge-agent
    version: str
    title: str | None = None
    model: str | None = None  # the model the version is given to
    state: str  # prototype, active or retired
    frozen_on: str | None
    why: str | None
    previous: str | None  # the version before it in its role
    files: list[PromptFile]  # [] for a version whose text nobody holds (a vendor's package, an agent's unknown prompt)
    origin: PromptOrigin | None = None


class PromptPart(BaseModel):
    """What a prompt file is, as the registry's `parts` names it: its key, its name before the colon, the rest after."""

    key: str
    label: str
    about: str | None


class PromptList(BaseModel):
    about: str | None
    parts: list[PromptPart] = []  # in the registry's order: the view's tabs
    versions: list[PromptVersion]


def part_of(key: str, says: str) -> PromptPart:
    label, _, about = says.partition(': ')
    return PromptPart(key=key, label=label, about=about or None)


def words_changed(removed: str, added: str) -> tuple[list[DiffPart], list[DiffPart]]:
    """The two lines' words, spaces kept, each marked where it differs from the other line's."""
    old, new = re.split(r'(\s+)', removed), re.split(r'(\s+)', added)
    old_parts, new_parts = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if i2 > i1:
            old_parts.append(DiffPart(text=''.join(old[i1:i2]), changed=tag != 'equal'))
        if j2 > j1:
            new_parts.append(DiffPart(text=''.join(new[j1:j2]), changed=tag != 'equal'))
    return old_parts, new_parts


def diff_of(before: str, after: str) -> list[DiffLine]:
    """The line diff of two texts; a removed line followed by an added one is a replacement, and carries its words."""
    kinds = {' ': 'same', '+': 'added', '-': 'removed'}
    lines = [DiffLine(kind=kinds[line[0]], text=line[2:]) for line in difflib.ndiff(before.splitlines(), after.splitlines())
             if line[0] in kinds]
    for at in range(len(lines) - 1):
        if lines[at].kind == 'removed' and lines[at + 1].kind == 'added':
            lines[at].parts, lines[at + 1].parts = words_changed(lines[at].text, lines[at + 1].text)
    return lines


def earlier_file(before: dict | None, at: int, part: str | None) -> str | None:
    """The previous version's file this one changes: the one of the same part, else the one at the same place."""
    if not before:
        return None
    same_part = [path for path in before['files'] if part and (before.get('parts') or {}).get(path) == part]
    if same_part:
        return same_part[0]
    return before['files'][at] if at < len(before['files']) else None


def prompt_list() -> PromptList:
    """Every version in the registry's order, each file with its part, its text, its sha256 now and frozen, and its change
    from the version before it in its role, and its origin as the core gives it (`page_judge.prompt_origins`: the registry's,
    this machine's own laid over it, so a clone says "kept on this machine" where this machine names the author); and the
    parts, the view's tabs."""
    from backend.conversion.judge import page_judge

    origins = page_judge.prompt_origins()
    registry = json.loads(VERSIONS.read_text(encoding='utf-8'))
    frozen = json.loads(FROZEN.read_text(encoding='utf-8')).get('sha256', {})
    listed: list[PromptVersion] = []
    last_of: dict[str, dict] = {}
    for entry in registry['versions']:
        before = last_of.get(entry['role'])
        files = []
        for at, path in enumerate(entry['files']):
            raw = (CONVERSION / path).read_bytes()
            text = raw.decode('utf-8')
            part = (entry.get('parts') or {}).get(path)
            earlier = earlier_file(before, at, part)
            files.append(PromptFile(path=path, part=part, text=text, sha256=hashlib.sha256(raw).hexdigest(),
                                    frozen_sha256=frozen.get(path),
                                    diff=diff_of((CONVERSION / earlier).read_text(encoding='utf-8'), text) if earlier else None))
        listed.append(PromptVersion(role=entry['role'], version=entry['version'], title=entry.get('title'),
                                    model=entry.get('model'), state=entry['state'], frozen_on=entry.get('frozen_on'),
                                    why=entry.get('why'), previous=before['version'] if before else None, files=files,
                                    origin=PromptOrigin(**origins[entry['version']]) if origins.get(entry['version']) else None))
        last_of[entry['role']] = entry
    parts = [part_of(key, says) for key, says in (registry.get('parts') or {}).items()]
    return PromptList(about=registry.get('about'), parts=parts, versions=listed)
