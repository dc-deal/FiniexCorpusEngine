"""The one place that knows how to reach OpenRouter.

The chatbot's model calls, embeddings and chat, go through OpenRouter with the project's key, read
from `.env` (git-ignored). The key never appears in code, in a log, or in anything the interface
could show. The two other providers have their own modules: `anthropic_client.py` (reading page
images) and `openai_client.py` (the same embedding model without OpenRouter).
"""

import json
import os
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

ROOT = Path(__file__).resolve().parents[3]
OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'
CHAT_TIMEOUT_SECONDS = 120

# Measured on 2026-09-28 from GET /api/v1/embeddings/models: 0.02 USD per million input tokens.
EMBEDDING_MODEL = 'openai/text-embedding-3-small'
EMBEDDING_USD_PER_MILLION_TOKENS = 0.02
EMBEDDING_DIMENSIONS = 1536


class MissingApiKeyError(RuntimeError):
    """Raised when no OpenRouter key is configured, with the fix in the message."""


def api_key() -> str:
    """Read the OpenRouter key from the environment or `.env`.

    Returns:
        The key.

    Raises:
        MissingApiKeyError: When no key is configured.
    """
    load_dotenv(ROOT / '.env')
    key = os.environ.get('OPENROUTER_API_KEY', '').strip()
    if not key:
        raise MissingApiKeyError(
            'OPENROUTER_API_KEY is not set. Copy .env.example to .env and put the key in it.')
    return key


def key_usage() -> float:
    """What the key has spent so far, in USD, as OpenRouter reports it (GET /api/v1/key).

    Read before and after a run, the difference is what the run actually cost, as opposed to
    what the token count estimated.

    Returns:
        The key's cumulative usage in USD.
    """
    request = urllib.request.Request(f'{OPENROUTER_BASE_URL}/key',
                                     headers={'Authorization': f'Bearer {api_key()}'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return float(json.load(response)['data']['usage'])


# OpenRouter books a run's cost late and in parts. Measured 2026-09-28: the first run's cost
# appeared 30-60 s after the run (read at once it showed 0.0000, which was stored), and the second
# run's arrived as 0.023198 and, 15 s later, the rest up to 0.025302. So the cost counts as booked
# only once two readings in a row agree. That was not enough on 2026-09-30: a rebuild stood still at
# 0.004864 for 15 s, and the rest (up to its estimate of 0.007667) arrived later. So when an
# estimate is known, the readings must also have reached 95 % of it.
BOOKING_TIMEOUT_SECONDS = 240
BOOKING_POLL_SECONDS = 15
BOOKED_SHARE_OF_ESTIMATE = 0.95


def measured_cost(usage_before: float, estimate: float | None = None) -> float | None:
    """Wait until a run's cost has been booked in full on the key, then return it.

    Args:
        usage_before: The key's usage read before the run.
        estimate: The run's estimated cost, if known. The estimate has equalled the full booking in
            every run so far; a real price change would show up as a timeout, not as a wrong number.

    Returns:
        The cost once two consecutive readings agree (and, with an estimate, have reached 95 % of
        it), or None if that did not happen within the timeout. None means "not measured", which is
        not the same as 0.
    """
    floor = estimate * BOOKED_SHARE_OF_ESTIMATE if estimate else 0.0
    deadline = time.monotonic() + BOOKING_TIMEOUT_SECONDS
    previous = None
    while time.monotonic() <= deadline:
        spent = key_usage() - usage_before
        if spent > 0 and spent >= floor and previous is not None and abs(spent - previous) < 1e-9:
            return spent
        previous = spent
        time.sleep(BOOKING_POLL_SECONDS)
    return None


def model_prices(model_ids: list[str]) -> dict[str, dict[str, float]]:
    """Current prices of chat models, in USD per million tokens (GET /api/v1/models, no key needed).

    Read at run time rather than written down, because OpenRouter's prices change and a stale
    constant would make every cost estimate quietly wrong.

    Returns:
        {model_id: {'input': USD, 'output': USD}} for every id OpenRouter lists.
    """
    with urllib.request.urlopen(f'{OPENROUTER_BASE_URL}/models', timeout=30) as response:
        listed = {m['id']: m['pricing'] for m in json.load(response)['data']}
    return {model_id: {'input': float(listed[model_id]['prompt']) * 1e6,
                       'output': float(listed[model_id]['completion']) * 1e6}
            for model_id in model_ids if model_id in listed}


def chat_model(model: str, reasoning_effort: str | None = None, max_tokens: int = 2000) -> ChatOpenAI:
    """A chat model behind OpenRouter, as the course builds it (`ChatOpenAI` with a `base_url`).

    Two traps are handled here, both measured:

    - Reasoning is sent as `extra_body={'reasoning': {'effort': ...}}`, the route OpenRouter
      documents for every provider.
    - Reasoning models spend their output budget on invisible reasoning tokens and then return
      `content: null` without an error. `max_tokens` is therefore generous, and every caller checks
      for an empty answer.

    `temperature=0`, as in the course, is sent only to models without reasoning: reasoning models do
    not support it, and OpenRouter drops an unsupported parameter silently.

    Args:
        model: An OpenRouter model id, e.g. 'openai/gpt-4.1-mini'.
        reasoning_effort: 'minimal', 'low', 'medium' or 'high' for a reasoning model; None otherwise.
        max_tokens: The output budget, reasoning tokens included.
    """
    options = {'extra_body': {'reasoning': {'effort': reasoning_effort}}} if reasoning_effort else {'temperature': 0}
    # An explicit timeout and no hidden retries, as the Anthropic and OpenAI clients have (decision 95.a): ChatOpenAI's
    # defaults are no timeout and two retries, so a hanging provider blocked a turn without end and a failure could be
    # billed three times. 120 s against a router median of 3.4 s and a maximum of 15 s, measured on 2026-11-05.
    return ChatOpenAI(model=model, base_url=OPENROUTER_BASE_URL, api_key=api_key(), max_tokens=max_tokens,
                      timeout=CHAT_TIMEOUT_SECONDS, max_retries=0, **options)


def embeddings() -> OpenAIEmbeddings:
    """Build the embedding client used for indexing and for queries.

    `check_embedding_ctx_length=False` makes the class send the text itself. Its default is to
    tokenise locally with OpenAI's tokenizer and send token ids. Measured 2026-09-28: OpenRouter
    accepts both for this model, and both give the same vector (cosine 1.000000). The text is sent
    anyway, because token ids tie the call to OpenAI's tokenizer. Another embedding model behind
    OpenRouter would read the same ids as different tokens.

    Returns:
        A LangChain embeddings object bound to OpenRouter.
    """
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        base_url=OPENROUTER_BASE_URL,
        api_key=api_key(),
        check_embedding_ctx_length=False,
    )
