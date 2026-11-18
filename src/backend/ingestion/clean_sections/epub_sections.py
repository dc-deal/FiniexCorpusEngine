"""EPUB → sections, one per heading, in the book's reading order (decision 123.a, the EPUB route; the operator's P1.a, 18 Nov).

An EPUB is born-digital XHTML in a zip, so it needs no reader, no judge and no API call: the route is deterministic, and a fix
re-runs it whole under a new `LOADER_VERSION` (decision 54.a). The container names the package (OPF); the package names the
reading order (the spine) and every file; the navigation document (EPUB 3's nav, or EPUB 2's NCX) names each chapter. Each
document of the spine is cut at its headings by the HTML route's own walker (`html_sections.parse_sections`), so both
formats read text the same way.

An image stays where it stands, as the mark `IMAGE_MARK`, and is listed with its file and alt text in its section. In several
of the books the formulas are images whose alt text says nothing (18 Nov: one book with 1,506 standalone images, another
with 667 inline in the text, alt texts of five or six characters), so a route of text alone would lose them without a word. A quote shows the
gap; the search server leaves the mark out of the words its ranking sees (`Page.index_text`), so it never ranks by "image".

Checked first (framework first): EbookLib reads the same container, package and spine; it is not taken because the standard
library's zipfile and ElementTree do this in a few lines without a new dependency, and the text comes through the HTML
route's walker either way. Pandoc would need a system program, which the project does not require.
"""

import posixpath
import xml.etree.ElementTree as ElementTree
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from bs4 import BeautifulSoup

from backend.ingestion.clean_sections import html_sections
from backend.ingestion.sections import Section

LOADER_VERSION = 1
IMAGE_MARK = '⟦image⟧'
DOCUMENT_TYPES = ('application/xhtml+xml', 'text/html')
NAMESPACES = {'container': 'urn:oasis:names:tc:opendocument:xmlns:container', 'opf': 'http://www.idpf.org/2007/opf',
              'dc': 'http://purl.org/dc/elements/1.1/', 'ncx': 'http://www.daisy.org/z3986/2005/ncx/'}
# The whole body is the content; a chapter's first heading is its title, which the navigation's label stands in for where a
# document has none.
PROFILE = html_sections.Profile(content=None, noise=['script', 'style', 'nav'], first_heading_is_title=True)


@dataclass
class Image:
    """One image of a section, in the order it stands: its file inside the EPUB, its alt text, and whether it stands inside a
    line of text (an inline formula, most often) or on its own."""
    href: str
    alt: str
    inline: bool


@dataclass
class EpubSection:
    section: Section
    images: list[Image] = field(default_factory=list)


@dataclass
class Book:
    title: str
    documents: list[tuple[str, str]]  # the spine's documents in reading order: (path inside the zip, its chapter's label)


def _href(base: str, href: str) -> str:
    """A path inside the zip, from a reference relative to the document `base` lies in; without its fragment."""
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), unquote(href.split('#', 1)[0])))


def _nav_labels(archive: zipfile.ZipFile, nav: str) -> dict[str, str]:
    soup = BeautifulSoup(archive.read(nav), 'html.parser')
    toc = next((element for element in soup.find_all('nav') if 'toc' in (element.get('epub:type') or '')), None) or soup
    labels = {}
    for link in toc.find_all('a', href=True):
        labels.setdefault(_href(nav, link['href']), ' '.join(link.get_text(' ').split()))
    return labels


def _ncx_labels(archive: zipfile.ZipFile, ncx: str) -> dict[str, str]:
    labels = {}
    for point in ElementTree.fromstring(archive.read(ncx)).iter(f"{{{NAMESPACES['ncx']}}}navPoint"):
        content = point.find('ncx:content', NAMESPACES)
        text = point.findtext('ncx:navLabel/ncx:text', default='', namespaces=NAMESPACES)
        if content is not None and content.get('src'):
            labels.setdefault(_href(ncx, content.get('src')), ' '.join(text.split()))
    return labels


def read_book(archive: zipfile.ZipFile) -> Book:
    """The book's title and its spine's documents in reading order, each with its chapter's label where the navigation has one."""
    container = ElementTree.fromstring(archive.read('META-INF/container.xml'))
    package_path = container.find('.//container:rootfile', NAMESPACES).get('full-path')
    package = ElementTree.fromstring(archive.read(package_path))
    title = ' '.join((package.findtext('.//dc:title', default='', namespaces=NAMESPACES) or '').split())
    items, nav, ncx = {}, None, None
    for item in package.findall('.//opf:manifest/opf:item', NAMESPACES):
        href = _href(package_path, item.get('href'))
        items[item.get('id')] = (href, item.get('media-type'))
        if 'nav' in (item.get('properties') or '').split():
            nav = href
        if item.get('media-type') == 'application/x-dtbncx+xml':
            ncx = href
    labels = _nav_labels(archive, nav) if nav else _ncx_labels(archive, ncx) if ncx else {}
    documents = []
    for reference in package.findall('.//opf:spine/opf:itemref', NAMESPACES):
        href, media = items.get(reference.get('idref'), (None, None))
        if href and media in DOCUMENT_TYPES and href != nav and reference.get('linear', 'yes') != 'no':
            documents.append((href, labels.get(href, '')))
    return Book(title, documents)


def marked(html: bytes, document: str) -> tuple[str, list[Image]]:
    """The document with each image replaced by `IMAGE_MARK` where it stands, and the images in that order. An image on its
    own becomes a paragraph of its own, so the walker, which reads paragraphs and headings, keeps its place."""
    soup = BeautifulSoup(html, 'html.parser')
    # Some publishers set every paragraph as a <div class="tx"> (one book: 3,081 of them, none a <p>), which the walker, reading
    # paragraphs and headings, would skip: a div that holds text and no block of its own is read as the paragraph it is.
    for division in soup.find_all('div'):
        if division.find(['div', *html_sections.BLOCKS, *html_sections.HEADINGS]) is None and division.get_text(strip=True):
            division.name = 'p'
    images = []
    for image in soup.find_all('img'):
        holder = image.find_parent(html_sections.BLOCKS)
        inline = holder is not None and bool(holder.get_text(strip=True))
        images.append(Image(_href(document, image.get('src') or ''), ' '.join((image.get('alt') or '').split()), inline))
        if holder is not None:
            image.replace_with(f' {IMAGE_MARK} ')
        else:
            paragraph = soup.new_tag('p')
            paragraph.string = IMAGE_MARK
            image.replace_with(paragraph)
    return str(soup), images


def load_epub_sections(path: Path, source_id: str) -> list[EpubSection]:
    """Every document of the spine cut into sections at its headings, numbered across the book, each with its images.

    Args:
        path: The EPUB.
        source_id: The work's key, which the sections carry.

    Returns:
        The sections in reading order. A section's url is `<file name>/<document>#<anchor>`: where it stands in the EPUB.
    """
    out: list[EpubSection] = []
    with zipfile.ZipFile(path) as archive:
        book = read_book(archive)
        for document, label in book.documents:
            html, images = marked(archive.read(document), document)
            for section in html_sections.parse_sections(html, PROFILE, source_id, f'{path.name}/{document}', label or book.title):
                count = section.text.count(IMAGE_MARK)
                section.ordinal = len(out)
                out.append(EpubSection(section, images[:count]))
                images = images[count:]
    return out
