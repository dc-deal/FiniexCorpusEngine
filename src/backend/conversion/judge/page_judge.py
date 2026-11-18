"""Stage 3 of the check flow: a model compares a reading with the page image and gives a verdict.

Stage 2 cannot check what the text layer lacks: formulas drawn as paths, tables printed as images, text inside figures. The judge
sees the page image, the reading and each formula rendered (`formula_sheet`), and it is blind to stage 2's findings, so the two can
be measured apart. Its noise is measured on planted errors and on clean readings before its issues mean anything (`mini_pilot`).
A person stays the final judge. It answers with a verdict and short evidence, never the page's text.

A judge request is a request kind of `vision_batches`: same manifests, same ledger, same spend guard, and any stored result blocks
buying it again. A refused or blocked judge request is recorded and never re-sent.
"""

import base64
import copy
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from backend.conversion.contract import page_contract
from backend.conversion.judge import formula_sheet
from backend.conversion.reading import page_render, reader_requests
from backend.conversion.contract.page_contract import ParsedPage
from backend.conversion.store.reading_store import open_store
from backend.providers import anthropic_client

CONVERSION = Path(__file__).resolve().parents[1]
PROMPT = CONVERSION / 'prompts' / 'judge_page1.txt'  # judge/1, the version every record before 9 Nov was judged with
VERSIONS = CONVERSION / 'prompt_versions.json'  # every version of the reader's and the judge's instructions, and its state
FIRST_VERSION = 'judge/1'  # a record without a `judge_version` was judged with it
MAX_TOKENS = 2000
MAX_TOKENS_WITH_RULES = 3000  # a version that also proposes rules for the reader writes more (decision 197.a)
EXPECTED_OUTPUT_TOKENS = 300  # for estimates; the usage of each result replaces it
# Every attribute that carries printed words goes to the judge: without `term` it judged a glossary entry's definition alone
# and called the term missing (decision 190.a, finance pp. 136 and 562); `key` and `target` are a reference's and a contents
# entry's printed numbers.
VIEW_ATTRIBUTES = ('label', 'kind', 'of', 'in', 'marker', 'cont', 'raster', 'form', 'status', 'lang', 'number', 'term', 'key', 'target')
VERDICTS = ('ok', 'bad', 'unsure')
FINDING_KINDS = ('wrong_value', 'wrong_word', 'omission', 'invented', 'order', 'structure', 'binding', 'other')
ENTRY_FIELDS = ('target_key', 'planted', 'planted_block', 'view_sha256', 'sheet_sha256s', 'judge_version')
VERDICT_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['verdict', 'findings'],
    'properties': {
        'verdict': {'type': 'string', 'enum': list(VERDICTS)},
        'findings': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['block', 'kind', 'severity', 'evidence'],
            'properties': {'block': {'type': 'string'}, 'kind': {'type': 'string', 'enum': list(FINDING_KINDS)},
                           'severity': {'type': 'string', 'enum': ['major', 'minor']}, 'evidence': {'type': 'string'}}}},
    },
}

RULE_KINDS = ('format_rule', 'class', 'attribute')
# A version that also proposes rules for the reader (decision 197.a, the operator, 10 Nov: "do we also get the valuable
# improvements of the reader prompt?"): clear format rules, classes and attributes of the vocabulary, gathered and merged
# across pages by `check_run reader-rules`, never applied by themselves.
VERDICT_SCHEMA_WITH_RULES = {
    **VERDICT_SCHEMA, 'required': ['verdict', 'findings', 'reader_rules'],
    'properties': {**VERDICT_SCHEMA['properties'], 'reader_rules': {'type': 'array', 'items': {
        'type': 'object', 'additionalProperties': False, 'required': ['kind', 'block', 'rule', 'class', 'attribute', 'value'],
        'properties': {'kind': {'type': 'string', 'enum': list(RULE_KINDS)}, 'block': {'type': 'string'}, 'rule': {'type': 'string'},
                       'class': {'type': 'string'}, 'attribute': {'type': 'string'}, 'value': {'type': 'string'}}}}},
}


@dataclass(frozen=True)
class Verdict:
    verdict: str
    findings: list = field(default_factory=list)
    reader_rules: list = field(default_factory=list)

    @property
    def major(self) -> list:
        return [finding for finding in self.findings if finding.get('severity') == 'major']

    @property
    def outcome(self) -> str:
        """ok or issue. A verdict of ok with minor findings stays ok; bad and unsure go to a person, and so does an ok that contradicts
        itself by naming a major finding."""
        return 'ok' if self.verdict == 'ok' and not self.major else 'issue'  # records before decision 97.a say 'bin'

    def as_dict(self) -> dict:
        found = {'verdict': self.verdict, 'findings': self.findings, 'outcome': self.outcome}
        return {**found, 'reader_rules': self.reader_rules} if self.reader_rules else found


def judge_versions() -> list[dict]:
    """The judge's versions, oldest first, each with its files and state (prototype, active, retired)."""
    return [version for version in json.loads(VERSIONS.read_text(encoding='utf-8'))['versions'] if version['role'] == 'judge']


def active_version() -> str:
    """The judge version the pipeline judges with: exactly one is active."""
    active = [version['version'] for version in judge_versions() if version['state'] == 'active']
    if len(active) != 1:
        raise ValueError(f'one active judge version expected, found {active}')
    return active[0]


def state_of(version: str) -> str:
    """prototype, active or retired; a version the registry does not know is an error, never a guess."""
    found = next((entry['state'] for entry in judge_versions() if entry['version'] == version), None)
    if found is None:
        raise ValueError(f'no judge version {version!r} in {VERSIONS.name}')
    return found


def version_of(record: dict) -> str:
    """The judge version a judge record was made with: records before the versions were named carry none, and were judge/1's."""
    return record.get('judge_version') or FIRST_VERSION


def entry_of(version: str) -> dict:
    state_of(version)  # an unknown version is refused by name
    return next(entry for entry in judge_versions() if entry['version'] == version)


def model_of(version: str) -> str:
    """The model a judge version runs on, as its registry entry names it."""
    return entry_of(version)['model']


def schema_of(version: str | None) -> dict:
    """The answer's schema: with rules for the reader for a version that proposes them (197.a), else the verdict alone, so
    every key made before stays the same."""
    return VERDICT_SCHEMA_WITH_RULES if version and entry_of(version).get('reader_rules') else VERDICT_SCHEMA


def system_prompt(version: str | None = None) -> str:
    """The judge's instructions of one version, the active one by default."""
    wanted = version or active_version()
    state_of(wanted)  # an unknown version is refused by name
    entry = next(entry for entry in judge_versions() if entry['version'] == wanted)
    return (CONVERSION / entry['files'][0]).read_bytes().decode('utf-8')


def cell_of(model: str, version: str) -> str:
    """The cell a judge request is filed under: a prototype's verdicts lie apart from the pipeline's, by name too."""
    return f'JUDGE-{model}' if state_of(version) != 'prototype' else f"JUDGE-{model}-{version.replace('/', '')}"


# A finding that contradicts its own evidence (decision 146.a, 9 Nov): the judge names a word wrong and quotes it printed and
# written alike ("printed 'Carlyse' ... written 'Carlyse'"), or says the two are identical. Its own rule says a finding states
# "printed X, written Y"; with X equal to Y there is no difference, so code voids it, and a person still sees it.
QUOTED = re.compile("'([^']+)'|\"([^\"]+)\"|\u2018([^\u2019]+)\u2019|\u201c([^\u201d]+)\u201d")
SAME_TEXT_KINDS = ('wrong_word', 'wrong_value')


def contradicts_itself(finding: dict, block_text: str | None = None, layer_text: str | None = None) -> bool:
    """Whether a finding names no difference: its evidence says the two are identical, or it quotes one string as printed and
    as written, or (given the judged block's text) every string it quotes stands word for word in that block, so the reading
    holds what the judge says the page prints. The last caught judge/2 on finance p. 5, which quoted 'Carlyse Ciocca' and
    'Carlyse', both in b12 (9 Nov). A real wrong word stays: 'Carlyle' does not stand in a block that says 'Carlyse'. A quoted
    string counts only as a whole run of words: '$2,467.' is not in '$2,467.48' (accounting p. 820, a value the judge rightly
    doubted, found by the audit before the rule acted). And the reading's word is not enough on its own: every quoted string
    must stand in the PDF's text layer too, a second witness that the reading and the print agree there; without a layer this
    part of the rule does not act, and a person decides (9 of 62 licensed cases differed from the layer, 9 Nov)."""
    evidence = finding.get('evidence') or ''
    if re.search(r'\bidentical\b', evidence, re.IGNORECASE):
        return True
    quoted = [' '.join(next(group for group in match if group).split()) for match in QUOTED.findall(evidence)]
    if finding.get('kind') not in SAME_TEXT_KINDS or len(quoted) < 2:
        return False
    if len(set(quoted)) == 1:
        return True
    text, layer = ' '.join((block_text or '').split()), ' '.join((layer_text or '').split())
    return bool(text) and bool(layer) and all(re.search(rf'(?<!\w){re.escape(string)}(?!\w)', text)
                                              and re.search(rf'(?<!\w){re.escape(string)}(?!\w)', layer) for string in quoted)


def blocks_if_needed(verdict: dict | None, text: str | None, form: str = 'markdown') -> dict[str, str]:
    """The judged reading's blocks by id, read only where a finding could need them (a wrong word or value)."""
    if not verdict or not text or not any(finding.get('kind') in SAME_TEXT_KINDS for finding in verdict.get('findings', [])):
        return {}
    try:
        return {block.id: block.body for block in page_contract.parse(text, form).blocks}
    except Exception:  # a reading that does not parse gives no blocks, and the rule falls back to the evidence alone
        return {}


def with_void(verdict: dict | None, blocks: dict[str, str] | None = None, layer: str | None = None) -> dict | None:
    """A verdict with each self-contradicting finding marked void, and its outcome as the findings that stand make it: a bad
    verdict whose every major finding is void comes out ok. The judge's own outcome stays beside it as `judge_outcome`.
    `blocks` are the judged reading's block texts by id (`blocks_if_needed`) and `layer` the page's PDF text layer, for the
    part of the rule that reads the reading itself and checks it against the print."""
    if not verdict:
        return verdict
    blocks = blocks or {}
    findings = [{**finding, 'void': True} if contradicts_itself(finding, blocks.get(finding.get('block')), layer) else finding
                for finding in verdict.get('findings', [])]
    standing = [finding for finding in findings if not finding.get('void')]
    voided = len(findings) - len(standing)
    if not voided:
        return verdict
    outcome = Verdict(verdict['verdict'], standing).outcome
    if verdict['verdict'] == 'bad' and not any(finding.get('severity') == 'major' for finding in standing):
        outcome = 'ok'  # its every major finding contradicts itself: nothing the judge saw stands
    return {**verdict, 'findings': findings, 'outcome': outcome, 'judge_outcome': verdict.get('outcome'), 'void': voided}


def judge_view(parsed: ParsedPage) -> str:
    """The reading as the judge sees it: no boxes, the derived description marked. Nothing of stage 2."""
    entries = []
    for block in parsed.blocks:
        attrs = ' '.join(f'{name}={block.attrs[name]}' for name in VIEW_ATTRIBUTES if name in block.attrs)
        derived = ' DERIVED' if page_contract.VOCAB['classes'].get(block.cls, {}).get('content') == 'D' else ''
        entries.append(f"[{block.id} {block.cls}{' ' + attrs if attrs else ''}{derived}]\n{block.body}")
    front = ', '.join(f'{name}: {parsed.front[name]}' for name in ('printed_label', 'page_kind') if name in parsed.front)
    return f'Transcription ({front}):\n\n' + '\n\n'.join(entries)


def _image(png: bytes) -> dict:
    return {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': base64.standard_b64encode(png).decode('ascii')},
            'transformations': dict(reader_requests.IMAGE_TRANSFORMATIONS)}


def message_params(*, model: str, system_text: str, page_png: bytes, sheet_pngs: list[bytes], view: str, pdf_page: int,
                   max_tokens: int = MAX_TOKENS, schema: dict | None = None) -> dict:
    content = [{'type': 'text', 'text': f'The image of PDF page {pdf_page}:'}, _image(page_png)]
    if sheet_pngs:
        content.append({'type': 'text', 'text': 'The formulas of the transcription, rendered:'})
        content.extend(_image(png) for png in sheet_pngs)
    content.append({'type': 'text', 'text': view})
    settings = copy.deepcopy(reader_requests.MODEL_SETTINGS[model])
    settings['output_config'] = {**settings.get('output_config', {}),
                                 'format': {'type': 'json_schema', 'schema': schema or VERDICT_SCHEMA}}
    return {**settings, 'model': model, 'max_tokens': max_tokens,
            'system': [{'type': 'text', 'text': system_text, 'cache_control': {'type': 'ephemeral'}}],
            'messages': [{'role': 'user', 'content': content}]}


def judge_key(*, target_key: str, model: str, system_sha: str, image_sha: str, view_sha: str, sheet_shas: list[str], max_tokens: int,
              again: int = 0, schema: dict | None = None) -> str:
    """Everything that was asked, so a changed prompt, view or sheet is a new request and the same one is never bought twice.
    `again` asks the same once more on purpose (a live demonstration, a check of the judge's own variance); 0 keeps every key
    made before it existed."""
    spec = {'kind': 'judge', 'target': target_key, 'model': model, 'system': system_sha, 'image': image_sha, 'view': view_sha,
            'sheets': sheet_shas, 'max_tokens': max_tokens, 'settings': reader_requests.MODEL_SETTINGS[model],
            'schema': hashlib.sha256(json.dumps(schema or VERDICT_SCHEMA, sort_keys=True).encode('utf-8')).hexdigest()}
    if again:
        spec['again'] = again
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def entry_for(record: dict, parsed: ParsedPage, model: str, planted=None, version: str | None = None, again: int = 0) -> dict:
    """A judge request on a stored reading, or on that reading with an error planted. Takes the exact image the reader saw.
    `version` names the judge's instructions (the active one by default); a prototype's request is filed under a cell of its
    own, and `again` asks once more what was asked before."""
    version = version or active_version()
    store = open_store(record['mirror'])
    image_png = store.get_input(record['image_sha256'], '.png')
    sheet_pngs = formula_sheet.sheets(parsed)
    sheet_shas = [store.put_input(png, '.png') for png in sheet_pngs]
    view = judge_view(parsed)
    view_sha = store.put_input(view.encode('utf-8'), '.txt')
    system_text = system_prompt(version)
    store.put_prompt(system_text)
    target = record['reading_key'] + (f':{planted.kind}:{planted.block}' if planted else '')
    schema = schema_of(version)
    max_tokens = MAX_TOKENS_WITH_RULES if schema is VERDICT_SCHEMA_WITH_RULES else MAX_TOKENS
    key = judge_key(target_key=target, model=model, system_sha=reader_requests.sha256_text(system_text), image_sha=record['image_sha256'],
                    view_sha=view_sha, sheet_shas=sheet_shas, max_tokens=max_tokens, again=again, schema=schema)
    width, height = record['image_size']
    patches = page_render.patches(width, height) + sum(page_render.patches(*Image.open(io.BytesIO(png)).size) for png in sheet_pngs)
    return {'kind': 'judge', 'reading_key': key, 'custom_id': reader_requests.custom_id(key), 'cell': cell_of(model, version),
            'page_id': record.get('page_id'), 'judge_version': version,
            'file': record['file'], 'pdf_page': record['pdf_page'], 'work': record['work'], 'mirror': record['mirror'], 'model': model, 'mode': 'batch',
            'attempt': 0, 'replicate': again, 'max_tokens': max_tokens, 'image_sha256': record['image_sha256'], 'image_size': record['image_size'],
            'image_bytes': len(image_png) + sum(len(png) for png in sheet_pngs), 'sheet_sha256s': sheet_shas, 'view_sha256': view_sha, 'target_key': record['reading_key'],
            'planted': planted.kind if planted else None, 'planted_block': planted.block if planted else None,
            'estimate_usd': estimate_usd(model, patches, len(view))}


def params_from_entry(entry: dict) -> dict:
    store = open_store(entry['mirror'])
    return message_params(model=entry['model'], system_text=system_prompt(entry.get('judge_version') or FIRST_VERSION), page_png=store.get_input(entry['image_sha256'], '.png'),
                          sheet_pngs=[store.get_input(sha, '.png') for sha in entry['sheet_sha256s']],
                          view=store.get_input(entry['view_sha256'], '.txt').decode('utf-8'), pdf_page=entry['pdf_page'],
                          max_tokens=entry['max_tokens'], schema=schema_of(entry.get('judge_version')))


def parse_verdict(text: str) -> Verdict | None:
    """None when the answer is not a verdict. Structured outputs make that rare, but it stays untrusted input."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get('verdict') not in VERDICTS or not isinstance(data.get('findings'), list):
        return None
    rules = [rule for rule in data.get('reader_rules') or [] if isinstance(rule, dict) and rule.get('kind') in RULE_KINDS]
    return Verdict(data['verdict'], [finding for finding in data['findings'] if isinstance(finding, dict)], rules)


def check_answer(entry: dict, text: str, stop_reason: str | None) -> tuple[str, dict | None]:
    """The result class of a judge request and the verdict a record keeps."""
    if stop_reason == 'refusal':
        return 'refused', None
    if stop_reason == 'max_tokens':
        return 'truncated', None
    if stop_reason != 'end_turn':
        return 'unexpected', None
    verdict = parse_verdict(text)
    return ('ok', verdict.as_dict()) if verdict else ('malformed', None)


def estimate_usd(model: str, image_tokens: int, view_chars: int) -> float:
    """A planning estimate: a character is about a third of a token in this mix of prose, numbers and LaTeX."""
    system_tokens = len(system_prompt()) // 4
    return anthropic_client.cost_usd(model, image_tokens + view_chars // 3, EXPECTED_OUTPUT_TOKENS, batch=True, cache_write_tokens=system_tokens)
