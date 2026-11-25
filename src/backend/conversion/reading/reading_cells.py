"""Which pages a cell reads, with which model, at which resolution, and in which form.

A cell is one arm of a measurement. Its page source is a data file, so phase 2 adds a corpus cell with one line here and
one list of pages: `mini_pilot_pages.json` is tracked and holds free pages only, while a list that names licensed works
lies under `_work/` and never enters the repository.

    {"work_cards": {work: card}, "pages": [{"file", "pdf_page", "work", "gold", "class_note", "expected_output_tokens"}]}

The mini pilot (decision OC-1.a) reads the same 20 pages in four cells: Haiku and Sonnet, each with Markdown blocks and
with JSON through structured outputs.

Phase 2 reads whole works. Such a cell names its works instead of listing 1,652 pages: the PDF, whose checksum the
manifest holds, already fixes which pages there are, and the files and cards come from the page source, so a page the
pilot read gets the same user turn, and with it the same key, and is not bought twice.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from backend.configuration import data_paths

MINI_PILOT = Path(__file__).resolve().parent / 'mini_pilot_pages.json'
PROVENANCE = data_paths.LICENSED_WORKING / 'provenance.json'
LICENSED_ARCHIVE = data_paths.LICENSED_ARCHIVE
FREE_ARCHIVE = data_paths.FREE_RAW

HAIKU, SONNET = 'claude-haiku-5-5', 'claude-sonnet-5-5'
RECHECK_PAGES = ('openstax-accounting:p0455', 'openstax-accounting:p0069', 'openstax-finance-2e:p0393', 'openstax-finance-2e:p0405',
                 'openstax-finance-2e:p0457', 'openstax-finance-2e:p0179', 'carta-conversano-kelly-2020:p0005')


@dataclass(frozen=True)
class Cell:
    name: str
    model: str
    resolution: str
    form: str
    page_source: Path
    replicate: int = 0
    max_tokens: int = 16000
    only: tuple[str, ...] = ()  # page ids; empty means all pages of the source
    whole_works: tuple[str, ...] = ()  # every page of these works instead of the listed pages
    mode: str = 'batch'  # how its readings are bought: Claude's batches, or 'openrouter' for the second reader (63.a)
    reader_version: str = 'page/1'  # the reader's instructions (prompt_versions.json); another is a prototype's (207.a)


CELLS = {cell.name: cell for cell in [
    Cell('MP-HM', HAIKU, 'hi', 'markdown', MINI_PILOT),
    Cell('MP-HJ', HAIKU, 'hi', 'json', MINI_PILOT),
    Cell('MP-SM', SONNET, 'hi', 'markdown', MINI_PILOT),
    Cell('MP-SJ', SONNET, 'hi', 'json', MINI_PILOT),
]}
# The revised prompt, measured again within the mini pilot's budget: every page on Haiku, the pages with findings on Sonnet.
RECHECK_CELLS = {cell.name: cell for cell in [
    Cell('MP2-HM', HAIKU, 'hi', 'markdown', MINI_PILOT),
    Cell('MP2-SM', SONNET, 'hi', 'markdown', MINI_PILOT, only=RECHECK_PAGES),
]}


# Phase 2: the free corpus's four PDFs, every page, read the way the mini pilot chose (Sonnet, Markdown blocks).
FREE_WORKS = ('openstax-finance-2e', 'openstax-accounting', 'carta-conversano-kelly-2020', 'deep-walk-forward-2025',
              'fed-sr-11-7', 'fed-sr-26-2', 'regulation-t',  # since decision 121.b (8 Nov)
              'eu-2017-565', 'reg-nms-600', 'reg-nms-605', 'reg-nms-606')  # since decision 143.a (9 Nov)
CORPUS_OUTPUT_TOKENS = 1900  # for the estimate only: Sonnet's mean on the mini pilot's pages was 1,907
CORPUS_CELLS = {cell.name: cell for cell in [
    Cell('FREE-SM', SONNET, 'hi', 'markdown', MINI_PILOT, whole_works=FREE_WORKS),
]}


# Decision 207.a (the operator, 11 Nov): the reader prompt page/2 as a prototype (147.a), free pages only and never served, since no
# knowledge base names these cells: the mini pilot's 20 pages, 14 with publisher gold, as the gate against page/1, and the
# six pages where the walk of 10 Nov found the reader wrong, each checked by code (`reader_prototype`).
WALK_ERRORS = ('openstax-finance-2e:p0094', 'openstax-finance-2e:p0119', 'openstax-finance-2e:p0387',
               'openstax-accounting:p0305', 'openstax-accounting:p0524', 'openstax-accounting:p0969')
# F4.a (the operator, 18 Nov): page/3, page/1 with one sentence on a backslash printed as text, a prototype the same way: the
# mini pilot's 20 pages as the gate against page/1, and the free pages whose readings failed only on a LaTeX command outside
# math, which page/3 must make valid. Nothing runs before the operator has seen the gate.
BACKSLASH_PAGES = ('carta-conversano-kelly-2020:p0006', 'deep-walk-forward-2025:p0012', 'openstax-finance-2e:p0109',
                   'openstax-finance-2e:p0179', 'openstax-finance-2e:p0229', 'openstax-finance-2e:p0405',
                   'openstax-finance-2e:p0446', 'openstax-finance-2e:p0573', 'openstax-finance-2e:p0575')
READER_PROTOTYPE_CELLS = {cell.name: cell for cell in [
    Cell('P2-MP-SM', SONNET, 'hi', 'markdown', MINI_PILOT, reader_version='page/2'),
    Cell('P2-WALK-SM', SONNET, 'hi', 'markdown', MINI_PILOT, reader_version='page/2',
         whole_works=('openstax-finance-2e', 'openstax-accounting'), only=WALK_ERRORS),
    Cell('P3-MP-SM', SONNET, 'hi', 'markdown', MINI_PILOT, reader_version='page/3'),
    Cell('P3-BS-SM', SONNET, 'hi', 'markdown', MINI_PILOT, reader_version='page/3',
         whole_works=('openstax-finance-2e', 'carta-conversano-kelly-2020', 'deep-walk-forward-2025'), only=BACKSLASH_PAGES),
]}


ROLLOUT = data_paths.LICENSED_WORKING / 'rollout'  # the licensed rounds, written by backend.conversion.reading.rollout


def rollout_cells() -> dict:
    """One cell per round of the licensed rollout (decision 68.a), found from the round files, which never enter the repository."""
    return {f'LIC-R{path.stem[-2:]}': Cell(f'LIC-R{path.stem[-2:]}', SONNET, 'hi', 'markdown', path)
            for path in sorted(ROLLOUT.glob('round_*.json'))}


SECOND_READER_PAGES = {'free': data_paths.FREE_WORKING / 'second_reader' / 'pages.json',  # written by second_reader
                      'licensed': data_paths.LICENSED_WORKING / 'second_reader' / 'pages.json'}
# The second reader's candidates (decision 63.a): models of other companies, through OpenRouter. A pilot chooses one.
SECOND_READERS = {'TERRA': 'openai/gpt-6.1-terra', 'ARGON': 'google/gemini-4-argon', 'MISTRAL': 'mistralai/mistral-large-4-0'}


def second_reader_cells() -> dict:
    """One cell per knowledge base and candidate over the pages the default reader could not give, found from the page
    lists `second_reader pages` writes into the git-ignored stores; read through OpenRouter, never in a Claude batch."""
    prefixes = {'free': 'FREE', 'licensed': 'LIC'}
    return {f'{prefixes[base]}-2ND-{slug}': Cell(f'{prefixes[base]}-2ND-{slug}', model, 'hi', 'markdown', path, mode='openrouter')
            for base, path in SECOND_READER_PAGES.items() if path.exists() for slug, model in SECOND_READERS.items()}


def submittable() -> dict:
    """Every cell a batch may read. Smoke and the free checks walk the four core cells only."""
    return {**CELLS, **RECHECK_CELLS, **CORPUS_CELLS, **READER_PROTOTYPE_CELLS, **rollout_cells()}


REPLAY_PAGES = {'free': data_paths.FREE_WORKING / 'replay' / 'pages.json',  # written by replay, one entry per replayed page
                'licensed': data_paths.LICENSED_WORKING / 'replay' / 'pages.json'}


def replay_cells() -> dict:
    """One cell per knowledge base for pages read again on request (decisions 54.a, 69.a): the default reader over the
    standard API, so a replay never mixes with a batch cell's attempts and has a check report of its own."""
    prefixes = {'free': 'FREE', 'licensed': 'LIC'}
    return {f'REPLAY-{prefixes[base]}': Cell(f'REPLAY-{prefixes[base]}', SONNET, 'hi', 'markdown', path, mode='standard')
            for base, path in REPLAY_PAGES.items() if path.exists()}


DIRECT_PAGES = {'free': data_paths.FREE_WORKING / 'direct' / 'pages.json',  # written by direct_reader pages
                'licensed': data_paths.LICENSED_WORKING / 'direct' / 'pages.json'}
DIRECT_READER = 'claude-opus-5-5'


def direct_cells() -> dict:
    """One cell per knowledge base for pages read in a Claude Code session (decision 280.a, route `direct reading`): the hard
    cases only, never a page a provider's filter blocked or a reader refused; its own cell, so its attempts and its check
    report stand apart from every batch's."""
    prefixes = {'free': 'FREE', 'licensed': 'LIC'}
    return {f'{prefixes[base]}-DIRECT-OPUS': Cell(f'{prefixes[base]}-DIRECT-OPUS', DIRECT_READER, 'hi', 'markdown', path,
                                                  mode='session')
            for base, path in DIRECT_PAGES.items() if path.exists()}


def free_planned_pages() -> set[tuple[str, int]]:
    """(file, PDF page) of every free page a plan holds: every page of the works the corpus cell reads whole (`FREE_WORKS`)
    and a session's pages to read (`DIRECT_PAGES['free']`, why 'unread'). A free PDF outside them is planned nowhere: a
    NoDerivatives work is never read (72.a), and a work taken in later serves its text layer until its reading is decided.
    Found 22 Nov: the view called every unread free page planned, the FIX specification's among them. A whole work whose
    PDF is not on this machine (a clone before `acquire`) adds nothing."""
    cell = CORPUS_CELLS['FREE-SM']
    source = json.loads(Path(cell.page_source).read_text(encoding='utf-8'))
    files = {page['work']: page['file'] for page in source['pages'] + source.get('corpus_works', [])}
    found = set()
    for work in cell.whole_works:
        path = FREE_ARCHIVE / files[work]
        if path.exists():
            with pymupdf.open(path) as document:
                found |= {(files[work], number) for number in range(1, len(document) + 1)}
    direct = DIRECT_PAGES['free']
    if direct.exists():
        found |= {(page['file'], page['pdf_page']) for page in json.loads(direct.read_text(encoding='utf-8')).get('pages', [])
                  if page.get('why') == 'unread'}
    return found


def known_cells() -> dict:
    """Every cell whose readings the check flow and the export can find: the batch cells, the second reader's, the replays,
    the direct readings."""
    return {**submittable(), **second_reader_cells(), **replay_cells(), **direct_cells()}


LICENSED_SOURCES = data_paths.LICENSED_WORKING


def knowledge_base_of(cell: Cell) -> str:
    """The knowledge base a cell reads: licensed when its page list lies with the licensed mirror, which never enters the
    repository (the rollout's rounds and every page list kept beside them); free otherwise."""
    return 'licensed' if Path(cell.page_source).resolve().is_relative_to(LICENSED_SOURCES.resolve()) else 'free'


def knowledge_bases_of(names) -> list[str] | None:
    """The knowledge bases the named cells read, sorted; None when a name is no known cell."""
    known = known_cells()
    if not names or any(name not in known for name in names):
        return None
    return sorted({knowledge_base_of(known[name]) for name in names})


def every_page_of(works: tuple[str, ...], listed: list[dict]) -> list[dict]:
    """Every page of each work, its file taken from the listed pages; a work the list does not name is an error."""
    files = {page['work']: page['file'] for page in listed}
    unknown = [work for work in works if work not in files]
    if unknown:
        raise ValueError(f'no file known for {unknown}')
    pages = []
    for work in works:
        _, path = source_of(files[work])
        with pymupdf.open(path) as document:
            count = len(document)
        pages += [{'file': files[work], 'pdf_page': number, 'work': work, 'gold': False, 'class_note': '',
                   'expected_output_tokens': CORPUS_OUTPUT_TOKENS} for number in range(1, count + 1)]
    return pages


def pages_for(cell: Cell) -> list[dict]:
    """The pages of a cell, each with its id ('openstax-finance-2e:p0179') and its work's card."""
    source = json.loads(Path(cell.page_source).read_text(encoding='utf-8'))
    cards = source['work_cards']
    # A whole work's file comes from the listed pages, or from `corpus_works` for a work with no page in the list (121.b)
    listed = (every_page_of(cell.whole_works, source['pages'] + source.get('corpus_works', [])) if cell.whole_works
              else source['pages'])
    missing = sorted({page['work'] for page in listed} - set(cards))
    if missing:
        raise ValueError(f'{Path(cell.page_source).name}: no work card for {missing}')
    pages = [{**page, 'id': f"{page['work']}:p{page['pdf_page']:04d}", 'work_card': cards[page['work']]} for page in listed]
    return [page for page in pages if not cell.only or page['id'] in cell.only]


def may_send(file_name: str) -> bool:
    """False for files the provenance list holds back (`send: false`, decision 33)."""
    files = json.loads(PROVENANCE.read_text(encoding='utf-8'))['files'] if PROVENANCE.exists() else {}
    return files.get(file_name, {}).get('send', True)


def images_changed_in_place(file_name: str) -> bool:
    """True for a file whose page images were changed under the same name (`image_destamped` in the provenance list: a
    mark covered in the pixels, the operator's 2.a, 25 Nov 2026), so a reading made before may have read another image."""
    files = json.loads(PROVENANCE.read_text(encoding='utf-8'))['files'] if PROVENANCE.exists() else {}
    return bool(files.get(file_name, {}).get('image_destamped'))


def source_of(file_name: str) -> tuple[str, Path]:
    """The mirror and the path of a source PDF: the free corpus if it is there, else the licensed archive."""
    free = FREE_ARCHIVE / file_name
    if free.exists():
        return 'free', free
    licensed = LICENSED_ARCHIVE / file_name
    if licensed.exists():
        return 'licensed', licensed
    raise FileNotFoundError(f'{file_name} is in neither archive')
