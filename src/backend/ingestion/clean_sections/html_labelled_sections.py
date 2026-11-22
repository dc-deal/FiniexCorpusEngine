"""HTML whose structure is its paragraph labels → cleaned sections, one per labelled heading, each with a link to its place.

A rule text published as a web page (a regulator's or a self-regulatory body's rulebook) often carries no h1 to h4: its
structure is the labels of its paragraphs, (a), (1), (A), (i), set in bold where a paragraph has a title, and its text sits
in nested blocks rather than in paragraphs. `html_sections` cuts at h1 to h4 and reads p, li and tr, so on such a page it
keeps one section and about a quarter of the words (measured on the first one, 22 Nov 2026). This loader
reads every text the content element holds, as a browser breaks it into lines, and follows the labels:

- every paragraph that starts with a label places it by its kind (a lower-case letter, a number, an upper-case letter, a
  lower-case roman numeral, a supplementary number such as `.01`): a kind already open closes everything below it, a kind
  not yet open goes one level deeper. A lone `(i)`, `(v)` or `(x)` is the letter where the letter before it is open, else
  the numeral, as rulebooks number;
- a bold run that opens its block is a heading and opens a section: a label with its title, a run-in title that is no
  label (nested like a kind of its own), or, standing alone in its block, a part of the text (a rule's "Supplementary
  Material"), which closes every open heading, its decoration (bullets, dashes, a colon) trimmed;
- a paragraph whose label is not bold opens a section where it stands at the level of the section being read or above
  (a sibling of its heading: "(B)" after a bold "(A) Definitions"), named by its label; one deeper stays in its section,
  so a list of definitions stays one section;
- a table is a section of its own, under the heading in effect, its rows as cells joined by ' | ', and the text after it
  continues that heading in a new section, so no section grows by a table's length.

Where a page names no anchor for its paragraphs, a section links to the page with a text directive (`#:~:text=`) to its
heading, or to its first words where its heading is a bare label that repeats on the page. Which element holds the text
is the source's own, named in its catalog entry, never here. Checked before building: LangChain's `HTMLHeaderTextSplitter`
and `HTMLSectionSplitter` cut at h1 to h6 only; Unstructured's HTML partitioner types elements by tag and would need the
same label rules on top, with its heavy install.
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup, CData, NavigableString, Tag

from backend.ingestion.clean_sections.html_sections import EDGES, prepared, replace_math, text_fragment, text_of
from backend.ingestion.sections import Section

# Part of every labelled source's fingerprint: raising it re-reads these sources, and only them.
LOADER_VERSION = 1

NOISE = ('script', 'style', 'button', 'select', 'nav', 'noscript')  # never text of a rule, whatever the site
BOLD = ('strong', 'b')
TABLE = 'table'
# Where a browser breaks the line: a paragraph ends there. A line break, a superscript or a subscript only keep their edge.
BREAKS = EDGES - {'br', 'sup', 'sub', 'table', 'tbody', 'thead', 'tfoot', 'tr', 'td', 'th', 'caption'}
INLINE_EDGES = frozenset({'br', 'sup', 'sub'})

LABEL = re.compile(r'^\((?P<roman>[ivxlc]{2,})\)|^\((?P<letter>[a-z])\)|^\((?P<number>\d{1,3})\)|^\((?P<upper>[A-Z]{1,2})\)'
                   r'|^(?P<supplement>\.\d{2})(?!\d)')
AMBIGUOUS = {'i': 'h', 'v': 'u', 'x': 'w'}  # a lone roman numeral that is also a letter, and the letter before it
PART = 'part'  # a heading standing alone that is no label: it closes every open heading
TITLE = 'title'  # a run-in heading that is no label
FRAGMENT_WORDS = 8  # the first words a link points at where the heading is a bare label
_SPACE = re.compile(r'\s+')
_DECORATION = re.compile(r'^[\W_]+|[\W_]+$')


def label_kind(text: str, open_labels: list[tuple[str, str]]) -> str | None:
    """The kind of label a text starts with, None where it starts with none. A lone `(i)`, `(v)` or `(x)` is the letter
    where the letter before it is the open letter's, else the roman numeral."""
    match = LABEL.match(text)
    if match is None:
        return None
    kind = match.lastgroup
    if kind == 'letter' and match.group('letter') in AMBIGUOUS:
        open_letter = next((label for open_kind, label in reversed(open_labels) if open_kind == 'letter'), None)
        return 'letter' if open_letter == AMBIGUOUS[match.group('letter')] else 'roman'
    return kind


def opened(open_labels: list[tuple[str, str]], kind: str, label: str) -> list[tuple[str, str]]:
    """The open levels, (kind, label) outermost first, once a label of this kind opens: a kind already open closes with all
    below it, a kind not yet open goes one level deeper, a part closes them all."""
    if kind == PART:
        return [(PART, label)]
    for index, (open_kind, _) in enumerate(open_labels):
        if open_kind == kind:
            return [*open_labels[:index], (kind, label)]
    return [*open_labels, (kind, label)]


def label_of(text: str) -> str:
    """A labelled text's label without its brackets ('e' of '(e) Exceptions'); the text itself where it has none."""
    match = LABEL.match(text)
    return next((group for group in match.groups() if group), text) if match else text


class _Reader:
    """Walks the content element once, in document order, and collects its sections."""

    def __init__(self, source_id: str, base_url: str, document_title: str) -> None:
        self.source_id, self.base_url, self.document_title = source_id, base_url, document_title
        self.sections: list[Section] = []
        self.open_labels: list[tuple[str, str]] = []  # (kind, label) per level, outermost first
        self.titles: list[str] = []  # each open level's name: a heading as printed, or a bare label such as '(B)'
        self.depth = 1  # the level of the section being read: a label at it or above opens a new one
        self.fragment: str | None = None  # the text a link to this section points at; None: its first words
        self.paragraphs: list[str] = []  # the section being read
        self.line: list[str] = []  # the paragraph being read

    def text_so_far(self) -> str:
        return _SPACE.sub(' ', ''.join(self.line)).strip()

    def end_paragraph(self) -> None:
        text = self.text_so_far()
        if text:
            self.paragraphs.append(text)
        self.line = []

    def end_section(self) -> None:
        self.end_paragraph()
        if not self.paragraphs:
            return
        path = self.titles[:self.depth]
        url = self.base_url
        if path:  # the page names no anchor for a paragraph: a text directive takes the reader to it
            url += '#' + text_fragment(self.fragment or ' '.join(self.paragraphs[0].split()[:FRAGMENT_WORDS]))
        self.sections.append(Section(self.source_id, len(self.sections), [self.document_title, *path],
                                     '\n'.join(self.paragraphs), url=url))
        self.paragraphs = []

    def place(self, kind: str, label: str, title: str) -> None:
        self.open_labels = opened(self.open_labels, kind, label)
        self.titles = [*self.titles[:len(self.open_labels) - 1], title]

    def heading(self, kind: str, heading: str) -> None:
        self.end_section()
        self.place(kind, heading if kind in (PART, TITLE) else label_of(heading), heading)
        self.depth, self.fragment = len(self.open_labels), heading

    def labelled(self, text: str) -> None:
        """A paragraph that starts with a label that is not bold: placed, and a section of its own where it stands at the
        level of the section being read or above."""
        kind = label_kind(text, self.open_labels)
        if kind is None:
            return
        label = LABEL.match(text).group(0)
        if len(opened(self.open_labels, kind, label_of(label))) <= self.depth:
            self.end_section()
            self.place(kind, label_of(label), label)
            self.depth, self.fragment = len(self.open_labels), None  # a bare label repeats on the page: link its first words
        else:
            self.place(kind, label_of(label), label)

    def table(self, table: Tag) -> None:
        self.end_section()
        for row in table.find_all('tr'):
            text = text_of(row)
            if text:
                self.paragraphs.append(text)
        self.end_section()

    def bold(self, run: Tag, block: Tag) -> bool:
        """Open a heading where this bold run opens its block; False where it is only emphasis."""
        if self.text_so_far():
            return False
        heading = _SPACE.sub(' ', run.get_text(' ')).strip()
        if not heading:
            return False
        kind = label_kind(heading, self.open_labels)
        if kind is None:
            alone = _SPACE.sub(' ', block.get_text(' ')).strip() == heading
            kind, heading = (PART, _DECORATION.sub('', heading)) if alone else (TITLE, heading)
            if not heading:
                return False
        self.heading(kind, heading)
        return True

    def walk(self, node: Tag, block: Tag) -> None:
        for child in node.children:
            if isinstance(child, Tag):
                if child.name == TABLE:
                    self.table(child)
                elif child.name in BREAKS:
                    self.end_paragraph()
                    self.walk(child, child)
                    self.end_paragraph()
                elif child.name in BOLD and self.bold(child, block):
                    continue
                else:
                    edge = child.name in INLINE_EDGES
                    if edge:
                        self.line.append(' ')
                    self.walk(child, block)
                    if edge:
                        self.line.append(' ')
            elif type(child) in (NavigableString, CData):  # the strings get_text reads: no comment, doctype or declaration
                if not self.text_so_far() and child.strip():
                    self.labelled(child.strip())
                self.line.append(str(child))


def parse_labelled_sections(html: str, content: str, source_id: str, base_url: str, document_title: str,
                            noise: tuple[str, ...] = ()) -> list[Section]:
    """Cut one HTML document into sections at its labelled headings.

    Args:
        html: The document.
        content: CSS selector of the element that holds the text.
        source_id: The catalog id.
        base_url: The address citations link to; a text directive to the section is appended.
        document_title: The outermost heading: the rule's or the document's title.
        noise: CSS selectors of elements removed before anything is read, beside `NOISE`.

    Returns:
        The sections in document order, numbered from 0.
    """
    soup = BeautifulSoup(prepared(html), 'html.parser')
    for selector in (*NOISE, *noise):
        for element in soup.select(selector):
            element.decompose()
    replace_math(soup)
    root = soup.select_one(content)
    if root is None:
        raise ValueError(f'{source_id}: content element {content!r} not found')
    reader = _Reader(source_id, base_url, document_title)
    reader.walk(root, root)
    reader.end_section()
    return reader.sections


def load_labelled_sections(entry: dict, folder: Path) -> list[Section]:
    """Load one HTML source a catalog entry describes: its `file` in `folder`, its `url`, `title` and `id`, and under
    `labelled_sections` the `content` selector and any `noise` selectors.

    Args:
        entry: The catalog entry.
        folder: The folder that holds the file.

    Returns:
        The sections in document order.
    """
    layout = entry['labelled_sections']
    html = (folder / entry['file']).read_text(encoding='utf-8')
    return parse_labelled_sections(html, layout['content'], entry['id'], entry['url'], entry['title'],
                                   tuple(layout.get('noise', ())))
