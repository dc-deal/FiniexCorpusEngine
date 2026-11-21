"""A PDF page's chunks in its base's vector index, chunk first (the operator, 21 Nov, in place of W4's dashed start lines): in
the page view's "as served" mode the page is shown as the chunks semantic search holds of it. A chunk is the index's cut of
the served text and usually holds several blocks, so each chunk is a group: a one-line head (its letter in page order, its
characters, its pages, what it shares with the one before, where it runs in from or on to, and for a kept edition that it is
held back from the search), then the quoted blocks inside it in the form the search and the chat quote. A block two chunks
share in part, or one a chunk splits, stands in each with only its part, marked as a part; the text two chunks share stands in
both. A block never quoted lies in no chunk and is not shown; quoted text no chunk placed here holds is listed apart.

A chunk is placed by its text, never by an offset: a chunk is a substring of its section's text (`html_works.placed`, the HTML
sections' own rule), and the page's quoted text, its quoted blocks joined as `served_readings.quotable_text` joins them, is
found in that section's text the same way. A free section runs over pages and may end or begin inside one (a heading starts a
new section mid page), so the page's part of a section is one of four: the whole page, the page's beginning at the section's
end, the section's beginning on the page running past it, or a whole section on the page; in the private index a section is a
page. Each quoted block is a span of the page's quoted text, and a chunk holds of it what the two spans share. A chunk the
index places on the page whose text cannot be found in the page's part of its section is said in words and never drawn.
"""

import json
from pathlib import Path
from typing import NamedTuple

from pydantic import BaseModel

from backend.diagnostics import html_works
from backend.ingestion import chunking
from backend.diagnostics.readings import Block, KnowledgeBase, counted_as

HEAD = 16  # the fewest characters of a page and a section that must meet where one runs into the other
JOIN = '\n\n'  # between two quoted blocks of a page, as `served_readings.quotable_text` joins them


class ChunkRun(BaseModel):
    """A run of a block's text in a chunk: whether another chunk of the page holds it too, so that it stands in both."""

    text: str
    shared: bool = False


class ChunkBlock(BaseModel):
    """A quoted block in a chunk, or in none, in its served form: only the part the chunk holds where it holds part of it."""

    block: str  # the block's id in the reading
    block_class: str
    part: bool = False
    runs: list[ChunkRun]


class ChunkGroup(BaseModel):
    """A chunk of the page as the index embedded it, lettered in page order, with its head's words and the blocks it holds."""

    letter: str
    id: str
    characters: int  # the chunk's whole text, on this page and on any other
    pages: str  # 'p. 7', or 'pp. 6–7' for one that runs over pages
    tokens: int | None = None
    shares: int = 0  # characters it shares with the chunk before it on the page
    shares_with: str | None = None  # that chunk's letter
    runs_in_from: int | None = None  # the PDF page it began on, where that is an earlier one
    runs_on_to: int | None = None  # the next PDF page, where it runs on to it
    kept: str | None = None  # a kept edition's chunk (E1.a): "kept: held back from the search"
    # its head after its letter, in the order read: "runs in from p. 6 · 25 characters · pp. 6–7"
    head: list[str]
    blocks: list[ChunkBlock] = []


class PageChunks(BaseModel):
    knowledge_base: KnowledgeBase
    source_id: str
    pdf_page: int
    groups: list[ChunkGroup] = []
    # the mode's head: "this page lies in 4 chunks: A runs in from p. 468; B, C, D begin here"
    head_said: str | None = None
    # quoted text no chunk placed here holds, by block; every quoted block whole where the page has no chunk
    outside: list[ChunkBlock] = []
    not_placed: str | None = None  # how many chunks the index places on the page that could not be placed, in words
    said: str | None = None  # why the page shows no chunk: not in the index here, never embedded, none of this page
    held_back: str | None = None  # a kept edition's chunks (E1.a): kept, and held back from the search
    # how the index cuts a section into chunks: the hint of what a chunk is, and why one repeats the end of the one before
    splitter: html_works.Splitter = html_works.Splitter(**chunking.splitting_config())


class Placed(NamedTuple):
    """A chunk where it stands in the page's quoted text, and the pages it runs in from or on to."""

    start: int
    end: int
    row: tuple
    runs_in_from: int | None
    runs_on_to: int | None


def page_text(blocks: list[Block]) -> tuple[str, list[tuple[str, int, int]]]:
    """The page's quoted text, its quoted blocks' served forms joined, and each block's place in it: (id, start, end)."""
    text, places = '', []
    for block in blocks:
        if not block.served:
            continue
        if text:
            text += JOIN
        places.append((block.id, len(text), len(text) + len(block.served)))
        text += block.served
    return text, places


def places(text: str, part: str) -> list[int]:
    """Every place a part stands in a text, from the last."""
    found, at = [], text.rfind(part)
    while at >= 0:
        found.append(at)
        at = text.rfind(part, 0, at)
    return found


def page_part(section: str, page: str) -> tuple[int, int, int] | None:
    """Where the page's text stands in a section's text, as (start, end) in the section and the page's offset at that start;
    None where the section holds none of it. Each case is checked word for word over all the two hold in common, never taken
    from where a few characters meet alone; where the two meet over fewer than `HEAD` characters, it is not taken at all."""
    if not page or not section:
        return None
    at = section.find(page)
    if at >= 0:  # the whole page
        return at, at + len(page), 0
    within = page.find(section)
    if within >= 0:  # a whole section on the page
        return 0, len(section), within
    for head in places(section, page[:HEAD]):  # the page's beginning ends the section
        if len(section) - head >= HEAD and page.startswith(section[head:]):
            return head, len(section), 0
    for start in places(page, section[:HEAD]):  # the section begins on the page and runs past it
        if len(page) - start >= HEAD and section.startswith(page[start:]):
            return 0, len(page) - start, start
    return None


def chunk_rows(database: Path, index_source: str, pdf_page: int) -> tuple[list[tuple], dict[str, str]] | None:
    """The index's chunks of the page in their order, each (id, section id, text, metadata), and their sections' texts; None
    where the index is not built here. A chunk is the page's where it begins on it, or began before and runs on to it."""
    connection = html_works.connect(database)
    if connection is None:
        return None
    with connection:
        rows = connection.execute(
            "select id, section_id, text, metadata from chunks where source_id = ? and ("
            "json_extract(metadata, '$.pdf_page') = ? or (json_extract(metadata, '$.pdf_page') < ? "
            "and json_extract(metadata, '$.pdf_page_end') >= ?)) order by id", (index_source, pdf_page, pdf_page, pdf_page)).fetchall()
        ids = sorted({row[1] for row in rows})
        sections = dict(connection.execute(f"select id, text from sections where id in ({','.join('?' * len(ids))})", ids).fetchall()
                        ) if ids else {}
    connection.close()
    return rows, sections


def placed_on(page: str, pdf_page: int, rows: list[tuple], sections: dict[str, str]) -> tuple[list[Placed], int]:
    """Each chunk placed in the page's quoted text, in reading order, and how many could not be placed."""
    found: list[Placed] = []
    lost = 0
    by_section: dict[str, list[tuple]] = {}
    for row in rows:
        by_section.setdefault(row[1], []).append(row)
    for section_id, chunks in by_section.items():
        text = sections.get(section_id, '')
        part = page_part(text, page)
        for row, (start, end, _) in zip(chunks, html_works.placed(text, [chunk[2] for chunk in chunks])):
            if part is None or start is None or end is None or end <= part[0] or start >= part[1]:
                lost += 1
                continue
            began = json.loads(row[3] or '{}').get('pdf_page')
            runs_in = int(began) if start < part[0] and began is not None and int(began) < pdf_page else None
            found.append(Placed(max(start, part[0]) - part[0] + part[2], min(end, part[1]) - part[0] + part[2], row, runs_in,
                                pdf_page + 1 if end > part[1] else None))
    return sorted(found, key=lambda chunk: (chunk.start, chunk.end)), lost


def letter(number: int) -> str:
    """A chunk's letter in page order, from 1: A to Z, then AA, AB, as a spreadsheet counts its columns."""
    out = ''
    while number:
        number, rest = divmod(number - 1, 26)
        out = chr(ord('A') + rest) + out
    return out


def runs_of(page: str, begin: int, end: int, others: list[tuple[int, int]]) -> list[ChunkRun]:
    """A span of the page in runs, cut where another chunk's span begins or ends: what another chunk holds too is shared."""
    cuts = sorted({begin, end, *(point for start, stop in others for point in (start, stop) if begin < point < end)})
    runs: list[ChunkRun] = []
    for left, right in zip(cuts, cuts[1:]):
        shared = any(start <= left < stop for start, stop in others)
        if runs and runs[-1].shared == shared:
            runs[-1] = ChunkRun(text=runs[-1].text + page[left:right], shared=shared)
        else:
            runs.append(ChunkRun(text=page[left:right], shared=shared))
    return runs


def a_part(page: str, left: int, right: int, start: int, stop: int) -> bool:
    """Whether a span holds less of a block than the whole, the spaces at its edges aside."""
    return page[left:right].strip() != page[start:stop].strip()


def blocks_in(page: str, places: list[tuple[str, int, int]], classes: dict[str, str], begin: int, end: int,
              others: list[tuple[int, int]]) -> list[ChunkBlock]:
    """The quoted blocks a chunk's span holds, each with what of it the chunk holds: the two spans' common part."""
    out = []
    for block_id, start, stop in places:
        left, right = max(start, begin), min(stop, end)
        if left < right and page[left:right].strip():
            out.append(ChunkBlock(block=block_id, block_class=classes[block_id], part=a_part(page, left, right, start, stop),
                                  runs=runs_of(page, left, right, others)))
    return out


def outside_of(page: str, places: list[tuple[str, int, int]], classes: dict[str, str],
               covered: list[tuple[int, int]]) -> list[ChunkBlock]:
    """The quoted text no placed chunk holds, by block, in the page's order."""
    out = []
    for block_id, start, stop in places:
        at = start
        for left, right in [*sorted(covered), (stop, stop)]:
            if right <= at:
                continue
            until = min(left, stop)
            if left > at and page[at:until].strip():
                out.append(ChunkBlock(block=block_id, block_class=classes[block_id], part=a_part(page, at, until, start, stop),
                                      runs=[ChunkRun(text=page[at:until])]))
            at = max(at, right)
            if at >= stop:
                break
    return out


def groups_of(page: str, pdf_page: int, places: list[tuple[str, int, int]], classes: dict[str, str], placed: list[Placed],
              held_back: str | None) -> list[ChunkGroup]:
    """Each placed chunk as a group: its letter, its head's words, and the quoted blocks it holds."""
    groups: list[ChunkGroup] = []
    spans = [(chunk.start, chunk.end) for chunk in placed]
    for number, chunk in enumerate(placed, 1):
        metadata = json.loads(chunk.row[3] or '{}')
        first = chunk.runs_in_from or pdf_page
        # a chunk running on ends where the index says, at the next page at the least
        last = max(chunk.runs_on_to, int(metadata.get('pdf_page_end') or pdf_page)) if chunk.runs_on_to else pdf_page
        pages = f'p. {first}' if first == last else f'pp. {first}–{last}'
        before = groups[-1] if groups else None
        shares = max(0, placed[number - 2].end - chunk.start) if before else 0
        kept = f'kept: {held_back}' if held_back else None
        head = [*([f'runs in from p. {chunk.runs_in_from}'] if chunk.runs_in_from else []), counted_as(len(chunk.row[2]), 'character'),
                pages, *([f"shares {counted_as(shares, 'character')} with {before.letter}"] if before and shares else []),
                *([f'runs on to p. {chunk.runs_on_to}'] if chunk.runs_on_to else []), *([kept] if kept else [])]
        groups.append(ChunkGroup(
            letter=letter(number), id=chunk.row[0], characters=len(chunk.row[2]), pages=pages, tokens=metadata.get('tokens'),
            shares=shares, shares_with=before.letter if before and shares else None, runs_in_from=chunk.runs_in_from,
            runs_on_to=chunk.runs_on_to, kept=kept, head=head,
            blocks=blocks_in(page, places, classes, chunk.start, chunk.end, spans[:number - 1] + spans[number:])))
    return groups


def head_said(groups: list[ChunkGroup]) -> str:
    """The mode's head in words: how many chunks the page lies in, which run in from a page before, which begin here."""
    running = [f'{group.letter} runs in from p. {group.runs_in_from}' for group in groups if group.runs_in_from]
    here = [group.letter for group in groups if not group.runs_in_from]
    begin = [f"{', '.join(here)} {'begins' if len(here) == 1 else 'begin'} here"] if here else []
    return f"this page lies in {counted_as(len(groups), 'chunk')}: {'; '.join([*running, *begin])}"


def page_chunks(knowledge_base: KnowledgeBase, source_id: str, pdf_page: int, blocks: list[Block], database: Path,
                index_source: str | None, no_index: str, held_back: str | None = None) -> PageChunks:
    """The page as the chunks of semantic search hold it; `index_source` the index's name of its work (a free work's source
    id, a licensed one's work key), `no_index` the words where the index holds nothing of it (not built here, never
    embedded), `held_back` a kept edition's words."""
    page, places = page_text(blocks)
    classes = {block.id: block.block_class for block in blocks}
    answer = PageChunks(knowledge_base=knowledge_base, source_id=source_id, pdf_page=pdf_page, held_back=held_back)
    found = chunk_rows(database, index_source, pdf_page) if index_source else None
    whole = outside_of(page, places, classes, [])
    if found is None:
        return answer.model_copy(update={'said': no_index, 'outside': whole})
    rows, sections = found
    if not rows:
        return answer.model_copy(update={'said': 'no chunk of this page', 'outside': whole})
    placed, lost = placed_on(page, pdf_page, rows, sections)
    not_placed = f"{counted_as(lost, 'chunk')} of this page could not be placed in its quoted text" if lost else None
    groups = groups_of(page, pdf_page, places, classes, placed, held_back)
    return answer.model_copy(update={
        'groups': groups, 'head_said': head_said(groups) if groups else None, 'not_placed': not_placed,
        'outside': outside_of(page, places, classes, [(chunk.start, chunk.end) for chunk in placed])})
