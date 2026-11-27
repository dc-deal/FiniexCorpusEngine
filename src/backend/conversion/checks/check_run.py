"""The check flow over the readings of corpus cells: stage 2 on every page, the judge on a sample, every suspect and every page
with a block stage 2 cannot check (decision 83.a), the states.

Decision OC-5.a. What lies between the stages is decided in `check_flow`; this module runs it over stored readings. Stage 1 is
judged under today's validator (`vision_batches.current_class`), so a corrected validator counts without a new reading, and a
page is represented by its latest attempt. Stage 2 reads each page's PDF text layer, so it runs where the sources are.

    python -m backend.conversion.checks.check_run plan --cells FREE-SM      # stage 2 and the judge's selection; spends nothing
    python -m backend.conversion.checks.check_run submit --cells FREE-SM [--cap 40] [--dry-run]
    python -m backend.conversion.checks.check_run report --cells FREE-SM    # every page's state, once the judge is collected

The judge's batches go through the guarded runner and come back with `vision_batches collect`. Reports hold ids, counts and
reasons, never page text.
"""

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

from backend.conversion.checks import check_flow, page_checks
from backend.conversion.judge import page_judge
from backend.conversion.reading import vision_batches
from backend.conversion.contract.page_contract import Expected, parse
from backend.conversion.store.reading_store import open_store
from backend.providers import anthropic_client

FROZEN = json.loads((Path(__file__).resolve().parents[1] / 'frozen_contract.json').read_text(encoding='utf-8'))
JUDGE_MODEL = FROZEN['judge']


def latest_per_page(records: list[dict], valid=None) -> list[dict]:
    """The reading that stands for each page: its highest attempt. A retry replaces its first reading, never the reverse.

    With `valid` (a reading -> whether it passes today's validator), a later reading that fails it never displaces one that
    passes (decision 174.a, the operator, 10 Nov): finance p. 229's first reading passes and its check is ok today, yet a re-read with
    the judge's findings as a hint, bought before the void rule, came back malformed and sent the page to its text layer."""
    latest = {}
    for record in records:
        page = (record['file'], record['pdf_page'])
        held = latest.get(page)
        newer = held is None or record.get('attempt', 0) > held.get('attempt', 0)
        if held is not None and valid is not None and valid(record) != valid(held):
            newer = valid(record)  # the reading that passes stands, whichever came later
        if newer:
            latest[page] = record
    return [latest[page] for page in sorted(latest)]


def flow_pages(records: list[dict], classes: dict, checks: dict) -> list[dict]:
    """The pages as check_flow takes them. A page stage 2 could not check (no layer) counts as not suspicious; a page with a block
    it could not check (stage 2's `unverifiable`) goes to the judge for that (decision 83.a)."""
    return [{'key': record['reading_key'], 'work': record['work'], 'result_class': classes[record['reading_key']],
             'suspicious': bool(checks.get(record['reading_key'], {}).get('suspicious')),
             'unverifiable': bool(checks.get(record['reading_key'], {}).get('unverifiable'))} for record in records]


def keep_sample(fresh: check_flow.Selection, pages: list[dict], previous_sampled: list[str]) -> check_flow.Selection:
    """The random sample is drawn once and kept by later plans, so a work's error rate stays comparable when pages are added
    (a second reader's pages are judged in full anyway). A work the earlier sample did not cover gets its fresh sample."""
    usable = {page['key']: page['work'] for page in pages if page['result_class'] == 'ok'}
    kept = {key for key in previous_sampled if key in usable and key not in fresh.suspicious}
    covered = {usable[key] for key in kept}
    added = {key for key in fresh.sampled if usable[key] not in covered}
    return check_flow.Selection(fresh.suspicious, frozenset(kept | added), fresh.unverifiable)


# The licensed mirror's sample is twice the free one's, with the same stopping share (decision 74.a, 2026-11-04): on the
# licensed round 1, stage 2 flagged 1 of the 4 readings the judge found bad, so there the random sample is the real net.
POLICIES = {'free': check_flow.Policy(), 'licensed': check_flow.Policy(sample_per_work=40, stop_above=6)}


def policy_of(store, cells: list[str] = ()) -> check_flow.Policy:
    """The mirror's policy; for a second reader's cells every page is in the sample, since each such page is judged (63.a)."""
    from backend.conversion.reading import reading_cells

    policy = POLICIES['licensed' if store.root == open_store('licensed').root else 'free']
    if cells and all(reading_cells.known_cells()[name].mode != 'batch' for name in cells):
        return check_flow.Policy(sample_per_work=EVERY_PAGE, stop_above=policy.stop_above,
                                 stop_share=policy.stop_above / policy.sample_per_work)
    return policy


EVERY_PAGE = 10 ** 6  # a sample larger than any work
# The operator's V1.b (19 Nov): a work the session read whole (`direct_reader pages --add-work`, a scanned book) is judged by
# a seeded sample of this many pages, the rest served unjudged; the stop rule holds as for every sample (more than 15 % of the
# sample bad stops the work). A scan has no text layer, so stage 2 flags none of its blocks as checked and 83.a would send
# every page to the judge: the sample replaces that for such a work alone.
WHOLE_WORK_SAMPLE = 60


def whole_works(cells: list[str]) -> set[str]:
    """The works the direct cell took whole, by their key (the file's stem), from its page list's `added_works`, and the works
    whose pages it took by a page list (`added_pages`, 27.a): both are judged by a sample, the share their list names."""
    from backend.conversion.reading import reading_cells

    lists = set(reading_cells.DIRECT_PAGES.values())
    works = set()
    for name in cells:
        source = Path(reading_cells.known_cells()[name].page_source)
        if source in lists and source.exists():
            listed = json.loads(source.read_text(encoding='utf-8'))
            works |= {Path(file_name).stem for file_name in listed.get('added_works', [])}
            works |= {Path(page['file']).stem for page in listed.get('added_pages', [])}
    return works


def judge_shares(cells: list[str]) -> dict[str, float]:
    """The share of its pages a work read whole is judged by, where its page list names one (`direct_reader pages --add-work
    FILE --judge-share 0.6`, the operator's N2.a for a night's work), by the work's key."""
    from backend.conversion.reading import reading_cells

    lists = set(reading_cells.DIRECT_PAGES.values())
    shares = {}
    for name in cells:
        source = Path(reading_cells.known_cells()[name].page_source)
        if source in lists and source.exists():
            shares.update(json.loads(source.read_text(encoding='utf-8')).get('judge_shares', {}))
    return shares


def whole_work_sample(selection: check_flow.Selection, pages: list[dict], works: set[str],
                      shares: dict[str, float] | None = None) -> check_flow.Selection:
    """For a work read whole, a seeded sample of its passed pages in place of every page and of 83.a's unverifiable pages:
    `WHOLE_WORK_SAMPLE` pages, or the share its page list names (N2.a); a page stage 2 found suspicious is still judged."""
    if not works:
        return selection
    own = {page['key'] for page in pages if page['work'] in works}
    sample = set()
    for work in sorted(works):
        usable = sorted(page['key'] for page in pages if page['work'] == work and page['result_class'] == 'ok'
                        and page['key'] not in selection.suspicious)
        size = round((shares or {})[work] * len(usable)) if work in (shares or {}) else WHOLE_WORK_SAMPLE
        sample.update(random.Random(work).sample(usable, min(size, len(usable))))
    return check_flow.Selection(selection.suspicious, frozenset((selection.sampled - own) | sample),
                                frozenset(selection.unverifiable - own), selection.reread)


SAMPLE_FILE = 'judge_sample.json'  # the random sample of a mirror, whatever cells a plan names


def earlier_sample(store) -> list[str]:
    """The judge's random sample as drawn before, kept in one file per mirror so a plan over other cells keeps it too (the review
    of 2026-11-03: a sample found by the cell list was drawn anew when a cell was added). Before that file existed the sample
    lived in the plans themselves, so their samples seed it."""
    kept = store.path('reports', SAMPLE_FILE)
    if kept.exists():
        return json.loads(kept.read_text(encoding='utf-8'))['sampled']
    folder = store.path('reports', 'x').parent
    return sorted({key for path in folder.glob('check_plan_*.json') for key in json.loads(path.read_text(encoding='utf-8'))['sampled']})


def store_of(cells: list[str]):
    """The mirror the cells' pages lie in, from their first page: free and licensed cells never mix in one plan."""
    from backend.conversion.reading import reading_cells

    mirrors = {reading_cells.source_of(reading_cells.pages_for(reading_cells.known_cells()[name])[0]['file'])[0] for name in cells}
    if len(mirrors) != 1:
        raise SystemExit(f'cells of one mirror only, not {sorted(mirrors)}')
    return open_store(mirrors.pop())


def _plan_name(cells: list[str]) -> str:
    return f"check_plan_{'_'.join(cells)}.json"


def _cells(args) -> list[str]:
    return sorted({name.strip() for name in args.cells.split(',') if name.strip()})


def plan(args) -> dict:
    from backend.conversion.reading import reading_cells

    cells = _cells(args)
    if any(reading_cells.is_test_cell(name) for name in cells):  # its plan keeps one reading per page and feeds the sample
        raise SystemExit('test cells are planned by `local_reader judge-plan`, one cell at a time, never here')
    store = store_of(cells)
    records = latest_per_page(vision_batches.readings_of(cells, store),
                              valid=lambda record: vision_batches.current_class(record, store) == 'ok')  # 174.a
    classes = {record['reading_key']: vision_batches.current_class(record, store) for record in records}
    parsed = {}
    for record in records:
        if classes[record['reading_key']] == 'ok':
            text = store.reading_text(record['reading_key']) or ''
            parsed[record['reading_key']] = parse(text, record['form'], Expected(record['work'], record['pdf_page'], tuple(record['image_size'])))
    rendered = page_checks.render_formulas(list(parsed.values()))
    documents, checks = vision_batches.Documents(), {}
    for record in records:
        if record['reading_key'] in parsed:
            _, pdf_page = documents.page(record['file'], record['pdf_page'])
            checks[record['reading_key']] = page_checks.check_page(parsed[record['reading_key']], pdf_page, rendered).as_dict()
    pages = flow_pages(records, classes, checks)
    policy = policy_of(store, cells)
    fresh = check_flow.select_for_judge(pages, policy)
    # A kept sample covers a work once; a second reader's every page is judged, so its later pages must never fall outside it.
    selection = fresh if policy.sample_per_work >= EVERY_PAGE else keep_sample(fresh, pages, earlier_sample(store))
    # A re-read after the judge's issue is judged again in every case (decision 133.b): it replaces a reading known to be bad
    reread = frozenset(record['reading_key'] for record in records
                       if record.get('retry_of') and classes[record['reading_key']] == 'ok')
    selection = check_flow.Selection(selection.suspicious, selection.sampled, selection.unverifiable, reread)
    selection = whole_work_sample(selection, pages, whole_works(cells), judge_shares(cells))  # V1.b, N2.a: by a sample
    store.write_report(SAMPLE_FILE, {'sampled': sorted(selection.sampled | set(earlier_sample(store)))})
    entries = [page_judge.entry_for(record, parsed[record['reading_key']], JUDGE_MODEL)
               for record in records if record['reading_key'] in selection.keys]
    result = {'cells': cells, 'judge': JUDGE_MODEL, 'policy': vars(policy), 'pages': pages,
              # stage 2 in full, ids, counts and ratios without page text, so a view can show each stage on its own (the operator, 9 Nov)
              'stage2': {key: {'suspicious': check['suspicious'], 'has_layer': check['has_layer'], 'recall': check['recall'],
                               'precision': check['precision'],
                               'findings': [{name: finding[name] for name in ('kind', 'block', 'detail', 'severity')}
                                            for finding in check['findings']],
                               'unverifiable': [{name: item[name] for name in ('block', 'cls', 'why')} for item in check['unverifiable']]}
                         for key, check in checks.items()},
              'suspicious': sorted(selection.suspicious), 'sampled': sorted(selection.sampled),
              'unverifiable': sorted(selection.unverifiable), 'reread': sorted(selection.reread), 'entries': entries,
              'estimate_usd': sum(entry['estimate_usd'] for entry in entries)}
    path = store.write_report(_plan_name(cells), result)
    by_work = Counter(page['work'] for page in pages if page['suspicious'])
    print(f"{len(pages)} pages, {sum(1 for page in pages if page['result_class'] == 'ok')} past stage 1, "
          f"{len(selection.suspicious)} suspicious in stage 2 {dict(by_work)}, {len(selection.unverifiable)} more with a block stage 2 "
          f"cannot check, {len(selection.sampled)} sampled; "
          f"{len(entries)} judge requests, estimate {result['estimate_usd']:.4f} USD; written to {path.name}")
    return result


def verdicts_by_target(store) -> dict:
    """The judge's answered records by the reading they judged, for the frozen judge model. A reading judged once is judged:
    the judge's key also hashes the formula sheets, and their pixels change with the browser that renders them (Edge stopped
    writing screenshots on 2026-11-04 and Chrome took over), which must never buy a verdict twice.

    Only a verdict the pipeline may act on counts (decision 147.a): never a prototype version's, which is kept apart until a
    person makes it active, and never one asked again on purpose (`again`, a demonstration or a check of the judge's variance).
    Where a reading has verdicts of several versions, the active version's stands, else the latest retired one's."""
    active = page_judge.active_version()
    newest_first = [entry['version'] for entry in reversed(page_judge.judge_versions())]

    def preference(version: str) -> tuple:  # lower is better: the active version, then the newest retired one
        return (version != active, newest_first.index(version))

    found = {}
    for record in store.readings():
        # a planted-error judgement names the clean reading as its target but judged a changed copy: never a verdict on it
        if not (record.get('kind') == 'judge' and record.get('model') == JUDGE_MODEL and record.get('verdict') and record.get('target_key')
                and not record.get('planted') and verdicts_counted(record)):
            continue
        held = found.get(record['target_key'])
        if held is None or preference(page_judge.version_of(record)) < preference(page_judge.version_of(held)):
            found[record['target_key']] = record  # within one version the first found stands, as before versions had names
    return found


def judgements_by_target(store) -> dict[str, list[dict]]:
    """Every judgement of each reading, oldest first, whatever its version or purpose: a page's whole history for the views,
    the prototype's and the repeated ones included and labelled. Never a planted copy's."""
    found: dict[str, list[dict]] = {}
    for record in sorted(store.readings(), key=lambda record: record.get('stored_at') or ''):
        if (record.get('kind') == 'judge' and record.get('verdict') and record.get('target_key') and not record.get('planted')):
            version = page_judge.version_of(record)
            verdict = voided(store, record['verdict'], record['target_key'])
            found.setdefault(record['target_key'], []).append({
                'version': version, 'version_state': page_judge.state_of(version), 'model': record.get('model'),
                'mode': record.get('mode'), 'again': record.get('replicate') or 0, 'stored_at': record.get('stored_at'),
                'verdict': verdict['verdict'], 'outcome': check_flow.current_state(verdict['outcome']),  # 'bin' before 97.a
                'judge_outcome': verdict.get('judge_outcome') and check_flow.current_state(verdict['judge_outcome']),
                'findings': [{key: finding.get(key) for key in ('kind', 'block', 'severity', 'evidence', 'void') if finding.get(key) is not None}
                             for finding in verdict.get('findings', [])],
                # a version that proposes rules for the reader (197.a), shown read-only beside its findings (202.a); '' is not set
                'reader_rules': [{key: rule.get(key, '') for key in ('kind', 'block', 'rule', 'class', 'attribute', 'value')}
                                 for rule in record['verdict'].get('reader_rules') or []],
                'cost_usd': record.get('cost_usd'), 'counts': verdicts_counted(record) is not None,
                # its own key, which a person's verdict names as the judgement it answered, and the prompt that started its
                # session agent, where one did (#17, 22.a)
                'judgement_key': record.get('reading_key'),
                **({'agent_prompt': {key: record['agent_prompt'][key] for key in ('version', 'sha256')}}
                   if record.get('agent_prompt') else {})})
    return found


_DOCUMENTS = []  # one open set of PDFs per process, made on first need


def page_layer(file: str, pdf_page: int) -> str | None:
    """A page's PDF text layer, or None where the PDF is not on this machine or has no such page."""
    if not _DOCUMENTS:
        _DOCUMENTS.append(vision_batches.Documents())
    try:
        _, page = _DOCUMENTS[0].page(file, pdf_page)
        return page.get_text()
    except Exception:  # a PDF not here (a clone has no licensed archive): the rule's text part does not act
        return None


def voided(store, verdict: dict | None, reading_key: str) -> dict | None:
    """A verdict with its self-contradicting findings void (decision 146.a). The judged reading's blocks and the page's text
    layer are read only where a wrong word or value could need them."""
    if not verdict or not any(finding.get('kind') in page_judge.SAME_TEXT_KINDS for finding in verdict.get('findings', [])):
        return page_judge.with_void(verdict)
    reading = store.reading(reading_key) or {}
    blocks = page_judge.blocks_if_needed(verdict, store.reading_text(reading_key), reading.get('form') or 'markdown')
    layer = page_layer(reading['file'], reading['pdf_page']) if blocks and reading.get('file') else None
    return page_judge.with_void(verdict, blocks, layer)


def verdicts_counted(record: dict) -> dict | None:
    """The record itself where the pipeline may act on it (an active or retired version's, asked once), else None."""
    return record if (not record.get('replicate') and page_judge.state_of(page_judge.version_of(record)) != 'prototype') else None


def submit(args) -> None:
    cells = _cells(args)
    store = store_of(cells)
    planned = json.loads(store.path('reports', _plan_name(cells)).read_text(encoding='utf-8'))
    judged = verdicts_by_target(store)
    entries = [entry for entry in planned['entries'] if entry['target_key'] not in judged and store.reading(entry['reading_key']) is None]
    skipped = Counter({'already judged': len(planned['entries']) - len(entries)})
    vision_batches.send_entries(anthropic_client.client(), entries, skipped, args.cap, dry_run=args.dry_run)


def report(args) -> dict:
    cells = _cells(args)
    store = store_of(cells)
    planned = json.loads(store.path('reports', _plan_name(cells)).read_text(encoding='utf-8'))
    judged, verdicts, unanswered = verdicts_by_target(store), {}, Counter()
    for entry in planned['entries']:
        record = judged.get(entry['target_key']) or store.reading(entry['reading_key'])
        if record is None or record.get('verdict') is None:
            unanswered[record['result_class'] if record else 'not collected'] += 1
        else:  # a finding that contradicts its own evidence is void (decision 146.a)
            verdicts[entry['target_key']] = voided(store, record['verdict'], entry['target_key'])
    selection = check_flow.Selection(frozenset(planned['suspicious']), frozenset(planned['sampled']),
                                     frozenset(planned.get('unverifiable', [])),  # a plan before 83.a has none
                                     frozenset(planned.get('reread', [])))  # nor one before 133.b
    result = check_flow.outcomes(planned['pages'], verdicts, selection, check_flow.Policy(**planned['policy']))
    result.update(cells=cells, judged=len(verdicts), unanswered=dict(unanswered), issues=check_flow.issue_entries(result),
                  judge_cost_usd=sum((judged.get(entry['target_key']) or store.reading(entry['reading_key']) or {}).get('cost_usd', 0.0)
                                         for entry in planned['entries']))
    path = store.write_report(f"check_report_{'_'.join(cells)}.json", result)
    for work, row in result['works'].items():
        print(f"{work}: {row['states']}, sample {row['sample_bad']} bad of {row['sample_size']}{', STOPPED' if row['stopped'] else ''}")
    print(f"judged {len(verdicts)}, unanswered {dict(unanswered)}, issues {len(result['issues'])}, "
          f"judge cost {result['judge_cost_usd']:.4f} USD; written to {path.name}")
    return result


def judged_bad(store, cells: list[str]) -> list[dict]:
    """The cells' readings the active judge's counted verdict called bad: the pages a new judge version is tried on first."""
    counted = verdicts_by_target(store)
    return [record for record in latest_per_page(vision_batches.readings_of(cells, store))
            if (counted.get(record['reading_key']) or {}).get('verdict', {}).get('verdict') == 'bad']


def prototype(args) -> list[dict]:
    """A judge version's run on chosen pages (decision 147.a, the operator: "prototype first"): the readings judge/1 called bad, in
    batches, filed under the version's own cell and never counted. `prototype-report` sets them beside judge/1 and a person."""
    from backend.conversion.contract.page_contract import parse as parse_page

    cells = _cells(args)
    store = store_of(cells)
    every_page = getattr(args, 'every_page', False)  # a reader prototype's readings, each judged (decision 207.a)
    targets = (latest_per_page(vision_batches.readings_of(cells, store),
                               valid=lambda record: vision_batches.current_class(record, store) == 'ok')
               if every_page else judged_bad(store, cells))
    entries = []
    for record in targets:
        if every_page and vision_batches.current_class(record, store) != 'ok':
            continue  # a malformed reading has no blocks to judge
        parsed = parse_page(store.reading_text(record['reading_key']) or '', record['form'],
                            Expected(record['work'], record['pdf_page'], tuple(record['image_size'])))
        entries.append(page_judge.entry_for(record, parsed, page_judge.model_of(args.version), version=args.version))
    fresh = [entry for entry in entries if store.reading(entry['reading_key']) is None]
    print(f"{args.version} ({page_judge.state_of(args.version)}) on {len(entries)} pages "
          f"{'of the cells' if every_page else 'judge/1 called bad'}, {len(fresh)} not asked yet")
    vision_batches.send_entries(anthropic_client.client(), fresh, Counter({'asked before': len(entries) - len(fresh)}), args.cap,
                                dry_run=args.dry_run)
    return entries


def prototype_report(args) -> list[dict]:
    """Per page judge/1 called bad: judge/1's outcome before and after the void rule, the version's, and a person's verdict."""
    from backend.conversion.store import pipeline_db

    cells = _cells(args)
    store = store_of(cells)
    history = judgements_by_target(store)
    people = pipeline_db.human_verdicts('licensed' if store.root == open_store('licensed').root else 'free')
    rows = []
    for record in judged_bad(store, cells):
        judged = history.get(record['reading_key'], [])
        first = next((item for item in judged if item['counts']), None)
        tried = [item for item in judged if item['version'] == args.version and not item['again']]
        person = [verdict for verdict in people.get((record['file'], record['pdf_page']), [])
                  if verdict['reading_key'] == record['reading_key'] and verdict['verdict'] != 'note']
        rows.append({'page': f"{record['work']}:p{record['pdf_page']}", 'judge_1': first and check_flow.current_state(first['judge_outcome'] or first['outcome']),
                     'judge_1_after_void': first and check_flow.current_state(first['outcome']),
                     args.version: check_flow.current_state(tried[-1]['outcome']) if tried else None,
                     'person': person[-1]['verdict'] if person else None})
    for row in rows:
        print(f"{row['page']:34} judge/1 {row['judge_1']:6} after void {row['judge_1_after_void']:6} "
              f"{args.version} {row[args.version] or '-':6} person {row['person'] or '-'}")
    agree = [row for row in rows if row['person'] and row[args.version]]
    if agree:
        right = sum((row[args.version] == 'ok') == (row['person'] == 'accept') for row in agree)
        print(f'{args.version} agrees with a person on {right} of {len(agree)} pages a person judged')
    store.write_report(f"prototype_{args.version.replace('/', '')}_{'_'.join(cells)}.json", {'version': args.version, 'rows': rows})
    return rows


_RULE_WORD = re.compile(r"[a-z0-9_]+")
_RULE_STOP = frozenset({'a', 'an', 'the', 'and', 'or', 'as', 'its', 'it', 'of', 'in', 'on', 'to', 'is', 'be', 'with', 'for', 'each',
                        'every', 'one', 'per', 'that', 'this', 'write', 'always', 'into', 'by', 'from', 'are'})


def rule_key(rule: dict) -> tuple:
    """What makes two proposals the same (decision 197.a, the operator: "gathered in one shared store, so that we don't have so
    many duplicates"): a class or an attribute by the vocabulary's names, a format rule by the set of its words without
    the small ones, order aside; "never" and "not" count, so a rule and its opposite stay apart. Wording that differs beyond
    that stays apart, for a person or one model call to merge."""
    if rule['kind'] == 'class':
        return ('class', rule.get('class', '').strip().lower(), rule.get('value', '').strip().lower())
    if rule['kind'] == 'attribute':
        return ('attribute', rule.get('attribute', '').strip().lower(), rule.get('value', '').strip().lower())
    words = [word for word in _RULE_WORD.findall(rule.get('rule', '').lower()) if word not in _RULE_STOP]
    return ('format_rule', ' '.join(sorted(set(words))))


def reader_rules(args) -> dict:
    """Every rule for the reader a judge version proposed, merged where the same (`rule_key`) and counted by pages and works,
    most often first; written to the store's reports. Nothing is applied: the list is where a person starts page/2."""
    cells = _cells(args)
    store = store_of(cells)
    merged: dict[tuple, dict] = {}
    for record in store.readings():
        if record.get('kind') != 'judge' or page_judge.version_of(record) != args.version or record.get('planted'):
            continue
        for rule in (record.get('verdict') or {}).get('reader_rules') or []:
            item = merged.setdefault(rule_key(rule), {'kind': rule['kind'], 'rule': rule.get('rule', ''), 'class': rule.get('class', ''),
                                                       'attribute': rule.get('attribute', ''), 'value': rule.get('value', ''),
                                                       'wordings': [], 'pages': [], 'works': set()})
            if rule.get('rule') and rule['rule'] not in item['wordings']:
                item['wordings'].append(rule['rule'])
            item['pages'].append({'work': record.get('work'), 'pdf_page': record.get('pdf_page'), 'block': rule.get('block')})
            item['works'].add(record.get('work'))
    rows = sorted(({**item, 'works': sorted(item['works']), 'count': len(item['pages'])} for item in merged.values()),
                  key=lambda item: (-item['count'], item['kind']))
    report = {'version': args.version, 'cells': cells, 'proposals': sum(row['count'] for row in rows), 'rules': rows}
    store.write_report(f"reader_rules_{args.version.replace('/', '')}_{'_'.join(cells)}.json", report)
    for row in rows[:30]:
        print(f"{row['count']:3} pages, {len(row['works'])} works  {row['kind']:11} {row['class'] or row['attribute'] or ''} "
              f"{row['value']}  {(row['rule'] or '')[:90]}")
    print(f"{report['proposals']} proposals merged into {len(rows)} rules")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    for name, run in (('plan', plan), ('submit', submit), ('report', report), ('prototype', prototype),
                      ('prototype-report', prototype_report), ('reader-rules', reader_rules)):
        command = commands.add_parser(name)
        command.add_argument('--cells', required=True)
        command.set_defaults(run=run)
        if name in ('submit', 'prototype'):
            command.add_argument('--cap', type=float, default=vision_batches.DEFAULT_CAP_USD)
            command.add_argument('--dry-run', action='store_true')
        if name in ('prototype', 'prototype-report', 'reader-rules'):
            command.add_argument('--version', required=True, help='the judge version to try, as judge/2')
        if name == 'prototype':
            command.add_argument('--every-page', action='store_true',
                                 help="judge every valid reading of the cells, not only those judge/1 called bad (a reader prototype's)")
    return parser


def main() -> None:
    from backend.conversion.store import pipeline_db

    sys.stdout.reconfigure(encoding='utf-8')
    args = build_parser().parse_args()
    base = 'licensed' if store_of(_cells(args)).root == open_store('licensed').root else 'free'
    with pipeline_db.run([base], pipeline_db.command_line('backend.conversion.checks.check_run')):
        args.run(args)


if __name__ == '__main__':
    main()
