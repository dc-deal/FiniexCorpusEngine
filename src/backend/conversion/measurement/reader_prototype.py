"""A reader prompt version measured as a prototype beside page/1 (decision 207.a, the operator, 11 Nov: "let's do that").

The same free pages read with page/2 (cells P2-MP-SM and P2-WALK-SM, never served) against the reading each page serves
today, by two measures written before the run (the phase 2 protocol, 11 Nov): publisher gold on the mini pilot's 20 pages,
and the reader errors a person confirmed in the walk of 10 Nov, each checked by code against what the person recorded.
judge/4's verdict on each reading is reported beside them, not gated: a prototype judging a prototype.

    python -m backend.conversion.measurement.reader_prototype report
"""

import argparse
import json
import re
import sys
from collections import Counter

from backend.configuration import data_paths
from backend.conversion.checks import check_run
from backend.conversion.measurement import mini_pilot
from backend.conversion.reading import reading_cells, vision_batches
from backend.conversion.store import served_readings
from backend.conversion.contract.page_contract import ParsedPage, parse
from backend.conversion.store.reading_store import open_store

CELLS = tuple(sorted(reading_cells.READER_PROTOTYPE_CELLS))
JUDGE = 'judge/4'
EXPORT = data_paths.FREE_READINGS / 'index.json'
REPORT = 'reader_prototype_page2.json'

YEAR = re.compile(r'\b(19[4-9]\d|20[0-4]\d)\b')
MEETING = re.compile(r'cross|overtak|surpass|exceed|meet|intersect|converge', re.IGNORECASE)


def _texts(page: ParsedPage, *classes: str) -> list[str]:
    return [served_readings.block_text(block) for block in page.blocks if block.cls in classes]


def row_widths(block) -> list[int]:
    """Each row's width in columns: its own cells' colspans plus the cells reaching down into it from rows above."""
    widths, reaching = [], []  # reaching: [colspan, rows still covered] of cells with a rowspan
    for row in block.rows or []:
        widths.append(sum(span for span, _ in reaching) + sum(cell.colspan for cell in row))
        reaching = [[span, left - 1] for span, left in reaching if left > 1]
        reaching += [[cell.colspan, cell.rowspan - 1] for cell in row if cell.rowspan > 1]
    return widths


def chart_crossing(page: ParsedPage) -> tuple[bool, str]:
    """Finance p. 94: the lines meet at about 2012, the base year of chained 2012 dollars (the person's correction); page/1
    put it at 2000. Years named after a word of meeting, in the chart's description."""
    years = sorted({int(year) for text in _texts(page, 'description') for sentence in re.split(r'(?<=[.;])\s+', text)
                    for match in [MEETING.search(sentence)] if match for year in YEAR.findall(sentence[match.start():])})
    return any(2008 <= year <= 2016 for year in years) and not any(year <= 2005 for year in years), \
        f"years where the lines meet: {years or 'none named'}"


def equal_rows(page: ParsedPage) -> tuple[bool, str]:
    """Finance p. 119: the header's operator columns had no cells below them, so the grid shifted (the person's correction)."""
    widths = [row_widths(block) for block in page.blocks if block.cls == 'table']
    return bool(widths) and all(len(set(rows)) == 1 for rows in widths), f'row widths per table: {widths}'


def no_photo_text(page: ParsedPage) -> tuple[bool, str]:
    """Finance p. 387: the chapter opener's photo, whose signs and labels page/1 transcribed (decision 194.a)."""
    photos = [block for block in page.blocks if block.cls == 'figure' and block.attrs.get('kind') == 'photo']
    art = [block for block in page.blocks if block.cls == 'decoration' and block.attrs.get('kind') == 'chapter_art']
    lines = sum(1 for block in photos for line in block.body.splitlines() if line.strip())
    return bool(photos or art) and lines == 0, f'{len(photos)} photo(s), {lines} line(s) read from them'


def t_accounts_as_tables(page: ParsedPage) -> tuple[bool, str]:
    """Accounting p. 305: Figure 5.16 holds eleven T-accounts (the person counted them); page/1 wrote one grouped figure."""
    tables = [block for block in page.blocks if block.cls == 'table']
    return len(tables) == 11, f'{len(tables)} tables'


def journal_boxes_read(page: ParsedPage) -> tuple[bool, str]:
    """Accounting p. 524: three journal boxes printed as images and legible; page/1 marked them unreadable."""
    unreadable = [block.id for block in page.blocks if block.attrs.get('status') == 'unreadable']
    read = sum('Petty Cash' in served_readings.block_text(block) for block in page.blocks if block.cls == 'table')
    return not unreadable and read >= 3, f"unreadable: {unreadable or 'none'}; {read} tables with Petty Cash"


def index_number(page: ParsedPage) -> tuple[bool, str]:
    """Accounting p. 969: the index prints 'accumulated depletion 655'; page/1 wrote 489."""
    entries = [text for text in _texts(page, 'index_entry') if 'accumulated depletion' in text.lower()]
    return any(re.search(r'\b655\b', text) for text in entries), f"entries: {entries or 'none'}"


def table_title(page: ParsedPage) -> tuple[bool, str]:
    """Accounting p. 69: 'Types of Business Structures', printed above Table 2.1 (the served reading has it; a pilot one did not)."""
    titled = [text for text in _texts(page, 'heading', 'caption') if 'types of business structures' in text.lower()]
    return bool(titled), 'the title stands' if titled else 'no block holds the title'


KNOWN = {('openstax-finance-2e', 94): ('the chart crossing at about 2012', chart_crossing),
         ('openstax-finance-2e', 119): ('every table row of equal width', equal_rows),
         ('openstax-finance-2e', 387): ("no text read from the opener's photo", no_photo_text),
         ('openstax-accounting', 305): ('eleven T-accounts as eleven tables', t_accounts_as_tables),
         ('openstax-accounting', 524): ('three journal boxes read', journal_boxes_read),
         ('openstax-accounting', 969): ('accumulated depletion 655', index_number),
         ('openstax-accounting', 69): ('the table title kept', table_title)}
WALK = [place for place in KNOWN if place != ('openstax-accounting', 69)]


def served_keys() -> dict:
    """The reading each free page serves today, as the export names it: page/1's side of the comparison."""
    data = json.loads(EXPORT.read_text(encoding='utf-8'))
    rows = data['pages'] if isinstance(data, dict) else data
    return {(row['file'], row['pdf_page']): row['reading_key'] for row in rows if row.get('reading_key')}


def _reading(store, record: dict) -> mini_pilot.Reading:
    text = store.reading_text(record['reading_key']) or ''
    return mini_pilot.Reading(record, text, parse(text, record['form'], mini_pilot.expected_of(record)))


def _judged(history: dict, key: str) -> str | None:
    tried = [item for item in history.get(key, []) if item['version'] == JUDGE and not item['again']]
    return tried[-1]['outcome'] if tried else None


def _gold(rows: list) -> dict:
    scored = [row for row in rows if row.score]
    return {'valid': sum(row.page.valid for row in rows), 'pages': len(rows), 'gold_pages': len(scored),
            'formulas_exact': sum(row.score.formula['exact'] for row in scored), 'formulas': sum(row.score.formula['gold'] for row in scored),
            'cells_exact': sum(row.score.table['exact'] for row in scored if row.score.table),
            'cells': sum(row.score.table['cells'] for row in scored if row.score.table),
            'clean': sum(mini_pilot._gold_clean(row) for row in scored)}


def report(args) -> dict:
    sys.stdout.reconfigure(encoding='utf-8')
    store = open_store('free')
    served = served_keys()
    newest = check_run.latest_per_page(vision_batches.readings_of(CELLS, store),
                                       valid=lambda record: vision_batches.current_class(record, store) == 'ok')
    pairs = []
    for record in newest:
        before = served.get((record['file'], record['pdf_page']))
        if before and store.reading(before):
            pairs.append((_reading(store, store.reading(before)), _reading(store, record)))
    mini_pilot.measure([row for pair in pairs for row in pair])
    history = check_run.judgements_by_target(store)
    gold_pages = {(page['file'], page['pdf_page']) for page in reading_cells.pages_for(reading_cells.READER_PROTOTYPE_CELLS['P2-MP-SM'])}
    on_gold = [pair for pair in pairs if (pair[0].record['file'], pair[0].record['pdf_page']) in gold_pages]
    rows = []
    for one, two in sorted(pairs, key=lambda pair: (pair[0].record['work'], pair[0].record['pdf_page'])):
        place = (one.record['work'], one.record['pdf_page'])
        row = {'page': f'{place[0]}:p{place[1]}', 'page_1': one.key, 'page_2': two.key,
               'valid': [one.page.valid, two.page.valid], 'judge_4': [_judged(history, one.key), _judged(history, two.key)],
               'cost_usd': two.record.get('cost_usd')}
        if one.score and two.score:
            row['gold'] = [{'formulas': f"{side.score.formula['exact']}/{side.score.formula['gold']}",
                            'cells': f"{side.score.table['exact']}/{side.score.table['cells']}" if side.score.table else None,
                            'clean': mini_pilot._gold_clean(side)} for side in (one, two)]
        if place in KNOWN:
            what, check = KNOWN[place]
            row['known'] = {'what': what, 'page_1': check(one.page), 'page_2': check(two.page)}
        rows.append(row)
    gold = {'page_1': _gold([one for one, _ in on_gold]), 'page_2': _gold([two for _, two in on_gold])}
    walk = [row for row in rows if 'known' in row and row['page'] != 'openstax-accounting:p69']
    fixed = sum(row['known']['page_2'][0] for row in walk)
    one_gold, two_gold = gold['page_1'], gold['page_2']
    gates = {'gold: every page valid': two_gold['valid'] == two_gold['pages'] == 20,
             'gold: formulas exact no fewer': two_gold['formulas_exact'] >= one_gold['formulas_exact'],
             'gold: table cells exact no fewer': two_gold['cells_exact'] >= one_gold['cells_exact'],
             'gold: clean pages no fewer': two_gold['clean'] >= one_gold['clean'],
             'walk: at least four of six fixed': fixed >= 4,
             'p. 69 keeps its table title': any(row['page'] == 'openstax-accounting:p69' and row['known']['page_2'][0] for row in rows)}
    result = {'cells': CELLS, 'judge': JUDGE, 'rows': rows, 'gold': gold, 'walk_fixed': f'{fixed} of {len(walk)}', 'gates': gates,
              'cost_usd': round(sum(row['cost_usd'] or 0 for row in rows), 4)}
    store.write_report(REPORT, result)
    print(f"gold, page/1 -> page/2: {json.dumps(gold)}")
    for row in rows:
        if 'known' in row:
            known = row['known']
            print(f"{row['page']:28} {known['what']:38} page/1 {'fixed' if known['page_1'][0] else 'wrong':5} -> page/2 "
                  f"{'fixed' if known['page_2'][0] else 'wrong':5} | {known['page_2'][1][:110]}")
    print(f"walk: {result['walk_fixed']} fixed; judge/4 on page/2: {dict(Counter(row['judge_4'][1] for row in rows))}")
    for gate, held in gates.items():
        print(f"{'HOLDS' if held else 'FAILS'}  {gate}")
    print(f"cost {result['cost_usd']} USD")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('report', help='page/2 against the served page/1 readings, by gold, the walk and judge/4').set_defaults(run=report)
    return parser


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    args.run(args)


if __name__ == '__main__':
    main()
