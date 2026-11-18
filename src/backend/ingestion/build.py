"""Build the index: load → clean → split → embed → store, for every source in the catalog.

Run from the repository root:
    python -m backend.ingestion.build --dry-run          # load and split only; counts and estimated cost
    python -m backend.ingestion.build                    # embed and store what changed
    python -m backend.ingestion.build --source ID        # one source
    python -m backend.ingestion.build --force            # re-index even unchanged sources

A source is re-indexed only when its fingerprint changed: the checksums of its raw files (from
the manifest) plus the splitting configuration. A second build therefore costs nothing.
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.configuration import data_paths
from backend.conversion.store import served_readings
from backend.ingestion import chunking, index_store
from backend.ingestion.clean_sections import html_sections, pdf_sections
from backend.ingestion.clean_sections.html_sections import load_html_sections
from backend.ingestion.clean_sections.pdf_sections import load_pdf_sections
from backend.ingestion.sections import Section
from backend.providers import embedding_route, openrouter_client
from backend.types.config_types.app_config_types import EmbeddingProvider

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / 'corpus' / 'catalog.json'
MANIFEST = data_paths.FREE_RAW / '_manifest.json'
INDEX = data_paths.INDEX


LOADER_VERSIONS = {'pdf': pdf_sections.LOADER_VERSION, 'html': html_sections.LOADER_VERSION}


def fingerprint(source: dict, manifest: dict) -> str:
    """Everything that changes a source's chunks: its raw files, the version of the loader for its
    format, the splitting configuration, and for a PDF the readings its pages come from (each page's
    route and text hash). A change to the PDF loader re-indexes only PDFs; a corrected reading only
    its own source."""
    files = sorted((entry['path'], manifest[entry['path']]['sha256']) for entry in source['files'])
    readings = (served_readings.readings_fingerprint(Path(source['files'][0]['path']).name)
                if source['format'] == 'pdf' else None)
    payload = json.dumps({'files': files, 'loader': LOADER_VERSIONS[source['format']],
                          'config': chunking.splitting_config(), 'readings': readings}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def load_sections(source: dict, manifest: dict) -> list[Section]:
    if source['format'] == 'pdf':
        path = data_paths.locate(source['files'][0]['path'])
        return load_pdf_sections(source['id'], path, served_readings.served_pages(path.name))
    return load_html_sections(source, manifest, data_paths.DATA)


def missing_files(sources: list[dict]) -> list[str]:
    return [entry['path'] for source in sources for entry in source['files']
            if not data_paths.locate(entry['path']).exists()]


def estimated_usd(tokens: int) -> float:
    return tokens * embedding_route.USD_PER_MILLION_TOKENS / 1_000_000


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--source', help='only this source id')
    parser.add_argument('--dry-run', action='store_true', help='load and split only; spend nothing')
    parser.add_argument('--force', action='store_true', help='re-index unchanged sources too')
    args = parser.parse_args(argv)

    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))['files'] if MANIFEST.exists() else {}
    sources = [s for s in catalog['sources'] if args.source in (None, s['id'])]
    if not sources:
        print(f'unknown source {args.source!r}', file=sys.stderr)
        return 2
    missing = missing_files(sources)
    if missing:
        print(f'{len(missing)} raw file(s) missing, e.g. {missing[0]}. Run: python -m backend.ingestion.acquire',
              file=sys.stderr)
        return 2

    connection = None if args.dry_run else index_store.connect(INDEX / 'knowledge.sqlite3')
    started = datetime.now(timezone.utc).isoformat(timespec='seconds')
    plans = []
    for source in sources:
        print_ = fingerprint(source, manifest)
        if connection is not None and not args.force and index_store.stored_fingerprint(connection, source['id']) == print_:
            plans.append({'source': source, 'fingerprint': print_, 'status': 'unchanged'})
            continue
        began = time.perf_counter()
        sections = load_sections(source, manifest)
        chunks = chunking.chunk_sections(sections, source)
        plans.append({
            'source': source, 'fingerprint': print_, 'status': 'planned', 'sections': sections,
            'chunks': chunks, 'tokens': sum(c.metadata['tokens'] for c in chunks),
            'seconds': time.perf_counter() - began,
        })

    measured = None
    if not args.dry_run and any(p['status'] == 'planned' for p in plans):
        store = index_store.chroma(INDEX / 'chroma', embedding_route.embeddings(), embedding_route.INDEX_MODEL)
        # Only OpenRouter books a key's usage where a run can read it; OpenAI shows a project key's in its dashboard.
        booked = embedding_route.provider() is EmbeddingProvider.OPENROUTER
        usage_before = openrouter_client.key_usage() if booked else None
        for plan in plans:
            if plan['status'] != 'planned':
                continue
            began = time.perf_counter()
            index_store.replace_source(connection, store, plan['source'], plan['fingerprint'],
                                       plan['sections'], plan['chunks'])
            plan['status'] = 'indexed'
            plan['embed_seconds'] = time.perf_counter() - began
        if booked:
            print(f'indexed; waiting for OpenRouter to book the cost '
                  f'(up to {openrouter_client.BOOKING_TIMEOUT_SECONDS} s)...')
            measured = openrouter_client.measured_cost(
                usage_before, estimated_usd(sum(p['tokens'] for p in plans if p['status'] == 'indexed')))

    print(f"{'source':46} {'sections':>8} {'chunks':>7} {'tokens':>10} {'est. USD':>9}  status")
    for plan in plans:
        if plan['status'] == 'unchanged':
            print(f"{plan['source']['id']:46} {'':>8} {'':>7} {'':>10} {'':>9}  unchanged")
            continue
        print(f"{plan['source']['id']:46} {len(plan['sections']):>8} {len(plan['chunks']):>7} "
              f"{plan['tokens']:>10,} {estimated_usd(plan['tokens']):>9.4f}  "
              f"{'dry run' if args.dry_run else plan['status']}")
    done = [p for p in plans if p['status'] != 'unchanged']
    tokens = sum(p['tokens'] for p in done)
    print(f"{'total':46} {sum(len(p['sections']) for p in done):>8} {sum(len(p['chunks']) for p in done):>7} "
          f"{tokens:>10,} {estimated_usd(tokens):>9.4f}")
    if not args.dry_run and any(p['status'] == 'indexed' for p in plans):
        if measured is not None:
            print(f'measured on the key: {measured:.6f} USD')
        elif embedding_route.provider() is EmbeddingProvider.OPENROUTER:
            print(f'measured on the key: not booked within {openrouter_client.BOOKING_TIMEOUT_SECONDS} s '
                  f'(stored as unknown, not 0)')
        else:
            print('measured on the key: not readable on OpenAI direct, its dashboard shows it (stored as unknown, not 0)')

    if connection is not None:
        index_store.record_run(connection, {
            'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'model': embedding_route.INDEX_MODEL,
            'sources_indexed': len(done), 'sources_unchanged': len(plans) - len(done),
            'chunks': sum(len(p['chunks']) for p in done), 'tokens': tokens,
            'estimated_usd': estimated_usd(tokens), 'measured_usd': measured,
            'config': chunking.splitting_config(),
        })
    return 0


if __name__ == '__main__':
    from backend.conversion.store import pipeline_db

    with pipeline_db.run(['free'], pipeline_db.command_line('backend.ingestion.build')) as recorded:
        code = main()
        recorded.note = f'exit {code}; the embeddings are paid on OpenRouter, outside the ledgers'
    sys.exit(code)
