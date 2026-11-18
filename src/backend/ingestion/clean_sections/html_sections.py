"""HTML sources → cleaned sections, one per heading, each with a link to its exact place.

A small hand-written walker is used here rather than LangChain's `HTMLHeaderTextSplitter`,
because the splitter keeps a heading's *text* but drops its *id*. The id is what a citation links
to (`…#Definition`), and heading texts repeat within a source (SRE has many "Conclusion"s), so the
id cannot be recovered from the text afterwards.

Each site is described by a profile: where its content sits, what is noise, and how a section is
anchored. Which profile a source uses is set in the catalog (`html_profile`). What counts as noise
was measured in phase 1.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from bs4 import BeautifulSoup, CData, NavigableString, Tag

from backend.ingestion.sections import Section

# Part of every HTML source's fingerprint: raising it re-indexes the HTML sources, and only them.
# 2 (2026-09-30): Wikipedia's combined "Notes and references" heading is dropped too; its 8 chunks of
# citations took places in q02's top 10.
# 3 (2026-11-04): a heading that borrows an earlier heading's anchor links by a text fragment to itself (decision 91.a;
# one heading in the free corpus, SRE's "DevOps or SRE?", whose citations landed on the section before it).
# 4 (2026-11-10, decision 155.a): the text reads as a browser shows it. Every element's edge used to read as a space, so a
# quote said "the Sortino ratio , which" and "( m − d ) ÷ σ ,": 1,230 such spaces in the four sources. Now an inline
# element (a link, an italic word) joins its neighbours as written; a stray </br> is a line break; a formula is its LaTeX in
# \( \), or \[ \] where it stands as a block, as a PDF page's reading writes it.
LOADER_VERSION = 4

HEADINGS = ('h1', 'h2', 'h3', 'h4')
# The elements whose text is collected. Where one sits inside another, only the outer one is
# read, so a paragraph inside a list item is not counted twice.
BLOCKS = ('p', 'li', 'dd', 'dt', 'pre', 'blockquote', 'figcaption', 'tr')
# Where a browser breaks the line, and the marks it sets apart: their edges separate words; every other element joins its
# neighbours as written. A superscript or subscript keeps its edge, so a footnote mark or an exponent never fuses with the
# word before it ("Sloss 6 Edited", "1.1 6", never "Sloss6" or "1.16"). Measured before the change (decision 155.a): the
# words of every section unchanged, 1,230 spaces gone beside punctuation, 15 joins of two words, each as a browser shows it
# ("/ˈɑːrbɪtrɑːʒ/", "1/Nth", "1,000P").
EDGES = frozenset({'address', 'article', 'aside', 'blockquote', 'br', 'caption', 'dd', 'details', 'div', 'dl', 'dt',
                   'figcaption', 'figure', 'footer', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hr', 'li', 'main', 'nav',
                   'ol', 'p', 'pre', 'section', 'sub', 'summary', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr',
                   'ul'})

_SPACE = re.compile(r'\s+')
_DISPLAYSTYLE = re.compile(r'^\{\\displaystyle\s*(.*)\}$', re.S)
_STRAY_BR = re.compile(r'</br\s*>', re.I)


@dataclass
class Profile:
    """How one site's HTML is read.

    Attributes:
        content: CSS selector of the element that holds the article; the whole body if None.
        noise: CSS selectors of elements removed before anything is read.
        drop_headings: Heading ids whose section is left out (reference and link lists).
        first_heading_is_title: Treat the first heading as the document title, not a section.
    """

    content: str | None
    noise: list[str] = field(default_factory=list)
    drop_headings: set[str] = field(default_factory=set)
    first_heading_is_title: bool = False


PROFILES = {
    # Wikipedia REST HTML: sections are <section> elements whose heading carries the id.
    'wikipedia': Profile(
        content=None,
        noise=['style', 'script', 'sup.mw-ref', '.mw-ref', '.navbox', '.sidebar', '.mw-editsection',
               'link', 'meta', '.hatnote'],
        drop_headings={'References', 'External_links', 'See_also', 'Further_reading', 'Notes',
                       'Notes_and_references', 'Bibliography', 'Citations', 'Sources', 'Footnotes'},
    ),
    # sre.google: the chapter sits in div#maia-main; headings are anchored by their <section id>.
    'sre': Profile(
        content='#maia-main',
        noise=['script', 'style', '.footer', 'nav'],
        first_heading_is_title=True,
    ),
    # Project Gutenberg: licence header and footer, the contents list, and the print edition's
    # page numbers (308 of them) that are interleaved with the text.
    'gutenberg': Profile(
        content=None,
        noise=['#pg-header', '#pg-footer', 'section.pg-boilerplate', 'span.pagenum', '.transnote',
               'script', 'style'],
        drop_headings={'CONTENTS', 'pg-header-heading'},
        first_heading_is_title=True,
    ),
    # martin.kleppmann.com: the post is div#content, without sub-headings.
    'kleppmann': Profile(
        content='#content',
        noise=['script', 'style', '#comments', '.comments'],
        first_heading_is_title=True,
    ),
}


def prepared(html: str) -> str:
    """A document as a browser reads it: a stray `</br>` is a line break (SRE has nine). html.parser drops it, and the words
    on either side would fuse ("Winkel" and "Edited by")."""
    return _STRAY_BR.sub('<br>', html)


def _collect(node: Tag, out: list[str]) -> None:
    for child in node.children:
        if isinstance(child, Tag):
            edge = child.name in EDGES
            if edge:
                out.append(' ')
            _collect(child, out)
            if edge:
                out.append(' ')
        elif type(child) in (NavigableString, CData):  # the strings get_text reads: no comment, doctype or declaration
            out.append(str(child))


def _words(element: Tag) -> str:
    out: list[str] = []
    _collect(element, out)
    return _SPACE.sub(' ', ''.join(out)).strip()


def text_of(element: Tag) -> str:
    """The readable text of an element as a browser shows it (`EDGES`); table rows as cells joined by ' | '."""
    if element.name == 'tr':
        cells = [_words(cell) for cell in element.find_all(['td', 'th'])]
        return ' | '.join(cell for cell in cells if cell)
    return _words(element)


def latex_of(math: Tag) -> str:
    """A MathML element's LaTeX: Wikipedia supplies it in `alttext`, wrapped in {\\displaystyle …}."""
    alt = math.get('alttext', '').strip()
    match = _DISPLAYSTYLE.match(alt)
    return match.group(1).strip() if match else alt


def delimited(latex: str, block: bool) -> str:
    """A formula as a PDF page's reading writes it: \\( … \\) in the line, \\[ … \\] standing as a block, set apart."""
    return f' \\[ {latex} \\] ' if block else f'\\({latex}\\)'


def replace_math(soup: BeautifulSoup) -> None:
    """Replace MathML with its LaTeX source.

    Read as plain text, a formula becomes a jumble of its glyphs. Wikipedia supplies each formula's
    LaTeX in `alttext`, e.g. S_{a}={\\frac {E[R_{a}-R_{b}]}{\\sigma _{a}}}.
    """
    for math in soup.find_all('math'):
        latex = latex_of(math)
        math.replace_with(delimited(latex, math.get('display') == 'block') if latex else ' ')


def anchor_of(heading: Tag) -> str | None:
    """A heading's link target: its own id, else the id of the section that encloses it."""
    if heading.get('id'):
        return heading['id']
    section = heading.find_parent('section')
    return section.get('id') if section is not None and section.get('id') else None


def borrows_anchor(heading: Tag) -> bool:
    """Whether a heading links by an id that belongs to an earlier heading: it has none of its own and is not the first
    heading of the section whose id it takes, so its link would land one section early (decision 91.a)."""
    if heading.get('id'):
        return False
    section = heading.find_parent('section')
    return section is not None and bool(section.get('id')) and section.find(HEADINGS) is not heading


def text_fragment(text: str) -> str:
    """A text directive that takes a browser to this text (URL fragment text directives, supported by current Chrome, Edge,
    Safari and Firefox). '-', '&' and ',' mean something inside a directive, so they are encoded with the rest."""
    return ':~:text=' + quote(text, safe='').replace('-', '%2D')


def drop_sections(root: Tag, heading_ids: set[str]) -> list[str]:
    """Remove the sections whose heading id is listed, with everything under them.

    Where the heading opens a <section> (Wikipedia), the whole element goes, subsections
    included. Otherwise (Gutenberg), the heading goes with its following siblings up to the next
    heading of the same level.

    Returns:
        The ids that were dropped, for the report.
    """
    dropped = []
    for heading in root.find_all(HEADINGS):
        # A heading inside a section removed earlier in this loop is already gone.
        if heading.decomposed or heading.get('id') not in heading_ids:
            continue
        dropped.append(heading['id'])
        container = heading.find_parent('section')
        if container is not None and container.find(HEADINGS) is heading:
            container.decompose()
            continue
        for sibling in list(heading.find_next_siblings()):
            if sibling.name == heading.name or (isinstance(sibling, Tag) and sibling.find(heading.name)):
                break
            sibling.decompose()
        heading.decompose()
    return dropped


def parse_sections(html: str, profile: Profile, source_id: str, base_url: str,
                   document_title: str) -> list[Section]:
    """Cut one HTML document into sections at its headings.

    Args:
        html: The document.
        profile: How this site is read.
        source_id: The catalog id.
        base_url: The address citations link to; the anchor is appended.
        document_title: The outermost heading (article or book title).

    Returns:
        The sections in document order, numbered from 0 within this document.
    """
    soup = BeautifulSoup(prepared(html), 'html.parser')
    for selector in profile.noise:
        for element in soup.select(selector):
            element.decompose()
    replace_math(soup)
    root = soup.select_one(profile.content) if profile.content else (soup.body or soup)
    if root is None:
        raise ValueError(f'{source_id}: content element {profile.content!r} not found')
    drop_sections(root, profile.drop_headings)

    title = document_title
    sections: list[Section] = []
    stack: list[tuple[int, str]] = []  # the open headings, (level, text)
    anchor, parts, borrowed = None, [], False
    first_heading = True

    def flush():
        if parts:
            path = [title] + [text for _, text in stack]
            url = f'{base_url}#{anchor}' if anchor else base_url
            if borrowed:  # the anchor is an earlier heading's: the text fragment takes the reader to this one
                url += text_fragment(path[-1])
            sections.append(Section(source_id, len(sections), path, '\n'.join(parts), url=url, anchor=anchor))

    for element in root.find_all(HEADINGS + BLOCKS):
        if element.name in HEADINGS:
            if first_heading and profile.first_heading_is_title:
                title = text_of(element) or title
                first_heading = False
                continue
            first_heading = False
            flush()
            level = int(element.name[1])
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, text_of(element)))
            anchor, parts, borrowed = anchor_of(element), [], borrows_anchor(element)
            continue
        if element.find_parent(BLOCKS) is not None:
            continue
        text = text_of(element)
        if text:
            parts.append(text)
    flush()
    return sections


def wikipedia_permalink(title: str, revision: int | None) -> str:
    base = 'https://en.wikipedia.org/w/index.php?title='
    return f'{base}{title}&oldid={revision}' if revision else f'https://en.wikipedia.org/wiki/{title}'


def load_html_sections(source: dict, manifest: dict, root: Path) -> list[Section]:
    """Load every file of one HTML source into sections, numbered across the whole source.

    Args:
        source: The catalog entry.
        manifest: The manifest's file records, keyed by path (for Wikipedia revisions).
        root: The folder the catalog's paths are relative to: `_data/` for the free sources (`DATA` in
            `backend.data_paths`).

    Returns:
        The sections of all files, in catalog order.
    """
    profile = PROFILES[source['html_profile']]
    sections: list[Section] = []
    for entry in source['files']:
        path = root / entry['path']
        html = path.read_text(encoding='utf-8')
        if source['html_profile'] == 'wikipedia':
            article = Path(entry['path']).stem
            revision = manifest.get(entry['path'], {}).get('wikipedia_revision')
            base_url, title = wikipedia_permalink(article, revision), article.replace('_', ' ')
        else:
            base_url, title = entry['url'], source['title']
        for section in parse_sections(html, profile, source['id'], base_url, title):
            section.ordinal = len(sections)
            sections.append(section)
    return sections
