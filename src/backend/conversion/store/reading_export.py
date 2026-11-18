"""The page readings of both knowledge bases as files beside their trace, in one shape for the views and the chat (72.a, 80.a).

The reading store is git-ignored, because it holds both mirrors' working data. This writes the latest reading of every page read
so far to `<export>/<work>/pNNNN.md`, byte for byte as the reader returned it, and one `index.json`: the works, each with the id
the views link by, its title, its PDF and its own outline as the chat's sections cut it (decision 84.a), and one row per page
with its trace. A row names its knowledge base first (decision 80.a), then the outline's units whose text lies on the page, the
reading's key and hash, model, attempt, cost, its class when collected and under today's validator, the printed page label the
reader found, the provider's message where the provider refused the page, and the check flow's state with the judge's verdict,
or why the page was not judged.

- free: `_data/corpus/readings/`, kept in the local data folder (decisions 72.a, 264.a, 282), with the attribution its licences ask for in a README (CC BY 4.0,
  CC BY-NC-SA 4.0). Only free sources are read there.
- licensed: `_work/licensed/readings/`, git-ignored like every top-level `_` folder and refused anywhere git would track it:
  the operator's private data, local only, never committed and never in the recorded review (decision 81.a). A clone has none.

    python -m backend.conversion.store.reading_export                              # spends nothing; again after any reading or check run
    python -m backend.conversion.store.reading_export --knowledge-base licensed
"""

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from backend.configuration import data_paths
from backend.constants.reading_constants import DIRECT_DEVIATION
from backend.conversion.checks import check_flow, check_run
from backend.conversion.judge import page_judge
from backend.conversion.reading import reader_requests, reading_cells, vision_batches
from backend.conversion.store import reading_store
from backend.conversion.store.reading_store import REPO, open_store

FROZEN = json.loads((REPO / 'src' / 'backend' / 'conversion' / 'frozen_contract.json').read_text(encoding='utf-8'))
CATALOG = REPO / 'corpus' / 'catalog.json'
OUTLINES = 'outlines.json'  # in the store's reports: each PDF's outline, by what it was computed from
QUOTED = 'quoted'  # in the store's reports: each PDF's quoted page texts, one file per PDF, cut with its outline
DECIDED_STOPS = 'decided_stops.json'  # in the store's reports: the stops a person decided, {"stops": {cell: [work, ...]}}


@dataclass(frozen=True)
class KnowledgeBase:
    """Where one knowledge base's readings come from and where they go."""
    name: str                             # 'free' or 'licensed': the first key of every row (decision 80.a)
    export: Path
    pdfs: Path                            # the folder of its PDFs, named in each work
    cells: Callable[[], tuple[str, ...]]  # the cells whose readings it holds, looked up when it is exported
    tracked: bool                         # a tracked export carries the README with its licences; an untracked one never lands in git


FREE = KnowledgeBase('free', data_paths.FREE_READINGS, data_paths.FREE_RAW, lambda: ('FREE-SM',), tracked=True)
LICENSED = KnowledgeBase('licensed', data_paths.LICENSED_WORKING / 'readings', data_paths.LICENSED_ARCHIVE,
                         lambda: tuple(sorted(reading_cells.rollout_cells())), tracked=False)
BASES = {base.name: base for base in (FREE, LICENSED)}
ABOUT = {'free': 'The latest reading of every free PDF page and its trace (decisions 72.a, 80.a). Written by '
                 'python -m backend.conversion.store.reading_export; do not edit by hand.',
         'licensed': 'The latest reading of every licensed PDF page read so far and its trace (decision 80.a): private, local only, '
                     'never committed. Written by python -m backend.conversion.store.reading_export --knowledge-base licensed.'}


def check_states(store, cells: tuple[str, ...]) -> dict:
    """The check flow's state per reading key, from each cell's own report, and the judge's verdict where it ran.

    The free corpus has one cell, the licensed rollout one per round, and the rounds' pages never overlap. A report over several
    cells at once is an older run's and is never read: the one of 3 Nov over FREE-SM and MP2-SM still holds the free pages' states
    from before the refused class (75.a), and read after the current one it put a refused page back among the issues."""
    judgements = check_run.verdicts_by_target(store)  # never a planted copy's
    decided = decided_stops(store)
    states = {}
    for cell in cells:
        path = store.path('reports', f'check_report_{cell}.json')
        if not path.exists():
            continue
        plan_path = store.path('reports', f'check_plan_{cell}.json')
        stage2 = json.loads(plan_path.read_text(encoding='utf-8')).get('stage2', {}) if plan_path.exists() else {}
        for row in json.loads(path.read_text(encoding='utf-8'))['pages']:
            judgement = judgements.get(row['key'])
            verdict = judgement and check_run.voided(store, judgement['verdict'], row['key'])  # a self-contradicting finding is void (146.a)
            judged = ('in the random sample' if row['in_sample'] else 'suspicious in stage 2' if row['suspicious']
                      else 'a block stage 2 cannot check' if row.get('unverifiable')  # since decision 83.a
                      else 'a replay, judged on request' if row.get('replayed')  # since decision 69.a
                      else "a re-read after the judge's issue" if row.get('reread') else None)  # since decision 133.b
            state = check_flow.current_state(row['state'])
            if (cell, row.get('work')) in decided and state in ('ok', 'ok_unjudged'):  # an older row names no work
                state = 'stopped'  # a person's stop holds whatever the report's sample now says (130.a)
            states[row['key']] = {'state': state, 'reasons': row['reasons'], 'judged': judged is not None and verdict is not None,
                                  'why_judged': judged or 'not judged: passed stages 1 and 2, outside the sample',
                                  'verdict': verdict and {'verdict': verdict['verdict'], 'outcome': check_flow.current_state(verdict['outcome']),
                                                          **({'judge_outcome': check_flow.current_state(verdict['judge_outcome']),
                                                              'void': verdict['void']} if verdict.get('void') else {}),
                                                          'findings': [{'kind': finding.get('kind', 'other'), 'block': finding.get('block'),
                                                                       'severity': finding.get('severity'),
                                                                       'evidence': finding.get('evidence'),
                                                                       **({'void': True} if finding.get('void') else {})}
                                                                      for finding in verdict['findings']]},
                                  'judge': judgement and {'model': judgement.get('model'), 'provider': 'anthropic',
                                                          'mode': judgement.get('mode'), 'cost_usd': judgement.get('cost_usd'),
                                                          'version': page_judge.version_of(judgement)},
                                  'stage2': stage2_of(stage2.get(row['key']))}
    return states


def stage2_of(summary: dict | None) -> dict | None:
    """Stage 2 of one reading as its plan kept it: in full since 9 Nov (each finding with its block and detail, each block it
    could not check with why), as kinds and reasons alone in a plan written before. Never page text."""
    if summary is None:
        return None
    findings = [finding if isinstance(finding, dict) else {'kind': finding} for finding in summary.get('findings', [])]
    unverifiable = [item if isinstance(item, dict) else {'why': item} for item in summary.get('unverifiable', [])]
    return {**summary, 'findings': findings, 'unverifiable': unverifiable}


def decided_stops(store) -> set[tuple[str, str]]:
    """(cell, work) for every stop a person decided, kept in the store beside the reports, never tracked (it names works).

    A report's stop follows its sample, and the sample follows the cell's pages: when a second reader's cell came to hold
    every page its reader read (18 Nov), the sample of a work a person had stopped grew, and its share of bad pages fell
    under the gate. A stop a person decided (130.a) is the person's, not the gate's, so it is kept apart from every report
    and holds over each of them.
    """
    path = store.path('reports', DECIDED_STOPS)
    if not path.exists():
        return set()
    return {(cell, work) for cell, works in json.loads(path.read_text(encoding='utf-8'))['stops'].items() for work in works}


def stopped_works(store, cells: tuple[str, ...]) -> set[tuple[str, str]]:
    """(cell, work) for every work a cell's report stopped or a person stopped for it: its readings there are not served."""
    stopped = {pair for pair in decided_stops(store) if pair[0] in cells}
    for cell in cells:
        path = store.path('reports', f'check_report_{cell}.json')
        if path.exists():
            report = json.loads(path.read_text(encoding='utf-8'))  # a replay's one-page report has no works
            stopped |= {(cell, work) for work, row in report.get('works', {}).items() if row.get('stopped')}
    return stopped


def earlier_state(record: dict, judgements: list[dict] | None, stopped: set[tuple[str, str]]) -> dict | None:
    """The state of a reading no current report holds, from its own counted verdict: a reading chosen before a later one of the
    same page was planned (found 9 Nov: readings chosen on one day, their cell planned again on a later one). Its cell's
    stop holds for it too (decision 130.a). None where no counted verdict exists: then it is not served at all."""
    counted = [judgement for judgement in judgements or [] if judgement['counts']]
    if not counted:
        return None
    last = counted[-1]
    state = 'ok' if last['outcome'] == 'ok' else 'issue'
    if state == 'ok' and (record.get('cell'), record['work']) in stopped:
        state = 'stopped'
    reasons = [] if state != 'issue' else [f"judge: {last['verdict']}"] + [finding.get('kind', 'other') for finding in last['findings']]
    return {'state': state, 'reasons': reasons, 'judged': True, 'why_judged': 'an earlier check: its own verdict, outside the reports',
            'verdict': {'verdict': last['verdict'], 'outcome': last['outcome'], 'findings': last['findings']},
            'judge': {'model': last['model'], 'provider': 'anthropic', 'mode': last['mode'], 'cost_usd': last['cost_usd'],
                      'version': last['version']}, 'stage2': None}


def _named(path: Path) -> str:
    """A path as the rows name it: in the repository's layout where it lies inside (the data as if in place), else as it is."""
    return data_paths.stored(path)


def works_of(base: KnowledgeBase, read: list[tuple[str, str]]) -> list[dict]:
    """Each work read so far, (work, file) pairs, with the id the views link by, its title and its PDF. A free work takes both from
    the catalog. A licensed work has no catalog, so its file's stem is its id and its title, as on the search server."""
    catalog = {}
    if base.name == 'free' and CATALOG.exists():
        catalog = {entry['path'].rsplit('/', 1)[-1]: source
                   for source in json.loads(CATALOG.read_text(encoding='utf-8'))['sources'] for entry in source['files']}
    works = []
    for work, file in read:
        source = catalog.get(file)
        works.append({'knowledge_base': base.name, 'work': work, 'source_id': source['id'] if source else Path(file).stem,
                      'title': source['title'] if source else Path(file).stem, 'file': file, 'pdf': _named(base.pdfs / file)})
    return works


def outline_key(pdf: Path, rows: list[dict]) -> str:
    """What a PDF's outline is computed from: the loader's version, the PDF's bytes, and each page's route and reading text."""
    from backend.ingestion.clean_sections import pdf_sections

    digest = hashlib.sha256()
    with pdf.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    pages = sorted((row['pdf_page'], row['route'], row.get('text_sha256')) for row in rows)
    return hashlib.sha256(json.dumps([pdf_sections.LOADER_VERSION, digest.hexdigest(), pages]).encode('utf-8')).hexdigest()


def outlines_of(base: KnowledgeBase, store, works: list[dict], rows: list[dict]) -> dict:
    """File -> each work's own outline and, per PDF page, the units whose text lies on it (decision 84.a); None where its PDF is
    missing. The outline is cut by the chat index's own loader over the same pages, the served readings in place, so the views
    order a work the way its sections are cut. Kept in the store by what it was computed from, since cutting the accounting book
    takes about a minute: only a PDF whose bytes, loader or served pages changed is cut again."""
    from backend.conversion.store.served_readings import served_pages
    from backend.ingestion.clean_sections import pdf_sections

    cache_path = store.path('reports', OUTLINES)
    cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    found, kept = {}, {}
    for work in works:
        pdf = base.pdfs / work['file']
        if not pdf.exists():
            found[work['file']] = None
            continue
        own = [row for row in rows if row['file'] == work['file']]
        key = outline_key(pdf, own)
        quoted = quoted_path(store, work['file'])
        if key not in cache or not quoted.exists() or json.loads(quoted.read_text(encoding='utf-8')).get('key') != key:
            text = pdf_sections.read_pdf(pdf, served_pages(work['file'], own, base.export))
            outline = pdf_sections.outline_of(text.outline_toc, text.pages, fold_headings=text.toc_source == 'readings')
            cache[key] = {'units': [asdict(unit) for unit in outline.units],
                          'page_units': {str(page): units for page, units in sorted(outline.page_units.items())}}
            store.write_report(f'{QUOTED}/{Path(work["file"]).stem}.json',
                               {'key': key, 'file': work['file'], 'pages': {str(number): page for number, page in enumerate(text.pages, 1)}})
        found[work['file']] = kept[key] = cache[key]
    store.write_report(OUTLINES, kept)  # today's outlines only, so the file never keeps a stale one
    return found


def quoted_path(store, file_name: str) -> Path:
    return store.path('reports', QUOTED, Path(file_name).stem + '.json')


def quoted_pages(knowledge_base: str, file_name: str) -> dict[int, str]:
    """PDF page -> the text the search and the chat quote for it (decision 93.a): the page's served reading as quotable text,
    or its text layer cleaned of running heads and page numbers with tables as rows, exactly as the chat's sections are cut
    from it (`pdf_sections.read_pdf`). Written by the export with each PDF's outline; on a machine where the export has not
    run, cut now from the export's rows and kept. One function for every reader of a page, so no two can quote it apart."""
    from backend.conversion.store.served_readings import served_pages
    from backend.ingestion.clean_sections import pdf_sections

    base = BASES[knowledge_base]
    store = open_store(base.name)
    path = quoted_path(store, file_name)
    if not path.exists():
        rows = [row for row in json.loads((base.export / 'index.json').read_text(encoding='utf-8'))['pages'] if row['file'] == file_name]
        pdf = base.pdfs / file_name
        text = pdf_sections.read_pdf(pdf, served_pages(file_name, rows, base.export))
        store.write_report(f'{QUOTED}/{Path(file_name).stem}.json',
                           {'key': outline_key(pdf, rows), 'file': file_name,
                            'pages': {str(number): page for number, page in enumerate(text.pages, 1)}})
    return {int(number): page for number, page in json.loads(path.read_text(encoding='utf-8'))['pages'].items()}


def cells_beside(base: KnowledgeBase) -> tuple[str, ...]:
    """The cells beside the default ones whose readings may stand for a page of this knowledge base: the second reader's
    (63.a), the replays (69.a) and the direct readings (280.a). Their check reports hold the states of the readings chosen
    there."""
    prefix = 'FREE' if base.name == 'free' else 'LIC'
    beside = {**reading_cells.second_reader_cells(), **reading_cells.replay_cells(), **reading_cells.direct_cells()}
    return tuple(sorted(name for name in beside if name.startswith((f'{prefix}-2ND-', f'REPLAY-{prefix}', f'{prefix}-DIRECT-'))))


def too_few_to_export(base: KnowledgeBase, readings: int) -> str | None:
    """Why an export must not run here, or None. A clone holds the free export but not the store it is written from;
    run there (by hand, or after a verdict from the page view, decision 213.b) it would write an empty index and delete
    every reading text as stale. So the export refuses when the store holds fewer than half the pages the export it would
    replace already has."""
    index = base.export / 'index.json'
    if not index.exists():
        return None
    exported = len(json.loads(index.read_text(encoding='utf-8')).get('pages') or [])
    if exported and readings < exported / 2:
        return (f'the {base.name} store here holds {readings} readings for an export of {exported} pages: a clone has the '
                'export but not the store it is written from, so nothing is written')
    return None


def replace_file(path: Path, data: bytes) -> None:
    """Write a file whole or not at all: a view reading it while the export runs in the background (decision 213.b) sees
    the old file or the new one, never half of one."""
    partial = path.with_name(f'.{path.name}.partial')
    partial.write_bytes(data)
    os.replace(partial, path)


def prototypes_beside(base: KnowledgeBase) -> tuple[str, ...]:
    """The reader prototypes' cells of this knowledge base (decision 210.a): their readings stand in a page's history as
    attempts, marked as a prototype's, and never in its choice, its check states or its route (147.a)."""
    return tuple(sorted(name for name, cell in reading_cells.READER_PROTOTYPE_CELLS.items()
                        if reading_cells.knowledge_base_of(cell) == base.name))


CATEGORY_OF_KIND = {  # the reader's page_kind, as a person sorts pages (decision 172.a, the operator, 10 Nov)
    'body': 'content', 'chapter_opener': 'content', 'part_opener': 'content', 'slide': 'content', 'plate': 'content',
    'index': 'index', 'toc': 'contents', 'front_matter': 'front matter', 'copyright': 'front matter', 'cover': 'cover',
    'back_matter': 'back matter', 'blank': 'blank', 'ad': 'advertisement'}


def category_of(page_kind: str | None, unit_titles: list[str], exercise_titles: set[str]) -> str | None:
    """A page's category: what the reader called its kind, and 'exercise' for a content page whose every outline unit is an
    exercise section (the sections retrieval demotes, phase 6). Such pages stay in the holding and out of the answers' way;
    an issue on them is noted, not repaired (decisions 169.a, 172.a). None where no reading named the kind."""
    category = CATEGORY_OF_KIND.get(page_kind or '')
    if category == 'content' and unit_titles and all(title in exercise_titles for title in unit_titles):
        return 'exercise'
    return category


def purpose_of(record: dict) -> str:
    """What a reading was, in words, from the fields it was stored with, so a view never has to guess it (line 2's finding of
    10 Nov: four readings of accounting p. 524 read "attempt 2, attempt 0, attempt 1, attempt 0")."""
    prototype = reading_cells.READER_PROTOTYPE_CELLS.get(record.get('cell') or '')
    if prototype is not None:
        return f'a reader prototype ({prototype.reader_version}), never served'
    if str(record.get('cell') or '').startswith('REPLAY'):
        return 'read again by a replay'
    if record.get('deviation') == DIRECT_DEVIATION:  # 280.a
        return 'direct reading in a Claude Code session' + (', a format retry' if record.get('attempt') else '')
    if record.get('deviation'):
        return 'second reader'
    if record.get('retry_of'):
        return "read again with the judge's findings as a hint"
    attempt = record.get('attempt', 0)
    if attempt == vision_batches.HINTED_AFTER_PLAIN_RETRY:
        return 'format retry with the errors as a hint, after a plain retry'
    if attempt == vision_batches.RETRY_ATTEMPT:
        return 'the one format retry'
    return 'first reading'


def attempts_of(store, cells: tuple[str, ...]) -> dict[tuple[str, int], list[dict]]:
    """Every reading of each page, oldest first: the default reader's attempts and a second reader's, each with its class under
    today's validator and what it was (`purpose_of`), so a view can show a page's history and which of them stands (decision
    69.a)."""
    found: dict[tuple[str, int], list[dict]] = {}
    for record in sorted(vision_batches.readings_of(cells, store), key=lambda record: record.get('stored_at') or ''):
        prototype = reading_cells.READER_PROTOTYPE_CELLS.get(record.get('cell') or '')
        found.setdefault((record['file'], record['pdf_page']), []).append({
            'reading_key': record['reading_key'], 'model': record.get('model'), 'mode': record.get('mode'),
            'reader_version': prototype.reader_version if prototype else reader_requests.FIRST_VERSION,
            **({'prototype': True} if prototype else {}),  # decision 210.a: shown beside the served one, never served
            'attempt': record.get('attempt', 0), 'purpose': purpose_of(record), 'cell': record.get('cell'),
            'retry_of': record.get('retry_of'), 'class_now': vision_batches.current_class(record, store),
            'stored_at': record.get('stored_at'), 'deviation': record.get('deviation'),
            'provider': record.get('provider', 'anthropic'), 'upstream': record.get('response_provider'),  # who served a 2nd reader
            'cost_usd': cost_of(record), 'format_errors': format_errors(record, store)})
    return found


def format_errors(record: dict, store) -> list[str] | None:
    """What the format check found wrong with an attempt under today's validator, in its own words (they name lines, blocks
    and attributes): the "why" a page's history lacked for a malformed reading (the operator, 18 Nov: "what exactly was it?").
    At most as many and as long as a format retry's hint is told; None for an attempt that passed or never succeeded."""
    if record.get('result_type') != 'succeeded':
        return None
    errors = vision_batches.stage_one_errors(record, store)
    return [error[:vision_batches.HINT_ERROR_CHARS] for error in errors[:vision_batches.HINT_ERRORS]] or None


def cost_of(record: dict) -> float | None:
    """What an attempt cost in USD, or None where it cannot be measured: a reading in a Claude Code session (280.a) is paid
    by the plan's usage, not by an API, and 0.0 would claim it was free (the operator, 18 Nov)."""
    if record.get('mode') == 'session':
        return None
    return record.get('cost_usd', 0.0)


def attempt_check(state: dict | None, judgements: list[dict] | None = None) -> dict | None:
    """One attempt's check in brief, beside it in the page's history: the flow's state and the judge's verdict where it ran;
    None where no check ran on that reading (line 2's request, 5 Nov). The chosen reading's full check stays in `check`.

    An earlier attempt the current reports no longer hold keeps the verdict it was judged with (the operator, 9 Nov: the first reading
    of finance p. 5 showed "not checked", though the judge had found it bad, which is why it was read again)."""
    if state is None:
        counted = [judgement for judgement in judgements or [] if judgement['counts']]
        if not counted:
            return None
        last = counted[-1]
        return {'state': 'ok' if last['outcome'] == 'ok' else 'issue', 'verdict': last['verdict'], 'outcome': last['outcome'],
                'from': 'an earlier check'}
    verdict = state.get('verdict') or {}
    return {'state': state['state'], 'verdict': verdict.get('verdict'), 'outcome': verdict.get('outcome'),
            'reasons': state.get('reasons') or []}  # why the flow gave that state: "malformed", "judge: bad", a finding's kind


def human_of(verdicts: list[dict], reading_key: str, resets: list[dict] | None = None) -> list[dict]:
    """A page's verdicts by a person, oldest first, each saying whether it applies to the reading that stands: a verdict was
    given on the reading the person saw, and never carries over to a later one by itself (decision 146.a). A verdict given
    before the page's latest reset is archived: kept, shown, and no longer applying (decision 191.a)."""
    from backend.conversion.store import pipeline_db

    standing = {id(verdict) for verdict in pipeline_db.since_last_reset(verdicts, resets or [])}
    return [{'reading_key': verdict['reading_key'], 'applies': verdict['reading_key'] == reading_key and id(verdict) in standing,
             'archived': id(verdict) not in standing, 'block': verdict['block'],
             'verdict': verdict['verdict'], 'reason': verdict['reason'], 'reason_text': pipeline_db.HUMAN_REASONS[verdict['reason']],
             'tag': verdict['tag'], 'note': verdict['note'], 'given_by': verdict['given_by'], 'given_at': verdict['given_at'],
             # a person's manual parts (188.a), marked as theirs: the block's text as they say it reads, and their rating of the judge
             'correction': verdict.get('correction'), 'judge_assessment': verdict.get('judge_assessment'),
             'judge_assessment_text': pipeline_db.JUDGE_ASSESSMENTS.get(verdict.get('judge_assessment') or '')}
            for verdict in verdicts]


def with_block_classes(state: dict | None, parsed) -> dict | None:
    """A reading's check with the class of each finding's block, so the serving rule can tell a finding on a quoted block from
    one on a block never quoted (decision 133.b). A finding on the page as a whole, or on a block the reading lacks, gets none."""
    if not state or not state.get('verdict') or parsed is None:
        return state
    classes = {block.id: block.cls for block in parsed.blocks}
    findings = [{**finding, 'block_class': classes.get(finding.get('block'))} for finding in state['verdict']['findings']]
    return {**state, 'verdict': {**state['verdict'], 'findings': findings}}


def with_people(base: KnowledgeBase, store, records: list[dict]) -> list[dict]:
    """What a person said about a page's reading, applied (decision 191.a): the reading a person accepted stays the page's
    reading, unless a choice made after the accept names another (a replay a person ran over it on purpose); a reading a
    person's reset discarded carries the reset, so the page serves its text layer until a new reading stands."""
    from backend.conversion.store import pipeline_db

    verdicts, resets = pipeline_db.human_verdicts(base.name), pipeline_db.page_resets(base.name)
    out = []
    for record in records:
        page = (record['file'], record['pdf_page'])
        counting = pipeline_db.since_last_reset(verdicts.get(page, []), resets.get(page, []))
        accepts = [verdict for verdict in counting if verdict['verdict'] == 'accept']
        if accepts and accepts[-1]['reading_key'] != record['reading_key']:
            chosen_after = (record.get('chosen') or {}).get('chosen_at', '') > accepts[-1]['given_at']
            pinned = store.reading(accepts[-1]['reading_key'])
            if pinned is not None and not chosen_after:
                record = {**pinned, 'pinned_by_a_person': accepts[-1]['given_at']}
        discarded = [reset for reset in resets.get(page, []) if reset['reading_key'] == record['reading_key']]
        if discarded:
            record = {**record, 'reset': {key: discarded[-1][key] for key in ('reason', 'given_by', 'given_at')}}
        out.append(record)
    return out


def with_choices(base: KnowledgeBase, store, records: list[dict]) -> list[dict]:
    """Each page's latest attempt, unless the pipeline database names another reading for it (decision 47.a): a replay's new
    attempt, or a second reader's reading where the default one could not be served. The record then carries the choice."""
    from backend.conversion.store import pipeline_db

    choices = pipeline_db.chosen(base.name)
    out = []
    for record in records:
        choice = choices.get((record['file'], record['pdf_page']))
        if choice is not None and choice['reading_key'] != record['reading_key']:
            named = store.reading(choice['reading_key'])
            if named is not None:
                record = {**named, 'chosen': {key: choice[key] for key in ('why', 'run_id', 'chosen_at')}}
        out.append(record)
    return out


def export(base: KnowledgeBase = FREE, store=None) -> dict:
    """Write one knowledge base's readings and their index; returns the index.

    Raises:
        reading_store.UnsafeRootError: When an untracked knowledge base's export would lie where git tracks it.
    """
    from backend.conversion.contract.page_contract import parse
    from backend.conversion.store.served_readings import printed_of, route_level, route_of

    if not base.tracked:
        reason = reading_store.refusal(base.export.resolve())
        if reason:
            raise reading_store.UnsafeRootError(f'the {base.name} readings are never exported there: {reason}')
    store = store or open_store(base.name)
    cells = base.cells()
    standing = check_run.latest_per_page(vision_batches.readings_of(cells, store),  # a failed re-read displaces no valid reading (174.a)
                                         valid=lambda record: vision_batches.current_class(record, store) == 'ok')
    refusal = too_few_to_export(base, len(standing))
    if refusal:
        raise RuntimeError(refusal)
    records = with_people(base, store, with_choices(base, store, standing))
    states = check_states(store, cells + cells_beside(base))
    attempts = attempts_of(store, cells + cells_beside(base) + prototypes_beside(base))  # a prototype is listed, never chosen
    judgements = check_run.judgements_by_target(store)  # every verdict of every reading, any version or purpose
    from backend.conversion.store import pipeline_db

    people = pipeline_db.human_verdicts(base.name)
    resets = pipeline_db.page_resets(base.name)
    stopped = stopped_works(store, cells + cells_beside(base))
    for record in records:  # a chosen reading no current report holds keeps the state of its own verdict
        if record['reading_key'] not in states:
            earlier = earlier_state(record, judgements.get(record['reading_key']), stopped)
            if earlier is not None:
                states[record['reading_key']] = earlier
    works = works_of(base, sorted({(record['work'], record['file']) for record in records}))
    source_ids = {work['file']: work['source_id'] for work in works}
    rows, written = [], set()
    for record in records:
        text = store.reading_text(record['reading_key']) if record.get('result_type') == 'succeeded' else None
        class_now = vision_batches.current_class(record, store)
        read = parse(text, record['form']) if text else None  # a malformed reading still names its page's kind
        parsed = read if class_now == 'ok' else None
        row = {'knowledge_base': base.name, 'work': record['work'], 'file': record['file'], 'pdf_page': record['pdf_page'],
               'printed_label': printed_of(parsed) if parsed is not None else None,
               'unit': None, 'units': None,  # from the work's outline below
               'page_kind': read.front.get('page_kind') if read is not None else None, 'category': None,  # below (172.a)
               'reading_key': record['reading_key'], 'model': record['model'], 'form': record['form'], 'contract': FROZEN['contract'],
               'validator': FROZEN['validator'], 'attempt': record.get('attempt', 0), 'cost_usd': cost_of(record),
               'stored_at': record.get('stored_at'), 'image_sha256': record.get('image_sha256'), 'image_size': record.get('image_size'),
               'resolution': record.get('resolution'), 'class_when_collected': record['result_class'], 'class_now': class_now,
               'error_type': record.get('error_type'), 'error_message': record.get('error_message'),  # the provider's words, never page text
               'deviation': record.get('deviation'), 'chosen': record.get('chosen'),  # why a reading off the default stands here
               'attempts': [{**attempt, 'check': attempt_check(states.get(attempt['reading_key']), judgements.get(attempt['reading_key'])),
                             'judgements': judgements.get(attempt['reading_key'], [])}
                            for attempt in attempts.get((record['file'], record['pdf_page']), [])],
               'check': with_block_classes(states.get(record['reading_key']), parsed),
               'human': human_of(people.get((record['file'], record['pdf_page']), []), record['reading_key'],
                                 resets.get((record['file'], record['pdf_page']), [])),
               # decision 191.a: a page a person checked is protected from being read again; a reset lifts it and discards
               'protected': bool(pipeline_db.since_last_reset(people.get((record['file'], record['pdf_page']), []),
                                                              resets.get((record['file'], record['pdf_page']), []))),
               'reset': record.get('reset'), 'pinned_by_a_person': record.get('pinned_by_a_person')}
        if text:
            relative = f"{record['work']}/p{record['pdf_page']:04d}.md"
            target = base.export / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            data = text.encode('utf-8')
            if not target.exists() or target.read_bytes() != data:
                replace_file(target, data)
            row.update(text_file=relative, text_sha256=hashlib.sha256(data).hexdigest())
            written.add(target)
        row.update(source_id=source_ids[record['file']], route=route_of(row),  # the id the views link by; the route the server serves
                   route_level=route_level(row))  # checked, noted or fallback (the operator, 10 Nov)
        rows.append(row)
    base.export.mkdir(parents=True, exist_ok=True)
    for stale in base.export.glob('*/p*.md'):
        if stale not in written:
            stale.unlink()
    outlines = outlines_of(base, store, works, rows)
    for work in works:
        work['outline'] = outlines[work['file']] and outlines[work['file']]['units']
    from backend.chat import app_config

    exercise_titles = set(app_config.load().get('retrieval', {}).get('demote_sections') or ())
    for row in rows:
        outline = outlines[row['file']]
        if outline is not None:  # None where the PDF is missing: unknown, not empty
            row['units'] = outline['page_units'].get(str(row['pdf_page']), [])
            row['unit'] = row['units'][0] if row['units'] else None
        titles = {unit['id']: unit['title'] for unit in (outline or {}).get('units') or []}
        row['category'] = category_of(row['page_kind'], [titles[unit] for unit in row['units'] or [] if unit in titles],
                                      exercise_titles)
    index = {'about': ABOUT[base.name], 'knowledge_base': base.name, 'cells': list(cells), 'works': works, 'pages': rows}
    replace_file(base.export / 'index.json', (json.dumps(index, indent=1, ensure_ascii=False) + '\n').encode('utf-8'))
    if base.tracked:
        replace_file(base.export / 'README.md', readme(sorted({row['file'] for row in rows})).encode('utf-8'))
    print(f'{base.name}: {len(rows)} pages, {len(written)} reading texts written to {_named(base.export)}')
    return index


def readme(files: list[str]) -> str:
    """The attribution every derivative here owes its source, drawn from the catalog so it cannot drift from it."""
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))['sources']
    lines = ['# Page readings of the free corpus', '',
             'Each `pNNNN.md` is one page of a freely licensed PDF, transcribed from the page image by a vision model into the',
             'Markdown blocks of contract `page/1` (verbatim text, formulas as LaTeX, tables as HTML; figure descriptions are marked',
             'as derived). `index.json` holds every page\'s trace: the reading key and hash, the model, the attempt, the cost, its',
             'class under the validator, and the check flow\'s state with the judge\'s verdict, or why it was not judged. Written by',
             '`python -m backend.conversion.store.reading_export`.', '',
             'These are adaptations of the works below and carry their licences. Changes: transcribed from page images into',
             'Markdown blocks, checked against the PDF\'s text layer and, for a sample, by a model judge.', '',
             '| work | authors | licence | source |', '|---|---|---|---|']
    for source in catalog:
        if source.get('format') == 'pdf' and any(entry['path'].endswith('/' + name) for entry in source['files'] for name in files):
            lines.append(f"| {source['title']} | {source.get('authors', '')} | {source['licence']} | {source.get('source_url', '')} |")
    return '\n'.join(lines) + '\n'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Export the latest page readings of one knowledge base with their trace.')
    parser.add_argument('--knowledge-base', choices=sorted(BASES), default='free',
                        help='free: _data/corpus/readings, the data folder; licensed: _work/licensed/readings, local only')
    return parser


def main() -> None:
    from backend.conversion.store import pipeline_db

    sys.stdout.reconfigure(encoding='utf-8')
    base = BASES[build_parser().parse_args().knowledge_base]
    with pipeline_db.run([base.name], pipeline_db.command_line('backend.conversion.store.reading_export')):
        export(base)


if __name__ == '__main__':
    main()
