"""The registry of models and parameters (issue: models and parameters, the operator's 53.a, 28 Nov 2026): where a reader ran,
which model with which weights, and every parameter it ran with, in `conversion/models_and_parameters.json`.

A reading names its parameter set beside its prompt version: `{"version": "paddleocr-vl-pipeline/1", "sha256": …}`, the hash
taken over the set as registered, so a set edited after a reading named it is seen. `require` refuses a version the registry
does not hold before anything is stored ("was hier nicht hinterlegt ist, kommt nicht in die Datenbank"). A reading stored
before the registry gets its set through the cells a set names (`used_by_cells`), marked as derived, never guessed beyond.
"""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / 'models_and_parameters.json'
STATES = ('prototype', 'active', 'retired')


@lru_cache(maxsize=1)
def registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding='utf-8'))


def sets() -> dict[str, dict]:
    return {entry['version']: entry for entry in registry()['parameter_sets']}


def sha256_of(entry: dict) -> str:
    """The set's hash: its registered entry as canonical JSON."""
    return hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def require(version: str) -> dict:
    """The set a reading is about to be stored under, as its record names it.

    Raises:
        ValueError: For a version the registry does not hold, or whose model or host it does not hold.
    """
    entry = sets().get(version)
    if entry is None:
        raise ValueError(f'parameter set {version!r} is not registered in {REGISTRY.name}: nothing is stored under it')
    models = {model['id'] for model in registry()['models']}
    hosts = {host['id'] for host in registry()['hosts']}
    if entry['model'] not in models or entry['host'] not in hosts:
        raise ValueError(f'parameter set {version!r} names a model or host the registry does not hold')
    return {'version': version, 'sha256': sha256_of(entry)}


def of_record(record: dict) -> dict | None:
    """The set a reading was made with: the one its record names, else the one registered for its cell, marked derived;
    None where neither says."""
    named = record.get('parameter_set')
    if named:
        return named
    for entry in registry()['parameter_sets']:
        if record.get('cell') in entry.get('used_by_cells', []):
            return {'version': entry['version'], 'sha256': sha256_of(entry), 'derived': 'by its cell'}
    return None
