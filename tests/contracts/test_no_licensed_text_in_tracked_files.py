"""No tracked file holds a passage of the licensed text: the check before every push (the operator, 18 Nov), kept as a test.

Every tracked text file is cut into 8-word shingles; the licensed text on this machine is streamed once: the legacy
Markdown and the page readings (their page format stripped), and since 24 Nov 2026 (the operator: the thorough check
before every release) also every licensed PDF's text layer as it is quoted, the EPUBs' text and the companion code. The
test fails where a file shares a run of consecutive
shingles long enough to be a copied passage. Short shared runs are expected and harmless: a citation of a free work the
collection also holds, a licence formula, the page format's own words. Measured on the first public commit: the longest
run anywhere was 5 shingles (12 words). A copied sentence of 17 words or more fails. On a machine without the licensed
text, which is every clone, the test is skipped. It reports files and run lengths, never the text.
"""

import json
import re
import subprocess
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.configuration import data_paths

ROOT = Path(__file__).resolve().parent.parent.parent
WORD = re.compile(r'[a-z0-9]+')
SHINGLE = 8
LONGEST_HARMLESS_RUN = 9  # consecutive shingles; 10 are 17 words in a row
TEXT = ('.py', '.md', '.txt', '.json', '.ts', '.vue', '.toml', '.ini', '.yml', '.yaml', '.html', '.css', '.cfg')
LICENSED = (data_paths.LICENSED_WORKING / 'legacy_markdown', data_paths.LICENSED_WORKING / 'readings')
PAGE_FORMAT = (re.compile(r'\A---\n.*?\n---\n', re.S), re.compile(r'^:::.*$', re.M), re.compile(r'<[^>]+>'))
TAG = re.compile(r'<[^>]+>')


def shingles(text: str) -> list[int]:
    words = WORD.findall(text.lower())
    return [hash(tuple(words[i:i + SHINGLE])) for i in range(len(words) - SHINGLE + 1)]


def book_text(path: Path) -> str:
    """A licensed file's words without the page format a reading adds: its front matter, its block fences, HTML tags."""
    text = path.read_text(encoding='utf-8', errors='replace')
    for pattern in PAGE_FORMAT:
        text = pattern.sub(' ', text)
    return text


def tracked_text_files() -> list[str]:
    listed = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    return [path for path in listed if path.endswith(TEXT) and '/dist/' not in path]  # dist: built from the sources


def licensed_texts(markdown: list[Path], quoted: Path | None = None, archive: Path | None = None) -> Iterator[str]:
    """Every licensed text on this machine, one at a time: the Markdown (legacy text, readings) without its page format,
    each PDF's quoted text layer, each EPUB's text without its tags, each companion code file."""
    for path in markdown:
        yield book_text(path)
    for path in sorted(quoted.glob('*.json')) if quoted is not None and quoted.is_dir() else []:
        yield ' '.join(json.loads(path.read_text(encoding='utf-8'))['pages'].values())
    if archive is not None and archive.is_dir():
        for path in sorted(archive.glob('*.epub')):
            with zipfile.ZipFile(path) as epub:
                yield ' '.join(TAG.sub(' ', epub.read(name).decode('utf-8', 'replace'))
                               for name in epub.namelist() if name.endswith(('.html', '.xhtml', '.htm')))
        for path in sorted((archive / 'code').rglob('*')) if (archive / 'code').is_dir() else []:
            if path.is_file():
                yield path.read_text(encoding='utf-8', errors='replace')


def longest_shared_runs(files: dict[str, list[int]], licensed) -> dict[str, int]:
    """Per file, the longest run of its consecutive shingles that the licensed text holds too. `licensed`: paths of
    Markdown files, or texts."""
    wanted = {shingle for sequence in files.values() for shingle in sequence}
    shared = set()
    for item in licensed:
        text = book_text(item) if isinstance(item, Path) else item
        shared.update(shingle for shingle in shingles(text) if shingle in wanted)
    runs = {}
    for name, sequence in files.items():
        best = run = 0
        for shingle in sequence:
            run = run + 1 if shingle in shared else 0
            best = max(best, run)
        runs[name] = best
    return runs


def test_a_copied_passage_is_found_and_a_short_shared_phrase_is_not(tmp_path):
    book = tmp_path / 'book.md'
    book.write_text('---\nwork: x\n---\n::: {#b01 .paragraph}\n' + ' '.join(f'word{i}' for i in range(40)) + '\n:::\n',
                    encoding='utf-8')
    copied = shingles(' '.join(f'word{i}' for i in range(5, 30)))  # 25 words in a row
    phrase = shingles('ours ' * 5 + ' '.join(f'word{i}' for i in range(10, 20)) + ' ours' * 5)  # 10 words
    runs = longest_shared_runs({'copied': copied, 'phrase': phrase, 'format': shingles('work x paragraph b01')}, [book])
    assert runs['copied'] > LONGEST_HARMLESS_RUN >= runs['phrase'] and runs['format'] == 0


def test_every_kind_of_licensed_text_is_compared(tmp_path):
    # 24 Nov 2026: until then only the Markdown was, and most new works are served from their text layer
    quoted = tmp_path / 'quoted'
    quoted.mkdir()
    (quoted / 'book.json').write_text(json.dumps({'pages': {'1': 'layer one two three four five six seven eight nine'}}),
                                      encoding='utf-8')
    archive = tmp_path / 'archive'
    (archive / 'code' / 'work').mkdir(parents=True)
    with zipfile.ZipFile(archive / 'book.epub', 'w') as epub:
        epub.writestr('ch1.xhtml', '<p>epub one two three four five six seven eight nine</p>')
    (archive / 'code' / 'work' / 'unit.txt').write_text('code one two three four five six seven eight nine', encoding='utf-8')
    texts = list(licensed_texts([], quoted, archive))
    assert len(texts) == 3 and all(len(shingles(text)) == 3 for text in texts)


def test_no_tracked_file_holds_a_passage_of_the_licensed_text():
    from backend.conversion.store.reading_store import open_store

    markdown = [path for folder in LICENSED if folder.is_dir() for path in folder.rglob('*.md')]
    if not markdown:
        pytest.skip('no licensed text on this machine')
    files = {name: shingles((ROOT / name).read_text(encoding='utf-8', errors='replace')) for name in tracked_text_files()}
    runs = longest_shared_runs(files, licensed_texts(markdown, open_store('licensed').path('reports', 'quoted'),
                                                     data_paths.LICENSED_ARCHIVE))
    copied = {name: run for name, run in runs.items() if run > LONGEST_HARMLESS_RUN}
    assert copied == {}, f'tracked files sharing a run of consecutive shingles with the licensed text: {copied}'
