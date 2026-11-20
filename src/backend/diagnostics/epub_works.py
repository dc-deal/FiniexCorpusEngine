"""The licensed EPUB works (decision 123.a, the operator's P1.a, 18 Nov), shown as the free HTML works are: an outline by
heading and each section's text, with its images where its marks stand.

The core cuts an EPUB into sections (`epub_sections.load_epub_sections`), and the librarian serves them as pages `s1`, `s2`, …
with the route `epub, parsed by section` (`search_server.epub_pages`); this module reads them the same way, so a section's
label here is the one a search hit names. The marks the provenance list records are stripped from every text, as the
librarian strips them. An image is read from the EPUB's own zip by its path inside it, never extracted.

Only the licensed knowledge base has EPUB works, and only a licensed route reaches this module: an app started with
--public-only answers them 404 before anything here runs (81.a). Cutting an EPUB takes up to about 5 s, so each one is cut
once and kept while its file is unchanged; the app's warm-up cuts them all ahead (`warm`).
"""

import mimetypes
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from backend.diagnostics.html_works import HtmlNode, outline_of
from backend.diagnostics.ladder_types import PageLadder
from backend.diagnostics.readings import KnowledgeBase
from backend.ingestion.clean_sections.epub_sections import IMAGE_MARK, load_epub_sections
from backend.search import search_server

ROUTE = search_server.EPUB_ROUTE


class EpubImage(BaseModel):
    """One image where its mark stands: its path inside the EPUB, its alt text, and whether it stands inside a line of text (an
    inline formula, most often) or on its own."""

    href: str
    alt: str
    inline: bool


class EpubPart(BaseModel):
    """A section's text in its order: a run of text, or an image where its mark stood."""

    kind: Literal['text', 'image']
    text: str | None = None
    image: EpubImage | None = None


class EpubSectionRow(BaseModel):
    label: str
    heading_path: str
    characters: int  # the section's text without its image marks
    images: int


class EpubWork(BaseModel):
    knowledge_base: KnowledgeBase = 'licensed'
    source_id: str  # the librarian's work key: the legacy work's key where the EPUB serves it, else the file's stem
    title: str
    file: str
    licence: str | None = None  # the local licensed catalog's, as the sources list shows it; None where it lists no entry
    route: str = ROUTE
    sections: int = 0
    images: int = 0
    outline: list[HtmlNode] = []
    rows: list[EpubSectionRow] = []


class EpubSection(BaseModel):
    knowledge_base: KnowledgeBase = 'licensed'
    source_id: str
    work_title: str
    label: str
    heading_path: str
    place: str | None  # where it stands in the EPUB, `<document>#<anchor>`
    parts: list[EpubPart]
    previous: str | None
    next: str | None
    # the section's own coverage ladder (V2.a), which the app sets from the search; None where it has not
    ladder: PageLadder | None = None


@dataclass
class Cut:
    """One section as the librarian serves it: its label, heading path, place, text with its marks, and its images."""

    label: str
    heading_path: str
    place: str | None
    text: str
    images: list[EpubImage]


_cut: dict[tuple[str, int], list[Cut]] = {}
_lock = threading.Lock()
_warming = threading.Lock()


def epubs() -> dict[str, Path]:
    """The licensed EPUB works, by the librarian's key: never a stand-in (`search_server.licensed_epubs`)."""
    return search_server.licensed_epubs(search_server.legacy_keys())


def label_of(ordinal: int) -> str:
    return f's{ordinal + 1}'


def cut(key: str, path: Path) -> list[Cut]:
    """The EPUB's sections as the librarian serves them, in reading order: a section left empty once the provenance marks
    are stripped is not served there, so not here either. Kept while the file is unchanged."""
    stamp = (str(path), path.stat().st_mtime_ns)
    with _lock:
        if stamp in _cut:
            return _cut[stamp]
    marks = search_server.stamps()
    sections = []
    for item in load_epub_sections(path, key):
        text = search_server.strip_stamps(item.section.text, marks)
        if not text.strip():
            continue
        place = item.section.url.split('/', 1)[1] if item.section.url and '/' in item.section.url else item.section.url
        sections.append(Cut(label_of(item.section.ordinal), ' > '.join(item.section.heading_path), place, text,
                            [EpubImage(href=image.href, alt=image.alt, inline=image.inline) for image in item.images]))
    with _lock:
        _cut[stamp] = sections
    return sections


def counted(path: Path) -> int | None:
    """The sections of an EPUB already cut, None while it is not: the sources list never waits for a cut."""
    try:
        stamp = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return None
    with _lock:
        found = _cut.get(stamp)
    return len(found) if found is not None else None


def warm(works: dict[str, Path] | None = None) -> None:
    """Cut every EPUB ahead, one after another, so the sources list counts their sections; one warm-up at a time."""
    if not _warming.acquire(blocking=False):
        return
    try:
        for key, path in (works if works is not None else epubs()).items():
            cut(key, path)
    finally:
        _warming.release()


def warm_in_background() -> None:
    threading.Thread(target=warm, name='warm-epubs', daemon=True).start()


def work(key: str, title: str) -> EpubWork | None:
    """One EPUB work whole: its outline by heading and its sections in reading order. None where there is no such work."""
    path = epubs().get(key)
    if path is None:
        return None
    sections = cut(key, path)
    ordinals = [int(section.label[1:]) - 1 for section in sections]
    outline = outline_of(title, [(ordinal, section.heading_path or title) for ordinal, section in zip(ordinals, sections)], {})
    return EpubWork(source_id=key, title=title, file=path.name, sections=len(sections),
                    images=sum(len(section.images) for section in sections), outline=outline,
                    rows=[EpubSectionRow(label=section.label, heading_path=section.heading_path,
                                         characters=len(section.text.replace(IMAGE_MARK, '')), images=len(section.images))
                          for section in sections])


def parts_of(text: str, images: list[EpubImage]) -> list[EpubPart]:
    """The text in runs, each image where its mark stands: the n-th mark is the n-th image. A mark without an image (a file
    the core could not name) stays out rather than stand as a broken image."""
    parts: list[EpubPart] = []
    runs = text.split(IMAGE_MARK)
    for at, run in enumerate(runs):
        if run:
            parts.append(EpubPart(kind='text', text=run))
        if at < len(runs) - 1 and at < len(images):
            parts.append(EpubPart(kind='image', image=images[at]))
    return parts


def section(key: str, label: str, title: str) -> EpubSection | None:
    """One section of an EPUB work by its label, as the librarian names it; None where there is no such work or section."""
    path = epubs().get(key)
    if path is None:
        return None
    sections = cut(key, path)
    at = next((at for at, one in enumerate(sections) if one.label == label), None)
    if at is None:
        return None
    one = sections[at]
    return EpubSection(source_id=key, work_title=title, label=one.label, heading_path=one.heading_path, place=one.place,
                       parts=parts_of(one.text, one.images), previous=sections[at - 1].label if at > 0 else None,
                       next=sections[at + 1].label if at + 1 < len(sections) else None)


def image(key: str, href: str) -> tuple[bytes, str] | None:
    """An image of an EPUB work by its path inside the EPUB, with its content type from its extension; None where the work
    has no such image. Only a path one of its sections names is read, never any other file of the zip."""
    path = epubs().get(key)
    if path is None or not any(one.href == href for section in cut(key, path) for one in section.images):
        return None
    with zipfile.ZipFile(path) as archive:
        try:
            data = archive.read(href)
        except KeyError:
            return None
    return data, mimetypes.guess_type(href)[0] or 'application/octet-stream'
