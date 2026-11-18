"""A page's integrity, as the core's `integrity.page_state` says it, remembered by its reading file's place, modification
time and size, so a file is hashed again only when one of them changed (line 1's proposal, 10 Nov: a stat is cheap, a hash
is not). The overview asks for every page on every call: hashing all 9,600 reading files took 1.8 s with a warm disk cache
and most of the operator's 22 s first load after a start; a stat of each takes a fraction of that.

What it cannot see: a file rewritten within the same tick of the file system's clock to the same size. The core's own
`integrity` command hashes every file and stays the check of record; a page's own view asks the core directly.

Built here rather than taken from a library: `functools.lru_cache` keys by arguments and cannot tell that a file changed,
and `cachetools` would add a dependency for a dictionary keyed by a stat.
"""

import threading
from pathlib import Path

from backend.conversion.checks import integrity

# reading file -> ((modified, size, the hash the export expects), the state found)
_KNOWN: dict[Path, tuple[tuple[int, int, str | None], str]] = {}
_LOCK = threading.Lock()


def state(export: Path, row: dict) -> str:
    """The page's integrity: 'whole', 'tampered', 'missing' or 'no reading', exactly as `integrity.page_state` says it."""
    if not row.get('text_file'):
        return 'no reading'
    target = export / row['text_file']
    try:
        found = target.stat()
    except FileNotFoundError:
        return 'missing'
    key = (found.st_mtime_ns, found.st_size, row.get('text_sha256'))
    with _LOCK:
        known = _KNOWN.get(target)
    if known is not None and known[0] == key:
        return known[1]
    said = integrity.page_state(export, row)
    with _LOCK:
        _KNOWN[target] = (key, said)
    return said


def warm(exports_and_rows) -> None:
    """Hashes every reading file once, ahead of the first overview: given (export, rows) pairs."""
    for export, rows in exports_and_rows:
        for row in rows:
            state(export, row)


def forget() -> None:
    """Forgets every state remembered: for tests."""
    with _LOCK:
        _KNOWN.clear()
