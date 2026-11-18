"""`NOTICE.md` names every free work the catalog holds; a work taken in without it fails here."""

import json

from backend.ingestion import notice


def test_the_notice_is_written_from_the_catalog_as_it_stands():
    catalog = json.loads(notice.CATALOG.read_text(encoding='utf-8'))
    assert notice.NOTICE.read_text(encoding='utf-8') == notice.render_notice(catalog), \
        'NOTICE.md is stale - run python -m backend.ingestion.notice'


def test_every_work_and_every_non_commercial_one_is_named():
    catalog = json.loads(notice.CATALOG.read_text(encoding='utf-8'))
    text = notice.NOTICE.read_text(encoding='utf-8')
    assert all(f"### {source['title']}" in text for source in catalog['sources'])
    non_commercial = text.split('## Non-commercial works', 1)[1].split('## For rights holders', 1)[0]
    assert all(source['title'] in non_commercial for source in catalog['sources'] if '-NC' in source['licence'])
