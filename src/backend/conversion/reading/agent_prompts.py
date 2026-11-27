"""The prompts that start a Claude Code session's agents, rendered by code (#17, decision 22.a, 27 Nov 2026).

Until 26 Nov each agent's prompt was written anew for its run from a skill's text, with notes for that run, so no two
runs got the same text and none was kept with what it made. Now a registered template (`prompt_versions.json`, roles
`reader-agent` and `judge-agent`) is filled by code with the run's details, the filled text is kept in the store by its
sha256, and every request made for the agent records the template's version, the details and that sha256. A run is then
"judge-agent/1 with these details", and can be asked again with the same prompt.

The details are the run's own: folders, a batch file, the repository's interpreter, and notes. They never go into a tracked
file, since they can name licensed works; the template holds placeholders only.
"""

import json
import string
import sys
from pathlib import Path

from backend.conversion.judge import page_judge

ROLES = ('reader-agent', 'judge-agent')
REPOSITORY = Path(__file__).resolve().parents[4]  # the repository root, filled in at run time, never written into a template
PYTHON = REPOSITORY / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')


def template(version: str) -> str:
    """The template text of a registered agent prompt version; an entry without a file (a retired or lost one) has none."""
    entry = next((entry for entry in json.loads(page_judge.VERSIONS.read_text(encoding='utf-8'))['versions']
                  if entry['role'] in ROLES and entry['version'] == version), None)
    if entry is None or not entry['files']:
        raise ValueError(f'no agent prompt template {version!r} in {page_judge.VERSIONS.name}')
    return ''.join((page_judge.CONVERSION / path).read_bytes().decode('utf-8') for path in entry['files'])


def placeholders(version: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template(version)) if name}


def render(version: str, **details: str) -> str:
    """The template filled with the run's details; every placeholder must be given and nothing else, so a prompt never
    silently lacks a part. A note, where given, stands on lines of its own."""
    wanted = placeholders(version)
    if set(details) != wanted:
        raise ValueError(f'{version} takes {sorted(wanted)}, not {sorted(details)}')
    filled = {name: (f'\n{value.strip()}\n' if name == 'notes' and value.strip() else value) for name, value in details.items()}
    return template(version).format(**filled)


def kept(store, version: str, **details: str) -> tuple[str, dict]:
    """The rendered prompt, kept in the store, and the record every request made for the agent carries."""
    text = render(version, **details)
    return text, {'version': version, 'sha256': store.put_prompt(text), 'details': details}
