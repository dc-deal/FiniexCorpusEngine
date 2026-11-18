from backend.ingestion import build, chunking


def test_the_fingerprint_changes_with_the_raw_file_and_with_the_splitting(monkeypatch):
    source = {'format': 'pdf', 'files': [{'path': 'corpus/raw/a.pdf'}]}
    before = build.fingerprint(source, {'corpus/raw/a.pdf': {'sha256': 'aaa'}})
    assert build.fingerprint(source, {'corpus/raw/a.pdf': {'sha256': 'bbb'}}) != before
    monkeypatch.setattr(chunking, 'CHUNK_OVERLAP', 100)
    assert build.fingerprint(source, {'corpus/raw/a.pdf': {'sha256': 'aaa'}}) != before


def test_a_new_pdf_loader_version_re_indexes_pdfs_and_nothing_else(monkeypatch):
    manifest = {'corpus/raw/a.pdf': {'sha256': 'aaa'}, 'corpus/raw/b.html': {'sha256': 'bbb'}}
    pdf_source = {'format': 'pdf', 'files': [{'path': 'corpus/raw/a.pdf'}]}
    html_source = {'format': 'html', 'files': [{'path': 'corpus/raw/b.html'}]}
    before = build.fingerprint(pdf_source, manifest), build.fingerprint(html_source, manifest)
    monkeypatch.setitem(build.LOADER_VERSIONS, 'pdf', build.LOADER_VERSIONS['pdf'] + 1)
    assert build.fingerprint(pdf_source, manifest) != before[0]
    assert build.fingerprint(html_source, manifest) == before[1]
