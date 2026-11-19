"""The judge in a Claude Code session (the operator's N1.a, N2.a and N3.a, 19 Nov): the same request the check flow would send to
the API, answered by a Sonnet agent of the session, and stored so the check report reads it as it reads a batch's.

Once the API credit ends, a work read whole overnight is still judged. The request is the API judge's own (`page_judge.entry_for`:
the image the reader saw, the formulas rendered, the transcription as the judge sees it, the active judge's instructions and
answer schema); only the door differs, so the record says `mode: session` and keeps the request's key beside its own.

    python -m backend.conversion.judge.session_judge calibrate             # judge/1's calibration set, for the gate (N1.a)
    python -m backend.conversion.judge.session_judge prepare --cells LIC-DIRECT-OPUS --chunk 1 --chunks 6
    python -m backend.conversion.judge.session_judge store --knowledge-base licensed
    python -m backend.conversion.judge.session_judge score                 # the calibration's gate
    python -m backend.conversion.judge.session_judge gate --cells LIC-DIRECT-OPUS   # each work's bad share so far (N2.a)

A chunk is a tenth of each work's judge requests, suspects first and then a seeded random order, so every chunk is a sample of
its own and a work's bad share can be read after each one. Prints ids and counts, never page text.
"""

import argparse
import hashlib
import json
import math
import random
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

from backend.conversion.checks import check_flow, check_run
from backend.conversion.judge import page_judge
from backend.conversion.reading import reader_requests, reading_cells, vision_batches
from backend.conversion.store.reading_store import open_store

MODE = 'session'
ADAPTER = 'claude-code-session'
PROVIDER = 'anthropic, in a Claude Code session (a Sonnet agent)'
CALIBRATION = 'calibration'  # the folder of judge/1's calibration set, judged once on the free mirror
# N1.a set the API judge's own gate (judge/1, 30 Oct: 48 of 49 planted errors caught, 0 of 8 clean readings flagged). The session's
# judge caught 46 and flagged none; on a real scanned work it agreed with the API judge on 58 of 60 pages, the two others being the
# API judge's false alarms. The operator's C1.a (19 Nov): it serves at the measured level, at least 46 caught and none flagged, and
# its first work is compared with the API judge's verdicts where they exist (`again`, `compare`).
CAUGHT_AT_LEAST = 46
CLEAN_FLAGGED_AT_MOST = 0


def session_root(knowledge_base: str) -> Path:
    """Where the session's judge folders lie, beside the direct reader's page list."""
    return reading_cells.DIRECT_PAGES[knowledge_base].parent / 'judge_session'


def session_key(entry: dict, again: int = 0) -> str:
    """The key of the session's answer to one request: the request's own key and the door, so the API's answer to the same
    request, should one ever be bought, never collides with it. `again` asks a request the API judge answered once more, to
    compare the two judges on the same pages; such an answer never counts."""
    spec = {'mode': MODE, 'request': entry['reading_key'], **({'again': again} if again else {})}
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def calibration_plan() -> dict:
    """The active judge's calibration set on the free mirror, as `mini_pilot judge-plan` wrote it."""
    from backend.conversion.measurement import mini_pilot

    version = page_judge.active_version()
    name = mini_pilot._plan_name(check_run.JUDGE_MODEL, None if version == page_judge.FIRST_VERSION else version)
    return json.loads(open_store('free').path('reports', name).read_text(encoding='utf-8'))


def chunked(plan: dict, chunks: int) -> dict[str, list[list[dict]]]:
    """Each work's judge requests in `chunks` slices: the suspects stage 2 found first, then the rest in an order seeded by the
    work, so every slice is a random sample of the work and the first ones carry the suspects (N2.a)."""
    suspicious = set(plan.get('suspicious') or [])
    by_work: dict[str, list[dict]] = defaultdict(list)
    for entry in plan['entries']:
        by_work[entry['work']].append(entry)
    out = {}
    for work, entries in sorted(by_work.items()):
        first = sorted((entry for entry in entries if entry['target_key'] in suspicious), key=lambda entry: entry['pdf_page'])
        rest = sorted((entry for entry in entries if entry['target_key'] not in suspicious), key=lambda entry: entry['pdf_page'])
        random.Random(f'{work}:chunks').shuffle(rest)
        ordered = first + rest
        size = math.ceil(len(ordered) / chunks) if ordered else 0
        out[work] = [ordered[index * size:(index + 1) * size] for index in range(chunks)]
    return out


ENTRIES = '_entries'  # the requests themselves, beside the agent's folders, never in them


def folder_name(entry: dict, calibration: bool = False) -> str:
    """A page's folder by its work and page; a calibration request's by its key alone, so neither the name nor the order says
    which copies carry a planted error (judge/1's plan lists the clean readings first)."""
    return f'cal_{session_key(entry)[:10]}' if calibration else f"{entry['work']}__p{entry['pdf_page']:04d}"


def write_folder(root: Path, entry: dict, store, calibration: bool = False, again: int = 0) -> Path | None:
    """One request as files for the agent: the page, the rendered formulas, the transcription as the judge sees it. The entry
    itself lies in `_entries/`, out of the agent's folder: for a calibration it names the planted error and its block. None
    where it was answered already or waits in a folder."""
    key = session_key(entry, again)
    if store.reading(key) is not None:
        return None
    name = folder_name(entry, calibration)
    kept = root / ENTRIES / f'{name}.json'
    if kept.exists():
        return None
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'page.png').write_bytes(store.get_input(entry['image_sha256'], '.png'))
    for number, sha in enumerate(entry['sheet_sha256s'], start=1):
        (folder / f'formulas_{number:02d}.png').write_bytes(store.get_input(sha, '.png'))
    (folder / 'transcription.txt').write_bytes(store.get_input(entry['view_sha256'], '.txt'))
    session_entry = {**entry, 'request_key': entry['reading_key'], 'reading_key': key, 'custom_id': reader_requests.custom_id(key),
                     'mode': MODE, 'replicate': 1 if calibration or again else entry.get('replicate', 0)}  # 1: never counts
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_text(json.dumps(session_entry, indent=1) + '\n', encoding='utf-8')
    return folder


def write_instructions(root: Path, version: str) -> None:
    """The judge's instructions and its answer's schema, once per folder of requests."""
    root.mkdir(parents=True, exist_ok=True)
    (root / 'judge_instructions.md').write_text(
        page_judge.system_prompt(version) + '\n\nAnswer with one JSON object only, matching `verdict_schema.json` beside this file, '
        'written to `verdict.json` in the page\'s folder.\n', encoding='utf-8')
    (root / 'verdict_schema.json').write_text(json.dumps(page_judge.schema_of(version), indent=1) + '\n', encoding='utf-8')


def stopped_works(root: Path) -> set[str]:
    gate = root / 'gate.json'
    return set(json.loads(gate.read_text(encoding='utf-8')).get('stopped', [])) if gate.exists() else set()


def root_gate(knowledge_base: str) -> dict:
    """The last gate's counts per work and the works it stopped; empty before the first gate."""
    path = session_root(knowledge_base) / 'gate.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def prepare(args) -> list[str]:
    """The folders of one chunk of the check plan's requests not answered yet; a work the gate stopped gets none. Nothing is
    bought."""
    cells = check_run._cells(args)
    store = check_run.store_of(cells)
    plan = json.loads(store.path('reports', check_run._plan_name(cells)).read_text(encoding='utf-8'))
    knowledge_base = 'licensed' if store.root == open_store('licensed').root else 'free'
    root = session_root(knowledge_base)
    write_instructions(root, page_judge.active_version())
    judged = check_run.verdicts_by_target(store)
    turned_away = filtered_pages(knowledge_base)
    stopped, made, refused = stopped_works(root), [], Counter()
    for work, slices in chunked(plan, args.chunks).items():
        if work in stopped:
            print(f'{work}: stopped by the gate, no chunk prepared')
            continue
        for entry in slices[args.chunk - 1]:
            if entry['target_key'] in judged:
                continue
            if (entry['file'], entry['pdf_page']) in turned_away or not reading_cells.may_send(entry['file']):
                refused['a filter or a reader turned the page away, or the file is held back'] += 1
                continue
            folder = write_folder(root, entry, store)
            if folder is not None:
                made.append(str(folder))
    print(f"chunk {args.chunk} of {args.chunks}: {len(made)} folders in {root}{f', never judged here: {dict(refused)}' if refused else ''}")
    return made


COMPARE = 'compare'  # the folder of requests the API judge answered, asked of the session once more


def api_judged(store) -> dict[str, dict]:
    """The counted verdicts the API gave, by the reading they judged: what the session's answers are compared with."""
    return {target: record for target, record in check_run.verdicts_by_target(store).items() if record.get('mode') != MODE}


def again(args) -> list[str]:
    """The requests of a check plan the API judge answered, for one work, asked of the session once more (the operator, 19 Nov:
    a test of the session's judge on a real work); its answers never count, `compare` sets them beside the API's. With
    `issues_only`, only the pages the API judge sent to an issue (R2.a: a second judge before a person's review)."""
    cells = check_run._cells(args)
    store = check_run.store_of(cells)
    plan = json.loads(store.path('reports', check_run._plan_name(cells)).read_text(encoding='utf-8'))
    knowledge_base = 'licensed' if store.root == open_store('licensed').root else 'free'
    root = session_root(knowledge_base) / COMPARE
    write_instructions(root, page_judge.active_version())
    judged, turned_away, made = api_judged(store), filtered_pages(knowledge_base), []
    for entry in plan['entries']:
        if entry['work'] != args.work or entry['target_key'] not in judged:
            continue
        if (entry['file'], entry['pdf_page']) in turned_away or not reading_cells.may_send(entry['file']):
            continue
        api = check_run.voided(store, judged[entry['target_key']]['verdict'], entry['target_key'])
        if getattr(args, 'issues_only', False) and api['outcome'] == 'ok':
            continue
        folder = write_folder(root, entry, store, again=1)
        if folder is not None:
            made.append(str(folder))
    print(f'{args.work}: {len(made)} folders of requests the API judge answered, in {root}')
    return made


def compare(args) -> dict:
    """The session's second answers beside the API's on the same requests: whether each sends the page to an issue, and the
    blocks each names. Ids and counts only."""
    cells = check_run._cells(args)
    store = check_run.store_of(cells)
    plan = json.loads(store.path('reports', check_run._plan_name(cells)).read_text(encoding='utf-8'))
    judged, pages, counts = api_judged(store), [], Counter()
    for entry in plan['entries']:
        api = judged.get(entry['target_key'])
        session = store.reading(session_key(entry, 1))
        if entry['work'] != args.work or api is None or session is None or session.get('verdict') is None:
            continue
        mine = check_run.voided(store, session['verdict'], entry['target_key'])
        theirs = check_run.voided(store, api['verdict'], entry['target_key'])
        pair = (theirs['outcome'], mine['outcome'])
        counts[f'api {pair[0]}, session {pair[1]}'] += 1
        blocks = {name: sorted({finding.get('block') for finding in verdict['findings'] if not finding.get('void')})
                  for name, verdict in (('api', theirs), ('session', mine))}
        pages.append({'pdf_page': entry['pdf_page'], 'api': pair[0], 'session': pair[1], **{f'{name}_blocks': found
                                                                                             for name, found in blocks.items()}})
    agree = sum(1 for page in pages if page['api'] == page['session'])
    result = {'work': args.work, 'pages': len(pages), 'agree': agree, 'counts': dict(counts), 'by_page': pages}
    path = store.write_report(f"judge_compare_session_{'_'.join(cells)}.json", result)
    print(f"{args.work}: {len(pages)} pages, the judges agree on {agree}; {dict(counts)}; {path.name}")
    return result


def filtered_pages(knowledge_base: str) -> set[tuple[str, int]]:
    """The pages a provider's filter blocked or a reader refused in any attempt, from the export: the session never sees them,
    to judge no more than to read (280.a: never the same model by another door), whoever's reading stands there now."""
    from backend.conversion.reading import direct_reader
    from backend.conversion.store import reading_export

    index = reading_export.BASES[knowledge_base].export / 'index.json'
    rows = json.loads(index.read_text(encoding='utf-8'))['pages'] if index.exists() else []
    return {(row['file'], row['pdf_page']) for row in rows if direct_reader.touched_by_a_filter(row)}


def calibrate(args) -> list[str]:
    """The folders of the active judge's calibration set (N1.a), on the free mirror."""
    plan, store, root = calibration_plan(), open_store('free'), session_root('free') / CALIBRATION
    write_instructions(root, page_judge.active_version())
    made = [str(folder) for entry in plan['entries'] if (folder := write_folder(root, entry, store, calibration=True)) is not None]
    print(f"calibration: {len(made)} folders of {len(plan['entries'])} in {root}")
    return made


def record_for(entry: dict, text: str) -> dict:
    """The stored record of one answer, in the shape a batch's judge record has; it costs no API money."""
    result_class, verdict = page_judge.check_answer(entry, text, 'end_turn')
    record = {name: entry.get(name) for name in (*vision_batches.RECORD_FIELDS, *page_judge.ENTRY_FIELDS)}
    record.update(kind='judge', request_key=entry['request_key'], adapter=ADAPTER, provider=PROVIDER,
                  stored_at=vision_batches.now(), sdk='claude-code session', result_type='succeeded', error_type=None,
                  error_message=None, stop_reason='end_turn', usage={}, cost_usd=0.0, result_class=result_class, verdict=verdict,
                  text_sha256=reader_requests.sha256_text(text), text_chars=len(text))
    return record


def store(args) -> Counter:
    """Store every folder the agent wrote `verdict.json` in, and remove it with its entry; a folder not answered yet stays."""
    outcome = Counter()
    root = session_root(args.knowledge_base)
    for entry_file in sorted(root.rglob(f'{ENTRIES}/*.json')):
        folder = entry_file.parent.parent / entry_file.stem
        written = folder / 'verdict.json'
        if not written.exists():
            outcome['not answered yet'] += 1
            continue
        entry = json.loads(entry_file.read_text(encoding='utf-8'))
        target = open_store(entry['mirror'])
        if target.reading(entry['reading_key']) is None:
            text = written.read_text(encoding='utf-8')
            record = record_for(entry, text)
            target.save_reading(entry['reading_key'], record, text)
            outcome[record['result_class']] += 1
        else:
            outcome['already stored'] += 1
        shutil.rmtree(folder)
        entry_file.unlink()
    print(f'{args.knowledge_base}: {dict(outcome)}')
    return outcome


def calibration_gate(measures: dict, entries: int) -> dict:
    """Whether the session's judge holds the API judge's gate (N1.a): every request answered, at least 48 planted errors sent
    to an issue, no clean reading flagged."""
    caught = sum(row['to_issue'] for row in measures['groups'].values())
    planted = sum(row['n'] for row in measures['groups'].values())
    passed = (measures['answered'] == entries and caught >= CAUGHT_AT_LEAST
              and measures['clean']['issue'] <= CLEAN_FLAGGED_AT_MOST)
    return {'caught': caught, 'planted': planted, 'clean_flagged': measures['clean']['issue'], 'clean': measures['clean']['n'],
            'answered': measures['answered'], 'entries': entries, 'passed': passed}


def score(args) -> dict:
    """The calibration's measures and gate, written beside the API judge's (`judge_score_session_<model>.json`)."""
    from backend.conversion.measurement import mini_pilot

    plan, store = calibration_plan(), open_store('free')
    records = {entry['reading_key']: store.reading(session_key(entry)) for entry in plan['entries']}
    measures = mini_pilot.judge_measures(plan, {key: record for key, record in records.items() if record is not None})
    report = {**measures, 'gate': calibration_gate(measures, len(plan['entries'])), 'mode': MODE}
    path = store.write_report(f"judge_score_session_{plan['model']}.json", report)
    gate = report['gate']
    print(f"session judge: {gate['answered']} of {gate['entries']} answered; caught {gate['caught']} of {gate['planted']} planted, "
          f"flagged {gate['clean_flagged']} of {gate['clean']} clean: {'PASSED' if gate['passed'] else 'NOT PASSED'}; {path.name}")
    return report


def gate(args) -> dict:
    """Each work's judged requests so far and how many came back bad; a work above the check flow's stop share is stopped, so no
    further chunk of it is prepared and a person looks first (N2.a)."""
    cells = check_run._cells(args)
    target = check_run.store_of(cells)
    plan = json.loads(target.path('reports', check_run._plan_name(cells)).read_text(encoding='utf-8'))
    policy = check_flow.Policy(**plan['policy'])
    share = policy.stop_share or policy.stop_above / policy.sample_per_work  # 6 of 40 and 3 of 20 alike: 15 % (74.a)
    judged = check_run.verdicts_by_target(target)
    counts: dict[str, Counter] = defaultdict(Counter)
    for entry in plan['entries']:
        record = judged.get(entry['target_key'])
        if record is not None:
            verdict = check_run.voided(target, record['verdict'], entry['target_key'])
            counts[entry['work']]['judged'] += 1
            counts[entry['work']]['bad'] += verdict['outcome'] != 'ok'
    knowledge_base = 'licensed' if target.root == open_store('licensed').root else 'free'
    root = session_root(knowledge_base)
    stopped = stopped_works(root)
    for work, count in sorted(counts.items()):
        over = count['judged'] and count['bad'] / count['judged'] > share
        if over:
            stopped.add(work)
        print(f"{work}: judged {count['judged']}, bad {count['bad']} ({count['bad'] / count['judged']:.0%}), "
              f"gate {share:.0%}: {'STOPPED' if over else 'passes'}")
    root.mkdir(parents=True, exist_ok=True)
    result = {'stop_share': share, 'works': {work: dict(count) for work, count in counts.items()}, 'stopped': sorted(stopped)}
    (root / 'gate.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    prepared = commands.add_parser('prepare', help="one chunk of a check plan's requests, as folders")
    prepared.add_argument('--cells', required=True)
    prepared.add_argument('--chunk', type=int, required=True)
    prepared.add_argument('--chunks', type=int, default=6)
    commands.add_parser('calibrate', help="the active judge's calibration set, as folders")
    stored = commands.add_parser('store', help='store the answered folders')
    stored.add_argument('--knowledge-base', choices=('free', 'licensed'), required=True)
    commands.add_parser('score', help="the calibration's measures and gate")
    gated = commands.add_parser('gate', help="each work's bad share so far")
    gated.add_argument('--cells', required=True)
    for name, said in (('again', "one work's requests the API judge answered, asked of the session once more"),
                       ('compare', "the session's second answers beside the API judge's")):
        command = commands.add_parser(name, help=said)
        command.add_argument('--cells', required=True)
        command.add_argument('--work', required=True, help="the work's key, its file's stem")
        if name == 'again':
            command.add_argument('--issues-only', action='store_true', help='only the pages the API judge sent to an issue')
    return parser


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    args = build_parser().parse_args(argv)
    {'prepare': prepare, 'calibrate': calibrate, 'store': store, 'score': score, 'gate': gate, 'again': again,
     'compare': compare}[args.command](args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
