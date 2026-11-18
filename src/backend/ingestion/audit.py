"""Check that the indexed text is clean: count known noise, and sample chunks for a human to read.

Two checks, because they find different things. The counts find noise that is already known,
such as a running footer that slipped through or a print-edition page marker. The sample finds
noise nobody has thought of yet. It is written to a git-ignored file for reading. The finance
book being read twice, the worst defect of phase 2, was found by looking at a number, not by a
rule written in advance.

Run from the repository root, after `python -m backend.ingestion.build`:
    python -m backend.ingestion.audit                 # counts, and a sample of 5 chunks per source
    python -m backend.ingestion.audit --sample 10
"""

import argparse
import json
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backend.configuration import data_paths

DATABASE = data_paths.INDEX / 'knowledge.sqlite3'
SAMPLE_FILE = data_paths.LOGS / 'audit_sample.md'

# Noise that phase 1 and 2 removed. Any occurrence in the index is a defect. OpenStax's own
# preface quotes the attribution line in its licence text, which is content and allowed there.
MUST_BE_ZERO = {
    'openstax attribution line': re.compile(r'Access for free at openstax\.org'),
    'running footer (page no. + chapter)': re.compile(r'^\d{1,4}\s{3,}\d+\s•\s|\s•\s.*\S\s{3,}\d{1,4}$', re.M),
    'print-edition page marker [Pg n]': re.compile(r'\[Pg\s*\d+\]'),
    'replacement character': re.compile('�'),
    # The wrapper Wikipedia puts around every formula's LaTeX, '{\displaystyle ...}', must be gone.
    # \displaystyle *inside* a formula is LaTeX the article itself uses (found 2026-09-29 in
    # Moving_average: 'x \mapsto \displaystyle {\frac ...}') and is content.
    'MathML leftovers (displaystyle)': re.compile(r'\{\\displaystyle'),
    'Project Gutenberg licence': re.compile(r'Project Gutenberg License|START OF THE PROJECT GUTENBERG'),
}

# Signals worth knowing, but legitimate in some amount: a footnote in a textbook cites a URL, a
# table cell holds a lone number. They are counted, not pinned.
SIGNALS = {
    'URL': re.compile(r'https?://'),
    'footnote marker [n]': re.compile(r'\[\d{1,3}\]'),
    'line of digits only': re.compile(r'^\s*\d{1,4}\s*$', re.M),
    'line-end hyphen break': re.compile(r'[a-z]-\n[a-z]'),
    'table row (Markdown)': re.compile(r'^\|.*\|$', re.M),
}
SHORT_CHUNK = 100          # characters; a chunk this short carries little meaning
REPEATED_LINE_MIN = 25     # characters; shorter lines repeat naturally ("Solution", "Example")
REPEATED_IN_CHUNKS = 15    # a line in this many chunks of one source may be leftover furniture


def load_chunks(database: Path) -> list[dict]:
    connection = sqlite3.connect(database)
    rows = connection.execute('SELECT id, source_id, text, metadata FROM chunks ORDER BY id').fetchall()
    return [{'id': i, 'source_id': s, 'text': t, 'metadata': json.loads(m)} for i, s, t, m in rows]


def is_allowed(name: str, chunk: dict) -> bool:
    """The one known legitimate occurrence of must-be-zero noise."""
    return name == 'openstax attribution line' and 'Preface' in chunk['metadata'].get('heading_path', '')


def count_noise(chunks: list[dict]) -> dict[str, dict[str, int]]:
    """Occurrences of every pattern, per source.

    Returns:
        {source_id: {pattern name: count}}, plus 'short chunk' and 'chunks' per source.
    """
    counts: dict[str, dict[str, int]] = defaultdict(Counter)
    for chunk in chunks:
        per_source = counts[chunk['source_id']]
        per_source['chunks'] += 1
        for name, pattern in {**MUST_BE_ZERO, **SIGNALS}.items():
            allowed = name in MUST_BE_ZERO and is_allowed(name, chunk)
            per_source[name] += 0 if allowed else len(pattern.findall(chunk['text']))
        if len(chunk['text']) < SHORT_CHUNK:
            per_source['short chunk (<100 chars)'] += 1
    return {source: dict(values) for source, values in counts.items()}


def repeated_lines(chunks: list[dict]) -> dict[str, list[tuple[int, str]]]:
    """Long lines that recur across many chunks of one source: possible leftover furniture.

    Overlapping chunks share up to 200 characters, so a line counts once per chunk and only
    lines seen in many chunks are reported.
    """
    per_source: dict[str, Counter] = defaultdict(Counter)
    for chunk in chunks:
        lines = {line.strip() for line in chunk['text'].splitlines() if len(line.strip()) >= REPEATED_LINE_MIN}
        per_source[chunk['source_id']].update(lines)
    return {source: [(n, line) for line, n in counter.most_common(5) if n >= REPEATED_IN_CHUNKS]
            for source, counter in per_source.items()}


def defects(counts: dict[str, dict[str, int]]) -> list[tuple[str, str, int]]:
    return [(source, name, values.get(name, 0)) for source, values in counts.items()
            for name in MUST_BE_ZERO if values.get(name, 0)]


def write_sample(chunks: list[dict], per_source: int, seed: int, path: Path) -> None:
    """A reproducible random sample of chunks per source, with their citation, for reading."""
    by_source = defaultdict(list)
    for chunk in chunks:
        by_source[chunk['source_id']].append(chunk)
    rng = random.Random(seed)
    lines = [f'# Audit sample: {per_source} random chunks per source (seed {seed})', '',
             f'Written {datetime.now(timezone.utc).isoformat(timespec="seconds")} by `python -m backend.ingestion.audit`.',
             'Git-ignored. Read it for noise the counts do not know about yet.', '']
    for source, items in by_source.items():
        lines += [f'## {source}', '']
        for chunk in rng.sample(items, min(per_source, len(items))):
            m = chunk['metadata']
            where = (f"p. {m.get('printed_page')} (PDF p. {m.get('pdf_page')})" if 'pdf_page' in m
                     else m.get('url', ''))
            lines += [f"### `{chunk['id']}` · {m.get('heading_path', '')} · {where}", '', '```text',
                      chunk['text'], '```', '']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines), encoding='utf-8', newline='\n')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--sample', type=int, default=5, help='chunks per source to write for reading')
    parser.add_argument('--seed', type=int, default=20260928)
    args = parser.parse_args(argv)
    if not DATABASE.exists():
        print('no index yet. Run: python -m backend.ingestion.build', file=sys.stderr)
        return 2

    chunks = load_chunks(DATABASE)
    counts = count_noise(chunks)
    columns = ['chunks'] + list(MUST_BE_ZERO) + list(SIGNALS) + ['short chunk (<100 chars)']
    print(f'{len(chunks):,} chunks from {len(counts)} sources\n')
    for name in columns:
        marker = '  must be 0' if name in MUST_BE_ZERO else ''
        print(f'{name:38}' + ''.join(f'{counts[s].get(name, 0):>9,}' for s in counts) + marker)
    print(f"{'':38}" + ''.join(f'{s[:8]:>9}' for s in counts))

    print('\nlong lines repeated across many chunks of one source:')
    found = False
    for source, items in repeated_lines(chunks).items():
        for n, line in items:
            found = True
            print(f'   {source[:30]:30} {n:>4}×  {line[:80]!r}')
    if not found:
        print('   none')

    write_sample(chunks, args.sample, args.seed, SAMPLE_FILE)
    print(f'\nsample for reading: {SAMPLE_FILE.name}')

    problems = defects(counts)
    for source, name, n in problems:
        print(f'DEFECT: {source}: {name} × {n}', file=sys.stderr)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
