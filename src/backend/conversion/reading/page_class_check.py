"""A cheap model's look at pages the free check calls text only, to measure what the check misses (decision 66.a).

The rules in `page_classes` were tuned on textbooks; on other books they may miss structure. Haiku sees a sample of the pages
they would send to the text layer and names only the kinds of content on each (formula, table, figure, code), never their
text, so the answer is short and holds nothing of the book. A request plugs into the batch runner as its own kind.
"""

import base64
import copy
import hashlib
import json
from pathlib import Path

from backend.conversion.reading import reader_requests
from backend.conversion.store.reading_store import open_store
from backend.providers import anthropic_client

PROMPT = Path(__file__).resolve().parents[1] / 'prompts' / 'page_classes_check.txt'
MODEL = 'claude-haiku-5-5'
MAX_TOKENS = 200
EXPECTED_OUTPUT_TOKENS = 30
KINDS = ('formula', 'table', 'figure', 'code')
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['classes'],
          'properties': {'classes': {'type': 'array', 'items': {'type': 'string', 'enum': list(KINDS)}}}}
ENTRY_FIELDS = ('system_sha256', 'rule_classes')


def system_prompt() -> str:
    return PROMPT.read_bytes().decode('utf-8')


def message_params(*, model: str, system_text: str, page_png: bytes, pdf_page: int, max_tokens: int = MAX_TOKENS) -> dict:
    image = {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': base64.standard_b64encode(page_png).decode('ascii')},
             'transformations': dict(reader_requests.IMAGE_TRANSFORMATIONS)}
    settings = copy.deepcopy(reader_requests.MODEL_SETTINGS[model])
    settings['output_config'] = {**settings.get('output_config', {}), 'format': {'type': 'json_schema', 'schema': SCHEMA}}
    return {**settings, 'model': model, 'max_tokens': max_tokens,
            'system': [{'type': 'text', 'text': system_text, 'cache_control': {'type': 'ephemeral'}}],
            'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': f'The image of PDF page {pdf_page}:'}, image]}]}


def check_key(*, file_name: str, pdf_page: int, model: str, system_sha: str, image_sha: str) -> str:
    spec = {'kind': 'classcheck', 'file': file_name, 'pdf_page': pdf_page, 'model': model, 'system': system_sha, 'image': image_sha,
            'max_tokens': MAX_TOKENS, 'settings': reader_requests.MODEL_SETTINGS[model],
            'schema': hashlib.sha256(json.dumps(SCHEMA, sort_keys=True).encode('utf-8')).hexdigest()}
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


def entry_for(*, mirror: str, file_name: str, work: str, pdf_page: int, image, rule_classes: list, model: str = MODEL) -> dict:
    """A request for one page: the rendered image is stored by its hash, like a reading's, and the key holds what is asked."""
    store = open_store(mirror)
    image_sha = store.put_input(image.png, '.png')
    system_text = system_prompt()
    system_sha = store.put_prompt(system_text)
    key = check_key(file_name=file_name, pdf_page=pdf_page, model=model, system_sha=system_sha, image_sha=image_sha)
    estimate = anthropic_client.cost_usd(model, image.patches + len(system_text) // 4, EXPECTED_OUTPUT_TOKENS, batch=True)
    return {'kind': 'classcheck', 'reading_key': key, 'custom_id': reader_requests.custom_id(key), 'cell': f'CLASSCHECK-{model}',
            'page_id': f'{work}:p{pdf_page:04d}', 'file': file_name, 'pdf_page': pdf_page, 'work': work, 'mirror': mirror,
            'model': model, 'mode': 'batch', 'attempt': 0, 'replicate': 0, 'max_tokens': MAX_TOKENS, 'image_sha256': image_sha,
            'image_size': [image.width, image.height], 'image_bytes': len(image.png), 'system_sha256': system_sha,
            'rule_classes': rule_classes, 'estimate_usd': estimate}


def params_from_entry(entry: dict) -> dict:
    store = open_store(entry['mirror'])
    return message_params(model=entry['model'], system_text=store.get_prompt(entry['system_sha256']),
                          page_png=store.get_input(entry['image_sha256'], '.png'), pdf_page=entry['pdf_page'],
                          max_tokens=entry['max_tokens'])


def check_answer(entry: dict, text: str, stop_reason: str | None) -> tuple[str, dict | None]:
    """ok with the named classes, or why not. The answer is untrusted input: only known kinds are kept."""
    if stop_reason != 'end_turn':
        return ('refused' if stop_reason == 'refusal' else 'truncated' if stop_reason == 'max_tokens' else 'unexpected'), None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return 'malformed', None
    if not isinstance(data, dict) or not isinstance(data.get('classes'), list):
        return 'malformed', None
    return 'ok', {'classes': sorted({name for name in data['classes'] if name in KINDS})}
