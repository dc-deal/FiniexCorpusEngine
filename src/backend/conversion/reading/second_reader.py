"""A second reader for pages the default reader could not give: another company's model through OpenRouter (decision 63.a).

The default reader is Claude Sonnet in batches (`frozen_contract.json`). Where it gave no usable page (the provider's filter
blocked it, the reader declined it, or for a free page it stayed malformed after its one format retry), this module asks a model
of another company through OpenRouter's OpenAI-compatible endpoint: the same frozen system prompt, the same page image, the same
user turn. Its reading is stored like any other, keyed by everything that was asked, so it is never bought twice, and it says why
it exists: its `deviation` names what the default reader did. Stage 1 classes it as it classes every reading; stage 2 and the
judge then see every page of a second reader's cell (`check_run`).

    python -m backend.conversion.reading.second_reader pages --knowledge-base free            # which pages and why; spends nothing
    python -m backend.conversion.reading.second_reader read --knowledge-base free --reader TERRA --limit 5 [--dry-run]
    python -m backend.conversion.reading.second_reader choose --knowledge-base free --reader TERRA  # the judged ones stand

The candidates and their cells are in `reading_cells` (`SECOND_READERS`, `FREE-2ND-*`). Their spend is the course key's, never
the Claude credit's: their ledger lines say `provider: openrouter`, the Claude spend guard leaves them out, and this module stops
before the key's usage would pass `--key-cap`, read from OpenRouter itself. OpenAI's SDK is used directly, with an explicit
timeout and no hidden retries; a page whose request failed for a passing reason (a timeout, a server error) is not stored, so it
can be asked again, while an answer, a refusal or a block is stored for good.
"""

import argparse
import base64
import concurrent.futures
import json
import random
import sys
import threading
from collections import Counter, defaultdict
from pathlib import Path

import openai

from backend.conversion.reading import page_render, reader_requests, reading_cells, vision_batches
from backend.conversion.store import served_readings
from backend.conversion.store.reading_store import open_store
from backend.providers import openrouter_client

ADAPTER = 'openai-compatible'
PROVIDER = 'openrouter'
MODE = 'openrouter'
FORM = 'markdown'
RESOLUTION = 'hi'
MAX_TOKENS = 16000
TIMEOUT_SECONDS = 600
# The course key's own limit (33 USD): no reserve of our own any more (the operator, 18 Nov: "wir brauchen keine limits mehr";
# should the key run dry before 23 Nov, the router moves to Anthropic early). Until then 28 kept 5 for the capstone's runs.
KEY_CAP_USD = 33.0
IMAGE_TOKENS_ESTIMATE = 3000  # providers count image tokens differently; above what the three candidates charge for a page
PILOT_SEED = 'second reader pilot'
# What the default reader did, by the text-layer reason of `served_readings`, and for which of these reasons each knowledge
# base lets a second reader read a page (decision 63.a for the free one).
# A default reading that found no page declined it in prose (18 Nov: five of five), so it is a refusal for the second reader
# too (G1.a, the operator, 18 Nov).
DEVIATIONS = {'blocked': 'anthropic blocked the page (content filter)',
              'refused': 'the default reader declined the page',
              'no_page': 'the default reader declined the page in prose, with no page',
              'malformed': 'the default reading stayed malformed after its one format retry'}
REASONS = {'free': ('blocked', 'refused', 'no_page', 'malformed'), 'licensed': ('blocked', 'refused', 'no_page')}
REASON_OF = {text: reason for reason, text in DEVIATIONS.items()}  # a second reading's deviation back to its reason
STOP_REASONS = {'stop': 'end_turn', 'length': 'max_tokens', 'content_filter': 'refusal'}  # OpenAI's words in Claude's


def export_of(knowledge_base: str) -> Path:
    from backend.conversion.store import reading_export

    return reading_export.BASES[knowledge_base].export


def pages(args) -> dict:
    """Write the page list of a knowledge base's second reader: every page whose default reading may not be served for one of
    the reasons above, with the work card and the estimate its default cell gave it, and its deviation."""
    from backend.conversion.store import reading_export

    base = reading_export.BASES[args.knowledge_base]
    rows = json.loads((base.export / 'index.json').read_text(encoding='utf-8'))['pages']
    # the default cells' pages, and the session's: a page the filter blocked while the session read it (a work read whole at
    # night) is in no default cell (found 20 Nov: such a page raised a KeyError here)
    direct = tuple(name for name in reading_export.cells_beside(base) if '-DIRECT-' in name)
    listed = {(page['file'], page['pdf_page']): page
              for name in base.cells() + direct for page in reading_cells.pages_for(reading_cells.known_cells()[name])}
    stopped: dict[str, set[str]] = defaultdict(set)
    for cell, work in reading_export.stopped_works(open_store(args.knowledge_base),
                                                   base.cells() + reading_export.cells_beside(base)):
        stopped[work].add(cell)
    chosen, reasons, held = select(rows, listed, args.knowledge_base, stopped)
    cards = {page['work']: page.pop('work_card') for page in chosen}
    target = reading_cells.SECOND_READER_PAGES[args.knowledge_base]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'work_cards': cards, 'pages': chosen}, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'{args.knowledge_base}: {len(chosen)} pages for the second reader {dict(reasons)}, written to {target.name}'
          + (f'; {sum(held.values())} of them in works a check stopped for a reader, not read by that reader (130.a, 288.a): '
             f'{dict(held)}' if held else ''))
    return {'pages': chosen, 'reasons': dict(reasons), 'stopped': dict(held)}


def select(rows: list[dict], listed: dict, knowledge_base: str,
           stopped: dict[str, set[str]]) -> tuple[list[dict], Counter, Counter]:
    """The pages of a second reader's cell: those whose default reading may not be served for one of this base's reasons.

    A stop belongs to the reader whose check stopped a work, not to the work (decision 288.a, the operator, 18 Nov): a reader
    that read a work badly is stopped there, and another reader may still read it. So a page of a stopped work names the
    cells that stopped it (`stopped_by`), and `read` skips it for those cells alone. A page whose second reading is held back by
    such a stop (its text layer serves it, `stopped`) is in the cell too, under the reason its default reading failed, so
    another reader can read it. Every such page stays in the list all the same: the list is the cell, the cell's plan and
    report are made over it, and the report is where the stop is kept. Leaving stopped pages out (17 Nov) took the stopped
    works out of the next report, the stop with them, and the export served pages the stop holds back. Returns the pages
    (with their work cards), the count by reason, and the count of pages in stopped works by work."""
    chosen, reasons, held = [], Counter(), Counter()
    for row in rows:
        why = served_readings.text_layer_why(row)
        # A second reading served, or held back by its reader's stop: the page failed its default reader before. Both stay
        # in the cell, so its plan and report keep every page a reader read: when chosen pages left the list (18 Nov), the
        # sample gate counted only the bad pages left behind and stopped a reader on a work it had read well.
        served = why is None and REASON_OF.get(row.get('deviation')) is not None
        if why == 'stopped' or served:
            why = REASON_OF.get(row.get('deviation'))
        if why not in REASONS[knowledge_base]:
            continue
        page = listed[(row['file'], row['pdf_page'])]
        entry = {'file': page['file'], 'pdf_page': page['pdf_page'], 'work': page['work'], 'gold': False,
                 'class_note': page.get('class_note', ''), 'expected_output_tokens': page['expected_output_tokens'],
                 'deviation': DEVIATIONS[why], 'work_card': page['work_card']}
        if served:
            entry['served'] = True  # `read` leaves it: its second reading is served already
        if stopped.get(page['work']):
            entry['stopped_by'] = sorted(stopped[page['work']])
            held[page['work']] += 1
        chosen.append(entry)
        reasons[why] += 1
    return chosen, reasons, held


def pilot_order(cell_pages: list[dict]) -> list[dict]:
    """The cell's pages in one seeded order, so every candidate of a pilot reads the same first pages."""
    ordered = sorted(cell_pages, key=lambda page: (page['file'], page['pdf_page']))
    random.Random(PILOT_SEED).shuffle(ordered)
    return ordered


def reading_spec(*, image_sha: str, model: str, system_sha: str, user_sha: str) -> dict:
    """Everything a second reading asks, as hashes and parameters: the input of its key. No Claude parameter is in it."""
    return {'inputs': {'image': image_sha}, 'model': model, 'adapter': ADAPTER, 'provider': PROVIDER,
            'prompt': {'system': system_sha, 'user': user_sha, 'form': FORM, 'schema': None},
            'params': {'max_tokens': MAX_TOKENS, 'replicate': 0, 'attempt': 0}, 'mode': MODE}


def estimate_usd(prices: dict, expected_output_tokens: int) -> float:
    tokens_in = reader_requests.SYSTEM_PROMPT_TOKENS[FORM] + reader_requests.USER_TURN_TOKENS + IMAGE_TOKENS_ESTIMATE
    return (tokens_in * prices['input'] + min(expected_output_tokens, MAX_TOKENS) * prices['output']) / 1e6


def entry_for(cell: reading_cells.Cell, page: dict, image: page_render.PageImage, mirror: str, store, prices: dict) -> dict:
    """One request of a second reader's cell: what it sends stored by hash, everything it asks in its key."""
    system_sha = store.put_prompt(reader_requests.system_prompt(FORM))
    user_sha = store.put_prompt(vision_batches.reader_turn(page, image))
    image_sha = store.put_input(image.png, '.png')
    key = reader_requests.reading_key(reading_spec(image_sha=image_sha, model=cell.model, system_sha=system_sha, user_sha=user_sha))
    return {'kind': 'reading', 'reading_key': key, 'custom_id': reader_requests.custom_id(key), 'cell': cell.name,
            'page_id': page['id'], 'file': page['file'], 'pdf_page': page['pdf_page'], 'work': page['work'], 'mirror': mirror,
            'model': cell.model, 'resolution': RESOLUTION, 'form': FORM, 'replicate': 0, 'attempt': 0, 'max_tokens': MAX_TOKENS,
            'image_sha256': image_sha, 'image_size': [image.width, image.height], 'image_bytes': len(image.png),
            'system_sha256': system_sha, 'user_sha256': user_sha, 'mode': MODE, 'adapter': ADAPTER, 'provider': PROVIDER,
            'deviation': page['deviation'], 'estimate_usd': estimate_usd(prices, page['expected_output_tokens'])}


def request_body(entry: dict, system_text: str, user_text: str, png: bytes) -> dict:
    """The chat completion of one page: the frozen prompt as the system message, the image first and the user turn after it.
    `usage.include` asks OpenRouter for the request's cost."""
    image = {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.standard_b64encode(png).decode('ascii')}}
    return {'model': entry['model'], 'max_tokens': entry['max_tokens'],
            'messages': [{'role': 'system', 'content': system_text},
                         {'role': 'user', 'content': [image, {'type': 'text', 'text': user_text}]}],
            'extra_body': {'usage': {'include': True}}}


def client() -> openai.OpenAI:
    return openai.OpenAI(base_url=openrouter_client.OPENROUTER_BASE_URL, api_key=openrouter_client.api_key(),
                         timeout=TIMEOUT_SECONDS, max_retries=0)


def answer_text(choice) -> str:
    content = choice.message.content
    if isinstance(content, list):  # some providers answer in parts
        return ''.join(part.get('text', '') if isinstance(part, dict) else str(part) for part in content)
    return content or ''


def record_for(entry: dict, response=None, error: Exception | None = None) -> tuple[dict, str | None]:
    """The stored record of one answer, a refusal or a block, and the answer's text (None when there is none)."""
    record = {name: entry.get(name) for name in vision_batches.RECORD_FIELDS}
    record.update(kind='reading', adapter=ADAPTER, provider=PROVIDER, deviation=entry['deviation'], stored_at=vision_batches.now(),
                  sdk=f'openai {openai.__version__}')
    if response is None:
        message = str(getattr(error, 'message', error))[:vision_batches.ERROR_MESSAGE_CHARS]
        record.update(result_type='errored', error_type=f'http_{getattr(error, "status_code", "error")}', error_message=message,
                      result_class='errored', cost_usd=0.0)
        return record, None
    choice = response.choices[0]
    text = answer_text(choice)
    stop_reason = STOP_REASONS.get(choice.finish_reason, choice.finish_reason)
    result_class, checked = vision_batches.check_reading(entry, text, stop_reason)
    usage = response.usage.model_dump() if response.usage is not None else {}
    record.update(result_type='succeeded', error_type=None, error_message=None, message_id=response.id,
                  response_model=response.model, response_provider=getattr(response, 'provider', None), stop_reason=stop_reason,
                  finish_reason=choice.finish_reason, usage=usage, cost_usd=float(usage.get('cost') or 0.0),
                  result_class=result_class, text_sha256=reader_requests.sha256_text(text), text_chars=len(text), contract=checked)
    return record, text


def is_passing(error: Exception) -> bool:
    """A failure that says nothing about the page: asked again later, never stored. Only a refusal of the content is stored,
    which OpenRouter answers with 403 when a moderation flags the request. Everything else concerns the key or the route:
    a 404 "0 endpoints … matching your guardrail" (the course key's data policy excludes a provider; measured on Google's
    models, 2026-11-04), a timeout, a server error, a rate limit."""
    return not isinstance(error, openai.PermissionDeniedError)


def cell_name(knowledge_base: str, reader: str) -> str:
    return f"{'FREE' if knowledge_base == 'free' else 'LIC'}-2ND-{reader}"


def choose(args) -> dict:
    """Let a second reading stand for its page where the judge found it ok: one append-only row per page in the pipeline
    database, naming the reader and why the default reading could not stand (decisions 47.a, 63.a). A page whose second
    reading is an issue, malformed or not yet judged keeps its text layer; a page already chosen is left as it is."""
    from backend.conversion.checks import check_run
    from backend.conversion.store import pipeline_db, reading_export

    name = cell_name(args.knowledge_base, args.reader)
    store = open_store(args.knowledge_base)
    states = reading_export.check_states(store, (name,))
    current = pipeline_db.chosen(args.knowledge_base)
    recorded = getattr(args, 'recorded', None)
    outcome = Counter()
    for record in check_run.latest_per_page(vision_batches.readings_of([name], store)):
        state = (states.get(record['reading_key']) or {}).get('state')
        if state != 'ok':
            outcome[f'not chosen: {state or "not judged"}'] += 1
        elif (current.get((record['file'], record['pdf_page'])) or {}).get('reading_key') == record['reading_key']:
            outcome['already chosen'] += 1
        else:
            pipeline_db.choose(args.knowledge_base, record['file'], record['pdf_page'], record['reading_key'],
                               why=f"second reader ({record['model']}): {record['deviation']}",
                               run_id=recorded.run_id if recorded else None)
            outcome['chosen'] += 1
    print(f'{name}: {dict(outcome)}')
    return dict(outcome)


def read(args) -> dict:
    """Read the pages of one second reader's cell through OpenRouter, `--workers` requests side by side (one by default),
    until `--limit` or the key cap."""
    name = cell_name(args.knowledge_base, args.reader)
    cell = reading_cells.known_cells().get(name)
    if cell is None:
        sys.exit(f'no cell {name}: run `second_reader pages --knowledge-base {args.knowledge_base}` first')
    prices = openrouter_client.model_prices([cell.model]).get(cell.model)
    if prices is None:
        sys.exit(f'OpenRouter does not list {cell.model}')
    documents, todo, skipped = vision_batches.Documents(), [], Counter()
    from backend.conversion.store import pipeline_db

    over = (getattr(args, 'over_a_person', None) or '').strip()
    checked = {}
    for page in pilot_order(reading_cells.pages_for(cell)):
        if args.limit and len(todo) >= args.limit:
            break
        if name in page.get('stopped_by', ()) or page.get('stopped') is True:  # this reader's stop holds (130.a, 288.a)
            skipped['a check stopped its work for this reader'] += 1
            continue
        if page.get('served'):  # in the cell for its report, its second reading served already
            skipped['a second reading is served'] += 1
            continue
        mirror, pdf_page = documents.page(page['file'], page['pdf_page'])
        if not over:  # a page a person checked is not read again (decision 191.a)
            if mirror not in checked:
                checked[mirror] = pipeline_db.protected_pages(mirror)
            if (page['file'], page['pdf_page']) in checked[mirror]:
                skipped['a person checked it'] += 1
                continue
        store = open_store(mirror)
        entry = entry_for(cell, page, page_render.render(pdf_page, RESOLUTION), mirror, store, prices)
        if store.reading(entry['reading_key']) is not None:
            skipped['already read'] += 1
            continue
        todo.append(entry)
    estimate = sum(entry['estimate_usd'] for entry in todo)
    used = openrouter_client.key_usage()
    print(f'{name} ({cell.model}): {len(todo)} pages, estimate {estimate:.4f} USD; key used {used:.4f} of the cap {args.key_cap}; '
          f'skipped {dict(skipped)}')
    if args.dry_run or not todo:
        return {'cell': name, 'pages': len(todo), 'estimate_usd': estimate, 'classes': {}}
    caller, classes, lock = client(), Counter(), threading.Lock()
    money = {'spent': 0.0, 'reserved': 0.0, 'capped': False}

    def one(entry: dict) -> None:
        # A request's estimate is reserved before it goes out, so pages read side by side never pass the key cap together
        with lock:
            if money['capped'] or used + money['spent'] + money['reserved'] + entry['estimate_usd'] > args.key_cap:
                if not money['capped']:
                    print(f"stopped at the key cap: used {used:.4f} + spent {money['spent']:.4f} + reserved "
                          f"{money['reserved']:.4f} + next {entry['estimate_usd']:.4f} > {args.key_cap}")
                money['capped'] = True
                return
            money['reserved'] += entry['estimate_usd']
        store = open_store(entry['mirror'])
        body = request_body(entry, store.get_prompt(entry['system_sha256']), store.get_prompt(entry['user_sha256']),
                            store.get_input(entry['image_sha256'], '.png'))
        try:
            record, text = record_for(entry, caller.chat.completions.create(**body))
        except openai.APIError as error:
            if is_passing(error):
                with lock:
                    money['reserved'] -= entry['estimate_usd']
                    classes['passing failure, not stored'] += 1
                return
            record, text = record_for(entry, error=error)
        with lock:  # one writer at a time into the store and its ledger
            vision_batches.store_result(entry, record, text)
            money['reserved'] -= entry['estimate_usd']
            money['spent'] += record['cost_usd']
            classes[record['result_class']] += 1

    # The time is the model's generation (about a minute a page for Mistral, 8 Nov), not the money: pages side by side
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, getattr(args, 'workers', 1))) as pool:
        for future in [pool.submit(one, entry) for entry in todo]:
            future.result()  # an unexpected error ends the run here, as it did one page at a time
    spent = money['spent']
    measured = openrouter_client.key_usage() - used
    print(f'{name}: {dict(classes)}, {spent:.4f} USD by the answers, {measured:.4f} USD by the key')
    return {'cell': name, 'pages': len(todo), 'estimate_usd': estimate, 'classes': dict(classes), 'spent_usd': spent,
            'measured_usd': measured}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    pages_parser = commands.add_parser('pages')
    pages_parser.add_argument('--knowledge-base', choices=sorted(REASONS), required=True)
    pages_parser.set_defaults(run=pages)
    read_parser = commands.add_parser('read')
    read_parser.add_argument('--knowledge-base', choices=sorted(REASONS), required=True)
    read_parser.add_argument('--reader', choices=sorted(reading_cells.SECOND_READERS), required=True)
    read_parser.add_argument('--limit', type=int, default=0, help='at most this many pages, in the pilot order; 0 reads all')
    read_parser.add_argument('--key-cap', type=float, default=KEY_CAP_USD, help="stop before the course key's usage passes this")
    read_parser.add_argument('--workers', type=int, default=1, help='pages read side by side (default 1, one at a time)')
    read_parser.add_argument('--dry-run', action='store_true')
    read_parser.add_argument('--over-a-person', metavar='REASON',
                             help='read pages a person checked too; without it they are skipped (decision 191.a)')
    read_parser.set_defaults(run=read)
    choose_parser = commands.add_parser('choose')
    choose_parser.add_argument('--knowledge-base', choices=sorted(REASONS), required=True)
    choose_parser.add_argument('--reader', choices=sorted(reading_cells.SECOND_READERS), required=True)
    choose_parser.set_defaults(run=choose)
    return parser


def main() -> None:
    from backend.conversion.store import pipeline_db

    sys.stdout.reconfigure(encoding='utf-8')
    vision_batches.quiet_sdk_logs()
    args = build_parser().parse_args()
    with pipeline_db.run([args.knowledge_base], pipeline_db.command_line('backend.conversion.reading.second_reader')) as recorded:
        args.recorded = recorded
        args.run(args)


if __name__ == '__main__':
    main()
