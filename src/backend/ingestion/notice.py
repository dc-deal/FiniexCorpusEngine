"""`NOTICE.md`: every free work this project reads, with its authors, source and licence, and what the project does with it.

Written from `corpus/catalog.json` alone, so the list grows with every work the catalog takes in and cannot drift from it;
a contract test fails when the file is stale. No work is in the repository: `python -m backend.ingestion.acquire`
fetches each from the place named, under the licence named, so a contributor gets the same files the same way.

    python -m backend.ingestion.notice     # writes NOTICE.md; spends nothing
"""

import json
import sys

from backend.configuration import data_paths
from backend.ingestion.acquire import LICENCE_DEEDS

CATALOG = data_paths.ROOT / 'corpus' / 'catalog.json'
NOTICE = data_paths.ROOT / 'NOTICE.md'

INTRODUCTION = """# Notice

FiniexCorpusEngine's code is MIT-licensed ([LICENSE](LICENSE)). It is built to read the works listed below, and none
of them is part of this repository:

- **Not uploaded here.** `python -m backend.ingestion.acquire` downloads each work from the place named below, under
  the licence named below, into the data folder `_data/corpus/raw/`. A contributor gets the same files the same way.
- **What the project does with them:** it reads each work page by page into a local search index, checks every page's
  reading against the original, and answers with a verbatim quote, its page and its licence. Its checked readings and
  measurements are kept in a local data folder, never in any repository.
- **Where excerpts appear here, they keep their work's licence:** the screenshots in `docs/images/` (the README's
  section "What it looks like" names the works) and the page transcriptions in `tests/fixtures/page_contract/` (its
  README does).
- **A work under a NoDerivatives licence is never transformed,** only quoted word for word with its source.

This file is written from `corpus/catalog.json` by `python -m backend.ingestion.notice`; do not edit it by hand.
"""

NON_COMMERCIAL = """## Non-commercial works

The code may be used commercially under its MIT licence; these works may not. Their licences forbid commercial use, so
a commercial use of this project leaves them out:
"""

RIGHTS_HOLDERS = """## For rights holders

If you hold rights in a work listed here and see a problem with how it is used, please open an issue in this
repository. The material concerned is taken out while the question is open.

## Libraries

The built interface bundles libraries under their own licences, listed in
`src/frontend/diagnostics/dist/THIRD_PARTY_NOTICES.md`; KaTeX, vendored for the page checks, carries its licence in
`src/backend/conversion/vendor/katex.LICENSE`.
"""


def render_notice(catalog: dict) -> str:
    """The whole of `NOTICE.md` for a catalog: the introduction, one entry per work, the non-commercial ones, a contact."""
    lines = [INTRODUCTION, '## The works', '']
    for source in catalog['sources']:
        deed = LICENCE_DEEDS.get(source['licence'])
        licence = f"[{source['licence']}]({deed})" if deed else source['licence']
        lines += [
            f"### {source['title']}",
            '',
            f"- **Authors:** {source['authors']}",
            f"- **Publisher:** {source['publisher']}" + (f", {source['year']}" if source.get('year') else ''),
            f"- **Licence:** {licence}, stated at <{source['licence_url']}>, checked {source['licence_checked']}",
            f"- **Source:** <{source['source_url']}>",
            '',
        ]
    non_commercial = [source['title'] for source in catalog['sources'] if '-NC' in source['licence']]
    if non_commercial:
        lines += [NON_COMMERCIAL] + [f'- {title}' for title in non_commercial] + ['']
    lines.append(RIGHTS_HOLDERS)
    return '\n'.join(lines)


def main() -> int:
    """Write `NOTICE.md` from the catalog."""
    sys.stdout.reconfigure(encoding='utf-8')
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    NOTICE.write_bytes(render_notice(catalog).encode('utf-8'))
    print(f'NOTICE.md: {len(catalog["sources"])} works')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
