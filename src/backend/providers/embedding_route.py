"""Which route the vectors take: OpenRouter or OpenAI direct (decision 278.a).

Both routes serve the same model, OpenAI's text-embedding-3-small, and return the same vectors (cosine 1.0 and
0.999999 on two sentences, measured 2026-10-29 by `provider_check`), so one index serves both and nothing is
re-embedded when the route changes. The route is a setting (`embeddings.provider` in `configs/app_config.json`); the
model is not: it is fixed with the index, which records it under `INDEX_MODEL` and refuses to open with another
(`index_store.check_embedding_model`). Every caller that embeds, the build, the search and the evaluations, takes its
client from here.
"""

from langchain_openai import OpenAIEmbeddings

from backend.configuration.app_config_manager import AppConfigManager
from backend.providers import openai_client, openrouter_client
from backend.types.config_types.app_config_types import EmbeddingProvider

# The name the index has recorded since it was first built: OpenRouter's, which carries the maker.
INDEX_MODEL = openrouter_client.EMBEDDING_MODEL
# The same price on both routes (OpenRouter's list, read 2026-09-28; OpenAI's, read 2026-10-29).
USD_PER_MILLION_TOKENS = openrouter_client.EMBEDDING_USD_PER_MILLION_TOKENS
MAKER = 'openai/'


def provider() -> EmbeddingProvider:
    """The configured route."""
    return AppConfigManager().get_embeddings().provider


def embeddings() -> OpenAIEmbeddings:
    """The embedding client of the configured route."""
    if provider() is EmbeddingProvider.OPENAI:
        return openai_client.embeddings()
    return openrouter_client.embeddings()


def index_name(model: str) -> str:
    """The name the index records for a model as a route reports it.

    OpenRouter names a model with its maker ('openai/text-embedding-3-small'); OpenAI direct serves only its own models
    and names them bare ('text-embedding-3-small'). Both are the same model, so the bare name gets the maker.
    """
    return model if '/' in model else f'{MAKER}{model}'
