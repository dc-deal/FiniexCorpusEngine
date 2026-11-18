"""What the diagnostics UI shows about the sources, read from the core's data and never written.

Every model here is the response shape of a route in `app.py`. It reaches the UI's TypeScript through
the OpenAPI schema (`python -m backend.diagnostics.build`), never by hand.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from backend.diagnostics.readings import KnowledgeBase, WorkReadings

ROOT = Path(__file__).resolve().parents[3]
CATALOG = ROOT / 'corpus' / 'catalog.json'
# What the sources view says, in place of page counts, of a licensed catalog entry the export has no pages of (O1.a): the
# view's own state until the core reads it, an EPUB by its sections as the free HTML works are (123.a), which then replace it
NOT_READ = 'not read page by page'
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


def works(catalog: Path = CATALOG) -> list[Work]:
    """Every work in the catalog, in the catalog's order. The catalog is the free knowledge base's, kept with it in
    `corpus/`, so each of its works is free; the licensed knowledge base has none."""
    sources = json.loads(catalog.read_text(encoding='utf-8'))['sources']
    return [Work(knowledge_base='free', **CatalogSource.model_validate(source).model_dump()) for source in sources]
