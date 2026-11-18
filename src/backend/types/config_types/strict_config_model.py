"""The base of a configuration model whose file must not swallow a typo: an unknown key is a hard error.

A key that starts with an underscore (`_about`, `_comment`) is how a config file explains itself; it is dropped before
the strict check sees it, so the explanation never counts as a setting.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class StrictConfigModel(BaseModel):
    """A configuration section: every key declared, every unknown one refused."""

    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='before')
    @classmethod
    def _drop_meta_keys(cls, data: Any) -> Any:
        """Remove the explanatory keys before the strict check."""
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if not str(key).startswith('_')}
        return data
