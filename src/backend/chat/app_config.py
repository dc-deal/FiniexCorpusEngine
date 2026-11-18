"""The app's runtime settings, from `configs/app_config.json`.

One file for what can change without rebuilding the index: which chat model routes a question,
how many search queries a broad question gets, how many chunks come back. What would need
re-embedding (the embedding model, the chunk size) stays a constant next to the code that uses it.
"""

import functools
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / 'configs' / 'app_config.json'


@functools.cache
def load() -> dict:
    """The settings, read once per process."""
    return json.loads(CONFIG.read_text(encoding='utf-8'))
