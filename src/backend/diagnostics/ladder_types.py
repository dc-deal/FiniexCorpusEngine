"""The coverage ladder's shapes (the operator's U1.a, 20 Nov), apart from how it is counted (`coverage_ladder`), so a work's
page list (`readings.WorkPages`) can carry one without the two modules importing each other."""

from typing import Literal

from pydantic import BaseModel

KnowledgeBase = Literal['free', 'licensed']  # the knowledge bases the core exports (80.a); `readings` takes it from here
Level = Literal['text served', 'keyword search', 'semantic chunks', 'read', 'checked']
LEVELS: tuple[Level, ...] = ('text served', 'keyword search', 'semantic chunks', 'read', 'checked')


class LadderState(BaseModel):
    """A state of a work's read pages and how many are in it, as the lists count them."""

    value: str
    count: int
    # of a state to look at, how many of its pages the core serves all the same (18 Nov, `StateCount.served`); None otherwise
    served: int | None = None


class Rung(BaseModel):
    """One level of a ladder: how many of the whole reach it, said in a line."""

    level: Level
    means: str = ''  # what the level counts, in a line: the hint's legend
    count: int | None  # None where the level does not apply, or is not measured here; `said` says which
    of: int | None  # the whole it is drawn against
    said: str
    # the corpus's parts per knowledge base, for its card; {} for a work
    by_base: dict[KnowledgeBase, int] = {}
    # the Pages view's filter that lists exactly its pages, where one exists ({} for every page); None where none does
    pages_filter: dict[str, list[str]] | None = None
    # where a look is called for (C1.b): the pages the judge found bad beside the checked ones, drawn as a segment of the
    # checked meter in the issue's role; and a level nothing reaches that should, a work that serves no text at all, drawn
    # in the warning role. The words stay the card's either way
    issues: int | None = None
    warn: bool = False


class Ladder(BaseModel):
    """A work's or the corpus's coverage ladder, and the details a fold or a card shows."""

    unit: str  # what the whole counts: 'PDF pages', 'sections', or 'pages and sections' for the corpus
    whole: int | None
    rungs: list[Rung]
    # the details: what serves the text, by route; why a file is held from providers or not served; passed readings the
    # search does not serve, by why; every state of the read pages; the pages planned
    by_route: dict[str, int] = {}
    held: str | None = None
    not_served: str | None = None
    unplaced: dict[str, int] = {}
    states: list[LadderState] = []
    planned: int | None = None
    passed: int | None = None  # of the read pages, those whose reading passed, as the shelf counts them
    built_at: str | None = None  # when the core built the shelf levels 1 to 4 come from


PageLevel = Literal['text layer', 'text served', 'keyword search', 'semantic chunks', 'reading and check']


class PageRung(BaseModel):
    """One level of a page's or a section's own ladder (V2.a): whether the page reaches it, said in a line."""

    level: PageLevel
    reached: bool | None  # None where it is not known here, which `said` says
    said: str


class PageLadder(BaseModel):
    """A page's or a section's own ladder (the operator's V2.a, 20 Nov), and the text the librarian serves for it."""

    rungs: list[PageRung]
    served_text: str | None = None  # the librarian's own text of the page, from the search's pages; None where none is shown
    served_why_not: str | None = None  # why no served text is shown: nothing is served, or the search is not built yet
    held: str | None = None  # why the file is never sent to a provider; shown here all the same, on this machine only
