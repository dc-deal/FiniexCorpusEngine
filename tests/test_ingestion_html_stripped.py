"""The HTML sources as stripped, readable HTML for the diagnostics view (the operator's 5.a, 9 Nov): nothing that runs or loads, the
same text the index holds, the loader untouched, and the dropped sections each once in order."""

import hashlib
import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from backend.configuration import data_paths
from backend.ingestion.clean_sections import html_sections, html_stripped

REPO = Path(__file__).resolve().parents[1]
CATALOG = json.loads((REPO / 'corpus' / 'catalog.json').read_text(encoding='utf-8'))['sources']
MANIFEST_FILE = data_paths.FREE_RAW / '_manifest.json'
MANIFEST = json.loads(MANIFEST_FILE.read_text(encoding='utf-8')).get('files', {}) if MANIFEST_FILE.exists() else {}
HTML_SOURCES = [source for source in CATALOG if source.get('format') == 'html']
FORBIDDEN_TAGS = {'script', 'style', 'link', 'meta', 'base', 'iframe', 'noscript', 'form', 'object', 'embed', 'svg', 'canvas',
                  'video', 'audio', 'img'}


def present(source: dict) -> bool:
    return all(data_paths.locate(entry['path']).exists() for entry in source['files'])


@pytest.fixture(scope='module', params=[source['id'] for source in HTML_SOURCES])
def stripped_source(request):
    source = next(source for source in HTML_SOURCES if source['id'] == request.param)
    if not present(source):
        pytest.skip(f"{source['id']} is not downloaded: python -m backend.ingestion.acquire")
    return source, *html_stripped.strip_source(source, MANIFEST, data_paths.DATA)


def walker_text(fragment: str) -> str:
    """A stripped section's text read the way the loader reads text: its outer blocks, each by `text_of`."""
    root = BeautifulSoup(fragment, 'html.parser')
    return '\n'.join(text for text in (html_sections.text_of(element) for element in root.find_all(html_sections.BLOCKS)
                                       if element.find_parent(html_sections.BLOCKS) is None) if text)


def test_no_forbidden_tag_or_attribute_survives(stripped_source):
    _, sections, dropped = stripped_source
    for part in [section.html for section in sections] + [section.html for section in dropped]:
        for tag in BeautifulSoup(part, 'html.parser').find_all(True):
            assert tag.name not in FORBIDDEN_TAGS
            assert all(not name.startswith('on') and name not in ('style', 'class') for name in tag.attrs), (tag.name, tag.attrs)
            assert tag.name != 'a' or not tag.get('href') or tag['href'].startswith(('http://', 'https://', '#'))


def test_every_stripped_section_reads_as_the_text_the_index_holds(stripped_source):
    source, sections, _ = stripped_source
    loaded = html_sections.load_html_sections(source, MANIFEST, data_paths.DATA)
    assert [section.ordinal for section in sections] == [section.ordinal for section in loaded]
    for made, indexed in zip(sections, loaded):
        assert made.heading_path == indexed.heading_path and made.anchor == indexed.anchor
        assert walker_text(made.html) == indexed.text, (source['id'], indexed.ordinal, indexed.heading_path)


def test_a_formula_is_marked_for_typesetting_and_shown_once():
    # Wikipedia gives each formula as MathML with its LaTeX and as a picture whose alt text is the same LaTeX: the view showed
    # it twice, once as text and once as an image placeholder (the operator, 10 Nov, Sharpe ratio).
    page = ('<html><body><div class="mw-parser-output"><h2 id="Definition">Definition</h2><p>The ratio is'
            '<span><math display="block" alttext="{\\displaystyle S_{a}={\\frac {a}{b}},}"><mi>S</mi></math></span>'
            '<img class="mwe-math-fallback-image-display" alt="{\\displaystyle S_{a}={\\frac {a}{b}},}" src="x.svg"/>'
            ' where <math alttext="{\\displaystyle R_{a}}"><mi>R</mi></math>'
            '<img class="mwe-math-fallback-image-inline" alt="{\\displaystyle R_{a}}" src="y.svg"/> is the return.</p>'
            '</div></body></html>')
    profile = html_sections.PROFILES['wikipedia']
    sections, _ = html_stripped.strip_document(page, profile, 'probe', 'Probe', 'probe.html')
    marks = BeautifulSoup(sections[0].html, 'html.parser').find_all(attrs={'data-tex': True})
    assert [(mark['data-tex'], mark['data-display']) for mark in marks] == [('S_{a}={\\frac {a}{b}},', 'block'), ('R_{a}', 'inline')]
    assert 'data-image' not in sections[0].html
    indexed = html_sections.parse_sections(page, profile, 'probe', 'https://example.org/probe', 'Probe')
    assert walker_text(sections[0].html) == indexed[0].text


def test_the_loader_and_its_version_are_untouched():
    # The chat's index is keyed by the loader's version and code: the strip module reads beside it, never inside it.
    assert html_sections.LOADER_VERSION == 4
    digest = hashlib.sha256((REPO / 'src' / 'backend' / 'ingestion' / 'clean_sections' / 'html_sections.py').read_bytes()).hexdigest()
    index = REPO / 'corpus' / 'sections' / 'index.json'
    if index.exists():
        recorded = json.dumps(json.loads(index.read_text(encoding='utf-8')))
        assert digest in recorded or 'code_sha256' not in recorded


def test_every_dropped_heading_comes_back_once_in_document_order(stripped_source):
    source, sections, dropped = stripped_source
    profile = html_sections.PROFILES[source['html_profile']]
    expected = []
    for entry in source['files']:
        soup = BeautifulSoup(data_paths.locate(entry['path']).read_text(encoding='utf-8'), 'html.parser')
        for selector in profile.noise:
            for element in soup.select(selector):
                element.decompose()
        root = soup.select_one(profile.content) if profile.content else (soup.body or soup)
        expected += [(entry['path'], heading_id) for heading_id in html_sections.drop_sections(root, profile.drop_headings)]
    assert [(section.file, section.heading_id) for section in dropped] == expected
    ordinals = [section.ordinal for section in sections]
    assert all(section.after_ordinal is None or section.after_ordinal in ordinals for section in dropped)
