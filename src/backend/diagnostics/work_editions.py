"""A work's editions as the view shows them (the operator's E1.a, 20 Nov): an edition is a level under its work, work ›
edition › page or section, never a group of works. Exactly one edition is served; the others are kept, each with all it has
(its readings, its chunks, its pages, its own record), and only the two searches skip it. Which edition is served changes only
by a core command on the operator's word (`backend.search.editions`), so the view stays read-only.

The core writes a work's family on its shelf rows (`shelf.with_editions`): every row of a family carries `editions` (which
edition is served, when and why it was chosen, each edition with its label, year and format), a kept edition the key of the
served one (`kept_for`), and a file that looks like another edition and is linked with none, the keys it may be an edition of
(`possible_edition_of`). This module reads that and nothing else: it finds each edition's row by the edition's key, which is
the row's work key, its source id or its file's stem, and from the row where its own record opens here.
"""

from typing import Literal

from pydantic import BaseModel

UNKNOWN = 'edition unknown'  # the core's label of an edition whose catalog entry names neither edition nor year


class Edition(BaseModel):
    """One edition of a work: its label as the core names it, its format, whether it is the one served, and where its own
    record opens here."""

    key: str
    label: str  # "2nd edition, 2003", or a year alone ("2017")
    named: str  # the edition in a sentence's words: "2nd edition, 2003", "2017 edition"
    format: str | None = None
    served: bool
    # its own record: a page list by its source id, or an EPUB view by its key; None where it has none here
    view: Literal['pages', 'epub'] | None = None
    id: str | None = None


class Editions(BaseModel):
    """A work held in more than one edition, as its row in the list and every edition's record show it."""

    title: str  # the work's title: the served edition's
    serves: str  # the served edition's key
    chosen: str  # when the operator chose it, ISO 8601; the view says it in words
    why: str
    said: str  # "2 editions · serves the 2nd edition, 2003"
    editions: list[Edition]
    current: str | None = None  # on an edition's own record, its key: the bar marks it, the trail names it


def named(label: str) -> str:
    """An edition in a sentence's words: "2nd edition, 2003" stays, a year alone becomes "2017 edition"."""
    if label == UNKNOWN:
        return 'edition of unknown date'
    return label if 'edition' in label else f'{label} edition'


def words(edition: str | None, year: int | str | None) -> str | None:
    """The edition a citation names beside the title: "2nd edition, 2003", "2nd edition", "2003"; None where there is
    neither, as the core's label words it."""
    parts = [f'{edition} edition' if edition else None, str(year) if year else None]
    return ', '.join(part for part in parts if part) or None


def keys_of(row: dict) -> set[str]:
    """The keys a shelf row answers to: its work key, its source id, its file's stem."""
    stem = (row.get('file') or '').rsplit('.', 1)[0]
    return {key for key in (row.get('work'), row.get('source_id'), stem) if key}


def row_of(key: str, rows: list[dict]) -> dict | None:
    """An edition's row on its base's shelf, by its key."""
    return next((row for row in rows if key in keys_of(row)), None)


def family_of(row: dict, rows: list[dict]) -> dict | None:
    """The family a row belongs to: its own `editions`, or one another row carries that names this row's key as an edition
    (the core names a family on every row it can match by its work key or its file's stem; a row whose work key is a legacy
    work's is matched here by its source id too)."""
    if row.get('editions'):
        return row['editions']
    keys = keys_of(row)
    return next((other['editions'] for other in rows if other.get('editions')
                 and keys & {edition['key'] for edition in other['editions']['editions']}), None)


def target(row: dict | None) -> tuple[Literal['pages', 'epub'] | None, str | None]:
    """Where an edition's own record opens here: an EPUB by its librarian's key in the EPUB view, a PDF by its source id in
    its page list (every PDF opens, read or not); a work served from the IDE's Markdown alone has none."""
    if row is None:
        return None, None
    if row.get('format') == 'epub':
        return 'epub', row.get('work') or (row.get('file') or '').rsplit('.', 1)[0] or None
    if row.get('format') == 'pdf' and row.get('source_id'):
        return 'pages', row['source_id']
    return None, None


def editions_of(row: dict, rows: list[dict], title: str, current: str | None = None) -> Editions | None:
    """A row's work in its editions, None for a work held in one; `title` the work's, the served edition's title."""
    family = family_of(row, rows)
    if family is None:
        return None
    editions = []
    for edition in family['editions']:
        view, record = target(row_of(edition['key'], rows))
        editions.append(Edition(key=edition['key'], label=edition['label'], named=named(edition['label']),
                                format=edition.get('format'), served=edition['served'], view=view, id=record))
    served = next(edition for edition in editions if edition.served)
    return Editions(title=title, serves=family['serves'], chosen=family['chosen'], why=family['why'],
                    said=f'{len(editions)} editions · serves the {served.named}', editions=editions, current=current)


def kept_for(row: dict, rows: list[dict]) -> str | None:
    """The served edition's key where this row is a kept edition, None otherwise."""
    if row.get('kept_for'):
        return row['kept_for']
    family = family_of(row, rows)
    if family is None:
        return None
    return None if family['serves'] in keys_of(row) else family['serves']


def served_named(row: dict, rows: list[dict]) -> str | None:
    """The served edition in a sentence's words, for a kept edition's ladder: "2nd edition, 2003"; None for any other row."""
    if kept_for(row, rows) is None:
        return None
    family = family_of(row, rows)
    served = next(edition for edition in family['editions'] if edition['served'])
    return named(served['label'])


def possible_said(row: dict, title_of) -> str | None:
    """A file that looks like another edition and is linked with none, in the warning's words: a call to look."""
    keys = row.get('possible_edition_of') or []
    if not keys:
        return None
    return f"possible edition of {' and '.join(title_of(key) for key in keys)}: not linked; the operator decides"
