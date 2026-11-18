import urllib.request

import pytest

from backend.configuration import data_paths
from backend.ingestion import acquire

CATALOG = {
    'sources': [
        {'id': 'book', 'format': 'pdf', 'files': [{'url': 'https://example.org/b.pdf', 'path': 'corpus/raw/b.pdf'}]},
        {'id': 'wiki', 'format': 'html', 'files': [
            {'url': 'https://en.wikipedia.org/api/rest_v1/page/html/A', 'path': 'corpus/raw/w/A.html'},
            {'url': 'https://en.wikipedia.org/api/rest_v1/page/html/B', 'path': 'corpus/raw/w/B.html'},
        ]},
    ]
}


def test_planned_files_lists_every_file_with_its_source_and_format():
    planned = acquire.planned_files(CATALOG)
    assert [(p['source_id'], p['format'], p['path']) for p in planned] == [
        ('book', 'pdf', 'corpus/raw/b.pdf'),
        ('wiki', 'html', 'corpus/raw/w/A.html'),
        ('wiki', 'html', 'corpus/raw/w/B.html'),
    ]


def test_planned_files_can_be_restricted_to_one_source():
    assert [p['path'] for p in acquire.planned_files(CATALOG, 'book')] == ['corpus/raw/b.pdf']
    assert acquire.planned_files(CATALOG, 'unknown') == []


@pytest.mark.parametrize('etag, expected', [
    ('W/"1368876746/5b1350a3-bab6-11f1-836f-ff8057489174/view"', 1368876746),
    ('"1368876746/5b1350a3"', 1368876746),
    ('"8f781dfa4834cc7062227fa3bce814fc-4"', None),  # an S3 ETag carries no revision
    (None, None),
])
def test_wikipedia_revision_is_read_from_the_etag(etag, expected):
    assert acquire.wikipedia_revision(etag) == expected


@pytest.mark.parametrize('file_format, content_type, body, problem', [
    ('pdf', 'application/pdf', b'%PDF-1.7 ...', None),
    ('html', 'text/html; charset=utf-8', b'<html></html>', None),
    ('pdf', 'text/html', b'<html>error</html>', 'content type'),  # an error page under a .pdf name
    ('pdf', 'application/pdf', b'<html>', '%PDF'),
    ('html', 'text/html', b'', 'empty'),
])
def test_check_content_rejects_what_the_format_does_not_promise(file_format, content_type, body, problem):
    result = acquire.check_content(file_format, content_type, body)
    if problem is None:
        assert result is None
    else:
        assert problem in result


def test_merge_manifest_keeps_the_record_of_a_file_that_was_not_replaced():
    existing = {'files': {'a': {'path': 'a', 'sha256': 'old'}, 'b': {'path': 'b', 'sha256': 'old'}}}
    records = [
        {'path': 'a', 'outcome': 'downloaded', 'sha256': 'new'},
        {'path': 'b', 'outcome': 'failed', 'error': 'timeout'},  # failed re-download: file unchanged
        {'path': 'c', 'outcome': 'failed', 'error': 'timeout'},  # never downloaded: record the failure
    ]
    merged = acquire.merge_manifest(existing, records)['files']
    assert merged['a']['sha256'] == 'new'
    assert merged['b']['sha256'] == 'old'
    assert merged['c']['error'] == 'timeout'
    assert all('outcome' not in record for record in merged.values())


def test_fetch_file_keeps_an_existing_file_without_downloading(tmp_path, monkeypatch):
    monkeypatch.setattr(data_paths, 'DATA', tmp_path)
    (tmp_path / 'corpus' / 'raw').mkdir(parents=True)
    (tmp_path / 'corpus' / 'raw' / 'b.pdf').write_bytes(b'%PDF-1.7')
    monkeypatch.setattr(acquire, 'download', lambda url: pytest.fail('must not download'))
    record = acquire.fetch_file(acquire.planned_files(CATALOG, 'book')[0], force=False)
    assert record['outcome'] == 'kept'


def test_fetch_file_never_writes_a_response_that_fails_the_content_check(tmp_path, monkeypatch):
    monkeypatch.setattr(data_paths, 'DATA', tmp_path)
    monkeypatch.setattr(acquire, 'download', lambda url: (b'<html>not found</html>', {
        'status': 200, 'content_type': 'text/html', 'etag': None, 'last_modified': None}))
    record = acquire.fetch_file(acquire.planned_files(CATALOG, 'book')[0], force=False)
    assert record['outcome'] == 'failed'
    assert not (tmp_path / 'corpus' / 'raw' / 'b.pdf').exists()


def test_fetch_file_records_size_hash_and_wikipedia_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(data_paths, 'DATA', tmp_path)
    monkeypatch.setattr(acquire, 'download', lambda url: (b'<html>A</html>', {
        'status': 200, 'content_type': 'text/html', 'etag': 'W/"42/abc/view"', 'last_modified': None}))
    record = acquire.fetch_file(acquire.planned_files(CATALOG, 'wiki')[0], force=False)
    assert record['outcome'] == 'downloaded'
    assert record['bytes'] == len(b'<html>A</html>')
    assert len(record['sha256']) == 64
    assert record['wikipedia_revision'] == 42
    assert (tmp_path / 'corpus' / 'raw' / 'w' / 'A.html').read_bytes() == b'<html>A</html>'
    assert not list((tmp_path / 'corpus' / 'raw' / 'w').glob('*.partial'))


def test_the_manifest_and_the_licences_are_written_with_lf_line_endings(tmp_path, monkeypatch):
    import json

    catalog = tmp_path / 'catalog.json'
    catalog.write_text(json.dumps({'sources': [{**CATALOG['sources'][0], 'title': 'B', 'authors': 'A', 'publisher': 'P', 'year': 2026, 'licence': 'CC BY 4.0',
                                                'licence_url': 'https://example.org', 'licence_checked': '2026-11-08',
                                                'source_url': 'https://example.org'}]}), encoding='utf-8')
    monkeypatch.setattr(data_paths, 'DATA', tmp_path)
    for name, value in [('ROOT', tmp_path), ('CATALOG', catalog), ('MANIFEST', tmp_path / 'manifest.json'),
                        ('LICENSES', tmp_path / 'LICENSES.md'), ('PAUSE_SECONDS', 0)]:
        monkeypatch.setattr(acquire, name, value)
    monkeypatch.setattr(acquire, 'download', lambda url: (b'%PDF-1.7 a page', {
        'status': 200, 'content_type': 'application/pdf', 'etag': None, 'last_modified': None}))
    acquire.main([])
    assert b'\r\n' not in (tmp_path / 'manifest.json').read_bytes() and b'\r\n' not in (tmp_path / 'LICENSES.md').read_bytes()


def test_wikipedia_permalink_points_at_the_recorded_revision():
    assert acquire.wikipedia_permalink('corpus/raw/w/Sharpe_ratio.html', 1368876746) == (
        'https://en.wikipedia.org/w/index.php?title=Sharpe_ratio&oldid=1368876746')


def test_render_licences_attributes_every_source_and_names_what_is_missing():
    catalog = {'sources': [
        {'id': 'book', 'title': 'A Book', 'authors': 'A. Author', 'publisher': 'Pub', 'year': 2020,
         'licence': 'CC BY-NC-SA 4.0', 'licence_url': 'https://example.org/licence',
         'licence_checked': '2026-09-28', 'source_url': 'https://example.org/book',
         'files': [{'path': 'corpus/raw/b.pdf', 'tracked': False, 'not_tracked_because': 'too large'}]},
        {'id': 'wiki', 'title': 'Articles', 'authors': 'Wikipedia contributors', 'publisher': 'WMF',
         'year': None, 'licence': 'CC BY', 'licence_url': 'https://example.org/cc',
         'licence_checked': '2026-09-28', 'source_url': 'https://en.wikipedia.org/',
         'files': [{'path': 'corpus/raw/w/Sharpe_ratio.html'}]},
    ]}
    manifest = {'files': {'corpus/raw/w/Sharpe_ratio.html': {'wikipedia_revision': 42}}}
    text = acquire.render_licences(catalog, manifest)
    assert '## A Book' in text and '## Articles' in text
    assert '[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)' in text
    # an unversioned licence name is shown as stated, never linked to a guessed version
    assert '**Licence:** CC BY, stated at' in text
    assert '`corpus/raw/b.pdf`: too large' in text
    assert 'title=Sharpe_ratio&oldid=42' in text


def test_the_offline_guard_refuses_a_real_download():
    with pytest.raises(RuntimeError, match='offline test'):
        urllib.request.urlopen('https://example.org', timeout=5)
