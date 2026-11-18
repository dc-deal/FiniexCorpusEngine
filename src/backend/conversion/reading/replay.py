"""One page's whole trace, and its repair by a new reading: the self-healing demo (decisions 54.a, 69.a).

    python -m backend.conversion.reading.replay show --work openstax-accounting --page 19                # the trace; spends nothing
    python -m backend.conversion.reading.replay reread --work openstax-accounting --page 19 --cap 95 [--dry-run]
    python -m backend.conversion.reading.replay judge --work openstax-finance-2e --page 5 --version judge/1 --fresh --cap 200

`judge` judges the reading that stands with a chosen version of the judge's instructions (decision 147.a), live over the
standard API: the old judge again where it erred, a prototype beside it. It changes nothing the pipeline serves.

`show` gives what the export, the pipeline database and the integrity scan know of the page: its route and state, why it was
judged and what the judge found, every attempt with its class, and every choice made for it.

`reread` reads the page again as a new attempt of the default reader, over the standard API rather than a batch, so the demo
waits seconds, not hours. The new reading is checked like any other: stage 1, then stage 2 against the PDF's text layer, then
the judge, also over the standard API. If the judge finds it ok, it is chosen in the pipeline database; otherwise the reading
that stood before keeps standing. Its check is written as a one-page report of the replay cell, which the export reads beside
the cell's own, and the export is written again, so a tampered or deleted reading file is replaced by the new reading's text.
Nothing is overwritten in the store: the earlier reading stays as the trace, and each choice is a row of its own.
"""

import argparse
import json
import sys
from pathlib import Path

from backend.conversion.checks import check_flow, check_run, integrity, page_checks
from backend.conversion.contract.page_contract import Expected, parse
from backend.conversion.judge import page_judge
from backend.conversion.reading import page_render, reading_cells, vision_batches
from backend.conversion.store import pipeline_db, reading_export
from backend.conversion.store.reading_store import open_store


def row_of(base: reading_export.KnowledgeBase, work: str, pdf_page: int) -> dict:
    rows = json.loads((base.export / 'index.json').read_text(encoding='utf-8'))['pages']
    found = next((row for row in rows if row['work'] == work and row['pdf_page'] == pdf_page), None)
    if found is None:
        sys.exit(f'{work} has no page {pdf_page} in the {base.name} export')
    return found


def show(base: reading_export.KnowledgeBase, work: str, pdf_page: int) -> dict:
    """What is known of one page: its row in the export, its choices, and whether its reading file is still what was checked."""
    row = row_of(base, work, pdf_page)
    findings = integrity.scan(base.export)
    broken = [kind for kind in ('tampered', 'missing_files') if any(place['work'] == work and place['pdf_page'] == pdf_page
                                                                     for place in findings[kind])]
    return {'row': row, 'choices': pipeline_db.history(base.name, row['file'], pdf_page), 'integrity': broken or ['whole']}


def page_of(base: reading_export.KnowledgeBase, work: str, pdf_page: int) -> dict:
    """The page as its default cell lists it: file, work card, the expected length of a reading."""
    for name in base.cells():
        for page in reading_cells.pages_for(reading_cells.known_cells()[name]):
            if page['work'] == work and page['pdf_page'] == pdf_page:
                return page
    sys.exit(f'{work} p{pdf_page} is in none of the {base.name} cells')


def list_replayed(base: reading_export.KnowledgeBase, page: dict) -> reading_cells.Cell:
    """Add the page to its knowledge base's replay page list, and return the replay cell that now holds it."""
    path = reading_cells.REPLAY_PAGES[base.name]
    listed = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'work_cards': {}, 'pages': []}
    if not any(entry['file'] == page['file'] and entry['pdf_page'] == page['pdf_page'] for entry in listed['pages']):
        listed['pages'].append({key: page[key] for key in ('file', 'pdf_page', 'work', 'gold', 'class_note', 'expected_output_tokens')
                                if key in page})
    listed['work_cards'][page['work']] = page['work_card']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(listed, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    return next(cell for cell in reading_cells.replay_cells().values() if Path(cell.page_source) == path)


def next_attempt(store, cells: list[str], page: dict) -> int:
    """One past every attempt the page has had in these cells, so the replay's key is new."""
    tried = [record.get('attempt', 0) for record in vision_batches.readings_of(cells, store)
             if record['file'] == page['file'] and record['pdf_page'] == page['pdf_page']]
    return max(tried, default=-1) + 1


def ask(entry: dict) -> tuple[dict, str | None]:
    """One request over the standard API, recorded and stored like a batch result; the record keeps Anthropic's request id."""
    from backend.providers import anthropic_client

    message = anthropic_client.client().messages.create(**vision_batches.params_for(entry))
    record, text = vision_batches.record_for(entry, 'succeeded', message, batch=False)
    record['request_id'] = getattr(message, '_request_id', None)
    vision_batches.store_result(entry, record, text)
    return record, text


def write_check(store, cell: str, row: dict) -> None:
    """The replay cell's report: one row per replayed reading, a later replay of the same reading replacing its row."""
    path = store.path('reports', f'check_report_{cell}.json')
    report = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'cells': [cell], 'pages': []}
    report['pages'] = [kept for kept in report['pages'] if kept['key'] != row['key']] + [row]
    store.write_report(path.name, report)


def review_findings(base: reading_export.KnowledgeBase, file: str, pdf_page: int, reading_key: str) -> list[dict]:
    """The rejects that name a block of the standing reading: what a review found wrong on it, for the re-read's hint."""
    return [verdict for verdict in pipeline_db.human_verdicts(base.name).get((file, pdf_page), [])
            if verdict['verdict'] == 'reject' and verdict['reading_key'] == reading_key and verdict.get('note')]


def reread(base: reading_export.KnowledgeBase, work: str, pdf_page: int, cap: float, dry_run: bool = False, run_id: int | None = None,
           asker=ask, over_a_person: str | None = None, review_hint: bool = False, export: bool = True) -> dict:
    """Read one page again, check it, judge it, choose it if it is ok, and write the export again. A page a person checked is
    refused unless `over_a_person` gives the reason, or a person reset the page first (decision 191.a).

    With `review_hint` the reader is told what a review's rejects found wrong on the standing reading (M2.c, 18 Nov): the
    judge alone missed those errors, so whoever runs it checks the new reading against the review's correction before
    trusting the choice. Without `export` the export is left to one run after several re-reads (a licensed one takes minutes)."""
    store = open_store(base.name)
    page = page_of(base, work, pdf_page)
    refused = pipeline_db.refused_over_a_person(base.name, page['file'], pdf_page, over_a_person)
    if refused:
        raise SystemExit(refused)
    before = row_of(base, work, pdf_page)
    hint = None
    if review_hint:
        findings = review_findings(base, page['file'], pdf_page, before['reading_key'])
        if not findings:
            raise SystemExit(f'no reject with a note on the standing reading of p. {pdf_page}: nothing to tell the reader')
        hint = vision_batches.review_hint(findings)
    cell = list_replayed(base, page)
    attempt = next_attempt(store, [*base.cells(), cell.name], page)
    mirror, pdf = vision_batches.Documents().page(page['file'], pdf_page)
    entry = vision_batches.reading_entry(cell, {**page, 'id': f"{work}:p{pdf_page:04d}"}, page_render.render(pdf, cell.resolution),
                                         mirror, store, mode='standard', attempt=attempt, hint=hint)
    estimate = entry['estimate_usd'] * 2  # the reading, and about as much again for the judge, who sees the page and the reading
    print(f'{base.name} {work} p{pdf_page}: attempt {attempt}, estimate {estimate:.4f} USD; standing now {before["reading_key"][:12]}'
          f' ({before["route"]})')
    if dry_run:
        return {'estimate_usd': estimate, 'attempt': attempt}
    if asker is ask:  # a real request: the spend guard first, as for every batch
        from backend.providers import anthropic_client

        vision_batches.guard(vision_batches.spend_status(anthropic_client.client()), estimate, cap)
    record, text = asker(entry)
    result = {'reading_key': entry['reading_key'], 'class': record['result_class'], 'cost_usd': record['cost_usd'], 'verdict': None,
              'suspicious': None}
    verdict, check = None, {'suspicious': False, 'unverifiable': []}
    if record['result_class'] == 'ok':
        parsed = parse(text, entry['form'], Expected(work, pdf_page, tuple(entry['image_size'])))
        check = page_checks.check_page(parsed, pdf, page_checks.render_formulas([parsed])).as_dict()
        judge_entry = {**page_judge.entry_for(record, parsed, check_run.JUDGE_MODEL), 'mode': 'standard'}
        judged, _ = asker(judge_entry)
        verdict = judged.get('verdict')
        result.update(cost_usd=result['cost_usd'] + judged['cost_usd'], verdict=verdict, suspicious=check['suspicious'])
    state, reasons = check_flow.state_of(record['result_class'], verdict)
    write_check(store, cell.name, {'key': entry['reading_key'], 'work': work, 'state': state, 'reasons': reasons, 'in_sample': False,
                                   'suspicious': bool(check['suspicious']), 'unverifiable': bool(check['unverifiable']),
                                   'replayed': True})
    if state == 'ok':
        pipeline_db.choose(base.name, page['file'], pdf_page, entry['reading_key'], why='replay --reread: judged ok', run_id=run_id)
    result.update(state=state, reasons=reasons, chosen=state == 'ok', reading_before=before['reading_key'])
    if export:
        reading_export.export(base, store)
    print(f"{work} p{pdf_page}: class {record['result_class']}, stage 2 {'suspicious' if check['suspicious'] else 'clean'}, "
          f"{state}{' ' + ', '.join(reasons) if reasons else ''}; "
          f"{('chosen' + (', and the export written again' if export else ', the export left for later')) if state == 'ok' else 'not chosen: the reading before keeps standing'}; "
          f"key {entry['reading_key'][:12]}; {result['cost_usd']:.4f} USD")
    return result


def judge(base: reading_export.KnowledgeBase, work: str, pdf_page: int, version: str, cap: float, fresh: bool = False,
          reading_key: str | None = None, dry_run: bool = False, asker=ask) -> dict:
    """Judge one page's reading with a chosen version of the judge's instructions, over the standard API (decision 147.a).

    For verification and for the demo: judge/1 can be run again where it erred and judge/2, a prototype, beside it. It changes
    nothing the pipeline serves: a prototype's verdict, or one asked again (`fresh`), is kept and shown, never counted. A verdict
    asked before with the same version is shown from the store and never bought twice, unless `fresh` asks once more."""
    store = open_store(base.name)
    row = row_of(base, work, pdf_page)
    key = reading_key or row['reading_key']
    record = store.reading(key)
    text = store.reading_text(key) if record else None
    if record is None or text is None:
        sys.exit(f'{work} p{pdf_page}: no stored reading {key[:12]}')
    parsed = parse(text, record['form'], Expected(work, pdf_page, tuple(record['image_size'])))
    again = 0
    entry = page_judge.entry_for(record, parsed, check_run.JUDGE_MODEL, version=version)
    while fresh and store.reading(entry['reading_key']) is not None:  # the next repetition no one has asked yet
        again += 1
        entry = page_judge.entry_for(record, parsed, check_run.JUDGE_MODEL, version=version, again=again)
    entry = {**entry, 'mode': 'standard'}
    estimate = entry['estimate_usd'] * 2  # the standard API costs twice the batch price the estimate is made for
    stored = store.reading(entry['reading_key'])
    print(f"{base.name} {work} p{pdf_page}: reading {key[:12]}, judge {version} ({page_judge.state_of(version)})"
          f"{f', asked again ({again})' if again else ''}; "
          f"{'answered before, shown from the store' if stored else f'estimate {estimate:.4f} USD'}")
    if dry_run and stored is None:
        return {'estimate_usd': estimate, 'again': again}
    if stored is None:
        if asker is ask:  # a real request: the spend guard first, as for every batch
            from backend.providers import anthropic_client

            vision_batches.guard(vision_batches.spend_status(anthropic_client.client()), estimate, cap)
        stored, _ = asker(entry)
    verdict = page_judge.with_void(stored.get('verdict'), {block.id: block.body for block in parsed.blocks},
                                   check_run.page_layer(record['file'], pdf_page))
    if verdict is None:
        print(f"no verdict: {stored.get('result_class')}")
        return {'verdict': None, 'record': stored}
    print(f"verdict {verdict['verdict']}, outcome {verdict['outcome']}"
          f"{' (the judge said ' + verdict['judge_outcome'] + ')' if verdict.get('judge_outcome') else ''}; {stored.get('cost_usd', 0):.4f} USD")
    for finding in verdict['findings']:
        print(f"  {finding.get('block')} {finding.get('kind')} {finding.get('severity')}{' VOID' if finding.get('void') else ''}: "
              f"{finding.get('evidence')}")
    if not stored.get('verdict', {}).get('findings'):
        print('  no findings')
    reading_export.export(base, store)  # the page's history in the views shows the new judgement
    return {'verdict': verdict, 'version': version, 'again': again, 'judge_key': entry['reading_key']}


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    vision_batches.quiet_sdk_logs()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('show', 'reread', 'judge'):
        command = commands.add_parser(name)
        command.add_argument('--knowledge-base', choices=sorted(reading_export.BASES), default='free')
        command.add_argument('--work', required=True)
        command.add_argument('--page', type=int, required=True, help='the PDF page')
        if name in ('reread', 'judge'):
            command.add_argument('--cap', type=float, required=True, help='the spend guard: cumulative USD by the ledger')
            command.add_argument('--dry-run', action='store_true')
        if name == 'reread':
            command.add_argument('--over-a-person', metavar='REASON',
                                 help='read again a page a person checked; the reason is recorded with the run (decision 191.a)')
            command.add_argument('--review-hint', action='store_true',
                                 help="tell the reader what a review's rejects found wrong on the standing reading (M2.c)")
            command.add_argument('--no-export', action='store_true', help='leave the export to one run after several re-reads')
        if name == 'judge':
            command.add_argument('--version', default=None, help='the judge version, as judge/1 or judge/2 (default: the active one)')
            command.add_argument('--fresh', action='store_true', help='ask once more even where this version answered before')
            command.add_argument('--reading', help='another reading of the page than the one that stands, by its key')
    args = parser.parse_args()
    base = reading_export.BASES[args.knowledge_base]
    if args.command == 'show':
        print(json.dumps(show(base, args.work, args.page), indent=1, ensure_ascii=False))
        return
    with pipeline_db.run([base.name], pipeline_db.command_line('backend.conversion.reading.replay')) as recorded:
        if args.command == 'judge':
            judge(base, args.work, args.page, args.version or page_judge.active_version(), args.cap, fresh=args.fresh,
                  reading_key=args.reading, dry_run=args.dry_run)
            return
        reread(base, args.work, args.page, args.cap, args.dry_run, run_id=recorded.run_id, over_a_person=args.over_a_person,
               review_hint=args.review_hint, export=not args.no_export)


if __name__ == '__main__':
    main()
