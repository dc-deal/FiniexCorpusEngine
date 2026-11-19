"""Direct reading (decision 280.a): a page read in a Claude Code session, its own route, for the hard cases only.

After the API credit, a page whose reading stayed malformed or found no page is read in a session by `claude-opus-5-5`
under the reader's own instructions (page/1, the same system prompt and user turn a batch sends), and stored like any
reading: keyed by everything it was asked, checked by stages 1 and 2, judged by the same judge, chosen only where the judge
finds it ok. A failed attempt is stored too (malformed, or an issue the judge names), so the page view shows every attempt.
It costs no API money; the plan's usage pays for it. **Never a page a provider's filter blocked or a reader refused,
anywhere in its history**, and never a file held back from every provider (`send: false`): that would be Claude through
another door, around the provider's own safeguard (the filter rule; 280.a). `pages` leaves such pages out and `prepare`
checks again.

    python -m backend.conversion.reading.direct_reader pages --knowledge-base licensed
    python -m backend.conversion.reading.direct_reader prepare --knowledge-base licensed --limit 1
        (the session reads page.png under instructions.md and writes reading.md beside them)
    python -m backend.conversion.reading.direct_reader store --knowledge-base licensed
    python -m backend.conversion.checks.check_run plan|submit|report --cells LIC-DIRECT-OPUS
    python -m backend.conversion.reading.direct_reader choose --knowledge-base licensed

Prints ids, counts and classes, never page text.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from backend.configuration import data_paths
from backend.constants.reading_constants import DIRECT_DEVIATION
from backend.conversion.reading import page_render, reader_requests, reading_cells, vision_batches
from backend.conversion.store import served_readings
from backend.conversion.store.reading_store import open_store

MODE = 'session'
ADAPTER = 'claude-code-session'
PROVIDER = 'anthropic, in a Claude Code session'
FORM = 'markdown'
RESOLUTION = 'hi'
REASONS = ('malformed',)  # the hard case this cell takes; a judge's issue goes to a person's review first
# A reader that found no page wrote prose instead, and every such answer of the licensed run read on 18 Nov (5 of 5) declined
# the page as a published book's text: a refusal in other words. So a no_page anywhere in a page's history counts as a refusal,
# and the session never reads such a page (280.a: never the same model by another door).
FILTER_WORDS = ('blocked', 'refus', 'declin', 'content_filter', 'policy', 'no_page')
SOFT_REFUSAL = 'no page found: a reader declined it in prose'
PASSED = ('ok', 'ok_unjudged')  # the check states a direct reading is chosen with (`choose`)


def cell_name(knowledge_base: str) -> str:
    return f"{'FREE' if knowledge_base == 'free' else 'LIC'}-DIRECT-OPUS"


def session_folder(knowledge_base: str) -> Path:
    working = data_paths.FREE_WORKING if knowledge_base == 'free' else data_paths.LICENSED_WORKING
    return working / 'direct' / 'session'


def touched_by_a_filter(row: dict) -> bool:
    """Whether any reading of the page was blocked by a provider's filter or refused by a reader, as its row records it."""
    said = [{name: attempt.get(name) for name in ('class_now', 'class_when_collected', 'deviation', 'upstream', 'error_type')}
            for attempt in row.get('attempts') or []]
    said.append({name: row.get(name) for name in ('class_now', 'class_when_collected', 'error_type', 'deviation')})
    text = json.dumps(said).lower()
    return any(word in text for word in FILTER_WORDS)


def select(rows: list[dict], listed: dict, protected: set, may_send=reading_cells.may_send) -> tuple[list[dict], Counter]:
    """The pages of the direct cell: a hard case of `REASONS`, no filter or refusal in its history, sendable, unchecked by a
    person (191.a), and in a default cell (which gives its work card and estimate). Returns them and why others were left."""
    chosen, left = [], Counter()
    for row in rows:
        why = served_readings.text_layer_why(row)
        key = (row['file'], row['pdf_page'])
        # A page the session read stays in the cell whatever came of it, so the cell's plan and report keep its check: when a
        # served page left the list (18 Nov), the next report lost its state and the export would have served its text layer.
        # The same lesson as the second reader's `served` (288.a). It is not prepared again unless its reading is malformed.
        if any(attempt.get('deviation') == DIRECT_DEVIATION for attempt in [row, *(row.get('attempts') or [])]) and key in listed:
            page = listed[key]
            chosen.append({'file': page['file'], 'pdf_page': page['pdf_page'], 'work': page['work'], 'gold': False,
                           'class_note': page.get('class_note', ''), 'expected_output_tokens': page['expected_output_tokens'],
                           'deviation': DIRECT_DEVIATION, 'why': why or 'served', 'work_card': page['work_card'],
                           'read': True, **({'protected': True} if key in protected else {})})
            continue
        if why == 'no_page':
            left[SOFT_REFUSAL] += 1
            continue
        if why not in REASONS:
            continue
        if touched_by_a_filter(row):
            left['a filter or a refusal in its history'] += 1
        elif not may_send(row['file']):
            left['held back from every provider (send: false)'] += 1
        elif key in protected:
            left['a person checked it'] += 1
        elif key not in listed:
            left['in no default cell'] += 1
        else:
            page = listed[key]
            chosen.append({'file': page['file'], 'pdf_page': page['pdf_page'], 'work': page['work'], 'gold': False,
                           'class_note': page.get('class_note', ''),
                           'expected_output_tokens': page['expected_output_tokens'], 'deviation': DIRECT_DEVIATION,
                           'why': why, 'work_card': page['work_card']})
    return chosen, left


def reading_spec(*, image_sha: str, model: str, system_sha: str, user_sha: str, max_tokens: int, attempt: int = 0) -> dict:
    """Everything a direct reading asks, as hashes and parameters: the input of its key."""
    return {'inputs': {'image': image_sha}, 'model': model, 'adapter': ADAPTER, 'provider': PROVIDER,
            'prompt': {'system': system_sha, 'user': user_sha, 'form': FORM, 'schema': None},
            'params': {'max_tokens': max_tokens, 'replicate': 0, 'attempt': attempt}, 'mode': MODE}


def pages(args) -> dict:
    from backend.conversion.store import pipeline_db, reading_export

    base = reading_export.BASES[args.knowledge_base]
    rows = json.loads((base.export / 'index.json').read_text(encoding='utf-8'))['pages']
    listed = {(page['file'], page['pdf_page']): page
              for name in base.cells() for page in reading_cells.pages_for(reading_cells.known_cells()[name])}
    chosen, left = select(rows, listed, set(pipeline_db.protected_pages(base.name)))
    target = reading_cells.DIRECT_PAGES[args.knowledge_base]
    earlier = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    added = sorted(set(earlier.get('added_works', [])) | set(getattr(args, 'add_work', None) or []))
    shares = {**earlier.get('judge_shares', {}),  # the share of a work's pages its judge sees (N2.a), by the work's key
              **({Path(name).stem: args.judge_share for name in args.add_work or []} if getattr(args, 'judge_share', None) else {})}
    known = {(page['file'], page['pdf_page']) for page in chosen}
    for file_name in added:
        chosen += [page for page in whole_work(base, file_name, rows) if (page['file'], page['pdf_page']) not in known]
    cards = {page['work']: page.pop('work_card') for page in chosen}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'work_cards': cards, 'added_works': added, 'judge_shares': shares, 'pages': chosen}, indent=1,
                                 ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"{args.knowledge_base}: {len(chosen)} pages for a direct reading {dict(Counter(p['why'] for p in chosen))}, "
          f'written to {target.name}; left out {dict(left)}')
    return {'pages': len(chosen), 'left': dict(left)}


WORK_CARD = ('A book in English. Read the page as printed: its columns in reading order, its printed page number and running '
             'head as page furniture, and every label (figure, table, equation number) exactly as printed.')
SCAN_NOTE = ' The page is a scan of print with no text layer: read every word from the image, and mark what you cannot read.'


def whole_work(base, file_name: str, rows: list[dict]) -> list[dict]:
    """Every page of one licensed file that no reader has read, for the direct cell: the operator's experiment of 18 Nov night
    ("das ganze Buch über Nacht konvertieren, readings, kein Judge"), a scanned book no batch round took. A file the provenance
    list holds back, or a page with a filter or a refusal in its history, is never added (280.a)."""
    import pymupdf

    if not reading_cells.may_send(file_name):
        raise SystemExit(f'{file_name} is held back by the provenance list (send: false): never sent to a provider')
    own = [row for row in rows if row['file'] == file_name]
    # A page the session read stays in the list, so its readings and its check stay the cell's (found 19 Nov: the list written
    # anew after the reading had dropped every read page, and the export would have lost the whole work); a page another reader
    # read, or one a filter or a reader turned away, stays out.
    in_session = {row['pdf_page'] for row in own if read_in_session(row)}
    read = {row['pdf_page'] for row in own if row['pdf_page'] not in in_session} | {row['pdf_page'] for row in own if touched_by_a_filter(row)}
    path = data_paths.LICENSED_ARCHIVE / file_name if base.name == 'licensed' else data_paths.locate(file_name)
    work = Path(file_name).stem
    with pymupdf.open(path) as document:
        scan = not any(document[number].get_text().strip() for number in range(0, document.page_count, 25))
        count = document.page_count
    card = WORK_CARD + (SCAN_NOTE if scan else '')
    return [{'file': file_name, 'pdf_page': number, 'work': work, 'gold': False, 'class_note': '',
             'expected_output_tokens': 1900, 'deviation': DIRECT_DEVIATION,
             'why': READ_IN_SESSION if number in in_session else 'unread', 'work_card': card}
            for number in range(1, count + 1) if number not in read]


READ_IN_SESSION = 'read in the session'  # a page of a work read whole that the session read already: kept, never read again


def read_in_session(row: dict) -> bool:
    """Whether a page's history holds a reading made in a Claude Code session."""
    return any(attempt.get('mode') == 'session' for attempt in row.get('attempts') or [])


def entry_for(cell: reading_cells.Cell, page: dict, image: page_render.PageImage, mirror: str, store,
              retry_of: dict | None = None) -> dict:
    """One direct reading's request. A retry of a malformed attempt is a new attempt with the format check's own messages as
    a hint in the user turn, as a batch's format retry has (113.a), so it gets a new key and the attempt before stays."""
    hint = vision_batches.format_hint(vision_batches.stage_one_errors(retry_of, store)) if retry_of else None
    attempt = retry_of['attempt'] + 1 if retry_of else 0
    system_sha = store.put_prompt(reader_requests.system_prompt(FORM))
    user_sha = store.put_prompt(vision_batches.reader_turn(page, image, hint))
    image_sha = store.put_input(image.png, '.png')
    key = reader_requests.reading_key(reading_spec(image_sha=image_sha, model=cell.model, system_sha=system_sha,
                                                   user_sha=user_sha, max_tokens=cell.max_tokens, attempt=attempt))
    return {'kind': 'reading', 'reading_key': key, 'custom_id': reader_requests.custom_id(key), 'cell': cell.name,
            'page_id': page['id'], 'file': page['file'], 'pdf_page': page['pdf_page'], 'work': page['work'], 'mirror': mirror,
            'model': cell.model, 'resolution': RESOLUTION, 'form': FORM, 'replicate': 0, 'attempt': attempt,
            'retry_of': retry_of['reading_key'] if retry_of else None,
            'max_tokens': cell.max_tokens, 'image_sha256': image_sha, 'image_size': [image.width, image.height],
            'system_sha256': system_sha, 'user_sha256': user_sha, 'mode': MODE, 'adapter': ADAPTER, 'provider': PROVIDER,
            'deviation': DIRECT_DEVIATION}


def prepare(args) -> list[str]:
    """For the next pages of the cell not read yet: the page image, the reader's instructions and the request, in one folder
    per page, for the session to read. Nothing is bought."""
    from backend.conversion.store import reading_export

    cell = reading_cells.known_cells().get(cell_name(args.knowledge_base))
    if cell is None:
        sys.exit(f'no cell {cell_name(args.knowledge_base)}: run `direct_reader pages` first')
    rows = {(row['file'], row['pdf_page']): row for row in json.loads(
        (reading_export.BASES[args.knowledge_base].export / 'index.json').read_text(encoding='utf-8'))['pages']}
    documents, made = vision_batches.Documents(), []
    # The session's readings, gathered once per store: looked up per page, as `latest_direct` does, every page read the whole
    # store again, and preparing 25 pages of a whole work took over ten minutes once a hundred of its pages were stored (18 Nov).
    session_records: dict[str, dict] = {}
    for page in reading_cells.pages_for(cell):
        if args.limit and len(made) >= args.limit:
            break
        if args.page and page['id'] != args.page:
            continue
        if getattr(args, 'work', None) and page['file'] not in args.work:
            continue  # a night's batch takes its own works' pages only (night_run)
        row = rows.get((page['file'], page['pdf_page']))
        if (row is None and page.get('why') != 'unread') or (row is not None and touched_by_a_filter(row)) \
                or not reading_cells.may_send(page['file']) or page.get('protected'):
            continue  # checked again: the list may be older than the page's history; a page a person checked is not read again;
            # an unread page of a whole work (`--add-work`) has no row in the export yet
        mirror, pdf_page = documents.page(page['file'], page['pdf_page'])
        store = open_store(mirror)
        if mirror not in session_records:
            session_records[mirror] = session_readings(store)
        own = session_records[mirror].get((page['file'], page['pdf_page']), [])
        latest = max(own, key=lambda record: record.get('attempt', 0)) if own else None
        if latest is not None and not (args.retry_malformed and vision_batches.current_class(latest, store) == 'malformed'):
            continue  # read already; a malformed attempt is retried only on request, and only once more each time
        image = page_render.render(pdf_page, RESOLUTION)
        entry = entry_for(cell, page, image, mirror, store, retry_of=latest)
        if store.reading(entry['reading_key']) is not None:
            continue
        folder = session_folder(args.knowledge_base) / (f"{page['work']}__p{page['pdf_page']:04d}"
                                                         + (f"__a{entry['attempt']}" if entry['attempt'] else ''))
        if (folder / 'entry.json').exists():
            continue  # prepared before and not stored yet: another session is reading it (two at a time, 18 Nov night)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'page.png').write_bytes(image.png)
        (folder / 'instructions.md').write_text(
            '# System prompt\n\n' + store.get_prompt(entry['system_sha256']) + '\n\n# User turn\n\n'
            + store.get_prompt(entry['user_sha256']) + '\n', encoding='utf-8')
        (folder / 'entry.json').write_text(json.dumps(entry, indent=1) + '\n', encoding='utf-8')
        (folder / 'layout.md').write_text(layout_lines(pdf_page, image), encoding='utf-8')
        made.append(str(folder))
        print(f"prepared {page['id']} ({page.get('why', '')}): {folder}")
    return made


def session_readings(store) -> dict[tuple[str, int], list[dict]]:
    """Every reading made in a session, by (file, PDF page): the store read once."""
    found: dict[tuple[str, int], list[dict]] = {}
    for record in store.readings():
        if record.get('kind', 'reading') == 'reading' and record.get('mode') == MODE:
            found.setdefault((record['file'], record['pdf_page']), []).append(record)
    return found


def latest_direct(store, page: dict) -> dict | None:
    """The page's latest direct reading, or None."""
    own = [record for record in store.readings() if record.get('kind', 'reading') == 'reading' and record.get('mode') == MODE
           and record['file'] == page['file'] and record['pdf_page'] == page['pdf_page']]
    return max(own, key=lambda record: record.get('attempt', 0)) if own else None


def layout_lines(pdf_page, image: page_render.PageImage) -> str:
    """The PDF's text-layer lines in pixels of the image the session reads, one per line, so a block's bbox is taken from them
    rather than estimated by eye: the first direct readings' boxes, read off a scaled-down view, sat up to a line off (18 Nov).
    A page without a text layer, or a rotated one, says so, and the session estimates as any reader does."""
    if pdf_page.rotation:
        return '(the page is rotated: estimate the boxes from the image)\n'
    sx, sy = image.width / pdf_page.rect.width, image.height / pdf_page.rect.height
    lines = []
    for block in pdf_page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            text = ' '.join(span['text'] for span in line['spans']).strip()
            if text:
                x0, y0, x1, y1 = line['bbox']
                lines.append(f'{round(x0 * sx)} {round(y0 * sy)} {round(x1 * sx)} {round(y1 * sy)} | {text[:60]}')
    header = f'# text-layer lines, x0 y0 x1 y1 in pixels of the {image.width}x{image.height} image, top to bottom\n'
    return header + ('\n'.join(lines) if lines else '(no text layer: estimate the boxes from the image)') + '\n'


def record_for(entry: dict, text: str) -> tuple[dict, str]:
    """The stored record of one direct reading: stage 1 decides its class, as for any reading; it costs no API money."""
    record = {name: entry.get(name) for name in vision_batches.RECORD_FIELDS}
    result_class, checked = vision_batches.check_reading(entry, text, 'end_turn')
    record.update(kind='reading', adapter=ADAPTER, provider=PROVIDER, deviation=entry['deviation'],
                  stored_at=vision_batches.now(), sdk='claude-code session', result_type='succeeded', error_type=None,
                  error_message=None, stop_reason='end_turn', usage={}, cost_usd=0.0, result_class=result_class,
                  text_sha256=reader_requests.sha256_text(text), text_chars=len(text), contract=checked)
    return record, text


BLOCKED_FILE = 'blocked.json'  # {"error_message": the API's words, "request_id": ...}: the filter stopped the session's reader


def blocked_record(entry: dict, said: dict) -> dict:
    """The record of a page the provider's filter blocked while a session's agent read it, in the shape of a batch's blocked
    result (`vision_batches.is_block`), so the export and every check treat it alike. It costs no API money."""
    record = {name: entry.get(name) for name in vision_batches.RECORD_FIELDS}
    record.update(kind='reading', adapter=ADAPTER, provider=PROVIDER, deviation=entry['deviation'],
                  stored_at=vision_batches.now(), sdk='claude-code session', result_type='errored',
                  error_type='invalid_request_error', error_message=said['error_message'][:vision_batches.ERROR_MESSAGE_CHARS],
                  request_id=said.get('request_id'), stop_reason=None, usage={}, cost_usd=0.0, result_class='errored')
    return record


def store(args) -> Counter:
    """Store every prepared page the session has written `reading.md` for, whatever its class: a failed attempt is kept
    and shown like any other. A page already stored is left as it is. A page the provider's filter blocked while the session
    read it (`blocked.json`, written by the session from the agent's error) is stored as blocked: it is never read in the
    session again, by any route (280.a)."""
    outcome = Counter()
    for folder in sorted(session_folder(args.knowledge_base).glob('*__p*')):
        written, blocked = folder / 'reading.md', folder / BLOCKED_FILE
        if not written.exists() and not blocked.exists():
            outcome['not read yet'] += 1
            continue
        entry = json.loads((folder / 'entry.json').read_text(encoding='utf-8'))
        target = open_store(entry['mirror'])
        if target.reading(entry['reading_key']) is not None:
            outcome['already stored'] += 1
            continue
        if not written.exists():
            record = blocked_record(entry, json.loads(blocked.read_text(encoding='utf-8')))
            target.save_reading(entry['reading_key'], record, None)
            outcome['blocked'] += 1
            print(f"stored {entry['page_id']}: blocked by the provider's filter, key {entry['reading_key'][:12]}")
            continue
        record, text = record_for(entry, written.read_text(encoding='utf-8'))
        target.save_reading(entry['reading_key'], record, text)
        outcome[record['result_class']] += 1
        print(f"stored {entry['page_id']}: {record['result_class']}, key {entry['reading_key'][:12]}")
    print(f'{cell_name(args.knowledge_base)}: {dict(outcome)}')
    return outcome


def choose(args) -> dict:
    """Let a direct reading stand for its page where the check passed it, as for a second reader (47.a): one append-only row
    per page; a page whose direct reading is an issue, malformed or not yet checked keeps what it had. Passed is the judge's
    ok, or `ok_unjudged` where the page lay outside the judge's sample of a work read whole and that sample passed (the
    operator's V1.b, 19 Nov), as on every other cell."""
    from backend.conversion.checks import check_run
    from backend.conversion.store import pipeline_db, reading_export

    name = cell_name(args.knowledge_base)
    target = open_store(args.knowledge_base)
    states = reading_export.check_states(target, (name,))
    current = pipeline_db.chosen(args.knowledge_base)
    outcome = Counter()
    for record in check_run.latest_per_page(vision_batches.readings_of([name], target)):
        state = (states.get(record['reading_key']) or {}).get('state')
        if state not in PASSED:
            outcome[f'not chosen: {state or "not checked"}'] += 1
        elif (current.get((record['file'], record['pdf_page'])) or {}).get('reading_key') == record['reading_key']:
            outcome['already chosen'] += 1
        else:
            pipeline_db.choose(args.knowledge_base, record['file'], record['pdf_page'], record['reading_key'],
                               why=f"direct reading ({record['model']}): {record['deviation']}")
            outcome['chosen'] += 1
    print(f'{name}: {dict(outcome)}')
    return dict(outcome)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('pages', 'prepare', 'store', 'choose'):
        command = commands.add_parser(name)
        command.add_argument('--knowledge-base', choices=('free', 'licensed'), required=True)
        if name == 'pages':
            command.add_argument('--add-work', action='append', metavar='FILE',
                                 help='add every unread page of this file to the cell, kept on later runs (the experiment of 18 Nov)')
            command.add_argument('--judge-share', type=float, metavar='SHARE',
                                 help="with --add-work: judge this share of the work's pages, e.g. 0.6 for a night's work (N2.a)")
        if name == 'prepare':
            command.add_argument('--limit', type=int, default=1, help='at most this many pages; 0 prepares all')
            command.add_argument('--page', help="one page by its id, e.g. 'work:p0103'")
            command.add_argument('--work', action='append', metavar='FILE', help="only this file's pages (a night's works)")
            command.add_argument('--retry-malformed', action='store_true',
                                 help="prepare a new attempt where the latest direct reading is malformed, its errors as the hint")
    checked = commands.add_parser('check', help="the format check on one prepared folder's reading.md, for the reading agent")
    checked.add_argument('folder', type=Path)
    args = parser.parse_args(argv)
    {'pages': pages, 'prepare': prepare, 'store': store, 'choose': choose, 'check': check}[args.command](args)
    return 0


def check(args) -> bool:
    """The format check (today's validator) on a folder's `reading.md` against its entry: valid or MALFORMED, and the errors,
    which name lines and blocks. Run once by the agent that wrote it; the reading is not changed after, since a retry is an
    attempt of its own. Prints no page text."""
    from backend.conversion.contract import page_contract

    entry = json.loads((args.folder / 'entry.json').read_text(encoding='utf-8'))
    expected = page_contract.Expected(entry['work'], entry['pdf_page'], tuple(entry['image_size']))
    page = page_contract.parse((args.folder / 'reading.md').read_text(encoding='utf-8'), 'markdown', expected)
    print('valid' if page.valid else 'MALFORMED', f'{len(page.blocks)} blocks, {len(page.warnings)} warnings')
    for error in page.errors:
        print('  error:', error[:200])
    return page.valid


if __name__ == '__main__':
    raise SystemExit(main())
