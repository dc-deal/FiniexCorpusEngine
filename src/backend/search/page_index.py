"""Okapi BM25 over one document per printed page, ported unchanged from a predecessor search tool (decision 56.b).

The predecessor was calibrated over a private collection and found every work of it with a probe from its middle third,
nearly all at rank 1; its tokenizer, its page filters and its BM25 are kept exactly, so that measurement carries over. What changes
is how a query is scored: the index is built once and a query walks the postings of its terms, which gives the same numbers as
scoring every page and is what a server needs. `rank-bm25`, the course's BM25, was checked: its idf has another form and would
move the calibrated ranking. SQLite FTS5 with `bm25()` is the target that replaces this port once it holds the same gate.

A source is Markdown with `<!-- page N -->` markers, where a marker without a number (`<!-- page None -->`) counts by its
ordinal. The back index of a book, a page that is mostly an image, a table of contents or an index is left out.
"""

import collections
import math
import re
from dataclasses import dataclass
from pathlib import Path

# A word starts with a letter and may carry digits, underscores and an apostrophe: a technical corpus is full of
# identifiers (the predecessor measured MT5 327 times and dry_run 37 times, invisible to a letters-only pattern).
TOKEN = re.compile(r"[a-z][a-z0-9_']*")
POSSESSIVE = re.compile(r"'s$|'$")
# An image reference carries no text a reader wants, but its file name is derived from the work's slug, so indexing it would
# let a work win on words from its own title.
IMAGE_MARKUP = re.compile(r'!\[[^\]]*\]\([^)]*\)')
PAGE_MARKER = re.compile(r'<!-- page (\S+) -->')
ANY_HEADING = re.compile(r'^#{1,6} .*$', re.M)
INDEX_HEADINGS = {'index', 'subjectindex', 'generalindex', 'stichwortverzeichnis'}
INDEX_TAIL_SHARE = 0.66  # a heading "Index" this far into the file is the back index; one near the start is a mislabelled contents
K1 = 1.5
B = 0.75
MIN_CHARS = 200
SNIPPET_CHARS = 250  # where the predecessor's curve bent: 61 % of a query's words visible, the next 100 characters buy 3 points


def tokenize(text: str) -> list[str]:
    """The words the ranking sees: possessives reduced, an identifier followed by its parts."""
    words = []
    for raw in TOKEN.findall(text.lower()):
        word = POSSESSIVE.sub('', raw)
        if len(word) < 2:
            continue
        words.append(word)
        if '_' in word:
            words.extend(part for part in word.split('_') if len(part) >= 2)
    return words


def is_structural(text: str) -> bool:
    """A page that matches on words but holds no prose: only an image, a table of contents, an index."""
    return structural_why(text) is not None


def structural_why(text: str) -> str | None:
    """Why the ranking leaves a page out (`is_structural`), in words a view can show; None for a page it ranks. One rule
    for the search and the views (asked by line 2 for a page's coverage ladder, 20 Nov)."""
    stripped = re.sub(r'!\[\]\([^)]*\)', '', text)
    if not stripped.strip():
        return 'no text'
    if len(stripped.strip()) < MIN_CHARS:
        return f'too short: under {MIN_CHARS} characters'
    words = TOKEN.findall(stripped.lower())
    if not words:
        return 'no words'
    if len(re.findall(r'\b\d{1,4}\b', stripped)) > len(words) / 3:
        return 'mostly figures'
    if stripped.count('|---') > 2:
        return 'a table'
    return None


def back_index_start(text: str) -> int | None:
    """Where a book's back index begins, so its entries stop competing with its prose; None where it has none."""
    for head in ANY_HEADING.finditer(text):
        if re.sub(r'[#*_\s]', '', head.group(0)).lower() not in INDEX_HEADINGS:
            continue
        if head.start() >= INDEX_TAIL_SHARE * len(text):
            return head.start()
    return None


@dataclass(frozen=True)
class Page:
    work: str
    page: str  # the page's label as its source names it: the marker's number, or its ordinal where the marker has none
    line: int  # the first line of what is shown, measured from the marker's position, never accumulated
    text: str
    path: str
    pdf: str | None = None  # the PDF page, only where it is known: a numbered marker, a page reading; never a guess
    section: str | None = None  # the heading in effect where the page begins
    line_end: int | None = None  # the last line of the page in its file
    knowledge_base: str = ''
    route: str = ''  # how this page's text was made: a vision reading, a text layer and why, legacy Markdown
    printed: str | None = None  # the page number as printed, where a reading saw one
    reading_key: str | None = None
    # The words the ranking sees, where they differ from the text a hit quotes: a free PDF page is quoted with its formulas
    # in LaTeX, as the chat quotes it, and ranked without the LaTeX commands (decision 93.a). None: the text itself.
    index_text: str | None = None
    # False for a page the ranking leaves out (`is_structural`: short, mostly digits, a table) that `open_page` still opens:
    # the chat's passages come from the whole text, so a source it cites must open (found on 2026-11-05: 44 HTML sections).
    searchable: bool = True

    @property
    def words(self) -> str:
        return self.text if self.index_text is None else self.index_text


LATEX_COMMAND = re.compile(r'\\[A-Za-z]+')


def without_latex(text: str) -> str:
    r"""A quoted text as the ranking reads it: LaTeX commands are markup, never words (the review of 2026-11-03 found `frac` in
    the index), so `\frac{a}{b}` reads as `a b`."""
    return LATEX_COMMAND.sub(' ', text)


SOURCE_LINE = re.compile(r'^> Quelle:\s*(.+?)\s*$', re.M)  # the predecessor's header names the converted source file


def heading_text(line: str) -> str:
    return re.sub(r'[*_`]', '', line.lstrip('#')).strip()


def pages_of(text: str, work: str, path: str, numbers_are_pdf_pages: bool = True) -> list[Page]:
    """One page per marker, the back index and structural pages left out. A numbered marker is the PDF page (49 of the
    predecessor's works); a marker without a number, or any marker of a work converted from an EPUB, gives no PDF page."""
    pages = []
    index_start = back_index_start(text)
    markers = list(PAGE_MARKER.finditer(text))
    headings = [(head.start(), heading_text(head.group(0))) for head in ANY_HEADING.finditer(text)]
    for ordinal, marker in enumerate(markers, start=1):
        if index_start is not None and marker.start() >= index_start:
            continue
        end = markers[ordinal].start() if ordinal < len(markers) else len(text)
        body = text[marker.end():min(end, index_start) if index_start is not None else end]
        page = marker.group(1) if marker.group(1) != 'None' else str(ordinal)
        if is_structural(body):
            continue
        shown = IMAGE_MARKUP.sub(' ', body).strip()
        opening = shown.split('\n', 1)[0].strip()[:40]
        offset = body.find(opening) if opening else -1
        if offset < 0:
            offset = len(body) - len(body.lstrip('\n'))
        first_line = text.count('\n', 0, marker.end() + offset) + 1
        body_end = marker.end() + len(body.rstrip())  # the page's last line of content, not the next marker's line
        in_effect = [title for position, title in headings if position < marker.end() + offset + len(opening) and title]
        pdf = page if numbers_are_pdf_pages and marker.group(1) != 'None' else None
        pages.append(Page(work, page, first_line, shown, path, pdf=pdf, section=in_effect[-1] if in_effect else None,
                          line_end=text.count('\n', 0, body_end) + 1))
    return pages


def load_works(folder: Path, keys: dict) -> list[Page]:
    """Every Markdown work in a folder, named by its citation key where one is known (`keys`: key -> file stem)."""
    by_slug = {slug: key for key, slug in keys.items()}
    pages = []
    for path in sorted(folder.glob('*.md')):
        text = path.read_text(encoding='utf-8')
        source = SOURCE_LINE.search(text[:2000])
        from_pdf = not (source and source.group(1).lower().endswith('.epub'))
        pages += pages_of(text, by_slug.get(path.stem, path.stem), path.as_posix(), numbers_are_pdf_pages=from_pdf)
    return pages


class PageIndex:
    """BM25 over a fixed list of pages, built once; a query scores only the pages that hold one of its terms."""

    def __init__(self, pages: list[Page]):
        self.pages = pages
        documents = [tokenize(page.words) for page in pages]
        self.lengths = [len(words) for words in documents]
        self.average_length = sum(self.lengths) / len(documents) if documents else 0.0
        self.postings = collections.defaultdict(list)
        for number, words in enumerate(documents):
            for term, frequency in collections.Counter(words).items():
                self.postings[term].append((number, frequency))
        total = len(documents)
        self.idf = {term: math.log(1 + (total - len(hits) + 0.5) / (len(hits) + 0.5)) for term, hits in self.postings.items()}

    def scored(self, query: str) -> list[tuple[float, int]]:
        """Every page holding a query term, with its score, best first; a number indexes `pages`. A repeated query term
        counts once per repetition, as in the predecessor."""
        scores = collections.defaultdict(float)
        for term in tokenize(query):
            for number, frequency in self.postings.get(term, ()):
                norm = K1 * (1 - B + B * self.lengths[number] / self.average_length)
                scores[number] += self.idf[term] * frequency * (K1 + 1) / (frequency + norm)
        return sorted(((score, number) for number, score in scores.items() if score > 0), reverse=True)

    def holding_every_term(self, query: str) -> set[int]:
        """The pages that hold every word of the query: the honest negative answer, since a page holding one of them scores."""
        terms = set(tokenize(query))
        if not terms:
            return set()
        return set.intersection(*({number for number, _ in self.postings.get(term, ())} for term in terms))

    def search(self, query: str, hits: int = 6, accept=None) -> list[tuple[float, Page]]:
        """The best pages, best first. `accept` filters pages after scoring, so a filtered search ranks on the statistics of
        the whole index (decision 71.a)."""
        ranked = self.scored(query)
        if accept is not None:
            ranked = [(score, number) for score, number in ranked if accept(self.pages[number])]
        return [(score, self.pages[number]) for score, number in ranked[:hits]]


def snippet(text: str, query: str, width: int = SNIPPET_CHARS) -> str:
    """The part of the page around the longest query word present: the first is often a function word."""
    flat = ' '.join(text.split())
    lowered, best = flat.lower(), 0
    for term in sorted(set(tokenize(query)), key=len, reverse=True):
        found = lowered.find(term)
        if found > 0:
            best = max(0, found - 40)
            break
    return flat[best:best + width]


def coverage(text: str, query: str) -> tuple[list[str], list[str]]:
    """Query terms the page holds and those it lacks: shown to the caller, never a gate (it does not separate good hits)."""
    terms = list(dict.fromkeys(tokenize(query)))
    present = set(tokenize(text))
    return [term for term in terms if term in present], [term for term in terms if term not in present]
