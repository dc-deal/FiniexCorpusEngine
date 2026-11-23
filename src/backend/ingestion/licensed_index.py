"""The private knowledge base's vector index (issue #8): every page the librarian serves for it, chunked and embedded as the
free index is, kept on this machine only.

The free index is built from the raw sources (`build`); the private base has no such single source, since its pages come by
four routes (a checked reading, the earlier Markdown conversion, a PDF's text layer, an EPUB's section). So this index is
built from the librarian's own pages (`search_server.licensed_pages`): the very text the keyword search serves, each page a
section with its PDF page, route and reading key, split by the free index's splitter, stored in the free index's format, in
its own folder under the private working data. A hit cites as a free one does.

A work whose file the provenance list holds back stays out whole, its earlier Markdown and its EPUB sections included: an
embedding sends text to a provider (decision 33). The folder is refused wherever git would track it.

    python -m backend.ingestion.licensed_index --dry-run   # pages, chunks, tokens and the estimate; spends nothing
    python -m backend.ingestion.licensed_index             # embed what changed, work by work
"""

import argparse
import hashlib
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from backend.configuration import data_paths
from backend.ingestion import chunking, index_store
from backend.ingestion.build import estimated_usd
from backend.ingestion.sections import Section

KNOWLEDGE_BASE = 'licensed'


def held_works(keys: dict[str, str]) -> set[str]:
    """The private works whose file the provenance list holds back from providers, by work key: a legacy work's PDF or EPUB,
    an EPUB work, a stand-in, an HTML source. Their text never reaches the embedding provider."""
    from backend.conversion.reading import reading_cells
    from backend.search import search_server

    held = set()
    for key, slug in keys.items():
        for suffix in ('.pdf', '.epub'):
            if (search_server.LICENSED_ARCHIVE / f'{slug}{suffix}').exists() and not reading_cells.may_send(f'{slug}{suffix}'):
                held.add(key)
    html = {key: path for key, (path, _) in search_server.licensed_html().items()}
    for key, path in {**search_server.licensed_epubs(keys), **search_server.stand_ins(keys), **html}.items():
        if not reading_cells.may_send(path.name):
            held.add(key)
    return held


def sections_of(work: str, pages: list) -> list[Section]:
    """A work's served pages as sections, one a page, in the order the librarian holds them: each keeps its PDF page, its
    printed page, its route and its reading key, so a chunk cites the page it came from."""
    sections = []
    for ordinal, page in enumerate(pages):
        number = int(page.pdf) if page.pdf else None
        sections.append(Section(source_id=work, ordinal=ordinal, heading_path=[page.section] if page.section else [],
                                text=page.text, pages=[(0, number, page.printed)] if number is not None else [],
                                routes={number: (page.route, page.reading_key)} if number is not None else {}))
    return sections


def code_chunks(pages: list, source: dict, code_language: str) -> list:
    """A code work's chunks (#12): one a file, never cut, under a header line that names the work, the file and the language,
    so a passage of code carries what it is to the embedding. Its page label rides along, so a hit opens the file."""
    from langchain_core.documents import Document

    chunks = []
    for ordinal, page in enumerate(pages):
        content = f"{source['title']} · {page.page} · {code_language}" + '\n\n' + page.text
        metadata = {**chunking.source_metadata(source), 'chunk_id': f"{page.work}:{ordinal:04d}:000",
                    'section_id': f"{page.work}:{ordinal:04d}", 'section': page.section, 'page_label': page.page,
                    'route': page.route, 'tokens': chunking.count_tokens(content)}
        chunks.append(Document(page_content=content, metadata={k: v for k, v in metadata.items() if v is not None}))
    return chunks


def source_of(work, entry: dict | None) -> dict:
    """A private work as a chunk's citation fields, the free catalog's names: title, authors and shelf from the local licensed
    catalog where it lists the work's file (N1.a), else the librarian's own title. The shelf is what the router's shelf filter
    matches, so it must be the catalog's (trading_finance, architecture), never a description."""
    entry = entry or {}
    authors = entry.get('authors') or ''
    return {'id': work.key, 'title': entry.get('title') or work.title,
            'authors': ', '.join(authors) if isinstance(authors, list) else authors, 'shelf': entry.get('shelf') or '',
            'format': entry.get('format') or work.route, 'licence': work.licence, 'licence_url': ''}


def catalog_entries(keys: dict[str, str]) -> dict[str, dict]:
    """The local licensed catalog's entry of each work key: by the file stem the key names (a legacy work's slug), else by the
    key itself (a new work, an EPUB). Empty without a catalog on this machine."""
    import json

    path = data_paths.LICENSED_CATALOG
    if not path.exists():
        return {}
    by_stem = {Path(entry['file']).stem: entry for entry in json.loads(path.read_text(encoding='utf-8'))['sources']}
    found = {key: by_stem[slug] for key, slug in keys.items() if slug in by_stem}
    return {**{stem: entry for stem, entry in by_stem.items()}, **found}


def fingerprint(pages: list) -> str:
    """Everything a work's chunks are made of: each page's place, route and text. A work whose pages are the same is not
    embedded again."""
    digest = hashlib.sha256()
    for page in pages:
        digest.update(f'{page.page}\x00{page.pdf}\x00{page.route}\x00{page.reading_key}\x00'.encode('utf-8'))
        digest.update(page.text.encode('utf-8'))
    return digest.hexdigest()


def index_connection(path: Path, dry_run: bool) -> sqlite3.Connection | None:
    """The private index's facts. A dry run opens them read-only, so it compares each work's fingerprint without writing
    (found 22 Nov: without them a dry run counted every work as changed, 0.21 USD instead of the new works' cents); None
    where a dry run finds no index yet."""
    if not dry_run:
        return index_store.connect(path)
    if not path.exists():
        return None
    return sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)


def plans(pages: list, works: dict, held: set[str], catalog: dict[str, dict] | None = None) -> tuple[list[dict], dict]:
    """Per private work not held back: its source, sections, chunks and token count; and what was left out, by why."""
    by_work = defaultdict(list)
    for page in pages:
        if page.knowledge_base == KNOWLEDGE_BASE:
            by_work[page.work].append(page)
    planned, left_out = [], defaultdict(int)
    for key in sorted(by_work):
        if key in held:
            left_out['held back by the provenance list'] += len(by_work[key])
            continue
        source = source_of(works[key], (catalog or {}).get(key))
        sections = sections_of(key, by_work[key])
        code = getattr(works[key], 'code_language', None)
        chunks = code_chunks(by_work[key], source, code) if code else chunking.chunk_sections(sections, source)
        for chunk in chunks:
            chunk.metadata['knowledge_base'] = KNOWLEDGE_BASE
        planned.append({'source': source, 'fingerprint': fingerprint(by_work[key]), 'sections': sections, 'chunks': chunks,
                        'pages': len(by_work[key]), 'tokens': sum(chunk.metadata['tokens'] for chunk in chunks)})
    return planned, dict(left_out)


def main(argv: list[str] | None = None) -> int:
    from backend.conversion.store import reading_store
    from backend.providers import embedding_route
    from backend.search import search_server

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--dry-run', action='store_true', help='plan only: pages, chunks, tokens, the estimate; spend nothing')
    parser.add_argument('--force', action='store_true', help='embed unchanged works too')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')

    directory = data_paths.LICENSED_INDEX
    refused = reading_store.refusal(directory.resolve())
    if refused:
        print(f'the private index is never built there: {refused}', file=sys.stderr)
        return 2
    keys = search_server.legacy_keys()
    pages, works = search_server.licensed_pages()
    planned, left_out = plans(pages, works, held_works(keys), catalog_entries(keys))
    connection = index_connection(directory / 'knowledge.sqlite3', args.dry_run)
    if connection is not None and not args.force:
        for plan in planned:
            if index_store.stored_fingerprint(connection, plan['source']['id']) == plan['fingerprint']:
                plan['unchanged'] = True
    todo = [plan for plan in planned if not plan.get('unchanged')]
    tokens = sum(plan['tokens'] for plan in todo)
    print(f"{len(planned)} works, {sum(plan['pages'] for plan in planned):,} pages, "
          f"{sum(len(plan['chunks']) for plan in planned):,} chunks; to embed: {len(todo)} works, "
          f"{sum(len(plan['chunks']) for plan in todo):,} chunks, {tokens:,} tokens, estimate {estimated_usd(tokens):.4f} USD; "
          f"left out: {left_out or 'nothing'}")
    if args.dry_run or not todo:
        if connection is not None:
            connection.close()
        return 0
    started = datetime.now(timezone.utc).isoformat(timespec='seconds')
    store = index_store.chroma(directory / 'chroma', embedding_route.embeddings(), embedding_route.INDEX_MODEL)
    for number, plan in enumerate(todo, start=1):
        index_store.replace_source(connection, store, plan['source'], plan['fingerprint'], plan['sections'], plan['chunks'])
        print(f"{number}/{len(todo)}: {len(plan['chunks'])} chunks embedded")
    index_store.record_run(connection, {
        'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'model': embedding_route.INDEX_MODEL, 'sources_indexed': len(todo), 'sources_unchanged': len(planned) - len(todo),
        'chunks': sum(len(plan['chunks']) for plan in todo), 'tokens': tokens, 'estimated_usd': estimated_usd(tokens),
        'measured_usd': None, 'config': chunking.splitting_config()})
    return 0


if __name__ == '__main__':
    from backend.conversion.store import pipeline_db

    with pipeline_db.run([KNOWLEDGE_BASE], pipeline_db.command_line('backend.ingestion.licensed_index')) as recorded:
        code = main()
        recorded.note = f'exit {code}; the embeddings are paid outside the ledgers'
    sys.exit(code)
