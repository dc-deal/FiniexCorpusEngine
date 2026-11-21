"""Run vision readings: free checks, a smoke test, and Message Batches (submit, collect, status).

The commands are idempotent, because a process that polls for hours on a laptop does not
survive. `submit` writes a manifest before the batch is created; `collect` makes one pass over
ended batches, stores every result before it prints anything and appends to the ledger; with
`--delete` it also deletes each batch at Anthropic once all its results are stored (results stay
there 29 days otherwise). Running `collect` twice changes nothing.

The spend guard refuses a submission when the ledgers' actual cost, plus 1.3 x the estimate of
every batch still running, plus 1.3 x the new one, would pass the cap. A batch running at
Anthropic that no local manifest knows also stops a submission: its cost cannot be counted.

A reading is never bought twice: any stored result blocks its key. `--retry-malformed` is stage 1
of the check flow: it re-reads a page whose stored reading of that cell broke the format, once, as
attempt 1, which is a new key. Nothing else is ever re-sent. A refused or blocked page is final, in
every cell: no splitting, no paraphrasing, no second model, no arguing in the prompt.

A batch holds requests of a kind, `reading` unless an entry says otherwise. `KINDS` says how a kind
builds its parameters and checks its answer; `send_entries` and `collect` are the same for all.
Manifests of the old contract v1.1 stay known, so `collect --delete` and `status` still work on
them, and a result of such an entry is stored unchecked, since that contract is archived.

Console output carries ids, counts and costs, never page text: the pages are licensed books.

    python -m backend.conversion.reading.vision_batches free-checks
    python -m backend.conversion.reading.vision_batches smoke
    python -m backend.conversion.reading.vision_batches submit --cells MP-HM,MP-HJ,MP-SM,MP-SJ [--cap 5] [--dry-run] [--retry-malformed]
    python -m backend.conversion.reading.vision_batches collect [--delete]
    python -m backend.conversion.reading.vision_batches status
"""

import argparse
import copy
import hashlib
import logging
import os
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import pymupdf

from backend.conversion.contract import page_contract
from backend.conversion.judge import page_judge
from backend.conversion.reading import page_class_check, page_render, reader_requests, reading_cells
from backend.conversion.store.reading_store import Store, open_store
from backend.providers import anthropic_client

IN_FLIGHT_FACTOR = 1.3
DEFAULT_CAP_USD = 5.0
SMOKE_CAP_USD = 0.10
PACK_REQUESTS, PACK_BYTES = 300, 50_000_000  # the API allows 256 MB; a laptop upload should not time out
REQUEST_OVERHEAD_BYTES = 20_000  # the prompts, the schema and the user turn of one request
OPEN_STATES = ('submitting', 'submitted')
RETRY_ATTEMPT = 1
HINTED_AFTER_PLAIN_RETRY = 2  # decision 113.a: one hinted attempt for a page whose plain retry, sent before it, failed too
ERROR_MESSAGE_CHARS = 200
FILTER_MESSAGE = 'content filtering'  # 'Output blocked by content filtering policy' (pilot, 2026-10-29)
RECORD_FIELDS = ('reading_key', 'custom_id', 'cell', 'page_id', 'file', 'pdf_page', 'work', 'mirror', 'model',
                 'resolution', 'form', 'replicate', 'attempt', 'max_tokens', 'image_sha256', 'image_size',
                 'system_sha256', 'user_sha256', 'mode', 'retry_of')  # retry_of: the reading a judge-hinted re-read replaces
FREE_CHECK_PAGE = 'openstax-finance-2e:p0179'
SMOKE_PLAN = (('MP-HM', 'openstax-finance-2e:p0179'), ('MP-HJ', 'openstax-finance-2e:p0179'),
              ('MP-SM', 'openstax-finance-2e:p0445'), ('MP-SJ', 'openstax-finance-2e:p0445'))


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def quiet_sdk_logs() -> None:
    """At DEBUG the SDK logs whole request bodies, page images included: never let that happen."""
    if os.environ.get('ANTHROPIC_LOG'):
        sys.exit('ANTHROPIC_LOG is set; unset it, it would log page images and text')
    for name in ('anthropic', 'httpx', 'httpx2', 'httpcore'):
        logging.getLogger(name).setLevel(logging.WARNING)


class Documents:
    """Open each source PDF once."""

    def __init__(self):
        self._open = {}

    def page(self, file_name: str, pdf_page: int):
        if file_name not in self._open:
            mirror, path = reading_cells.source_of(file_name)
            self._open[file_name] = (mirror, pymupdf.open(path))
        mirror, document = self._open[file_name]
        return mirror, document[pdf_page - 1]


# ---------------------------------------------------------------- the kinds of request

def reading_params(entry: dict) -> dict:
    """The parameters of a reading, from the stored bytes its key was computed on."""
    store = open_store(entry['mirror'])
    return reader_requests.message_params(model=entry['model'], form=entry['form'],
                                          system_text=store.get_prompt(entry['system_sha256']),
                                          user_text=store.get_prompt(entry['user_sha256']),
                                          png=store.get_input(entry['image_sha256'], '.png'), max_tokens=entry['max_tokens'])


# The reader declining a page in prose instead of writing it (decision 75.a, 2026-11-04): on the licensed round 2 all 6 answers
# without a page file named copyright, transcription or verbatim text and offered a summary. Such a page is refused, like one
# the provider's filter blocked: it keeps its text layer, gets no retry and no second reader, and the summary is never used.
# Only an answer without a page file is ever classed so; a page file that mentions copyright stays a page.
DECLINED = re.compile(r"copyright|\bverbatim\b|(?:can.?t|cannot|not able to|unable to|won.?t)\s+(?:transcribe|reproduce)", re.I)


# Decision 214.a (the operator, 11 Nov: "technically this is less critical, since the result must not change"): one export
# validated each stored reading about three times (latest_per_page, attempts_of, the row), 42 of its 69 seconds. Within one
# process the validator cannot change and a reading's text is the key's, so the answer is kept by everything it depends on,
# the text's hash included; a copy is handed out, so no caller can change what the next one gets.
_CHECKED: dict[tuple, tuple[str, dict | None]] = {}


def check_reading(entry: dict, text: str, stop_reason: str | None) -> tuple[str, dict | None]:
    """Stage 1: the result class and what the record keeps of the check, which is no page text."""
    key = (entry.get('form'), entry.get('work'), entry.get('pdf_page'), tuple(entry.get('image_size') or ()), stop_reason,
           hashlib.sha256(text.encode('utf-8')).hexdigest())
    if key not in _CHECKED:
        _CHECKED[key] = _check_reading(entry, text, stop_reason)
    result_class, check = _CHECKED[key]
    return result_class, copy.deepcopy(check)


def _check_reading(entry: dict, text: str, stop_reason: str | None) -> tuple[str, dict | None]:
    if entry.get('form') not in page_contract.FORMS:  # contract v1.1, archived: the text is kept and nothing can check it
        result_class = page_contract.classify('succeeded', stop_reason, None)
        return ('unchecked' if result_class == 'no_page' else result_class), None
    if not text.strip():
        return page_contract.classify('succeeded', stop_reason, None), None
    expected = page_contract.Expected(entry['work'], entry['pdf_page'], tuple(entry['image_size']))
    try:
        page = page_contract.parse(text, entry['form'], expected)
    except Exception as error:  # untrusted output: one odd answer must not stop a collect, on this pass or the next
        page = page_contract.ParsedPage(entry['form'], {}, [], [f'the parser failed: {type(error).__name__}'])
    result_class = page_contract.classify('succeeded', stop_reason, page)
    if result_class == 'no_page' and DECLINED.search(text):
        result_class = 'refused'
    return result_class, page.as_dict()


@dataclass(frozen=True)
class RequestKind:
    """What differs between the kinds of request. An entry of any kind has reading_key, custom_id, cell, model, mirror,
    mode, image_bytes and estimate_usd, which `send_entries` and `collect` read."""
    params: Callable[[dict], dict]  # entry -> the Messages API parameters
    check: Callable[[dict, str, str | None], tuple[str, dict | None]]  # entry, answer, stop reason -> result class, what to keep
    record_field: str = 'contract'  # where a record keeps the check
    extra_fields: tuple[str, ...] = ()  # entry fields a record keeps beyond RECORD_FIELDS


KINDS = {'reading': RequestKind(reading_params, check_reading),
         'judge': RequestKind(page_judge.params_from_entry, page_judge.check_answer, record_field='verdict',
                              extra_fields=page_judge.ENTRY_FIELDS),
         'classcheck': RequestKind(page_class_check.params_from_entry, page_class_check.check_answer, record_field='answer',
                                   extra_fields=page_class_check.ENTRY_FIELDS)}


def kind_of(entry: dict) -> RequestKind:
    return KINDS[entry.get('kind', 'reading')]


def params_for(entry: dict) -> dict:
    return kind_of(entry).params(entry)


# ---------------------------------------------------------------- records

def record_for(entry: dict, result_type: str, message=None, error_type: str | None = None,
               error_message: str | None = None, batch: bool = True) -> tuple[dict, str | None]:
    """The stored record of one result, and the response text (None when there is none)."""
    kind = kind_of(entry)
    record = {name: entry.get(name) for name in (*RECORD_FIELDS, *kind.extra_fields)}
    record.update(kind=entry.get('kind', 'reading'), result_type=result_type, error_type=error_type,
                  error_message=error_message[:ERROR_MESSAGE_CHARS] if error_message else None, stored_at=now(),
                  sdk=reader_requests.sdk_version(), anthropic_version=reader_requests.API_VERSION)
    if message is None:
        record.update(result_class=page_contract.classify(result_type, None, None), cost_usd=0.0)
        return record, None
    text = anthropic_client.answer_text(message)
    result_class, checked = kind.check(entry, text, message.stop_reason)
    usage = message.usage.to_dict()
    cost = anthropic_client.cost_usd(entry['model'], usage.get('input_tokens') or 0, usage.get('output_tokens') or 0,
                                     batch=batch, cache_write_tokens=usage.get('cache_creation_input_tokens') or 0,
                                     cache_read_tokens=usage.get('cache_read_input_tokens') or 0)
    stop_details = getattr(message, 'stop_details', None)
    record.update(message_id=message.id, response_model=message.model, stop_reason=message.stop_reason,
                  stop_details=stop_details.to_dict() if stop_details is not None else None, usage=usage,
                  cost_usd=cost, result_class=result_class, text_sha256=reader_requests.sha256_text(text),
                  text_chars=len(text))
    record[kind.record_field] = checked
    return record, text


def store_result(entry: dict, record: dict, text: str | None) -> None:
    """Keep a result once. A pass that died half way sees its batch again, and a reading is immutable, so what is
    stored stays. The ledger line goes first: a spend guard may count a cost twice but must not miss one."""
    store = open_store(entry['mirror'])
    if store.reading(entry['reading_key']) is not None:
        return
    store.append_ledger({'reading_key': entry['reading_key'], 'custom_id': entry['custom_id'], 'cell': entry['cell'],
                         'kind': entry.get('kind', 'reading'), 'model': entry['model'], 'mode': entry['mode'],
                         'provider': entry.get('provider', 'anthropic'),  # the Claude spend guard counts its own alone
                         'result_class': record['result_class'], 'cost_usd': record['cost_usd'],
                         'at': record['stored_at']})
    store.save_reading(entry['reading_key'], record, text)


def is_block(record: dict) -> bool:
    """Whether the API would not read this page. The pilot's records keep only the error's type, and its findings name
    the block's message with that type. A newer record says which invalid request it was: a wrong parameter is no block."""
    if record.get('result_class') == 'refused':
        return True
    if record.get('result_class') != 'errored' or record.get('error_type') != 'invalid_request_error':
        return False
    message = record.get('error_message')
    return message is None or FILTER_MESSAGE in message


def blocked_pages(store: Store) -> set[tuple[str, int]]:
    """The pages that were refused or blocked, in any cell: the filter rule forbids a second model after a block."""
    return {(record.get('file'), record.get('pdf_page')) for record in store.readings() if is_block(record)}


# ---------------------------------------------------------------- planning

def reader_turn(page: dict, image: page_render.PageImage, hint: str | None = None) -> str:
    turn = reader_requests.user_turn(work=page['work'], pdf_page=page['pdf_page'], image_size=(image.width, image.height),
                                     work_card=page['work_card'])
    return turn + '\n\n' + hint if hint else turn


HINT_ERRORS, HINT_ERROR_CHARS = 8, 160


def format_hint(errors: list[str]) -> str:
    """What a format retry is told (decision 113.a, the operator, 2026-11-08): the format check's own messages about the attempt before,
    in the user turn beside the frozen system prompt (decision 54.a). Retried without it, 10 of round 6's 15 pages came back
    with exactly the same error. The messages name lines, blocks and attributes, never the page's text."""
    listed = '\n'.join(f'- {error[:HINT_ERROR_CHARS]}' for error in errors[:HINT_ERRORS])
    return ('The format check refused your previous reading of this page:\n' + listed +
            '\nRead the page again and write all of it in the format the instructions give.')


FINDING_WORDS = {'wrong_value': 'a wrong value', 'wrong_word': 'a wrong word', 'omission': 'something left out',
                 'invented': 'something not on the page', 'structure': 'a wrong structure', 'binding': 'a wrong binding',
                 'order': 'a wrong order'}


def judge_hint(findings: list[dict]) -> str:
    """What a re-read after the judge's issue is told (decision 133.b, the operator, 2026-11-09): the judge's own findings on the reading
    before, each with its block and evidence, in the user turn beside the frozen system prompt (54.a), as the format retry is
    told the format check's messages (113.a). A hint never serves to get past the provider's filter: these pages were read."""
    listed = '\n'.join(f"- {finding.get('block') or 'the page'}, {FINDING_WORDS.get(finding.get('kind'), 'an error')}: "
                       f"{' '.join(str(finding.get('evidence') or '').split())[:HINT_ERROR_CHARS]}"
                       for finding in findings[:HINT_ERRORS])
    return ('An independent check of your previous reading of this page against the page image found these places wrong:\n'
            + listed + '\nRead the whole page again from the image, exactly as printed: correct these places and keep '
            'everything else as it is.')


def review_hint(verdicts: list[dict]) -> str:
    """What a re-read after a review's reject is told (M2.c, the operator, 18 Nov): the review's own findings on the reading
    before, each with its block, worded as the judge's are (133.b). Never the review's correction itself: the reader reads the
    page again from the image, it does not copy a text it is handed. The notes name blocks and what is wrong, in a few words."""
    listed = '\n'.join(f"- {verdict.get('block') or 'the page'}: {' '.join(str(verdict.get('note') or '').split())[:HINT_ERROR_CHARS]}"
                       for verdict in verdicts[:HINT_ERRORS])
    return ('A review of your previous reading of this page against the page image found these places wrong:\n'
            + listed + '\nRead the whole page again from the image, exactly as printed: correct these places and keep '
            'everything else as it is.')


def reading_entry(cell: reading_cells.Cell, page: dict, image: page_render.PageImage, mirror: str, store: Store,
                  mode: str, attempt: int = 0, hint: str | None = None) -> dict:
    """One request of a cell: what it sends stored by hash, everything it asks in its key."""
    system_sha = store.put_prompt(reader_requests.system_prompt(cell.form, cell.reader_version))
    user_sha = store.put_prompt(reader_turn(page, image, hint))
    image_sha = store.put_input(image.png, '.png')
    spec = reader_requests.reading_spec(image_sha=image_sha, model=cell.model, system_sha=system_sha, user_sha=user_sha,
                                        form=cell.form, max_tokens=cell.max_tokens, replicate=cell.replicate,
                                        attempt=attempt, mode=mode)
    key = reader_requests.reading_key(spec)
    estimate = reader_requests.estimate_usd(cell.model, image.patches, min(page['expected_output_tokens'], cell.max_tokens),
                                            cell.form, batch=(mode == 'batch'))
    return {'kind': 'reading', 'reading_key': key, 'custom_id': reader_requests.custom_id(key), 'cell': cell.name,
            'page_id': page['id'], 'file': page['file'], 'pdf_page': page['pdf_page'], 'work': page['work'],
            'mirror': mirror, 'model': cell.model, 'resolution': cell.resolution, 'form': cell.form,
            'replicate': cell.replicate, 'attempt': attempt, 'max_tokens': cell.max_tokens, 'image_sha256': image_sha,
            'image_size': [image.width, image.height], 'image_bytes': len(image.png), 'system_sha256': system_sha,
            'user_sha256': user_sha, 'mode': mode, 'estimate_usd': estimate,
            **({'reader_version': cell.reader_version} if cell.reader_version != reader_requests.FIRST_VERSION else {})}


def readings_of(cell_names, store: Store) -> list[dict]:
    """The stored readings of these cells' pages, recognised by what their keys hold (model, form, system prompt, token limit,
    replicate, batch mode), never by the cell label a record carries: a page another cell bought first under the same question
    is the same reading, and the submit skipped it as already read. Selecting by label left 7 pages out (review, 2026-11-03)."""
    wanted = []
    for name in cell_names:
        cell = reading_cells.known_cells()[name]
        system_sha = reader_requests.sha256_text(reader_requests.system_prompt(cell.form, cell.reader_version))
        wanted.append((cell, system_sha, {(page['file'], page['pdf_page']) for page in reading_cells.pages_for(cell)}))
    found = []
    for record in store.readings():
        if record.get('kind', 'reading') != 'reading':
            continue
        if any((record['file'], record['pdf_page']) in pages and record.get('model') == cell.model and record.get('form') == cell.form
               and record.get('system_sha256') == system_sha and record.get('max_tokens') == cell.max_tokens
               and record.get('replicate', 0) == cell.replicate and record.get('mode') == cell.mode
               for cell, system_sha, pages in wanted):
            found.append(record)
    return found


def stage_one_errors(record: dict, store: Store) -> list[str]:
    """A stored reading's format errors under today's validator, as the hint of its retry names them."""
    cache = getattr(store, 'class_cache', None)  # an export's snapshot keeps them between runs (issue #5)
    if cache is not None and (kept := cache.errors(record)) is not None:
        return kept
    result_class, check = check_reading(record, store.reading_text(record['reading_key']) or '', record.get('stop_reason'))
    errors = list((check or {}).get('errors') or [])
    if cache is not None:
        cache.put(record, result_class, errors)
    return errors


def current_class(record: dict, store: Store) -> str:
    """A reading's class under today's validator. The record keeps the verdict it got when it was collected, and the stored
    text stays as it was; a corrected validator (page/1.1) changes the verdict, never the reading."""
    if record.get('kind', 'reading') != 'reading' or record.get('result_type') != 'succeeded':
        return record['result_class']
    cache = getattr(store, 'class_cache', None)  # an export's snapshot keeps the classes between runs (issue #5)
    if cache is not None and (kept := cache.get(record)) is not None:
        return kept
    result_class, check = check_reading(record, store.reading_text(record['reading_key']) or '', record.get('stop_reason'))
    if cache is not None:
        cache.put(record, result_class, list((check or {}).get('errors') or []))
    return result_class


def plan_entries(cell: reading_cells.Cell, documents: Documents, mode: str = 'batch',
                 retry_malformed: bool = False, retry_issues: bool = False, over_a_person: str | None = None) -> tuple[list, Counter]:
    """The requests a cell still needs: rendered, stored as inputs, keyed; skipped ones counted by why.

    With `retry_malformed` only a page whose stored first reading is malformed comes back, as attempt 1. Any other
    class stays as it is, and attempt 1 is the last: the filter rule is absolute, and a format retry is the only retry.
    **→ now** (decision 113.a, 2026-11-08): the retry carries the format check's messages as a hint. A page whose retry was
    sent without one, before that, and is still malformed under today's validator gets one hinted attempt more, attempt 2.
    """
    if retry_issues:
        return issue_entries(cell, documents, mode, over_a_person)
    skipped, entries, blocked, checked = Counter(), [], {}, {}
    for page in reading_cells.pages_for(cell):
        if not reading_cells.may_send(page['file']):
            skipped['held by provenance'] += 1
            continue
        mirror, pdf_page = documents.page(page['file'], page['pdf_page'])
        store = open_store(mirror)
        if mirror not in blocked:
            blocked[mirror] = blocked_pages(store)
        if (page['file'], page['pdf_page']) in blocked[mirror]:
            skipped['blocked before'] += 1
            continue
        if retry_malformed and not (over_a_person or '').strip():  # a page a person checked is not read again (decision 191.a)
            if mirror not in checked:
                from backend.conversion.store import pipeline_db

                checked[mirror] = pipeline_db.protected_pages(mirror)
            if (page['file'], page['pdf_page']) in checked[mirror]:
                skipped['a person checked it'] += 1
                continue
        image = page_render.render(pdf_page, cell.resolution)
        entry = reading_entry(cell, page, image, mirror, store, mode)
        if retry_malformed:
            first = store.reading(entry['reading_key'])
            first_class = current_class(first, store) if first else 'not read'
            if first_class != 'malformed':
                skipped[f'not malformed ({first_class})'] += 1
                continue
            plain = store.reading(reading_entry(cell, page, image, mirror, store, mode, attempt=RETRY_ATTEMPT)['reading_key'])
            if plain is not None:  # retried before 113.a, without a hint
                plain_class = current_class(plain, store)
                if plain_class != 'malformed':
                    skipped[f'retried before ({plain_class})'] += 1
                    continue
                entry = reading_entry(cell, page, image, mirror, store, mode, attempt=HINTED_AFTER_PLAIN_RETRY,
                                      hint=format_hint(stage_one_errors(plain, store)))
            else:
                entry = reading_entry(cell, page, image, mirror, store, mode, attempt=RETRY_ATTEMPT,
                                      hint=format_hint(stage_one_errors(first, store)))
        if store.reading(entry['reading_key']) is not None:
            # Any stored result, refused or truncated too: a reading is immutable and never bought
            # twice. A retry is a deliberate new attempt, and with it a new key.
            skipped['already read'] += 1
            continue
        entries.append(entry)
    return entries, skipped


def issue_entries(cell: reading_cells.Cell, documents: Documents, mode: str = 'batch',
                  over_a_person: str | None = None) -> tuple[list, Counter]:
    """One re-read for each page whose standing reading the judge found bad on a quoted block (decision 133.b): a new attempt
    past the page's last, told the judge's findings. A page whose findings all lie on blocks never quoted stands as it is (the
    serving rule passes it), a page re-read after an issue once is not re-read again, and a stopped work stays stopped."""
    from backend.conversion.checks import check_run
    from backend.conversion.store import reading_export
    from backend.conversion.contract.page_contract import parse
    from backend.conversion.store.served_readings import NOT_QUOTED

    skipped, entries, stores = Counter(), [], {}
    for page in reading_cells.pages_for(cell):
        mirror, pdf_page = documents.page(page['file'], page['pdf_page'])
        if mirror not in stores:
            store = open_store(mirror)
            latest = {(record['file'], record['pdf_page']): record
                      for record in check_run.latest_per_page(readings_of([cell.name], store))}
            from backend.conversion.store import pipeline_db

            checked = {} if (over_a_person or '').strip() else pipeline_db.protected_pages(mirror)  # decision 191.a
            stores[mirror] = (store, latest, reading_export.check_states(store, (cell.name,)), checked)
        store, latest, states, checked = stores[mirror]
        if (page['file'], page['pdf_page']) in checked:
            skipped['a person checked it'] += 1
            continue
        record = latest.get((page['file'], page['pdf_page']))
        state = states.get(record['reading_key']) if record else None
        findings = (((state or {}).get('verdict')) or {}).get('findings') or []
        if record is None or (state or {}).get('state') != 'issue' or not findings:
            skipped['no issue of the judge'] += 1
            continue
        if record.get('retry_of'):
            skipped['re-read after an issue before'] += 1
            continue
        parsed = parse(store.reading_text(record['reading_key']) or '', record['form'])
        classes = {block.id: block.cls for block in parsed.blocks}
        if all(classes.get(finding.get('block')) in NOT_QUOTED for finding in findings):
            skipped['findings on blocks never quoted'] += 1
            continue
        image = page_render.render(pdf_page, cell.resolution)
        entry = reading_entry(cell, page, image, mirror, store, mode, attempt=record.get('attempt', 0) + 1, hint=judge_hint(findings))
        if store.reading(entry['reading_key']) is not None:
            skipped['already read'] += 1
            continue
        entries.append({**entry, 'retry_of': record['reading_key']})
    return entries, skipped


def packs(entries: list) -> list[list]:
    """Split into batches by request count and by request bytes (base64 grows the PNG by 4/3)."""
    out, current, size = [], [], 0
    for entry in entries:
        request_bytes = entry['image_bytes'] * 4 // 3 + REQUEST_OVERHEAD_BYTES
        if current and (len(current) >= PACK_REQUESTS or size + request_bytes > PACK_BYTES):
            out.append(current)
            current, size = [], 0
        current.append(entry)
        size += request_bytes
    if current:
        out.append(current)
    return out


# ---------------------------------------------------------------- the guard

def spend_status(client) -> dict:
    """Actual spend from both ledgers, the estimate of open batches, and batches nobody knows."""
    licensed, free = open_store('licensed'), open_store('free')
    manifests = licensed.manifests()
    open_estimate = sum(m['estimate_usd'] for m in manifests if m['status'] in OPEN_STATES)
    known = {m.get('batch_id') for m in manifests}
    unknown = [b.id for b in client.messages.batches.list(limit=100)
               if b.processing_status != 'ended' and b.id not in known]
    return {'spent_usd': licensed.spent_usd() + free.spent_usd(), 'open_estimate_usd': open_estimate,
            'unknown_running_batches': unknown}


def guard(status: dict, new_estimate: float, cap: float) -> None:
    if status['unknown_running_batches']:
        sys.exit(f"refused: batches running that no manifest knows: {status['unknown_running_batches']}")
    exposure = status['spent_usd'] + IN_FLIGHT_FACTOR * (status['open_estimate_usd'] + new_estimate)
    if exposure > cap:
        sys.exit(f"refused: spent {status['spent_usd']:.4f} + {IN_FLIGHT_FACTOR} x (open "
                 f"{status['open_estimate_usd']:.4f} + new {new_estimate:.4f}) = {exposure:.4f} USD > cap {cap:.2f}")


# ---------------------------------------------------------------- free checks and the smoke test

def public_page(cell: reading_cells.Cell, page_id: str, documents: Documents, what: str) -> tuple[dict, pymupdf.Page]:
    """A page of a cell's list, which must lie in the free corpus: a test of the request never reads a licensed page."""
    page = next(item for item in reading_cells.pages_for(cell) if item['id'] == page_id)
    mirror, pdf_page = documents.page(page['file'], page['pdf_page'])
    if mirror != 'free':
        sys.exit(f'{what} reads public pages only')
    return page, pdf_page


def count_input_tokens(client, params: dict) -> int:
    counted = {name: value for name, value in params.items() if name != 'max_tokens'}
    return client.messages.count_tokens(**counted).input_tokens


def free_checks(args) -> None:
    """Model availability and token counts for both forms, with the real parameters, on a public page. Costs nothing."""
    client = anthropic_client.client()
    documents = Documents()
    report = {'at': now(), 'page': FREE_CHECK_PAGE, 'models': {}, 'counts': []}
    for (model, form), cell in {(cell.model, cell.form): cell for cell in reading_cells.CELLS.values()}.items():
        if model not in report['models']:
            retrieved = client.models.retrieve(model)
            report['models'][model] = {'id': retrieved.id, 'display_name': getattr(retrieved, 'display_name', None)}
        page, pdf_page = public_page(cell, FREE_CHECK_PAGE, documents, 'free-checks')
        image = page_render.render(pdf_page, cell.resolution)
        user_text = reader_turn(page, image)
        params = reader_requests.message_params(model=model, form=form, system_text=reader_requests.system_prompt(form),
                                                user_text=user_text, png=image.png)
        full = count_input_tokens(client, params)
        text_only = count_input_tokens(client, {**params, 'messages': [{'role': 'user', 'content': user_text}]})
        row = {'model': model, 'form': form, 'size': [image.width, image.height], 'patches': image.patches,
               'input_tokens': full, 'text_tokens': text_only, 'image_tokens': full - text_only,
               'estimated_text_tokens': reader_requests.SYSTEM_PROMPT_TOKENS[form] + reader_requests.USER_TURN_TOKENS
               + (reader_requests.JSON_SCHEMA_TOKENS if form == 'json' else 0)}
        if form == 'json':
            without_schema = {**params, 'output_config': reader_requests.output_config(model, 'markdown')}
            row['schema_tokens'] = full - count_input_tokens(client, without_schema)
        report['counts'].append(row)
    path_out = open_store('free').write_report(f"free_checks_{report['at'][:19].replace(':', '')}.json", report)
    for row in report['counts']:
        print(f"{row['model']:18} {row['form']:8} {row['size'][0]}x{row['size'][1]} tokens {row['input_tokens']} "
              f"= text {row['text_tokens']} (constants {row['estimated_text_tokens']}) "
              f"+ image {row['image_tokens']} (patches {row['patches']})"
              f"{', schema ' + str(row['schema_tokens']) if 'schema_tokens' in row else ''}")
    print('written to', path_out)


def read_now(client, entry: dict) -> dict:
    """One reading through the standard API, stored at once. A block comes back as a 400 here and is stored like any
    result; another 400 is a fault of the request, which nothing should remember, because a fixed request may then be sent."""
    started = time.monotonic()
    try:
        with client.messages.stream(**params_for(entry)) as stream:
            message = stream.get_final_message()
    except anthropic.BadRequestError as error:
        if FILTER_MESSAGE not in str(error):
            sys.exit(f'the request was rejected, nothing stored: {str(error)[:ERROR_MESSAGE_CHARS]}')
        record, text = record_for(entry, 'errored', error_type='invalid_request_error', error_message=str(error),
                                  batch=False)
    else:
        record, text = record_for(entry, 'succeeded', message, batch=False)
    record['seconds'] = round(time.monotonic() - started, 1)
    store_result(entry, record, text)
    return record


def smoke_control(cell_name: str, record: dict, patches: int, bought: bool) -> dict:
    """What a reading proves about its parameters: the model answered, the image was not shrunk, the cache wrote, the
    form parsed."""
    usage = record.get('usage') or {}
    contract = record.get('contract') or {}
    return {'cell': cell_name, 'page': record['page_id'], 'model': record['model'], 'form': record['form'],
            'bought': bought, 'class': record['result_class'],
            'found_page': contract.get('found_page'), 'blocks': contract.get('blocks'),
            'errors': contract.get('errors') or ([record['error_message']] if record.get('error_message') else []),
            'model_echo': str(record.get('response_model')).startswith(record['model']),
            'image_counted': (usage.get('input_tokens') or 0) >= patches, 'image_patches': patches,
            'thinking_tokens': (usage.get('output_tokens_details') or {}).get('thinking_tokens'),
            'cache_write': usage.get('cache_creation_input_tokens'), 'cache_read': usage.get('cache_read_input_tokens'),
            'input_tokens': usage.get('input_tokens'), 'output_tokens': usage.get('output_tokens'),
            'cost_usd': round(record['cost_usd'], 5), 'seconds': record.get('seconds')}


def smoke(args) -> None:
    """Four standard-API readings of public pages, one per cell, with positive controls on what the parameters did.
    A reading stored by an earlier run is shown again and not bought twice."""
    client = anthropic_client.client()
    documents = Documents()
    store = open_store('free')
    plan = []
    for cell_name, page_id in SMOKE_PLAN:
        cell = reading_cells.CELLS[cell_name]
        page, pdf_page = public_page(cell, page_id, documents, 'the smoke test')
        image = page_render.render(pdf_page, cell.resolution)
        entry = {**reading_entry(cell, page, image, 'free', store, 'standard'), 'cell': 'SMOKE'}
        plan.append((cell_name, entry, image.patches))
    estimate = sum(entry['estimate_usd'] for _, entry, _ in plan if store.reading(entry['reading_key']) is None)
    if estimate > SMOKE_CAP_USD:
        sys.exit(f'refused: the smoke test is estimated at {estimate:.4f} USD, above its cap of {SMOKE_CAP_USD:.2f}')
    guard(spend_status(client), estimate, DEFAULT_CAP_USD)
    controls = []
    for cell_name, entry, patches in plan:
        stored = store.reading(entry['reading_key'])
        controls.append(smoke_control(cell_name, stored or read_now(client, entry), patches, bought=stored is None))
    report = {'at': now(), 'estimate_usd': estimate, 'controls': controls,
              'total_usd': sum(control['cost_usd'] for control in controls if control['bought'])}
    path_out = store.write_report(f"smoke_{report['at'][:19].replace(':', '')}.json", report)
    for c in controls:
        print(f"{c['cell']:6} {c['page']:28} {c['class']:10} found_page={c['found_page']} blocks={c['blocks']} "
              f"model_ok={c['model_echo']} image_ok={c['image_counted']} thinking={c['thinking_tokens']} "
              f"cache w/r={c['cache_write']}/{c['cache_read']} in={c['input_tokens']} out={c['output_tokens']} "
              f"{c['cost_usd']} USD {c['seconds']} s{'' if c['bought'] else ' (stored before)'}"
              f"{' errors ' + str(c['errors'][:3]) if c['errors'] else ''}")
    print(f"total {report['total_usd']:.4f} USD (estimate {estimate:.4f}), written to {path_out}")


# ---------------------------------------------------------------- batches

def send_entries(client, entries: list, skipped: Counter, cap: float, dry_run: bool = False) -> None:
    """The flow every kind shares: leave out what an open batch holds, guard the spend, then one manifest and one batch
    per pack."""
    licensed = open_store('licensed')
    open_keys = {r['reading_key'] for m in licensed.manifests() if m['status'] in OPEN_STATES for r in m['requests']}
    fresh = []
    for entry in entries:
        if entry['reading_key'] in open_keys:
            skipped['in an open batch'] += 1
        else:
            fresh.append(entry)
            open_keys.add(entry['reading_key'])
    estimate = sum(e['estimate_usd'] for e in fresh)
    by_cell = Counter(e['cell'] for e in fresh)
    print(f'requests {len(fresh)} {dict(by_cell)} | skipped {dict(skipped)} | estimate {estimate:.4f} USD')
    status = spend_status(client)
    print(f"spent {status['spent_usd']:.4f} USD, open batches estimated {status['open_estimate_usd']:.4f} USD")
    guard(status, estimate, cap)
    if dry_run or not fresh:
        print('dry run: nothing submitted' if dry_run else 'nothing to submit')
        return
    for number, pack in enumerate(packs(fresh)):
        local_id = f"{now()[:19].replace(':', '')}_{number:02d}_{pack[0]['custom_id'][:9]}"
        manifest = {'local_id': local_id, 'status': 'submitting', 'created_at': now(),
                    'cells': sorted({e['cell'] for e in pack}), 'estimate_usd': sum(e['estimate_usd'] for e in pack),
                    'requests': pack, 'cap_usd': cap}
        licensed.save_manifest(manifest)
        try:
            batch = client.messages.batches.create(requests=[
                {'custom_id': e['custom_id'], 'params': params_for(e)} for e in pack])
        except Exception as error:
            manifest.update(status='create_failed', error=f'{type(error).__name__}')
            licensed.save_manifest(manifest)
            sys.exit(f'batch create failed ({type(error).__name__}); run status to look for a batch that was created anyway')
        manifest.update(status='submitted', batch_id=batch.id, submitted_at=now())
        licensed.save_manifest(manifest)
        print(f"submitted {batch.id}: {len(pack)} requests {manifest['cells']}, estimate {manifest['estimate_usd']:.4f} USD")


def submit(args) -> None:
    client = anthropic_client.client()
    documents = Documents()
    names = [name.strip() for name in args.cells.split(',') if name.strip()]
    unknown = [name for name in names if name not in reading_cells.submittable()]
    if unknown:
        sys.exit(f'unknown cells: {unknown}; known: {sorted(reading_cells.submittable())}')
    entries, skipped = [], Counter()
    for name in names:
        planned, cell_skipped = plan_entries(reading_cells.submittable()[name], documents, retry_malformed=args.retry_malformed,
                                             retry_issues=getattr(args, 'retry_issues', False),
                                             over_a_person=getattr(args, 'over_a_person', None))
        entries.extend(planned)
        skipped.update(cell_skipped)
    send_entries(client, entries, skipped, cap=args.cap, dry_run=args.dry_run)


def delete_at_anthropic(client, manifest: dict, licensed: Store) -> None:
    try:
        client.messages.batches.delete(manifest['batch_id'])
    except anthropic.NotFoundError:  # already gone, by hand or after its 29 days: there is nothing left to delete
        manifest['gone_at_anthropic'] = True
    manifest.update(status='deleted', deleted_at=now())
    licensed.save_manifest(manifest)


def collect(args) -> None:
    client = anthropic_client.client()
    licensed = open_store('licensed')
    for manifest in licensed.manifests():
        if manifest['status'] == 'collected' and args.delete and not manifest.get('missing'):
            delete_at_anthropic(client, manifest, licensed)
            print(f"{manifest['batch_id']}: deleted at Anthropic")
            continue
        if manifest['status'] != 'submitted':
            continue
        batch = client.messages.batches.retrieve(manifest['batch_id'])
        if batch.processing_status != 'ended':
            counts = batch.request_counts
            print(f"{batch.id} {batch.processing_status}: processing {counts.processing}, succeeded {counts.succeeded}")
            continue
        by_id = {entry['custom_id']: entry for entry in manifest['requests']}
        classes, cost, seen = Counter(), 0.0, set()
        for result in client.messages.batches.results(batch.id):
            entry = by_id[result.custom_id]
            outcome = result.result
            if outcome.type == 'succeeded':
                record, text = record_for(entry, 'succeeded', outcome.message)
            elif outcome.type == 'errored':
                error = outcome.error.error
                record, text = record_for(entry, 'errored', error_type=error.type, error_message=error.message)
            else:
                record, text = record_for(entry, outcome.type)
            store_result(entry, record, text)
            classes[record['result_class']] += 1
            cost += record['cost_usd']
            seen.add(result.custom_id)
        missing = sorted(set(by_id) - seen)
        manifest.update(status='collected', collected_at=now(), classes=dict(classes), cost_usd=cost,
                        missing=missing)
        licensed.save_manifest(manifest)
        print(f"{batch.id}: {dict(classes)}, {cost:.4f} USD (estimate {manifest['estimate_usd']:.4f})"
              f"{', missing ' + str(len(missing)) if missing else ''}")
        if args.delete and not missing:
            delete_at_anthropic(client, manifest, licensed)


def status(args) -> None:
    client = anthropic_client.client()
    spend = spend_status(client)
    print(f"spent {spend['spent_usd']:.4f} USD | open batches estimated {spend['open_estimate_usd']:.4f} USD"
          f" | unknown running batches {spend['unknown_running_batches']}")
    for manifest in open_store('licensed').manifests():
        print(f"{manifest['local_id']}: {manifest['status']:12} {manifest.get('batch_id', '-')} {manifest['cells']} "
              f"{len(manifest['requests'])} requests, estimate {manifest['estimate_usd']:.4f}"
              f"{', cost ' + format(manifest['cost_usd'], '.4f') if 'cost_usd' in manifest else ''}"
              f"{', ' + str(manifest['classes']) if 'classes' in manifest else ''}")


def recheck(args) -> None:
    """Stage 1 again over the stored readings of some cells, under today's validator: how many change class. No API call,
    no page text; the report goes to each mirror's reports/ beside the readings."""
    names = {name.strip() for name in args.cells.split(',') if name.strip()}
    validator = hashlib.sha256(Path(page_contract.__file__).read_bytes()).hexdigest()
    for mirror in ('free', 'licensed'):
        store = open_store(mirror)
        moves = Counter()
        for record in readings_of(names, store):
            moves[f"{record['result_class']} -> {current_class(record, store)}"] += 1
        if moves:
            report = {'at': now(), 'cells': sorted(names), 'page_contract_sha256': validator, 'moves': dict(sorted(moves.items()))}
            path = store.write_report(f"recheck_{now()[:19].replace(':', '')}.json", report)
            print(f'{mirror}: ' + ', '.join(f'{move} {count}' for move, count in sorted(moves.items())) + f' (report {path.name})')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('free-checks').set_defaults(run=free_checks)
    commands.add_parser('smoke').set_defaults(run=smoke)
    submit_parser = commands.add_parser('submit')
    submit_parser.add_argument('--cells', required=True)
    submit_parser.add_argument('--cap', type=float, default=DEFAULT_CAP_USD)
    submit_parser.add_argument('--dry-run', action='store_true')
    submit_parser.add_argument('--retry-malformed', action='store_true',
                               help='re-read only pages whose stored reading of these cells is malformed, once; '
                                    'never a refused, blocked, errored or truncated page')
    submit_parser.add_argument('--retry-issues', action='store_true',
                               help="re-read once each page the judge found bad on a quoted block, told the judge's findings "
                                    '(decision 133.b); every such re-read goes to the judge again')
    submit_parser.add_argument('--over-a-person', metavar='REASON',
                               help='read again pages a person checked too; without it they are skipped (decision 191.a)')
    submit_parser.set_defaults(run=submit)
    collect_parser = commands.add_parser('collect')
    collect_parser.add_argument('--delete', action='store_true',
                                help='delete each fully stored batch at Anthropic (off until the store is checked)')
    collect_parser.set_defaults(run=collect)
    commands.add_parser('status').set_defaults(run=status)
    recheck_parser = commands.add_parser('recheck', help='stage 1 again over stored readings, under today\'s validator')
    recheck_parser.add_argument('--cells', required=True)
    recheck_parser.set_defaults(run=recheck)
    return parser


RECORDED_COMMANDS = ('submit', 'collect', 'smoke', 'recheck')  # those that spend or store; status and free checks do neither


def main() -> None:
    from backend.conversion.store import pipeline_db

    sys.stdout.reconfigure(encoding='utf-8')
    quiet_sdk_logs()
    args = build_parser().parse_args()
    if args.command not in RECORDED_COMMANDS:
        args.run(args)
        return
    with pipeline_db.run(run_bases(args), pipeline_db.command_line('backend.conversion.reading.vision_batches')):
        args.run(args)


def run_bases(args) -> list[str]:
    """The knowledge bases a run is recorded in: those its cells read. Until 5 Nov every run went into both databases, so
    the free one listed licensed rounds (found by line 2). `collect` stores both mirrors' results and stays in both; `smoke`
    reads four public pages; a cell name the runner does not know fails in the command itself, and its run is kept in both."""
    if args.command == 'smoke':
        return ['free']
    if args.command in ('submit', 'recheck'):
        names = [name.strip() for name in args.cells.split(',') if name.strip()]
        return reading_cells.knowledge_bases_of(names) or ['free', 'licensed']
    return ['free', 'licensed']


if __name__ == '__main__':
    main()
