import pymupdf
import pytest

from backend.ingestion.clean_sections import pdf_sections as pdf


def ruled_table_pdf(path, rows):
    """A one-page PDF: a heading, a sentence, a table drawn with ruled cells, and its caption."""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 60), '1.1 Prices', fontsize=12)
    page.insert_text((72, 90), 'The schedule below lists prices.', fontsize=10)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = pymupdf.Rect(72 + c * 120, 110 + r * 20, 72 + (c + 1) * 120, 130 + r * 20)
            page.draw_rect(cell, color=(0, 0, 0), width=0.8)
            page.insert_text((cell.x0 + 4, cell.y1 - 6), value, fontsize=10)
    page.insert_text((72, 110 + len(rows) * 20 + 20), 'Table 1.1 A schedule', fontsize=10)
    document.set_toc([[1, '1.1 Prices', 1]])
    document.save(path)
    return path


def test_a_ruled_table_is_read_as_rows_in_its_place(tmp_path):
    path = ruled_table_pdf(tmp_path / 't.pdf', [['Price', 'Quantity'], ['55', '0'], ['50', '4'], ['45', '8']])
    text = pdf.load_pdf_sections('t', path)[0].text
    assert text == ('1.1 Prices\nThe schedule below lists prices.\n'
                    '|Price|Quantity|\n|---|---|\n|55|0|\n|50|4|\n|45|8|\nTable 1.1 A schedule')


def test_table_markup_that_is_not_content_is_removed():
    class Table:
        def to_markdown(self):
            return '|**Price**|Col2|\n|---|---|\n|55|<br>0|\n'
    assert pdf.table_text(Table()) == '|Price||\n|---|---|\n|55| 0|'


def book(pages_body: list[str], offset: int = 2) -> list[str]:
    """Synthetic pages in the OpenStax layout: body, running footer with the printed number,
    and the attribution line on every page."""
    pages = []
    for pdf_page, body in enumerate(pages_body, start=1):
        printed = pdf_page - offset
        footer = f'{printed}     1 • Chapter Title' if pdf_page % 2 == 0 else f'1.1 • Section Title     {printed}'
        lines = [body]
        if printed >= 1:
            lines.append(footer)
        lines.append('Access for free at openstax.org')
        pages.append('\n'.join(lines))
    return pages


def test_repeated_lines_ignores_digits_and_needs_a_share_of_pages():
    pages = ['Header 12\nbody a', 'Header 13\nbody b', 'Header 14\nbody c', 'Header 15\nonce only']
    assert pdf.repeated_lines(pages) == {'Header #'}


def test_clean_pages_removes_headers_footers_and_reads_the_printed_number():
    cleaned, printed = pdf.clean_pages(book(['cover', 'title', 'first', 'second', 'third', 'fourth']))
    assert printed == [None, None, 1, 2, 3, 4]
    assert all('Access for free' not in page and '•' not in page for page in cleaned)
    assert cleaned[2] == 'first'


def test_a_number_that_disagrees_with_the_page_offset_is_kept_as_text():
    pages = book(['a', 'b', 'c', 'd', 'e', 'f'])
    pages[4] = 'body ends with a count\n1999\nAccess for free at openstax.org'  # 1999 is not page 3
    cleaned, printed = pdf.clean_pages(pages)
    assert '1999' in cleaned[4]
    assert printed[4] == 3  # still known from the offset


def test_a_page_number_alone_on_its_line_is_read_before_repeated_lines_are_removed():
    # Papers print the bare number; ignoring digits it reads '#' on every page.
    bodies = ['alpha', 'beta', 'gamma', 'delta', 'epsilon']
    pages = [f'Author and Author\n{body}\n{n}' for n, body in enumerate(bodies, start=1)]
    cleaned, printed = pdf.clean_pages(pages)
    assert printed == [1, 2, 3, 4, 5]
    assert cleaned == bodies


def test_sections_are_cut_at_their_heading_on_the_page():
    pages = ['1.1 First\nfirst text\n1.2 Second\nsecond text', 'more second text']
    toc = [[1, '1.1 First', 1], [1, '1.2 Second', 1]]
    sections = pdf.build_sections('s', pages, [10, 11], toc)
    assert [s.title for s in sections] == ['1.1 First', '1.2 Second']
    assert sections[0].text == '1.1 First\nfirst text'
    assert sections[1].text.startswith('1.2 Second\nsecond text')
    assert [(pdf_page, printed) for _, pdf_page, printed in sections[1].pages] == [(1, 10), (2, 11)]


def test_heading_path_follows_the_outline_levels():
    pages = ['Chapter 1 Money\nintro\n1.1 Coins\ncoins', 'Chapter 2 Risk\nrisk']
    toc = [[1, 'Chapter 1 Money', 1], [2, '1.1 Coins', 1], [1, 'Chapter 2 Risk', 2]]
    sections = pdf.build_sections('s', pages, [1, 2], toc)
    assert [s.heading_path for s in sections] == [
        ['Chapter 1 Money'], ['Chapter 1 Money', '1.1 Coins'], ['Chapter 2 Risk']]


def test_back_matter_and_front_pages_are_left_out():
    pages = ['cover', '1 Intro\ntext', 'References\n[1] A. Author. Title.']
    toc = [[1, '1 Intro', 2], [1, 'References', 3]]
    sections = pdf.build_sections('s', pages, [None, 1, 2], toc)
    assert [s.title for s in sections] == ['1 Intro']
    assert 'cover' not in sections[0].text


def test_a_contents_entry_keeps_the_chapters_nested_under_it_and_an_index_does_not():
    # SR 11-7's outline nests every chapter under 'Contents' (loader 5); an index's letters stay out with their index
    pages = ['Contents\nI. Introduction\nThe guidance applies to banks.', 'Index\nA\nalpha, 1']
    toc = [[1, 'Contents', 1], [2, 'I. Introduction', 1], [1, 'Index', 2], [2, 'A', 2]]
    sections = pdf.build_sections('s', pages, [1, 2], toc)
    assert [s.title for s in sections] == ['I. Introduction'] and 'applies to banks' in sections[0].text


def test_a_pdf_without_bookmarks_is_cut_at_its_readings_headings_where_every_page_is_read_else_page_by_page():
    read = {1: {'text': 'PART 220 CREDIT\n§ 220.1 Authority.\nThis part...', 'headings': ['PART 220 CREDIT', '§ 220.1 Authority.']},
            2: {'text': '§ 220.2 Definitions.\nThe terms...', 'headings': ['§ 220.2 Definitions.']}}
    assert pdf.outline_without_bookmarks(read, [5, 6]) == ('readings', [[1, 'PART 220 CREDIT', 1], [1, '§ 220.1 Authority.', 1],
                                                                       [1, '§ 220.2 Definitions.', 2]])
    on_its_layer = {1: read[1], 2: {'text': None, 'headings': None}}
    assert pdf.outline_without_bookmarks(on_its_layer, [5, None]) == ('pages', [[1, 'Page 5', 1], [1, 'Page 2', 2]])
    assert pdf.outline_without_bookmarks(None, [5, 6])[0] == 'pages'


def test_a_heading_with_no_text_of_its_own_becomes_the_parent_of_the_next_where_the_readings_made_the_outline():
    # Loader 6 (decision 143.a): the EU regulation's 'Article 50' stands over its title with nothing between them
    pages = ['CHAPTER III\nArticle 50\nInformation on costs\n1. Firms shall aggregate costs.\nArticle 51\nOther information\nText.']
    toc = [[1, 'CHAPTER III', 1], [1, 'Article 50', 1], [1, 'Information on costs', 1], [1, 'Article 51', 1],
           [1, 'Other information', 1]]
    folded = pdf.build_sections('s', pages, [47], toc, fold_headings=True)
    assert [s.heading_path for s in folded] == [['CHAPTER III', 'Article 50', 'Information on costs'],
                                                ['Article 51', 'Other information']]
    assert folded[0].text == 'Information on costs\n1. Firms shall aggregate costs.'
    # an outline from bookmarks keeps its sections as they are, the empty ones too
    assert len(pdf.build_sections('s', pages, [47], toc)) == 5


def test_the_views_outline_nests_a_heading_with_no_text_of_its_own_as_the_sections_do():
    # Loader 6 in the export too (line 2's check, 9 Nov): the views' chapters nest as the chat's sections
    pages = ['CHAPTER III\nArticle 50\nInformation on costs\n1. Firms shall aggregate costs.\nArticle 51\nOther information\nText.']
    toc = [[1, 'CHAPTER III', 1], [1, 'Article 50', 1], [1, 'Information on costs', 1], [1, 'Article 51', 1],
           [1, 'Other information', 1]]
    units = pdf.outline_of(toc, pages, fold_headings=True).units
    assert [(unit.title, unit.level, unit.parent) for unit in units] == [
        ('CHAPTER III', 1, None), ('Article 50', 2, 'u001'), ('Information on costs', 3, 'u002'), ('Article 51', 1, None),
        ('Other information', 2, 'u004')]
    assert all(unit.level == 1 and unit.parent is None for unit in pdf.outline_of(toc, pages).units)


def test_a_heading_only_section_holds_no_word_beyond_its_title():
    assert pdf.heading_only('Article 33', '33 Article 33') and pdf.heading_only('Article 50', 'Article 50')
    assert not pdf.heading_only('Article 50\n1. Firms shall', 'Article 50') and not pdf.heading_only('', 'Article 50')


def test_an_outline_of_a_single_entry_counts_as_none(tmp_path):
    # Loader 6: the EU regulation's one bookmark is its title over all 83 pages
    document = pymupdf.open()
    for words in ('Article 1\nThe first article of the act.', 'Article 2\nThe second article of the act.'):
        document.new_page().insert_text((72, 72), words)
    document.set_toc([[1, 'Commission Delegated Regulation', 1]])
    document.save(tmp_path / 'act.pdf')
    assert pdf.read_pdf(tmp_path / 'act.pdf').toc_source == 'pages'
    assert [s.title for s in pdf.load_pdf_sections('act', tmp_path / 'act.pdf')] == ['Page 1', 'Page 2']


def test_a_page_by_page_cut_serves_the_sections_and_leaves_the_views_outline_empty(tmp_path):
    document = pymupdf.open()
    for words in ('First page of the rule, long enough to be text.', 'Second page of the rule, with more text.'):
        document.new_page().insert_text((72, 72), words)
    document.save(tmp_path / 'rule.pdf')
    text = pdf.read_pdf(tmp_path / 'rule.pdf')
    assert text.toc_source == 'pages' and text.outline_toc == [] and len(text.toc) == 2
    assert [s.title for s in pdf.load_pdf_sections('rule', tmp_path / 'rule.pdf')] == ['Page 1', 'Page 2']
    assert pdf.load_pdf_outline(tmp_path / 'rule.pdf').units == []


def test_an_outline_entry_pointing_backwards_does_not_duplicate_the_book():
    # Measured on the finance book: a trailing "Blank Page" entry points to page 2.
    pages = ['front', 'Part A\na text', 'Part B\nb text', 'b continues']
    toc = [[1, 'Part A', 2], [1, 'Part B', 3], [1, 'Blank Page', 1]]
    sections = pdf.build_sections('s', pages, [1, 2, 3, 4], toc)
    total = sum(len(s.text) for s in sections)
    assert total <= sum(len(p) for p in pages)
    assert [s.title for s in sections] == ['Part A', 'Part B']


def test_a_title_not_found_on_its_page_starts_where_the_previous_entry_did():
    pages = ['1.1 Found\ntext one\ntext two']
    toc = [[1, '1.1 Found', 1], [1, 'Not On The Page', 1]]
    starts = pdf.section_starts(toc, pages)
    assert starts[1][1] == starts[0][1]


def test_a_heading_set_in_capitals_is_found_at_the_start_of_its_line():
    # Phase 6: the Kelly paper's PDF p. 14 sets "DATA AVAILABILITY STATEMENT" in capitals; its outline is in title case.
    page = 'Table 5 | Growth rates\n|a|b|\nDATA AVAILABILITY STATEMENT\nThe data are available.'
    assert pdf._find_title(page, 'Data Availability Statement', 0) == page.index('DATA')
    # Only at a line's start: the title's words inside a sentence are not its heading.
    assert pdf._find_title('we give a data availability statement below', 'Data Availability Statement', 0) is None
    # The outline's own spelling comes first, so a heading found before the change is found where it was.
    both = 'RESULTS IN BRIEF\nsome text\nResults\nmore'
    assert pdf._find_title(both, 'Results', 0) == both.index('Results\nmore')


def test_text_above_a_back_matter_heading_in_capitals_stays_with_the_unit_before():
    # Before the fix the heading was not found, the back-matter unit began at the top of its page, and the table above the
    # heading went out of the index with the back matter.
    pages = ['4. Conclusions\nThe growth rate peaks.', 'Table 5 | Growth by rebalancing\nDATA AVAILABILITY STATEMENT\nOn request.']
    toc = [[1, '4. Conclusions', 1], [1, 'Data Availability Statement', 2]]
    (conclusions,) = pdf.build_sections('s', pages, [1, 2], toc)
    assert 'Table 5 | Growth by rebalancing' in conclusions.text and 'On request' not in conclusions.text


def test_a_heading_in_capitals_must_stand_as_a_line_of_its_own():
    # The review of 6 Nov: a line that begins with the title's words is a sentence, not the heading.
    page = '5 SUMMARY\nWe close.\ndiscussions of risk follow.\nDISCUSSION\nThe risks.'
    assert pdf._find_title(page, 'Discussion', 0) == page.index('DISCUSSION')
    assert pdf._find_title('index funds track the market.\nmore', 'Index', 0) is None


def test_a_heading_above_the_previous_entry_is_found_where_the_page_prints_it():
    # The Kelly paper's PDF p. 15: the outline lists Acknowledgments before References, the page prints References first.
    # Before, Acknowledgments raised the floor, References was placed at it, and the reference list fell under Author
    # Contributions.
    page = 'AUTHOR CONTRIBUTIONS\nBoth authors.\nREFERENCES\n1. A paper.\nACKNOWLEDGMENTS\nWe thank.'
    toc = [[1, 'Author Contributions', 1], [1, 'Acknowledgments', 1], [1, 'References', 1]]
    starts = {path[-1]: position for _, position, path in pdf.section_starts(toc, [page])}
    assert starts == {'Author Contributions': 0, 'References': page.index('REFERENCES'), 'Acknowledgments': page.index('ACKNOWLEDGMENTS')}


@pytest.mark.parametrize('before, after, marked, expected', [
    ('the return of the', 'period is eight percent.', True, ('the return of the', ' ')),
    ('The return ends here', 'A new paragraph starts.', False, ('The return ends here', '\n\n')),
    ('the return of the', 'period is eight percent.', None, ('the return of the', ' ')),
    ('The return is eight percent.', 'more follows', None, ('The return is eight percent.', '\n\n')),
    ('the hold-', 'ing period', None, ('the hold', '')),
    ('see the table', 'Table 3.2 shows it', None, ('see the table', '\n\n')),
])
def test_two_pages_join_as_the_reader_marked_or_by_rule(before, after, marked, expected):
    assert pdf.joiner(before, after, marked) == expected


def test_a_section_over_a_page_boundary_is_stitched_and_its_page_marks_still_point_at_each_page():
    pages = ['1 Intro\nThe holding period return of an asset over the', 'period is its gain divided by its price.', 'Next page.']
    toc = [[1, '1 Intro', 1]]
    routes = {1: ('vision reading (m)', 'k1'), 2: ('text layer: the reader declined the page', None), 3: ('vision reading (m)', 'k3')}
    section = pdf.build_sections('s', pages, [1, 2, 3], toc, continues=[None, True, False], routes=routes)[0]
    assert 'over the period is its gain' in section.text and 'price.\n\nNext page.' in section.text
    for offset, pdf_page, _ in section.pages:
        assert section.text[offset:].startswith(pages[pdf_page - 1].strip()[:10])
    assert section.routes == routes


def test_the_outline_is_the_sections_own_cut_with_back_matter_marked_and_a_shared_page_under_both_units():
    pages = ['cover', 'Chapter 1 Money\nintro\n1.1 Coins\ncoins', 'more coins\n1.2 Notes\nnotes', 'References\n[1] A. Author.']
    toc = [[1, 'Chapter 1 Money', 2], [2, '1.1 Coins', 2], [2, '1.2 Notes', 3], [1, 'References', 4]]
    outline = pdf.outline_of(toc, pages)
    chapter, coins, notes, references = outline.units
    assert (chapter.level, chapter.parent, chapter.first_page, chapter.last_page) == (1, None, 2, 3)
    assert (coins.parent, coins.first_page, coins.last_page) == (chapter.id, 2, 3) and notes.parent == chapter.id
    assert chapter.indexed and not references.indexed
    assert outline.page_units == {2: [chapter.id, coins.id], 3: [coins.id, notes.id], 4: [references.id]}
    sections = pdf.build_sections('s', pages, [None, 1, 2, 3], toc)
    indexed = {unit.id for unit in outline.units if unit.indexed}
    assert {page for section in sections for _, page, _ in section.pages} == {
        page for page, units in outline.page_units.items() if indexed & set(units)}


def test_the_outline_keeps_an_entry_pointing_backwards_in_reading_order_and_marks_it():
    pages = ['front', 'Part A\na text', 'Part B\nb text', 'b continues']
    toc = [[1, 'Part A', 2], [1, 'Part B', 3], [1, 'Blank Page', 1]]
    outline = pdf.outline_of(toc, pages)
    assert [unit.title for unit in outline.units] == ['Blank Page', 'Part A', 'Part B']
    assert not outline.units[0].indexed and outline.units[2].last_page == 4
