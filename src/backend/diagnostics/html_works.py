"""The HTML works: their outline, their sections and the chunks the index embedded (the operator's 6.a, 2026-11-09, an exception to
the feature seal 142.a named as such).

Read from the chat's own index, `corpus/index/knowledge.sqlite3` (`retrieval.DATABASE`), opened read-only: the sections
the loader cut by heading, each with its heading path, and the chunks embedded from them. Nothing is counted that the index
does not hold, and nothing is written. The index is derived and not tracked, so on a fresh clone it does not exist until it
is built: every answer then says so and names the command.

The outline follows the work's own flow (the operator's 1.a): its top level is the work's unit (SRE's chapter files, the Wikipedia
articles, Lefèvre's chapters, Kleppmann's one post), built from the heading paths rather than the section list, so a
heading without text of its own stands as a node without a section label. A section is labelled as the search server
labels it, `s` and its position from 1 within the work. Where a work's only top node is its own title, its children move up.

A chunk's place in its section is not stored; it is found by searching the chunk's text in the section text, in order, and
a chunk not found is counted, never hidden.
"""

import json
import sqlite3
import threading
from pathlib import Path

from pydantic import BaseModel

from backend.configuration import data_paths
from backend.diagnostics import sources as catalog
from backend.diagnostics.ladder_types import PageLadder
from backend.diagnostics.readings import KnowledgeBase
from backend.ingestion import chunking
from backend.ingestion.clean_sections import html_stripped
from backend.search import retrieval

DATABASE = retrieval.DATABASE
MANIFEST = data_paths.FREE_RAW / '_manifest.json'
ROUTE = 'html, parsed by section'
NOT_BUILT = ('No search index on this machine yet: the HTML works are cut into sections and chunks when it is built, '
             'with `python -m backend.ingestion.build`.')
NO_ORIGINAL = 'The raw file of this work is not on this machine: `python -m backend.ingestion.acquire` fetches it.'

# The stripped originals (line 1's `html_stripped.strip_source`), made from corpus/raw on the first ask and kept in this
# process's memory only: SRE is CC BY-NC-ND, so no converted copy of it is written anywhere (decision 91.a)
_STRIPPED: dict[str, tuple[list, list]] = {}
_STRIPPING = threading.Lock()


def stripped_of(source_id: str) -> tuple[list, list] | None:
    """A work's stripped sections and its dropped headings, from its raw files; None where they cannot be read here."""
    with _STRIPPING:
        if source_id not in _STRIPPED:
            entry = next((source for source in json.loads(catalog.CATALOG.read_text(encoding='utf-8'))['sources']
                          if source['id'] == source_id), None)
            if entry is None:
                return None
            try:
                manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))['files']
                _STRIPPED[source_id] = html_stripped.strip_source(entry, manifest, data_paths.DATA)
            except (OSError, KeyError):  # a raw file missing on this machine
                return None
        return _STRIPPED[source_id]


class HtmlCounts(BaseModel):
    sections: int
    chunks: int


class HtmlNode(BaseModel):
    """A heading of the work's outline. Its label is its own section's; a heading with no text of its own has none."""

    id: str
    title: str
    parent: str | None
    level: int
    label: str | None
    first: str | None  # the first and last section label of the node and everything beneath it; None for a dropped one
    last: str | None
    sections: int  # sections in the node and beneath it
    chunks: int
    # a heading the loader drops as noise (References, See also, CONTENTS), at its place: its label opens its stripped
    # original, it has no chunks, and its text is in no index (the operator's 2.a)
    dropped: str | None = None


class HtmlSectionRow(BaseModel):
    """A section in the flat table, in the work's order."""

    label: str
    heading_path: str
    chunks: int
    characters: int


class HtmlWork(BaseModel):
    knowledge_base: KnowledgeBase = 'free'
    source_id: str
    title: str
    authors: str | None = None
    licence: str | None = None
    licence_url: str | None = None
    route: str = ROUTE
    why_not: str | None = None  # the index is not built on this machine
    sections: int = 0
    chunks: int = 0
    outline: list[HtmlNode] = []
    rows: list[HtmlSectionRow] = []


class HtmlChunk(BaseModel):
    """A chunk as the index embedded it, and where its text stands in its section's text: start and end as character
    offsets, None where it is not found there. `overlap` is how many of its first characters the chunk before it shares."""

    id: str
    number: int
    text: str
    start: int | None
    end: int | None
    overlap: int
    tokens: int | None = None


class Splitter(BaseModel):
    """How the index cuts a section into chunks, as `chunking.splitting_config` gives it: the view's legend of the overlap
    says from it why a chunk repeats the end of the one before."""

    splitter: str
    chunk_size: int
    chunk_overlap: int


class HtmlSection(BaseModel):
    knowledge_base: KnowledgeBase = 'free'
    source_id: str
    work_title: str
    authors: str | None = None
    licence: str | None = None
    licence_url: str | None = None
    label: str
    heading_path: str
    url: str | None  # the original, at the section's anchor where it has one
    text: str  # the section's text as indexed
    chunks: list[HtmlChunk]
    not_found: int  # chunks whose text was not found in the section's text
    previous: str | None
    next: str | None
    # the section's stripped original, from line 1's function: allow-listed HTML the view sanitises again before showing
    original: str | None = None
    original_why_not: str | None = None
    dropped: bool = False  # a heading dropped as noise: an original, no chunks
    # the section's own coverage ladder (V2.a), which the app sets from the search; None where it has not
    ladder: PageLadder | None = None
    splitter: Splitter = Splitter(**chunking.splitting_config())


class HtmlArticleEntry(BaseModel):
    """One place in an article's scroll, in the work's order: a section with its original and its chunks, a heading the
    loader dropped as noise with its original alone, or a heading with no text of its own, which stands as a heading."""

    label: str | None  # s<n> or d<n>; None for a heading with no text of its own
    title: str
    level: int  # within the article, from 1
    section: HtmlSection | None = None


class HtmlArticle(BaseModel):
    """A top unit of a work's outline whole, on one scroll (the operator, 10 Nov: a click on "Sharpe ratio" should show the whole
    article): a Wikipedia article, an SRE chapter, a chapter of Lefèvre. The section asked for is the one to scroll to."""

    knowledge_base: KnowledgeBase = 'free'
    source_id: str
    work_title: str
    title: str  # the article's own heading
    label: str  # the section asked for
    previous: str | None  # the first section of the article before it, and of the one after
    previous_title: str | None = None
    next: str | None
    next_title: str | None = None
    authors: str | None = None
    licence: str | None = None
    licence_url: str | None = None
    splitter: Splitter = Splitter(**chunking.splitting_config())
    entries: list[HtmlArticleEntry]


def label_of(ordinal: int) -> str:
    """The section's label as the search server gives it (`search_server`, an HTML work's pages)."""
    return f's{ordinal + 1}'


def connect(database: Path) -> sqlite3.Connection | None:
    """The index, read-only; None where it is not built."""
    if not database.is_file():
        return None
    return sqlite3.connect(f'{database.as_uri()}?mode=ro', uri=True)


def counts(database: Path | None = None) -> dict[str, HtmlCounts] | None:
    """Sections and chunks of every HTML work, as the index records them; None where the index is not built."""
    connection = connect(database or DATABASE)
    if connection is None:
        return None
    with connection:
        rows = connection.execute("select id, sections, chunks from sources where format = 'html'").fetchall()
    connection.close()
    return {source: HtmlCounts(sections=sections or 0, chunks=chunks or 0) for source, sections, chunks in rows}


def outline_of(title: str, sections: list[tuple[int, str]], chunks_of: dict[int, int]) -> list[HtmlNode]:
    """The outline from the heading paths, in the work's order: every heading of a path a node, created where it first
    occurs, the full path's node carrying its section's label. Counts and ranges cover a node and everything beneath it."""
    nodes: list[dict] = []
    latest: dict[tuple[str, ...], dict] = {}  # a path's newest node: a repeated path opens a new one
    for ordinal, heading_path in sections:
        path = tuple(heading_path.split(' > '))
        parent = None
        for depth in range(1, len(path) + 1):
            prefix = path[:depth]
            node = latest.get(prefix)
            if node is None or (depth == len(path) and node['ordinal'] is not None):
                node = {'id': f'h{len(nodes) + 1}', 'title': path[depth - 1], 'parent': parent, 'level': depth,
                        'ordinal': None, 'ordinals': []}
                nodes.append(node)
                latest[prefix] = node
            node['ordinals'].append(ordinal)
            parent = node['id']
        node['ordinal'] = ordinal
    roots = [node for node in nodes if node['parent'] is None]
    # a work whose only top node is its own title: its children move up, the title keeps its own text as a node beside them
    if len(roots) == 1 and roots[0]['title'].casefold() == title.casefold() and any(n['parent'] == roots[0]['id'] for n in nodes):
        root = roots[0]
        for node in nodes:
            if node['parent'] == root['id']:
                node['parent'] = None
            if node is not root and node['level'] > 1:
                node['level'] -= 1
        root['ordinals'] = [root['ordinal']] if root['ordinal'] is not None else []
        if not root['ordinals']:
            nodes.remove(root)
    return [HtmlNode(id=node['id'], title=node['title'], parent=node['parent'], level=node['level'],
                     label=None if node['ordinal'] is None else label_of(node['ordinal']),
                     first=label_of(min(node['ordinals'])), last=label_of(max(node['ordinals'])),
                     sections=len(node['ordinals']), chunks=sum(chunks_of.get(o, 0) for o in node['ordinals']))
            for node in nodes]


def with_dropped(outline: list[HtmlNode], dropped: list) -> list[HtmlNode]:
    """The outline with each dropped heading at its place, in document order: after the section it follows, beside it
    under the same top unit (a Wikipedia article's References under its article); before everything where it follows none."""
    placed = list(outline)
    by_id = {node.id: node for node in outline}
    after: dict[str | None, int] = {}  # where the last node placed after a section stands, so the next follows it
    for number, heading in enumerate(dropped, 1):
        label = None if heading.after_ordinal is None else label_of(heading.after_ordinal)
        anchor = next((at for at, node in enumerate(placed) if label and node.label == label), None)
        top = placed[anchor] if anchor is not None else None
        while top is not None and top.parent is not None:
            top = by_id[top.parent]
        at = after.get(label, anchor if anchor is not None else -1) + 1
        node = HtmlNode(id=f'x{number}', title=heading.heading, parent=top.id if top else None, level=top.level + 1 if top else 1,
                        label=None, first=None, last=None, sections=0, chunks=0, dropped=f'd{number}')
        placed.insert(at, node)
        after[label] = at
        after.update({key: index + 1 for key, index in after.items() if key != label and index >= at})
    return placed


def work(source_id: str, title: str, database: Path | None = None) -> HtmlWork | None:
    """One HTML work whole: its outline and its sections in the work's order. None where the index holds no such work;
    a work with `why_not` where the index is not built."""
    connection = connect(database or DATABASE)
    if connection is None:
        return HtmlWork(source_id=source_id, title=title, why_not=NOT_BUILT)
    with connection:
        source = connection.execute("select title, authors, licence, licence_url from sources where id = ? and format = 'html'",
                                    (source_id,)).fetchone()
        listed = connection.execute('select id, ordinal, heading_path, length(text) from sections where source_id = ? '
                                    'order by ordinal', (source_id,)).fetchall()
        # counted over the index's own `chunks_by_source`: a join on the section id, which has no index, took 15 s for SRE
        per_section = dict(connection.execute('select section_id, count(*) from chunks where source_id = ? group by section_id',
                                              (source_id,)).fetchall())
    connection.close()
    if source is None:
        return None
    rows = [(ordinal, path, characters, per_section.get(section_id, 0)) for section_id, ordinal, path, characters in listed]
    chunks_of = {ordinal: chunks for ordinal, _, _, chunks in rows}
    outline = outline_of(title, [(ordinal, path) for ordinal, path, _, _ in rows], chunks_of)
    stripped = stripped_of(source_id)
    return HtmlWork(source_id=source_id, title=title, authors=source[1], licence=source[2], licence_url=source[3],
                    sections=len(rows), chunks=sum(chunks_of.values()),
                    outline=with_dropped(outline, stripped[1]) if stripped else outline,
                    rows=[HtmlSectionRow(label=label_of(ordinal), heading_path=path, chunks=chunks, characters=characters or 0)
                          for ordinal, path, characters, chunks in rows])


def placed(text: str, chunk_texts: list[str]) -> list[tuple[int | None, int | None, int]]:
    """Each chunk's start, end and overlap with the one before it, found by searching its text in the section's text in
    order: from just after the previous chunk's start, else anywhere; None where it is not there at all. A text that
    repeated itself over a whole chunk's length could place a chunk at the earlier repeat; on the index of 9 Nov every
    chunk of the four works stood in its place, which a test checks where the index is built."""
    found: list[tuple[int | None, int | None, int]] = []
    previous: tuple[int, int] | None = None
    for chunk in chunk_texts:
        at = text.find(chunk, previous[0] + 1 if previous else 0)
        if at < 0:
            at = text.find(chunk)
        if at < 0:
            found.append((None, None, 0))
            continue
        end = at + len(chunk)
        found.append((at, end, max(0, previous[1] - at) if previous else 0))
        previous = (at, end)
    return found


def article(source_id: str, label: str, title: str, database: Path | None = None) -> HtmlArticle | None:
    """The top unit of the outline that holds section `label`, every place in it in the work's order: its sections, each with
    its original and chunks, its dropped headings where they stand, and its headings without text of their own. Grouped by
    the outline built from the index, not by raw file, so it stands where the raw files are not on the machine, and a book
    in one file, as Lefèvre's, opens chapter by chapter. None where the index or the label is not there."""
    whole = work(source_id, title, database)
    if whole is None or whole.why_not:
        return None
    by_id = {node.id: node for node in whole.outline}

    def top_of(node: HtmlNode) -> HtmlNode:
        while node.parent is not None:
            node = by_id[node.parent]
        return node

    asked = next((node for node in whole.outline if label in (node.label, node.dropped)), None)
    if asked is None:
        return None
    top = top_of(asked)
    entries = [HtmlArticleEntry(label=node.label or node.dropped, title=node.title, level=node.level - top.level + 1,
                                section=section(source_id, node.label or node.dropped, title, database)
                                if node.label or node.dropped else None)
               for node in whole.outline if top_of(node) is top]
    tops = [node for node in whole.outline if node.parent is None]
    at = tops.index(top)

    def first_of(node: HtmlNode) -> str | None:
        return node.label or node.first or node.dropped

    before, after = (tops[at - 1] if at > 0 else None), (tops[at + 1] if at + 1 < len(tops) else None)
    return HtmlArticle(source_id=source_id, work_title=title, title=top.title, label=label,
                       previous=first_of(before) if before else None, previous_title=before.title if before else None,
                       next=first_of(after) if after else None, next_title=after.title if after else None,
                       authors=whole.authors, licence=whole.licence, licence_url=whole.licence_url, entries=entries)


def dropped_section(source_id: str, label: str, title: str, database: Path | None = None) -> HtmlSection | None:
    """A heading dropped as noise, `d` and its place among the work's dropped headings: its stripped original, no chunks."""
    stripped = stripped_of(source_id)
    number = int(label[1:])
    if stripped is None or not 1 <= number <= len(stripped[1]):
        return None
    heading = stripped[1][number - 1]
    connection = connect(database or DATABASE)
    source = None
    if connection is not None:
        with connection:
            source = connection.execute("select authors, licence, licence_url from sources where id = ? and format = 'html'",
                                        (source_id,)).fetchone()
        connection.close()
    authors, licence, licence_url = source or (None, None, None)
    return HtmlSection(source_id=source_id, work_title=title, authors=authors, licence=licence, licence_url=licence_url,
                       label=label, heading_path=heading.heading, url=None, text='', chunks=[], not_found=0,
                       previous=f'd{number - 1}' if number > 1 else None,
                       next=f'd{number + 1}' if number < len(stripped[1]) else None, original=heading.html, dropped=True)


def section(source_id: str, label: str, title: str, database: Path | None = None) -> HtmlSection | None:
    """One section as indexed, its chunks in order with their places and its stripped original beside; a `d` label is a
    dropped heading's. None where the index or the section is not there."""
    if len(label) < 2 or label[0] not in 'sd' or not label[1:].isdigit() or int(label[1:]) < 1:
        return None
    if label[0] == 'd':
        return dropped_section(source_id, label, title, database)
    connection = connect(database or DATABASE)
    if connection is None:
        return None
    ordinal = int(label[1:]) - 1
    with connection:
        source = connection.execute("select authors, licence, licence_url from sources where id = ? and format = 'html'",
                                    (source_id,)).fetchone()
        row = connection.execute('select id, heading_path, url, text from sections where source_id = ? and ordinal = ?',
                                 (source_id, ordinal)).fetchone()
        last = connection.execute('select max(ordinal) from sections where source_id = ?', (source_id,)).fetchone()[0]
        chunk_rows = [] if row is None else connection.execute(
            'select id, text, metadata from chunks where source_id = ? and section_id = ? order by id', (source_id, row[0])).fetchall()
    connection.close()
    if source is None or row is None:
        return None
    _, heading_path, url, text = row
    places = placed(text, [chunk_text for _, chunk_text, _ in chunk_rows])
    chunks = [HtmlChunk(id=chunk_id, number=number, text=chunk_text, start=start, end=end, overlap=overlap,
                        tokens=(json.loads(metadata or '{}') or {}).get('tokens'))
              for number, ((chunk_id, chunk_text, metadata), (start, end, overlap)) in enumerate(zip(chunk_rows, places), 1)]
    stripped = stripped_of(source_id)
    original = next((one.html for one in stripped[0] if one.ordinal == ordinal), None) if stripped else None
    return HtmlSection(source_id=source_id, work_title=title, authors=source[0], licence=source[1], licence_url=source[2],
                       label=label, heading_path=heading_path, url=url, text=text, chunks=chunks,
                       not_found=sum(1 for chunk in chunks if chunk.start is None),
                       previous=label_of(ordinal - 1) if ordinal > 0 else None,
                       next=label_of(ordinal + 1) if last is not None and ordinal < last else None,
                       original=original, original_why_not=None if original is not None else NO_ORIGINAL)
