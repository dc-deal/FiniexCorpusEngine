"""What phase 1 measured on the real files, pinned so that a change to loading cannot lose it.

These read corpus/raw/ and are skipped where it is missing (marker `corpus`). They make no
network calls and spend nothing. The ones that read an OpenStax book are also marked `slow`:
with table detection a book takes 60-100 s, so they run with `pytest -m slow`, not by default.
"""

import functools
import json
import re
from pathlib import Path

import pytest

from backend.configuration import data_paths
from backend.ingestion.clean_sections.html_sections import load_html_sections
from backend.ingestion.clean_sections.pdf_sections import load_pdf_sections

ROOT = Path(__file__).resolve().parent.parent
RAW = data_paths.FREE_RAW
pytestmark = pytest.mark.corpus


def catalog_source(source_id: str) -> dict:
    catalog = json.loads((ROOT / 'corpus' / 'catalog.json').read_text(encoding='utf-8'))
    return next(s for s in catalog['sources'] if s['id'] == source_id)


def pdf(source_id: str):
    path = RAW / f'{source_id}.pdf'
    if not path.exists():
        pytest.skip(f'{path.name} not downloaded')
    return _load_pdf(source_id)


@functools.cache
def _load_pdf(source_id: str):
    # Reading a whole book with table detection takes 60-80 s, so each book is read once per run.
    return load_pdf_sections(source_id, RAW / f'{source_id}.pdf')


@pytest.fixture(scope='module')
def manifest():
    if not (RAW / '_manifest.json').exists():  # a module fixture is set up before the marker's skip could run
        pytest.skip('_data/corpus/raw/ is empty - run python -m backend.ingestion.acquire first')
    return json.loads((RAW / '_manifest.json').read_text(encoding='utf-8'))['files']


def section(sections, prefix):
    return next(s for s in sections if s.title.startswith(prefix))


@pytest.mark.slow
def test_finance_section_15_4_starts_on_pdf_page_470_printed_456():
    found = section(pdf('openstax_principles_of_finance_2e'), '15.4 ')
    assert found.pages[0][1:] == (470, 456)


@pytest.mark.slow
def test_accounting_section_3_5_starts_on_pdf_page_137_printed_123():
    found = section(pdf('openstax_principles_of_accounting_v1'), '3.5 ')
    assert found.pages[0][1:] == (137, 123)


@pytest.mark.slow
def test_openstax_attribution_line_is_gone_except_where_the_preface_quotes_it():
    for sec in pdf('openstax_principles_of_finance_2e'):
        if 'Access for free at openstax.org' in sec.text:
            assert 'Preface' in sec.heading_path, sec.heading_path


@pytest.mark.slow
def test_the_finance_book_is_not_read_twice():
    # A trailing outline entry pointing back to page 2 once doubled the book (3.1 M characters).
    assert sum(len(s.text) for s in pdf('openstax_principles_of_finance_2e')) < 1_620_000


def test_kelly_paper_words_are_whole_and_its_back_matter_is_gone():
    sections = pdf('carta_conversano_kelly_criterion_2020')
    text = ' '.join(s.text for s in sections)
    assert 'fron tiersin' not in text and 'follo wing' not in text
    assert not any(s.title in ('References', 'Author Contributions') for s in sections)
    assert all(printed == pdf_page for s in sections for _, pdf_page, printed in s.pages)


def test_wikipedia_keeps_its_content_drops_its_link_lists_and_links_the_revision(manifest):
    sections = load_html_sections(catalog_source('wikipedia_trading_set'), manifest, data_paths.DATA)
    titles = {s.title for s in sections}
    assert not titles & {'References', 'External links', 'See also', 'Further reading'}
    definition = next(s for s in sections if s.url.endswith('Sharpe_ratio&oldid=1368876746#Definition'))
    assert '\\frac' in definition.text


def test_gutenberg_print_page_numbers_and_licence_are_gone(manifest):
    sections = load_html_sections(catalog_source('lefevre_reminiscences_of_a_stock_operator'), manifest, data_paths.DATA)
    text = ' '.join(s.text for s in sections)
    assert not re.search(r'\[Pg\s*\d+\]', text)
    assert 'Project Gutenberg License' not in text
    assert sum(1 for s in sections if s.anchor) == 24  # chapters I–XXIV


def test_every_sre_section_but_the_chapter_openings_has_an_anchor(manifest):
    sections = load_html_sections(catalog_source('google_site_reliability_engineering'), manifest, data_paths.DATA)
    without = [s for s in sections if not s.anchor]
    assert len(without) <= 40  # at most one opening passage per file


@pytest.mark.slow
def test_finance_tables_keep_their_rows_and_columns():
    # Table 3.4 was a column of bare numbers before phase 2 used find_tables().
    text = next(s.text for s in pdf('openstax_principles_of_finance_2e') if 'Table 3.4 Demand and Supply' in s.text)
    assert '|Price ($)|Quantity|Price ($)|Quantity|' in text
    assert '|55| 0| 55| 45|' in text
    digit_lines = sum(len(re.findall(r'^\s*\d{1,4}\s*$', s.text, re.M)) for s in pdf('openstax_principles_of_finance_2e'))
    assert digit_lines < 200  # 1,067 before; 69 after


def test_the_one_sre_heading_without_an_anchor_of_its_own_links_to_itself(manifest):
    sections = load_html_sections(catalog_source('google_site_reliability_engineering'), manifest, data_paths.DATA)
    fragments = [s for s in sections if ':~:text=' in (s.url or '')]
    assert [s.heading_path[-1] for s in fragments] == ['DevOps or SRE?']
