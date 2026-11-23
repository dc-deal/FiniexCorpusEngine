"""Source code as a source (issue #12; the operator's 1.a to 4.a, 23 Nov 2026): a work's companion code served file by file.

A code work is its own work beside the book it accompanies (`companion_of`). The local licensed catalog describes it with
`format: "code"`, its folder under the licensed archive (`file`) and its programming language (`code_language`).

- **One source file is one page.** Its label is its path inside the work's folder (`Indicators/Fast Average.txt`), its
  section the folder, its lines the whole file. A citation names the file and its lines.
- **The text is the file as the publisher gave it,** decoded and never rewritten.
- **The ranking sees more words than the quote shows:** the text, and each identifier split at its camelCase
  (`MarketPosition` adds `market position`), since the port's tokenizer splits only snake_case and would leave a code
  identifier as one rare word. The prose ranking is untouched: only a code page carries the extra words.
- **A code page is never left out of the ranking** for being short or full of digits (`page_index.is_structural`): a
  function of five lines is a whole unit of code.

Licensed code is read and cited, never copied into another codebase; the tool descriptions say so to every client.
"""

import json
import re
from pathlib import Path

from backend.configuration import data_paths
from backend.search import page_index

CODE_ROUTE = 'source code, as the publisher gave it'
SUFFIXES = frozenset({'.txt', '.el', '.els', '.py', '.mq4', '.mq5', '.mqh', '.pine', '.cs', '.r', '.m'})
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
CAMEL = re.compile(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])')
UNIT_KINDS = {'functions': 'function', 'indicators': 'indicator', 'strategies': 'strategy'}  # a folder's name, the unit it holds


def decode(raw: bytes) -> str:
    """A source file's text: UTF-8 where it is, else Windows-1252, the platform's own encoding; NUL dropped, as on every
    route (the index database cannot store it)."""
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252', errors='replace')
    return text.replace('\x00', '').replace('\r\n', '\n').replace('\r', '\n')


def index_words(text: str) -> str:
    """The words the ranking sees: the text, then each camelCase identifier's parts, once each, lower case."""
    parts = []
    for name in dict.fromkeys(IDENTIFIER.findall(text)):
        split = [piece for piece in CAMEL.split(name) if piece]
        if len(split) > 1:
            parts.append(' '.join(piece.lower() for piece in split))
    return text if not parts else text + '\n' + '\n'.join(parts)


def unit_kind(label: str) -> str | None:
    """What a file holds by the folder it stands in: a function, an indicator, a strategy; None where the folder says not."""
    folder = label.split('/', 1)[0].lower() if '/' in label else ''
    return UNIT_KINDS.get(folder)


def licensed_code(catalog: Path | None = None, archive: Path | None = None) -> dict[str, tuple[Path, dict]]:
    """Work key -> (folder, catalog entry) of each code work the local licensed catalog describes, keyed by its folder's
    name as a new PDF is by its stem; empty on a machine without the catalog or the folder."""
    catalog = catalog or data_paths.LICENSED_CATALOG
    archive = archive or data_paths.LICENSED_ARCHIVE
    if not catalog.exists():
        return {}
    found = {}
    for entry in json.loads(catalog.read_text(encoding='utf-8')).get('sources', []):
        if entry.get('format') != 'code' or not entry.get('file'):
            continue
        folder = archive / entry['file']
        if folder.is_dir():
            found[folder.name] = (folder, entry)
    return found


def source_files(folder: Path) -> list[Path]:
    """The work's source files in a stable order: by folder, then by name."""
    return sorted((path for path in folder.rglob('*') if path.is_file() and path.suffix.lower() in SUFFIXES),
                  key=lambda path: path.relative_to(folder).as_posix().lower())


def code_pages(key: str, folder: Path, knowledge_base: str = 'licensed', prefix: str | None = None) -> list[page_index.Page]:
    """Each source file of a code work as one page, every page in the ranking. `prefix`: the mark a publisher puts before
    each unit's name (the catalog's `name_prefix`), split off so the name itself is a word too."""
    pages = []
    for path in source_files(folder):
        label = path.relative_to(folder).as_posix()
        text = decode(path.read_bytes())
        if not text.strip():
            continue
        pages.append(page_index.Page(key, label, 1, text, data_paths.stored(path), section=label.split('/', 1)[0] if '/' in label
                                     else None, line_end=text.count('\n') + 1, knowledge_base=knowledge_base, route=CODE_ROUTE,
                                     index_text=index_words(text) + '\n' + name_words(path.stem), searchable=True))
    return pages


def name_words(stem: str, prefix: str | None = None) -> str:
    """A file's name as words the ranking sees, since a unit is often asked for by its name: with the prefix `XYZ`,
    `XYZFAST` gives `xyzfast fast`; `XYZ Fast Average (I)` gives `xyz fast average i`; `FastAverage` adds `fast
    average`."""
    words = []
    for piece in filter(None, re.split(r'[\s_()\-.]+', stem)):
        rest = piece[len(prefix):] if prefix and piece.startswith(prefix) and len(piece) > len(prefix) else piece
        split = [part for part in CAMEL.split(rest) if part]
        words += [piece.lower(), rest.lower(), *(part.lower() for part in split if len(split) > 1)]
    return ' '.join(dict.fromkeys(words))


def contents(pages: list[page_index.Page]) -> list[dict]:
    """A code work's contents: each folder, then its files, each opening its page."""
    entries, folder = [], object()
    for page in pages:
        current = page.page.split('/', 1)[0] if '/' in page.page else None
        if current != folder and current is not None:
            entries.append({'level': 1, 'title': current, 'page': None})
        folder = current
        entries.append({'level': 2 if current is not None else 1, 'title': Path(page.page).stem, 'page': page.page})
    return entries
