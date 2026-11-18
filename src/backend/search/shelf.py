"""Every work on the shelf of both knowledge bases, and how far it is converted (decision 129.a, the operator, 2026-11-08).

One row per work: what the search serves of it, by route, counted from the very pages the search server builds
(`search_server.knowledge_bases`), so the shelf and the server can never disagree; beside that, what the cascade planned
for the reader, how many readings passed and why the others did not, why a passed reading is not served, and the files the
server does not serve at all, with the reason. Written into each knowledge base's store as a report, never into the
repository, since the licensed rows name private works. The diagnostics frontend shows it and computes nothing.

    python -m backend.search.shelf                  # both knowledge bases; about a minute, it builds every page
    python -m backend.search.shelf --public-only    # the free knowledge base alone
    python -m backend.search.shelf --markdown FILE  # also the table for a person, between the markers in FILE
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from backend.configuration import data_paths
from backend.conversion.store.served_readings import text_layer_why

SHELF = 'shelf.json'  # in each knowledge base's store reports
REASONS = ('blocked', 'refused', 'malformed', 'no_page', 'issue', 'stopped')
NOTHING_TO_QUOTE = 'nothing to quote on the page (an index, a picture)'
NO_NUMBERS = 'the legacy text has no PDF page numbers, so its readings cannot be matched page by page'
BESIDE_LEGACY = 'a stand-in file beside the legacy text of its work, which stands'
HELD = 'held back by the provenance list (send: false): never sent to a provider'
NO_ROUTE = 'no legacy text, and no route for this format yet'
START, END, HISTORY = '<!-- shelf:start -->', '<!-- shelf:end -->', '<!-- shelf:history -->'


def reading_counts(rows: dict[int, dict]) -> dict:
    """A file's readings: how many pages were read, how many passed, and why the others did not."""
    why = Counter(text_layer_why(row) for row in rows.values())
    return {'read': len(rows), 'passed': why[None], 'not_passed': {reason: why[reason] for reason in REASONS if why[reason]}}


def served_counts(pages: list) -> dict:
    from backend.search.search_server import route_kind

    return {'pages': len(pages), 'searchable': sum(page.searchable for page in pages),
            'from_readings': sum(1 for page in pages if page.reading_key),
            'by_route': dict(sorted(Counter(route_kind(page.route) for page in pages).items()))}


def page_count(path: Path) -> int | None:
    import pymupdf

    if path.suffix.lower() != '.pdf' or not path.exists():
        return None
    with pymupdf.open(path) as document:
        return document.page_count


def unplaced_reasons(rows: dict[int, dict], served: list, quoted: dict[int, str] | None, why: str | None) -> dict[str, int]:
    """Why passed readings are not served: the reason the whole file's readings cannot be placed, else per page; a count left
    unexplained is kept as such, so a gap between the shelf and the server shows instead of hiding."""
    passed = [number for number, row in rows.items() if text_layer_why(row) is None]
    placed = {int(page.pdf) for page in served if page.reading_key and page.pdf}
    left = [number for number in passed if number not in placed]
    if not left:
        return {}
    if why is not None:
        return {why: len(left)}
    empty = sum(1 for number in left if quoted is not None and not quoted.get(number, '').strip())
    reasons = {NOTHING_TO_QUOTE: empty, 'unexplained': len(left) - empty}
    return {reason: count for reason, count in reasons.items() if count}


def row_of(knowledge_base: str, work: str | None, title: str, source_id: str, file: str | None, file_format: str,
           pages: int | None, planned: int | None, rows: dict[int, dict], served: list, unplaced: dict[str, int],
           held: str | None = None, not_served: str | None = None) -> dict:
    counts = reading_counts(rows)
    return {'knowledge_base': knowledge_base, 'work': work, 'title': title, 'source_id': source_id, 'file': file,
            'format': file_format, 'pages': pages, 'planned': planned, **counts,
            'share_passed': round(counts['passed'] / planned, 4) if planned else None,
            'served': served_counts(served), 'unplaced': unplaced, 'held': held, 'not_served': not_served}


def free_rows(pages: list, works: dict) -> list[dict]:
    """The free works: each PDF read page by page (every page planned), each HTML source by section."""
    from backend.conversion.store import reading_export
    from backend.search import search_server

    catalog = json.loads(search_server.CATALOG.read_text(encoding='utf-8'))['sources']
    keys = search_server.free_work_keys()
    rows = search_server.export_rows_by_file(search_server.EXPORT)
    by_work = defaultdict(list)
    for page in pages:
        by_work[page.work].append(page)
    out = []
    for source in catalog:
        path = data_paths.locate(source['files'][0]['path'])
        if source.get('format') == 'pdf':
            key, own = keys.get(path.name, source['id']), rows.get(path.name, {})
            quoted = reading_export.quoted_pages('free', path.name) if own and path.exists() else None
            out.append(row_of('free', key if key in works else None, source['title'], source['id'], path.name, 'pdf',
                              page_count(path), len(own) or None, own, by_work.get(key, []),
                              unplaced_reasons(own, by_work.get(key, []), quoted, None)))
        else:
            key = source['id']
            out.append(row_of('free', key if key in works else None, source['title'], source['id'], None,
                              source.get('format', 'html'), None, None, {}, by_work.get(key, []), {}))
    return out


def licensed_rows(pages: list, works: dict) -> list[dict]:
    """The licensed works: each served work with its file in the archive, and every archive file no work serves."""
    from backend.conversion.reading import reading_cells, rollout
    from backend.conversion.store import reading_export
    from backend.search import search_server

    keys = search_server.legacy_keys()
    rows = search_server.export_rows_by_file(search_server.LICENSED_EXPORT)
    plan_path = rollout.FOLDER / 'plan.json'
    planned = Counter(page['file'] for page in json.loads(plan_path.read_text(encoding='utf-8'))['order']) if plan_path.exists() else Counter()
    archive = {path.name: path for path in sorted(search_server.LICENSED_ARCHIVE.glob('*')) if path.suffix.lower() in ('.pdf', '.epub')}
    new = search_server.new_licensed_pdfs(keys)
    standing_in = search_server.stand_ins(keys)  # a stand-in serving its work whole (126.a)
    by_work = defaultdict(list)
    for page in pages:
        by_work[page.work].append(page)
    out, used = [], set()

    def file_row(key: str | None, file: str, served: list, why: str | None = None, held: str | None = None,
                 not_served: str | None = None) -> dict:
        path, own = archive[file], rows.get(file, {})
        quoted = reading_export.quoted_pages('licensed', file) if own and why is None else None
        used.add(file)
        return row_of('licensed', key, Path(file).stem, Path(file).stem, file, path.suffix.lower().lstrip('.'), page_count(path),
                      planned.get(file) or None, own, served, unplaced_reasons(own, served, quoted, why), held, not_served)

    for key in sorted(works):
        served = by_work.get(key, [])
        if key in new or key in standing_in:
            out.append(file_row(key, (new.get(key) or standing_in[key]).name, served))
            continue
        slug = keys.get(key, key)
        own = [name for name in (f'{slug}.pdf', f'{slug}.epub') if name in archive]
        suffix = search_server.stand_in_rule()[0]
        alternates = [name for name in ((f'{slug}{suffix}.pdf', f'{slug}{suffix}.epub') if suffix else ()) if name in archive]
        numbered = any(page.pdf for page in served if not page.reading_key)
        if own:
            file = own[0]
            held = None if reading_cells.may_send(file) else HELD
            why = None if numbered or not rows.get(file) else NO_NUMBERS
            out.append(file_row(key, file, served, why, held))
        else:
            out.append(row_of('licensed', key, slug, slug, None, 'legacy markdown', None, None, {}, served, {}))
        for file in alternates:  # read, perhaps, but its work's legacy text stands (or the file is held)
            held = None if reading_cells.may_send(file) else HELD
            out.append(file_row(None, file, [], BESIDE_LEGACY, held, BESIDE_LEGACY))
    for file in sorted(set(archive) - used):  # a file no work serves: held back, or an EPUB with no legacy text yet
        held = HELD if not reading_cells.may_send(file) else None
        out.append(file_row(None, file, [], held=held, not_served=held or NO_ROUTE))
    return out


def build(public_only: bool = False) -> dict[str, dict]:
    """The shelf of each knowledge base the server gives out, from the pages it builds."""
    from backend.search import search_server

    bases = search_server.knowledge_bases(public_only)
    built = datetime.now(UTC).isoformat(timespec='seconds')
    shelves = {}
    for name, (pages, works) in bases.items():
        rows = free_rows(pages, works) if name == 'free' else licensed_rows(pages, works)
        shelves[name] = {'about': 'Every work of this knowledge base and how far it is converted (decision 129.a). Written by '
                                  'python -m backend.search.shelf; do not edit by hand.',
                         'knowledge_base': name, 'built_at': built, 'export_sha256': export_sha256(name), 'works': rows,
                         'totals': totals(rows)}
    return shelves


def export_sha256(knowledge_base: str) -> str | None:
    """The sha256 of the export index the shelf was built from, so a view can tell a shelf of another export from its own
    (asked by line 2, 2026-11-09: an uncommitted free export and a committed one disagreed for a morning). None: no export."""
    import hashlib

    from backend.search import search_server

    index = (search_server.EXPORT if knowledge_base == 'free' else search_server.LICENSED_EXPORT) / 'index.json'
    return hashlib.sha256(index.read_bytes()).hexdigest() if index.exists() else None


def totals(rows: list[dict]) -> dict:
    total = Counter()
    for row in rows:
        total['works'] += 1
        total['planned'] += row['planned'] or 0
        total['read'] += row['read']
        total['passed'] += row['passed']
        total['served'] += row['served']['pages']
        total['served_from_readings'] += row['served']['from_readings']
        for reason, count in row['not_passed'].items():
            total[reason] += count
        total['unplaced'] += sum(row['unplaced'].values())
    return dict(total)


def write(shelves: dict[str, dict]) -> list[Path]:
    from backend.conversion.store.reading_store import open_store

    return [open_store(name).write_report(SHELF, shelf) for name, shelf in shelves.items()]


def load(knowledge_base: str) -> dict | None:
    """A knowledge base's shelf as last written, or None where the command has not run on this machine."""
    from backend.conversion.store.reading_store import open_store

    path = open_store(knowledge_base).path('reports', SHELF)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def _cell(value) -> str:
    return '–' if value in (None, 0, {}) else f'{value:,}' if isinstance(value, int) else str(value)


def table(shelves: dict[str, dict]) -> str:
    """The shelf as one Markdown table for a person, with each base's totals under it."""
    lines = ['| base | work | file | pages | planned | passed | % | blocked/refused | judge issue | malformed | served | '
             'from readings | note |', '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    for name, shelf in shelves.items():
        for row in shelf['works']:
            lost = row['not_passed']
            share = f"{row['share_passed']:.0%}" if row['share_passed'] is not None else '–'
            why = '; '.join(f'{count} passed readings unused' if reason == row['not_served'] else f'{count} {reason}'
                            for reason, count in row['unplaced'].items())
            why = '; '.join(filter(None, [row['held'], row['not_served'] if row['not_served'] != row['held'] else None, why]))
            lines.append(f"| {name} | {row['work'] or '–'} | {row['file'] or row['format']} | {_cell(row['pages'])} | "
                         f"{_cell(row['planned'])} | {_cell(row['passed'])} | {share} | "
                         f"{_cell(lost.get('blocked', 0) + lost.get('refused', 0))} | "
                         f"{_cell(lost.get('issue', 0) + lost.get('stopped', 0))} | "
                         f"{_cell(lost.get('malformed', 0) + lost.get('no_page', 0))} | {_cell(row['served']['pages'])} | "
                         f"{_cell(row['served']['from_readings'])} | {why or '–'} |")
    for name, shelf in shelves.items():
        total = shelf['totals']
        lines += ['', f"**{name}, built {shelf['built_at']}:** {total['works']} works, {total.get('planned', 0):,} pages planned, "
                      f"{total.get('passed', 0):,} passed, {total.get('served', 0):,} served "
                      f"({total.get('served_from_readings', 0):,} from readings), "
                      f"{total.get('blocked', 0) + total.get('refused', 0):,} blocked or refused, "
                      f"{total.get('issue', 0) + total.get('stopped', 0):,} judge issues, "
                      f"{total.get('malformed', 0) + total.get('no_page', 0):,} malformed, "
                      f"{total.get('unplaced', 0):,} passed but not served."]
    return '\n'.join(lines)


def into_markdown(path: Path, shelves: dict[str, dict], milestone: str | None = None) -> None:
    """Put the table between the markers of a person's file, everything else in it kept; with a milestone, one line more in
    the history under its marker. A file without the markers gets them at its end."""
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    block = f'{START}\n{table(shelves)}\n{END}'
    if START in text and END in text:
        text = text[:text.index(START)] + block + text[text.index(END) + len(END):]
    else:
        text = text.rstrip('\n') + ('\n\n' if text else '') + block + '\n'
    if milestone:
        total = Counter()
        for shelf in shelves.values():
            total.update(shelf['totals'])
        line = (f"| {datetime.now(UTC).date().isoformat()} | {milestone} | {total['planned']:,} | {total['passed']:,} | "
                f"{total['served_from_readings']:,} | {total['blocked'] + total['refused']:,} | "
                f"{total['issue'] + total['stopped']:,} | {total['malformed'] + total['no_page']:,} |")
        if HISTORY not in text:
            text = text.rstrip('\n') + f'\n\n## History\n\n{HISTORY}\n'
        head, tail = text.split(HISTORY, 1)
        text = head + HISTORY + tail.rstrip('\n') + '\n' + line + '\n'
    path.write_bytes(text.encode('utf-8'))


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--public-only', action='store_true', help='the free knowledge base alone')
    parser.add_argument('--markdown', type=Path, help='a Markdown file whose shelf block is replaced by the table')
    parser.add_argument('--milestone', help='with --markdown: add a line to the history, named this')
    args = parser.parse_args()
    shelves = build(args.public_only)
    for path in write(shelves):
        print(f'written {path}')
    if args.markdown:
        into_markdown(args.markdown, shelves, args.milestone)
        print(f'table written into {args.markdown}')
    for name, shelf in shelves.items():
        print(f"{name}: {json.dumps(shelf['totals'])}")


if __name__ == '__main__':
    main()
