"""The route the vectors take (278.a): a setting, while the model stays fixed with the index."""

from pathlib import Path

import pytest

from backend.configuration.config_file_loader import ConfigFileLoader
from backend.ingestion import index_store
from backend.providers import embedding_route, openai_client, openrouter_client
from backend.types.config_types.app_config_types import EmbeddingProvider, EmbeddingsConfig


def use_route(monkeypatch, route: str) -> None:
    config = {**ConfigFileLoader.get_config(), 'embeddings': {'provider': route}}
    monkeypatch.setattr(ConfigFileLoader, '_config', config)


def test_the_tracked_route_is_openrouter_until_the_course_key_ends():
    assert embedding_route.provider() is EmbeddingProvider.OPENROUTER


def test_each_route_hands_out_its_own_client_for_the_same_model(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
    monkeypatch.setenv(openai_client.KEY_NAME, 'sk-test')
    use_route(monkeypatch, 'openrouter')
    assert embedding_route.embeddings().openai_api_base == openrouter_client.OPENROUTER_BASE_URL
    use_route(monkeypatch, 'openai')
    direct = embedding_route.embeddings()
    assert direct.openai_api_base is None  # OpenAI's own endpoint
    assert embedding_route.index_name(direct.model) == embedding_route.INDEX_MODEL


def test_an_unknown_route_stops_the_program_at_its_start(monkeypatch):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        EmbeddingsConfig(provider='voyage')


def test_the_bare_name_and_the_maker_s_name_are_the_same_model_and_no_other_is():
    assert embedding_route.index_name('text-embedding-3-small') == 'openai/text-embedding-3-small'
    assert embedding_route.index_name('openai/text-embedding-3-small') == 'openai/text-embedding-3-small'
    assert embedding_route.index_name('text-embedding-3-large') != embedding_route.INDEX_MODEL


class Named:
    """An embeddings object that only says its model's name."""

    def __init__(self, model: str):
        self.model = model


def test_the_index_opens_with_openai_s_bare_name_and_refuses_another_model():
    directory = Path('corpus/index/chroma')
    index_store.check_embedding_model(embedding_route.INDEX_MODEL, embedding_route.INDEX_MODEL,
                                      Named(openai_client.EMBEDDING_MODEL), directory)
    with pytest.raises(index_store.EmbeddingModelMismatch):
        index_store.check_embedding_model(embedding_route.INDEX_MODEL, embedding_route.INDEX_MODEL,
                                          Named('text-embedding-3-large'), directory)
