"""Which pages need the paid vision reader: a free check from the PDF's own objects, one class set per page (decision 64.a).

Born-digital prose reads well from the text layer; what it loses are formulas, tables, figures and code. This check runs
before any paid reading, and its classes and the signals behind them are recorded, so a route decision can be traced. Its
recall is measured against the readings of the free corpus, whose classes the vision reader found:

    python -m backend.conversion.reading.page_classes bench      # per class: found, missed, false alarms; spends nothing

Checked before building: the large pipelines route the same way (a cheap layout pass, then the expensive model only where it
helps), and the layout models that do this locally (PP-DocLayout, PyMuPDF Layout, Docling's) are the next candidates, measured
on the same bench. These rules need no install and say why they fired.
"""

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from backend.conversion.checks.page_checks import MATH_FONTS, _is_glyph

MONOSPACED = 8  # PyMuPDF's span flag for a monospaced font
MONO_FONTS = re.compile(r'mono|courier|consol|menlo|inconsolata|cmtt|sourcecode', re.I)
MATH_CHARS = re.compile(r'[Ͱ-Ͽ∀-⋿←-⇿⁰-₟±×÷√]')
IMAGE_SHARE = 0.04  # an image this share of the page or more is a figure; a logo or an ornament is smaller
REPEATED_IMAGE = 5  # an image on this many pages of a work or more is furniture (a logo, a running ornament)
DRAWN_AREA_SHARE = 0.04  # a cluster of drawings covering this share of the page is a chart or a ruled table
MATH_LINE_SHARE = 0.3  # a line whose characters are this share math is a formula line
CODE_LINES = 3  # this many consecutive monospaced lines are a listing; one identifier in prose never is
TEXT_LAYER_CHARS = 50  # fewer characters than this: a scan, which takes its own route
DRAWN_GLYPHS = 10  # this many glyphs drawn as small filled paths are math the text layer lacks (OpenStax draws its formulas)
TEXT_TABLE_SIZE = 3  # a table found from text alignment alone needs this many rows and columns


@dataclass
class PageClasses:
    classes: set = field(default_factory=set)  # of 'formula', 'table', 'figure', 'code'; empty means text only
    signals: dict = field(default_factory=dict)
    scan: bool = False

    @property
    def needs_reader(self) -> bool:
        return bool(self.classes) and not self.scan


def repeated_images(document: pymupdf.Document) -> set:
    """The images that recur on many pages of a work: furniture, never a figure."""
    seen = Counter()
    for page in document:
        seen.update({image[0] for image in page.get_images()})
    return {xref for xref, pages in seen.items() if pages >= REPEATED_IMAGE}


def _lines(page: pymupdf.Page) -> list[list[dict]]:
    return [line['spans'] for block in page.get_text('dict')['blocks'] if block.get('type') == 0 for line in block['lines']]


def classify(page: pymupdf.Page, furniture: set = frozenset()) -> PageClasses:
    signals = measure(page, furniture)
    return PageClasses(decide(signals), signals, scan=signals['text_chars'] < TEXT_LAYER_CHARS)


def decide(signals: dict, rules: dict | None = None) -> set:
    """The classes the signals of one page add up to. `rules` overrides thresholds, so a bench can try other ones."""
    rules = {**THRESHOLDS, **(rules or {})}
    classes = set()
    if signals['text_chars'] < TEXT_LAYER_CHARS:
        return classes
    if signals['figure_images']:
        classes.add('figure')
    if signals['drawn_glyphs'] >= rules['drawn_glyphs']:
        classes.add('formula')
    if signals['math_lines'] >= rules['math_lines']:
        classes.add('formula')
    if signals['ruled_tables']:
        classes.add('table')
    elif signals['drawn_clusters'] >= rules['drawn_clusters']:
        classes.add('figure')
    if rules['aligned_tables'] and signals['aligned_cells'] >= rules['aligned_tables'] and not signals['drawn_clusters']:
        classes.add('table')
    if signals['mono_run'] >= rules['mono_run']:
        classes.add('code')
    return classes


# Decision 66.a (the operator, 2026-11-03): the rule set that keeps recall at 97 % on the free corpus (31 of 1,101 structure pages missed,
# 214 of 482 text-only pages sent along). Tables found from text alignment alone stay off: they fired on 300 text-only pages.
THRESHOLDS = {'drawn_glyphs': DRAWN_GLYPHS, 'math_lines': 1, 'drawn_clusters': 1, 'aligned_tables': 0, 'mono_run': CODE_LINES}


def measure(page: pymupdf.Page, furniture: set = frozenset()) -> dict:
    """Every signal of one page as a number, so a decision can be traced and a threshold tuned without reading the page again."""
    area = abs(page.rect)
    signals = {'text_chars': len(page.get_text('text').strip()), 'figure_images': 0, 'drawn_glyphs': 0, 'drawn_clusters': 0,
               'ruled_tables': 0, 'aligned_cells': 0, 'math_lines': 0, 'mono_run': 0}
    if signals['text_chars'] < TEXT_LAYER_CHARS:
        return signals
    signals['figure_images'] = sum(1 for info in page.get_image_info(xrefs=True) if info.get('xref') not in furniture
                                   and abs(pymupdf.Rect(info['bbox']) & page.rect) / area >= IMAGE_SHARE)
    drawings = page.get_drawings()
    signals['drawn_glyphs'] = sum(1 for drawing in drawings if _is_glyph(drawing))
    clusters = [rect for rect in page.cluster_drawings(drawings=drawings) if abs(rect) / area >= DRAWN_AREA_SHARE]
    signals['drawn_clusters'] = len(clusters)
    if clusters:
        signals['ruled_tables'] = sum(1 for table in page.find_tables(strategy='lines').tables
                                      if table.row_count >= 2 and table.col_count >= 2)
    else:
        signals['aligned_cells'] = max((table.row_count * table.col_count for table in page.find_tables(strategy='text').tables
                                        if table.row_count >= TEXT_TABLE_SIZE and table.col_count >= TEXT_TABLE_SIZE), default=0)
    math_lines = mono_run = longest_run = 0
    for spans in _lines(page):
        chars = sum(len(span['text'].strip()) for span in spans)
        if not chars:
            continue
        math = sum(len(span['text'].strip()) for span in spans if MATH_FONTS.search(span['font']))
        math += sum(len(MATH_CHARS.findall(span['text'])) for span in spans if not MATH_FONTS.search(span['font']))
        math_lines += math / chars >= MATH_LINE_SHARE
        mono = all(span['flags'] & MONOSPACED or MONO_FONTS.search(span['font']) for span in spans if span['text'].strip())
        mono_run = mono_run + 1 if mono else 0
        longest_run = max(longest_run, mono_run)
    signals['math_lines'], signals['mono_run'] = math_lines, longest_run
    return signals


def truth_of(parsed) -> set:
    """The classes a valid reading holds: a formula block or inline math, a table, a figure, a code listing."""
    found = {block.cls for block in parsed.blocks} & {'formula', 'table', 'figure', 'code'}
    if any(block.inline.get('math') for block in parsed.blocks if getattr(block, 'inline', None)):
        found.add('formula')
    return found


def bench(args) -> dict:
    """Recall and precision per class against the free corpus's valid readings (latest attempt per page)."""
    from backend.conversion.checks import check_run
    from backend.conversion.reading import vision_batches
    from backend.conversion.contract.page_contract import Expected, parse
    from backend.conversion.store.reading_store import open_store

    store = open_store('free')
    records = check_run.latest_per_page([record for record in store.readings()
                                         if record.get('cell') in ('FREE-SM', 'MP2-SM') and record.get('kind', 'reading') == 'reading'])
    documents, furniture, counts, missed, rows = vision_batches.Documents(), {}, Counter(), Counter(), []
    for record in records:
        if vision_batches.current_class(record, store) != 'ok':
            continue
        parsed = parse(store.reading_text(record['reading_key']) or '', record['form'],
                       Expected(record['work'], record['pdf_page'], tuple(record['image_size'])))
        _, page = documents.page(record['file'], record['pdf_page'])
        if record['file'] not in furniture:
            furniture[record['file']] = repeated_images(page.parent)
        signals = measure(page, furniture[record['file']])
        truth, predicted = truth_of(parsed), decide(signals)
        rows.append({'key': record['reading_key'], 'work': record['work'], 'pdf_page': record['pdf_page'],
                     'truth': sorted(truth), 'signals': signals})
        counts['pages'] += 1
        for name in ('formula', 'table', 'figure', 'code', 'any'):
            has, says = (bool(truth), bool(predicted)) if name == 'any' else (name in truth, name in predicted)
            counts[f'{name} found'] += has and says
            counts[f'{name} missed'] += has and not says
            counts[f'{name} false alarm'] += says and not has
            if name == 'any' and has and not says:
                missed[', '.join(sorted(truth))] += 1
    result = {'thresholds': THRESHOLDS, 'counts': dict(counts), 'missed_any_by_truth': dict(missed)}
    path = store.write_report('page_classes_bench.json', result)
    store.write_report('page_classes_rows.json', {'rows': rows})
    print(f"{counts['pages']} pages")
    for name in ('any', 'formula', 'table', 'figure', 'code'):
        found, lost, false = counts[f'{name} found'], counts[f'{name} missed'], counts[f'{name} false alarm']
        recall = found / (found + lost) if found + lost else float('nan')
        precision = found / (found + false) if found + false else float('nan')
        print(f'  {name:8} recall {recall:.3f} ({found}/{found + lost}), precision {precision:.3f}, false alarms {false}')
    print(f'missed structure pages, by what the reader found: {dict(missed)}; written to {path.name}')
    return result


def score(rows: list[dict], rules: dict) -> dict:
    """Over the bench's rows: how many structure pages a rule set finds and misses, and how many text-only pages it sends."""
    found = missed = alarms = text_only = 0
    for row in rows:
        says, has = bool(decide(row['signals'], rules)), bool(row['truth'])
        found += has and says
        missed += has and not says
        alarms += says and not has
        text_only += not has
    return {'recall': found / (found + missed) if found + missed else 1.0, 'missed': missed, 'false_alarms': alarms,
            'text_only': text_only}


def tune(args) -> None:
    """Tries other thresholds on the bench's stored rows, without reading a page again."""
    import itertools

    from backend.conversion.store.reading_store import open_store

    rows = json.loads(open_store('free').path('reports', 'page_classes_rows.json').read_text(encoding='utf-8'))['rows']
    grid = {'drawn_glyphs': (5, 10, 20, 40, 80, 10 ** 9), 'math_lines': (1, 2, 3), 'drawn_clusters': (1, 2, 3, 4),
            'aligned_tables': (0, 36, 64, 100, 150, 250, 400), 'mono_run': (CODE_LINES,)}
    results = []
    for values in itertools.product(*grid.values()):
        rules = dict(zip(grid, values))
        results.append((rules, score(rows, rules)))
    for floor in (0.99, 0.98, 0.97, 0.95):
        best = min((item for item in results if item[1]['recall'] >= floor), key=lambda item: item[1]['false_alarms'], default=None)
        if best:
            rules, result = best
            print(f"recall >= {floor}: {rules} -> recall {result['recall']:.3f}, missed {result['missed']}, "
                  f"false alarms {result['false_alarms']} of {result['text_only']} text-only pages")


CANDIDATE_RULES = {  # from `tune` on the free corpus, 2026-11-03: recall >= 0.97 and >= 0.95 with the fewest false alarms
    'recall97': {'drawn_glyphs': 10, 'math_lines': 1, 'drawn_clusters': 1, 'aligned_tables': 0, 'mono_run': 3},
    'recall95': {'drawn_glyphs': 10, 'math_lines': 1, 'drawn_clusters': 4, 'aligned_tables': 0, 'mono_run': 3},
}


def estimate(args) -> None:
    """Over the licensed PDFs a provider may receive: how many pages each candidate rule set would send to the reader, and what
    that would cost. Signals are stored in the licensed mirror's reports, never page text; spends nothing."""
    from backend.conversion.reading import reading_cells
    from backend.conversion.store.reading_store import open_store

    store, rows = open_store('licensed'), []
    for path in sorted(reading_cells.LICENSED_ARCHIVE.glob('*.pdf')):
        if not reading_cells.may_send(path.name):
            continue
        with pymupdf.open(path) as document:
            furniture = repeated_images(document)
            rows += [{'file': path.name, 'pdf_page': page.number + 1, 'signals': measure(page, furniture)} for page in document]
    store.write_report('page_classes_licensed_rows.json', {'rows': rows})
    scans = sum(1 for row in rows if row['signals']['text_chars'] < TEXT_LAYER_CHARS)
    print(f'{len(rows)} sendable pages, {scans} scans (own route)')
    for name, rules in CANDIDATE_RULES.items():
        sent = sum(1 for row in rows if decide(row['signals'], rules))
        print(f'  {name}: {sent} pages to the reader ({sent / len(rows):.1%}), about {sent * args.usd_per_page:.0f} USD')


def files_named(rows: list[dict], names: list[str] | None) -> set[str] | None:
    """The files `--files` names among the measured pages' files, each named by its file name or its stem; None where no name
    is given, which means every file (22 Nov: a new work's intake, while other sendable works wait for another route). A
    name that is not there, or a held file's, which `estimate` never measures, stops the command before anything is written."""
    if not names:
        return None
    by_name = {}
    for file in {row['file'] for row in rows}:
        by_name[file] = by_name[Path(file).stem] = file
    unknown = sorted(name for name in names if name not in by_name)
    if unknown:
        raise SystemExit(f'--files: {unknown} not among the measured sendable PDFs; nothing written')
    return {by_name[name] for name in names}


SAMPLE_SIZE = 200
PLANS = {'sample': 'page_classes_sample_plan.json',  # 200 random text-only pages: measures what the rules miss
         'cascade': 'page_classes_cascade_plan.json'}  # every text-only page: decision 67.a, rules then Haiku then Sonnet


def sample_plan(args) -> None:
    """A seeded random sample of the licensed pages the rules call text only, each rendered and planned for the cheap check."""
    import random

    from backend.conversion.reading import page_class_check, page_render, reading_cells
    from backend.conversion.store.reading_store import open_store

    store = open_store('licensed')
    rows = json.loads(store.path('reports', 'page_classes_licensed_rows.json').read_text(encoding='utf-8'))['rows']
    chosen = files_named(rows, getattr(args, 'files', None))
    rows = [row for row in rows if chosen is None or row['file'] in chosen]
    text_only = [row for row in rows if row['signals']['text_chars'] >= TEXT_LAYER_CHARS and not decide(row['signals'])]
    # The seed keeps the label it was drawn with (the decision is 66.a now): a new seed would draw another sample and buy it again
    sample = text_only if args.plan == 'cascade' else random.Random('page_classes:29.a').sample(text_only, min(args.size, len(text_only)))
    entries, documents = [], {}
    for row in sorted(sample, key=lambda row: (row['file'], row['pdf_page'])):
        if row['file'] not in documents:
            documents[row['file']] = pymupdf.open(reading_cells.LICENSED_ARCHIVE / row['file'])
        image = page_render.render(documents[row['file']][row['pdf_page'] - 1], 'hi')
        entries.append(page_class_check.entry_for(mirror='licensed', file_name=row['file'], work=Path(row['file']).stem,
                                                  pdf_page=row['pdf_page'], image=image, rule_classes=[]))
    plan = {'text_only_pages': len(text_only), 'sample': len(entries), 'thresholds': THRESHOLDS, 'entries': entries,
            'estimate_usd': sum(entry['estimate_usd'] for entry in entries)}
    store.write_report(PLANS[args.plan], plan)
    print(f"{len(text_only)} licensed pages the rules call text only; sample {len(entries)}, estimate {plan['estimate_usd']:.4f} USD")


def sample_submit(args) -> None:
    from backend.conversion.reading import vision_batches
    from backend.conversion.store.reading_store import open_store
    from backend.providers import anthropic_client

    store = open_store('licensed')
    plan = json.loads(store.path('reports', PLANS[args.plan]).read_text(encoding='utf-8'))
    entries = [entry for entry in plan['entries'] if store.reading(entry['reading_key']) is None]
    vision_batches.send_entries(anthropic_client.client(), entries, Counter({'already checked': len(plan['entries']) - len(entries)}),
                                args.cap, dry_run=args.dry_run)


def sample_report(args) -> None:
    """How many sampled text-only pages the cheap model finds structure on: the rules' miss rate on these books, as a bound."""
    from backend.conversion.store.reading_store import open_store

    store = open_store('licensed')
    plan = json.loads(store.path('reports', PLANS[args.plan]).read_text(encoding='utf-8'))
    named, unanswered, flagged = Counter(), Counter(), 0
    for entry in plan['entries']:
        record = store.reading(entry['reading_key'])
        if record is None or record.get('answer') is None:
            unanswered[record['result_class'] if record else 'not collected'] += 1
            continue
        classes = record['answer']['classes']
        flagged += bool(classes)
        named.update(classes)
    answered = len(plan['entries']) - sum(unanswered.values())
    result = {'sample': len(plan['entries']), 'answered': answered, 'with_structure': flagged, 'classes': dict(named),
              'unanswered': dict(unanswered), 'text_only_pages': plan['text_only_pages']}
    store.write_report(PLANS[args.plan].replace('_plan.json', '_report.json'), result)
    share = flagged / answered if answered else float('nan')
    print(f"{flagged} of {answered} sampled text-only pages hold structure by the cheap model ({share:.1%}): {dict(named)}; "
          f"unanswered {dict(unanswered)}")


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('bench').set_defaults(run=bench)
    commands.add_parser('tune').set_defaults(run=tune)
    estimate_parser = commands.add_parser('estimate')
    estimate_parser.add_argument('--usd-per-page', type=float, default=0.0163)  # Sonnet, Markdown, batch: the mini pilot
    estimate_parser.set_defaults(run=estimate)
    plan_parser = commands.add_parser('sample-plan')
    plan_parser.add_argument('--size', type=int, default=SAMPLE_SIZE)
    plan_parser.add_argument('--files', nargs='+', metavar='NAME',
                             help='plan only these PDFs, each by its file name or stem; default every sendable PDF')
    plan_parser.set_defaults(run=sample_plan)
    submit_parser = commands.add_parser('sample-submit')
    submit_parser.add_argument('--cap', type=float, default=40.0)
    submit_parser.add_argument('--dry-run', action='store_true')
    submit_parser.set_defaults(run=sample_submit)
    report_parser = commands.add_parser('sample-report')
    report_parser.set_defaults(run=sample_report)
    for command in (plan_parser, submit_parser, report_parser):
        command.add_argument('--plan', choices=sorted(PLANS), default='sample')
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
