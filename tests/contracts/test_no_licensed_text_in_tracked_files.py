"""No tracked file holds a passage of the licensed text: the check before every push (the operator, 18 Nov), kept as a test.

Every tracked text file is cut into 8-word shingles; the licensed text on this machine (the legacy Markdown and the page
readings, their page format stripped) is streamed once, and the test fails where a file shares a run of consecutive
shingles long enough to be a copied passage. Short shared runs are expected and harmless: a citation of a free work the
collection also holds, a licence formula, the page format's own words. Measured on the first public commit: the longest
run anywhere was 5 shingles (12 words). A copied sentence of 17 words or more fails. On a machine without the licensed
text, which is every clone, the test is skipped. It reports files and run lengths, never the text.
"""

import re
import subprocess
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


def longest_shared_runs(files: dict[str, list[int]], licensed: list[Path]) -> dict[str, int]:
    """Per file, the longest run of its consecutive shingles that the licensed text holds too."""
    wanted = {shingle for sequence in files.values() for shingle in sequence}
    shared = set()
    for path in licensed:
        shared.update(shingle for shingle in shingles(book_text(path)) if shingle in wanted)
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


def test_no_tracked_file_holds_a_passage_of_the_licensed_text():
    licensed = [path for folder in LICENSED if folder.is_dir() for path in folder.rglob('*.md')]
    if not licensed:
        pytest.skip('no licensed text on this machine')
    files = {name: shingles((ROOT / name).read_text(encoding='utf-8', errors='replace')) for name in tracked_text_files()}
    runs = longest_shared_runs(files, licensed)
    copied = {name: run for name, run in runs.items() if run > LONGEST_HARMLESS_RUN}
    assert copied == {}, f'tracked files sharing a run of consecutive shingles with the licensed text: {copied}'
