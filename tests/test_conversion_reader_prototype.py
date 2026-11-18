"""The checks that measure a reader prototype against what a person recorded (decision 207.a), on invented blocks."""

from backend.conversion.measurement import reader_prototype
from backend.conversion.contract.page_contract import Block, Cell, ParsedPage


def page(*blocks: Block) -> ParsedPage:
    return ParsedPage('markdown', {}, list(blocks))


def block(cls: str, body: str = '', rows=None, **attrs) -> Block:
    return Block('b01', cls, attrs, body, 1, rows=rows)


def test_a_crossing_counts_by_the_year_named_where_the_lines_meet():
    wrong = 'A chart from the late 1940s to 2020. The blue line overtakes the red one around 2000 and ends higher.'
    right = 'A chart from the late 1940s to 2020. The blue line crosses the red one between 2010 and 2015, near 2012.'
    assert not reader_prototype.chart_crossing(page(block('description', wrong)))[0]
    assert reader_prototype.chart_crossing(page(block('description', right)))[0]  # 1940s before the crossing word does not count
    assert not reader_prototype.chart_crossing(page(block('description', 'Both lines rise.')))[0]


def test_a_row_is_as_wide_as_its_cells_and_the_cells_reaching_down_from_above():
    shifted = block('table', rows=[[Cell('Assets', colspan=2), Cell('='), Cell('Liabilities', colspan=2)],
                                   [Cell('Debit'), Cell('Credit'), Cell('Debit'), Cell('Credit')]])
    even = block('table', rows=[[Cell('Year', rowspan=2), Cell('Cash', colspan=2)], [Cell('In'), Cell('Out')]])
    assert reader_prototype.row_widths(shifted) == [5, 4] and not reader_prototype.equal_rows(page(shifted))[0]
    assert reader_prototype.row_widths(even) == [3, 3] and reader_prototype.equal_rows(page(even))[0]


def test_a_photo_passes_with_no_text_read_from_it():
    assert not reader_prototype.no_photo_text(page(block('figure', 'OPEN\nMain St', kind='photo')))[0]
    assert reader_prototype.no_photo_text(page(block('figure', '', kind='photo')))[0]
    assert reader_prototype.no_photo_text(page(block('decoration', '', kind='chapter_art')))[0]


def test_t_accounts_journal_boxes_index_numbers_and_a_title_each_by_what_the_person_recorded():
    eleven = page(*[block('table', rows=[[Cell('Cash', colspan=2)]]) for _ in range(11)])
    assert reader_prototype.t_accounts_as_tables(eleven)[0]
    assert not reader_prototype.t_accounts_as_tables(page(block('figure', 'Cash\nAug. 1 70,000', kind='diagram')))[0]
    boxes = [block('table', rows=[[Cell('Petty Cash'), Cell('150')]]) for _ in range(3)]
    assert reader_prototype.journal_boxes_read(page(*boxes))[0]
    assert not reader_prototype.journal_boxes_read(page(*boxes, block('table', status='unreadable')))[0]
    assert reader_prototype.index_number(page(block('index_entry', 'accumulated depletion, 655')))[0]
    assert not reader_prototype.index_number(page(block('index_entry', 'accumulated depletion 489')))[0]
    assert reader_prototype.table_title(page(block('heading', 'Types of Business Structures')))[0]
    assert not reader_prototype.table_title(page(block('caption', 'Table 2.1')))[0]


def test_each_prototype_version_is_measured_on_its_own_cells_alone():
    # 18 Nov: the cell list was every prototype cell, so page/3's readings of the mini pilot would have stood in for page/2's
    from backend.conversion.reading import reading_cells

    versions = reader_prototype.VERSIONS
    assert set(versions['page/2']['cells']) == {'P2-MP-SM', 'P2-WALK-SM'}
    assert set(versions['page/3']['cells']) == {'P3-MP-SM', 'P3-BS-SM'}
    for name, version in versions.items():
        assert {reading_cells.READER_PROTOTYPE_CELLS[cell].reader_version for cell in version['cells']} == {name}
