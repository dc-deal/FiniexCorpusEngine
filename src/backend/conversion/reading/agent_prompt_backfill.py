"""Which session agent's prompt made each session reading and verdict before agent prompts were rendered by code (#17, 22.a).

From 19 to 26 Nov each agent's prompt was written anew for its run, and nothing kept it beside what it made. The prompts were
saved from the session transcripts on 27 Nov (`_work/prompt_history/agent_calls.jsonl`, local: they name licensed works).
A reader's prompt names its batch file, which lists its page folders; a judge's prompt lists its folders. A record is tied
to the call whose folders hold its page and work and which came last before the record was stored: derived, by the folders
and the time, and said so. The prompt itself is kept in the record's own store by its sha256.

Stored records are never changed: the result is a report in each store (`agent_prompts_backfill.json`), read by the export
beside a record's own `agent_prompt`. A session record no saved call can be tied to points at `reader-agent/unknown` or
`judge-agent/unknown`, the registry's entries without text.

    python -m backend.conversion.reading.agent_prompt_backfill
"""

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from backend.configuration import data_paths
from backend.conversion.store.reading_store import open_store

CALLS = data_paths.WORKING / 'prompt_history' / 'agent_calls.jsonl'
REPORT = 'agent_prompts_backfill.json'
FOLDER = re.compile(r'(?:LAB-[A-Z0-9-]+__)?([\w.-]+?)__p(\d{4})(?:__a(\d+))?\b')
BATCH_FILE = re.compile(r'listed in `([^`]+)`')
VERSIONS = {'reader': ('reader-agent/0', 'reader-agent/unknown'), 'judge': ('judge-agent/0', 'judge-agent/unknown')}


def _moment(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _mirror(prompt: str) -> str | None:
    """The store a call's pages lie in, from the paths its prompt names."""
    flat = prompt.replace('\\', '/')
    return 'licensed' if '_work/licensed/' in flat else 'free' if '_work/free/' in flat else None


def pages_of(call: dict) -> set[tuple[str, int, int]]:
    """The (work, PDF page, attempt) a call worked on: the folders its agent wrote into, where its own transcript was saved
    (exact); else a reader's from its batch file, a judge's from its own text (batch files were reused by later runs, so the
    first is the one to trust)."""
    if call.get('written') is not None:
        return {(work, int(page), int(attempt or 0)) for work, page, attempt in FOLDER.findall(' '.join(call['written']))}
    text = call['prompt']
    if call['kind'] == 'reader':
        named = BATCH_FILE.search(text)
        if not named or not Path(named.group(1)).exists():
            return set()
        text = Path(named.group(1)).read_text(encoding='utf-8')
    return {(work, int(page), int(attempt or 0)) for work, page, attempt in FOLDER.findall(text)}


def session_records(store) -> dict[str, list[dict]]:
    """The store's session readings and session verdicts, by kind."""
    found = {'reader': [], 'judge': []}
    for record in store.readings():
        if record.get('mode') != 'session':
            continue
        if record.get('kind', 'reading') == 'reading':
            found['reader'].append(record)
        elif record.get('kind') == 'judge':
            found['judge'].append(record)
    return found


def backfill(calls: list[dict] | None = None) -> dict[str, Counter]:
    """Tie every session record of both stores to the saved call that made it, write each store's report, and count."""
    calls = calls if calls is not None else [json.loads(line) for line in CALLS.read_text(encoding='utf-8').splitlines()]
    # an agent's own transcript names what it wrote; the parent's call is used only where no such transcript was saved
    own = [call for call in calls if call.get('source') == 'subagent']
    calls = own or calls
    outcome = {}
    for mirror in ('free', 'licensed'):
        store = open_store(mirror)
        # an agent's store from where it wrote, else from the paths its prompt names (the first nights' named none)
        mine = sorted((call for call in calls if call.get('timestamp')
                       and (call.get('mirror') or _mirror(call['prompt'] or '')) == mirror),
                      key=lambda call: call['timestamp'])
        tied, counts = {}, Counter()
        for kind, records in session_records(store).items():
            made, lost = VERSIONS[kind]
            for record in records:
                if record.get('agent_prompt'):
                    continue  # rendered by code and recorded when it was made
                place = (record.get('work'), record.get('pdf_page'), record.get('attempt', 0) if kind == 'reader' else 0)
                before = [call for call in mine if call['kind'] == kind and _moment(call['timestamp']) <= _moment(record['stored_at'])
                          and (place in pages_of(call) or (kind == 'judge' and place[:2] in {page[:2] for page in pages_of(call)}))]
                if before:
                    call = before[-1]
                    exact = call.get('written') is not None
                    tied[record['reading_key']] = {
                        'version': made, 'sha256': store.put_prompt(call['prompt']),
                        'derived': 'its agent wrote this page' if exact else 'by its folders and the time',
                        'agent': call.get('transcript') if exact else call.get('tool_use_id')}
                    counts[f'{kind}: tied'] += 1
                else:
                    tied[record['reading_key']] = {'version': lost, 'sha256': None, 'derived': 'no saved call holds its page'}
                    counts[f'{kind}: lost'] += 1
        store.write_report(REPORT, {'about': __doc__.split('\n\n')[0], 'records': tied})
        outcome[mirror] = counts
    return outcome


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    for mirror, counts in backfill().items():
        print(f'{mirror}: {dict(sorted(counts.items()))}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
