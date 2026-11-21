"""A proposed correction of one block of a reading (the operator's W2.a, 21 Nov 2026).

A person who finds a block wrong records a verdict with the block as it should read (decision 188.a), and until now wrote
that text by hand. A model may propose it: it sees the image the reader saw, the block and every finding a judge wrote on
it, and returns the whole block with as little changed as it can. The finding is a pointer to check in the image, never a
fact: a judge is right for a wrong reason at times (finance p. 94, 10 Nov), and a proposal that took its evidence would write
the judge's error in. The person reads the proposal, may change it, and records it or not; it never enters a reading.

What is never sent, as everywhere: a file the provenance list holds back, and a page a provider's filter blocked or a reader
refused in any attempt (280.a: never the same model by another door). Every request is kept by a key of everything asked,
so the same proposal is never bought twice, and its cost goes into the ledger the spend guard reads. The model comes from
the configuration (`correction` in `configs/app_config.json`), the instructions from the active version of the role
`correction` in `prompt_versions.json`; a prototype is run only by `calibrate`, on the corrections persons already made.

    python -m backend.conversion.judge.correction_proposal calibrate --dry-run   # the cases and the estimate, spends nothing
    python -m backend.conversion.judge.correction_proposal calibrate             # the prototype on every case, then the gate
"""

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from backend.conversion.contract import page_contract
from backend.conversion.judge import page_judge
from backend.conversion.reading import reader_requests, reading_cells
from backend.conversion.store.reading_store import open_store
from backend.providers import anthropic_client

ROLE = 'correction'
AGREES = ('yes', 'partly', 'no')
SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['agrees_with_judge', 'image_shows', 'correction'],
    'properties': {'agrees_with_judge': {'type': 'string', 'enum': list(AGREES)}, 'image_shows': {'type': 'string'},
                   'correction': {'type': 'string'}},
}
# A proposal that changes more of a verbatim block than this share of its words is shown with a warning: a minimal
# correction of a value or a word changes a few; a block written anew is for a person to look at twice. A block that was
# empty, a description (prose about a figure, never quoted), or a block of fewer words than LARGE_CHANGE_FROM is not held
# to it: an index entry of five words with two values corrected changes 40 % of it (the calibration, 21 Nov).
LARGE_CHANGE = 0.4
LARGE_CHANGE_FROM = 12
SPEND_CAP_USD = 200.0  # decision 122.a: the two credits together, by the ledgers of both mirrors
GUARD_FACTOR = 1.3  # the spend guard reserves 1.3 times an estimate, as `vision_batches submit` does
EXPECTED_OUTPUT_TOKENS = 800
WORD = re.compile(r'[a-z]+|\d+(?:[.,]\d+)*')
MIRRORS = ('free', 'licensed')


class Refused(Exception):
    """A proposal that is never asked for: why, in words a person reads."""


def versions() -> list[dict]:
    return [entry for entry in json.loads(page_judge.VERSIONS.read_text(encoding='utf-8'))['versions'] if entry['role'] == ROLE]


def active_version() -> str | None:
    """The version the view's button asks with; None until a person makes one active after its gate."""
    active = [entry['version'] for entry in versions() if entry['state'] == 'active']
    return active[0] if active else None


def instructions(version: str) -> str:
    entry = next((entry for entry in versions() if entry['version'] == version), None)
    if entry is None:
        raise ValueError(f'no {ROLE} version {version!r} in {page_judge.VERSIONS.name}')
    return (page_judge.CONVERSION / entry['files'][0]).read_bytes().decode('utf-8')


def refusal(knowledge_base: str, file: str, pdf_page: int) -> str | None:
    """Why this page is never sent for a proposal, or None."""
    from backend.conversion.judge import session_judge

    if not reading_cells.may_send(file):
        return 'held back by the provenance list (send: false): never sent to a provider'
    if (file, pdf_page) in session_judge.filtered_pages(knowledge_base):
        return "a provider's filter blocked this page or a reader refused it: never sent again (280.a)"
    return None


def block_view(block) -> str:
    """One block as the judge saw it: its id, class and printed attributes, DERIVED where it is a description."""
    attrs = ' '.join(f'{name}={block.attrs[name]}' for name in page_judge.VIEW_ATTRIBUTES if name in block.attrs)
    derived = ' DERIVED' if derived_block(block) else ''
    return f"[{block.id} {block.cls}{' ' + attrs if attrs else ''}{derived}]\n{block.body}"


def derived_block(block) -> bool:
    return page_contract.VOCAB['classes'].get(block.cls, {}).get('content') == 'D'


def findings_view(findings: list[dict]) -> str:
    return '\n'.join(f"- {finding.get('kind', 'other')}, {finding.get('severity', 'minor')}: {finding.get('evidence', '')}"
                     for finding in findings) or '- (no finding written)'


def request_key(*, model: str, system_text: str, image_sha: str, view: str, findings: str, max_tokens: int) -> str:
    spec = {'kind': ROLE, 'model': model, 'system': reader_requests.sha256_text(system_text), 'image': image_sha,
            'view': reader_requests.sha256_text(view), 'findings': reader_requests.sha256_text(findings),
            'max_tokens': max_tokens, 'settings': reader_requests.MODEL_SETTINGS[model],
            'schema': hashlib.sha256(json.dumps(SCHEMA, sort_keys=True).encode('utf-8')).hexdigest()}
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def message_params(*, model: str, system_text: str, page_png: bytes, pdf_page: int, view: str, findings: str,
                   max_tokens: int) -> dict:
    settings = copy.deepcopy(reader_requests.MODEL_SETTINGS[model])
    settings['output_config'] = {**settings.get('output_config', {}), 'format': {'type': 'json_schema', 'schema': SCHEMA}}
    content = [{'type': 'text', 'text': f'The image of PDF page {pdf_page}:'}, page_judge._image(page_png),
               {'type': 'text', 'text': f'The block, as the transcription writes it:\n\n{view}'},
               {'type': 'text', 'text': f"What the judge found wrong in it:\n{findings}"}]
    return {**settings, 'model': model, 'max_tokens': max_tokens,
            'system': [{'type': 'text', 'text': system_text, 'cache_control': {'type': 'ephemeral'}}],
            'messages': [{'role': 'user', 'content': content}]}


def words(text: str) -> Counter:
    return Counter(WORD.findall((text or '').lower()))


def edit_of(before: str, after: str) -> tuple[Counter, Counter]:
    """The words added and removed from one text to the other."""
    old, new = words(before), words(after)
    return new - old, old - new


def flags_of(block, proposal: str, agrees: str) -> list[str]:
    """What a person is told beside the proposal: it changes nothing, or a verbatim block more than a little, or it finds
    no error where the judge saw one."""
    flags = []
    if proposal.strip() == block.body.strip():
        flags.append('unchanged')
    added, removed = edit_of(block.body, proposal)
    total = sum(words(block.body).values())
    if (total >= LARGE_CHANGE_FROM and not derived_block(block)
            and (sum(added.values()) + sum(removed.values())) / total > LARGE_CHANGE):
        flags.append('large change')
    if agrees == 'no':
        flags.append('the image shows no such error')
    return flags


def spent_usd() -> float:
    return sum(open_store(mirror).spent_usd() for mirror in MIRRORS)


def estimate_usd(model: str, record: dict, view: str, system_text: str) -> float:
    from backend.conversion.reading import page_render

    image_tokens = page_render.patches(*record['image_size']) if record.get('image_size') else 4800
    return anthropic_client.cost_usd(model, image_tokens + (len(view) + 400) // 3, EXPECTED_OUTPUT_TOKENS,
                                     cache_write_tokens=len(system_text) // 4)


def ask_anthropic(params: dict):
    return anthropic_client.client().messages.create(**params)


def propose(knowledge_base: str, reading_key: str, block_id: str, findings: list[dict], *, version: str | None = None,
            asker=ask_anthropic, spent=spent_usd, model: str | None = None) -> dict:
    """A proposal for one block of one stored reading, asked once and kept; the same question answers from the store.

    Raises Refused with the reason where the page or the file is never sent, the block is not in the reading, no version
    is active, the configured provider is not built, or the spend guard would pass its cap."""
    from backend.configuration.app_config_manager import AppConfigManager

    config = AppConfigManager().get_correction()
    if model:  # a calibration on another model (the operator's A1.b, 21 Nov); the view always asks the configured one
        config = config.model_copy(update={'model': model})
    if config.provider.value != 'anthropic':
        raise Refused(f'no route for provider {config.provider.value!r}: the request carries the page image')
    version = version or active_version()
    if version is None:
        raise Refused(f'no active {ROLE} version: a person makes one active after its gate')
    store = open_store(knowledge_base)
    record, text = store.reading(reading_key), store.reading_text(reading_key)
    if not record or text is None or not record.get('image_sha256'):
        raise Refused('no stored reading with the image its reader saw')
    if why := refusal(knowledge_base, record['file'], record['pdf_page']):
        raise Refused(why)
    parsed = page_contract.parse(text, record.get('form') or 'markdown')
    block = next((block for block in parsed.blocks if block.id == block_id), None)
    if block is None:
        raise Refused(f'no block {block_id!r} in this reading')
    system_text, view, said = instructions(version), block_view(block), findings_view(findings)
    key = request_key(model=config.model, system_text=system_text, image_sha=record['image_sha256'], view=view, findings=said,
                      max_tokens=config.max_tokens)
    kept = store.path('corrections', key[:2], key + '.json')
    if kept.exists():
        return json.loads(kept.read_text(encoding='utf-8'))
    estimate = estimate_usd(config.model, record, view, system_text)
    if spent() + GUARD_FACTOR * estimate > SPEND_CAP_USD:
        raise Refused(f'the spend guard: {spent():.2f} USD spent of the cap of {SPEND_CAP_USD:.0f}')
    params = message_params(model=config.model, system_text=system_text, page_png=store.get_input(record['image_sha256'], '.png'),
                            pdf_page=record['pdf_page'], view=view, findings=said, max_tokens=config.max_tokens)
    message = asker(params)
    usage = message.usage.to_dict()
    cost = anthropic_client.cost_usd(config.model, usage.get('input_tokens') or 0, usage.get('output_tokens') or 0,
                                     cache_write_tokens=usage.get('cache_creation_input_tokens') or 0,
                                     cache_read_tokens=usage.get('cache_read_input_tokens') or 0)
    at = datetime.now(timezone.utc).isoformat(timespec='seconds')
    store.append_ledger({'at': at, 'cell': f'CORRECTION-{config.model}', 'cost_usd': cost, 'kind': ROLE, 'mode': 'standard',
                         'model': config.model, 'provider': 'anthropic', 'reading_key': key,
                         'result_class': message.stop_reason})  # the ledger line first, as every spend writes it
    answer = None
    if message.stop_reason == 'end_turn':
        try:
            answer = json.loads(anthropic_client.answer_text(message))
        except json.JSONDecodeError:
            answer = None
    found = {'key': key, 'version': version, 'model': config.model, 'knowledge_base': knowledge_base, 'file': record['file'],
             'pdf_page': record['pdf_page'], 'reading_key': reading_key, 'block': block_id, 'at': at, 'cost_usd': cost,
             'request_id': getattr(message, '_request_id', None), 'stop_reason': message.stop_reason}
    if not isinstance(answer, dict) or answer.get('agrees_with_judge') not in AGREES or not isinstance(answer.get('correction'), str):
        found.update(state='no proposal', why=f'the answer was not a proposal (stop: {message.stop_reason})')
    else:
        found.update(state='proposed', agrees_with_judge=answer['agrees_with_judge'], image_shows=answer.get('image_shows', ''),
                     correction=answer['correction'], flags=flags_of(block, answer['correction'], answer['agrees_with_judge']))
    store._write(kept, json.dumps(found, indent=1, ensure_ascii=False).encode('utf-8'))
    return found


# --- calibration: the prototype against the corrections persons already made --------------------------------------------

GATE_RATINGS = ('right', 'right_for_a_wrong_reason')
RECALL_AT_LEAST, PRECISION_AT_LEAST = 0.8, 0.6


def calibration_cases() -> list[dict]:
    """Every person correction, with its reading's block, the judge's findings on that block and the person's rating."""
    from backend.conversion.checks import check_run
    from backend.conversion.store import pipeline_db

    cases = []
    for mirror in MIRRORS:
        store, judged = open_store(mirror), None
        for verdicts in pipeline_db.human_verdicts(mirror).values():
            for verdict in verdicts:
                if not verdict.get('correction'):
                    continue
                judged = judged if judged is not None else check_run.judgements_by_target(store)
                findings = [{key: finding.get(key) for key in ('kind', 'severity', 'evidence')}
                            for judgement in judged.get(verdict['reading_key'], []) for finding in judgement['findings']
                            if finding.get('block') == verdict['block'] and not finding.get('void')]
                cases.append({'knowledge_base': mirror, 'file': verdict['file'], 'pdf_page': verdict['pdf_page'],
                              'reading_key': verdict['reading_key'], 'block': verdict['block'], 'findings': findings,
                              'rating': verdict.get('judge_assessment'), 'person': verdict['correction']})
    return cases


def edit_scores(original: str, person: str, proposal: str) -> tuple[float, float]:
    """How much of the person's edit the proposal makes (recall), and how much of the proposal's edit the person made
    (precision), in words added and removed against the reading."""
    person_added, person_removed = edit_of(original, person)
    proposal_added, proposal_removed = edit_of(original, proposal)
    hit = sum((person_added & proposal_added).values()) + sum((person_removed & proposal_removed).values())
    person_size = sum(person_added.values()) + sum(person_removed.values())
    proposal_size = sum(proposal_added.values()) + sum(proposal_removed.values())
    return (hit / person_size if person_size else 1.0), (hit / proposal_size if proposal_size else (1.0 if not person_size else 0.0))


def calibrate(version: str, dry_run: bool, asker=ask_anthropic, model: str | None = None) -> dict:
    cases = calibration_cases()
    rows = []
    for case in cases:
        store = open_store(case['knowledge_base'])
        record, text = store.reading(case['reading_key']), store.reading_text(case['reading_key'])
        block = next(block for block in page_contract.parse(text, record.get('form') or 'markdown').blocks if block.id == case['block'])
        row = {key: case[key] for key in ('knowledge_base', 'file', 'pdf_page', 'block', 'rating')}
        row.update(cls=block.cls, in_gate=case['rating'] in GATE_RATINGS and bool(case['findings']))
        if dry_run:
            from backend.configuration.app_config_manager import AppConfigManager

            row['estimate_usd'] = estimate_usd(model or AppConfigManager().get_correction().model, record, block_view(block),
                                               instructions(version))
        else:
            found = propose(case['knowledge_base'], case['reading_key'], case['block'], case['findings'], version=version, asker=asker,
                            model=model)
            proposal = found.get('correction')
            recall, precision = edit_scores(block.body, case['person'], proposal) if proposal is not None else (0.0, 0.0)
            row.update(state=found['state'], agrees=found.get('agrees_with_judge'), flags=found.get('flags'),
                       recall=round(recall, 3), precision=round(precision, 3), cost_usd=found['cost_usd'],
                       passes_by_words=recall >= RECALL_AT_LEAST and precision >= PRECISION_AT_LEAST, key=found['key'])
        rows.append(row)
    return {'version': version, 'rows': rows}


def main(argv: list[str] | None = None) -> int:
    from backend.configuration import data_paths

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    calibrating = commands.add_parser('calibrate', help='the prototype on every correction a person made, then the gate')
    calibrating.add_argument('--version', default=f'{ROLE}/1')
    calibrating.add_argument('--dry-run', action='store_true')
    calibrating.add_argument('--model', help='another model than the configured one, for a comparison')
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8')
    report = calibrate(args.version, args.dry_run, model=args.model)
    rows = report['rows']
    if args.dry_run:
        print(f"{len(rows)} cases, {sum(row['in_gate'] for row in rows)} in the gate; "
              f"estimate {sum(row['estimate_usd'] for row in rows):.3f} USD, spent so far {spent_usd():.2f} of {SPEND_CAP_USD:.0f}")
        return 0
    # the report holds the proposals' keys, never their text; it lies beside the private working data all the same
    suffix = f"_{args.model}" if args.model else ''
    path = data_paths.LICENSED_WORKING / 'corrections' / f"calibration_{args.version.replace('/', '')}{suffix}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(report, indent=1, ensure_ascii=False).encode('utf-8'))
    gate = [row for row in rows if row['in_gate']]
    print(f"{len(rows)} cases, {sum(row['cost_usd'] for row in rows):.4f} USD; in the gate {len(gate)}: "
          f"{sum(row['passes_by_words'] for row in gate)} pass by words; report {path}")
    for row in rows:
        print(f"  {row['knowledge_base'][:3]} {Path(row['file']).stem[:24]:24} p{row['pdf_page']:<4} {row['block']:4} {row['cls']:12} "
              f"{row['rating'] or '-':24} gate={row['in_gate']!s:5} {row['state']:11} agrees={row['agrees']!s:6} "
              f"recall={row['recall']:.2f} precision={row['precision']:.2f} flags={row['flags']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
