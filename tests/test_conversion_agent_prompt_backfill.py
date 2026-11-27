"""Older session records tied to the agent prompt that made them (#17, 22.a): by the folders the agent itself wrote, else by
its batch file or folder list and the time; a record no saved agent wrote points at the registry's entry without text."""

import json

from backend.conversion.reading import agent_prompt_backfill as backfill
from backend.conversion.store import reading_export, reading_store


def call(kind, at, written=None, prompt='p', mirror='free'):
    return {'kind': kind, 'source': 'subagent', 'timestamp': at, 'written': written, 'prompt': prompt, 'mirror': mirror,
            'transcript': f'session/{kind}-{at}.jsonl'}


def test_an_agent_s_own_folders_name_its_pages_exactly():
    one = call('reader', '2026-11-19T10:00:00Z', ['w__p0012', 'LAB-X__w__p0013', 'w__p0014__a1'])
    assert backfill.pages_of(one) == {('w', 12, 0), ('w', 13, 0), ('w', 14, 1)}


def test_each_session_record_is_tied_to_the_agent_that_wrote_it_and_an_unknown_one_says_so(tmp_path, monkeypatch):
    store, licensed = reading_store.Store(tmp_path / 'vision'), reading_store.Store(tmp_path / 'licensed_vision')
    monkeypatch.setattr(backfill, 'open_store', lambda mirror: store if mirror == 'free' else licensed)
    reading = {'kind': 'reading', 'mode': 'session', 'reading_key': 'r' * 64, 'work': 'w', 'pdf_page': 12, 'attempt': 0,
               'stored_at': '2026-11-19T11:00:00+00:00'}
    orphan = {**reading, 'reading_key': 'o' * 64, 'pdf_page': 99}
    verdict = {'kind': 'judge', 'mode': 'session', 'reading_key': 'j' * 64, 'work': 'w', 'pdf_page': 12,
               'stored_at': '2026-11-19T12:30:00+00:00'}
    for record in (reading, orphan, verdict):
        store.save_reading(record['reading_key'], record, 'x')
    calls = [call('reader', '2026-11-19T09:00:00Z', ['w__p0012'], prompt='older reader'),
             call('reader', '2026-11-19T10:00:00Z', ['w__p0012'], prompt='the reader that wrote it'),
             call('reader', '2026-11-19T11:30:00Z', ['w__p0012'], prompt='a later one'),
             call('judge', '2026-11-19T12:00:00Z', ['w__p0012'], prompt='the judge')]
    counts = backfill.backfill(calls)['free']
    assert counts == {'reader: tied': 1, 'reader: lost': 1, 'judge: tied': 1}
    tied = json.loads(store.path('reports', backfill.REPORT).read_text(encoding='utf-8'))['records']
    assert store.get_prompt(tied['r' * 64]['sha256']) == 'the reader that wrote it'  # the last before it was stored
    assert tied['r' * 64]['version'] == 'reader-agent/0' and tied['r' * 64]['derived'] == 'its agent wrote this page'
    assert tied['o' * 64] == {'version': 'reader-agent/unknown', 'sha256': None, 'derived': 'no saved call holds its page'}
    assert store.get_prompt(tied['j' * 64]['sha256']) == 'the judge'
    assert reading_export.agent_prompt_of(reading, tied)['version'] == 'reader-agent/0'
    own = {**reading, 'agent_prompt': {'version': 'reader-agent/1', 'sha256': 's' * 64}}
    assert reading_export.agent_prompt_of(own, tied) == {'version': 'reader-agent/1', 'sha256': 's' * 64}  # its own stands
