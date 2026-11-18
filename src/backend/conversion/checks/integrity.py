"""The integrity of an export of page readings: is every reading still what was checked, and has every page one (decision 69.a)?

Two scans, both by code and free:

- **tampered:** a reading's file no longer matches the sha256 its row recorded when it was exported, so what the search and the
  chat would quote is not what stages 1 and 2 and the judge saw.
- **gaps:** a page of a work's PDF without a row, or a row whose reading file is gone. Such a page is served from its text layer
  at best, without anyone having decided so.

Either finding is repaired by `replay --reread`, which buys that one page again as a new attempt (decision 54.a), never by
copying a stored file back: the demo shows the pipeline at work, and every version stays in the trace.

    python -m backend.conversion.checks.integrity [--knowledge-base licensed]    # exit 1 when anything is found
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pymupdf

from backend.configuration import data_paths


def page_state(export: Path, row: dict) -> str:
    """One page of an export: 'whole' when its reading file holds what was checked, 'tampered' when it differs, 'missing'
    when it is gone, 'no reading' for a row without one (a text-layer page). One file hashed, so a page view can ask on
    every visit, and a live change shows at once; `scan` asks the same function (line 2's request, 5 Nov)."""
    if not row.get('text_file'):
        return 'no reading'
    target = export / row['text_file']
    if not target.exists():
        return 'missing'
    return 'whole' if hashlib.sha256(target.read_bytes()).hexdigest() == row.get('text_sha256') else 'tampered'


def scan(export: Path) -> dict:
    """Every finding of one export: {'tampered': [...], 'missing_files': [...], 'gaps': [...], 'unknown_pdfs': [...]}."""
    index = json.loads((export / 'index.json').read_text(encoding='utf-8'))
    found = {'knowledge_base': index.get('knowledge_base'), 'pages': len(index['pages']), 'tampered': [], 'missing_files': [],
             'gaps': [], 'unknown_pdfs': []}
    for row in index['pages']:
        state = page_state(export, row)
        if state in ('missing', 'tampered'):
            place = {'work': row['work'], 'pdf_page': row['pdf_page'], 'text_file': row['text_file']}
            found['missing_files' if state == 'missing' else 'tampered'].append(place)
    rows = {(row['work'], row['pdf_page']) for row in index['pages']}
    for work in index.get('works', []):
        pdf = data_paths.locate(work['pdf'])
        if not pdf.exists():
            found['unknown_pdfs'].append({'work': work['work'], 'pdf': work['pdf']})
            continue
        with pymupdf.open(pdf) as document:
            found['gaps'] += [{'work': work['work'], 'pdf_page': number} for number in range(1, document.page_count + 1)
                              if (work['work'], number) not in rows]
    return found


def problems(found: dict) -> int:
    return len(found['tampered']) + len(found['missing_files']) + len(found['gaps'])


def main() -> None:
    from backend.conversion.store import pipeline_db, reading_export

    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--knowledge-base', choices=sorted(reading_export.BASES), default='free')
    base = reading_export.BASES[parser.parse_args().knowledge_base]
    with pipeline_db.run([base.name], pipeline_db.command_line('backend.conversion.checks.integrity')) as recorded:
        found = scan(base.export)
        recorded.note = f'{problems(found)} problems'
    print(f"{base.name}: {found['pages']} pages; tampered {len(found['tampered'])}, reading file missing "
          f"{len(found['missing_files'])}, pages without a row {len(found['gaps'])}, PDFs not here {len(found['unknown_pdfs'])}")
    for kind in ('tampered', 'missing_files', 'gaps'):
        for place in found[kind][:20]:
            print(f"  {kind}: {place['work']} p{place['pdf_page']}")
    sys.exit(1 if problems(found) else 0)


if __name__ == '__main__':
    main()
