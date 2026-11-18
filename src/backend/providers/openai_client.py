"""The one place that knows how to reach OpenAI directly, with the project's own key.

OpenRouter (`openrouter_client.py`) was the course's route and ends with its key (about 23 Nov 2026). The same OpenAI
embedding model is reachable here without it, so the index is queried and rebuilt afterwards (decision 278.a;
`embedding_route.py` picks the route). The key is the OpenAI project `corpus-engine`'s, `CORPUS_OPENAI_API_KEY`, which
is allowed text-embedding-3-small and nothing else; it is read from the environment or `.env` (git-ignored) and never
appears in code, in a log, or in anything the interface could show.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[3]

# The model OpenRouter serves as 'openai/text-embedding-3-small', under OpenAI's own name.
# 0.02 USD per million input tokens on both routes (OpenRouter's list, read 2026-10-29).
EMBEDDING_MODEL = 'text-embedding-3-small'
EMBEDDING_DIMENSIONS = 1536

# No hidden retries and no ten-minute wait, for the same reason as in anthropic_client.py.
TIMEOUT_SECONDS = 60
MAX_RETRIES = 0
KEY_NAME = 'CORPUS_OPENAI_API_KEY'


class MissingApiKeyError(RuntimeError):
    """Raised when no OpenAI key is configured, with the fix in the message."""


def api_key() -> str:
    """Read the project's OpenAI key from the environment or `.env`.

    Returns:
        The key.

    Raises:
        MissingApiKeyError: When no key is configured.
    """
    load_dotenv(ROOT / '.env')
    key = os.environ.get(KEY_NAME, '').strip()
    if not key:
        raise MissingApiKeyError(
            f'{KEY_NAME} is not set. Create a project key at platform.openai.com, allowed '
            f'{EMBEDDING_MODEL} only, and put it in .env (see .env.example).')
    return key


def client() -> OpenAI:
    """The SDK client, with an explicit timeout and no automatic retries."""
    return OpenAI(api_key=api_key(), timeout=TIMEOUT_SECONDS, max_retries=MAX_RETRIES)


def embeddings() -> OpenAIEmbeddings:
    """The embedding client, built like `openrouter_client.embeddings()` but without OpenRouter.

    The text is sent as text (`check_embedding_ctx_length=False`), exactly as on the OpenRouter
    route, so the two routes differ only in where the request goes.
    """
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        api_key=api_key(),
        check_embedding_ctx_length=False,
        timeout=TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
    )
