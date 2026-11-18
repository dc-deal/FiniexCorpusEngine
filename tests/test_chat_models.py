"""Who serves the chat's models (287.b): a setting per model, OpenRouter or Anthropic, with a price for each."""

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from backend.chat import app_config
from backend.providers import anthropic_client, chat_models, openrouter_client
from backend.types.config_types.app_config_types import ChatProvider

HAIKU = {'provider': 'anthropic', 'model': 'claude-haiku-5-5', 'reasoning_effort': None, 'max_tokens': 1500}


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-test')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-test')


def test_every_chat_model_in_the_file_names_its_provider():
    config = app_config.load()
    for part in ('agent', 'router', 'generator'):
        assert chat_models.provider(config[part]) in set(ChatProvider), part


def test_an_unknown_provider_is_refused():
    with pytest.raises(ValueError):
        chat_models.provider({**HAIKU, 'provider': 'mistral'})


def test_an_anthropic_section_builds_chat_anthropic_without_thinking_temperature_or_retries(keys):
    llm = chat_models.chat_model(HAIKU)
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == 'claude-haiku-5-5' and llm.max_tokens == 1500
    assert llm.thinking == {'type': 'disabled'}  # with_structured_output forces a tool call, which thinking forbids
    assert llm.temperature is None  # this API version answers a temperature with a 400
    assert llm.max_retries == 0 and llm.default_request_timeout == anthropic_client.CHAT_TIMEOUT_SECONDS
    assert llm.output_config is None
    assert chat_models.chat_model({**HAIKU, 'reasoning_effort': 'low'}).output_config == {'effort': 'low'}


def test_an_openrouter_section_builds_the_course_s_chat_openai(keys):
    llm = chat_models.chat_model(app_config.load()['generator'] | {'provider': 'openrouter'})
    assert isinstance(llm, ChatOpenAI)
    assert llm.openai_api_base == openrouter_client.OPENROUTER_BASE_URL


def test_anthropic_prices_come_from_the_table_and_need_no_network(monkeypatch):
    def refuse(_):
        raise AssertionError('OpenRouter asked although no section is on it')
    monkeypatch.setattr(openrouter_client, 'model_prices', refuse)
    assert chat_models.model_prices([HAIKU]) == {'claude-haiku-5-5': {'input': 0.10, 'output': 0.50}}


def test_a_mixed_set_asks_openrouter_for_its_own_models_only(monkeypatch):
    asked = []
    monkeypatch.setattr(openrouter_client, 'model_prices',
                        lambda ids: asked.extend(ids) or {i: {'input': 1.0, 'output': 2.0} for i in ids})
    routed = {'provider': 'openrouter', 'model': 'openai/gpt-5-mini', 'reasoning_effort': 'low', 'max_tokens': 10}
    prices = chat_models.model_prices([routed, HAIKU])
    assert asked == ['openai/gpt-5-mini']
    assert set(prices) == {'openai/gpt-5-mini', 'claude-haiku-5-5'}


def test_anthropic_models_answer_through_structured_outputs_and_openrouter_s_keep_their_default(keys, monkeypatch):
    # Haiku 5.5 left required fields out of a forced tool call (2 of 61 answers, 17 Nov); structured outputs hold the schema
    asked = []
    monkeypatch.setattr(ChatAnthropic, 'with_structured_output', lambda self, schema, **options: asked.append(options))
    monkeypatch.setattr(ChatOpenAI, 'with_structured_output', lambda self, schema, **options: asked.append(options))
    chat_models.structured(chat_models.chat_model(HAIKU), dict)
    chat_models.structured(chat_models.chat_model(app_config.load()['generator'] | {'provider': 'openrouter'}), dict)
    assert asked == [{'include_raw': True, 'method': 'json_schema'}, {'include_raw': True}]
