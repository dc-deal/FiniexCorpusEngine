"""Logging and monitoring of the chat turns (phase 10).

Three things, all derived from the dict `chat_agent.ask` returns, so that what the interface shows,
what the log holds and what the monitoring counts are one record (one message shape end to end):

    security_checks   every safety check of a turn, each with its outcome
    write             one JSON line per turn, appended to the conversation's own file in logs/
                      (git-ignored), named by its start and its id: 2026-10-01_15-12-04_f99c2ef4.jsonl
    summary           counts over every file in logs/, for the monitoring view
    conversations     the past conversations, to reopen (`messages`), download (`transcript`) or delete

Why not a tracing service: LangSmith, LangChain's own (lesson 1, "for observability and
evaluation"), was checked first (2026-10-01). It was not chosen because every question, prompt and
passage would leave the machine for a further service, the reviewer could not see any of it in the
repository, and the app has to run without an account. A JSON line per turn keeps all of it local
and readable. Lines are appended with `open(..., 'a')` rather than the `logging` module: its
handlers are process-wide and would need guarding against a second set-up in one process, for no feature used here.
"""

import json
import re
import statistics
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from backend.configuration import data_paths

LOG_DIR = data_paths.LOGS

# The checks in the order a turn meets them. `applied` marks a fixed rule with no verdict of its own
# per turn (whether it holds is measured over the dataset, e.g. q30); `not reached` a check the turn
# never got to, because an earlier step ended it or took another path.
CHECKS = {
    'input': 'Input check: not empty, not too long',
    'agent_tool': 'The agent answered through a tool',
    'call_limit': 'Model and tool calls per message within the cap',
    'tool_input': 'Tool inputs accepted',
    'route': 'Router: on topic and not harmful',
    'relevance': 'Relevance floor',
    'passages_as_data': 'Passages are data, not instructions (prompt rule)',
    'quotes': 'Quotes appear word for word in their passage',
    'disclaimer': 'Disclaimer added by code',
    'no_html': 'Output rendered without HTML',
}
STATUSES = ('passed', 'warning', 'blocked', 'applied', 'not reached')
# The tools whose input can be refused: the two calculations, and the search server's, which answer state "error" (98.c).
CHECKED_TOOLS = ('performance_metrics', 'position_size', 'search', 'semantic_search', 'open_page', 'page_image', 'works')

_lock = threading.Lock()


def _check(check: str, status: str, detail: str = '') -> dict:
    return {'check': check, 'name': CHECKS[check], 'status': status, 'detail': detail}


def security_checks(result: dict) -> list[dict]:
    """Every check of one turn, in order, each `passed`, `warning`, `blocked`, `applied` or `not reached`.

    Derived from what the turn recorded, so a check can never be reported without having run.
    """
    kind = result.get('kind')
    turn = result.get('turn') or {}
    behaviour = turn.get('behaviour')
    calls = result.get('tool_calls') or []
    checks = []

    if kind == 'invalid':
        checks.append(_check('input', 'blocked', result.get('text', '')))
        checks += [_check(name, 'not reached', 'the input was refused') for name in CHECKS if name != 'input']
        return checks
    checks.append(_check('input', 'passed', f"{len(result.get('question') or '')} characters"))

    if result.get('fallback'):
        checks.append(_check('agent_tool', 'warning', 'the agent answered without a tool; its text was discarded '
                                                      'and the message went to the knowledge base'))
    else:
        checks.append(_check('agent_tool', 'passed', ', '.join(c['name'] for c in calls) or '—'))

    counted = f"{result.get('model_calls') or 0} model and {len(calls)} tool calls"
    if result.get('call_limit_reached'):
        checks.append(_check('call_limit', 'blocked', f"{result['call_limit_reached']} ({counted})"))
    else:
        checks.append(_check('call_limit', 'passed', counted))

    tool_calls = [c for c in calls if c['name'] in CHECKED_TOOLS]
    refused = [c for c in tool_calls if _refused(c.get('result') or {})]
    if not tool_calls:
        checks.append(_check('tool_input', 'not reached', 'no calculation and no tool of the search server'))
    elif len(refused) == len(tool_calls):
        checks.append(_check('tool_input', 'blocked', str(refused[-1]['result'].get('content', ''))[:300]))
    elif refused:
        checks.append(_check('tool_input', 'warning', f'{len(refused)} call(s) refused, then corrected by the agent'))
    else:
        checks.append(_check('tool_input', 'passed', ', '.join(c['name'] for c in tool_calls)))

    if not turn:
        reason = 'a calculation or a tool of the search server, no answer from the knowledge base'
        checks += [_check(name, 'not reached', reason) for name in ('route', 'relevance', 'passages_as_data', 'quotes')]
    elif behaviour in ('decline_off_topic', 'decline_harmful'):
        label = 'off-topic' if behaviour == 'decline_off_topic' else 'harmful'
        checks.append(_check('route', 'blocked', f'{label}: declined with a fixed text, nothing searched'))
        checks += [_check(name, 'not reached', 'declined by the router')
                   for name in ('relevance', 'passages_as_data', 'quotes')]
    else:
        route = (turn.get('plan') or {}).get('route', 'search')
        checks.append(_check('route', 'passed', f'route {route}'))
        relevance, floor = turn.get('relevance'), turn.get('relevance_floor')
        if relevance is None:
            checks.append(_check('relevance', 'warning', 'no similarity: the search found nothing'))
        elif turn.get('below_floor'):
            checks.append(_check('relevance', 'warning', f'best similarity {relevance:.3f} below {floor}: '
                                                         'the model was told to check the passages carefully'))
        else:
            checks.append(_check('relevance', 'passed', f'best similarity {relevance:.3f}'
                                                        + (f' ≥ {floor}' if floor is not None else '')))
        generated = 'prompt' in turn
        checks.append(_check('passages_as_data', 'applied' if generated else 'not reached',
                             'stated in the generator prompt' if generated else 'no answer was generated'))
        checks.append(_quote_check(turn))

    if result.get('disclaimer') or turn.get('disclaimer'):
        checks.append(_check('disclaimer', 'passed', 'added below the answer'))
    else:
        checks.append(_check('disclaimer', 'not reached', 'no answer or calculation was shown'))
    checks.append(_check('no_html', 'applied', "Markdown without HTML; a page's text as plain text"))
    return checks


def _refused(result: dict) -> bool:
    artifact = result.get('artifact')
    return result.get('status') == 'error' or (isinstance(artifact, dict) and artifact.get('state') == 'error')


def _quote_check(turn: dict) -> dict:
    behaviour = turn.get('behaviour')
    if behaviour == 'error' or 'prompt' not in turn:
        return _check('quotes', 'not reached', 'no answer was generated')
    if behaviour == 'not_found':
        return _check('quotes', 'passed', 'nothing found, so no quote is shown')
    kept, dropped = len(turn.get('quotes') or []), turn.get('quotes_dropped') or 0
    if not kept:
        return _check('quotes', 'warning', f'no quote could be verified ({dropped} dropped)')
    if dropped:
        return _check('quotes', 'warning', f'{kept} kept, {dropped} dropped: not in their passage word for word')
    return _check('quotes', 'passed', f'{kept} of {kept} kept')


# A conversation's file, as `conversation_log` names it. The folder holds other files too: the search server's call log
# (`search_server.jsonl`) sits beside the turns, and until 5 Nov it was listed as a past conversation, counted as turns,
# could be opened and appended to (page text in a log meant to hold none) and deleted (found by the review of 99.a).
CONVERSATION_FILE = re.compile(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_[0-9A-Za-z_-]{1,8}\.jsonl')


def conversation_files(directory: Path) -> list[Path]:
    """The conversations in a log folder: the files named as `conversation_log` names them, and no other."""
    return sorted(path for path in directory.glob('*.jsonl') if CONVERSATION_FILE.fullmatch(path.name))


def conversation_log(thread_id: str, started: datetime | None = None, directory: Path | None = None) -> Path:
    """The file one conversation is logged to: its local start time and the first 8 characters of its id.

    One file per conversation (the operator, 2026-10-01), so a chat can be read on its own, in order. Its id must begin with 1 to 8
    characters of `[0-9A-Za-z_-]`, the ones `CONVERSATION_FILE` reads back, so a file name taken from a caller never leaves
    the folder (line 2's request, 5 Nov; its route checks for a UUID as well).
    """
    if not re.fullmatch(r'[0-9A-Za-z_-]{1,8}', str(thread_id)[:8]):
        raise ValueError(f'a conversation id must begin with 1 to 8 of [0-9A-Za-z_-], not {str(thread_id)[:8]!r}')
    started = started or datetime.now()
    return (directory or LOG_DIR) / f"{started:%Y-%m-%d_%H-%M-%S}_{thread_id[:8]}.jsonl"


def stored(result: dict, *, keep_pixels: bool = False) -> dict:
    """A turn as the log stores it: a tool's artifact that *is* the turn, the opened section or the server's answer kept
    once, not two or three times; a page image by its type and size, unless `keep_pixels` (an interface that shows it).

    Public since line 2's chat route returns the same shape (its request 4, 5 Nov). The result itself is never changed."""
    server = result.get('server')
    shown = [result.get('turn'), result.get('section'), (server or {}).get('answer')]
    calls = [{**c, 'result': {**c['result'], 'artifact': 'the turn, section or server answer of this record'}}
             if any(c.get('result', {}).get('artifact') is part for part in shown if part is not None) else c
             for c in result.get('tool_calls') or []]
    if not keep_pixels and server and isinstance(server.get('answer', {}).get('sent_image'), dict):
        image = server['answer']['sent_image']
        logged = {'mime_type': image.get('mime_type'), 'base64_characters': len(image.get('data') or ''), 'not_logged': 'pixels'}
        server = {**server, 'answer': {**server['answer'], 'sent_image': logged}}
    return {**result, 'server': server, 'tool_calls': calls}


def write(result: dict, thread_id: str, path: Path) -> None:
    """Append the whole turn as one JSON line: when, which conversation, and everything it recorded, in the shape of
    `stored`: each artifact once, a page image without its pixels, since the log is for reading a turn again and the page
    is in the server."""
    record = {'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'thread_id': thread_id, **stored(result)}
    # ASCII JSON: a lone surrogate in a question could not be written as UTF-8 and lost the turn after it was paid for, and a
    # line separator (U+2028, U+0085) in it split the record (the review of 99.a, 5 Nov). Every reader decodes the escapes.
    line = json.dumps(record, default=str)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, path.open('a', encoding='utf-8') as log:
        log.write(line + '\n')


def _read(path: Path) -> tuple[list[dict], int]:
    """The records of one log file, and how many lines could not be read."""
    records, unreadable = [], 0
    for line in path.read_text(encoding='utf-8').split('\n'):  # not splitlines(): it also splits at U+2028 and U+0085
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            unreadable += 1
    return records, unreadable


# Past conversations (17.a, the operator 2026-10-01): the log files already hold every turn in the shape the
# interface renders (one message shape end to end), so a conversation is reopened from its file.

def conversations(directory: Path | None = None) -> list[dict]:
    """Every logged conversation, newest first: its file, id, local start, first question and turns."""
    found = []
    for path in conversation_files(directory or LOG_DIR):
        records, _ = _read(path)
        if not records:
            continue
        found.append({'path': path, 'thread_id': records[0].get('thread_id'), 'started': path.stem[:19],
                      'first_question': records[0].get('question') or '', 'turns': len(records)})
    return sorted(found, key=lambda c: c['path'].name, reverse=True)  # names begin with the start time


def messages(path: Path) -> list[dict]:
    """A logged conversation as the interface keeps it: each question, then the result it got."""
    shown = []
    for record in _read(path)[0]:
        result = {k: v for k, v in record.items() if k not in ('at', 'thread_id')}
        shown += [{'role': 'user', 'content': record.get('question') or ''}, {'role': 'assistant', 'result': result}]
    return shown


def delete_conversation(path: Path, directory: Path | None = None) -> None:
    """Delete one conversation's log file; nothing outside the log folder, and only a .jsonl file."""
    folder = (directory or LOG_DIR).resolve()
    target = Path(path).resolve()
    if target.parent != folder or not CONVERSATION_FILE.fullmatch(target.name):
        raise ValueError(f'not a conversation log in {folder}: {target}')
    target.unlink()


def transcript(path: Path) -> str:
    """A logged conversation as Markdown, to download and read: questions, answers, verified quotes."""
    lines = [f'# Conversation of {path.stem[:10]} {path.stem[11:19].replace("-", ":")}', '']
    for record in _read(path)[0]:
        turn = record.get('turn') or {}
        server = (record.get('server') or {}).get('answer') or {}
        lines += [f"## {record.get('question') or ''}", '',
                  turn.get('answer') or (record.get('section') or {}).get('text') or server.get('text')
                  or (f"*{record['server']['tool']}: {server.get('state')}*" if server else '') or record.get('text') or '', '']
        for quote in turn.get('quotes') or []:
            lines += [f"> {quote['text']}", '', f"— [{quote['passage']}] {quote['citation']['text']} · "
                                                f"{quote['citation'].get('licence') or ''}", '']
        if turn.get('gaps'):
            lines += [f"*Not covered by the sources:* {turn['gaps']}", '']
        disclaimer = turn.get('disclaimer') or record.get('disclaimer')
        lines += [f'*{disclaimer}*', ''] if disclaimer else []
        lines += [f"<sub>turn {record.get('turn_id') or '—'} · {record.get('at') or ''}</sub>", '']
    return '\n'.join(lines)


def summary(path: Path | None = None) -> dict | None:
    """Counts over every turn logged: all files of a log folder, or one file; None when there is none.

    Unreadable lines are counted, not fatal.
    """
    path = path or LOG_DIR
    files = conversation_files(path) if path.is_dir() else [path] if path.exists() else []
    if not files:
        return None
    records, unreadable = [], 0
    for file in files:
        found, bad = _read(file)
        records += found
        unreadable += bad
    records.sort(key=lambda r: r.get('at') or '')
    outcomes = Counter((r.get('turn') or {}).get('behaviour') or r.get('kind') for r in records)
    checks = {name: Counter() for name in CHECKS}
    for record in records:
        for check in record.get('security') or []:
            if check.get('check') in checks:
                checks[check['check']][check['status']] += 1
    seconds = [r['seconds'] for r in records if isinstance(r.get('seconds'), (int, float))]
    costs = [r['usd'] for r in records if isinstance(r.get('usd'), (int, float))]
    lengths = [(r.get('turn') or {}).get('answer_words') for r in records]
    limits = [(r.get('turn') or {}).get('word_limit') for r in records]
    measured = [(w, limit) for w, limit in zip(lengths, limits) if isinstance(w, int) and isinstance(limit, int)]
    return {
        'turns': len(records),
        'conversations': len({r.get('thread_id') for r in records}),
        'files': len(files),
        'unreadable_lines': unreadable,
        'answer_words_median': statistics.median(w for w, _ in measured) if measured else None,
        'answers_over_limit': sum(w > limit for w, limit in measured),
        'answers_measured': len(measured),
        'first': records[0].get('at') if records else None,
        'last': records[-1].get('at') if records else None,
        'outcomes': dict(outcomes.most_common()),
        'checks': {name: dict(counts) for name, counts in checks.items()},
        'seconds_median': statistics.median(seconds) if seconds else None,
        'seconds_max': max(seconds) if seconds else None,
        'usd_total': sum(costs),
    }
