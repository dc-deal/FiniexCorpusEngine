import json
import re
from collections import Counter
from pathlib import Path

import pymupdf
import pytest

from backend.configuration import data_paths
from backend.conversion.contract import page_contract
from backend.conversion.reading import reading_cells
from backend.conversion.store.reading_store import REPO

CANDIDATES = data_paths.FREE_WORKING / 'gold' / 'candidates_public_exact.json'
SOURCE = json.loads(reading_cells.MINI_PILOT.read_text(encoding='utf-8'))
PAGES = SOURCE['pages']
GOLD = {('openstax_principles_of_finance_2e.pdf', page) for page in (204, 298, 343, 393, 457, 486)} \
    | {('openstax_principles_of_accounting_v1.pdf', page) for page in (69, 217, 455, 767)} \
    | {('carta_conversano_kelly_criterion_2020.pdf', page) for page in (5, 6)} \
    | {('deep_walk_forward_validation_2025.pdf', page) for page in (9, 12)}
COVERAGE = {('openstax_principles_of_finance_2e.pdf', page) for page in (179, 405, 445, 446)} \
    | {('openstax_principles_of_accounting_v1.pdf', page) for page in (192, 530)}
WORKS = {'openstax_principles_of_finance_2e.pdf': 'openstax-finance-2e', 'openstax_principles_of_accounting_v1.pdf': 'openstax-accounting',
         'carta_conversano_kelly_criterion_2020.pdf': 'carta-conversano-kelly-2020', 'deep_walk_forward_validation_2025.pdf': 'deep-walk-forward-2025'}
# Read whole by the corpus cell, with no page in the mini pilot (decision 121.b)
CORPUS_WORKS = {'fed_sr_11_7_model_risk_management_2011.pdf': 'fed-sr-11-7', 'fed_sr_26_2_model_risk_management_2026.pdf': 'fed-sr-26-2',
                'regulation_t_12_cfr_220_2025.pdf': 'regulation-t',
                # and since decision 143.a (9 Nov)
                'eu_delegated_regulation_2017_565.pdf': 'eu-2017-565', 'sec_regulation_nms_rule_600_2025.pdf': 'reg-nms-600',
                'sec_regulation_nms_rule_605_2025.pdf': 'reg-nms-605', 'sec_regulation_nms_rule_606_2025.pdf': 'reg-nms-606'}


def page_list(tmp_path: Path, pages: list, cards: dict) -> Path:
    path = tmp_path / 'pages.json'
    path.write_text(json.dumps({'work_cards': cards, 'pages': pages}), encoding='utf-8')
    return path


def test_the_four_cells_of_the_mini_pilot():
    cells = reading_cells.CELLS
    assert {name: (cell.model, cell.form) for name, cell in cells.items()} == {
        'MP-HM': ('claude-haiku-5-5', 'markdown'), 'MP-HJ': ('claude-haiku-5-5', 'json'),
        'MP-SM': ('claude-sonnet-5-5', 'markdown'), 'MP-SJ': ('claude-sonnet-5-5', 'json')}
    assert {cell.resolution for cell in cells.values()} == {'hi'}
    assert {cell.page_source for cell in cells.values()} == {reading_cells.MINI_PILOT}
    assert {cell.form for cell in cells.values()} == set(page_contract.FORMS)


def test_the_list_holds_the_14_gold_pages_and_the_6_for_class_coverage():
    assert len(PAGES) == 20
    assert {(page['file'], page['pdf_page']) for page in PAGES if page['gold']} == GOLD
    assert {(page['file'], page['pdf_page']) for page in PAGES if not page['gold']} == COVERAGE


def test_the_gold_pages_are_the_ones_of_the_candidates_list():
    if not CANDIDATES.exists():
        pytest.skip('the local candidates list is not on this machine')
    listed = {(item['file'], item['pdf_page']) for item in json.loads(CANDIDATES.read_text(encoding='utf-8'))['candidates']}
    assert listed == GOLD


def test_every_page_says_what_the_runner_and_a_reader_of_the_results_need():
    for page in PAGES:
        assert set(page) == {'file', 'pdf_page', 'work', 'gold', 'class_note', 'expected_output_tokens'}, page
        assert page['class_note'] and 1000 <= page['expected_output_tokens'] <= 8000, page
        assert WORKS[page['file']] == page['work'], page


def test_every_work_has_one_short_factual_card():
    assert set(SOURCE['work_cards']) == set(WORKS.values()) | set(CORPUS_WORKS.values())
    assert {work['file']: work['work'] for work in SOURCE['corpus_works']} == CORPUS_WORKS
    for work, card in SOURCE['work_cards'].items():
        assert 1 <= len(re.findall(r'[.!?](?:\s|$)', re.sub(r"'[^']*'", '', card))) <= 3, work
        assert 100 < len(card) < 800, work
    assert 'columns: 2' in SOURCE['work_cards']['carta-conversano-kelly-2020']


def test_every_page_lies_in_the_free_corpus_and_a_page_of_its_pdf(monkeypatch):
    monkeypatch.setattr(reading_cells, 'LICENSED_ARCHIVE', REPO / 'no_such_folder')
    for file_name, page_numbers in {name: [page['pdf_page'] for page in PAGES if page['file'] == name] for name in WORKS}.items():
        if not (reading_cells.FREE_ARCHIVE / file_name).exists():
            pytest.skip(f'{file_name} is not downloaded: python -m backend.ingestion.acquire')
        mirror, path = reading_cells.source_of(file_name)
        assert mirror == 'free'
        with pymupdf.open(path) as document:
            assert all(1 <= number <= len(document) for number in page_numbers)


def test_a_cells_pages_carry_their_id_and_their_card():
    pages = reading_cells.pages_for(reading_cells.CELLS['MP-SJ'])
    assert len(pages) == 20
    first = next(page for page in pages if page['id'] == 'openstax-finance-2e:p0179')
    assert first['pdf_page'] == 179 and first['work_card'] == SOURCE['work_cards']['openstax-finance-2e']
    assert len({page['id'] for page in pages}) == 20


def test_a_cell_reads_any_page_list_so_a_corpus_cell_is_one_more_file(tmp_path):
    source = page_list(tmp_path, [{'file': 'other.pdf', 'pdf_page': 3, 'work': 'other', 'expected_output_tokens': 1200}], {'other': 'A card.'})
    cell = reading_cells.Cell('C-1', reading_cells.SONNET, 'hi', 'markdown', source)
    assert reading_cells.pages_for(cell) == [{'file': 'other.pdf', 'pdf_page': 3, 'work': 'other', 'expected_output_tokens': 1200,
                                              'id': 'other:p0003', 'work_card': 'A card.'}]


def test_a_whole_work_cell_lists_every_page_of_its_pdf(tmp_path, monkeypatch):
    with pymupdf.open() as document:
        for _ in range(3):
            document.new_page()
        document.save(tmp_path / 'other.pdf')
    monkeypatch.setattr(reading_cells, 'FREE_ARCHIVE', tmp_path)
    source = page_list(tmp_path, [{'file': 'other.pdf', 'pdf_page': 2, 'work': 'other', 'expected_output_tokens': 1200}], {'other': 'A card.'})
    cell = reading_cells.Cell('C-2', reading_cells.SONNET, 'hi', 'markdown', source, whole_works=('other',))
    assert [page['id'] for page in reading_cells.pages_for(cell)] == ['other:p0001', 'other:p0002', 'other:p0003']


def test_a_whole_work_needs_its_file_in_the_page_source(tmp_path):
    source = page_list(tmp_path, [], {'other': 'A card.'})
    cell = reading_cells.Cell('C-2', reading_cells.SONNET, 'hi', 'markdown', source, whole_works=('other',))
    with pytest.raises(ValueError, match='no file known'):
        reading_cells.pages_for(cell)


def test_the_corpus_cell_reads_every_page_of_the_four_free_pdfs_as_the_pilot_chose(monkeypatch):
    monkeypatch.setattr(reading_cells, 'LICENSED_ARCHIVE', REPO / 'no_such_folder')
    if not all((reading_cells.FREE_ARCHIVE / name).exists() for name in {**WORKS, **CORPUS_WORKS}):
        pytest.skip('a free PDF is not downloaded: python -m backend.ingestion.acquire')
    cell = reading_cells.CORPUS_CELLS['FREE-SM']
    assert (cell.model, cell.form, cell.resolution) == (reading_cells.SONNET, 'markdown', 'hi')
    pages = reading_cells.pages_for(cell)
    assert Counter(page['work'] for page in pages) == {'openstax-finance-2e': 629, 'openstax-accounting': 973,
                                                       'carta-conversano-kelly-2020': 15, 'deep-walk-forward-2025': 35,
                                                       'fed-sr-11-7': 21, 'fed-sr-26-2': 14, 'regulation-t': 30,
                                                       'eu-2017-565': 83, 'reg-nms-600': 13, 'reg-nms-605': 5, 'reg-nms-606': 4}
    assert len({page['id'] for page in pages}) == 1822
    pilot_page = next(page for page in pages if page['id'] == 'openstax-finance-2e:p0179')
    assert pilot_page['work_card'] == SOURCE['work_cards']['openstax-finance-2e']


def test_the_free_plan_is_the_whole_works_and_a_sessions_unread_pages_nothing_else(tmp_path, monkeypatch):
    for name, count in (('whole.pdf', 3), ('other.pdf', 2)):
        with pymupdf.open() as document:
            for _ in range(count):
                document.new_page()
            document.save(tmp_path / name)
    monkeypatch.setattr(reading_cells, 'FREE_ARCHIVE', tmp_path)
    source = tmp_path / 'source.json'
    source.write_text(json.dumps({'work_cards': {}, 'pages': [], 'corpus_works': [{'file': 'whole.pdf', 'work': 'whole'},
                                                                                    {'file': 'absent.pdf', 'work': 'absent'}]}),
                      encoding='utf-8')
    monkeypatch.setattr(reading_cells, 'CORPUS_CELLS', {'FREE-SM': reading_cells.Cell(
        'FREE-SM', reading_cells.SONNET, 'hi', 'markdown', source, whole_works=('whole', 'absent'))})
    direct = tmp_path / 'direct.json'
    direct.write_text(json.dumps({'pages': [{'file': 'other.pdf', 'pdf_page': 2, 'why': 'unread'},
                                            {'file': 'other.pdf', 'pdf_page': 1, 'why': 'read in the session'}]}), encoding='utf-8')
    monkeypatch.setattr(reading_cells, 'DIRECT_PAGES', {'free': direct, 'licensed': tmp_path / 'none.json'})
    # every page of the whole work on this machine, the session's unread page; not the absent work, not a page read already
    assert reading_cells.free_planned_pages() == {('whole.pdf', 1), ('whole.pdf', 2), ('whole.pdf', 3), ('other.pdf', 2)}


def test_no_derivatives_work_of_the_free_catalog_is_planned():
    catalog = json.loads((REPO / 'corpus' / 'catalog.json').read_text(encoding='utf-8'))['sources']
    no_derivatives = {Path(source['files'][0]['path']).name for source in catalog
                      if source.get('format') == 'pdf' and '-ND' in source['licence'].replace(' ', '-')}
    assert no_derivatives  # the FIX specification and Makarov and Schoar, 22 Nov
    assert not {file for file, _ in reading_cells.free_planned_pages()} & no_derivatives


def test_a_page_whose_work_has_no_card_is_an_error_not_a_blank_prompt(tmp_path):
    source = page_list(tmp_path, [{'file': 'other.pdf', 'pdf_page': 3, 'work': 'other', 'expected_output_tokens': 1200}], {})
    with pytest.raises(ValueError, match='no work card'):
        reading_cells.pages_for(reading_cells.Cell('C-1', reading_cells.SONNET, 'hi', 'markdown', source))


def test_the_provenance_list_holds_files_back(tmp_path, monkeypatch):
    provenance = tmp_path / 'provenance.json'
    provenance.write_text(json.dumps({'files': {'stamped.pdf': {'send': False}, 'clean.pdf': {'send': True}}}), encoding='utf-8')
    monkeypatch.setattr(reading_cells, 'PROVENANCE', provenance)
    assert not reading_cells.may_send('stamped.pdf')
    assert reading_cells.may_send('clean.pdf') and reading_cells.may_send('unlisted.pdf')


def test_without_a_provenance_list_a_file_may_be_sent(tmp_path, monkeypatch):
    monkeypatch.setattr(reading_cells, 'PROVENANCE', tmp_path / 'absent.json')
    assert reading_cells.may_send('anything.pdf')


def test_a_source_is_looked_for_in_the_free_corpus_first(tmp_path, monkeypatch):
    free, licensed = tmp_path / 'free', tmp_path / 'licensed'
    free.mkdir()
    licensed.mkdir()
    (free / 'both.pdf').write_bytes(b'x')
    (licensed / 'both.pdf').write_bytes(b'x')
    (licensed / 'private.pdf').write_bytes(b'x')
    monkeypatch.setattr(reading_cells, 'FREE_ARCHIVE', free)
    monkeypatch.setattr(reading_cells, 'LICENSED_ARCHIVE', licensed)
    assert reading_cells.source_of('both.pdf') == ('free', free / 'both.pdf')
    assert reading_cells.source_of('private.pdf') == ('licensed', licensed / 'private.pdf')
    with pytest.raises(FileNotFoundError, match='neither archive'):
        reading_cells.source_of('absent.pdf')


def test_a_reader_prototype_reads_free_pages_and_no_knowledge_base_serves_it():
    # decision 207.a: page/2's readings are a prototype's (147.a): kept apart by their prompt's hash and by no export naming
    # their cells, so none can ever stand for a page
    from backend.conversion.reading import reader_requests
    from backend.conversion.store import reading_export

    served = set(reading_export.FREE.cells()) | set(reading_export.cells_beside(reading_export.FREE))
    page_1 = reader_requests.sha256_text(reader_requests.system_prompt('markdown'))
    for cell in reading_cells.READER_PROTOTYPE_CELLS.values():
        assert cell.name not in served and cell.reader_version != 'page/1'
        assert reading_cells.knowledge_base_of(cell) == 'free'
        assert reader_requests.sha256_text(reader_requests.system_prompt(cell.form, cell.reader_version)) != page_1
    # the walk's pages by the cell's own list: listing them opens the accounting PDF, which a clone lacks (167 MB, untracked)
    walk = reading_cells.READER_PROTOTYPE_CELLS['P2-WALK-SM']
    assert walk.only == reading_cells.WALK_ERRORS and set(walk.whole_works) == {page.split(':')[0] for page in walk.only}
    assert len(reading_cells.pages_for(reading_cells.READER_PROTOTYPE_CELLS['P2-MP-SM'])) == 20
