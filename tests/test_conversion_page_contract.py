import json
from pathlib import Path

import pytest
from docling_core.types.doc import DocItemLabel

from backend.conversion.contract import page_contract
from backend.conversion.contract.page_contract import Expected, callout_number, parse, strip_callouts

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'page_contract'
PROMPTS = Path(page_contract.__file__).resolve().parents[1] / 'prompts'  # conversion/prompts since 208.b
P179 = (FIXTURES / 'openstax-finance-2e_p0179.page.md').read_text(encoding='utf-8')
P446 = (FIXTURES / 'openstax-finance-2e_p0446.page.md').read_text(encoding='utf-8')
EXPECTED = Expected('openstax-finance-2e', 179, (1688, 2184))


def errors_of(text: str, expected: Expected | None = EXPECTED) -> str:
    return ' | '.join(parse(text, 'markdown', expected).errors)


def changed(old: str, new: str) -> str:
    assert old in P179, old
    return P179.replace(old, new, 1)


@pytest.mark.parametrize('name', sorted(path.name for path in FIXTURES.glob('*.page.md')))
def test_the_example_pages_pass(name):
    page = parse((FIXTURES / name).read_text(encoding='utf-8'), 'markdown')
    assert page.valid, page.errors
    assert page.warnings == []


def test_the_page_is_read_into_its_parts():
    page = parse(P179, 'markdown', EXPECTED)
    assert page.front['printed_label'] == '165' and page.front['language'] == 'en'
    assert [block.id for block in page.blocks][:3] == ['b01', 'b02', 'b03']
    assert page.block('b05').attrs['label'] == '6.3' and page.block('b05').bbox == (456, 339, 1232, 415)
    assert page.block('b05').body.startswith(r'\text{Average Accounts Receivable}')
    assert page.block('b17').inline['math'] == [r'\text{ART} = 8.46', r'\text{ART} = 6.13']
    assert page.block('b22').inline['spans'][0]['class'] == 'term'
    assert [[cell.text for cell in row] for row in page.block('b11').rows][3] == ['Net Credit Sales', '$550,000', '$460,000']
    assert page.block('b11').rows[0][1].header


def test_a_code_body_stays_byte_identical():
    page = parse(P446, 'markdown')
    assert 'Pr(>|t|)' in page.block('b03').body and page.block('b11').body.startswith('> a <- data.frame(SP500=6)')
    assert page.block('b03').attrs['cont'] == 'prev'


# The defects section 3.4 of the design plants, each caught by name.
@pytest.mark.parametrize('broken, expected', [
    (changed('\\$25{,}000\n:::\n', '\\$25{,}000\n'), 'opens inside another block'),
    (P179[:P179.index('Upon initial review')], 'block is not closed'),
    (changed('::: {#b07', 'Stray sentence written between blocks.\n\n::: {#b07'), 'text outside any block'),
    (changed('.box kind=feature bbox="194 666', '.sidebar kind=feature bbox="194 666'), "unknown class 'sidebar'"),
    (changed('of=b11', 'of=b99'), 'points to no block on this page'),
    (changed('.heading in=b08', '.heading in=b05'), 'in= must point to a box'),
    (changed('::: {#b21 .heading', '::: {#b30 .description form=prose}\nA table.\n:::\n\n::: {#b21 .heading'), ".description requires 'of'"),
    (changed(r'\(\text{ART} = 8.46\)', r'$\text{ART} = 8.46$'), 'LaTeX command outside math'),
    (changed(r'\(\text{ART} = 8.46\)', r'$\text{ART} = 8.46$'), 'possible $...$ math'),
    (changed(r'\(\text{ART} = 6.13\)', r'\(\text{ART} = 6.13'), 'unbalanced inline math'),
    (changed('bbox="464 906 1224 1066"', 'bbox="464 906 1224 2666"'), 'outside the image'),
    (changed('{#b15 ', '{#b14 '), 'duplicate id'),
    (changed('::: {#b07', '::: {#b30 .code kind=listing lang=markdown bbox="194 502 1477 655"}\n::: note\nA note\n:::\n:::\n\n::: {#b07'),
     'opens inside another block'),
    # The four checks the revision added.
    (changed('::: {#b21 .heading', '::: {#b30 .footnote bbox="194 1900 1000 1920"}\nA note without a marker.\n:::\n\n::: {#b21 .heading'),
     "requires 'marker' unless it continues"),
    (changed('of=b11', 'of="@somewhere"'), 'malformed binding'),
    (changed('.heading in=b08', '.heading in="@prev"'), 'in= stays on this page'),
    (changed('bbox="194 153 1426 240"', 'bbox="194 153 194 240"'), 'has no area'),
    # Further rules of the contract.
    (changed('.formula label="6.3"', '.formula label="(6.3)"'), 'without brackets'),
    (changed('.paragraph cont=prev', '.paragraph cont=sideways'), 'cont='),
    (changed('bbox="194 251 1494 328"', ''), 'requires a bbox'),
    (changed('Total Asset Turnover', '# Total Asset Turnover'), 'without # marks'),
    (changed(r'\text{Accounts Receivable Turnover}', r'\[\text{Accounts Receivable Turnover}'), 'bare LaTeX'),
    (changed('contract: page/1', 'contract: page/2'), 'is not page/1'),
    (changed('page_kind: body', 'page_kind: novel'), "page_kind='novel'"),
    (changed('pdf_page: 179', 'pdf_page: 180'), 'asked for 179'),
    (changed('work: openstax-finance-2e', 'work: other-work'), 'asked for'),
    (changed('image_size: "1688x2184"', 'image_size: "1600x2184"'), 'the image is'),
    (changed('printed_label: "165"\n', ''), "'printed_label' missing"),
    (changed('<td>80,000</td>', '<td>80,000<div>x</div></td>'), 'unexpected tag <div>'),
    (changed('Based on the information provided', 'Based on<sup>8</sup> the information'), 'HTML in prose'),
    (changed(r'\$20{,}000', r'$20{,}000'), 'dollar sign inside math'),
    # page/1.5 (49.a): the number belongs in label=; MinerU's test readings wrote it as LaTeX's \tag (finance p. 343)
    (changed(r'= \$25{,}000', r'= \$25{,}000 \tag{6.3}'), 'equation number inside the formula'),
    (changed(r'= \$25{,}000', r'= \$25{,}000 \tag*{6.3}'), 'equation number inside the formula'),
])
def test_a_planted_defect_is_caught(broken, expected):
    assert expected in errors_of(broken)


# Mini pilot, 2026-10-30: most invalid readings failed on these, with every word intact. A retry would pay for nothing.
@pytest.mark.parametrize('broken, expected', [
    (changed('<td>80,000</td><td>90,000</td>', '<td>80,000</td>'), 'ragged table'),
    (changed('.formula label="6.3"', '.formula label="6.3" caption=none'), "attribute 'caption' not allowed"),
    (changed('.heading in=b08 bbox="211 753', '.heading level=2 in=b08 bbox="211 753'), "attribute 'level' not allowed"),
    (changed('.box kind=feature bbox="194 666', '.box kind=shiny bbox="194 666'), "kind='shiny'"),
    (changed('[Total asset turnover]{.term}', '[Total asset turnover]{.link}'), 'unknown inline class'),
])
def test_what_loses_no_text_is_a_warning_and_the_reading_stays_valid(broken, expected):
    page = parse(broken, 'markdown', EXPECTED)
    assert page.valid, page.errors
    assert expected in ' | '.join(page.warnings)


def test_a_bare_dollar_inside_inline_math_is_repaired():
    page = parse(changed(r'\(\text{ART} = 8.46\)', r'\($8.46 + $2\)'), 'markdown', EXPECTED)
    assert page.valid, page.errors
    assert page.block('b17').inline['math'][0] == r'\$8.46 + \$2' and 'bare dollar' in ' '.join(page.warnings)


def test_a_stray_attribute_is_dropped():
    page = parse(changed('.formula label="6.3"', '.formula label="6.3" caption=none'), 'markdown', EXPECTED)
    assert 'caption' not in page.block('b05').attrs


def test_bold_in_a_table_cell_loses_nothing():
    page = parse(changed('<td>80,000</td>', '<td><strong>80,000</strong></td>'), 'markdown', EXPECTED)
    assert page.valid and page.block('b11').rows[2][1].text == '80,000'


# page/1.4 (18 Nov): a backslash the page prints as text is written &#92;, in prose and in a table cell alike.
def test_a_backslash_written_as_an_entity_is_text():
    page = parse(changed('Based on the information provided', 'Based on rate&#92;term provided'), 'markdown', EXPECTED)
    assert page.valid, page.errors
    assert page.block('b13').inline['plain'].startswith('Based on rate\\term provided')
    cell = parse(changed('<td>80,000</td>', '<td>rate&#92;term</td>'), 'markdown', EXPECTED)
    assert cell.valid, cell.errors
    assert cell.block('b11').rows[2][1].text == 'rate\\term' and cell.block('b11').rows[2][1].source == 'rate&#92;term'


@pytest.mark.parametrize('written', ['rate\\term', 'rate\\\\term'])  # bare, and as Markdown's escape: a doubled \\frac looks so
def test_every_other_spelling_of_a_printed_backslash_still_fails(written):
    assert 'LaTeX command outside math' in errors_of(changed('Based on the information provided', f'Based on {written}'))
    assert 'LaTeX command outside math' in errors_of(changed('<td>80,000</td>', f'<td>{written}</td>'))


def line_of(text: str, needle: str) -> int:
    """The page's line a needle stands on, counted from 1 as the validator counts."""
    return next(number for number, line in enumerate(text.split('\n'), 1) if needle in line)


@pytest.mark.parametrize('old, new, needle, said', [
    ('Based on the information provided', 'Based on the information\nprovided \\HL here', '\\HL here',
     'LaTeX command outside math on line {}: \\HL'),
    ('<td>90,000</td></tr>', '<td>90,000</td></tr>\n<tr><td>a</td><td>b</td><td>c \\alpha</td></tr>', 'c \\alpha',
     'LaTeX command outside math on line {}: \\alpha'),
    ('Based on the information provided', 'Based on the information\nprovided <sup>8</sup>', '<sup>8</sup>',
     'HTML in prose on line {} '),
    ('Based on the information provided', 'Based on the information\ncosts $a_1$ provided', '$a_1$',
     'possible $...$ math on line {} '),
])
def test_a_problem_names_the_line_it_stands_on(old, new, needle, said):
    broken = changed(old, new)
    errors = errors_of(broken)
    assert said.format(line_of(broken, needle)) in errors, errors  # the block's opening line stands lines above it


def test_without_a_line_a_problem_is_named_as_before():
    """The JSON form has no lines, and a caller that gives none gets the message as page/1.3 wrote it."""
    assert page_contract.parse_inline('a \\HL b')['problems'] == ['LaTeX command outside math: \\HL']
    assert page_contract.parse_table('<table><tr><td>a \\HL</td></tr></table>')[1] == ['LaTeX command outside math: \\HL']


def test_a_listing_that_holds_a_fence_line_needs_a_longer_fence():
    block = ':::: {#b30 .code kind=listing lang=markdown bbox="194 502 1477 655"}\n::: note\nA note\n:::\n::::\n\n'
    page = parse(changed('::: {#b07', block + '::: {#b07'), 'markdown', EXPECTED)
    assert page.valid, page.errors
    assert page.block('b30').body == '::: note\nA note\n:::'


def test_a_lost_json_escape_is_caught_in_either_form():
    # \t in a JSON string that should have been \\t: the body holds a TAB, and KaTeX would still render it.
    assert 'control character' in errors_of(changed(r'\text{Average', '\text{Average'))


def test_detached_bindings_are_accepted():
    for binding in ('@label:Figure 12.3', '@prev', '@next'):
        assert parse(changed('of=b11', f'of="{binding}"'), 'markdown', EXPECTED).valid


def test_a_continued_caption_or_footnote_needs_no_label_or_marker_and_does_not_count_as_a_second_caption():
    extra = ('::: {#b30 .caption of=b11 cont=prev in=b08 bbox="506 1104 1182 1120"}\nFigure 6.3 (continued)\n:::\n\n'
             '::: {#b31 .footnote cont=prev bbox="194 2000 1000 2020"}\nthe end of a note from the page before.\n:::\n\n')
    page = parse(changed('::: {#b21 .heading', extra + '::: {#b21 .heading'), 'markdown', EXPECTED)
    assert page.valid, page.errors
    assert page.warnings == []
    second = '::: {#b30 .caption of=b11 in=b08 bbox="506 1104 1182 1120"}\nFigure 6.3 again\n:::\n\n'
    assert 'b11 has 2 captions' in ' '.join(parse(changed('::: {#b21 .heading', second + '::: {#b21 .heading'), 'markdown', EXPECTED).warnings)


BOX = 'bbox="194 2000 1000 2020"'


@pytest.mark.parametrize('extra, warning', [
    # page/1.2 (2026-11-08), each from a page of the licensed round 6 that was malformed though no text was lost.
    (f'::: {{#b30 .list_item cont=prev {BOX}}}\nthe end of an item begun on the page before.\n:::\n\n', None),
    (f'::: {{#b30 .caption cont=prev {BOX}}}\nTABLE 18. (continued)\n:::\n\n', None),
    (f'::: {{#b30 .callout marker="1" of=b11 {BOX}}}\n=AVERAGE(B2:B14)\n:::\n\n', None),
    (f'::: {{#b30 .list_item marker="(iv)" {BOX}}}\nAn item.\n:::\n\n'
     '::: {#b31 .paragraph in=b30 bbox="194 2030 1000 2050"}\nIts second paragraph.\n:::\n\n', None),
    (f'::: {{#b30 .decoration {BOX}}}\n:::\n\n', "without 'kind'"),
    (f'::: {{#b30 .footnote kind=table of=b11 {BOX}}}\n*Note:* Continuously compounded rates of return.\n:::\n\n',
     'a table note without a marker'),
    (f'::: {{#b30 .toc_entry level=1 {BOX}}}\nChapter Four. Portfolio Allocation\t69\n:::\n\n', 'a tab between title and page'),
    (f'::: {{#b30 .list_item marker="" kind=definition defines=@prev {BOX}}}\nalpha = unconditional alpha\n:::\n\n',
     'defines= written without quotes'),
    (f'::: {{#b30 .caption of=@label:Figure\\ 5-20 {BOX}}}\nFigure 5-20. Grid lines in a table.\n:::\n\n', 'of= written without quotes'),
    (f'::: {{#b30 .list_item marker="\\(\\sigma_{{\\text{{down}}}}\\)" kind=definition {BOX}}}\n= target semideviation.\n:::\n\n',
     'a brace inside a quoted value'),
])
def test_what_loses_no_text_passes_with_a_warning_at_most(extra, warning):
    page = parse(changed('::: {#b21 .heading', extra + '::: {#b21 .heading'), 'markdown', EXPECTED)
    assert page.valid, page.errors
    assert (page.warnings == []) if warning is None else any(warning in notice for notice in page.warnings), page.warnings


def test_the_mended_attributes_keep_their_values():
    extra = (f'::: {{#b30 .caption of=@label:Figure\\ 5-20 {BOX}}}\nFigure 5-20.\n:::\n\n'
             f'::: {{#b31 .list_item marker="\\(\\sigma_{{\\text{{down}}}}\\)" kind=definition {BOX}}}\n= x.\n:::\n\n'
             f'::: {{#b32 .toc_entry level=1 {BOX}}}\nChapter Four\t69\n:::\n\n')
    page = parse(changed('::: {#b21 .heading', extra + '::: {#b21 .heading'), 'markdown', EXPECTED)
    assert page.block('b30').attrs['of'] == '@label:Figure 5-20'
    assert page.block('b31').attrs['marker'] == r'\(\sigma_{\text{down}}\)'
    assert page.block('b32').body == 'Chapter Four 69'


@pytest.mark.parametrize('extra, error', [
    # What page/1.2 still refuses: a missing marker or caption binding where nothing continues, a tab outside a contents
    # entry (a lost \t escape), and a block placed inside one that cannot hold it.
    (f'::: {{#b30 .list_item {BOX}}}\nAn item without its printed marker.\n:::\n\n', "requires 'marker'"),
    (f'::: {{#b30 .caption {BOX}}}\nFigure 9.9 A caption bound to nothing.\n:::\n\n', "requires 'of'"),
    (f'::: {{#b30 .footnote kind=foot {BOX}}}\nA footnote without its marker.\n:::\n\n', "requires 'marker'"),
    (f'::: {{#b30 .paragraph {BOX}}}\nA \text that lost its escape.\n:::\n\n', 'a control character'),
    (f'::: {{#b30 .toc_entry level=1 {BOX}}}\nChapter\t4\f\n:::\n\n', 'a control character'),
    (f'::: {{#b30 .paragraph {BOX}}}\nOne.\n:::\n\n::: {{#b31 .paragraph in=b30 bbox="194 2030 1000 2050"}}\nTwo.\n:::\n\n',
     'in= must point to a box or a list item'),
])
def test_what_page_1_2_still_refuses(extra, error):
    assert error in errors_of(changed('::: {#b21 .heading', extra + '::: {#b21 .heading'))


def test_a_table_may_group_its_rows_span_cells_and_break_lines_in_a_cell():
    table = ('<table><thead><tr><th rowspan="2">Item</th><th colspan="2">Year</th></tr><tr><th>2020</th><th>2021</th></tr></thead>'
             '<tbody><tr><th colspan="3">Assets</th></tr><tr><td>Cash<br>and bank</td><td>&lt;1</td><td></td></tr></tbody></table>')
    page = parse(changed(P179[P179.index('<table>'):P179.index('</table>') + 8], table), 'markdown', EXPECTED)
    assert page.valid, page.errors
    assert page.block('b11').rows[3][0].text == 'Cash and bank' and page.block('b11').rows[3][1].text == '<1'


def test_a_value_that_looks_like_something_else_stays_a_string():
    page = parse(changed('language: en', 'language: no'), 'markdown', EXPECTED)
    assert page.valid and page.front['language'] == 'no' and page.front['pdf_page'] == '179'


def test_a_dollar_amount_is_not_math():
    assert parse(P179, 'markdown', EXPECTED).block('b04').inline['problems'] == []


def test_dollar_amounts_inside_inline_math_are_not_dollar_math():
    body = 'The total is ' + chr(92) + '(' + chr(92) + '$1{,}000 + ' + chr(92) + '$2{,}000' + chr(92) + ') in all.'
    assert parse(changed('Based on the information provided, do the following:', body), 'markdown', EXPECTED).valid


@pytest.mark.parametrize('body', [
    'It bought back $18.5 billion of its own stock in 2020.[1]{.fn} Later it spent $2 billion more.',
    'The bond pays $1,000; the period is 7 [years]{.sup} and the coupon is $40.',
    r'<table><tr><td>$20,000</td><td>Common Stock<br>+\$20,000</td></tr></table>',
])
def test_a_dollar_amount_before_an_inline_mark_or_an_escaped_dollar_is_not_math(body):
    page = parse(changed('Based on the information provided, do the following:', body), 'markdown', EXPECTED)
    assert not any('possible $...$ math' in error for error in page.errors), page.errors


def test_dollar_math_is_still_caught_beside_an_inline_mark():
    body = 'The slope is $x^2$ here.[1]{.fn}'
    page = parse(changed('Based on the information provided, do the following:', body), 'markdown', EXPECTED)
    assert any('possible $...$ math' in error for error in page.errors)


def test_a_gap_and_an_uncertain_reading_are_counted():
    body = 'Read [0.05]{.unclear alt="0.06"} and []{.gap reason="illegible" extent="3 words"} here.'
    record = parse(changed('Based on the information provided, do the following:', body), 'markdown', EXPECTED).as_dict()
    assert (record['unclear'], record['gaps']) == (1, 1)


@pytest.mark.parametrize('character, number', [('①', 1), ('⑳', 20), ('⓫', 11), ('⓴', 20), ('❶', 1), ('➀', 1), ('➊', 1), ('➓', 10), ('㉑', 21), ('㊱', 36), ('㊿', 50)])
def test_every_circled_digit_family_is_a_callout(character, number):
    assert callout_number(character) == number
    assert strip_callouts(f'x = 1  {character}\ny = 2') == ('x = 1\ny = 2', {1: [number]})


def test_two_callouts_on_a_line_and_ordinary_characters():
    assert strip_callouts('x = 1 ① ②') == ('x = 1', {1: [1, 2]})
    assert callout_number('x') is None and callout_number('•') is None


def test_the_examples_in_the_prompts_follow_the_contract_and_agree():
    markdown = (PROMPTS / 'reader_page1_markdown.txt').read_text(encoding='utf-8')
    as_json = (PROMPTS / 'reader_page1_json.txt').read_text(encoding='utf-8')
    expected = Expected('example-work', 42, (1688, 2184))
    one = parse(markdown[markdown.index('---\ncontract'):], 'markdown', expected)
    other = parse(as_json[as_json.rindex('{"front"'):], 'json', expected)
    assert one.valid and other.valid and not one.warnings, (one.errors, other.errors)
    assert one.front == other.front
    assert [(block.id, block.cls, block.attrs, block.body) for block in one.blocks] == [
        (block.id, block.cls, block.attrs, block.body) for block in other.blocks]


def test_the_prompts_name_every_class_and_every_attribute():
    rules = (PROMPTS / 'reader_page1_rules.txt').read_text(encoding='utf-8')
    for name, spec in page_contract.VOCAB['classes'].items():
        assert name in rules, name
        for attribute in spec['attrs']:
            assert attribute in rules, (name, attribute)
        for kind in spec.get('kinds', []):
            assert kind in rules, (name, kind)


def test_json_that_is_not_a_page_is_malformed_not_a_crash():
    assert 'not JSON' in ' '.join(parse('{"front": [', 'json').errors)
    assert 'not a page object' in ' '.join(parse('[1, 2]', 'json').errors)
    with pytest.raises(ValueError):
        parse('x', 'yaml')


def test_the_json_schema_has_what_structured_outputs_require():
    def objects(node):
        if isinstance(node, dict):
            if node.get('type') == 'object':
                yield node
            for value in node.values():
                yield from objects(value)
        elif isinstance(node, list):
            for value in node:
                yield from objects(value)

    schema = page_contract.json_schema()
    assert all(node['additionalProperties'] is False and set(node['required']) == set(node['properties']) for node in objects(schema))
    json.dumps(schema)


@pytest.mark.parametrize('name, spec', sorted(page_contract.VOCAB['classes'].items()))
def test_every_class_maps_to_a_docling_label_or_says_why_not(name, spec):
    if spec['docling_label'] is None:
        assert spec['docling_note'], name
    else:
        DocItemLabel(spec['docling_label'])


def test_results_fall_into_exactly_one_class():
    good = parse(P179, 'markdown', EXPECTED)
    assert page_contract.classify('succeeded', 'end_turn', good) == 'ok'
    assert page_contract.classify('succeeded', 'refusal', None) == 'refused'
    assert page_contract.classify('succeeded', 'max_tokens', None) == 'truncated'
    assert page_contract.classify('succeeded', 'pause_turn', None) == 'unexpected'
    assert page_contract.classify('succeeded', 'end_turn', parse('I cannot help.', 'markdown')) == 'no_page'
    assert page_contract.classify('succeeded', 'end_turn', parse(P179, 'markdown', Expected('x', 1, (1, 1)))) == 'malformed'
    assert page_contract.classify('errored', None, None) == 'errored'


def test_a_stored_record_of_the_check_holds_no_page_text():
    record = page_contract.parse(P179, 'markdown', EXPECTED).as_dict()
    assert record['blocks'] == 22 and record['classes']['formula'] == 2 and record['printed_label'] == '165'
    assert 'Accounts Receivable' not in json.dumps(record)


FRONT = P179.split('\n---\n', 1)[0] + '\n---\n'


def test_a_list_item_whose_content_is_the_table_after_it_is_a_warning_not_an_error():
    # page/1.3 (decision 212.a): "7." or "A." alone, its journal entry the table printed right below; nothing is lost
    option = '::: {#b01 .list_item marker="A." kind=point bbox="254 607 280 634"}\n:::\n\n'
    table = ('::: {#b02 .table kind=journal bbox="300 637 997 738"}\n<table><tbody><tr><td>Petty Cash</td><td>150</td></tr>'
             '</tbody></table>\n:::\n')
    page = parse(FRONT + '\n' + option + table, 'markdown', EXPECTED)
    assert page.valid and any('content is the block after it' in warning for warning in page.warnings)
    bound = option + table.replace('kind=journal', 'kind=journal in=b01')
    assert parse(FRONT + '\n' + bound, 'markdown', EXPECTED).valid  # bound with in= is the same
    paragraph = '::: {#b02 .paragraph bbox="300 637 997 738"}\nNo entry is required.\n:::\n'
    assert 'empty body' in errors_of(FRONT + '\n' + option + paragraph)  # prose after it is no content of the option
    assert 'empty body' in errors_of(FRONT + '\n' + option.replace(' marker="A."', ''))  # nor without a marker
