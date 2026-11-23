"""Where the default reader and its judge share a blind spot: an independent reader of another company on pages they passed.

The default reader and the judge are the same model (`frozen_contract.json`), so an error both miss is never measured. This
measurement asks a reader of another company, through OpenRouter, to read a seeded sample of free pages that the default reader
read and the judge passed. Code then compares the two readings word by word, and a person looks at the pages where they differ:
a difference the image confirms is an error the reader and the judge share. The measurement used the course key's last credit
(the operator, 23 Nov 2026).

Its readings are a measurement's, never a page's reading. The purpose is part of their key, so no other cell's question can
ever be the same one. They stand in no cell a knowledge base serves, and nothing chooses them. Free pages only.

    python -m backend.conversion.measurement.blind_spot sample --pages 100            # the sample; spends nothing
    python -m backend.conversion.measurement.blind_spot read [--limit N] [--workers 4] [--dry-run]
    python -m backend.conversion.measurement.blind_spot compare                       # the comparison; spends nothing
"""

import argparse
import concurrent.futures
import difflib
import json
import random
import re
import sys
import threading
from collections import Counter
from pathlib import Path

import openai

from backend.configuration import data_paths
from backend.conversion.contract import page_contract
from backend.conversion.reading import page_render, reader_requests, reading_cells, second_reader, vision_batches
from backend.conversion.store.reading_store import open_store
from backend.providers import openrouter_client

FOLDER = data_paths.FREE_WORKING / 'blind_spot'
SAMPLE = FOLDER / 'pages.json'
REPORT = FOLDER / 'comparison.json'
EXPORT = data_paths.FREE_READINGS
CELL = 'BLIND-FREE-TERRA'  # a label for the ledger and the records; no knowledge base names it
MODEL = reading_cells.SECOND_READERS['TERRA']
PURPOSE = 'blind spot: an independent reader of a page the default reader read and the judge passed'
SEED = 'blind spot 2026-11-23'
EXPECTED_OUTPUT_TOKENS = reading_cells.CORPUS_OUTPUT_TOKENS
FLAG_BELOW = 0.97  # a page whose verbatim words agree less than this is looked at by a person
WORD = re.compile(r"[a-z0-9]+(?:[.,'][a-z0-9]+)*")
TAG = re.compile(r'<[^>]+>')  # a table's markup: two readers write the same table with other tags, and only its words count


def candidates(rows: list[dict]) -> list[dict]:
    """The free pages the default reader read and the judge passed: a checked reading of the corpus cell, judged ok, on a page
    of content (not a cover, a table of contents or an index)."""
    found = []
    for row in rows:
        check = row.get('check') or {}
        if (check.get('state') == 'ok' and check.get('judged') and row.get('route_level') == 'checked'
                and row.get('category') == 'content' and row.get('deviation') is None and row.get('text_file')):
            found.append({'file': row['file'], 'pdf_page': row['pdf_page'], 'work': row['work'],
                          'served_key': row['reading_key'], 'text_file': row['text_file']})
    return sorted(found, key=lambda page: (page['file'], page['pdf_page']))


def sample(args) -> dict:
    rows = json.loads((EXPORT / 'index.json').read_text(encoding='utf-8'))['pages']
    pool = candidates(rows)
    chosen = sorted(random.Random(SEED).sample(pool, min(args.pages, len(pool))), key=lambda page: (page['file'], page['pdf_page']))
    FOLDER.mkdir(parents=True, exist_ok=True)
    SAMPLE.write_text(json.dumps({'about': PURPOSE, 'seed': SEED, 'model': MODEL, 'pool': len(pool), 'pages': chosen},
                                 ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{len(chosen)} of {len(pool)} pages sampled, by works {dict(Counter(page["work"] for page in chosen))}')
    return {'pool': len(pool), 'pages': len(chosen)}


def reading_spec(*, image_sha: str, system_sha: str, user_sha: str) -> dict:
    """The second reader's question, its purpose added, so its key is never another cell's."""
    spec = second_reader.reading_spec(image_sha=image_sha, model=MODEL, system_sha=system_sha, user_sha=user_sha)
    spec['purpose'] = PURPOSE
    return spec


def entry_for(page: dict, image: page_render.PageImage, cards: dict, store, prices: dict) -> dict:
    turn_page = {**page, 'work_card': cards[page['work']]}
    system_sha = store.put_prompt(reader_requests.system_prompt(second_reader.FORM))
    user_sha = store.put_prompt(vision_batches.reader_turn(turn_page, image))
    image_sha = store.put_input(image.png, '.png')
    key = reader_requests.reading_key(reading_spec(image_sha=image_sha, system_sha=system_sha, user_sha=user_sha))
    return {'kind': 'reading', 'reading_key': key, 'custom_id': reader_requests.custom_id(key), 'cell': CELL,
            'page_id': f"{page['work']}:p{page['pdf_page']:04d}", 'file': page['file'], 'pdf_page': page['pdf_page'],
            'work': page['work'], 'mirror': 'free', 'model': MODEL, 'resolution': second_reader.RESOLUTION,
            'form': second_reader.FORM, 'replicate': 0, 'attempt': 0, 'max_tokens': second_reader.MAX_TOKENS,
            'image_sha256': image_sha, 'image_size': [image.width, image.height], 'image_bytes': len(image.png),
            'system_sha256': system_sha, 'user_sha256': user_sha, 'mode': second_reader.MODE, 'adapter': second_reader.ADAPTER,
            'provider': second_reader.PROVIDER, 'deviation': PURPOSE,
            'estimate_usd': second_reader.estimate_usd(prices, EXPECTED_OUTPUT_TOKENS)}


def read(args) -> dict:
    listed = json.loads(SAMPLE.read_text(encoding='utf-8'))['pages']
    cards = json.loads(reading_cells.MINI_PILOT.read_text(encoding='utf-8'))['work_cards']
    prices = openrouter_client.model_prices([MODEL]).get(MODEL)
    if prices is None:
        sys.exit(f'OpenRouter does not list {MODEL}')
    store, documents, todo, skipped = open_store('free'), vision_batches.Documents(), [], Counter()
    for page in listed:
        if args.limit and len(todo) >= args.limit:
            break
        _, pdf_page = documents.page(page['file'], page['pdf_page'])
        entry = entry_for(page, page_render.render(pdf_page, second_reader.RESOLUTION), cards, store, prices)
        if store.reading(entry['reading_key']) is not None:
            skipped['already read'] += 1
            continue
        todo.append(entry)
    estimate, used = sum(entry['estimate_usd'] for entry in todo), openrouter_client.key_usage()
    print(f'{CELL} ({MODEL}): {len(todo)} pages, estimate {estimate:.4f} USD; key used {used:.4f} of the cap {args.key_cap}; '
          f'skipped {dict(skipped)}')
    if args.dry_run or not todo:
        return {'pages': len(todo), 'estimate_usd': estimate}
    caller, classes, lock = second_reader.client(), Counter(), threading.Lock()
    money = {'spent': 0.0, 'reserved': 0.0, 'capped': False}

    def one(entry: dict) -> None:
        with lock:  # an estimate is reserved before its request goes out, so requests side by side never pass the cap
            if money['capped'] or used + money['spent'] + money['reserved'] + entry['estimate_usd'] > args.key_cap:
                money['capped'] = True
                return
            money['reserved'] += entry['estimate_usd']
        body = second_reader.request_body(entry, store.get_prompt(entry['system_sha256']), store.get_prompt(entry['user_sha256']),
                                          store.get_input(entry['image_sha256'], '.png'))
        try:
            record, text = second_reader.record_for(entry, caller.chat.completions.create(**body))
        except openai.APIError as error:
            if second_reader.is_passing(error):
                with lock:
                    money['reserved'] -= entry['estimate_usd']
                    classes['passing failure, not stored'] += 1
                return
            record, text = second_reader.record_for(entry, error=error)
        with lock:
            vision_batches.store_result(entry, record, text)
            money['reserved'] -= entry['estimate_usd']
            money['spent'] += record['cost_usd']
            classes[record['result_class']] += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for future in [pool.submit(one, entry) for entry in todo]:
            future.result()
    print(f"{CELL}: {dict(classes)}, {money['spent']:.4f} USD by the answers"
          + (', stopped at the key cap' if money['capped'] else ''))
    return {'pages': len(todo), 'classes': dict(classes), 'spent_usd': money['spent']}


def verbatim_words(text: str) -> list[str]:
    """The words of a reading's verbatim blocks, lower case, in reading order: what a quote could take from it. A block the
    contract marks derived (a figure's description) is left out, since two readers describe a picture in their own words."""
    page = page_contract.parse(text, 'markdown')
    words = []
    for block in page.blocks:
        spec = page_contract.VOCAB['classes'].get(block.cls) or {}
        if spec.get('content') in ('V', 'V*'):
            words += WORD.findall(TAG.sub(' ', block.body or '').lower())
    return words


def differences(served: list[str], other: list[str], limit: int = 6) -> tuple[float, list[dict]]:
    """How far the two word lists agree (difflib's ratio), and the first places where they do not."""
    matcher = difflib.SequenceMatcher(a=served, b=other, autojunk=False)
    spans = [{'op': op, 'served': ' '.join(served[i1:i2])[:120], 'other': ' '.join(other[j1:j2])[:120]}
             for op, i1, i2, j1, j2 in matcher.get_opcodes() if op != 'equal']
    return round(matcher.ratio(), 4), spans[:limit]


def compare(args) -> dict:
    listed = json.loads(SAMPLE.read_text(encoding='utf-8'))['pages']
    cards = json.loads(reading_cells.MINI_PILOT.read_text(encoding='utf-8'))['work_cards']
    store, documents, rows, outcome = open_store('free'), vision_batches.Documents(), [], Counter()
    for page in listed:
        _, pdf_page = documents.page(page['file'], page['pdf_page'])
        image = page_render.render(pdf_page, second_reader.RESOLUTION)
        key = entry_for(page, image, cards, store, {'input': 0.0, 'output': 0.0})['reading_key']
        record = store.reading(key)
        if record is None:
            outcome['not read'] += 1
            continue
        if record.get('result_class') != 'ok':
            outcome[f"other reader: {record.get('result_class')}"] += 1
            continue
        served = verbatim_words((EXPORT / page['text_file']).read_text(encoding='utf-8'))
        other = verbatim_words(store.reading_text(key))
        ratio, spans = differences(served, other)
        outcome['flagged' if ratio < FLAG_BELOW else 'agree'] += 1
        rows.append({'file': page['file'], 'pdf_page': page['pdf_page'], 'work': page['work'], 'ratio': ratio,
                     'served_words': len(served), 'other_words': len(other), 'differences': spans})
    rows.sort(key=lambda row: row['ratio'])
    REPORT.write_text(json.dumps({'about': PURPOSE, 'flag_below': FLAG_BELOW, 'outcome': dict(outcome), 'pages': rows},
                                 ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{dict(outcome)}; written to {REPORT}')
    for row in rows:
        if row['ratio'] < FLAG_BELOW:
            print(f"{row['ratio']:.3f}  {row['work']} p.{row['pdf_page']}  {row['differences'][:2]}")
    return dict(outcome)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    sample_parser = commands.add_parser('sample')
    sample_parser.add_argument('--pages', type=int, default=100)
    sample_parser.set_defaults(run=sample)
    read_parser = commands.add_parser('read')
    read_parser.add_argument('--limit', type=int, default=0)
    read_parser.add_argument('--workers', type=int, default=1)
    read_parser.add_argument('--key-cap', type=float, default=second_reader.KEY_CAP_USD)
    read_parser.add_argument('--dry-run', action='store_true')
    read_parser.set_defaults(run=read)
    compare_parser = commands.add_parser('compare')
    compare_parser.set_defaults(run=compare)
    return parser


def main() -> None:
    from backend.conversion.store import pipeline_db

    sys.stdout.reconfigure(encoding='utf-8')
    vision_batches.quiet_sdk_logs()
    args = build_parser().parse_args()
    with pipeline_db.run(['free'], pipeline_db.command_line('backend.conversion.measurement.blind_spot')):
        args.run(args)


if __name__ == '__main__':
    main()
