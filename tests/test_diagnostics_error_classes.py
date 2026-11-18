"""Error classes: the export's findings grouped by stage, kind, block class and work, void ones apart, each with its
pages; every finding counted once, and nothing of the licensed export under --public-only."""

from collections import Counter

from fastapi.testclient import TestClient

from backend.diagnostics import readings
from backend.diagnostics.app import create_app

# TestClient's own host, "testserver", is refused like any other name that is not this machine's (app.TRUSTED_HOSTS)
LOCAL = 'http://127.0.0.1'


def test_every_finding_of_the_export_stands_in_exactly_one_class_with_its_pages():
    answer = TestClient(create_app(public_only=True), base_url=LOCAL).get('/api/error-classes').json()
    rows = readings.Readings().rows()
    judge = Counter((f.get('kind'), f.get('block_class'), bool(f.get('void')), row['source_id'])
                    for row in rows for f in ((row.get('check') or {}).get('verdict') or {}).get('findings') or [])
    stage2 = Counter((f.get('kind'), row['source_id']) for row in rows for f in ((row.get('check') or {}).get('stage2') or {}).get('findings') or [])
    listed_judge = {(c['kind'], c['block_class'], c['void'], c['source_id']): c['findings'] for c in answer['classes'] if c['stage'] == 'judge'}
    listed_stage2 = {(c['kind'], c['source_id']): c['findings'] for c in answer['classes'] if c['stage'] == 'stage 2'}
    assert listed_judge == dict(judge) and listed_stage2 == dict(stage2)
    assert {c['knowledge_base'] for c in answer['classes']} <= {'free'}
    # most first, and each class's pages are pages that carry such a finding
    counts = [c['findings'] for c in answer['classes']]
    assert counts == sorted(counts, reverse=True)
    by_page = {(row['source_id'], row['pdf_page']): row for row in rows}
    for one in answer['classes'][:5]:
        for page in one['pages']:
            check = by_page[(one['source_id'], page)]['check']
            found = (check.get('stage2') or {}).get('findings') if one['stage'] == 'stage 2' else check['verdict']['findings']
            assert any(f.get('kind') == one['kind'] for f in found)
