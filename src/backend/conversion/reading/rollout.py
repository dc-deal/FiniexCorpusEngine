"""The licensed structure pages in rounds, hardest first, each round a cell of its own (decisions 67.a, 68.a).

Which pages: those the free rules of `page_classes` flag, plus those Haiku found structure on among the rest (the cascade);
scans and pages a provider may not receive are left out. In what order: a difficulty score per page, from the classes on it and
the strength of its signals, the hardest first, works interleaved within a band so a round's judge sample spans several works.
In what size: rounds of 50, 150, 450 and 1,350 pages, so the first checks see few pages and the hardest, then two of 1,000, then
at most 2,000. The fifth round of 2,000 was split in two after four rounds had been read (decision 88.a), so its first half fits
under the spend cap before the old credit expires; `resplit` cuts the stored order again without planning anew.

Each round is written as a page source under the licensed mirror (never tracked) and becomes the cell `LIC-RNN`, read by the
batch runner and checked by `check_run` like any other cell. Every page keeps its way: the rules' signals and classes, Haiku's
classes, its difficulty and its round, in `rollout/plan.json` beside the rounds.

    python -m backend.conversion.reading.rollout plan             # writes the rounds; spends nothing
    python -m backend.conversion.reading.rollout resplit          # the stored order in today's round sizes; a sent round never changes
    python -m backend.conversion.reading.rollout append           # new works as rounds after the last; no round file changes
    python -m backend.conversion.reading.rollout append --files X # only the new work X (file name or stem); the others wait
    python -m backend.conversion.reading.rollout gates --round 1  # the four gates of a round, from its check report and manifests
"""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from backend.configuration import data_paths
from backend.conversion.checks import check_flow

FOLDER = data_paths.LICENSED_WORKING / 'rollout'
ROUND_SIZES = (50, 150, 450, 1350, 1000, 1000)  # the last two were one round of 2,000 until decision 88.a
ROUND_CAP = 2000
BAND = 5  # pages whose difficulty differs by less than this count as equally hard, and their works are interleaved
# One card for every licensed work until each has its own: what the free works' cards say, said generally.
GENERIC_CARD = ('A book in English. Read the page as printed: its columns in reading order, its printed page number and '
                'running head as page furniture, and every label (figure, table, equation number) exactly as printed.')


SIGNAL_CAP = 24  # signal strength orders pages within the same number of kinds, never across it


def difficulty(signals: dict, classes: set) -> int:
    """More kinds of structure first, then stronger signals: formula lines, drawn glyphs, code lines, ruled tables, figures."""
    strength = (min(signals.get('math_lines', 0), 20) + min(signals.get('drawn_glyphs', 0) // 10, 10)
                + min(signals.get('mono_run', 0), 20) // 2 + 3 * signals.get('ruled_tables', 0) + signals.get('figure_images', 0))
    return (SIGNAL_CAP + 1) * len(classes) + min(strength, SIGNAL_CAP)


def round_sizes(total: int) -> list[int]:
    sizes, left = [], total
    for size in ROUND_SIZES:
        if left <= 0:
            break
        sizes.append(min(size, left))
        left -= sizes[-1]
    while left > 0:
        sizes.append(min(ROUND_CAP, left))
        left -= sizes[-1]
    return sizes


def ordered(pages: list[dict]) -> list[dict]:
    """Hardest first; within a band of equal difficulty the works take turns, each in its own order of difficulty."""
    bands = defaultdict(lambda: defaultdict(list))
    for page in sorted(pages, key=lambda page: (-page['difficulty'], page['file'], page['pdf_page'])):
        bands[page['difficulty'] // BAND][page['file']].append(page)
    result = []
    for band in sorted(bands, reverse=True):
        queues = [bands[band][name] for name in sorted(bands[band])]
        while any(queues):
            for queue in queues:
                if queue:
                    result.append(queue.pop(0))
    return result


def select(rows: list[dict], haiku: dict, decide, scan_chars: int) -> list[dict]:
    """The pages the reader gets: the rules' or Haiku's structure, never a scan. `haiku`: (file, page) -> classes."""
    pages = []
    for row in rows:
        signals = row['signals']
        if signals['text_chars'] < scan_chars:
            continue
        rule_classes = sorted(decide(signals))
        haiku_classes = sorted(haiku.get((row['file'], row['pdf_page']), []))
        if not rule_classes and not haiku_classes:
            continue
        classes = set(rule_classes) | set(haiku_classes)
        pages.append({'file': row['file'], 'pdf_page': row['pdf_page'], 'work': Path(row['file']).stem, 'signals': signals,
                      'rule_classes': rule_classes, 'haiku_classes': haiku_classes, 'difficulty': difficulty(signals, classes)})
    return pages


def plan(args=None) -> dict:
    from backend.conversion.reading import page_classes, reading_cells
    from backend.conversion.store.reading_store import open_store

    store = open_store('licensed')
    rows = json.loads(store.path('reports', 'page_classes_licensed_rows.json').read_text(encoding='utf-8'))['rows']
    rows = [row for row in rows if reading_cells.may_send(row['file'])]  # the provenance hold, checked again at planning
    haiku = {(record['file'], record['pdf_page']): record['answer']['classes'] for record in store.readings()
             if record.get('kind') == 'classcheck' and record.get('answer')}
    pages = ordered(select(rows, haiku, page_classes.decide, page_classes.TEXT_LAYER_CHARS))
    return write_plan(pages, *cut_rounds(pages))


def cut_rounds(pages: list[dict]) -> tuple[list[dict], dict[int, str]]:
    """The rounds' summary and each round file's text, from the pages in rollout order; each page is marked with its round."""
    start, rounds, files = 0, [], {}
    for number, size in enumerate(round_sizes(len(pages)), start=1):
        chunk = pages[start:start + size]
        rounds.append(cut_round(number, chunk, files))
        start += size
    return rounds, files


def cut_round(number: int, chunk: list[dict], files: dict[int, str]) -> dict:
    """One round: its pages marked with it, its file's text added to `files`, its summary returned."""
    from backend.conversion.reading import reading_cells

    for page in chunk:
        page['round'] = number
    source = {'work_cards': {page['work']: GENERIC_CARD for page in chunk},
              'pages': [{'file': page['file'], 'pdf_page': page['pdf_page'], 'work': page['work'], 'gold': False,
                         'class_note': ', '.join(sorted(set(page['rule_classes']) | set(page['haiku_classes']))),
                         'expected_output_tokens': reading_cells.CORPUS_OUTPUT_TOKENS} for page in chunk]}
    files[number] = json.dumps(source, indent=1, ensure_ascii=False) + '\n'
    return {'round': number, 'pages': len(chunk), 'works': len({page['work'] for page in chunk}),  # works take turns
            'difficulty': [min(page['difficulty'] for page in chunk), max(page['difficulty'] for page in chunk)]}  # in a band


def appended(stored: dict, pages: list[dict]) -> tuple[list[dict], dict[int, str]]:
    """New works' pages, in rollout order, cut into rounds numbered after the stored plan's last, each at most ROUND_CAP pages.
    Nothing of the stored plan changes: its rounds were sent, and their cells' readings, reports and gates name their pages."""
    first = max((item['round'] for item in stored['rounds']), default=0) + 1
    rounds, files = [], {}
    for offset, start in enumerate(range(0, len(pages), ROUND_CAP)):
        rounds.append(cut_round(first + offset, pages[start:start + ROUND_CAP], files))
    return rounds, files


def append(args=None) -> dict:
    """Plan the works no round holds yet, as rounds after the last one, every existing round file unchanged: the intake of a new
    work (2026-11-08), the same cascade as `plan`. `plan` itself cuts every round anew and would rewrite the sent ones."""
    from backend.conversion.reading import page_classes, reading_cells
    from backend.conversion.store.reading_store import open_store

    store = open_store('licensed')
    rows = json.loads(store.path('reports', 'page_classes_licensed_rows.json').read_text(encoding='utf-8'))['rows']
    stored = json.loads((FOLDER / 'plan.json').read_text(encoding='utf-8'))
    planned = {page['file'] for page in stored['order']}
    chosen = page_classes.files_named(rows, getattr(args, 'files', None))  # only these new works, where named (22 Nov)
    if chosen is not None and chosen & planned:
        raise SystemExit(f'--files: {sorted(chosen & planned)} in a round already; nothing written')
    new_rows = [row for row in rows if reading_cells.may_send(row['file']) and row['file'] not in planned
                and (chosen is None or row['file'] in chosen)]
    checks = [record for record in store.readings() if record.get('kind') == 'classcheck']
    checked = {(record['file'], record['pdf_page']) for record in checks}
    haiku = {(record['file'], record['pdf_page']): record['answer']['classes'] for record in checks if record.get('answer')}
    unchecked = [row for row in new_rows if row['signals']['text_chars'] >= page_classes.TEXT_LAYER_CHARS
                 and not page_classes.decide(row['signals']) and (row['file'], row['pdf_page']) not in checked]
    if unchecked:  # Haiku finds structure the rules miss (14 % of the licensed text-only pages); without it those pages are lost
        raise SystemExit(f'{len(unchecked)} text-only pages of new works have no Haiku check yet: run '
                         '`page_classes sample-plan --plan cascade` and `sample-submit --plan cascade` first; nothing written')
    pages = ordered(select(new_rows, haiku, page_classes.decide, page_classes.TEXT_LAYER_CHARS))
    rounds, files = appended(stored, pages)
    taken = [number for number in files if (FOLDER / f'round_{number:02d}.json').exists()]
    if taken:
        raise SystemExit(f'round files {taken} exist already: nothing written')
    for number, text in files.items():
        (FOLDER / f'round_{number:02d}.json').write_text(text, encoding='utf-8')
    order = stored['order'] + pages
    result = {**stored, 'pages': len(order), 'by_rules': sum(1 for page in order if page['rule_classes']),
              'by_haiku_only': sum(1 for page in order if not page['rule_classes']), 'rounds': stored['rounds'] + rounds,
              'order': order}
    (FOLDER / 'plan.json').write_text(json.dumps(result, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"{len(pages)} pages of {len({page['work'] for page in pages})} new works in {len(rounds)} round(s):")
    for item in rounds:
        print(f"  round {item['round']:2}: {item['pages']:5} pages, {item['works']:2} works, difficulty {item['difficulty'][0]}-{item['difficulty'][1]}")
    return result


def write_plan(pages: list[dict], rounds: list[dict], files: dict[int, str]) -> dict:
    """Write the round files and `plan.json`; a round file no longer cut is removed."""
    FOLDER.mkdir(parents=True, exist_ok=True)
    for stale in FOLDER.glob('round_*.json'):
        if int(stale.stem[-2:]) not in files:
            stale.unlink()
    for number, text in files.items():
        (FOLDER / f'round_{number:02d}.json').write_text(text, encoding='utf-8')
    result = {'pages': len(pages), 'by_rules': sum(1 for page in pages if page['rule_classes']),
              'by_haiku_only': sum(1 for page in pages if not page['rule_classes']), 'rounds': rounds, 'order': pages}
    (FOLDER / 'plan.json').write_text(json.dumps(result, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"{result['pages']} pages ({result['by_rules']} by the rules, {result['by_haiku_only']} by Haiku alone) in {len(rounds)} rounds:")
    for item in rounds:
        print(f"  round {item['round']:2}: {item['pages']:5} pages, {item['works']:2} works, difficulty {item['difficulty'][0]}-{item['difficulty'][1]}")
    return result


def resplit(args=None) -> dict:
    """Cut the stored order into rounds again with today's sizes, without planning anew (decision 88.a split the fifth round).

    A round already sent to the reader must come out byte for byte as it was, or nothing is written: its cell's readings,
    reports and gates name its pages."""
    import re

    from backend.conversion.store import reading_store

    pages = json.loads((FOLDER / 'plan.json').read_text(encoding='utf-8'))['order']
    rounds, files = cut_rounds(pages)
    sent = sorted({int(match.group(1)) for manifest in reading_store.open_store('licensed').manifests()
                   for cell in manifest.get('cells', []) if (match := re.fullmatch(r'LIC-R(\d+)', cell))})
    changed = [number for number in sent
               if files.get(number) != (FOLDER / f'round_{number:02d}.json').read_text(encoding='utf-8')]
    if changed:
        raise SystemExit(f'rounds {changed} were sent and would change: nothing written')
    return write_plan(pages, rounds, files)


VALID_SHARE = 0.95
SAMPLE_BAD_SHARE = 3 / 20  # the check flow stops a work above 3 bad of 20; a small round's sample is judged by the same share
COST_FACTOR = 1.3


def issue_band(previous: float, pages: int) -> float:
    """How far a round's issue share may rise above the previous round's: one standard error of a share measured on this many
    pages, were the true share still the previous one (decision 109.a, the operator, 2026-11-08). Before, any rise failed the gate, so
    round 5a failed on 4.71 % after 4.47 %, well inside the noise of about 900 pages; its band would have been 0.68 points."""
    return math.sqrt(previous * (1 - previous) / pages) if pages else 0.0


def gates_of(report: dict, manifests: list[dict], previous_issue_share: float | None) -> dict:
    """The four gates of a round (decision 68.a), each passed or failed with its numbers. Pure, so a test needs no store."""
    states = [check_flow.current_state(row['state']) for row in report['pages']]
    unblocked = [state for state in states if state != 'blocked']
    valid = sum(1 for row in report['pages'] if row['state'] != 'blocked' and not any(reason.startswith('format:') for reason in row['reasons']))
    sample = [row for row in report['pages'] if row['in_sample']]
    sample_bad = sum(1 for row in sample if check_flow.current_state(row['state']) == 'issue')
    stopped = sorted(work for work, row in report['works'].items() if row['stopped'])
    estimate = sum(manifest['estimate_usd'] for manifest in manifests)
    cost = sum(manifest.get('cost_usd', 0.0) for manifest in manifests)
    issue_share = states.count('issue') / len(unblocked) if unblocked else 0.0
    allowed = None if previous_issue_share is None else previous_issue_share + issue_band(previous_issue_share, len(unblocked))
    gates = {
        'valid': {'passed': not unblocked or valid / len(unblocked) >= VALID_SHARE, 'valid': valid, 'of': len(unblocked)},
        'judge_sample': {'passed': not stopped and (not sample or sample_bad / len(sample) <= SAMPLE_BAD_SHARE),
                         'bad': sample_bad, 'of': len(sample), 'stopped_works': stopped},
        'cost': {'passed': cost <= COST_FACTOR * estimate, 'cost_usd': round(cost, 4), 'estimate_usd': round(estimate, 4)},
        'issue_share': {'passed': allowed is None or issue_share <= allowed,
                        'share': round(issue_share, 4), 'previous': previous_issue_share,
                        'allowed': None if allowed is None else round(allowed, 4)},
    }
    return {'passed': all(gate['passed'] for gate in gates.values()), 'gates': gates}


def gates(args) -> dict:
    from backend.conversion.store.reading_store import open_store

    store = open_store('licensed')
    cell = f'LIC-R{args.round:02d}'
    report = json.loads(store.path('reports', f'check_report_{cell}.json').read_text(encoding='utf-8'))
    manifests = [manifest for manifest in store.manifests() if manifest.get('cells') == [cell]]
    previous = store.path('reports', f'rollout_gates_r{args.round - 1:02d}.json')
    earlier = json.loads(previous.read_text(encoding='utf-8'))['gates'] if previous.exists() else None
    previous_share = (earlier.get('issue_share') or earlier['bin_share'])['share'] if earlier else None  # 'bin_share' before 97.a
    result = {'round': args.round, **gates_of(report, manifests, previous_share)}
    store.write_report(f'rollout_gates_r{args.round:02d}.json', result)
    for name, gate in result['gates'].items():
        print(f"  {'PASS' if gate['passed'] else 'FAIL'}  {name}: " + ', '.join(f'{key} {value}' for key, value in gate.items() if key != 'passed'))
    print(f"round {args.round}: {'all gates passed' if result['passed'] else 'a gate failed: the rollout stops until a person has looked'}")
    return result


def main() -> None:
    import argparse

    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('plan').set_defaults(run=plan)
    commands.add_parser('resplit').set_defaults(run=resplit)
    append_parser = commands.add_parser('append')
    append_parser.add_argument('--files', nargs='+', metavar='NAME',
                               help='plan only these new works, each by its file name or stem; default every new work')
    append_parser.set_defaults(run=append)
    gates_parser = commands.add_parser('gates')
    gates_parser.add_argument('--round', type=int, required=True)
    gates_parser.set_defaults(run=gates)
    args = parser.parse_args()
    from backend.conversion.store import pipeline_db

    with pipeline_db.run(['licensed'], pipeline_db.command_line('backend.conversion.reading.rollout')):
        args.run(args)


if __name__ == '__main__':
    main()
