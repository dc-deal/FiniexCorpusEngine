"""The mini pilot's measurements: Markdown blocks against JSON, Haiku against Sonnet, and what the checks and the judge catch.

Free pages only, so the reports may show text. The gates were written before any reading existed (docs/phase_01_reader_format.md).
Every command is idempotent and writes its result before it prints it. Only `judge-submit` spends, through the guarded runner.

    python -m backend.conversion.measurement.mini_pilot score
    python -m backend.conversion.measurement.mini_pilot plant [--cell MP-SM]
    python -m backend.conversion.measurement.mini_pilot judge-plan --model claude-haiku-5-5 [--cell MP-SM] [--clean 8] [--planted 2]
    python -m backend.conversion.measurement.mini_pilot judge-submit --model claude-haiku-5-5 [--cap 5] [--dry-run]
    python -m backend.conversion.measurement.mini_pilot judge-score --model claude-haiku-5-5
    python -m backend.conversion.measurement.mini_pilot report
"""

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass
from statistics import median

import pymupdf

from backend.conversion.checks import page_checks
from backend.conversion.judge import page_judge, planted_errors
from backend.conversion.measurement import publisher_gold, reader_scoring
from backend.conversion.reading import reading_cells, vision_batches
from backend.conversion.contract.page_contract import Expected, ParsedPage, parse
from backend.conversion.judge.page_judge import Verdict
from backend.conversion.store.reading_store import open_store
from backend.providers import anthropic_client

CELLS = ('MP-HM', 'MP-HJ', 'MP-SM', 'MP-SJ', 'MP2-HM', 'MP2-SM')
TEXT_FINDINGS = {'words_missing', 'words_added', 'number_missing', 'number_added', 'word_order'}
IOU_CLASSES = ('paragraph', 'heading', 'formula', 'table', 'figure', 'code', 'caption')
CLEAN_PROSE = 0.985  # a reading counts as clean against gold from here on: the gold's own edition noise lies below this distance
SUMMARY = 'mini_pilot_summary.md'


@dataclass
class Reading:
    record: dict
    text: str | None
    page: ParsedPage
    check: page_checks.PageCheck | None = None
    score: reader_scoring.PageScore | None = None

    @property
    def key(self) -> str:
        return self.record['reading_key']


class Documents:
    def __init__(self):
        self._open = {}

    def page(self, file_name: str, pdf_page: int) -> pymupdf.Page:
        if file_name not in self._open:
            self._open[file_name] = pymupdf.open(reading_cells.source_of(file_name)[1])
        return self._open[file_name][pdf_page - 1]


def expected_of(record: dict) -> Expected:
    return Expected(record['work'], record['pdf_page'], tuple(record['image_size']))


def stored_readings(cells: tuple[str, ...] = CELLS) -> list[Reading]:
    store = open_store('free')
    rows = []
    for record in store.readings():
        if record.get('cell') not in cells or record.get('kind', 'reading') != 'reading':
            continue
        text = store.reading_text(record['reading_key'])
        page = parse(text, record['form'], expected_of(record)) if text else ParsedPage(record['form'], {}, [], ['no text'])
        rows.append(Reading(record, text, page))
    return sorted(rows, key=lambda row: (row.record['cell'], row.record['file'], row.record['pdf_page'], row.record.get('attempt', 0)))


def measure(readings: list[Reading]) -> dict:
    """Stage 2 on every valid reading and gold on every page that has it. A lost reading scores as lost, not as absent."""
    documents = Documents()
    rendered = page_checks.render_formulas([row.page for row in readings])
    for row in readings:
        if row.page.valid:
            row.check = page_checks.check_page(row.page, documents.page(row.record['file'], row.record['pdf_page']), rendered)
        gold = publisher_gold.load_gold(row.record['file'], row.record['pdf_page'])
        if gold is not None:
            row.score = reader_scoring.score_reading(row.page, gold, rendered)
    return rendered


def _rate(part: int, whole: int) -> str:
    return f'{part}/{whole} ({part / whole:.1%})' if whole else 'n/a'


def _per_page(values: list, digits: int = 0) -> str:
    return f'{sum(values) / len(values):.{digits}f}' if values else 'n/a'


def _gold_clean(row: Reading) -> bool:
    """Gold shows no error in this reading: every formula exact, every cell right, the words the same, the label right."""
    score = row.score
    if score is None or not row.page.valid:
        return False
    tables_ok = score.table is None or score.table['exact'] == score.table['cells']
    prose_ok = score.prose is None or score.prose['similarity'] >= CLEAN_PROSE
    return score.formula['exact'] == score.formula['gold'] and tables_ok and prose_ok and score.page_label['ok']


def cell_measures(rows: list[Reading]) -> dict:
    first = [row for row in rows if row.record.get('attempt', 0) == 0]
    # Today's validator on the stored text: the class in a record is what the validator said when it was collected.
    classes = Counter(('ok' if row.page.valid else 'malformed') if row.record['result_class'] in ('ok', 'malformed') else row.record['result_class'] for row in first)
    usage = [row.record.get('usage') or {} for row in first]
    scores = [row.score for row in first if row.score]
    summary = reader_scoring.summarize(scores) if scores else None
    checked = [row for row in first if row.check]
    gold_clean = [row for row in checked if _gold_clean(row)]
    iou = {}
    for name in IOU_CLASSES:
        values = [block.iou for row in checked for block in row.check.blocks if block.cls == name and block.iou is not None]
        iou[name] = {'n': len(values), 'median': round(median(values), 3) if values else None}
    return {'readings': len(first), 'classes': dict(classes), 'valid_first': classes['ok'], 'warnings': sum(len(row.page.warnings) for row in first),
            'usd_per_page': round(sum(row.record.get('cost_usd', 0.0) for row in first) / max(len(first), 1), 5),
            'input_per_page': round(sum((u.get('input_tokens') or 0) + (u.get('cache_read_input_tokens') or 0) + (u.get('cache_creation_input_tokens') or 0) for u in usage) / max(len(usage), 1)),
            'output_per_page': round(sum(u.get('output_tokens') or 0 for u in usage) / max(len(usage), 1)),
            'control_characters': sum(1 for row in first if any('control character' in error for error in row.page.errors)),
            'katex_failures': sum(1 for row in checked for finding in row.check.findings if finding.kind == 'katex'),
            'suspicious': sum(1 for row in checked if row.check.suspicious), 'checked': len(checked),
            'suspicious_on_gold_clean': sum(1 for row in gold_clean if row.check.suspicious), 'gold_clean': len(gold_clean),
            'text_suspect_on_gold_clean': sum(1 for row in gold_clean if {finding.kind for finding in row.check.findings if finding.severity == 'suspect'} & TEXT_FINDINGS),
            'finding_kinds': dict(Counter(finding.kind for row in checked for finding in row.check.findings if finding.severity == 'suspect')),
            'iou': iou, 'gold': summary}


def _gold_line(cell: dict, *path: str, digits: int = 3) -> str:
    node = cell['gold']
    for name in path:
        node = node[name] if node else None
    return 'n/a' if node is None else (f'{node:.{digits}f}' if isinstance(node, float) else str(node))


def score_table(cells: dict) -> list[str]:
    def row(name: str, getter) -> str:
        return f'| {name} | ' + ' | '.join(str(getter(cells[cell])) for cell in cells) + ' |'

    lines = ['| measure | ' + ' | '.join(cells) + ' |', '|---|' + '---|' * len(cells)]
    lines += [
        row('readings', lambda c: c['readings']), row('valid on the first attempt', lambda c: _rate(c['valid_first'], c['readings'])),
        row('result classes', lambda c: c['classes']), row('warnings (text intact)', lambda c: c['warnings']), row('USD per page', lambda c: c['usd_per_page']),
        row('input tokens per page', lambda c: c['input_per_page']), row('output tokens per page', lambda c: c['output_per_page']),
        row('control characters (silent corruption)', lambda c: c['control_characters']), row('KaTeX failures', lambda c: c['katex_failures']),
        row('formula exact', lambda c: f"{_gold_line(c, 'formula', 'exact')}/{_gold_line(c, 'formula', 'gold')} = {_gold_line(c, 'formula', 'exact_rate')}"),
        row('  display exact', lambda c: f"{_gold_line(c, 'formula', 'display_exact')}/{_gold_line(c, 'formula', 'display')}"),
        row('  inline exact', lambda c: f"{_gold_line(c, 'formula', 'inline_exact')}/{_gold_line(c, 'formula', 'inline')}"),
        row('  formula similarity', lambda c: _gold_line(c, 'formula', 'mean_similarity')),
        row('  labels right', lambda c: f"{_gold_line(c, 'formula', 'label_ok')}/{_gold_line(c, 'formula', 'numbered')}"),
        row('  formulas missing, as text, unrendered', lambda c: f"{_gold_line(c, 'formula', 'missing')}, {_gold_line(c, 'formula', 'as_text')}, {_gold_line(c, 'formula', 'unrendered')}"),
        row('table cells exact', lambda c: f"{_gold_line(c, 'table', 'exact')}/{_gold_line(c, 'table', 'cells')} = {_gold_line(c, 'table', 'exact_rate')}"),
        row('  raster values found', lambda c: f"{_gold_line(c, 'table', 'raster_found')}/{_gold_line(c, 'table', 'raster_values')}"),
        row('prose similarity', lambda c: _gold_line(c, 'prose', 'mean_similarity')), row('prose recall', lambda c: _gold_line(c, 'prose', 'recall')),
        row('prose precision', lambda c: _gold_line(c, 'prose', 'precision')),
        row('printed label', lambda c: f"{_gold_line(c, 'page_label', 'ok')}/{_gold_line(c, 'page_label', 'pages')}"),
        row('furniture out of the body', lambda c: f"{_gold_line(c, 'furniture', 'passed')}/{_gold_line(c, 'furniture', 'tests')}"),
        row('stage 2 suspicious', lambda c: _rate(c['suspicious'], c['checked'])),
        row('readings gold shows clean', lambda c: c['gold_clean']),
        row('  of those stage 2 suspicious', lambda c: _rate(c['suspicious_on_gold_clean'], c['gold_clean'])),
        row('  of those a text finding', lambda c: _rate(c['text_suspect_on_gold_clean'], c['gold_clean'])),
        row('stage 2 finding kinds', lambda c: c['finding_kinds']),
    ]
    for name in IOU_CLASSES:
        lines.append(row(f'median box IoU, {name}', lambda c, n=name: f"{c['iou'][n]['median']} (n={c['iou'][n]['n']})"))
    return lines


def score(args) -> dict:
    readings = stored_readings()
    measure(readings)
    cells = {cell: cell_measures([row for row in readings if row.record['cell'] == cell]) for cell in CELLS}
    pages = [{'cell': row.record['cell'], 'page': row.record.get('page_id'), 'class': row.record['result_class'], 'errors': row.page.errors,
              'check': row.check.as_dict(words=True) if row.check else None, 'score': row.score.as_dict() if row.score else None}
             for row in readings]
    report = {'cells': cells, 'pages': pages}
    path = open_store('free').write_report('mini_pilot_score.json', report)
    print('\n'.join(score_table(cells)))
    print('written to', path)
    return report


def plant(args) -> dict:
    """What stage 2 catches of each planted error. A catch is a new suspect finding: a page already suspect proves nothing."""
    readings = [row for row in stored_readings((args.cell,)) if row.page.valid]
    measure(readings)
    trials = []
    for row in readings:
        for kind in planted_errors.KINDS:
            planted = planted_errors.plant(row.page, kind)
            if planted is not None:
                trials.append((row, planted, parse(planted.text, 'markdown')))
    rendered = page_checks.render_formulas([page for _, _, page in trials])
    documents = Documents()
    results = {}
    for row, planted, page in trials:
        pdf_page = documents.page(row.record['file'], row.record['pdf_page'])
        before = Counter((f.kind, f.block) for f in row.check.findings if f.severity == 'suspect')
        after = Counter((f.kind, f.block) for f in page_checks.check_page(page, pdf_page, rendered).findings if f.severity == 'suspect')
        entry = results.setdefault(planted.kind, {'group': planted_errors.GROUPS[planted.kind], 'applicable': 0, 'caught': 0})
        entry['applicable'] += 1
        entry['caught'] += bool(after - before)
    report = {'cell': args.cell, 'readings': len(readings), 'kinds': results}
    path = open_store('free').write_report('mini_pilot_plant.json', report)
    print(f'{args.cell}: {len(readings)} valid readings, {len(trials)} planted errors')
    for kind, entry in results.items():
        print(f"{entry['group']:10} {kind:26} caught by stage 2 {_rate(entry['caught'], entry['applicable'])}")
    print('written to', path)
    return report


def _suffix(version: str | None) -> str:
    """judge/1's files keep the names they had before versions were named; another version's carry it."""
    return '' if version in (None, page_judge.FIRST_VERSION) else '_' + version.replace('/', '')


def _plan_name(model: str, version: str | None = None) -> str:
    return f'judge_plan_{model}{_suffix(version)}.json'


def judge_plan(args) -> dict:
    """The calibration set: readings gold shows clean, and planted errors on them, with a fixed seed."""
    readings = [row for row in stored_readings((args.cell,)) if row.page.valid]
    measure(readings)
    store = open_store('free')
    clean = [row for row in readings if _gold_clean(row)]
    bases = clean + [row for row in readings if row not in clean]
    rng = random.Random(f'judge:{args.seed}')
    items = [(row, None, row.page) for row in rng.sample(clean, min(args.clean, len(clean)))]
    for kind in planted_errors.KINDS:
        done = 0
        for row in rng.sample(bases, len(bases)):
            planted = planted_errors.plant(row.page, kind, args.seed)
            if planted is not None:
                items.append((row, planted, parse(planted.text, 'markdown')))
                done += 1
            if done == args.planted:
                break
    entries = []
    for row, planted, page in items:
        entries.append(page_judge.entry_for(row.record, page, args.model, planted, version=getattr(args, 'version', None)))
    plan = {'model': args.model, 'version': getattr(args, 'version', None), 'cell': args.cell, 'seed': args.seed, 'clean_available': len(clean), 'entries': entries,
            'estimate_usd': sum(entry['estimate_usd'] for entry in entries)}
    path = store.write_report(_plan_name(args.model, getattr(args, 'version', None)), plan)
    print(f"{args.model}: {sum(1 for e in entries if not e['planted'])} clean, {sum(1 for e in entries if e['planted'])} planted, "
          f"{len(clean)} readings gold shows clean, estimate {plan['estimate_usd']:.4f} USD, written to {path}")
    return plan


def judge_replan(args) -> dict:
    """judge/1's calibration set judged by another version: every clean reading and planted copy of the first plan, made again,
    and kept only where the judge would see exactly the same view as before, so the prompt is the one thing that differs
    (decision 147.a). A fresh judge-plan would draw another set: the validator of 8 Nov changed which pilot readings are valid."""
    store = open_store('free')
    source = _plan_name(getattr(args, 'from_model', None) or args.model)  # judge/4 runs on Opus over Sonnet's set (197.a)
    first = json.loads(store.path('reports', source).read_text(encoding='utf-8'))
    rows = {row.record['reading_key']: row for row in stored_readings((first['cell'],))}
    entries, dropped = [], Counter()
    for entry in first['entries']:
        row = rows.get(entry['target_key'])
        if row is None:
            dropped['reading gone'] += 1
            continue
        planted, page = None, row.page
        if entry['planted']:
            planted = planted_errors.plant(row.page, entry['planted'], first['seed'])
            if planted is None or planted.block != entry['planted_block']:
                dropped['planted elsewhere now'] += 1
                continue
            page = parse(planted.text, 'markdown')
        made = page_judge.entry_for(row.record, page, args.model, planted, version=args.version)
        if made['view_sha256'] != entry['view_sha256']:
            dropped['another view now'] += 1
            continue
        entries.append({**made, 'first_entry': entry['reading_key']})
    plan = {'model': args.model, 'version': args.version, 'cell': first['cell'], 'seed': first['seed'], 'from': source,
            'entries': entries, 'dropped': dict(dropped), 'estimate_usd': sum(entry['estimate_usd'] for entry in entries)}
    path = store.write_report(_plan_name(args.model, args.version), plan)
    print(f"{args.model} {args.version}: {len(entries)} of {len(first['entries'])} entries made again with the same view "
          f"({sum(1 for e in entries if e['planted'])} planted), dropped {dict(dropped) or 'none'}, "
          f"estimate {plan['estimate_usd']:.4f} USD, written to {path}")
    return plan


def judge_submit(args) -> None:
    plan = json.loads(open_store('free').path('reports', _plan_name(args.model, getattr(args, 'version', None))).read_text(encoding='utf-8'))
    store = open_store('free')
    entries = [entry for entry in plan['entries'] if store.reading(entry['reading_key']) is None]
    skipped = Counter({'already judged': len(plan['entries']) - len(entries)})
    vision_batches.send_entries(anthropic_client.client(), entries, skipped, args.cap, dry_run=args.dry_run)


def judge_measures(plan: dict, records: dict) -> dict:
    """Detection per planted kind and group, false alarms on clean readings, and the unsure rate. Pure, so tests need no store."""
    groups, kinds, clean = {}, {}, {'n': 0, 'issue': 0, 'unsure': 0, 'major': 0}
    cost, answered, failed = 0.0, 0, Counter()
    for entry in plan['entries']:
        record = records.get(entry['reading_key'])
        if record is None:
            failed['not collected'] += 1
            continue
        cost += record.get('cost_usd', 0.0)
        verdict_data = record.get('verdict')
        if verdict_data is None:
            failed[record.get('result_class', 'unknown')] += 1
            continue
        answered += 1
        verdict = Verdict(verdict_data['verdict'], verdict_data.get('findings', []))
        if not entry['planted']:
            clean['n'] += 1
            clean['issue'] += verdict.outcome != 'ok'
            clean['unsure'] += verdict.verdict == 'unsure'
            clean['major'] += bool(verdict.major)
            continue
        on_block = any(finding.get('block') == entry['planted_block'] for finding in verdict.findings)
        for table, name in ((kinds, entry['planted']), (groups, planted_errors.GROUPS[entry['planted']])):
            row = table.setdefault(name, {'n': 0, 'to_issue': 0, 'on_block': 0})
            row['n'] += 1
            row['to_issue'] += verdict.outcome != 'ok'
            row['on_block'] += on_block
    return {'model': plan['model'], 'groups': groups, 'kinds': kinds, 'clean': clean, 'usd_per_page': round(cost / max(answered, 1), 5),
            'usd_total': round(cost, 4), 'answered': answered, 'failed': dict(failed)}


def judge_score(args) -> dict:
    store = open_store('free')
    plan = json.loads(store.path('reports', _plan_name(args.model, getattr(args, 'version', None))).read_text(encoding='utf-8'))
    records = {entry['reading_key']: store.reading(entry['reading_key']) for entry in plan['entries']}
    report = judge_measures(plan, records)
    disagreements = [{'target': entry['target_key'], 'page': entry.get('page_id'), 'verdict': records[entry['reading_key']]['verdict']}
                     for entry in plan['entries'] if not entry['planted'] and (records.get(entry['reading_key']) or {}).get('verdict')
                     and records[entry['reading_key']]['verdict']['outcome'] != 'ok']
    report['disagreements_on_clean'] = disagreements
    path = store.write_report(f'judge_score_{args.model}{_suffix(getattr(args, 'version', None))}.json', report)
    print(f"{args.model}: {report['answered']} answered, {report['failed'] or 'no failures'}, {report['usd_total']} USD, {report['usd_per_page']} USD per page")
    print(f"clean: {_rate(report['clean']['issue'], report['clean']['n'])} an issue, {report['clean']['unsure']} unsure")
    for group, row in report['groups'].items():
        print(f"{group:10} an issue {_rate(row['to_issue'], row['n'])}, a finding on the planted block {_rate(row['on_block'], row['n'])}")
    for kind, row in report['kinds'].items():
        print(f"   {kind:26} {_rate(row['to_issue'], row['n'])}")
    print('written to', path)
    return report


def report(args) -> None:
    """All of it in one Markdown file: tables with n beside every rate, no adjectives."""
    store = open_store('free')
    folder = store.path('reports', 'x').parent
    lines = ['# Mini pilot, measured', '']
    score_path = folder / 'mini_pilot_score.json'
    if score_path.exists():
        lines += ['## Readings', ''] + score_table(json.loads(score_path.read_text(encoding='utf-8'))['cells']) + ['']
    plant_path = folder / 'mini_pilot_plant.json'
    if plant_path.exists():
        data = json.loads(plant_path.read_text(encoding='utf-8'))
        lines += [f"## Planted errors against stage 2 ({data['cell']}, {data['readings']} readings)", '', '| group | kind | caught |', '|---|---|---|']
        lines += [f"| {row['group']} | {kind} | {_rate(row['caught'], row['applicable'])} |" for kind, row in data['kinds'].items()] + ['']
    for path in sorted(folder.glob('judge_score_*.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        lines += [f"## Judge {data['model']}", '', f"{data['usd_per_page']} USD per page, {data['answered']} answered, failed: {data['failed'] or 'none'}.",
                  f"Clean readings made an issue: {_rate(data['clean']['issue'], data['clean']['n'])}; unsure: {data['clean']['unsure']}.", '',
                  '| group | an issue | a finding on the planted block |', '|---|---|---|']
        lines += [f"| {group} | {_rate(row['to_issue'], row['n'])} | {_rate(row['on_block'], row['n'])} |" for group, row in data['groups'].items()] + ['']
    path = store.path('reports', SUMMARY)
    store._write(path, '\n'.join(lines).encode('utf-8'))
    print('written to', path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('score').set_defaults(run=score)
    plant_parser = commands.add_parser('plant')
    plant_parser.add_argument('--cell', default='MP-SM', choices=CELLS)
    plant_parser.set_defaults(run=plant)
    plan_parser = commands.add_parser('judge-plan')
    plan_parser.add_argument('--model', required=True, choices=anthropic_client.READER_MODELS)
    plan_parser.add_argument('--cell', default='MP-SM', choices=CELLS)
    plan_parser.add_argument('--clean', type=int, default=8)
    plan_parser.add_argument('--planted', type=int, default=2)
    plan_parser.add_argument('--seed', type=int, default=0)
    plan_parser.set_defaults(run=judge_plan)
    for command in (plan_parser,):
        command.add_argument('--version', default=page_judge.FIRST_VERSION, help='the judge version (decision 147.a)')
    replan_parser = commands.add_parser('judge-replan', help="judge/1's calibration set again, for another judge version")
    replan_parser.add_argument('--model', required=True, choices=anthropic_client.READER_MODELS)
    replan_parser.add_argument('--version', required=True, help='the judge version to measure, as judge/2')
    replan_parser.add_argument('--from-model', choices=anthropic_client.READER_MODELS,
                               help="whose judge/1 plan holds the set (default: --model's own; judge/4 on Opus takes Sonnet's)")
    replan_parser.set_defaults(run=judge_replan)
    submit_parser = commands.add_parser('judge-submit')
    submit_parser.add_argument('--model', required=True, choices=anthropic_client.READER_MODELS)
    submit_parser.add_argument('--cap', type=float, default=vision_batches.DEFAULT_CAP_USD)
    submit_parser.add_argument('--dry-run', action='store_true')
    submit_parser.set_defaults(run=judge_submit)
    submit_parser.add_argument('--version', default=page_judge.FIRST_VERSION, help='the judge version (decision 147.a)')
    score_parser = commands.add_parser('judge-score')
    score_parser.add_argument('--model', required=True, choices=anthropic_client.READER_MODELS)
    score_parser.set_defaults(run=judge_score)
    score_parser.add_argument('--version', default=page_judge.FIRST_VERSION, help='the judge version (decision 147.a)')
    commands.add_parser('report').set_defaults(run=report)
    return parser


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    vision_batches.quiet_sdk_logs()
    args = build_parser().parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
