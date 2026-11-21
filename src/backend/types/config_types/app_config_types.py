"""The typed shape of `configs/app_config.json`.

`paths` and `embeddings` are typed field by field; the chat's sections are taken as they stand until they get models of their own (an
issue, decision 260.a). Every default here is mirrored with the same value in the file, so a setting is visible and can
be tuned without reading code; a test holds the two in step.
"""

from enum import Enum
from typing import Any

from backend.types.config_types.strict_config_model import StrictConfigModel


class EmbeddingProvider(str, Enum):
    """The route the vectors take; both serve the same model with the same vectors (decision 278.a)."""

    OPENROUTER = 'openrouter'  # the course's key, until about 23 Nov 2026
    OPENAI = 'openai'  # OpenAI direct, the project key CORPUS_OPENAI_API_KEY


class ChatProvider(str, Enum):
    """Who serves one of the chat's models (agent, router, generator; decision 287.b)."""

    OPENROUTER = 'openrouter'  # the course's key, until about 23 Nov 2026
    ANTHROPIC = 'anthropic'  # Anthropic's API, from the credit that expires on 10 Dec 2026


class EmbeddingsConfig(StrictConfigModel):
    """Where the embeddings are fetched; the model itself is fixed with the index, not here."""

    provider: EmbeddingProvider = EmbeddingProvider.OPENROUTER


class PathsConfig(StrictConfigModel):
    """Where the data and the local state live: relative to the repository, or absolute."""

    data: str = '_data'  # the local data folder, never in any repository: free sources, readings, measurements
    originals: str = '_sources'  # the original books no repository holds: the licensed archive, free candidates
    working: str = '_work'  # what the pipeline makes and keeps on this machine: stores, databases, renders
    index: str = 'corpus/index'  # the search index (Chroma and SQLite), rebuilt by backend.ingestion.build
    logs: str = 'logs'  # the chat's turn log, the search server's call log, audit samples


class CorrectionConfig(StrictConfigModel):
    """The model that proposes how one block should read, from the page image and a judge's finding (the operator's W2.a, 21
    Nov); a person records the proposal or not. Its instructions are the active version of the role `correction` in
    `prompt_versions.json`."""

    provider: ChatProvider = ChatProvider.ANTHROPIC  # the request carries the page image; only Anthropic's route is built
    model: str = 'claude-sonnet-5-5'  # the reader's and the judge's model, so it reads the image as they did
    max_tokens: int = 4000  # a whole table written again, its thinking included


class AppConfig(StrictConfigModel):
    """The whole file; an unknown section is refused like an unknown key."""

    paths: PathsConfig = PathsConfig()
    embeddings: EmbeddingsConfig = EmbeddingsConfig()
    correction: CorrectionConfig = CorrectionConfig()
    router: dict[str, Any]
    agent: dict[str, Any]
    generator: dict[str, Any]
    answer: dict[str, Any]
    multi_query: dict[str, Any]
    retrieval: dict[str, Any]
    ui: dict[str, Any]
