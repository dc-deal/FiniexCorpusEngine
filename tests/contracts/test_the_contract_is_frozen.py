"""The reader's contract is frozen: what the batches read with is what the mini pilot measured.

A changed prompt or vocabulary would make the readings of one corpus disagree with each other, and the measurements would no longer
describe them. A change here is a decision, not an edit: it means a new contract version and a word in the phase's protocol. When it
is one, update the hash in frozen_contract.json in the same commit.
"""

import hashlib
import json
from pathlib import Path

from backend.conversion.contract import page_contract
from backend.conversion.reading import reader_requests
from backend.conversion.store.reading_store import open_store

CONVERSION = Path(page_contract.__file__).resolve().parents[1]  # the contract lies in conversion/contract/ since 208.b
FROZEN = json.loads((CONVERSION / 'frozen_contract.json').read_text(encoding='utf-8'))


def test_every_frozen_file_is_unchanged():
    changed = [name for name, digest in FROZEN['sha256'].items()
               if hashlib.sha256((CONVERSION / name).read_bytes()).hexdigest() != digest]
    assert changed == [], f'changed after the freeze: {changed}. See the docstring of this test.'


def test_the_frozen_contract_is_the_one_the_code_speaks():
    assert FROZEN['contract'] == page_contract.CONTRACT and FROZEN['form'] in page_contract.FORMS


def test_the_frozen_prompt_is_the_one_measured_last():
    # Only on the machine that holds the readings.
    measured = {record.get('system_sha256') for record in open_store('free').readings() if record.get('cell') == 'MP2-SM'}
    if measured:
        assert reader_requests.sha256_text(reader_requests.system_prompt(FROZEN['form'])) in measured
