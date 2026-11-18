import pytest

from backend.providers import openai_client, openrouter_client


def test_a_missing_key_says_how_to_fix_it(monkeypatch, tmp_path):
    monkeypatch.delenv(openai_client.KEY_NAME, raising=False)
    monkeypatch.setattr(openai_client, 'ROOT', tmp_path)  # no .env there
    with pytest.raises(openai_client.MissingApiKeyError, match='.env.example'):
        openai_client.api_key()


def test_embeddings_go_to_openai_itself_sent_as_text(monkeypatch):
    monkeypatch.setenv(openai_client.KEY_NAME, 'sk-test')
    monkeypatch.delenv('OPENAI_API_BASE', raising=False)
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)
    client = openai_client.embeddings()
    assert client.model == openai_client.EMBEDDING_MODEL
    assert client.openai_api_base is None  # OpenAI's own endpoint, not OpenRouter
    assert client.check_embedding_ctx_length is False  # as on the OpenRouter route
    assert client.max_retries == 0


def test_it_is_the_model_openrouter_serves_under_another_name():
    assert openrouter_client.EMBEDDING_MODEL == f'openai/{openai_client.EMBEDDING_MODEL}'
    assert openrouter_client.EMBEDDING_DIMENSIONS == openai_client.EMBEDDING_DIMENSIONS


def test_the_client_has_an_explicit_timeout_and_no_hidden_retries(monkeypatch):
    monkeypatch.setenv(openai_client.KEY_NAME, 'sk-test')
    client = openai_client.client()
    assert client.max_retries == 0
    assert client.timeout == openai_client.TIMEOUT_SECONDS
