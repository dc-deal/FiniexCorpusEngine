"""The coverage gate of the keyword search: every work must be found by a word run from its own middle third.

Ported from the predecessor's gate, which a collection had to pass before its old search could be retired: a probe of eight
uncommon words from the most distinctive line in the middle third of a work, and the work among the first six hits. Presence,
not rank 1: near-duplicates are correct hits (a standard and its handbook, a book that reuses its slides). The gate asks the
index directly instead of parsing a command's printed output.

    python -m backend.search.coverage_gate --folder _work/licensed/legacy_markdown --keys _work/licensed/legacy_markdown/keys.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

from backend.search import page_index

COMMON = set('the of and a to in is that for as we it with be this are on by an or not from '
             'at can will have has was were they their there which when what how'.split())
WORD = re.compile(r"[A-Za-z][A-Za-z'-]{3,}")
SKIP_LINE = ('<!--', '!', '|', '#', '>')
HITS = 6


def build_probe(text: str) -> str | None:
    """A distinctive word run from the middle third of a work, or None when no line qualifies."""
    lines = [re.sub(r'\s+', ' ', line).strip() for line in text.split('\n')]
    lines = [line for line in lines if 60 < len(line) < 400 and not line.startswith(SKIP_LINE)]
    if not lines:
        return None
    middle = lines[len(lines) // 3: 2 * len(lines) // 3][:400]
    best, best_score = None, -1
    for line in middle:
        rare = [word for word in WORD.findall(line) if word.lower() not in COMMON]
        if len(rare) < 6:
            continue
        score = sum(len(word) for word in rare[:8])
        if score > best_score:
            best_score, best = score, ' '.join(rare[:8])
    return best


def run_gate(folder: Path, keys: dict) -> dict:
    """Per work its probe's rank among the first six hits (0 when absent), and the totals."""
    index = page_index.PageIndex(page_index.load_works(folder, keys))
    by_slug = {slug: key for key, slug in keys.items()}
    rows = {}
    for path in sorted(folder.glob('*.md')):
        work = by_slug.get(path.stem, path.stem)
        probe = build_probe(path.read_text(encoding='utf-8'))
        if probe is None:
            rows[work] = {'rank': None, 'probe_words': 0}
            continue
        found = [page.work for _, page in index.search(probe, HITS)]
        rows[work] = {'rank': found.index(work) + 1 if work in found else 0, 'probe_words': len(probe.split())}
    ranked = [row['rank'] for row in rows.values() if row['rank'] is not None]
    return {'works': len(rows), 'reached': sum(1 for rank in ranked if rank), 'rank_1': sum(1 for rank in ranked if rank == 1),
            'no_probe': sum(1 for row in rows.values() if row['rank'] is None), 'rows': rows}


def run_gate_pages(pages: list[page_index.Page]) -> dict:
    """The same gate over pages that are not one Markdown file per work (the free works: PDF pages and HTML sections): a work's
    probe comes from its pages joined in order, and the index is built from exactly these pages."""
    index = page_index.PageIndex(pages)
    rows = {}
    for work in sorted({page.work for page in pages}):
        probe = build_probe('\n'.join(page.text for page in pages if page.work == work))
        if probe is None:
            rows[work] = {'rank': None, 'probe_words': 0}
            continue
        found = [page.work for _, page in index.search(probe, HITS)]
        rows[work] = {'rank': found.index(work) + 1 if work in found else 0, 'probe_words': len(probe.split())}
    ranked = [row['rank'] for row in rows.values() if row['rank'] is not None]
    return {'works': len(rows), 'reached': sum(1 for rank in ranked if rank), 'rank_1': sum(1 for rank in ranked if rank == 1),
            'no_probe': sum(1 for row in rows.values() if row['rank'] is None), 'rows': rows}


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--folder', type=Path, help='a folder of Markdown works with page markers')
    source.add_argument('--free', action='store_true', help="the free knowledge base as the search server builds it")
    parser.add_argument('--keys', type=Path)
    args = parser.parse_args()
    if args.free:
        from backend.search import search_server

        result = run_gate_pages(search_server.free_pages()[0])
    else:
        keys = json.loads(args.keys.read_text(encoding='utf-8'))['keys'] if args.keys else {}
        result = run_gate(args.folder, keys)
    missed = [work for work, row in result['rows'].items() if row['rank'] == 0]
    print(f"reached {result['reached']} of {result['works']} within the first {HITS}, {result['rank_1']} at rank 1, "
          f"{result['no_probe']} without a probe; missed: {missed}")
    if missed or result['no_probe']:
        sys.exit(1)  # as the predecessor's gate: a missed work fails it


if __name__ == '__main__':
    main()
