"""Subject sentences that describe a work by what its front matter names rather than by what it is about (issue #14).

A client plans a search from `works`, one sentence per work. Found on 23 Nov 2026: one sentence named the software a
book's front matter lists (a platform, a compiler, a function library) and not the book's subject, systematic tests of
entries and exits, so no client was sent to it. This check lists such sentences for a person to rewrite; it never rewrites
one itself. A sentence is flagged where it says "front matter", or names two products or more.

    python -m backend.ingestion.subject_check      # both catalogs' sentences; prints the flagged works
"""

import json
import re
import sys

from backend.configuration import data_paths

FRONT_MATTER = re.compile(r'(?i)\bfront matter\b')
PRODUCTS = re.compile(r'(?i)\b(tradestation|visual c\+\+|visual basic|excel|matlab|numerical recipes|metastock|ninjatrader|'
                      r'amibroker|multicharts|evolver|mesa|nag function library|metatrader|mathematica)(?!\w)')  # \b fails after ++


def flags(sentence: str | None) -> list[str]:
    """Why a sentence reads as a list of what the front matter names; empty where it does not."""
    if not sentence:
        return ['no sentence']
    found = []
    if FRONT_MATTER.search(sentence):
        found.append('names the front matter')
    products = sorted({match.lower() for match in PRODUCTS.findall(sentence)})
    if len(products) >= 2:
        found.append(f"names {len(products)} products: {', '.join(products)}")
    return found


def sentences() -> dict[str, str | None]:
    """Work id -> its subject sentence, from the free catalog and, where this machine holds it, the licensed list."""
    found = {source['id']: source.get('subject') for source in
             json.loads((data_paths.ROOT / 'corpus' / 'catalog.json').read_text(encoding='utf-8'))['sources']}
    licensed = data_paths.LICENSED_WORKING / 'subjects.json'
    if licensed.exists():
        found.update(json.loads(licensed.read_text(encoding='utf-8'))['subjects'])
    return found


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    flagged = {work: reasons for work, sentence in sentences().items() if (reasons := flags(sentence))}
    for work, reasons in sorted(flagged.items()):
        print(f'{work}: {"; ".join(reasons)}')
    print(f'{len(flagged)} sentences to read again')
    return 0


if __name__ == '__main__':
    sys.exit(main())
