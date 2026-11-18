"""The unit that loading produces and splitting consumes: one section of one source.

A section is the smallest piece of a source that its own structure names: a PDF outline entry, an
HTML heading. It carries everything a citation needs, so nothing downstream has to go back to the
raw file to say where a passage came from.
"""

from bisect import bisect_right
from dataclasses import dataclass, field


@dataclass
class Section:
    """One named section of a source, with its text and its locator.

    Attributes:
        source_id: The catalog id of the source.
        ordinal: Position of the section within the source, from 0; stable for a given raw file.
        heading_path: The headings above and including this one, outermost first.
        text: The cleaned text of the section.
        url: HTML only: the address a citation links to, including the anchor if there is one.
        anchor: HTML only: the fragment id of the section, or None for a section without one.
        pages: PDF only: (offset into text, PDF page, printed page) for every page the section
            touches, in order. The printed page is None where the book prints no number.
        routes: PDF only: PDF page -> (route, reading key) for every page, where the page's text
            came from a verified reading or from its text layer, and why (phase 5).
    """

    source_id: str
    ordinal: int
    heading_path: list[str]
    text: str
    url: str | None = None
    anchor: str | None = None
    pages: list[tuple[int, int, int | str | None]] = field(default_factory=list)
    routes: dict[int, tuple[str, str | None]] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f'{self.source_id}:{self.ordinal:04d}'

    @property
    def chapter(self) -> str:
        return self.heading_path[0] if self.heading_path else ''

    @property
    def title(self) -> str:
        return self.heading_path[-1] if self.heading_path else ''

    def page_at(self, offset: int) -> tuple[int | None, int | None]:
        """The PDF page and printed page on which a character offset of the text lies.

        Args:
            offset: A character offset into `text`.

        Returns:
            (PDF page, printed page); (None, None) for a section without pages.
        """
        if not self.pages:
            return None, None
        starts = [start for start, _, _ in self.pages]
        _, pdf_page, printed_page = self.pages[max(bisect_right(starts, offset) - 1, 0)]
        return pdf_page, printed_page
