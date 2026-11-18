"""A page's image as its PDF holds it: a scan's own pixels never upscaled, a born-digital page rendered (decision 92.a)."""

import io

import pymupdf
import pytest
from PIL import Image, features

from backend.search import page_images


def a_pdf(path, image: bytes | None = None, text: str | None = None, cover=1.0):
    document = pymupdf.open()
    page = document.new_page(width=216, height=288)  # 3 x 4 inches
    if image is not None:
        page.insert_image(pymupdf.Rect(0, 0, 216 * cover, 288 * cover), stream=image)
    if text:
        page.insert_text((20, 40), text)
    document.save(path)
    return path


def encoded(fmt: str, size=(300, 400)) -> bytes:
    buffer = io.BytesIO()
    Image.new('L', size, 180).save(buffer, fmt)
    return buffer.getvalue()


def test_a_scan_stored_as_jpeg_goes_out_as_stored_at_its_own_size(tmp_path):
    jpeg = encoded('JPEG')
    image = page_images.page_image(a_pdf(tmp_path / 'scan.pdf', jpeg), 1)
    assert (image.kind, image.stored_format, image.format, image.width, image.height, image.dpi) == ('native', 'jpeg', 'jpeg', 300, 400, 100)
    assert image.data == jpeg and image.stored_bytes == len(jpeg)


@pytest.mark.skipif(not features.check('jpg_2000'), reason='Pillow without JPEG 2000')
def test_a_jpeg2000_scan_goes_out_as_a_png_of_the_same_pixels(tmp_path):
    image = page_images.page_image(a_pdf(tmp_path / 'scan.pdf', encoded('JPEG2000')), 1)
    assert (image.kind, image.stored_format, image.format, image.width, image.height) == ('native', 'jpx', 'png', 300, 400)
    assert Image.open(io.BytesIO(image.data)).size == (300, 400), 'the same pixels, never upscaled'


def test_a_born_digital_page_is_rendered_and_says_so(tmp_path):
    image = page_images.page_image(a_pdf(tmp_path / 'text.pdf', text='A page of text.'), 1)
    assert (image.kind, image.stored_format, image.dpi, image.width, image.height) == ('rendered', 'none', 150, 450, 600)
    assert 'render' in image.describe()['what']


def test_a_small_picture_on_a_page_is_not_taken_for_the_page(tmp_path):
    image = page_images.page_image(a_pdf(tmp_path / 'figure.pdf', encoded('PNG', (60, 60)), text='Text beside it.', cover=0.3), 1)
    assert image.kind == 'rendered'


def test_a_page_the_pdf_does_not_have_is_named(tmp_path):
    with pytest.raises(page_images.NoSuchPage, match='1 pages'):
        page_images.page_image(a_pdf(tmp_path / 'text.pdf', text='One page.'), 2)
