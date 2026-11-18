import math

import pytest

from backend.providers import openrouter_client


def test_a_missing_key_says_how_to_fix_it(monkeypatch, tmp_path):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    monkeypatch.setattr(openrouter_client, 'ROOT', tmp_path)  # no .env there
    with pytest.raises(openrouter_client.MissingApiKeyError, match='.env.example'):
        openrouter_client.api_key()


def fake_key(monkeypatch, readings):
    values = iter(readings)
    monkeypatch.setattr(openrouter_client, 'key_usage', lambda: next(values))
    monkeypatch.setattr(openrouter_client.time, 'sleep', lambda seconds: None)


def test_the_cost_is_read_once_booking_has_settled_not_at_the_first_part(monkeypatch):
    # As measured: nothing yet, then a first part, then the rest, then stable.
    fake_key(monkeypatch, [1.0, 1.023198, 1.025302, 1.025302])
    assert abs(openrouter_client.measured_cost(1.0) - 0.025302) < 1e-9


def test_a_part_that_stands_still_is_not_taken_for_the_whole_when_an_estimate_is_known(monkeypatch):
    # As measured 2026-09-30: 0.004864 for two readings, then the rest up to the estimate 0.007667.
    fake_key(monkeypatch, [1.0, 1.004864, 1.004864, 1.007667, 1.007667])
    assert abs(openrouter_client.measured_cost(1.0, estimate=0.007667) - 0.007667) < 1e-9


def test_a_cost_not_booked_in_time_is_unknown_not_zero(monkeypatch):
    fake_key(monkeypatch, [1.0] * 1000)
    monkeypatch.setattr(openrouter_client, 'BOOKING_TIMEOUT_SECONDS', -1)  # deadline already passed
    assert openrouter_client.measured_cost(1.0) is None


def test_a_reasoning_model_gets_its_effort_in_extra_body_and_no_temperature(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
    reasoning = openrouter_client.chat_model('openai/gpt-5-mini', reasoning_effort='low')
    assert reasoning.extra_body == {'reasoning': {'effort': 'low'}}
    assert reasoning.temperature is None
    plain = openrouter_client.chat_model('openai/gpt-4.1-mini')
    assert plain.temperature == 0 and not plain.extra_body
    assert plain.openai_api_base == openrouter_client.OPENROUTER_BASE_URL
    assert plain.max_tokens == 2000


def test_embeddings_are_sent_as_text_not_as_openai_token_ids(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
    client = openrouter_client.embeddings()
    assert client.check_embedding_ctx_length is False
    assert client.model == openrouter_client.EMBEDDING_MODEL
    assert client.openai_api_base == openrouter_client.OPENROUTER_BASE_URL


@pytest.mark.live
def test_openrouter_returns_a_vector_of_the_documented_size():
    # Spends a fraction of a cent. Run with: pytest -m live
    client = openrouter_client.embeddings()
    close, far = client.embed_documents(['The Sharpe ratio measures excess return per unit of risk.',
                                         'Drawdown is the decline from a peak.'])
    query = client.embed_query('what is a sharpe ratio')
    cosine = lambda a, b: sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    assert len(query) == openrouter_client.EMBEDDING_DIMENSIONS
    assert cosine(query, close) > cosine(query, far)


def test_a_chat_model_has_a_timeout_and_no_hidden_retries(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
    model = openrouter_client.chat_model('openai/gpt-5-mini', 'low')
    assert model.root_client.max_retries == 0 and model.root_client.timeout == openrouter_client.CHAT_TIMEOUT_SECONDS == 120
