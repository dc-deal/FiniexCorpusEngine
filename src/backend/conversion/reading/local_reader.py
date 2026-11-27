"""Test readings by local models (#17): what a model on the bench machine read of free pages, imported into the reading
store under the test cells. Nothing is bought, and nothing imported is ever chosen, checked or served: it stands in the Lab.

A run folder under `_work/free/local_readers/<run>/` holds `gold/` (each page image as the pipeline renders it, the page/1
system prompt, each page's user turn, `manifest.json`), `results/<model>/` (one answer per page and `results.jsonl` with the
seconds, tokens and GPU memory of each), `logs/` and `scripts/`. Each answer becomes one reading:

- Qwen3-VL answered in page/1. Its boxes lie on its own 0-1000 scale, mostly: a box wholly on that scale is rescaled to the
  image's pixels, any other is kept as written, and the record counts both (the night of 26 Nov: 5 of 20 pages held a box in
  pixels, mostly the footer). A box under 1000 that was meant as pixels cannot be told apart; a box is the model's claim.
- The document models answered in Markdown. `markdown_page` turns it into page/1 blocks by code (`CONVERTER`): display
  formulas, HTML and pipe tables, headings, paragraphs, each with a box over the whole page since these models give none,
  and front matter the converter fills. The record names both. Dollar signs stay text: on a finance page `$` is money.

The model's own answer is kept as an input of the store, its sha256 in the record; the reading's text is the page/1 file.
A reading's key covers the image, the prompts, the parameters, the model's answer and the converter, so an import run twice
stores nothing new, and a changed converter stores new readings beside the old ones.

    python -m backend.conversion.reading.local_reader import --run night_2026-11-26

Why own code: docling-core reads Markdown into its document model, but that model is not the page/1 contract, and its
round trip into page/1 would be the same conversion with one more dependency in between (checked 27 Nov: the mini pilot's
readings are page/1 files, which no maintained library writes).
"""

import argparse
import json
import re
import sys
from collections import Counter
from html import escape
from pathlib import Path

from backend.configuration import data_paths
from backend.conversion.reading import reader_requests, reading_cells, vision_batches
from backend.conversion.store.reading_store import open_store

RUNS = data_paths.FREE_WORKING / 'local_readers'
MIRROR = 'free'  # the mini pilot's pages are free; a test reading of a licensed page needs its own decision
PROVIDER = 'local'
DEVIATION = 'a test reading by a local model, never served'
CONVERTER = 'markdown-to-page1/1'
QWEN_SCALE = 1000
# What each model of a run was, by its results folder: its test cell, how it was asked, and the shape of its answer. The
# document models' prompts are their vendors' task prompts, as their model cards give them; MinerU's two-step extraction
# asks with the package's own prompts, which were not copied off the bench machine, so its prompt is None.
MODELS = {
    'qwen3-vl-30b-a3b-q4km': {'cell': 'LAB-QWEN3VL-MP', 'adapter': 'llama.cpp server', 'answer': 'page1', 'prompt': None},
    'paddleocr-vl-1.6': {'cell': 'LAB-PADDLE-MP', 'adapter': 'transformers', 'answer': 'markdown', 'prompt': 'OCR:'},
    'mineru2.5-pro-2605': {'cell': 'LAB-MINERU-MP', 'adapter': 'mineru-vl-utils on transformers', 'answer': 'markdown',
                           'prompt': None},
    'glm-ocr': {'cell': 'LAB-GLMOCR-MP', 'adapter': 'transformers', 'answer': 'markdown', 'prompt': 'Text Recognition:'},
}
STOP_REASONS = {'stop': 'end_turn', 'length': 'max_tokens', None: 'end_turn'}
BOX = re.compile(r'bbox="(\d+) (\d+) (\d+) (\d+)"')


# ---------------------------------------------------------------- the answers into page/1

def rescale_boxes(text: str, width: int, height: int) -> tuple[str, dict]:
    """Qwen's boxes from its 0-1000 scale to the image's pixels; a box with a value above the scale is kept as written."""
    counts = Counter()

    def scaled(match: re.Match) -> str:
        x0, y0, x1, y1 = (int(value) for value in match.groups())
        if max(x0, y0, x1, y1) > QWEN_SCALE:
            counts['kept'] += 1
            return match.group(0)
        counts['rescaled'] += 1
        return (f'bbox="{round(x0 * width / QWEN_SCALE)} {round(y0 * height / QWEN_SCALE)} '
                f'{round(x1 * width / QWEN_SCALE)} {round(y1 * height / QWEN_SCALE)}"')

    return BOX.sub(scaled, text), {'boxes_rescaled': counts['rescaled'], 'boxes_kept': counts['kept']}


def _chunks(raw: str) -> list[str]:
    """The answer cut at blank lines, a display formula or a table that spans one kept whole."""
    pieces = [piece.strip() for piece in re.split(r'\n[ \t]*\n', raw.replace('\r\n', '\n').strip()) if piece.strip()]
    merged: list[str] = []
    for piece in pieces:
        if merged and _open(merged[-1]):
            merged[-1] += '\n\n' + piece
        else:
            merged.append(piece)
    return merged


def _open(chunk: str) -> bool:
    """Whether a display formula or a table begun in the chunk is still open at its end."""
    if chunk.startswith('$$'):
        return chunk.count('$$') % 2 == 1
    if chunk.startswith('\\['):
        return '\\]' not in chunk
    if chunk.lower().startswith('<table'):
        return '</table>' not in chunk.lower()
    return False


PIPE_RULE = re.compile(r'^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$')


def _pipe_table(chunk: str) -> str | None:
    """A Markdown pipe table as page/1's HTML table, its first row the head where a rule line follows it; None for any
    other chunk."""
    lines = [line.strip() for line in chunk.split('\n')]
    if len(lines) < 2 or not all(line.startswith('|') for line in lines):
        return None
    rows = [[escape(cell.strip(), quote=False) for cell in line.strip('|').split('|')] for line in lines
            if not PIPE_RULE.match(line)]
    head = rows[0] if len(lines) > 1 and PIPE_RULE.match(lines[1]) else None
    body = rows[1:] if head is not None else rows
    html = ['<table>']
    if head is not None:
        html.append('<thead><tr>' + ''.join(f'<th>{cell}</th>' for cell in head) + '</tr></thead>')
    html.append('<tbody>')
    html += ['<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>' for row in body]
    html += ['</tbody>', '</table>']
    return '\n'.join(html)


def _block(chunk: str) -> tuple[str, str] | None:
    """One chunk as (page/1 class, body), None for a chunk with nothing to read (an image reference)."""
    if chunk.startswith('$$') and chunk.endswith('$$') and len(chunk) > 4:
        return 'formula', chunk[2:-2].strip()
    if chunk.startswith('\\[') and chunk.endswith('\\]'):
        return 'formula', chunk[2:-2].strip()
    if chunk.lower().startswith('<table') and chunk.lower().endswith('</table>'):
        return 'table', chunk
    table = _pipe_table(chunk)
    if table is not None:
        return 'table', table
    if re.fullmatch(r'!\[[^\]]*\]\([^)]*\)', chunk):
        return None
    heading = re.match(r'^#{1,6}\s+(.*)$', chunk, re.S)
    if heading:
        return 'heading', ' '.join(heading.group(1).split())
    return 'paragraph', ' '.join(line.strip() for line in chunk.split('\n') if line.strip())


def markdown_page(raw: str, page: dict) -> tuple[str, dict]:
    """A document model's Markdown as a page/1 file: front matter the converter fills (the printed label unknown, the
    page taken as a body page), then one block per chunk, each with a box over the whole page."""
    width, height = page['width'], page['height']
    front = ['---', 'contract: page/1', f"work: {page['work']}", f"pdf_page: {page['pdf_page']}",
             f'image_size: "{width}x{height}"', 'printed_label: null', 'page_kind: body', '---', '']
    blocks, dropped, counts = [], 0, Counter()
    for chunk in _chunks(raw):
        found = _block(chunk)
        if found is None:
            dropped += 1
            continue
        cls, body = found
        counts[cls] += 1
        fence = ':' * max(3, 1 + max((len(run) for run in re.findall(r'^(:{3,})', body, re.M)), default=0))
        blocks.append(f'{fence} {{#b{len(blocks) + 1:02d} .{cls} bbox="0 0 {width} {height}"}}\n{body}\n{fence}\n')
    notes = {'converter': CONVERTER, 'boxes': 'the whole page: the model gives none',
             'front_filled': ['printed_label', 'page_kind'], 'blocks': dict(counts), 'images_dropped': dropped}
    return '\n'.join(front) + '\n'.join(blocks), notes


# ---------------------------------------------------------------- a run into the store

def answers(model_dir: Path) -> dict[str, dict]:
    """Each page's latest answered record of a model's run, by page id: a failed attempt or a load line is no answer."""
    found = {}
    log = model_dir / 'results.jsonl'
    for line in log.read_text(encoding='utf-8').splitlines() if log.exists() else []:
        record = json.loads(line)
        if record.get('id') and not record.get('error') and record.get('chars') is not None \
                and (model_dir / f"{record['id']}.md").exists():
            found[record['id']] = record
    return found


def reading_spec(*, image_sha: str, model: str, adapter: str, system_sha: str | None, user_sha: str | None,
                 max_tokens: int, answer_sha: str, converter: str | None) -> dict:
    """Everything a test reading asked and answered, as hashes and parameters: the input of its key."""
    return {'inputs': {'image': image_sha, 'answer': answer_sha}, 'model': model, 'adapter': adapter, 'provider': PROVIDER,
            'prompt': {'system': system_sha, 'user': user_sha, 'form': 'markdown', 'schema': None},
            'params': {'max_tokens': max_tokens, 'decoding': 'greedy', 'replicate': 0, 'attempt': 0},
            'mode': reading_cells.LOCAL, 'converter': converter}


def import_run(run: Path, store=None) -> Counter:
    """Every answer of a run as a test reading; an answer stored before is left as it is."""
    store = store or open_store(MIRROR)
    gold = run / 'gold'
    manifest = {page['id']: page for page in json.loads((gold / 'manifest.json').read_text(encoding='utf-8'))['pages']}
    system_text = (gold / 'system_page1_markdown.txt').read_bytes().decode('utf-8')
    if reader_requests.sha256_text(system_text) != reader_requests.sha256_text(reader_requests.system_prompt('markdown')):
        raise ValueError(f'{gold.name}: the system prompt differs from page/1 as the pipeline holds it')
    pilot = {f"{page['work']}_p{page['pdf_page']:04d}": page
             for page in json.loads(reading_cells.MINI_PILOT.read_text(encoding='utf-8'))['pages']}
    outcome = Counter()
    for folder, model in MODELS.items():
        model_dir = run / 'results' / folder
        if not model_dir.is_dir():
            continue
        cell = reading_cells.TEST_READING_CELLS[model['cell']]
        for page_id, said in sorted(answers(model_dir).items()):
            page, listed = manifest[page_id], pilot[page_id]
            raw = (model_dir / f'{page_id}.md').read_bytes().decode('utf-8')
            image_sha = store.put_input((gold / f'{page_id}.png').read_bytes(), '.png')
            if image_sha != page['image_sha256']:
                raise ValueError(f'{page_id}: the stored image is not the one the manifest names')
            answer_sha = store.put_input(raw.encode('utf-8'), '.md')
            if model['answer'] == 'page1':
                text, notes = rescale_boxes(raw, page['width'], page['height'])
                system_sha = store.put_prompt(system_text)
                user_sha = store.put_prompt((gold / f'{page_id}.user.txt').read_bytes().decode('utf-8'))
                converter = None
            else:
                text, notes = markdown_page(raw, page)
                system_sha = None
                user_sha = store.put_prompt(model['prompt']) if model['prompt'] else None
                converter = CONVERTER
            key = reader_requests.reading_key(reading_spec(
                image_sha=image_sha, model=cell.model, adapter=model['adapter'], system_sha=system_sha, user_sha=user_sha,
                max_tokens=cell.max_tokens, answer_sha=answer_sha, converter=converter))
            if store.reading(key) is not None:
                outcome['already stored'] += 1
                continue
            entry = {'reading_key': key, 'custom_id': reader_requests.custom_id(key), 'cell': cell.name,
                     'page_id': f"{listed['work']}:p{listed['pdf_page']:04d}", 'file': listed['file'],
                     'pdf_page': listed['pdf_page'], 'work': listed['work'], 'mirror': MIRROR, 'model': cell.model,
                     'resolution': cell.resolution, 'form': cell.form, 'replicate': 0, 'attempt': 0,
                     'max_tokens': cell.max_tokens, 'image_sha256': image_sha, 'image_size': [page['width'], page['height']],
                     'system_sha256': system_sha, 'user_sha256': user_sha, 'mode': cell.mode, 'retry_of': None}
            stop_reason = STOP_REASONS.get(said.get('finish'), 'end_turn')
            result_class, checked = vision_batches.check_reading(entry, text, stop_reason)
            record = {**entry, 'kind': 'reading', 'adapter': model['adapter'], 'provider': PROVIDER, 'deviation': DEVIATION,
                      'stored_at': vision_batches.now(), 'sdk': model['adapter'], 'result_type': 'succeeded',
                      'error_type': None, 'error_message': None, 'stop_reason': stop_reason, 'finish': said.get('finish'),
                      'usage': said.get('usage') or {key_: said[key_] for key_ in ('input_tokens', 'output_tokens')
                                                         if key_ in said},
                      'cost_usd': 0.0, 'seconds': said.get('seconds'), 'vram_used_mib': said.get('vram_used_mib'),
                      'torch_peak_mib': said.get('torch_peak_mib'), 'run': run.name, 'answer_sha256': answer_sha,
                      'conversion': notes, 'result_class': result_class,
                      'text_sha256': reader_requests.sha256_text(text), 'text_chars': len(text), 'contract': checked}
            store.save_reading(key, record, text)
            outcome[f"{cell.name} {result_class}"] += 1
    return outcome


# ---------------------------------------------------------------- the judge's requests on them

JUDGEABLE = ('ok', 'malformed')  # judged on what it says; the format check is a measure of its own in the Lab (#17)


def judge_plan(cell_name: str, store=None) -> dict:
    """The judge's requests on a test cell's readings: each page's latest that the page/1 parser cuts into blocks, valid or
    malformed. A reading with a stray `$` is still judged on what it says, and its format is counted apart. Written as the
    check flow's plan for the cell, which the session judge reads (`session_judge prepare --cells <cell>`); a test cell is
    planned alone, since a plan keeps one reading per page. Stage 2 and the pipeline's kept sample are left alone."""
    from backend.conversion.checks import check_run
    from backend.conversion.contract.page_contract import Expected, parse
    from backend.conversion.judge import page_judge

    if not reading_cells.is_test_cell(cell_name):
        raise ValueError(f'{cell_name} is no test cell: the pipeline plans its own (`check_run plan`)')
    store = store or open_store(MIRROR)
    skipped, entries = Counter(), []
    newest_first = sorted(vision_batches.readings_of([cell_name], store), key=lambda record: record.get('stored_at') or '',
                          reverse=True)  # every test reading is attempt 0: of two on a page (a new converter) the newer stands
    records = check_run.latest_per_page(newest_first,
                                        valid=lambda record: vision_batches.current_class(record, store) in JUDGEABLE)
    for record in sorted(records, key=lambda record: (record['file'], record['pdf_page'])):
        result_class = vision_batches.current_class(record, store)
        if result_class not in JUDGEABLE:
            skipped[result_class] += 1
            continue
        parsed = parse(store.reading_text(record['reading_key']) or '', record['form'],
                       Expected(record['work'], record['pdf_page'], tuple(record['image_size'])))
        if not parsed.blocks:
            skipped['no blocks'] += 1
            continue
        # the reading's cell travels with the request, so the session judge keeps four models' folders of one page apart
        entries.append({**page_judge.entry_for(record, parsed, check_run.JUDGE_MODEL), 'target_cell': cell_name})
    plan = {'cells': [cell_name], 'judge': check_run.JUDGE_MODEL, 'lab': True, 'suspicious': [], 'sampled': [],
            'entries': entries, 'skipped': dict(skipped), 'estimate_usd': sum(entry['estimate_usd'] for entry in entries)}
    store.write_report(check_run._plan_name([cell_name]), plan)
    return plan


# ---------------------------------------------------------------- the comparison

REPORT = 'local_readers_report.json'
REFERENCE = 'served'  # the reading each page serves today: Sonnet's page/1, judged, the bar a local reader must reach


def _side(store, records: list[dict], judgements: dict) -> dict:
    """One reader's measures over its pages: format, publisher gold (content, scored on every reading that parses, valid or
    not), the judge's verdicts, and its seconds and memory where it ran locally."""
    from statistics import median

    from backend.conversion.contract.page_contract import parse
    from backend.conversion.measurement import mini_pilot

    rows = []
    for record in records:
        text = store.reading_text(record['reading_key']) or ''
        rows.append(mini_pilot.Reading(record, text, parse(text, record['form'], mini_pilot.expected_of(record))))
    mini_pilot.measure(rows)
    scored = [row for row in rows if row.score]
    verdicts = Counter()
    for row in rows:
        counted = [judgement for judgement in judgements.get(row.key, []) if judgement.get('counts')]
        verdicts[counted[-1]['verdict'] if counted else 'not judged'] += 1
    seconds = [row.record['seconds'] for row in rows if row.record.get('seconds') is not None]
    memory = [row.record.get('torch_peak_mib') or row.record.get('vram_used_mib') for row in rows]
    return {'pages': len(rows), 'valid': sum(row.page.valid for row in rows),
            'classes': dict(Counter(vision_batches.current_class(row.record, store) for row in rows)),
            'gold_pages': len(scored),
            'formulas_exact': sum(row.score.formula['exact'] for row in scored),
            'formulas': sum(row.score.formula['gold'] for row in scored),
            'cells_exact': sum(row.score.table['exact'] for row in scored if row.score.table),
            'cells': sum(row.score.table['cells'] for row in scored if row.score.table),
            'prose_similarity_median': (round(median(row.score.prose['similarity'] for row in scored if row.score.prose), 4)
                                        if any(row.score.prose for row in scored) else None),
            'clean_pages': sum(mini_pilot._gold_clean(row) for row in scored),
            'judge': dict(verdicts),
            'seconds_median': median(seconds) if seconds else None,
            'memory_mib_max': max((value for value in memory if value), default=None),
            'pages_by_key': {row.key: {'page': f"{row.record['work']}:p{row.record['pdf_page']:04d}",
                                       'class': vision_batches.current_class(row.record, store),
                                       'formulas': (f"{row.score.formula['exact']}/{row.score.formula['gold']}"
                                                    if row.score else None)} for row in rows}}


def report(store=None) -> dict:
    """Each test cell beside the reading the same pages serve today, by the same measures; written to the store's reports."""
    from backend.conversion.checks import check_run

    store = store or open_store(MIRROR)
    judgements = check_run.judgements_by_target(store)
    index = json.loads((data_paths.FREE_READINGS / 'index.json').read_text(encoding='utf-8'))  # what each page serves now
    served = {(row['file'], row['pdf_page']): row['reading_key'] for row in index['pages'] if row.get('reading_key')}
    sides = {}
    pages = set()
    for name in reading_cells.TEST_READING_CELLS:
        newest = sorted(vision_batches.readings_of([name], store), key=lambda record: record.get('stored_at') or '', reverse=True)
        records = check_run.latest_per_page(newest)
        pages |= {(record['file'], record['pdf_page']) for record in records}
        if records:
            sides[name] = _side(store, records, judgements)
    reference = [store.reading(served[page]) for page in sorted(pages) if page in served and store.reading(served[page])]
    sides[REFERENCE] = _side(store, reference, judgements)
    result = {'about': 'Test readings by local models beside the reading each page serves (#17); content scored by '
                       'publisher gold on every reading that parses, format counted apart.', 'sides': sides}
    store.write_report(REPORT, result)
    return result


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    importing = commands.add_parser('import', help="a run's answers as test readings in the Lab")
    importing.add_argument('--run', required=True, help='the run folder under _work/free/local_readers/')
    planning = commands.add_parser('judge-plan', help="the judge's requests on test cells, one plan per cell")
    planning.add_argument('--cells', required=True, help='test cells, comma-separated (LAB-QWEN3VL-MP,...)')
    commands.add_parser('report', help='every test cell beside the served readings of the same pages')
    args = parser.parse_args(argv)
    if args.command == 'import':
        outcome = import_run(RUNS / args.run)
        print(json.dumps(dict(sorted(outcome.items())), indent=1))
    elif args.command == 'report':
        for name, side in report()['sides'].items():
            print(f"{name:16} valid {side['valid']:>2}/{side['pages']:<2} formulas {side['formulas_exact']:>3}/{side['formulas']:<3} "
                  f"cells {side['cells_exact']:>4}/{side['cells']:<4} prose {side['prose_similarity_median']} "
                  f"clean {side['clean_pages']:>2}/{side['gold_pages']:<2} judge {side['judge']} "
                  f"s/page {side['seconds_median']} MiB {side['memory_mib_max']}")
    else:
        for name in [name.strip() for name in args.cells.split(',') if name.strip()]:
            plan = judge_plan(name)
            print(f"{name}: {len(plan['entries'])} judge requests, skipped {plan['skipped']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
