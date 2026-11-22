"""The labelled HTML route (22 Nov 2026): a rule text whose structure is its paragraph labels, cut into sections at them."""

import pytest

from backend.ingestion.clean_sections.html_labelled_sections import (label_kind, load_labelled_sections,
                                                                     parse_labelled_sections)
from backend.ingestion.clean_sections.html_sections import text_fragment

BASE = 'https://example.org/rules/invented-rule'
TITLE = 'Rule 9: An Invented Rule'
# An invented rule page in the shape such pages take: no h1 to h4, text straight in nested divs, titled paragraphs in bold,
# untitled ones labelled in plain text, a table, a part standing alone, and things around the text that are not the rule.
RULE = ('<div id="tabs"><button>The Rule</button><div id="body-text">'
        '<div class="intro">An opening line before any label.</div>'
        '<div><strong>(a) Words</strong></div>'
        '<div class="indent_first">For this text:</div>'
        '<div class="indent_second">(1) The term "plum" means a fruit.</div>'
        '<div class="indent_second"><p>(2) The term "pear" means:</p>'
        '<div class="indent">(A) a green one; or</div><div class="indent">(B) a brown one.</div></div>'
        '<div><strong>(b) Baskets</strong></div>'
        '<div class="indent"><strong>(1) Small Baskets</strong> A small basket holds <span>ten</span> plums.</div>'
        '<div class="indent"><strong>(A) Woven</strong> Woven ones are light.</div>'
        '<div class="indent">(B) Plastic ones are heavy, see (b)(1).</div>'
        '<div class="indent">(i) heavy when wet; and</div>'
        '<div class="indent"><strong>(2) Large Baskets</strong> Large baskets hold <strong>more</strong> fruit.</div>'
        '<table><tr><td><strong>Size</strong></td><td>Plums</td></tr><tr><td>Small</td><td>10</td></tr></table>'
        '<div class="indent">After the table the text goes on.</div>'
        '<div><strong>(h) Eights</strong></div><div><strong>(i) Nines</strong></div>'
        '<div class="indent"><strong>(1) Units</strong></div>'
        '<div class="indent"><strong>(i) Roman One</strong> A numeral here.</div>'
        '<p><strong>• • • Extra Material: ------</strong></p>'
        '<div><strong>.01 First Note.</strong> A note.</div>'
        '<div><strong>"Long" Things</strong> A run-in title.</div>'
        '</div><div id="other">Not the text.</div><script>var hidden = 1;</script></div>')


def sections_of(html: str = RULE, **kwargs) -> list:
    return parse_labelled_sections(html, '#body-text', 'invented_rule', BASE, TITLE, **kwargs)


def paths(sections: list) -> list[list[str]]:
    return [section.heading_path[1:] for section in sections]


def test_every_word_of_the_content_is_read_in_order_and_nothing_around_it():
    sections = sections_of()
    text = '\n'.join(section.text for section in sections)
    for words in ('An opening line', 'For this text:', 'a green one; or', 'heavy when wet; and', 'holds ten plums.',
                  'Small | 10', 'After the table the text goes on.', 'A run-in title.'):
        assert words in text
    assert 'Not the text' not in text and 'hidden' not in text and 'The Rule' not in text
    assert [section.ordinal for section in sections] == list(range(len(sections)))
    assert all(section.heading_path[0] == TITLE and section.source_id == 'invented_rule' for section in sections)


def test_a_bold_label_opens_a_section_at_the_level_of_its_kind():
    assert paths(sections_of()) == [
        [],
        ['(a) Words'],
        ['(b) Baskets', '(1) Small Baskets'],
        ['(b) Baskets', '(1) Small Baskets', '(A) Woven'],
        ['(b) Baskets', '(1) Small Baskets', '(B)'],
        ['(b) Baskets', '(2) Large Baskets'],
        ['(b) Baskets', '(2) Large Baskets'],
        ['(b) Baskets', '(2) Large Baskets'],
        ['(i) Nines', '(1) Units', '(i) Roman One'],
        ['Extra Material', '.01 First Note.'],
        ['Extra Material', '.01 First Note.', '"Long" Things'],
    ]


def test_a_plain_label_below_the_section_stays_in_it_and_one_beside_its_heading_opens_its_own():
    sections = sections_of()
    assert sections[1].text.splitlines() == ['For this text:', '(1) The term "plum" means a fruit.', '(2) The term "pear" means:',
                                             '(A) a green one; or', '(B) a brown one.']
    assert sections[4].text.splitlines() == ['(B) Plastic ones are heavy, see (b)(1).', '(i) heavy when wet; and']


def test_bold_inside_a_paragraph_is_emphasis_and_the_heading_is_not_repeated_in_the_text():
    sections = sections_of()
    assert sections[5].text == 'Large baskets hold more fruit.'
    assert sections[2].text == 'A small basket holds ten plums.'


def test_a_table_is_a_section_of_its_own_and_the_text_after_it_continues_its_heading():
    sections = sections_of()
    assert sections[6].text == 'Size | Plums\nSmall | 10'
    assert sections[7].text == 'After the table the text goes on.'


def test_a_part_standing_alone_closes_every_open_heading_and_a_run_in_title_nests():
    sections = sections_of()
    assert sections[9].heading_path[1] == 'Extra Material'  # bullets, dashes and the colon trimmed
    assert sections[10].text == 'A run-in title.'


def test_a_section_links_to_its_heading_or_where_its_heading_is_a_bare_label_to_its_first_words():
    sections = sections_of()
    assert sections[0].url == BASE  # before any heading: the page itself
    assert sections[1].url == f'{BASE}#{text_fragment("(a) Words")}'
    assert sections[4].url == f'{BASE}#{text_fragment("(B) Plastic ones are heavy, see (b)(1).")}'
    assert sections[7].url == f'{BASE}#{text_fragment("(2) Large Baskets")}'


@pytest.mark.parametrize('text, open_labels, kind', [
    ('(ii) two', [], 'roman'),
    ('(i) after h', [('letter', 'h')], 'letter'),
    ('(i) under e', [('letter', 'e'), ('number', '2')], 'roman'),
    ('(v) lone', [], 'roman'),
    ('(12) twelve', [], 'number'),
    ('(B) bee', [], 'upper'),
    ('.03 Note', [], 'supplement'),
    ('.031 no', [], None),
    ('see (a)', [], None),
])
def test_a_label_s_kind(text, open_labels, kind):
    assert label_kind(text, open_labels) == kind


def test_the_catalog_entry_names_the_file_its_content_and_its_noise(tmp_path):
    (tmp_path / 'invented_rule.html').write_text(RULE, encoding='utf-8')
    entry = {'id': 'invented_rule', 'file': 'invented_rule.html', 'title': TITLE, 'url': BASE,
             'labelled_sections': {'content': '#body-text', 'noise': ['.intro']}}
    sections = load_labelled_sections(entry, tmp_path)
    assert paths(sections)[0] == ['(a) Words'] and 'An opening line' not in sections[0].text


def test_a_content_element_that_is_not_there_is_an_error():
    with pytest.raises(ValueError, match='not found'):
        parse_labelled_sections(RULE, '#missing', 'invented_rule', BASE, TITLE)
