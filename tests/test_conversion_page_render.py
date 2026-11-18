from pathlib import Path

import pymupdf
import pytest

from backend.configuration import data_paths
from backend.conversion.contract import page_contract
from backend.conversion.reading import page_render

RAW = data_paths.FREE_RAW
EXAMPLE_PAGE = Path(__file__).resolve().parent / 'fixtures' / 'page_contract' / 'openstax-finance-2e_p0179.page.md'


def test_sizes_follow_the_rule_of_each_resolution():
    # A 504 x 661.5 pt page, as measured in the pilot preparation.
    assert page_render.target_size(504.0, 661.5, 'hi') == (1680, 2205)
    assert page_render.target_size(504.0, 661.5, 'lo') == (1194, 1568)
    assert page_render.target_size(504.0, 661.5, 'old') == (946, 1242)


def test_a_us_letter_page_gets_the_size_of_the_reference_function():
    # 4,758 patches: the size the design computed with Anthropic's reference and the example pages use.
    assert page_render.target_size(612.0, 792.0, 'hi') == (1688, 2184)
    assert page_render.patches(1688, 2184) == 4758


def test_the_two_column_paper_gets_its_own_size():
    assert page_render.target_size(595.26, 779.52, 'hi') == (1680, 2200)


def test_the_reference_function_keeps_a_size_that_fits_and_shrinks_one_that_does_not():
    assert page_render.resized_size(1000, 1500) == (1000, 1500)
    width, height = page_render.resized_size(3000, 4000)
    assert page_render.patches(width, height) <= page_render.HI_PATCHES and height <= page_render.HI_EDGE
    assert width / height == pytest.approx(3000 / 4000, abs=0.001)


def test_a_landscape_page_is_the_portrait_page_turned():
    assert page_render.resized_size(4000, 3000) == page_render.resized_size(3000, 4000)[::-1]


def test_hi_respects_every_cap_on_odd_page_shapes():
    for width_pt, height_pt in [(612, 792), (792, 612), (420, 595), (1000, 300), (300, 1000), (728, 1288)]:
        width, height = page_render.target_size(width_pt, height_pt, 'hi')
        assert max(width, height) <= page_render.HI_EDGE
        assert width * height <= page_render.MAX_PIXELS
        assert page_render.patches(width, height) <= page_render.HI_PATCHES


def test_an_unknown_resolution_is_an_error():
    with pytest.raises(ValueError, match='unknown resolution'):
        page_render.target_size(500, 700, 'medium')


def test_a_page_whose_rotation_lays_its_text_on_its_side_is_rendered_upright_and_keeps_its_rotation():
    # The licensed round 6 (2026-11-08): a table set sideways by /Rotate 270 came back with boxes outside the image.
    with pymupdf.open() as document:
        page = document.new_page(width=792, height=612)  # a landscape table, its text horizontal
        page.insert_text((72, 72), 'TABLE 16. Global Bond Portfolio, a row of figures across the page.')
        page.set_rotation(270)  # shown as a portrait page with the table on its side
        assert page.rect.height > page.rect.width and page_render.text_runs_sideways(page)
        image = page_render.render(page, 'hi')
        assert image.width > image.height  # the reader sees the table upright
        assert page.rotation == 270  # and nothing after the render sees the change
        with page_render.upright(page):
            assert page.rect.width > page.rect.height  # stage 2 checks in the same frame


def test_a_rotation_that_sets_vertical_text_upright_is_kept():
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        page.insert_text((300, 700), 'A scan-like page whose lines run up the sheet.', rotate=90)
        page.set_rotation(90)
        assert not page_render.text_runs_sideways(page)
        image = page_render.render(page, 'hi')
        assert (image.width, image.height) == page_render.target_size(page.rect.width, page.rect.height, 'hi')
        plain = document.new_page(width=612, height=792)
        plain.insert_text((72, 72), 'An ordinary page.')
        assert not page_render.text_runs_sideways(plain)


def test_a_generated_page_renders_to_exactly_the_computed_size():
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        page.insert_text((72, 72), 'A page.')
        image = page_render.render(page, 'hi')
    assert (image.width, image.height) == (1688, 2184) and image.patches == 4758
    assert image.png.startswith(b'\x89PNG') and not image.colour


@pytest.mark.corpus
def test_a_public_page_renders_to_the_exact_size_and_the_same_bytes_twice():
    page = pymupdf.open(RAW / 'openstax_principles_of_finance_2e.pdf')[342]
    first, second = page_render.render(page, 'lo'), page_render.render(page, 'lo')
    assert (first.width, first.height) == page_render.target_size(page.rect.width, page.rect.height, 'lo')
    assert first.png.startswith(b'\x89PNG') and first.sha256 == second.sha256


@pytest.mark.corpus
def test_the_real_page_has_the_image_size_the_example_page_gives_its_boxes_in():
    # A reader told another size, or a judge shown this page beside the example, would report a false mismatch.
    image = page_render.render(pymupdf.open(RAW / 'openstax_principles_of_finance_2e.pdf')[178], 'hi')
    expected = page_contract.Expected('openstax-finance-2e', 179, (image.width, image.height))
    assert page_contract.parse(EXAMPLE_PAGE.read_text(encoding='utf-8'), 'markdown', expected).valid
