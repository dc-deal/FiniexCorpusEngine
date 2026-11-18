"""The one place that knows how to reach Anthropic's Claude API.

Used for reading page images (the vision conversion of the sources), paid for by the API credit of
The operator's Claude plan. Claude offers no embedding model, so embeddings never come from here
(`openrouter_client.py`, `openai_client.py`). The key is read from `.env` (git-ignored) and never
appears in code, in a log, or in anything the interface could show.

The official `anthropic` SDK is used rather than LangChain's `ChatAnthropic`, because the
conversion runs through the Message Batches API (half price), which LangChain does not cover.
The chat's models are the exception (`chat_model`, decision 287.b): there LangChain's `ChatAnthropic` is the maintained
component with the interface the agent, the router and the generator already use.
"""

import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

ROOT = Path(__file__).resolve().parents[3]

READER_MODELS = ('claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5')

# USD per million tokens (input, output), from the Claude API reference as of 2026-10; recheck on
# the pricing page before a large run. Haiku 5.5 has a second rate card (0.50 / 2.50) for prompts
# above 100,000 tokens, which a page never reaches. The Batch API halves both.
PRICES_USD_PER_MILLION = {
    'claude-haiku-5-5': (0.10, 0.50),
    'claude-sonnet-5-5': (2.00, 10.00),
    'claude-opus-5-5': (4.00, 20.00),
}
BATCH_DISCOUNT = 0.5
# Prompt caching: a 5-minute cache write costs 1.25 x the input price, a read 0.1 x, on Opus 5.5
# 0.05 x (Claude API reference, prompt caching, 2026-10).
CACHE_WRITE_FACTOR = 1.25
CACHE_READ_FACTOR = {'claude-opus-5-5': 0.05}
DEFAULT_CACHE_READ_FACTOR = 0.10

# No hidden retries: the SDK's default of 2 retries would bill a failed page up to three times
# and hide the failure. A caller that wants a retry makes it, and logs it. The SDK's default
# timeout of 10 minutes is shortened, but kept long enough for a dense page read by Opus.
TIMEOUT_SECONDS = 300
MAX_RETRIES = 0
CHAT_TIMEOUT_SECONDS = 120  # a chat call, as on the OpenRouter route (openrouter_client.CHAT_TIMEOUT_SECONDS)


class MissingApiKeyError(RuntimeError):
    """Raised when no Anthropic key is configured, with the fix in the message."""


def api_key() -> str:
    """Read the Anthropic key from the environment or `.env`.

    Returns:
        The key.

    Raises:
        MissingApiKeyError: When no key is configured.
    """
    load_dotenv(ROOT / '.env')
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not key:
        raise MissingApiKeyError(
            'ANTHROPIC_API_KEY is not set. Create a key in the Claude Console and put it in .env '
            '(see .env.example).')
    return key


def client() -> anthropic.Anthropic:
    """The SDK client, with an explicit timeout and no automatic retries.

    The SDK sends the API version its release defaults to (`2026-10-21` from 2.0.0 on). On that
    version `temperature`, `top_p` and `top_k` are rejected with a 400, so no call here sends them.
    """
    return anthropic.Anthropic(api_key=api_key(), timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)


def answer_text(message) -> str:
    """The answer's text, read by block type.

    Claude 5.5 models think by default, so a response can begin with `thinking` blocks; taking
    `content[0].text` would read the wrong block or fail.
    """
    return ''.join(block.text for block in message.content if block.type == 'text')


def cost_usd(model: str, input_tokens: int, output_tokens: int, batch: bool = False,
             cache_write_tokens: int = 0, cache_read_tokens: int = 0) -> float:
    """What a call costs at list price, from its token counts.

    Args:
        model: One of PRICES_USD_PER_MILLION's model ids.
        input_tokens: `usage.input_tokens` of the response (images included, cached tokens not).
        output_tokens: `usage.output_tokens` (thinking tokens included).
        batch: Whether the call ran through the Message Batches API (the discount stacks with caching).
        cache_write_tokens: `usage.cache_creation_input_tokens`.
        cache_read_tokens: `usage.cache_read_input_tokens`.

    Raises:
        KeyError: For a model without a recorded price, rather than a silent zero.
    """
    input_price, output_price = PRICES_USD_PER_MILLION[model]
    read_factor = CACHE_READ_FACTOR.get(model, DEFAULT_CACHE_READ_FACTOR)
    full = (input_tokens * input_price + cache_write_tokens * input_price * CACHE_WRITE_FACTOR
            + cache_read_tokens * input_price * read_factor + output_tokens * output_price) / 1e6
    return full * BATCH_DISCOUNT if batch else full


def chat_model(model: str, reasoning_effort: str | None = None, max_tokens: int = 2000) -> ChatAnthropic:
    """One of the chat's models on Anthropic's API (decision 287.b), built like `openrouter_client.chat_model`.

    The chat's models ran on OpenRouter until the course's key ended (about 23 Nov 2026); from then until the API credit
    expires (10 Dec 2026) they run here. `ChatAnthropic` (langchain-anthropic) has the interface the agent, the router
    and the generator use: tools, `with_structured_output`, `usage_metadata`.

    - Thinking is switched off: the chat's models pick a tool, plan a search and write a cited answer, as gpt-4.1-mini
      and gpt-5-mini at effort low did, and `with_structured_output` forces a tool call, which thinking does not allow.
      Haiku 5.5 takes `thinking: disabled` at effort high or below; Opus 5.5 does not take it at all, so it is no chat
      model here.
    - `reasoning_effort` becomes `output_config.effort` ('low', 'medium', 'high').
    - No temperature: this API version rejects it with a 400.
    - An explicit timeout and no hidden retries, as every client here.

    Args:
        model: An Anthropic model id, e.g. 'claude-haiku-5-5'.
        reasoning_effort: The effort, or None for the model's default.
        max_tokens: The output budget.
    """
    options = {'output_config': {'effort': reasoning_effort}} if reasoning_effort else {}
    return ChatAnthropic(model=model, api_key=api_key(), max_tokens=max_tokens, timeout=CHAT_TIMEOUT_SECONDS,
                         max_retries=MAX_RETRIES, thinking={'type': 'disabled'}, **options)
