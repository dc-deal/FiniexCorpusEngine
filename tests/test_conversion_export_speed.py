"""Issue #5: the licensed export keeps what did not change. Measured 21 Nov: 196 s natively and about 32 min in the view's
container; with these 15 s warm, and the same index byte for byte."""

import hashlib

import pytest

from backend.conversion.reading import vision_batches
from backend.conversion.store import reading_export, reading_store
from test_conversion_served_readings import page

TEXT = page('::: {#b01 .paragraph bbox="10 50 900 120"}\nA sentence.\n:::')
KEY = 'c' * 64


def a_reading(**fields) -> dict:
    return {'kind': 'reading', 'reading_key': KEY, 'work': 'w', 'file': 'w_book.pdf', 'pdf_page': 2, 'model': 'claude-sonnet-5-5',
            'form': 'markdown', 'attempt': 0, 'cost_usd': 0.01, 'image_size': [1688, 2184], 'result_type': 'succeeded',
            'result_class': 'ok', 'stop_reason': 'end_turn', 'text_sha256': hashlib.sha256(TEXT.encode('utf-8')).hexdigest(), **fields}


@pytest.fixture
def one_page(tmp_path, monkeypatch):
    store = reading_store.Store(tmp_path / 'vision')
    record = a_reading()
    store.save_reading(KEY, record, TEXT)
    monkeypatch.setattr(vision_batches, 'readings_of', lambda cells, store: [record])
    base = reading_export.KnowledgeBase('licensed', tmp_path / 'readings', tmp_path / 'pdfs', lambda: ('LIC-R01',), tracked=False)
    monkeypatch.setattr(reading_export, 'legacy_fallback_pages', lambda: {})
    return base, store, record


def test_a_plain_path_is_joined_as_it_stands_and_any_other_is_still_resolved_and_refused(tmp_path):
    store = reading_store.Store(tmp_path / 'vision')
    assert store.path('readings', 'ab', 'abc.json') == store.root / 'readings' / 'ab' / 'abc.json'
    for parts in (('..', 'outside'), ('a/../../outside',), ('readings', '..', '..', 'x')):
        with pytest.raises(reading_store.UnsafeRootError):
            store.path(*parts)


def test_a_snapshot_reads_every_record_once(tmp_path, monkeypatch):
    store = reading_store.Store(tmp_path / 'vision')
    store.save_reading(KEY, a_reading(), TEXT)
    calls = []
    real = store.readings
    monkeypatch.setattr(store, 'readings', lambda: calls.append(1) or real())
    snapshot = reading_store.Snapshot(store)
    assert snapshot.readings() == snapshot.readings() and snapshot.reading(KEY)['reading_key'] == KEY
    assert len(calls) == 1 and snapshot.reading_text(KEY) == TEXT


def test_the_validator_runs_once_per_reading_across_runs_and_again_for_another_validator(tmp_path, monkeypatch):
    store = reading_store.Store(tmp_path / 'vision')
    record = a_reading()
    store.save_reading(KEY, record, TEXT)
    asked = []
    real = vision_batches.check_reading
    monkeypatch.setattr(vision_batches, 'check_reading', lambda *args: asked.append(1) or real(*args))
    first = reading_store.Snapshot(store)
    assert vision_batches.current_class(record, first) == 'ok' and vision_batches.stage_one_errors(record, first) == []
    first.class_cache.save()
    second = reading_store.Snapshot(store)
    assert vision_batches.current_class(record, second) == 'ok' and vision_batches.stage_one_errors(record, second) == []
    assert len(asked) == 1  # one check gave both the class and the errors, then nothing ran again
    monkeypatch.setattr(reading_store, 'validator_code_hash', lambda: 'another validator')
    assert vision_batches.current_class(record, reading_store.Snapshot(store)) == 'ok' and len(asked) == 2


def test_an_unchanged_page_is_neither_read_nor_written_again_and_the_index_stays_the_same(one_page, monkeypatch):
    base, store, record = one_page
    reading_export.export(base, store)
    first_index = (base.export / 'index.json').read_bytes()
    text_file = base.export / 'w' / 'p0002.md'
    written_at = text_file.stat().st_mtime_ns
    read = []
    real = reading_store.Store.reading_text
    monkeypatch.setattr(reading_store.Store, 'reading_text', lambda self, key: read.append(key) or real(self, key))
    reading_export.export(base, store)
    assert read == [] and text_file.stat().st_mtime_ns == written_at
    assert (base.export / 'index.json').read_bytes() == first_index


def test_a_changed_reading_is_read_and_written_again(one_page, monkeypatch):
    base, store, record = one_page
    reading_export.export(base, store)
    changed = page('::: {#b01 .paragraph bbox="10 50 900 120"}\nAnother sentence.\n:::')
    newer = {**record, 'text_sha256': hashlib.sha256(changed.encode('utf-8')).hexdigest()}
    store.save_reading(KEY, newer, changed)
    monkeypatch.setattr(vision_batches, 'readings_of', lambda cells, store: [newer])
    reading_export.export(base, store)
    assert (base.export / 'w' / 'p0002.md').read_text(encoding='utf-8') == changed


def test_the_legacy_fallback_pages_are_kept_by_what_they_depend_on(tmp_path, monkeypatch):
    from backend.configuration import data_paths
    from backend.search import search_server

    monkeypatch.setattr(data_paths, 'LICENSED_WORKING', tmp_path)
    computed = []
    monkeypatch.setattr(search_server, 'legacy_fallback_pages', lambda: computed.append(1) or {'a.pdf': {1, 2}})
    monkeypatch.setattr(reading_export, 'legacy_inputs_key', lambda: 'inputs one')
    assert reading_export.legacy_fallback_pages() == reading_export.legacy_fallback_pages() == {'a.pdf': {1, 2}}
    assert len(computed) == 1
    monkeypatch.setattr(reading_export, 'legacy_inputs_key', lambda: 'inputs two')  # a mark, an offset or a file changed
    reading_export.legacy_fallback_pages()
    assert len(computed) == 2


def test_a_text_file_changed_since_the_last_export_is_written_again(one_page):
    # the review of #5: an unchanged page's file was trusted without a look, so an edit by hand stayed for good
    base, store, record = one_page
    reading_export.export(base, store)
    text_file = base.export / 'w' / 'p0002.md'
    text_file.write_text('edited by hand', encoding='utf-8')
    reading_export.export(base, store)
    assert text_file.read_text(encoding='utf-8') == TEXT


def test_a_reading_whose_text_is_gone_is_exported_as_before_never_from_its_hash(one_page):
    # the review of #5: a cache keyed by the record's text hash answered for a text the store no longer held, or crashed
    base, store, record = one_page
    reading_export.export(base, store)
    store.path('readings', KEY[:2], KEY + '.md').unlink()
    (base.export / 'w' / 'p0002.md').unlink()
    (row,) = reading_export.export(base, store)['pages']
    assert 'text_file' not in row and row['class_now'] != 'ok'


def test_a_cache_file_that_cannot_be_read_is_an_empty_cache(one_page):
    base, store, record = one_page
    reading_export.export(base, store)
    for name in ('classes.json', 'row_facts.json'):
        store.path('cache', name).write_text('{"half', encoding='utf-8')
    # a broken index.json still stops the export, as before: its guard (half the pages) cannot be judged without it
    reading_export.export(base, store)
    assert (base.export / 'w' / 'p0002.md').read_text(encoding='utf-8') == TEXT


def test_a_store_whose_folder_is_a_link_out_of_it_is_refused(tmp_path):
    import os

    outside = tmp_path / 'outside'
    outside.mkdir()
    root = tmp_path / 'vision'
    root.mkdir()
    try:
        os.symlink(outside, root / 'readings', target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            pytest.skip('this machine may not create a link')
        import _winapi

        _winapi.CreateJunction(str(outside), str(root / 'readings'))  # Windows without the right to a symlink: a junction
    with pytest.raises(reading_store.UnsafeRootError, match='is a link'):
        reading_store.Store(root)


def test_the_code_hash_is_of_the_code_as_loaded_and_not_of_where_it_lies():
    def one(x):
        return x + 1

    def other(x):
        return x + 2

    assert reading_store.loaded_code_hash(one) != reading_store.loaded_code_hash(other)
    assert reading_store.loaded_code_hash(one) == reading_store.loaded_code_hash(one)


def test_the_code_hashes_are_the_same_in_every_process():
    # found 21 Nov: a set's order changes with each start of Python, so the caches never held between two runs
    import os
    import subprocess
    import sys

    ask = ('from backend.conversion.store import reading_store, reading_export; '
           'print(reading_store.validator_code_hash(), reading_export.facts_code_hash())')
    seen = {subprocess.run([sys.executable, '-c', ask], capture_output=True, text=True, check=True,
                           env={**os.environ, 'PYTHONHASHSEED': seed}).stdout for seed in ('1', '2')}
    assert len(seen) == 1
