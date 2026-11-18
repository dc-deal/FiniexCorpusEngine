from types import SimpleNamespace

import pytest

from backend.providers import anthropic_client


def test_a_missing_key_says_how_to_fix_it(monkeypatch, tmp_path):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    monkeypatch.setattr(anthropic_client, 'ROOT', tmp_path)  # no .env there
    with pytest.raises(anthropic_client.MissingApiKeyError, match='.env.example'):
        anthropic_client.api_key()


def test_the_client_has_an_explicit_timeout_and_no_hidden_retries(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-test')
    client = anthropic_client.client()
    assert client.max_retries == 0
    assert client.timeout == anthropic_client.TIMEOUT_SECONDS


def test_the_answer_is_read_by_block_type_not_by_position():
    # Claude 5.5 models think by default: the first block can be a thinking block.
    message = SimpleNamespace(content=[SimpleNamespace(type='thinking', thinking=''),
                                       SimpleNamespace(type='text', text='o'),
                                       SimpleNamespace(type='text', text='k')])
    assert anthropic_client.answer_text(message) == 'ok'


def test_a_batch_costs_half_and_an_unpriced_model_is_an_error_not_zero():
    assert anthropic_client.cost_usd('claude-sonnet-5-5', 1_000_000, 100_000) == pytest.approx(3.0)
    assert anthropic_client.cost_usd('claude-sonnet-5-5', 1_000_000, 100_000, batch=True) == pytest.approx(1.5)
    with pytest.raises(KeyError):
        anthropic_client.cost_usd('claude-unknown', 1, 1)


def test_cache_writes_cost_more_and_reads_less_with_opus_reading_cheapest():
    # One million tokens each way, at Sonnet's 2 USD input price: write 1.25 x, read 0.1 x.
    assert anthropic_client.cost_usd('claude-sonnet-5-5', 0, 0, cache_write_tokens=1_000_000) == pytest.approx(2.5)
    assert anthropic_client.cost_usd('claude-sonnet-5-5', 0, 0, cache_read_tokens=1_000_000) == pytest.approx(0.2)
    assert anthropic_client.cost_usd('claude-opus-5-5', 0, 0, cache_read_tokens=1_000_000) == pytest.approx(0.2)  # 0.05 x 4


def test_every_reader_model_has_a_price():
    assert set(anthropic_client.READER_MODELS) <= set(anthropic_client.PRICES_USD_PER_MILLION)
