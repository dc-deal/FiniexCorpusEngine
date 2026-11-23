"""What the diagnostics UI shows about the sources, read from the core's data and never written.

Every model here is the response shape of a route in `app.py`. It reaches the UI's TypeScript through
the OpenAPI schema (`python -m backend.diagnostics.build`), never by hand.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from typing import Literal

from backend.diagnostics.ladder_types import Ladder
from backend.diagnostics.work_editions import Editions
from backend.diagnostics.readings import FREE_CATALOG, KnowledgeBase, Series, WorkReadings

ROOT = Path(__file__).resolve().parents[3]
CATALOG = FREE_CATALOG
# What the sources view says, in place of page counts, of a licensed catalog entry the export has no pages of (O1.a): the
# view's own state until the core reads it, an EPUB by its sections as the free HTML works are (123.a), which then replace it
NOT_READ = 'not read page by page'
# the structure facet's other two words (Y1.a): a work read page by page, and one cut by its headings
READ_PAGES = 'read page by page'
SECTIONS = 'sections by heading'
# What it says of a licensed EPUB whose sections are not counted yet: cutting all of them takes about 20 s, and the list
# never waits for it (123.a)
EPUB_COUNTING = 'sections by heading · being counted, here in a moment'


class CatalogSource(BaseModel):
    """A source as the catalog must list it: every field the sources view shows. A gap is refused, not shown empty."""

    id: str
    title: str
    authors: str
    publisher: str
    # None for the Wikipedia set: articles that change all the time have no year of publication
    year: int | None
    licence: str
    format: str
    shelf: str
    # the series the entry is a part of, in the licensed catalog's shape (line 1, 22 Nov): the free catalog names some too
    series: Series | None = None


class CodePart(BaseModel):
    """A book's companion code (#12), folded into the book's row as a kept edition is into the served one (E1.a): its own
    work in the search, its files opening in the code view."""

    key: str  # its work key, which its view and the search name it by
    title: str
    code_language: str | None = None
    files: int | None = None  # the files the shelf counts as served; None where the shelf has no row of it here
    said: str  # "companion code: EasyLanguage, 355 files"


class StandIn(BaseModel):
    """A stand-in file beside a work, which the librarian does not serve as long as the work's own text stands (the shelf's
    `stand_in_of`, line 1, 20 Nov): folded into its work's row, so a work stands once, the file named in its card."""

    id: str  # the file's own id, which its page list takes where it has one
    file: str | None
    said: str  # "stand-in file beside it: <file>, not served: <why>"
    held: str | None = None  # why the provenance list holds the file back, where it does
    page_list: bool = False  # its pages open as a list here (a PDF), so the card links them


class Work(BaseModel):
    """One work as the sources view lists it. A licensed work takes its fields from the local licensed catalog where this
    machine has one (N1.a); without it, its export gives an id and a title, the PDF's stem as on the search server, and the
    catalog's fields stay empty."""

    knowledge_base: KnowledgeBase
    id: str
    title: str
    authors: str | None = None
    publisher: str | None = None
    year: int | None = None
    licence: str | None = None
    format: str | None = None
    shelf: str | None = None
    # a licensed copy's edition and a few words about the copy, from the licensed catalog alone ("3rd", "stand-in file");
    # None for a free work, whose catalog notes are working notes the view does not show
    edition: str | None = None
    notes: str | None = None
    # The work's page readings in figures; None for a work that is not read page by page (HTML, for one).
    readings: WorkReadings | None = None
    # An HTML work's structure (the operator's 4.a): the sections the loader cut by heading and the chunks embedded from them, as
    # the search index records them; None for a work read page by page, or where the index is not built, which `why_not`
    # then says.
    sections: int | None = None
    chunks: int | None = None
    structure_why_not: str | None = None
    # a licensed catalog entry the export holds no pages of (O1.a): `NOT_READ`, in place of page counts; None otherwise
    not_read: str | None = None
    # a licensed EPUB the librarian serves by section (123.a): the key its view and its search hits name it by, which may
    # differ from the catalog's id (a legacy work's key); None for any other work
    epub_key: str | None = None
    # how the work is cut, as the list knows it (Y1.a): read page by page, by its sections (a free HTML work, a licensed
    # EPUB), or not read yet; the sources view's structure facet takes it as it stands
    structure: Literal['read page by page', 'sections by heading', 'not read page by page'] | None = None
    # the series its catalog puts it in, the free one's or the local licensed one's (Y1.a; the free catalog's since 22 Nov);
    # None for a work in none, and for a licensed work under --public-only
    series: Series | None = None
    # how far it is refined, the five levels of U1.a, from the shelf and its read pages' states; None where the shelf has no
    # row of it on this machine
    ladder: Ladder | None = None
    # its pages open as a list here (U1.a: every work opens): read page by page, or a licensed PDF not read yet, whose list
    # holds every page without a reading (V1.b)
    page_list: bool = False
    # a stand-in file beside it, folded into its row; None for every other work
    stand_in: StandIn | None = None
    # its editions, where it is held in more than one (E1.a): the served edition's row, every kept one folded into it
    editions: Editions | None = None
    # a file that looks like another edition and is linked with none, in a warning's words: a call to look; None otherwise
    possible_edition: str | None = None
    # its companion code (#12), folded into its row; on a code work whose book is not listed here, its own part
    code: CodePart | None = None


def works(catalog: Path = CATALOG) -> list[Work]:
    """Every work in the catalog, in the catalog's order. The catalog is the free knowledge base's, kept with it in
    `corpus/`, so each of its works is free; the licensed knowledge base has none."""
    sources = json.loads(catalog.read_text(encoding='utf-8'))['sources']
    return [Work(knowledge_base='free', **CatalogSource.model_validate(source).model_dump()) for source in sources]
