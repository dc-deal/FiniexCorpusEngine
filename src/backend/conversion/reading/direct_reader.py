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
REASONS = ('malformed', 'no_page')  # the hard cases this cell takes; a judge's issue goes to a person's review first
FILTER_WORDS = ('blocked', 'refus', 'declin', 'content_filter', 'policy')


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
        if why not in REASONS:
            continue
        key = (row['file'], row['pdf_page'])
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
    cards = {page['work']: page.pop('work_card') for page in chosen}
    target = reading_cells.DIRECT_PAGES[args.knowledge_base]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'work_cards': cards, 'pages': chosen}, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"{args.knowledge_base}: {len(chosen)} pages for a direct reading {dict(Counter(p['why'] for p in chosen))}, "
          f'written to {target.name}; left out {dict(left)}')
    return {'pages': len(chosen), 'left': dict(left)}


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
    for page in reading_cells.pages_for(cell):
        if args.limit and len(made) >= args.limit:
            break
        if args.page and page['id'] != args.page:
            continue
        row = rows.get((page['file'], page['pdf_page']))
        if row is None or touched_by_a_filter(row) or not reading_cells.may_send(page['file']):
            continue  # checked again: the list may be older than the page's history
        mirror, pdf_page = documents.page(page['file'], page['pdf_page'])
        image = page_render.render(pdf_page, RESOLUTION)
        store = open_store(mirror)
        latest = latest_direct(store, page)
        if latest is not None and not (args.retry_malformed and vision_batches.current_class(latest, store) == 'malformed'):
            continue  # read already; a malformed attempt is retried only on request, and only once more each time
        entry = entry_for(cell, page, image, mirror, store, retry_of=latest)
        if store.reading(entry['reading_key']) is not None:
            continue
        folder = session_folder(args.knowledge_base) / (f"{page['work']}__p{page['pdf_page']:04d}"
                                                         + (f"__a{entry['attempt']}" if entry['attempt'] else ''))
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


def store(args) -> Counter:
    """Store every prepared page the session has written `reading.md` for, whatever its class: a failed attempt is kept
    and shown like any other. A page already stored is left as it is."""
    outcome = Counter()
    for folder in sorted(session_folder(args.knowledge_base).glob('*__p*')):
        written = folder / 'reading.md'
        if not written.exists():
            outcome['not read yet'] += 1
            continue
        entry = json.loads((folder / 'entry.json').read_text(encoding='utf-8'))
        target = open_store(entry['mirror'])
        if target.reading(entry['reading_key']) is not None:
            outcome['already stored'] += 1
            continue
        record, text = record_for(entry, written.read_text(encoding='utf-8'))
        target.save_reading(entry['reading_key'], record, text)
        outcome[record['result_class']] += 1
        print(f"stored {entry['page_id']}: {record['result_class']}, key {entry['reading_key'][:12]}")
    print(f'{cell_name(args.knowledge_base)}: {dict(outcome)}')
    return outcome


def choose(args) -> dict:
    """Let a direct reading stand for its page where the judge found it ok, as for a second reader (47.a): one append-only row
    per page; a page whose direct reading is an issue, malformed or not yet judged keeps what it had."""
    from backend.conversion.checks import check_run
    from backend.conversion.store import pipeline_db, reading_export

    name = cell_name(args.knowledge_base)
    target = open_store(args.knowledge_base)
    states = reading_export.check_states(target, (name,))
    current = pipeline_db.chosen(args.knowledge_base)
    outcome = Counter()
    for record in check_run.latest_per_page(vision_batches.readings_of([name], target)):
        state = (states.get(record['reading_key']) or {}).get('state')
        if state != 'ok':
            outcome[f'not chosen: {state or "not judged"}'] += 1
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
        if name == 'prepare':
            command.add_argument('--limit', type=int, default=1, help='at most this many pages; 0 prepares all')
            command.add_argument('--page', help="one page by its id, e.g. 'work:p0103'")
            command.add_argument('--retry-malformed', action='store_true',
                                 help="prepare a new attempt where the latest direct reading is malformed, its errors as the hint")
    args = parser.parse_args(argv)
    {'pages': pages, 'prepare': prepare, 'store': store, 'choose': choose}[args.command](args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
