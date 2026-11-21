"""A PDF page's chunks in its base's vector index, drawn across the blocks it serves (the operator's W4, 21 Nov: "no new
tab"): in the page view's "as served" mode every quoted block shows the form the search and the chat quote, and where a chunk
of semantic search begins, a dashed line says so, as an HTML section's chunks show, with what it shares with the one before.

A chunk is placed by its text, never by an offset: a chunk is a substring of its section's text (`html_works.placed`, the HTML
sections' own rule), and the page's quoted text, its quoted blocks joined as `served_readings.quotable_text` joins them, is
found in that section's text the same way. A free section runs over pages and may end or begin inside one (a heading starts a
new section mid page), so the page's part of a section is one of four: the whole page, the page's beginning at the section's
end, the section's beginning on the page running past it, or a whole section on the page; in the private index a section is a
page. A chunk that began on an earlier page says so at its top, one running on to the next page at its foot (65.a). A chunk the
index places on the page whose text cannot be found in the page's part of its section is said in words and never drawn.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from backend.diagnostics import html_works
from backend.ingestion import chunking
from backend.diagnostics.readings import Block, KnowledgeBase

HEAD = 16  # the fewest characters of a page and a section that must meet where one runs into the other
JOIN = '\n\n'  # between two quoted blocks of a page, as `served_readings.quotable_text` joins them


class ServedPart(BaseModel):
    """A run of a quoted block's served form: the chunk it belongs to (the later one where two share it), whether it is shared
    with the chunk before, and the chunk that begins where it begins."""

    text: str
    chunk: int | None = None
    shared: bool = False
    starts: int | None = None


class ServedBlock(BaseModel):
    block: str  # the block's id in the reading
    parts: list[ServedPart]


class PageChunk(BaseModel):
    """A chunk of the page as the index embedded it, numbered on the page in reading order: where it stands in the page's
    quoted text (None where it cannot be placed), what it shares with the chunk before, and where it runs from or on to."""

    number: int
    id: str
    start: int | None
    end: int | None
    overlap: int = 0
    tokens: int | None = None
    continues_from: int | None = None  # the PDF page it began on, where that is an earlier one
    continues_on: int | None = None  # the next PDF page, where it runs on to it


class PageChunks(BaseModel):
    knowledge_base: KnowledgeBase
    source_id: str
    pdf_page: int
    chunks: list[PageChunk] = []
    # how many begin on the page, in words: the count the page's semantic level gives (`shelf.semantic_detail` counts a chunk
    # on the page it begins on), a chunk run on from the page before said apart on its own line
    count_said: str | None = None
    blocks: list[ServedBlock] = []  # each quoted block's served form in its runs
    not_placed: str | None = None  # how many chunks the index places on the page that could not be placed, in words
    said: str | None = None  # why the page shows no chunk: not in the index here, never embedded, none of this page
    held_back: str | None = None  # a kept edition's chunks (E1.a): kept, and held back from the search
    # how the index cuts a section into chunks: the hint of the dashed text says from it why a chunk repeats the one before
    splitter: html_works.Splitter = html_works.Splitter(**chunking.splitting_config())


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


def placed_on(page: str, pdf_page: int, rows: list[tuple], sections: dict[str, str]) -> list[PageChunk]:
    """Each chunk where it stands in the page's quoted text, numbered on the page in reading order, those not placed last."""
    found: list[tuple[int | None, int | None, tuple, int | None, int | None]] = []
    by_section: dict[str, list[tuple]] = {}
    for row in rows:
        by_section.setdefault(row[1], []).append(row)
    for section_id, chunks in by_section.items():
        text = sections.get(section_id, '')
        part = page_part(text, page)
        for row, (start, end, _) in zip(chunks, html_works.placed(text, [chunk[2] for chunk in chunks])):
            metadata = json.loads(row[3] or '{}')
            if part is None or start is None or end is None or end <= part[0] or start >= part[1]:
                found.append((None, None, row, None, None))
                continue
            began = metadata.get('pdf_page')
            from_page = began if start < part[0] and began is not None and int(began) < pdf_page else None
            on_page = pdf_page + 1 if end > part[1] else None
            found.append((max(start, part[0]) - part[0] + part[2], min(end, part[1]) - part[0] + part[2], row, from_page, on_page))
    placed = sorted((item for item in found if item[0] is not None), key=lambda item: (item[0], item[1]))
    lost = [item for item in found if item[0] is None]
    out: list[PageChunk] = []
    for number, (start, end, row, from_page, on_page) in enumerate([*placed, *lost], 1):
        before = out[-1] if out and out[-1].end is not None else None
        overlap = max(0, before.end - start) if before is not None and start is not None else 0
        out.append(PageChunk(number=number, id=row[0], start=start, end=end, overlap=overlap,
                             tokens=json.loads(row[3] or '{}').get('tokens'), continues_from=from_page, continues_on=on_page))
    return out


def parts_of(page: str, places: list[tuple[str, int, int]], chunks: list[PageChunk]) -> list[ServedBlock]:
    """Each quoted block's served form in runs: cut where a chunk begins or ends and where two chunks stop sharing; a chunk
    that begins between two blocks begins with the next one."""
    placed = [chunk for chunk in chunks if chunk.start is not None and chunk.end is not None]
    out = []
    for block_id, begin, end in places:
        starts = {max(chunk.start, begin): chunk.number for chunk in placed if chunk.start < end and chunk.end > begin
                  and (chunk.start >= begin or page[chunk.start:begin].strip() == '')}
        cuts = sorted({begin, end, *(point for chunk in placed for point in (chunk.start, chunk.end) if begin < point < end)})
        parts = []
        for left, right in zip(cuts, cuts[1:]):
            covering = [chunk for chunk in placed if chunk.start <= left < chunk.end]
            parts.append(ServedPart(text=page[left:right], chunk=covering[-1].number if covering else None,
                                    shared=len(covering) > 1, starts=starts.get(left)))
        out.append(ServedBlock(block=block_id, parts=parts))
    return out


def page_chunks(knowledge_base: KnowledgeBase, source_id: str, pdf_page: int, blocks: list[Block], database: Path,
                index_source: str | None, no_index: str, held_back: str | None = None) -> PageChunks:
    """The page's chunks in its quoted blocks; `index_source` the index's name of its work (a free work's source id, a licensed
    one's work key), `no_index` the words where the index holds nothing of it (not built here, never embedded)."""
    page, places = page_text(blocks)
    answer = PageChunks(knowledge_base=knowledge_base, source_id=source_id, pdf_page=pdf_page, held_back=held_back)
    found = chunk_rows(database, index_source, pdf_page) if index_source else None
    if found is None:
        return answer.model_copy(update={'said': no_index, 'blocks': parts_of(page, places, [])})
    rows, sections = found
    if not rows:
        return answer.model_copy(update={'said': 'no chunk of this page', 'blocks': parts_of(page, places, [])})
    chunks = placed_on(page, pdf_page, rows, sections)
    begin = sum(1 for row in rows if json.loads(row[3] or '{}').get('pdf_page') == pdf_page)
    count_said = f"{begin} {'chunk' if begin == 1 else 'chunks'} of semantic search {'begins' if begin == 1 else 'begin'} on this page"
    lost = sum(1 for chunk in chunks if chunk.start is None)
    not_placed = (f"{lost} {'chunk' if lost == 1 else 'chunks'} of this page could not be placed in its quoted text"
                  if lost else None)
    return answer.model_copy(update={'chunks': chunks, 'blocks': parts_of(page, places, chunks), 'not_placed': not_placed,
                                     'count_said': count_said})
