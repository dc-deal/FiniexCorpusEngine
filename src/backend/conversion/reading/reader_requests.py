"""What a vision reader is asked: the prompts, the parameters per model, and the reading key.

The system prompt is the rules of contract page/1 plus one of two output formats, `markdown` or `json`
(`prompts/reader_page1_*.txt`). The user turn gives the work, the PDF page and the image size, then the work card,
then asks to read the page. The image goes first and carries `transformations: {"oversized_image": "error"}`, because a
silent downscale would break every pixel bbox (measured 2026-10-30 on the free count_tokens endpoint: accepted on the
image block, and a too large image then gets a 400; inside `source` it is rejected). Form json also sends the page
schema as `output_config.format`, beside the model's effort (measured 2026-10-30: accepted with effort and thinking on
Haiku and Sonnet).

The reading key is the sha256 of a canonical JSON of everything that was asked: the image's hash, the hashes of the
system prompt, the user text and the schema, the model, the form and the parameters. The same question has the same
key, so a reading is never bought twice; a changed prompt or card, a deliberate repeat (`replicate`) or a retry
(`attempt`) is a new key. Like a tick store keyed by instrument and timestamp: writing the same reading twice changes
nothing.

Parameters per model (pilot plan, fixed settings; Claude API reference on the 5.5 models):

- Haiku 5.5: thinking disabled, effort high (disabled is accepted at effort high or below).
- Sonnet 5.5: thinking `between_tools`, effort high (`disabled` returns a 400 on Sonnet 5.5).
- Opus 5.5: thinking cannot be switched off; effort low keeps it short.

No `temperature`, `top_p` or `top_k`: API version 2026-10-21, which the SDK sends, rejects them.
"""

import base64
import copy
import hashlib
import json
from pathlib import Path

import anthropic
from anthropic import _constants

from backend.conversion.contract import page_contract
from backend.providers import anthropic_client

PROMPTS = Path(__file__).resolve().parents[1] / 'prompts'
RULES_PROMPT = PROMPTS / 'reader_page1_rules.txt'
VERSIONS = PROMPTS.parent / 'prompt_versions.json'  # read here, not through page_judge, which imports this module
FIRST_VERSION = 'page/1'
USER_TURN_TEMPLATE = ('work: {work}\npdf_page: {pdf_page}\nimage_size: {width}x{height}\n\n'
                      'Work card: {work_card}\n\nRead this page and write its page file.')
IMAGE_TRANSFORMATIONS = {'oversized_image': 'error'}
MAX_TOKENS = 16000
API_VERSION = _constants.ANTHROPIC_API_VERSION

MODEL_SETTINGS = {
    'claude-haiku-5-5': {'thinking': {'type': 'disabled'}, 'output_config': {'effort': 'high'}},
    'claude-sonnet-5-5': {'thinking': {'type': 'between_tools'}, 'output_config': {'effort': 'high'}},
    'claude-opus-5-5': {'output_config': {'effort': 'low'}},
}

# For estimates only; the usage of each result replaces them. The API has not counted the new prompts yet, so these are
# proxies, to be replaced by what `free-checks` prints: tiktoken's cl100k_base count (2026-10-30: 3,118 markdown, 3,699
# json, 454 schema, about 160 for a user turn) times 1.46, the factor between the API's count and tiktoken's on the old
# prompt (1,745 against 1,193). On answers the factor was 1.41 (47 stored public readings, API output tokens against
# tiktoken). An image costs its 28 x 28 patches plus 3 (counted 2026-10-29).
SYSTEM_PROMPT_TOKENS = {'markdown': 4561, 'json': 5411}
JSON_SCHEMA_TOKENS = 664
USER_TURN_TOKENS = 230
IMAGE_TOKEN_OVERHEAD = 3
OPUS_THINKING_TOKENS = 800
JSON_OUTPUT_FACTOR = 1.55  # a page as JSON against Markdown, by tiktoken: 1.46 to 1.58 on the 3 example pages (2026-10-30)
BATCH_CACHE_HIT_SHARE = 405 / 414  # measured in the pilot; a smoke reading finds no cache and writes the prompt


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def system_prompt(form: str, version: str = FIRST_VERSION) -> str:
    """The rules plus the output format of this form, byte for byte as the files hold them. page/1 as it always was, so no
    key changes; another version (decision 207.a, a prototype first) reads the files its registry entry names, Markdown only."""
    if form not in page_contract.FORMS:
        raise ValueError(f'unknown form {form!r}, expected one of {page_contract.FORMS}')
    if version == FIRST_VERSION:
        return RULES_PROMPT.read_bytes().decode('utf-8') + (PROMPTS / f'reader_page1_{form}.txt').read_bytes().decode('utf-8')
    entry = next((entry for entry in json.loads(VERSIONS.read_text(encoding='utf-8'))['versions']
                  if entry['role'] == 'reader' and entry['version'] == version), None)
    if entry is None or form != 'markdown':
        raise ValueError(f'no reader version {version!r} for the {form} form in {VERSIONS.name}')
    by_part = {part: name for name, part in entry['parts'].items()}
    return ''.join((PROMPTS.parent / by_part[part]).read_bytes().decode('utf-8') for part in ('rules', 'format'))


def user_turn(*, work: str, pdf_page: int, image_size: tuple[int, int], work_card: str) -> str:
    return USER_TURN_TEMPLATE.format(work=work, pdf_page=pdf_page, width=image_size[0], height=image_size[1],
                                     work_card=work_card)


def output_config(model: str, form: str) -> dict:
    """The model's effort, for form json with the page schema beside it."""
    config = copy.deepcopy(MODEL_SETTINGS[model]['output_config'])
    if form == 'json':
        config['format'] = {'type': 'json_schema', 'schema': page_contract.json_schema()}
    return config


def reading_spec(*, image_sha: str, model: str, system_sha: str, user_sha: str, form: str, max_tokens: int,
                 replicate: int, attempt: int, mode: str) -> dict:
    """Everything that was asked, as hashes and parameters: the input of the reading key."""
    settings = MODEL_SETTINGS[model]
    return {
        'inputs': {'image': image_sha},
        'model': model,
        'prompt': {'system': system_sha, 'user': user_sha, 'form': form,
                   'schema': sha256_text(_canonical(page_contract.json_schema())) if form == 'json' else None},
        'params': {'max_tokens': max_tokens, 'thinking': settings.get('thinking'),
                   'effort': settings['output_config']['effort'], 'transformations': IMAGE_TRANSFORMATIONS,
                   'anthropic_version': API_VERSION, 'cache_control': 'ephemeral', 'replicate': replicate,
                   'attempt': attempt},
        'mode': mode,
    }


def reading_key(spec: dict) -> str:
    return hashlib.sha256(_canonical(spec).encode('utf-8')).hexdigest()


def custom_id(key: str) -> str:
    """The batch request id: 'r' and 40 hex characters, well inside the API's 64-character limit."""
    return 'r' + key[:40]


def message_params(*, model: str, form: str, system_text: str, user_text: str, png: bytes,
                   max_tokens: int = MAX_TOKENS) -> dict:
    """The Messages API parameters of one page reading: the image first, the text after it."""
    image = {'type': 'image',
             'source': {'type': 'base64', 'media_type': 'image/png',
                        'data': base64.standard_b64encode(png).decode('ascii')},
             'transformations': dict(IMAGE_TRANSFORMATIONS)}
    return {
        **copy.deepcopy(MODEL_SETTINGS[model]),
        'model': model,
        'max_tokens': max_tokens,
        'system': [{'type': 'text', 'text': system_text, 'cache_control': {'type': 'ephemeral'}}],
        'messages': [{'role': 'user', 'content': [image, {'type': 'text', 'text': user_text}]}],
        'output_config': output_config(model, form),
    }


def estimate_usd(model: str, image_tokens: int, output_tokens: int, form: str, batch: bool = True) -> float:
    """A planning estimate; the spend guard adds its own margin on top."""
    system_tokens = SYSTEM_PROMPT_TOKENS[form] + (JSON_SCHEMA_TOKENS if form == 'json' else 0)
    hit_share = BATCH_CACHE_HIT_SHARE if batch else 0.0
    thinking = OPUS_THINKING_TOKENS if model == 'claude-opus-5-5' else 0
    answer = output_tokens * (JSON_OUTPUT_FACTOR if form == 'json' else 1.0) + thinking
    return anthropic_client.cost_usd(model, image_tokens + IMAGE_TOKEN_OVERHEAD + USER_TURN_TOKENS, answer, batch=batch,
                                     cache_write_tokens=system_tokens * (1 - hit_share),
                                     cache_read_tokens=system_tokens * hit_share)


def sdk_version() -> str:
    return anthropic.__version__
