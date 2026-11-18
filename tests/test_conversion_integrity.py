"""The integrity scan: a changed reading, a missing reading file and a page without a row are each found (decision 69.a)."""

import hashlib
import json

import pymupdf

import pytest

from backend.configuration import data_paths
from backend.conversion.checks import integrity


def an_export(tmp_path, pages=3):
    """An export of a three-page PDF with a reading for pages 1 and 2; the PDF lies under the repository's tmp-free path."""
    pdf = tmp_path / 'w.pdf'
    document = pymupdf.open()
    for _ in range(pages):
        document.new_page()
    document.save(pdf)
    export = tmp_path / 'readings'
    rows = []
    for number in (1, 2):
        text = f'page {number}\n'.encode('utf-8')
        (export / 'w').mkdir(parents=True, exist_ok=True)
        (export / 'w' / f'p{number:04d}.md').write_bytes(text)
        rows.append({'work': 'w', 'pdf_page': number, 'text_file': f'w/p{number:04d}.md', 'text_sha256': hashlib.sha256(text).hexdigest()})
    index = {'knowledge_base': 'free', 'works': [{'work': 'w', 'pdf': str(pdf)}], 'pages': rows}
    (export / 'index.json').write_text(json.dumps(index), encoding='utf-8')
    return export


def test_a_clean_export_has_no_finding_but_its_one_page_without_a_row(tmp_path, monkeypatch):
    found = integrity.scan(an_export(tmp_path))
    assert found['tampered'] == [] and found['missing_files'] == [] and found['gaps'] == [{'work': 'w', 'pdf_page': 3}]


def test_a_changed_number_and_a_deleted_reading_are_both_found(tmp_path, monkeypatch):
    export = an_export(tmp_path)
    (export / 'w' / 'p0001.md').write_text('page 7\n', encoding='utf-8')
    (export / 'w' / 'p0002.md').unlink()
    found = integrity.scan(export)
    assert [place['pdf_page'] for place in found['tampered']] == [1] and [place['pdf_page'] for place in found['missing_files']] == [2]
    assert integrity.problems(found) == 3


def test_one_page_s_state_is_the_scan_s_finding_for_it(tmp_path, monkeypatch):
    # Line 2's request (5 Nov): a page view asks for its own page on every visit, so a live change shows at once.
    export = an_export(tmp_path)
    rows = {row['pdf_page']: row for row in json.loads((export / 'index.json').read_text(encoding='utf-8'))['pages']}
    assert integrity.page_state(export, rows[1]) == 'whole'
    (export / 'w' / 'p0001.md').write_text('page 7\n', encoding='utf-8')
    (export / 'w' / 'p0002.md').unlink()
    assert (integrity.page_state(export, rows[1]), integrity.page_state(export, rows[2])) == ('tampered', 'missing')
    assert integrity.page_state(export, {'work': 'w', 'pdf_page': 3, 'text_file': None}) == 'no reading'


@pytest.mark.readings
def test_the_tracked_free_export_is_whole():
    found = integrity.scan(data_paths.FREE_READINGS)
    assert found['tampered'] == [] and found['missing_files'] == []
