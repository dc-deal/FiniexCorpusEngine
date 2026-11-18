"""Reads `configs/app_config.json` once per process: a run works on the configuration it started with.

A git-ignored `configs/app_config.local.json`, where one exists, is laid over it key by key (decision 285.a): this machine's
own settings, such as data folders elsewhere on disk or the main tree's folders for a second work tree, without touching
the tracked file. The strict model checks the merged result, so a typo in the local file stops the program like one in the
tracked file.
"""

import json
from pathlib import Path
from threading import Lock
from typing import Any


def deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """`over` laid on `base`: a section merges key by key, any other value replaces the one below it."""
    merged = dict(base)
    for key, value in over.items():
        merged[key] = deep_merge(merged[key], value) if isinstance(value, dict) and isinstance(merged.get(key), dict) else value
    return merged


class ConfigFileLoader:
    """The raw content of the app's main configuration, with this machine's local file laid over it, loaded on first use."""

    ROOT = Path(__file__).resolve().parents[3]
    CONFIG_FILE = ROOT / 'configs' / 'app_config.json'
    LOCAL_FILE = ROOT / 'configs' / 'app_config.local.json'
    _config: dict[str, Any] | None = None
    _lock = Lock()

    @staticmethod
    def get_config() -> dict[str, Any]:
        """The configuration as JSON; read on the first call only."""
        with ConfigFileLoader._lock:
            if ConfigFileLoader._config is None:
                config = json.loads(ConfigFileLoader.CONFIG_FILE.read_text(encoding='utf-8'))
                if ConfigFileLoader.LOCAL_FILE.exists():
                    config = deep_merge(config, json.loads(ConfigFileLoader.LOCAL_FILE.read_text(encoding='utf-8')))
                ConfigFileLoader._config = config
            return ConfigFileLoader._config
