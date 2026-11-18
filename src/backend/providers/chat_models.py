"""Who serves each of the chat's models: OpenRouter or Anthropic (decision 287.b).

The chat has three models, each a section of `configs/app_config.json` with its `provider`, `model`, `reasoning_effort`
and `max_tokens`: `agent` picks a tool, `router` plans the search, `generator` writes the cited answer. OpenRouter served
all three on the course's key, which ends about 23 Nov 2026; Anthropic serves them from the API credit until it expires
on 10 Dec 2026. After that the chat has no model, and the search and the views go on without it. Every caller builds
its models and reads their prices here.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from backend.providers import anthropic_client, openrouter_client
from backend.types.config_types.app_config_types import ChatProvider


def provider(section: dict) -> ChatProvider:
    """The section's provider; an unknown one stops the call with a ValueError."""
    return ChatProvider(section['provider'])


def chat_model(section: dict) -> BaseChatModel:
    """The model a section names, from its provider."""
    build = anthropic_client.chat_model if provider(section) is ChatProvider.ANTHROPIC else openrouter_client.chat_model
    return build(section['model'], section['reasoning_effort'], section['max_tokens'])


def structured(llm, schema) -> Runnable:
    """`llm.with_structured_output(schema, include_raw=True)` by the provider's surer method.

    On Anthropic its structured outputs (`json_schema`), which hold the reply to the schema: LangChain's default there is a
    forced tool call, and in it Haiku 5.5 left required fields out (`quotes`, `gaps`: 2 of 61 answers ended in an error,
    measured 17 Nov). OpenRouter's models keep the default they were measured with.
    """
    if isinstance(llm, ChatAnthropic):
        return llm.with_structured_output(schema, include_raw=True, method='json_schema')
    return llm.with_structured_output(schema, include_raw=True)


def model_prices(sections: list[dict]) -> dict[str, dict[str, float]]:
    """Prices in USD per million tokens, {model: {'input', 'output'}}, for the models the sections name.

    OpenRouter's are read at run time (no key needed, the network is); Anthropic's come from `anthropic_client`'s table.
    A model with no known price is left out, and a turn on it shows no cost rather than a wrong one.
    """
    routed = [section['model'] for section in sections if provider(section) is ChatProvider.OPENROUTER]
    prices = openrouter_client.model_prices(routed) if routed else {}
    for section in sections:
        listed = anthropic_client.PRICES_USD_PER_MILLION.get(section['model'])
        if provider(section) is ChatProvider.ANTHROPIC and listed:
            prices[section['model']] = {'input': listed[0], 'output': listed[1]}
    return prices
