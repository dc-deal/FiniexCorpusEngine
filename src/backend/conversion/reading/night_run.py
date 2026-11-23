"""A night's run in a Claude Code session (the operator's N3.a, 19 Nov): works the operator names, read whole by the session's
agents, judged by a Sonnet agent in chunks, and counted as it goes, so the morning says what was done and what it cost in the
plan's usage.

It holds no reading and no verdict itself: `direct_reader` prepares and stores the pages, `session_judge` the judge's requests,
`check_run` plans and reports the check. This module keeps the run's ledger (per batch: pages, the agents' tokens and minutes as
their task notification reports them) and the batches' folder lists, so a session that wakes after a rate limit knows where it
stands. Generalised from the first such run (a scanned work, 18 Nov night).

    python -m backend.conversion.reading.night_run start --knowledge-base licensed --run night01 --work FILE.pdf [--judge-share 0.6]
    python -m backend.conversion.reading.night_run start --knowledge-base licensed --run night02 --add-pages LIST.json
    python -m backend.conversion.reading.night_run batch --run night01 --number 3 --size 25     # prepare, write the folder list
    python -m backend.conversion.reading.night_run store --run night01 --number 3              # store it, remove its folders
    python -m backend.conversion.reading.night_run log --run night01 --number 3 --tokens 270000 --ms 812000 --pages 25
    python -m backend.conversion.reading.night_run log --run night01 --judge-chunk 1 --tokens 90000 --ms 300000 --pages 66
    python -m backend.conversion.reading.night_run status --run night01

Prints ids and counts, never page text.
"""

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from backend.conversion.reading import direct_reader, reading_cells
from backend.conversion.store.reading_store import open_store

JUDGE_SHARE = 0.6  # the operator's N2.a: a night's work is judged by 60 % of its pages
CHUNKS = 6  # in six chunks of a tenth of the work each


def runs_folder(knowledge_base: str) -> Path:
    return reading_cells.DIRECT_PAGES[knowledge_base].parent / 'night'


def ledger_path(knowledge_base: str, run: str) -> Path:
    return runs_folder(knowledge_base) / f'{run}.json'


def find_run(run: str) -> tuple[str, dict]:
    """The run's knowledge base and ledger, wherever it was started."""
    for base in ('licensed', 'free'):
        path = ledger_path(base, run)
        if path.exists():
            return base, json.loads(path.read_text(encoding='utf-8'))
    sys.exit(f'no night run {run!r}: start it first')


def save(knowledge_base: str, run: str, ledger: dict) -> None:
    path = ledger_path(knowledge_base, run)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=1) + '\n', encoding='utf-8')


def start(args) -> dict:
    """The works join the direct cell whole, or the pages a page list names do (27.a), with the share of their pages the judge
    sees, and the run's ledger begins; the run's works are the files it names either way."""
    add_pages = getattr(args, 'add_pages', None)
    works = sorted(set(args.work or []) | {file_name for file_name, _ in direct_reader.page_list(add_pages)})
    if not works:
        sys.exit('name the works to read whole (--work) or a page list (--add-pages)')
    direct_reader.pages(SimpleNamespace(knowledge_base=args.knowledge_base, add_work=args.work, add_pages=add_pages,
                                        judge_share=args.judge_share))
    ledger = {'about': "a night's run in the session (N3.a): per batch the pages it finished and the agents' tokens and time as "
                       'their task notification reports them; per judge chunk the same', 'run': args.run,
              'knowledge_base': args.knowledge_base, 'works': works, 'judge_share': args.judge_share, 'chunks': CHUNKS,
              'started_at': datetime.now(UTC).isoformat(), 'batches': {}, 'judge_chunks': {}}
    save(args.knowledge_base, args.run, ledger)
    print(f"night run {args.run}: {len(works)} works, judge share {args.judge_share:.0%} in {CHUNKS} chunks")
    return ledger


def prefixes(ledger: dict) -> tuple[str, ...]:
    return tuple(f'{Path(name).stem}__p' for name in ledger['works'])


def waiting_folders(knowledge_base: str, ledger: dict) -> list[Path]:
    """The run's prepared pages not stored yet."""
    root = direct_reader.session_folder(knowledge_base)
    return sorted(path for path in root.glob('*__p*') if path.is_dir() and path.name.startswith(prefixes(ledger)))


def listed_pages(knowledge_base: str) -> set[tuple[str, int]]:
    """The pages the direct cell lists now, by file and PDF page."""
    cell = reading_cells.known_cells().get(direct_reader.cell_name(knowledge_base))
    return {(page['file'], page['pdf_page']) for page in reading_cells.pages_for(cell)} if cell else set()


def folder_page(path: Path) -> tuple[str, int] | None:
    """A prepared folder's page, from its entry."""
    entry = path / 'entry.json'
    if not entry.exists():
        return None
    data = json.loads(entry.read_text(encoding='utf-8'))
    return data['file'], data['pdf_page']


def batch_file(knowledge_base: str, run: str, number: int) -> Path:
    return runs_folder(knowledge_base) / f'{run}_batches' / f'batch_{number:02d}.json'


def batch(args) -> list[str]:
    """Up to `size` pages of the run's works no batch holds yet, prepared where needed; their folder names are the batch."""
    base, ledger = find_run(args.run)
    folder = batch_file(base, args.run, args.number).parent
    taken = {name for path in folder.glob('batch_*.json') for name in json.loads(path.read_text(encoding='utf-8'))}
    listed = listed_pages(base)

    def free_folders() -> list[str]:  # prepared, not read, in no batch, and still in the cell's list (N5.a may have left it)
        return [path.name for path in waiting_folders(base, ledger) if path.name not in taken and not (path / 'reading.md').exists()
                and folder_page(path) in listed]

    free = free_folders()
    if len(free) < args.size:
        direct_reader.prepare(SimpleNamespace(knowledge_base=base, limit=args.size - len(free), page=None, work=ledger['works'],
                                              retry_malformed=False))
        free = free_folders()
    chosen = free[:args.size]
    folder.mkdir(parents=True, exist_ok=True)
    batch_file(base, args.run, args.number).write_text(json.dumps(chosen, indent=1) + '\n', encoding='utf-8')
    print(f"batch {args.number}: {len(chosen)} folders{f', {chosen[0]} .. {chosen[-1]}' if chosen else ''}")
    return chosen


def store(args) -> dict:
    """Every finished reading of the run is stored; only the named batch's folders are removed, since a running agent checks
    each page after writing it."""
    base, ledger = find_run(args.run)
    names = set(json.loads(batch_file(base, args.run, args.number).read_text(encoding='utf-8'))) if args.number else None
    done = [path for path in waiting_folders(base, ledger)  # read, or blocked by the filter: neither goes back to the pool
            if ((path / 'reading.md').exists() or (path / direct_reader.BLOCKED_FILE).exists()) and (names is None or path.name in names)]
    outcome = direct_reader.store(SimpleNamespace(knowledge_base=base))
    for path in done:
        shutil.rmtree(path)
    if names is not None:  # an agent the rate limit stopped leaves pages unread: they leave its batch, so the next one takes them
        batch_file(base, args.run, args.number).write_text(json.dumps(sorted(path.name for path in done), indent=1) + '\n',
                                                           encoding='utf-8')
    print(f'folders removed {len(done)}{f", {len(names) - len(done)} unread pages back in the pool" if names else ""}')
    return dict(outcome)


def log(args) -> dict:
    """One batch's or one judge chunk's measure into the ledger, as the agents' task notifications report them."""
    base, ledger = find_run(args.run)
    seconds = round(args.ms / 1000)
    row = {'agent_tokens': args.tokens, 'duration_s': seconds, 'pages': args.pages,
           'tokens_per_page': round(args.tokens / args.pages) if args.pages else None,
           'seconds_per_page': round(seconds / args.pages) if args.pages else None,
           'note': args.note, 'logged_at': datetime.now(UTC).isoformat()}
    if args.judge_chunk:
        ledger['judge_chunks'][str(args.judge_chunk)] = row
    else:
        ledger['batches'][str(args.number)] = row
    save(base, args.run, ledger)
    print(f"{'judge chunk ' + str(args.judge_chunk) if args.judge_chunk else 'batch ' + str(args.number)} logged: "
          f"{args.pages} pages, {args.tokens} tokens, {seconds} s")
    return row


def totals(rows: dict) -> dict:
    pages = sum(row['pages'] for row in rows.values())
    tokens = sum(row['agent_tokens'] for row in rows.values())
    seconds = sum(row['duration_s'] for row in rows.values())
    return {'parts': len(rows), 'pages': pages, 'agent_tokens': tokens, 'duration_s': seconds,
            'tokens_per_page': round(tokens / pages) if pages else None, 'seconds_per_page': round(seconds / pages) if pages else None}


def status(args) -> dict:
    """What the run has read, stored and judged so far, and what its ledger counts: the morning's report."""
    from backend.conversion.judge import session_judge

    base, ledger = find_run(args.run)
    works = {Path(name).stem for name in ledger['works']}
    stored = sum(1 for record in open_store(base).readings()
                 if record.get('kind', 'reading') == 'reading' and record.get('mode') == 'session' and record['work'] in works)
    gate = session_judge.root_gate(base)
    result = {'run': args.run, 'works': sorted(works), 'stored_readings': stored, 'waiting_folders': len(waiting_folders(base, ledger)),
              'reading': totals(ledger['batches']), 'judging': totals(ledger['judge_chunks']),
              'gate': {work: gate.get('works', {}).get(work) for work in sorted(works)},
              'stopped': sorted(works & set(gate.get('stopped', [])))}
    reading, judging = result['reading'], result['judging']
    print(f"{args.run}: {stored} readings stored, {result['waiting_folders']} folders waiting; reading {reading['parts']} batches, "
          f"{reading['pages']} pages, {reading['agent_tokens']:,} tokens, {reading['duration_s'] // 60} min; judging "
          f"{judging['parts']} of {ledger['chunks']} chunks, {judging['pages']} pages, {judging['agent_tokens']:,} tokens"
          f"{'; STOPPED: ' + ', '.join(result['stopped']) if result['stopped'] else ''}")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    started = commands.add_parser('start')
    started.add_argument('--knowledge-base', choices=('free', 'licensed'), required=True)
    started.add_argument('--run', required=True)
    started.add_argument('--work', action='append', metavar='FILE', help='a work the run reads whole (its structure pages)')
    started.add_argument('--add-pages', metavar='FILE', help='a page list {about, pages: [{file, pdf_page}]}: the run reads '
                                                            'those pages, and its works are the files it names (27.a)')
    started.add_argument('--judge-share', type=float, default=JUDGE_SHARE)
    for name in ('batch', 'store', 'log', 'status'):
        command = commands.add_parser(name)
        command.add_argument('--run', required=True)
        if name in ('batch', 'store', 'log'):
            command.add_argument('--number', type=int, required=name == 'batch')
        if name == 'batch':
            command.add_argument('--size', type=int, default=25)
        if name == 'log':
            command.add_argument('--judge-chunk', type=int)
            command.add_argument('--tokens', type=int, required=True)
            command.add_argument('--ms', type=int, required=True)
            command.add_argument('--pages', type=int, required=True)
            command.add_argument('--note')
    return parser


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    args = build_parser().parse_args(argv)
    {'start': start, 'batch': batch, 'store': store, 'log': log, 'status': status}[args.command](args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
