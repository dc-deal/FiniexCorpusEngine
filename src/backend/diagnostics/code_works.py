"""A code work in the view (issue #12, the operator's 3.a, 23 Nov): a book's companion code, its folders and files, each file
with what the core's catalog says of it, and one file at a time, numbered, as the librarian serves it. Everything comes from
the view's search service (`toc`, `open_page`, `code_catalog`), so the view says what the librarian says and reads nothing
beside it; an app started with --public-only serves no licensed work, so no licensed code reaches it (81.a).

A unit's sentence is a model's, derived from the code (`summary_is` names the model), and is shown as derived, never as a
quote; its inputs and the source its opening comment names are read from the code itself by the core.
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from backend.diagnostics import work_editions
from backend.diagnostics.readings import KnowledgeBase

NO_CATALOG = "the core's catalog holds no unit of this work yet (python -m backend.ingestion.code_catalog)"


class LineRange(BaseModel):
    first: int
    last: int


class CodeInput(BaseModel):
    name: str
    default: str  # as the code writes it


class CodeUnit(BaseModel):
    """What the core's catalog says of one file's unit (`code_catalog`)."""

    name: str
    unit: str | None = None  # function, indicator or strategy, by the folder it stands in
    category: str | None = None
    aliases: list[str] = []
    inputs: list[CodeInput] = []
    source_named: str | None = None  # what the file's opening comment says it comes from, as written
    summary: str | None = None  # one sentence a model derived from the code: never a quote
    summary_is: str | None = None  # "derived (claude-haiku-5-5)": what made the sentence


class CodeFile(BaseModel):
    label: str  # its path in the work: the label `open_page` takes and the view's address names
    name: str  # as its folder lists it, without its extension
    unit: CodeUnit | None = None  # None where the catalog has no entry of it


class CodeFolder(BaseModel):
    title: str | None = None  # None for files at the work's top
    count: int = 0  # its files
    files: list[CodeFile]


class CategoryCount(BaseModel):
    category: str
    units: int


class Companion(BaseModel):
    """The book a code work accompanies, and where its record opens here (as an edition's does, E1.a)."""

    key: str
    title: str
    view: Literal['pages', 'epub'] | None = None
    id: str | None = None


class CodeWork(BaseModel):
    """A code work's own page: its folders and files, each file with its catalog entry, and the core's count by category."""

    knowledge_base: KnowledgeBase
    work: str
    title: str
    code_language: str | None = None
    companion: Companion | None = None
    licence: str | None = None
    route: str
    files: int
    units: int  # the units the core's catalog holds of it
    categories: list[CategoryCount] = []  # the core's own count (`code_catalog`'s `categories`), the most first
    catalog_said: str | None = None  # where the catalog holds none of its units: why
    folders: list[CodeFolder]


class CodePage(BaseModel):
    """One file of a code work, as `open_page` serves it, with its catalog entry and its neighbours in the work's order."""

    knowledge_base: KnowledgeBase
    work: str
    title: str
    code_language: str | None = None
    companion: Companion | None = None
    licence: str | None = None
    route: str
    label: str
    folder: str | None = None
    name: str
    text: str  # the file as the publisher gave it
    lines: LineRange
    unit: CodeUnit | None = None
    previous: str | None = None  # the neighbours' labels, which their addresses name
    next: str | None = None
    previous_name: str | None = None  # and their names, as the pager shows them
    next_name: str | None = None
    position: int  # its place among the work's files, from 1
    files: int


def code_meta(service: Any, knowledge_base: str, work: str) -> Any | None:
    """The service's work, where it is a code work of this knowledge base; None otherwise."""
    meta = service.works.get(work)
    if meta is None or getattr(meta, 'kind', 'text') != 'code' or meta.knowledge_base != knowledge_base:
        return None
    return meta


def files_of(service: Any, work: str) -> list[tuple[str | None, str, str]]:
    """(folder, name, label) of each file in the work's order, as `toc` lists them: a folder, then its files."""
    folder, out = None, []
    for entry in service.toc(work, depth=2).get('entries') or []:
        if entry.get('page') is None:
            folder = entry.get('title')
            continue
        out.append((folder if entry.get('level') == 2 else None, str(entry.get('title') or ''), str(entry['page'])))
    return out


def catalog_of(service: Any, work: str) -> dict:
    """The core's catalog of a work: every unit in one call, which a whole work fits (`CATALOG_HITS`)."""
    from backend.search import search_server

    answer = service.code_catalog(work=work, hits=search_server.CATALOG_HITS)
    return answer if answer.get('state') != 'error' else {'units': [], 'total': 0, 'categories': {}}


def unit_of(record: dict) -> CodeUnit:
    return CodeUnit(name=str(record.get('name') or Path(str(record.get('page') or '')).stem), unit=record.get('unit'),
                    category=record.get('category'), aliases=list(record.get('aliases') or []),
                    inputs=[CodeInput(name=str(one.get('name')), default=str(one.get('default') or ''))
                            for one in record.get('inputs') or [] if isinstance(one, dict) and one.get('name')],
                    source_named=record.get('source_named'), summary=record.get('summary'), summary_is=record.get('summary_is'))


def companion_of(service: Any, meta: Any, shelf: dict | None) -> Companion | None:
    """The book a code work accompanies, by its key, its title the service's and its record found on the base's shelf."""
    key = getattr(meta, 'companion_of', None)
    if not key:
        return None
    book = service.works.get(key)
    view, found = work_editions.target(work_editions.row_of(key, (shelf or {}).get('works') or []))
    return Companion(key=key, title=book.title if book is not None else key, view=view, id=found)


def code_work(service: Any, knowledge_base: str, work: str, shelf: dict | None = None) -> CodeWork | None:
    """A code work whole; None where the service holds no code work of that key in that knowledge base."""
    meta = code_meta(service, knowledge_base, work)
    if meta is None:
        return None
    catalog = catalog_of(service, work)
    units = {record.get('page'): unit_of(record) for record in catalog.get('units') or [] if isinstance(record, dict)}
    folders: list[CodeFolder] = []
    for folder, name, label in files_of(service, work):
        if not folders or folders[-1].title != folder:
            folders.append(CodeFolder(title=folder, files=[]))
        folders[-1].files.append(CodeFile(label=label, name=name, unit=units.get(label)))
        folders[-1].count = len(folders[-1].files)
    counts = sorted((catalog.get('categories') or {}).items(), key=lambda pair: (-pair[1], pair[0]))
    total = int(catalog.get('total') or 0)
    return CodeWork(knowledge_base=meta.knowledge_base, work=work, title=meta.title, code_language=meta.code_language,
                    companion=companion_of(service, meta, shelf), licence=meta.licence, route=meta.route,
                    files=sum(len(folder.files) for folder in folders), units=total,
                    categories=[CategoryCount(category=category, units=count) for category, count in counts],
                    catalog_said=None if total else NO_CATALOG, folders=folders)


def code_page(service: Any, knowledge_base: str, work: str, label: str, shelf: dict | None = None) -> CodePage | None:
    """One file of a code work; None where the work or the file is not served."""
    meta = code_meta(service, knowledge_base, work)
    if meta is None:
        return None
    opened = service.open_page(work, label)
    if opened.get('state') != 'found':
        return None
    files = files_of(service, work)
    labels = [one for _, _, one in files]
    at = labels.index(label) if label in labels else None
    record = next((one for one in catalog_of(service, work).get('units') or [] if one.get('page') == label), None)
    text = str(opened.get('text') or '')
    lines = opened.get('lines') or {'first': 1, 'last': text.count('\n') + 1}
    return CodePage(knowledge_base=meta.knowledge_base, work=work, title=meta.title, code_language=meta.code_language,
                    companion=companion_of(service, meta, shelf), licence=meta.licence, route=opened.get('route') or meta.route,
                    label=label, folder=opened.get('section'),
                    name=files[at][1] if at is not None else Path(label).stem, text=text, lines=LineRange(**lines),
                    unit=unit_of(record) if record else None,
                    previous=labels[at - 1] if at else None,
                    next=labels[at + 1] if at is not None and at + 1 < len(labels) else None,
                    previous_name=files[at - 1][1] if at else None,
                    next_name=files[at + 1][1] if at is not None and at + 1 < len(labels) else None,
                    position=(at or 0) + 1, files=len(labels))
