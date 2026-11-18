"""Download every file listed in corpus/catalog.json into corpus/raw/.

Writes _data/corpus/raw/_manifest.json with one record per file: URL, time, size, SHA-256, and for
Wikipedia the revision id, so a citation can link to the exact revision that was indexed.
Also writes _data/corpus/raw/LICENSES.md, the attribution every licence requires, from the catalog and
the manifest, so it cannot drift from either.

Files already on disk are kept unless --force is given, so a re-run only fetches what is
missing. Standard library only: acquisition has to work before anything else is installed.

Run from the repository root:
    python -m backend.ingestion.acquire                 # everything that is missing
    python -m backend.ingestion.acquire --source ID     # one source
    python -m backend.ingestion.acquire --force         # re-download everything
"""

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from backend.configuration import data_paths

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / 'corpus' / 'catalog.json'
MANIFEST = data_paths.FREE_RAW / '_manifest.json'
LICENSES = data_paths.FREE_RAW / 'LICENSES.md'

# The licence deeds, for the licence names the catalog uses. A name not listed here is shown as
# stated, with the page where it was checked, rather than linked to a guessed version.
LICENCE_DEEDS = {
    'CC BY 3.0 Unported': 'https://creativecommons.org/licenses/by/3.0/',
    'CC BY 4.0': 'https://creativecommons.org/licenses/by/4.0/',
    'CC BY-SA 4.0': 'https://creativecommons.org/licenses/by-sa/4.0/',
    'CC BY-NC-SA 4.0': 'https://creativecommons.org/licenses/by-nc-sa/4.0/',
    'CC BY-NC-ND 4.0': 'https://creativecommons.org/licenses/by-nc-nd/4.0/',
}

# Wikimedia asks every client to identify itself; the other hosts accept it too.
USER_AGENT = 'FiniexCorpusEngine/0.1 (corpus download; https://github.com/dc-deal/FiniexCorpusEngine)'
TIMEOUT_SECONDS = 120
PAUSE_SECONDS = 1.0  # between requests, to stay polite towards the hosts

# What a response must look like for its format. An HTML error page saved under a .pdf name
# would otherwise pass as a download and fail much later, far from the cause.
EXPECTED_CONTENT_TYPE = {'pdf': 'application/pdf', 'html': 'text/html'}

# The REST API's ETag carries the revision: W/"1368876746/5b1350a3-…/view"
_WIKIPEDIA_REVISION = re.compile(r'^(?:W/)?"(\d+)/')


def planned_files(catalog: dict, source_id: str | None = None) -> list[dict]:
    """List every file the catalog asks for.

    Args:
        catalog: The parsed catalog.
        source_id: Restrict the list to one source, or None for all.

    Returns:
        One dict per file with source_id, format, url and path (relative to the repository root).
    """
    files = []
    for source in catalog['sources']:
        if source_id is not None and source['id'] != source_id:
            continue
        for entry in source['files']:
            files.append({
                'source_id': source['id'],
                'format': source['format'],
                'url': entry['url'],
                'path': entry['path'],
            })
    return files


def wikipedia_revision(etag: str | None) -> int | None:
    """Read the revision id out of a Wikipedia REST API ETag.

    Args:
        etag: The ETag header value, or None.

    Returns:
        The revision id, or None when the header does not carry one.
    """
    if not etag:
        return None
    match = _WIKIPEDIA_REVISION.match(etag)
    return int(match.group(1)) if match else None


def check_content(file_format: str, content_type: str, body: bytes) -> str | None:
    """Check that a response is what its format promises.

    Args:
        file_format: 'pdf' or 'html', from the catalog.
        content_type: The Content-Type header.
        body: The response body.

    Returns:
        None when the response is acceptable, otherwise the reason it is not.
    """
    expected = EXPECTED_CONTENT_TYPE[file_format]
    if not content_type.lower().startswith(expected):
        return f'content type is {content_type!r}, expected {expected!r}'
    if not body:
        return 'empty body'
    if file_format == 'pdf' and not body.startswith(b'%PDF'):
        return 'body does not start with %PDF'
    return None


def download(url: str) -> tuple[bytes, dict]:
    """Fetch one URL.

    Args:
        url: The URL to fetch.

    Returns:
        The body and the response headers that matter for the manifest.
    """
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body = response.read()
        headers = {
            'status': response.status,
            'content_type': response.headers.get('Content-Type', ''),
            'etag': response.headers.get('ETag'),
            'last_modified': response.headers.get('Last-Modified'),
        }
    return body, headers


def fetch_file(planned: dict, force: bool) -> dict:
    """Download one planned file unless it is already on disk.

    The body is written to a temporary name first and renamed when complete, so an interrupted
    download never leaves a file that looks finished.

    Args:
        planned: One entry from planned_files().
        force: Download even when the file exists.

    Returns:
        The manifest record for this file, with 'outcome' set to downloaded, kept or failed.
    """
    target = data_paths.locate(planned['path'])
    record = dict(planned)
    if target.exists() and not force:
        record['outcome'] = 'kept'
        return record

    try:
        body, headers = download(planned['url'])
    except (urllib.error.URLError, TimeoutError) as error:
        record.update(outcome='failed', error=str(error))
        return record

    problem = check_content(planned['format'], headers['content_type'], body)
    if problem:
        record.update(outcome='failed', error=problem)
        return record

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.partial')
    partial.write_bytes(body)
    partial.replace(target)

    record.update(
        outcome='downloaded',
        fetched_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        bytes=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        http_status=headers['status'],
        content_type=headers['content_type'],
        etag=headers['etag'],
        last_modified=headers['last_modified'],
    )
    revision = wikipedia_revision(headers['etag']) if 'wikipedia.org' in planned['url'] else None
    if revision is not None:
        record['wikipedia_revision'] = revision
    return record


def merge_manifest(existing: dict, records: list[dict]) -> dict:
    """Fold new records into the manifest, keyed by path.

    A kept file keeps its earlier record, because that record describes the bytes on disk.
    A failed download keeps the earlier record too, if there is one: a failed re-download
    has not changed the file.

    Args:
        existing: The manifest as read from disk ({} if none).
        records: The records from this run.

    Returns:
        The updated manifest.
    """
    files = dict(existing.get('files', {}))
    for record in records:
        if record['outcome'] == 'downloaded' or record['path'] not in files:
            files[record['path']] = {k: v for k, v in record.items() if k != 'outcome'}
    return {'files': dict(sorted(files.items()))}


def wikipedia_permalink(path: str, revision: int) -> str:
    """Build the permanent link to one Wikipedia revision from a downloaded file's path.

    Args:
        path: The file's path, whose stem is the article title (e.g. .../Sharpe_ratio.html).
        revision: The revision id recorded in the manifest.

    Returns:
        The oldid permalink, which keeps pointing at exactly that revision.
    """
    title = Path(path).stem
    return f'https://en.wikipedia.org/w/index.php?title={title}&oldid={revision}'


def render_licences(catalog: dict, manifest: dict) -> str:
    """Render the attribution for every source: title, authors, licence, and where it came from.

    Args:
        catalog: The parsed catalog.
        manifest: The manifest, for Wikipedia revisions.

    Returns:
        The Markdown text of LICENSES.md.
    """
    files = manifest.get('files', {})
    lines = [
        '# Licences of the files in this folder',
        '',
        'Generated by `python -m backend.ingestion.acquire` from `corpus/catalog.json` and `_manifest.json`.',
        'Do not edit by hand: a re-run overwrites it.',
        '',
        'Every file here is an **unmodified copy**, as downloaded from the URL given. Each source is',
        'used under the licence stated at the page linked, checked on the date given.',
        '',
    ]
    for source in catalog['sources']:
        deed = LICENCE_DEEDS.get(source['licence'])
        licence = f"[{source['licence']}]({deed})" if deed else source['licence']
        lines += [
            f"## {source['title']}",
            '',
            f"- **Authors:** {source['authors']}",
            f"- **Publisher:** {source['publisher']}" + (f", {source['year']}" if source.get('year') else ''),
            f"- **Licence:** {licence}, stated at <{source['licence_url']}>, checked {source['licence_checked']}",
            f"- **Source:** <{source['source_url']}>",
        ]
        for entry in source['files']:
            if entry.get('tracked') is False:
                lines.append(f"- **Not in the repository:** `{entry['path']}`: {entry['not_tracked_because']}")
        revisions = [
            (entry['path'], files[entry['path']]['wikipedia_revision'])
            for entry in source['files']
            if files.get(entry['path'], {}).get('wikipedia_revision') is not None
        ]
        if revisions:
            lines.append('- **Revisions downloaded:**')
            lines += [f'  - [{Path(p).stem}]({wikipedia_permalink(p, r)})' for p, r in revisions]
        lines.append('')
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--source', help='only this source id')
    parser.add_argument('--force', action='store_true', help='re-download existing files')
    args = parser.parse_args(argv)

    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    planned = planned_files(catalog, args.source)
    if not planned:
        print(f'no files planned (unknown source {args.source!r}?)', file=sys.stderr)
        return 2

    records = []
    for index, entry in enumerate(planned):
        record = fetch_file(entry, args.force)
        records.append(record)
        size = f"{record.get('bytes', 0):>12,}" if record['outcome'] == 'downloaded' else ' ' * 12
        detail = record.get('error', '')
        print(f"{record['outcome']:<10} {size}  {record['path']}  {detail}")
        if record['outcome'] == 'downloaded' and index < len(planned) - 1:
            time.sleep(PAUSE_SECONDS)

    existing = json.loads(MANIFEST.read_text(encoding='utf-8')) if MANIFEST.exists() else {}
    manifest = merge_manifest(existing, records)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    # LF as everywhere in the repository: without `newline`, Windows wrote CRLF (found on the intake of 8 Nov)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    LICENSES.write_text(render_licences(catalog, manifest), encoding='utf-8', newline='\n')

    failed = [r for r in records if r['outcome'] == 'failed']
    counts = {o: sum(r['outcome'] == o for r in records) for o in ('downloaded', 'kept', 'failed')}
    print(f"\n{counts['downloaded']} downloaded, {counts['kept']} kept, {counts['failed']} failed")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
