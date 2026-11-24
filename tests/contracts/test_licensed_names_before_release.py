"""Before every release (the operator, 24 Nov 2026): no tracked file and no blob in the repository's history names a licensed
work, and every licensed author's surname in a tracked file is listed for a person to look at.

The two guards that run with every suite check the text (`test_no_licensed_text_in_tracked_files`) and the private names
(`test_no_private_material_in_tracked_files`) in the files as they are. This check goes wider, and runs with
`pytest -m release`:
- a licensed work's key, file stem, citation key or title (of three words or more) anywhere in a tracked text file fails;
- the same in any blob any commit ever held fails, since the repository is public with its history (263.a);
- an author's surname (six letters or more, not also an author of a free work) is printed with its file and line, never
  failing: most such words are ordinary ("trading", an indicator named after its inventor), and a person decides.
The names come from the local lists beside the archive; this file spells none of them, and a clone without the lists
skips. A hit is reported by its kind, file and line, never by the name it found.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

from backend.configuration import data_paths

pytestmark = pytest.mark.release
ROOT = Path(__file__).resolve().parent.parent.parent
TEXT = ('.py', '.md', '.txt', '.json', '.ts', '.vue', '.toml', '.ini', '.yml', '.yaml', '.html', '.css', '.cfg', '.js', '.mjs',
        '.svg', '.example', '.code-workspace', '.gitignore')
NOT_SURNAMES = {'editor', 'editors', 'edited', 'company', 'institute', 'university', 'european', 'commission'}


def git(*args: str) -> str:
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                          errors='replace').stdout


def licensed_names(catalog: list[dict], free: list[dict], keys: dict[str, str]) -> tuple[dict[str, str], set[str]]:
    """Lower-cased needle -> its kind ('key', 'stem', 'citation key', 'title'), and the authors' surnames to report."""
    names = {}
    for entry in catalog:
        for kind, value in (('key', entry.get('id') or ''), ('stem', Path(entry.get('file') or '').stem)):
            if len(value) >= 6:
                names[value.lower()] = kind
        title = (entry.get('title') or '').strip()
        if len(title.split()) >= 3:
            names[title.lower()] = 'title'
    for key, slug in keys.items():
        if len(key) >= 4:
            names.setdefault(key.lower(), 'citation key')
        names.setdefault(slug.lower(), 'stem')
    free_authors = {word.lower() for source in free for word in re.findall(r'[^\W\d_][\w\-]*', source.get('authors') or '')}
    surnames = {word.lower() for entry in catalog for word in re.findall(r'[^\W\d_][\w\-]*', entry.get('authors') or '')
                if len(word) >= 6 and word[0].isupper() and word.lower() not in free_authors | NOT_SURNAMES}
    return names, surnames


def found(text: str, needles: dict[str, re.Pattern]) -> list[tuple[str, int]]:
    """(needle, line) for each needle the text holds, as a whole word."""
    lower, hits = text.lower(), []
    for needle, pattern in needles.items():
        hits += [(needle, lower.count('\n', 0, match.start()) + 1) for match in pattern.finditer(lower)]
    return hits


def patterns(words) -> dict[str, re.Pattern]:
    return {word: re.compile(r'(?<![a-z0-9_])' + re.escape(word) + r'(?![a-z0-9_])') for word in words}


def test_a_name_is_found_as_a_whole_word_only():
    needles = patterns(['moving_average_book', 'the hidden book of trading'])
    assert found('see Moving_Average_Book here\nand The Hidden Book Of Trading', needles) == [
        ('moving_average_book', 1), ('the hidden book of trading', 2)]
    assert found('moving_average_books and xthe hidden book of trading', needles) == []
    names, surnames = licensed_names([{'id': 'a_book_writer', 'file': 'a_book_writer.pdf', 'title': 'A Book Of Things',
                                       'authors': 'Anna Writerson, Bob Sharedname'}],
                                     [{'authors': 'Cleo Sharedname'}], {'wr': 'a_book_writer'})
    assert names == {'a_book_writer': 'stem', 'a book of things': 'title'} and surnames == {'writerson'}


def local_lists() -> tuple[dict[str, str], set[str]]:
    catalog_path = data_paths.LICENSED_CATALOG
    if not catalog_path.exists():
        pytest.skip('no licensed catalog on this machine')
    keys_path = data_paths.LICENSED_WORKING / 'legacy_markdown' / 'keys.json'
    keys = json.loads(keys_path.read_text(encoding='utf-8'))['keys'] if keys_path.exists() else {}
    free = json.loads((ROOT / 'corpus' / 'catalog.json').read_text(encoding='utf-8'))['sources']
    return licensed_names(json.loads(catalog_path.read_text(encoding='utf-8'))['sources'], free, keys)


def test_no_tracked_file_names_a_licensed_work_and_every_surname_is_listed(capsys):
    names, surnames = local_lists()
    strong, people = patterns(names), patterns(surnames)
    failing, listed = [], []
    for name in git('ls-files').splitlines():
        path = ROOT / name
        if not name.endswith(TEXT) or not path.exists():
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        failing += [f'{name}:{line} ({names[needle]})' for needle, line in found(text, strong)]
        listed += [f'{name}:{line}' for _, line in found(text, people)]
    with capsys.disabled():
        print(f'\nlicensed authors\' surnames in tracked files, for a person to look at: {len(listed)}')
        for place in listed:
            print(f'  {place}')
    assert failing == [], f'tracked files naming a licensed work: {failing}'


def test_no_blob_in_the_history_names_a_licensed_work():
    names, _ = local_lists()
    strong = patterns(names)
    blobs = sorted({line.split()[0] for line in git('rev-list', '--all', '--objects').splitlines()
                    if len(line.split()) == 2 and line.split()[1].endswith(TEXT)})
    failing = [f'{blob[:10]} ({names[needle]})' for blob in blobs for needle, _ in found(git('cat-file', '-p', blob), strong)]
    assert failing == [], f'blobs in the history naming a licensed work: {failing}'
