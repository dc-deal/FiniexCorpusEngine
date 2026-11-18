"""Render one PDF page to the exact image a vision reader receives.

The API bills an image by 28 x 28 pixel patches and caps it (2,576 px long edge, 4,784 patches,
3.75 megapixels). The size is therefore computed here, and for 'hi' with Anthropic's reference
`resized_size()`: a US Letter page becomes 1688 x 2184, the size the contract's example pages
give their pixel boxes in. Separate x and y zoom factors give the exact pixel size: with a single
factor, 35 of 38 pages came out one pixel too large (measured 2026-10-29 in the pilot
preparation). A page without colour goes out as a greyscale PNG, the same tokens in fewer bytes.
The bytes are deterministic, so the image's sha256 names the input of a reading.
"""

import hashlib
import io
import math
from contextlib import contextmanager
from dataclasses import dataclass

import pymupdf
from PIL import Image, ImageChops

PATCH_PX = 28
HI_EDGE, HI_PATCHES, MAX_PIXELS = 2576, 4784, 3_750_000
START_DPI = 300  # the render the reference function shrinks from; a page that already fits at this size stays as it is
LO_EDGE = 1568
OLD_TOKENS = 1568  # the older image tier: about one token per 750 pixels
COLOUR_DIFFERENCE = 16  # a channel difference above this anywhere on the page counts as colour
RESOLUTIONS = ('hi', 'lo', 'old')


class RenderSizeError(RuntimeError):
    """The rendered image does not have the size computed for it, or breaks a cap."""


def patches(width: int, height: int) -> int:
    return math.ceil(width / PATCH_PX) * math.ceil(height / PATCH_PX)


def resized_size(width: int, height: int) -> tuple[int, int]:
    """Anthropic's reference function for the high-resolution tier (vision-coordinates page, read 2026-10-29), with the
    megapixel cap added: the largest size of this aspect that fits, or the size itself when it fits already."""
    def fits(w: int, h: int) -> bool:
        return (math.ceil(w / PATCH_PX) * PATCH_PX <= HI_EDGE and math.ceil(h / PATCH_PX) * PATCH_PX <= HI_EDGE
                and patches(w, h) <= HI_PATCHES and w * h <= MAX_PIXELS)

    if fits(width, height):
        return width, height
    if height > width:
        return resized_size(height, width)[::-1]
    aspect = width / height
    low, high = 1, width
    while low + 1 < high:
        middle = (low + high) // 2
        if fits(middle, max(round(middle / aspect), 1)):
            low = middle
        else:
            high = middle
    return low, max(round(low / aspect), 1)


def _largest_size(width_pt: float, height_pt: float, edge: int, patch_cap: int,
                  old_tier: bool = False) -> tuple[int, int]:
    """Shrink the long edge 2 px at a time until every cap holds (the pilot preparation's rule)."""
    while edge >= 200:
        zoom = edge / max(width_pt, height_pt)
        width, height = int(width_pt * zoom), int(height_pt * zoom)
        fits = patches(width, height) <= patch_cap and width * height <= MAX_PIXELS
        if fits and (not old_tier or width * height / 750 <= OLD_TOKENS):
            return width, height
        edge -= 2
    raise ValueError(f'no image size fits a {width_pt} x {height_pt} pt page')


def target_size(width_pt: float, height_pt: float, resolution: str) -> tuple[int, int]:
    """The pixel size for a page of this size in points.

    'hi' is the largest image the high-resolution tier takes, 'lo' a long edge of 1568 px, 'old'
    the older tier's size (about 1,600 tokens).
    """
    if resolution == 'hi':
        return resized_size(round(width_pt / 72 * START_DPI), round(height_pt / 72 * START_DPI))
    if resolution == 'lo':
        zoom = LO_EDGE / max(width_pt, height_pt)
        return int(width_pt * zoom), int(height_pt * zoom)
    if resolution == 'old':
        return _largest_size(width_pt, height_pt, LO_EDGE, OLD_TOKENS, old_tier=True)
    raise ValueError(f'unknown resolution {resolution!r}, expected one of {RESOLUTIONS}')


@dataclass(frozen=True)
class PageImage:
    png: bytes
    width: int
    height: int
    colour: bool

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.png).hexdigest()

    @property
    def patches(self) -> int:
        return patches(self.width, self.height)


def text_runs_sideways(page: pymupdf.Page) -> bool:
    """Whether the page's own rotation (/Rotate) lays horizontal text on its side: the page is rotated, yet the lines of its
    unrotated text layer run horizontally. Found in the licensed round 6 (2026-11-08): a table set sideways by /Rotate 270,
    read as printed, came back with its boxes in the upright frame, outside the image. 6 of the 25 rotated licensed pages are
    such; on the other 19 the rotation sets vertical lines upright, and a page without a text layer is left as it is."""
    if not page.rotation:
        return False
    horizontal = vertical = 0
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            if abs(line['dir'][0]) > 0.9:
                horizontal += 1
            else:
                vertical += 1
    return horizontal > vertical


@contextmanager
def upright(page: pymupdf.Page):
    """The page as the reader is shown it: unrotated where its rotation lays its text on its side, as it is otherwise. The
    rotation is put back afterwards, so a page is rendered and checked against its text layer in one and the same frame."""
    rotation = page.rotation
    if text_runs_sideways(page):
        page.set_rotation(0)
    try:
        yield page
    finally:
        if page.rotation != rotation:
            page.set_rotation(rotation)


def render(page: pymupdf.Page, resolution: str) -> PageImage:
    """The page as a PNG of exactly the computed size, without annotations such as highlighting, its text upright.

    Raises:
        RenderSizeError: When the pixmap's size differs from the computed one or a cap is broken.
    """
    with upright(page):
        return _render(page, resolution)


def _render(page: pymupdf.Page, resolution: str) -> PageImage:
    width, height = target_size(page.rect.width, page.rect.height, resolution)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(width / page.rect.width, height / page.rect.height),
                             annots=False)
    if (pixmap.width, pixmap.height) != (width, height):
        raise RenderSizeError(f'rendered {pixmap.width} x {pixmap.height}, computed {width} x {height}')
    if max(width, height) > HI_EDGE or width * height > MAX_PIXELS or patches(width, height) > HI_PATCHES:
        raise RenderSizeError(f'{width} x {height} breaks a cap')
    image = Image.frombytes('RGB', (width, height), pixmap.samples)
    red, green, blue = image.split()
    colour = max(ImageChops.difference(red, green).getextrema()[1],
                 ImageChops.difference(green, blue).getextrema()[1]) > COLOUR_DIFFERENCE
    out = io.BytesIO()
    (image if colour else image.convert('L')).save(out, format='PNG', optimize=False)
    return PageImage(out.getvalue(), width, height, colour)
