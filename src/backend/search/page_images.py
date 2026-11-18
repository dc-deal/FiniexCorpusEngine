"""A page's image as its PDF holds it, for a reader who has to see what the text lost (decision 92.a).

A scanned page is one embedded image over the whole page. It is given with its own pixels and never upscaled, because a render
at a higher resolution only invents pixels: a client measured it on a 100 dpi scan, where reading a 300 dpi render came out worse
than the scan itself (3.89 % unreadable tokens against 3.10 %). JPEG and PNG go out as stored. JPEG2000, JBIG2 and the fax
formats are converted to a PNG of the same pixels, since MCP clients and Claude's vision take PNG, JPEG, GIF and WebP only. A
born-digital page has no such image; it is rendered at 150 dpi, and the answer says so. Every answer states what it is: native
or rendered, the format the PDF stores, the pixels, the dpi and the bytes, so a 7 KB scan can be told from a clean page before a
vision call is spent on it.

PyMuPDF does the work, as everywhere in this project: `Page.get_images`, `Document.extract_image` and `Pixmap`.
"""

from dataclasses import dataclass
from pathlib import Path

import pymupdf

AS_STORED = {'png': 'png', 'jpeg': 'jpeg', 'jpg': 'jpeg'}  # formats a client can show as the PDF holds them
COVER = 0.9  # an image over at least this share of the page is the page's own scan
RENDER_DPI = 150


@dataclass(frozen=True)
class PageImage:
    data: bytes
    format: str  # what is sent: 'png' or 'jpeg'
    kind: str  # 'native': the page's own embedded pixels; 'rendered': a born-digital page drawn at RENDER_DPI
    stored_format: str  # as the PDF holds the image ('jpx', 'jpeg', 'png', 'jb2', ...), or 'none' for a render
    width: int
    height: int
    dpi: int
    stored_bytes: int  # the embedded image's own size; 0 for a render

    def describe(self) -> dict:
        what = ('the page\'s own embedded image, never upscaled' if self.kind == 'native'
                else f'a render at {self.dpi} dpi: the page holds no image of its own')
        return {'kind': self.kind, 'what': what, 'stored_format': self.stored_format, 'sent_as': self.format,
                'width': self.width, 'height': self.height, 'dpi': self.dpi, 'stored_bytes': self.stored_bytes,
                'sent_bytes': len(self.data)}


def own_image(page: pymupdf.Page) -> int | None:
    """The xref of the image that is the page itself: the largest one over most of the page that is no other image's mask."""
    images = page.get_images(full=True)
    masks = {image[1] for image in images if image[1]}
    area = page.rect.width * page.rect.height
    best = None
    for image in images:
        xref, width, height = image[0], image[2], image[3]
        if xref in masks:
            continue
        covered = max(((rect & page.rect).get_area() for rect in page.get_image_rects(xref)), default=0.0)
        if covered >= COVER * area and (best is None or width * height > best[1]):
            best = (xref, width * height)
    return best[0] if best else None


class NoSuchPage(LookupError):
    """A page number the PDF does not have."""


def page_image(path: Path, pdf_page: int) -> PageImage:
    """One page's image: its own pixels where it is a scan, else a render; see the module's docstring.

    Raises:
        NoSuchPage: When the PDF has no such page.
    """
    with pymupdf.open(path) as document:
        if not 1 <= pdf_page <= document.page_count:
            raise NoSuchPage(f'the PDF has {document.page_count} pages, not page {pdf_page}')
        page = document[pdf_page - 1]
        xref = own_image(page)
        if xref is None:
            pixmap = page.get_pixmap(dpi=RENDER_DPI)
            return PageImage(pixmap.tobytes('png'), 'png', 'rendered', 'none', pixmap.width, pixmap.height, RENDER_DPI, 0)
        extracted = document.extract_image(xref)
        stored = extracted['ext'].lower()
        if stored in AS_STORED:
            data, sent = extracted['image'], AS_STORED[stored]
        else:
            pixmap = pymupdf.Pixmap(document, xref)  # the same pixels, decoded by MuPDF
            if pixmap.n - pixmap.alpha > 3:  # CMYK and the like: PNG holds gray and RGB
                pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
            data, sent = pixmap.tobytes('png'), 'png'
        dpi = round(extracted['width'] / (page.rect.width / 72))
        return PageImage(data, sent, 'native', stored, extracted['width'], extracted['height'], dpi, len(extracted['image']))
