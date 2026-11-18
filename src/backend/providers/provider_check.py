"""Check that each model provider answers: Anthropic, OpenRouter and OpenAI.

One minimal paid call per provider (well under 0.001 USD in all), the balances that an API can
read, and one measurement: whether OpenRouter and OpenAI return the same vectors for the same text
from the same embedding model. The results go to logs/ (git-ignored) before they are printed.

    python -m backend.providers.provider_check                     # keys from .env
    python -m backend.providers.provider_check --extra-env PATH    # take a missing provider key from another .env

`--extra-env` takes only the three provider keys from that file, sets them for this process alone
and copies nothing.
"""

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from backend.configuration import data_paths
from backend.providers import anthropic_client, openai_client, openrouter_client

ROOT = Path(__file__).resolve().parents[3]
KEY_NAMES = ('ANTHROPIC_API_KEY', 'OPENROUTER_API_KEY', openai_client.KEY_NAME)
PROBE = 'Reply with the single word: ok'
PROBE_MODELS = {'anthropic': 'claude-haiku-5-5', 'openrouter': 'openai/gpt-4.1-mini'}
SENTENCES = ['The Sharpe ratio measures excess return per unit of risk.',
             'Drawdown is the decline from a peak to a trough.']
SECRET = re.compile(r'(sk-[A-Za-z0-9_]{1,4})[A-Za-z0-9_-]+')


def redact(text: str) -> str:
    """Cut anything that looks like a key to its first characters, for error messages."""
    return SECRET.sub(r'\1…', text)


def take_missing_keys(path: Path, environ=os.environ) -> list[str]:
    """Set the provider keys this process lacks from another .env file; take nothing else.

    Returns:
        The names of the keys taken.
    """
    taken = []
    for name, value in dotenv_values(path).items():
        if name in KEY_NAMES and value and not environ.get(name):
            environ[name] = value
            taken.append(name)
    return taken


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def check_anthropic() -> dict:
    """Model list and token count (both free), then one short answer from Haiku."""
    client = anthropic_client.client()
    listed = {model.id for model in client.models.list()}
    model = PROBE_MODELS['anthropic']
    messages = [{'role': 'user', 'content': PROBE}]
    counted = client.messages.count_tokens(model=model, messages=messages).input_tokens
    started = time.monotonic()
    # Thinking off: Haiku 5.5 accepts that at its default effort, and a one-word answer needs none.
    reply = client.messages.create(model=model, max_tokens=200, thinking={'type': 'disabled'},
                                   messages=messages)
    usage = reply.usage
    return {
        'reader_models_available': {m: m in listed for m in anthropic_client.READER_MODELS},
        'count_tokens_free': counted,
        'probe': {'model': model, 'answer': anthropic_client.answer_text(reply),
                  'stop_reason': reply.stop_reason, 'input_tokens': usage.input_tokens,
                  'output_tokens': usage.output_tokens, 'seconds': round(time.monotonic() - started, 2),
                  'cost_usd': anthropic_client.cost_usd(model, usage.input_tokens, usage.output_tokens)},
        'balance': 'no API for a normal key: the Claude Console shows it (organisation credits)',
    }


def openrouter_get(path: str) -> dict:
    request = urllib.request.Request(f'{openrouter_client.OPENROUTER_BASE_URL}{path}',
                                     headers={'Authorization': f'Bearer {openrouter_client.api_key()}'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)['data']


def check_openrouter(vectors: dict) -> dict:
    """The key's limit and usage, the account's credits if readable, one answer, one embedding."""
    key = openrouter_get('/key')
    try:
        credits = openrouter_get('/credits')
        account = {'total_credits_usd': credits.get('total_credits'), 'total_usage_usd': credits.get('total_usage')}
    except urllib.error.HTTPError as error:
        account = f'not readable with this key (HTTP {error.code})'
    model = PROBE_MODELS['openrouter']
    reply = openrouter_client.chat_model(model, max_tokens=20).invoke(PROBE)
    vectors['openrouter'] = openrouter_client.embeddings().embed_documents(SENTENCES)
    return {
        'key': {'limit_usd': key.get('limit'), 'usage_usd': key.get('usage'),
                'remaining_usd': key.get('limit_remaining'), 'expires_at': key.get('expires_at')},
        'account': account,
        'probe': {'model': model, 'answer': reply.content, 'usage': reply.usage_metadata},
        'embedding': {'model': openrouter_client.EMBEDDING_MODEL, 'dimensions': len(vectors['openrouter'][0])},
    }


def check_openai(vectors: dict) -> dict:
    """The embedding models this key can list (free), one embedding, the comparison with OpenRouter."""
    try:
        listed = sorted(model.id for model in openai_client.client().models.list() if 'embedding' in model.id)
    except Exception as error:  # a project key restricted to one model may not list models at all
        listed = f'not listable with this key ({type(error).__name__})'
    own = openai_client.embeddings().embed_documents(SENTENCES)
    report = {
        'embedding_models_available': listed,
        'embedding': {'model': openai_client.EMBEDDING_MODEL, 'dimensions': len(own[0])},
        'balance': 'no API for a project key: the OpenAI dashboard shows it',
    }
    if 'openrouter' in vectors:
        report['cosine_to_openrouter_vectors'] = [round(cosine(a, b), 6) for a, b in zip(vectors['openrouter'], own)]
    return report


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--extra-env', type=Path, help='another .env file to take a missing provider key from')
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')  # first, so this project's own keys win over the extra file
    results = {'checked_at': datetime.now().isoformat(timespec='seconds'),
               'keys_taken_from_extra_env': take_missing_keys(args.extra_env) if args.extra_env else []}
    vectors = {}
    checks = {'anthropic': check_anthropic,
              'openrouter': lambda: check_openrouter(vectors),
              'openai': lambda: check_openai(vectors)}
    for name, check in checks.items():
        try:
            results[name] = check()
        except Exception as error:  # one provider failing must not hide the others
            results[name] = {'error': f'{type(error).__name__}: {redact(str(error))}'}
    out = data_paths.LOGS / f'provider_check_{datetime.now():%Y%m%d_%H%M%S}.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f'\nwritten to {out.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
