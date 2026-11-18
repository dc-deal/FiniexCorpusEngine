import html
import json
from collections import Counter

import pytest

from backend.conversion.checks import katex_check, page_checks
from backend.conversion.measurement import publisher_gold, reader_scoring
from backend.conversion.contract.page_contract import parse
from backend.conversion.measurement.publisher_gold import parse_gold
from backend.conversion.measurement.reader_scoring import canonical_math, compare_math, score_reading, summarize

HAVE_GOLD = (publisher_gold.GOLD_ROOT / 'truth').is_dir()
needs_gold = pytest.mark.skipif(not HAVE_GOLD, reason='the local gold folder is missing, as in a clone')
MIN_AGREEMENT = 0.98  # measured 1.0 (125 of 125, 2026-10-30); the margin is for gold pages added later


ANSWERS: dict[tuple[str, bool], katex_check.Rendered] = {}  # every check_many starts a child process, so each formula renders once


def rendered_many(items: list[tuple[str, bool]]) -> dict:
    missing = [item for item in dict.fromkeys(items) if item not in ANSWERS]
    ANSWERS.update(zip(missing, katex_check.check_many(missing)))
    return {item: ANSWERS[item] for item in items}


def katex(latex: str) -> str:
    result = rendered_many([(latex, True)])[(latex, True)]
    assert result.ok, (latex, result.error)
    return result.mathml


def verdicts(page) -> dict:
    """The same answers page_checks.render_formulas would give for this page."""
    return rendered_many([(formula.latex, formula.display) for formula in reader_scoring.reader_formulas(page)]
                         + [(latex, False) for block in page.blocks for row in block.rows or [] for cell in row
                            for latex in (cell.inline or {}).get('math', [])])


# Short literals from OpenStax Principles of Finance 2e and Principles of Accounting (CC BY-NC-SA 4.0) and two CC BY 4.0 papers.
# Each row: spellings that print the same. A string with '<' is MathML as a publisher writes it, anything else is LaTeX for KaTeX.
SAME = [
    ('thousands', ['1{,}000', '1,000', '<mn>1,000</mn>', '<mn>1</mn><mo>,</mo><mn>000</mn>', '<mrow><mn>1</mn><mo separator="true">,</mo><mn>000</mn></mrow>']),
    ('dollar', [r'\$5', r'\text{\$}5', '<mo>$</mo><mn>5</mn>', '<mi mathvariant="normal">$</mi><mn>5</mn>', '<mn>$5</mn>']),
    ('percent', [r'5\%', '<mn>5</mn><mo>%</mo>', '<mn>5</mn><mi>%</mi>']),
    ('words', [r'\text{FV}', r'\mathrm{FV}', r'\mathit{FV}', 'FV', '<mi>FV</mi>', '<mtext>FV</mtext>', '<mi>F</mi><mi>V</mi>', '<ms>FV</ms>']),
    ('words with spaces', [r'\text{Future Value}', r'\text{Future}\ \text{Value}', '<mtext>Future Value</mtext>', '<mi>Future</mi><mo>&nbsp;</mo><mi>Value</mi>']),
    ('limits', [r'\sum_{i=1}^{n} x', r'\sum\nolimits_{i=1}^{n} x', r'{\sum}_{i=1}^{n} x', r'\sum^{n}_{i=1} x',
                '<munderover><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow><mi>n</mi></munderover><mi>x</mi>',
                '<msubsup><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow><mi>n</mi></msubsup><mi>x</mi>',
                '<msup><msub><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow></msub><mi>n</mi></msup><mi>x</mi>',
                '<msub><msup><mo>∑</mo><mi>n</mi></msup><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow></msub><mi>x</mi>']),
    ('sub and sup nested', ['x_i^2', 'x^2_i', '{x_i}^2', '{x^2}_i', '<msubsup><mi>x</mi><mi>i</mi><mn>2</mn></msubsup>',
                            '<msup><mrow><msub><mi>x</mi><mi>i</mi></msub></mrow><mn>2</mn></msup>']),
    ('limit under an operator', [r'\max_F x', r'{\text{max}}_F x', r'\text{max}_F x', r'\underset{F}{\max} x', '<munder><mo>max</mo><mi>F</mi></munder><mi>x</mi>']),
    ('minus and hyphen', ['a-b', 'a - b', r'a \text{-} b', '<mi>a</mi><mo>-</mo><mi>b</mi>', '<mi>a</mi><mo>−</mo><mi>b</mi>', '<mi>a</mi><mo>–</mo><mi>b</mi>', '<mi>a</mi><mo>&#x2212;</mo><mi>b</mi>']),
    ('spaces', [r'a+b', r'a + b', r'a\ +\ b', r'a\quad+\,b', r'a\hspace{1em}+b', '<mi>a</mi><mspace width="1em"/><mo>+</mo><mo> </mo><mi>b</mi>', '<mi>a</mi><mo>&nbsp;</mo><mo>+</mo><mi>b</mi>']),
    ('extra rows', ['a', '{a}', '{{a}}', '<mi>a</mi>', '<mrow><mrow><mi>a</mi></mrow></mrow>', '<mstyle displaystyle="true"><mpadded><mi>a</mi></mpadded></mstyle>']),
    ('invisible operators', ['f(x)', '<mi>f</mi><mo>&#x2061;</mo><mo>(</mo><mi>x</mi><mo>)</mo>', '<mi>f</mi><mo>​</mo><mrow><mo>(</mo><mi>x</mi><mo>)</mo></mrow>']),
    ('a script on the bracket or on the group', ['(1+r)^n', '{(1+r)}^n', r'\left(1+r\right)^n', r'{\left(1+r\right)}^{n}',
                                                 '<msup><mrow><mo>(</mo><mn>1</mn><mo>+</mo><mi>r</mi><mo>)</mo></mrow><mi>n</mi></msup>',
                                                 '<msup><mfenced><mrow><mn>1</mn><mo>+</mo><mi>r</mi></mrow></mfenced><mi>n</mi></msup>']),
    ('a bar', [r'\overline{x}', r'\bar{x}', '<mover><mi>x</mi><mo>¯</mo></mover>', '<mover accent="true"><mi>x</mi><mo>‾</mo></mover>', '<mover><mi>x</mi><mo>&#x0304;</mo></mover>', '<mover><mi>x</mi><mo>-</mo></mover>']),
    ('a hat', [r'\hat{\Sigma}', r'\widehat{\Sigma}', '<mover><mi>Σ</mi><mo>^</mo></mover>', '<mover accent="true"><mi mathvariant="normal">Σ</mi><mo>ˆ</mo></mover>']),
    ('a prime', ["x'", r'x^\prime', '<mi>x</mi><mo>′</mo>', '<msup><mi>x</mi><mo>′</mo></msup>', "<mi>x</mi><mo>'</mo>"]),
    ('fractions', [r'\frac{a}{b}', r'\dfrac{a}{b}', r'\tfrac{a}{b}', r'{a \over b}', '<mfrac><mi>a</mi><mi>b</mi></mfrac>', '<mfrac><mrow><mi>a</mi></mrow><mrow><mi>b</mi></mrow></mfrac>']),
    ('layout of several lines', [r'\begin{aligned} a &= b \\ c &= d \end{aligned}', r'\begin{array}{rcl} a & = & b \\ c & = & d \end{array}', r'a = b \quad c = d',
                                 '<mtable><mtr><mtd><mi>a</mi><mo>=</mo></mtd><mtd><mi>b</mi></mtd></mtr><mtr><mtd><mi>c</mi><mo>=</mo><mi>d</mi></mtd></mtr></mtable>']),
    ('brackets kept in attributes', ['[a,b]', r'\left[a,b\right]', '<mfenced open="[" close="]"><mi>a</mi><mi>b</mi></mfenced>', '<mfenced open="[" close="]" separators=","><mi>a</mi><mi>b</mi></mfenced>']),
    ('fonts', [r'\mathbb{E}', 'E', r'\mathbf{E}', '<mi>𝔼</mi>', '<mi mathvariant="double-struck">E</mi>']),
    ('script letters', [r'\mathcal{S}', 'S', '<mi>𝒮</mi>']),
    ('epsilon', [r'\epsilon', r'\varepsilon', '<mi>ϵ</mi>', '<mi>ε</mi>']),
    ('an ellipsis', [r'\ldots', r'\cdots', r'\dots', '...', '<mo>…</mo>', '<mo>⋯</mo>']),
    ('an equation number', ['a', r'a \tag{7.5}', '<mtable><mlabeledtr><mtd><mtext>(7.5)</mtext></mtd><mtd><mi>a</mi></mtd></mlabeledtr></mtable>']),
    ('less or equal', [r'a \le b', r'a \leq b', r'a \leqslant b', '<mi>a</mi><mo>≤</mo><mi>b</mi>']),
    ('a closing stop stands on either side of the math', ['a = b', 'a = b.', 'a = b,', 'a = b;', '<mi>a</mi><mo>=</mo><mi>b</mi><mo>.</mo>']),
    ('vertical bars', ['|x|', r'\lvert x \rvert', r'\left|x\right|', '<mo>|</mo><mi>x</mi><mo>|</mo>', '<mo>∣</mo><mi>x</mi><mo>∣</mo>']),
    ('centre dots and stars', [r'a \cdot b^*', r'a \cdot b^{\ast}', '<mi>a</mi><mo>·</mo><msup><mi>b</mi><mo>*</mo></msup>', '<mi>a</mi><mo>⋅</mo><msup><mi>b</mi><mo>∗</mo></msup>']),
    ('stacked over a relation', [r'\overset{\text{def}}{=}', r'\stackrel{\text{def}}{=}', '<mover><mo>=</mo><mtext>def</mtext></mover>']),
    ('function names', [r'\log x', r'\text{log} x', r'\mathrm{log}\, x', r'\operatorname{log} x', '<mi>log</mi><mo>&#x2061;</mo><mi>x</mi>']),
]

# Each row: spellings that must not compare equal, however close they look.
DIFFERENT = [
    ('a changed digit', '1{,}000', '1{,}001'),
    ('a changed digit in a decimal', '0.04', '0.05'),
    ('a dropped digit', '$100{,}000$'.strip('$'), '10{,}000'),
    ('a thousands comma against none', '1{,}000', '1000'),
    ('a thousands comma against a decimal point', '1{,}000', '1.000'),
    ('a dropped term', 'a + b + c', 'a + b'),
    ('a dropped factor', r'\$22.50 \times 13.61', r'\$22.50'),
    ('a flipped sign', 'a + b', 'a - b'),
    ('a flipped sign in an exponent', '10^{-6}', '10^{6}'),
    ('a lost leading minus', '-0.0302', '0.0302'),
    ('a changed exponent', 'x^2', 'x^3'),
    ('an exponent on the wrong side', 'x^2', 'x_2'),
    ('an exponent read as a digit', 'x^2', 'x2'),
    ('a lost exponent', '(1+r)^n', '(1+r)'),
    ('swapped scripts', 'x_i^2', 'x_2^i'),
    ('a fraction read as a slash', r'\frac{a}{b}', 'a/b'),
    ('a flipped fraction', r'\frac{a}{b}', r'\frac{b}{a}'),
    ('a term out of the numerator', r'\frac{a+b}{c}', r'\frac{a}{c}+b'),
    ('a lost root', r'\sqrt{x}', 'x'),
    ('a root of another degree', r'\sqrt[3]{x}', r'\sqrt{x}'),
    ('a lost bar', r'\overline{x}', 'x'),
    ('a bar read as a hat', r'\bar{x}', r'\hat{x}'),
    ('a bar over more than it should', r'\overline{x-y}', r'x-\overline{y}'),
    ('a bar under instead of over', r'\overline{x}', r'\underline{x}'),
    ('a lost bracket', '(a)', 'a'),
    ('another bracket', '(a)', '[a]'),
    ('upper and lower case', r'\text{FV}', r'\text{fv}'),
    ('a sum sign against a capital sigma', r'\sum x', r'\Sigma x'),
    ('a product sign against a capital pi', r'\prod x', r'\Pi x'),
    ('another relation', 'a = b', r'a \approx b'),
    ('less against less or equal', 'a < b', r'a \le b'),
    ('another letter', r'\mu', r'\sigma'),
    ('swapped symbols', 'ab', 'ba'),
    ('a lost ellipsis', r'1, 2, \ldots', '1, 2'),
    ('a lost closing bracket group', r'\left[1-\frac{1}{(1+r)^n}\right]', r'1-\frac{1}{(1+r)^n}'),
]


def as_mathml(spelling: str) -> str:
    return spelling if '<' in spelling else katex(spelling)


@pytest.fixture(scope='module')
def rendered_spellings():
    """All LaTeX spellings at once, since each call starts a child process."""
    latex = sorted({spelling for _, row in SAME for spelling in row if '<' not in spelling}
                   | {spelling for _, one, other in DIFFERENT for spelling in (one, other)})
    answers = rendered_many([(item, True) for item in latex])
    assert all(result.ok for result in answers.values()), [(item, result.error) for item, result in answers.items() if not result.ok]
    return {item: answers[(item, True)].mathml for item in latex}


@pytest.mark.parametrize('name, spellings', SAME, ids=[row[0] for row in SAME])
def test_spellings_of_one_print_compare_equal(name, spellings, rendered_spellings):
    forms = {spelling: canonical_math(spelling if '<' in spelling else rendered_spellings[spelling]) for spelling in spellings}
    first = forms[spellings[0]]
    assert first, name
    assert {spelling: form for spelling, form in forms.items() if form != first} == {}


@pytest.mark.parametrize('name, one, other', DIFFERENT, ids=[row[0] for row in DIFFERENT])
def test_a_misreading_does_not_compare_equal(name, one, other, rendered_spellings):
    exact, similarity = compare_math(canonical_math(rendered_spellings[one]), canonical_math(rendered_spellings[other]))
    assert not exact, name
    assert similarity < 1


def test_the_span_wrapper_and_the_annotation_of_katex_are_dropped():
    tokens = canonical_math('<span class="katex"><math xmlns="http://www.w3.org/1998/Math/MathML" display="block"><semantics><mrow><mi>x</mi></mrow>'
                            '<annotation encoding="application/x-tex">\\sigma + 12</annotation></semantics></math></span>')
    assert tokens == ['x']


def test_the_publishers_duplicate_in_annotation_xml_is_dropped():
    assert canonical_math('<math><semantics><mrow><mn>1</mn></mrow><annotation-xml encoding="MathML-Content"><mn>1</mn></annotation-xml></semantics></math>') == ['1']


def test_a_phantom_is_not_printed():
    assert canonical_math('<math><mi>a</mi><mphantom><mi>b</mi></mphantom></math>') == ['a']


def test_several_math_elements_side_by_side_are_one_formula():
    assert canonical_math('<math><mi>a</mi></math><math><mo>=</mo><mi>b</mi></math>') == ['a', '=', 'b']


def test_entities_and_a_namespace_prefix_are_understood():
    assert canonical_math('<mml:math><mml:mi>a</mml:mi><mml:mo>&lt;</mml:mo><mml:mi>b</mml:mi><mml:mo>&#x2212;</mml:mo><mml:mn>1</mml:mn></mml:math>') == ['a', '<', 'b', '-', '1']


def test_a_comment_is_not_printed():
    assert canonical_math('<math><mi>a</mi><!-- b --></math>') == ['a']


@pytest.mark.parametrize('empty', ['', None, 'no markup at all'])
def test_nothing_to_read_is_no_tokens(empty):
    assert canonical_math(empty) == []


def test_a_literal_brace_cannot_be_taken_for_structure():
    assert canonical_math(katex(r'\{a\}')) == ['{', 'a', '}']
    assert reader_scoring.END not in canonical_math(katex(r'\{a\}'))


def test_structure_comes_as_tokens_of_their_own():
    tokens = canonical_math(katex(r'\frac{a}{\sqrt{b}} + \overline{x}_i^2'))
    assert tokens == ['\\frac', 'a', '\\next', '\\sqrt', 'b', '\\end', '\\end', '+', '\\over:bar', 'x', '\\end', '\\sub', 'i', '\\end', '\\sup', '2', '\\end']


def test_similarity_is_one_minus_the_normalised_edit_distance():
    assert compare_math(list('abcd'), list('abcd')) == (True, 1.0)
    assert compare_math(list('abcd'), list('abce')) == (False, 0.75)
    assert compare_math(list('abcd'), []) == (False, 0.0)


def test_an_accepted_pair_counts_only_where_it_stands_opposite():
    accepts = (('I', '1'),)
    assert compare_math(['I', 'x'], ['1', 'x'], accepts) == (True, 1.0)
    assert not compare_math(['I', 'x'], ['I', '1'], accepts)[0]  # an I against an I is equal, an x against a 1 is not
    assert compare_math(['I', '1'], ['I', '1'], accepts)[0]
    assert not compare_math(['1', 'x'], ['I', 'x'], accepts)[0]  # one way only


# ---------------------------------------------------------------- a small page and its readings

FV_MATHML = ('<math display="block"><semantics><mrow><mi>FV</mi><mo> </mo><mo>=</mo><mo> </mo><mi>PV</mi><mo> </mo><mo>×</mo><mo> </mo><msup><mrow><mo>(</mo><mn>1</mn>'
             '<mo>+</mo><mi>r</mi><mo>)</mo></mrow><mi>n</mi></msup></mrow><annotation-xml encoding="MathML-Content"><mi>FV</mi></annotation-xml></semantics></math>')
EAR_MATHML = '<math display="block"><mtext>EAR</mtext><mo>=</mo><mn>0.0338</mn></math>'
RATE_MATHML = '<math display="inline"><mo>(</mo><mn>1</mn><mo>+</mo><mi>r</mi><mo>)</mo></math>'
N_MATHML = '<math display="inline"><mi>n</mi><mo>=</mo><mn>10</mn></math>'
LETTER_MATHML = '<math display="inline"><mi>t</mi></math>'
SENTENCE = 'The additional interest reflects the compounding of interest over the two years.'
GOLD_PAGE = parse_gold({
    'id': 'fin_p0204', 'pdf': 'openstax_principles_of_finance_2e.pdf', 'pdf_page': 204, 'printed_page': '190', 'pdf_header': '190 7 • Time Value of Money I: Single Payment Value',
    'blocks': [
        {'kind': 'para', 'partial': {'starts_mid_block': True, 'ends_mid_block': False}, 'text_md': 'of 4% reflects the interest the account would earn each year.', 'math': []},
        {'kind': 'equation', 'eq_number': '7.9', 'partial': None, 'text_md': None, 'math': [{'latex_preview': r'\mathrm{FV} = \mathrm{PV} \times {( 1 + r )}^{n}', 'mathml': FV_MATHML, 'display': 'block'}]},
        {'kind': 'para', 'partial': None, 'text_md': f'{SENTENCE} We multiply by $( 1 + r)$ each year, so $n = 10$ here.', 'math': [
            {'latex_preview': '( 1 + r )', 'mathml': RATE_MATHML, 'display': 'inline'}, {'latex_preview': 'n = 10', 'mathml': N_MATHML, 'display': 'inline'}]},
        {'kind': 'heading', 'level': 3, 'partial': None, 'text_md': 'Compound Interest', 'math': []},
        {'kind': 'table', 'partial': None, 'rows': [
            {'section': 'thead', 'cells': [{'tag': 'th', 'colspan': 1, 'rowspan': 1, 'text_md': '', 'math': []}, {'tag': 'th', 'colspan': 1, 'rowspan': 1, 'text_md': 'Moody’s', 'math': []}]},
            {'section': 'tbody', 'cells': [{'tag': 'td', 'colspan': 1, 'rowspan': 1, 'text_md': 'Highest Quality', 'math': []}, {'tag': 'td', 'colspan': 1, 'rowspan': 1, 'text_md': 'Aaa', 'math': []}]},
            {'section': 'tbody', 'cells': [{'tag': 'td', 'colspan': 1, 'rowspan': 1, 'text_md': 'High Quality', 'math': []}, {'tag': 'td', 'colspan': 1, 'rowspan': 1, 'text_md': 'AA–', 'math': []}]},
        ]},
        {'kind': 'caption', 'partial': {'starts_mid_block': False, 'ends_mid_block': True}, 'text_md': 'Table 13.1 Rating Agencies and what they', 'math': []},
        {'kind': 'footnote', 'partial': None, 'text_md': '8 Michael Schmidt. When to Trust Bond Rating Agencies.', 'math': []},
    ],
})
FRONT = '---\ncontract: page/1\nwork: openstax-finance-2e\npdf_page: 204\nimage_size: "1688x2184"\nprinted_label: "{label}"\npage_kind: body\n---\n\n'
FIRST = ('::: {#b01 .paragraph cont=prev bbox="1 1 2 2"}\nof 4% reflects the interest the account would earn each year.\n:::\n\n')
FORMULA = '::: {#b02 .formula label="7.9" bbox="1 1 2 2"}\n\\text{FV} = \\text{PV} \\times (1 + r)^n\n:::\n\n'
SECOND = f'::: {{#b03 .paragraph bbox="1 1 2 2"}}\n{SENTENCE} We multiply by \\((1 + r)\\) each year, so \\(n = 10\\) here.\n:::\n\n'
HEADING = '::: {#b04 .heading bbox="1 1 2 2"}\nCompound Interest\n:::\n\n'
TABLE = ('::: {#b05 .table bbox="1 1 2 2"}\n<table><tr><th></th><th>Moody’s</th></tr><tr><td>Highest Quality</td><td>Aaa</td></tr>'
         '<tr><td>High Quality</td><td>AA-</td></tr></table>\n:::\n\n')
CAPTION = '::: {#b06 .caption of=b05 label="Table 13.1" cont=next bbox="1 1 2 2"}\nTable 13.1 Rating Agencies and what they\n:::\n\n'
NOTE = '::: {#b07 .footnote marker="8" bbox="1 1 2 2"}\nMichael Schmidt. When to Trust Bond Rating Agencies.\n:::\n\n'
PERFECT = FIRST + FORMULA + SECOND + HEADING + TABLE + CAPTION + NOTE


def reading(blocks: str = PERFECT, label: str = '190', form_check: bool = True):
    page = parse(FRONT.format(label=label) + blocks, 'markdown')
    if form_check:
        assert page.valid, page.errors
    return page


def score(blocks: str = PERFECT, gold=GOLD_PAGE, label: str = '190', rendered=None):
    page = reading(blocks, label)
    return score_reading(page, gold, verdicts(page) if rendered is None else rendered)


def test_a_perfect_reading_scores_perfect_in_every_class():
    result = score()
    assert (result.formula['gold'], result.formula['exact'], result.formula['missing'], result.formula['reader_extra']) == (3, 3, 0, 0)
    assert result.formula['mean_similarity'] == 1.0 and result.formula['label_ok'] == 1
    assert (result.prose['similarity'], result.prose['recall'], result.prose['precision']) == (1.0, 1.0, 1.0)
    assert (result.table['cells'], result.table['exact'], result.table['lost']) == (6, 6, 0)
    assert result.page_label['ok'] and result.furniture['failed'] == [] and result.furniture['tests'] >= 2
    assert result.rewriting == {'precision': 1.0, 'rate': 0.0} and result.valid and result.gold_id == 'fin_p0204'


def test_both_forms_of_one_reading_score_the_same():
    page = reading()
    as_json = json.dumps({
        'front': [{'name': name, 'value': value} for name, value in page.front.items()],
        'blocks': [{'id': block.id, 'class': block.cls, 'attrs': [{'name': name, 'value': value} for name, value in block.attrs.items()],
                    'body': block.body} for block in page.blocks]})
    other = parse(as_json, 'json')
    assert other.valid, other.errors
    assert score_reading(other, GOLD_PAGE, verdicts(other)).as_dict() == score_reading(page, GOLD_PAGE, verdicts(page)).as_dict()


def test_rendered_takes_the_text_layer_checks_verdicts_or_plain_mathml_and_none_renders_here():
    page = reading()
    verdicts = page_checks.render_formulas([page])
    assert all(isinstance(value, katex_check.Rendered) for value in verdicts.values()) and len(verdicts) == 3
    plain = {latex: value.mathml for (latex, _), value in verdicts.items()}
    assert score_reading(page, GOLD_PAGE, verdicts).as_dict() == score_reading(page, GOLD_PAGE, plain).as_dict() == score_reading(page, GOLD_PAGE, None).as_dict()


# ---------------------------------------------------------------- formulas

def items_by_label(result) -> dict:
    return {item['label']: item for item in result.formula['items'] if item['label']}


def test_a_numbered_formula_is_found_by_its_label_wherever_it_stands():
    moved = FIRST + SECOND + HEADING + FORMULA + TABLE + CAPTION + NOTE
    item = items_by_label(score(moved))['7.9']
    assert (item['how'], item['reader_block'], item['exact'], item['label_ok']) == ('label', 'b02', True, True)


def test_a_changed_digit_is_not_exact_and_the_similarity_says_how_close():
    wrong = PERFECT.replace('(1 + r)^n', '(1 + r)^m')
    item = items_by_label(score(wrong))['7.9']
    assert not item['exact'] and 0.7 < item['similarity'] < 1


def test_a_wrong_label_still_finds_the_formula_by_edit_distance_and_costs_the_label():
    wrong = PERFECT.replace('label="7.9"', 'label="7.6"')
    result = score(wrong)
    item = items_by_label(result)['7.9']
    assert (item['how'], item['exact'], item['label_ok']) == ('edit', True, False)
    assert result.formula['exact'] == 3 and result.formula['label_ok'] == 0


def test_a_label_written_in_brackets_is_still_the_label():
    assert reader_scoring._normal_label('(7.9)') == reader_scoring._normal_label(' 7.9 ') == '7.9'


def test_a_formula_the_reader_lost_counts_as_missing():
    result = score(FIRST + SECOND + HEADING + TABLE + CAPTION + NOTE)
    item = items_by_label(result)['7.9']
    assert (item['how'], item['exact'], item['similarity'], item['label_ok']) == (None, False, 0.0, False)
    assert result.formula['missing'] == 1 and result.formula['exact'] == 2


def test_a_formula_katex_refused_is_no_match_and_says_so():
    broken = PERFECT.replace('(1 + r)^n', r'\frac{1}{')
    result = score(broken)
    item = items_by_label(result)['7.9']
    assert (item['how'], item['exact'], item['similarity']) == ('unrendered', False, 0.0)
    assert result.formula['unrendered'] == 1


def test_a_formula_missing_from_the_map_counts_as_unrendered():
    assert score(rendered={}).formula['unrendered'] == 3


def page_with_formulas(*mathml: str):
    blocks = [{'kind': 'para', 'partial': None, 'text_md': ' '.join(f'$x{index}$' for index in range(len(mathml))),
               'math': [{'latex_preview': f'x{index}', 'mathml': value} for index, value in enumerate(mathml)]}]
    return parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': blocks})


def test_unnumbered_formulas_take_the_best_match_without_reuse():
    gold = page_with_formulas(katex('a + b + c'), katex('x + y + z'))
    one = '::: {#b01 .paragraph bbox="1 1 2 2"}\n\\(x + y + z\\) and \\(a + b + c\\)\n:::\n'
    result = score(one, gold, '1')
    assert [item['exact'] for item in result.formula['items']] == [True, True]
    only = '::: {#b01 .paragraph bbox="1 1 2 2"}\n\\(a + b + c\\)\n:::\n'
    result = score(only, gold, '1')
    assert [item['exact'] for item in result.formula['items']] == [True, False]
    assert result.formula['items'][1]['how'] is None  # the one reader formula is not used twice


def test_two_equal_gold_formulas_need_two_in_the_reading():
    gold = page_with_formulas(katex(r'\frac{a}{b}'), katex(r'\frac{a}{b}'))
    assert score('::: {#b01 .paragraph bbox="1 1 2 2"}\n\\(\\frac{a}{b}\\)\n:::\n', gold, '1').formula['exact'] == 1
    assert score('::: {#b01 .paragraph bbox="1 1 2 2"}\n\\(\\frac{a}{b}\\) and \\(\\frac{a}{b}\\)\n:::\n', gold, '1').formula['exact'] == 2


def test_an_exact_match_wins_over_an_earlier_near_match():
    gold = page_with_formulas(katex('a + b + c + d'), katex('a + b + c + e'))
    result = score('::: {#b01 .paragraph bbox="1 1 2 2"}\n\\(a + b + c + e\\) and \\(a + b + c + d\\)\n:::\n', gold, '1')
    assert [item['exact'] for item in result.formula['items']] == [True, True]


def test_nothing_in_common_is_no_match():
    gold = page_with_formulas(katex('a'))
    result = score('::: {#b01 .paragraph bbox="1 1 2 2"}\nWord \\(b^2\\) word.\n:::\n', gold, '1')
    assert result.formula['items'][0]['how'] is None


def test_a_formula_written_as_plain_text_is_found_as_text():
    plain = PERFECT.replace(r'\(n = 10\)', 'n = 10')
    result = score(plain)
    item = result.formula['items'][-1]
    assert (item['how'], item['exact']) == ('as_text', True)
    assert result.formula['as_text'] == 1 and result.formula['exact'] == 3
    assert (result.prose['recall'], result.prose['precision'], result.prose['similarity']) == (1.0, 1.0, 1.0)


def test_as_text_needs_whole_words():
    gold = page_with_formulas(LETTER_MATHML)
    assert score('::: {#b01 .paragraph bbox="1 1 2 2"}\nthe interest\n:::\n', gold, '1').formula['exact'] == 0
    assert score('::: {#b01 .paragraph bbox="1 1 2 2"}\nat time t, we pay\n:::\n', gold, '1').formula['exact'] == 1


def test_a_formula_with_structure_cannot_be_found_as_text():
    gold = page_with_formulas(katex(r'\frac{a}{b}'))
    assert score('::: {#b01 .paragraph bbox="1 1 2 2"}\nread a b here\n:::\n', gold, '1').formula['exact'] == 0


def test_a_formula_in_the_reading_that_is_plain_text_in_the_gold_counts_as_prose():
    math_word = PERFECT.replace('the account would earn', r'the \(account\) would earn')
    result = score(math_word)
    assert result.formula['reader_extra'] == 0
    assert (result.prose['recall'], result.prose['precision'], result.prose['similarity']) == (1.0, 1.0, 1.0)


def test_a_raised_digit_written_as_math_counts_as_prose():
    gold = parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': [{'kind': 'para', 'partial': None, 'text_md': 'denoted by s 2. Thus it is', 'math': []}]})
    result = score('::: {#b01 .paragraph bbox="1 1 2 2"}\ndenoted by \\(s^2\\). Thus it is\n:::\n', gold, '1')
    assert result.prose['similarity'] == 1.0 and result.formula['reader_extra'] == 0


def test_a_formula_with_structure_the_gold_lacks_is_extra_not_prose():
    extra = PERFECT.replace('each year.', r'each year \(\frac{a}{b}\).', 1)
    result = score(extra)
    assert result.formula['reader_extra'] == 1 and result.prose['precision'] == 1.0


def test_a_print_defect_is_accepted_through_the_gold():
    data = {'pdf': 'p.pdf', 'pdf_page': 1, 'printed_page': '1', 'formulas': [
        {'kind': 'display', 'label': '7', 'placed_by': 'printed label', 'latex': r'\mathbb{1}(x)', 'latex_origin': 'LaTeXML alttext', 'mathml': katex(r'\mathbb{1}(x)')}]}
    for written in (r'\mathbb{1}(x)', r'\mathbb{I}(x)', r'\nVdash (x)', r'\mathbf{1}(x)'):
        result = score(f'::: {{#b01 .formula label="7" bbox="1 1 2 2"}}\n{written}\n:::\n', parse_gold(data), '1')
        assert result.formula['exact'] == 1, written


# ---------------------------------------------------------------- prose

def test_a_lost_sentence_shows_in_recall_and_not_in_precision():
    result = score(PERFECT.replace(SENTENCE + ' ', ''))
    assert result.prose['recall'] < 0.9 and result.prose['precision'] == 1.0 and result.prose['similarity'] < 0.9


def test_an_invented_sentence_shows_in_precision_and_not_in_recall():
    result = score(PERFECT.replace('We multiply', 'Nothing of this was ever printed on the page. We multiply'))
    assert result.prose['precision'] < 0.95 and result.prose['recall'] == 1.0
    assert result.rewriting['rate'] == pytest.approx(1 - result.prose['precision'], abs=0.0001)


def test_a_rewritten_word_shows_in_both_directions():
    result = score(PERFECT.replace('reflects', 'shows'))
    assert result.prose['recall'] < 1 and result.prose['precision'] < 1 and result.rewriting['rate'] > 0


def test_a_changed_order_moves_only_the_edit_distance():
    result = score(SECOND + FIRST + FORMULA + HEADING + TABLE + CAPTION + NOTE)
    assert result.prose['recall'] == 1.0 and result.prose['precision'] == 1.0 and result.prose['similarity'] < 0.8


def test_math_is_out_of_the_prose_on_both_sides():
    assert score().prose['gold_tokens'] == score().prose['reader_tokens']
    wrong_math = PERFECT.replace(r'\((1 + r)\)', r'\((1 + q)\)')
    result = score(wrong_math)
    assert result.prose['similarity'] == 1.0 and result.formula['exact'] == 2


def test_case_and_punctuation_do_not_count_in_prose():
    result = score(PERFECT.replace('Compound Interest', 'COMPOUND INTEREST:'))
    assert result.prose['similarity'] == 1.0


def test_the_words_are_those_of_the_text_layer_check_with_case_folded():
    assert reader_scoring._words('The “two–year” ($1,000.50), 4% (see p. 12). • -5') == ['the', 'two-year', '$1,000.50', '4%', 'see', 'p', '12', '-5']


def test_a_page_break_does_not_count_against_the_reader():
    at_start = PERFECT.replace('of 4% reflects', 'interest of 4% reflects')
    at_end = PERFECT.replace('and what they\n', 'and what they rate\n')
    for blocks in (at_start, at_end):
        result = score(blocks)
        assert (result.prose['recall'], result.prose['precision'], result.prose['similarity']) == (1.0, 1.0, 1.0)


def test_a_missing_word_at_a_page_break_does_not_count_either():
    result = score(PERFECT.replace('of 4% reflects', 'reflects').replace('and what they\n', 'and what\n'))
    assert (result.prose['recall'], result.prose['precision']) == (1.0, 1.0)


def test_inside_the_page_the_same_words_do_count():
    result = score(PERFECT.replace('Compound Interest', 'Compound Interest extra'))
    assert result.prose['precision'] < 1.0


def test_a_block_that_is_not_cut_gets_no_page_break_tolerance():
    whole = parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': [{'kind': 'para', 'partial': None, 'text_md': 'one two three four', 'math': []}]})
    assert score('::: {#b01 .paragraph bbox="1 1 2 2"}\nzero one two three four\n:::\n', whole, '1').prose['precision'] < 1


def test_more_words_than_a_page_break_explains_do_count():
    added = 'a b c d e f g h '
    result = score(PERFECT.replace('of 4% reflects', added + 'of 4% reflects'))
    assert result.prose['precision'] < 1.0


def test_the_heading_number_and_the_caption_label_may_stand_in_their_attributes():
    gold = parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': [
        {'kind': 'heading', 'partial': None, 'text_md': '16.2 Net Present Value', 'math': []}, {'kind': 'caption', 'partial': None, 'text_md': 'Table 16.3', 'math': []}]})
    for heading in ('{#b01 .heading number="16.2" bbox="1 1 2 2"}\nNet Present Value', '{#b01 .heading number="16.2" bbox="1 1 2 2"}\n16.2 Net Present Value', '{#b01 .heading bbox="1 1 2 2"}\n16.2 Net Present Value'):
        for caption in ('{#b02 .caption of="@prev" label="Table 16.3" bbox="1 1 2 2"}\nTable 16.3', ):
            result = score(f'::: {heading}\n:::\n\n::: {caption}\n:::\n', gold, '1')
            assert result.prose['similarity'] == 1.0, heading


def test_the_marker_of_a_footnote_stands_in_its_attribute_on_both_sides():
    result = score()
    assert GOLD_PAGE.footnotes[0].marker == '8' and result.prose['recall'] == 1.0


def test_a_footnote_is_not_held_to_its_place_in_the_reading_order():
    result = score(NOTE + FIRST + FORMULA + SECOND + HEADING + TABLE + CAPTION)
    assert result.prose['similarity'] == 1.0


def test_a_footnote_written_as_a_paragraph_costs_the_comparison():
    as_paragraph = PERFECT.replace('.footnote marker="8"', '.paragraph')
    assert score(as_paragraph).prose['similarity'] < 1.0


def test_a_box_kind_line_is_prose_and_figure_text_and_descriptions_are_not():
    gold = parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': [{'kind': 'heading', 'partial': None, 'text_md': 'Think It Through', 'math': []}]})
    blocks = ('::: {#b01 .box kind=feature bbox="1 1 2 2"}\nTHINK IT THROUGH\n:::\n\n::: {#b02 .figure kind=chart bbox="1 1 2 2"}\nYear\n:::\n\n'
              '::: {#b03 .description of=b02 form=prose}\nA line rises.\n:::\n')
    assert score(blocks, gold, '1').prose['similarity'] == 1.0


# ---------------------------------------------------------------- tables

def cells(result) -> dict:
    return result.table['tables'][0]


def test_every_cell_in_place_after_normalisation():
    table = cells(score())
    assert (table['cells'], table['exact'], table['exact_rate'], table['present'], table['lost']) == (6, 6, 1.0, 5, False)
    assert (table['gold_rows'], table['reader_rows'], table['rows_aligned']) == (3, 3, 3)


def test_a_wrong_cell_costs_that_cell():
    table = cells(score(PERFECT.replace('<td>Aaa</td>', '<td>AAA</td>')))  # Moody's Aaa is not Standard & Poor's AAA
    assert (table['exact'], table['present']) == (5, 4)


def test_a_changed_figure_costs_the_cell():
    gold = table_gold([['$550,000', '$460,000']])
    assert cells(score(table_reading('<tr><td>$560,000</td><td>$460,000</td></tr>'), gold, '1'))['exact'] == 1


def table_gold(rows: list[list[str]], spans: dict | None = None) -> publisher_gold.PageGold:
    spans = spans or {}
    data = [{'section': 'tbody', 'cells': [{'tag': 'td', 'colspan': spans.get((r, c), (1, 1))[0], 'rowspan': spans.get((r, c), (1, 1))[1], 'text_md': text, 'math': []}
                                           for c, text in enumerate(row)]} for r, row in enumerate(rows)]
    return parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': [{'kind': 'table', 'partial': None, 'rows': data}]})


def table_reading(rows: str) -> str:
    return f'::: {{#b01 .table bbox="1 1 2 2"}}\n<table>{rows}</table>\n:::\n'


def test_a_lost_row_costs_its_own_cells_and_not_every_row_below():
    gold = table_gold([['a', '1'], ['b', '2'], ['c', '3'], ['d', '4']])
    table = cells(score(table_reading('<tr><td>a</td><td>1</td></tr><tr><td>c</td><td>3</td></tr><tr><td>d</td><td>4</td></tr>'), gold, '1'))
    assert (table['exact'], table['present'], table['rows_aligned']) == (6, 6, 3)


def test_an_inserted_row_shifts_nothing():
    gold = table_gold([['a', '1'], ['b', '2']])
    table = cells(score(table_reading('<tr><td colspan="2">Title</td></tr><tr><td>a</td><td>1</td></tr><tr><td>b</td><td>2</td></tr>'), gold, '1'))
    assert table['exact'] == 4


def test_rows_align_even_when_every_row_holds_an_error():
    gold = table_gold([['a', '1', 'x'], ['b', '2', 'y'], ['c', '3', 'z']])
    rows = '<tr><td>new</td><td>row</td><td>here</td></tr><tr><td>a</td><td>1</td><td>?</td></tr><tr><td>b</td><td>2</td><td>?</td></tr><tr><td>c</td><td>3</td><td>?</td></tr>'
    assert cells(score(table_reading(rows), gold, '1'))['exact'] == 6


def test_a_lost_table_counts_all_its_cells_as_missing():
    result = score(FIRST + FORMULA + SECOND + HEADING + CAPTION.replace('of=b05', 'of="@prev"') + NOTE)
    table = cells(result)
    assert (table['lost'], table['exact'], table['cells'], table['exact_rate'], table['present']) == (True, 0, 6, 0.0, 0)
    assert result.table['lost'] == 1 and result.table['exact_rate'] == 0.0


def test_a_moved_column_is_present_but_not_in_place():
    gold = table_gold([['a', '1']])
    table = cells(score(table_reading('<tr><td>1</td><td>a</td></tr>'), gold, '1'))
    assert (table['exact'], table['present']) == (0, 2)


def test_case_is_significant_and_spacing_and_dash_kinds_are_not():
    gold = table_gold([['AA–', 'Two  words', '−5']])
    table = cells(score(table_reading('<tr><td>AA-</td><td>Two words</td><td>-5</td></tr>'), gold, '1'))
    assert table['exact'] == 3
    assert cells(score(table_reading('<tr><td>aa-</td><td>Two words</td><td>5</td></tr>'), gold, '1'))['exact'] == 1


def test_empty_cells_count_and_a_filled_one_where_the_gold_is_empty_does_not_match():
    gold = table_gold([['Example', ''], ['', '']])
    assert cells(score(table_reading('<tr><td>Example</td><td></td></tr><tr><td></td><td></td></tr>'), gold, '1'))['exact'] == 4
    table = cells(score(table_reading('<tr><td>Example</td><td></td></tr><tr><td>x</td><td></td></tr>'), gold, '1'))
    assert table['exact'] == 3 and table['filled_cells'] == 1


def test_a_span_or_empty_cells_beside_it_are_the_same_table():
    gold = table_gold([['wide', 'x'], ['a', 'b', 'c']], {(0, 0): (2, 1)})
    assert cells(score(table_reading('<tr><td colspan="2">wide</td><td>x</td></tr><tr><td>a</td><td>b</td><td>c</td></tr>'), gold, '1'))['exact'] == 5
    assert cells(score(table_reading('<tr><td>wide</td><td></td><td>x</td></tr><tr><td>a</td><td>b</td><td>c</td></tr>'), gold, '1'))['exact'] == 5


def test_a_rowspan_keeps_the_cells_after_it_in_place():
    gold = table_gold([['tall', 'x'], ['y']], {(0, 0): (1, 2)})
    assert cells(score(table_reading('<tr><td rowspan="2">tall</td><td>x</td></tr><tr><td>y</td></tr>'), gold, '1'))['exact'] == 3


def test_math_in_a_cell_is_compared_as_math_whichever_way_it_was_written():
    data = [{'section': 'tbody', 'cells': [{'tag': 'td', 'colspan': 1, 'rowspan': 1, 'text_md': '$40 - 46 = - 6$',
                                            'math': [{'latex_preview': '40 - 46 = - 6', 'mathml': katex('40 - 46 = - 6')}]}]}]
    gold = parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': [{'kind': 'table', 'partial': None, 'rows': data}]})
    for cell, expected in ((r'\(40-46=-6\)', 1), ('40 − 46 = −6', 1), (r'\(40-46=6\)', 0), ('40 - 46 = 6', 0)):
        assert cells(score(table_reading(f'<tr><td>{cell}</td></tr>'), gold, '1'))['exact'] == expected, cell


def test_a_formula_in_a_cell_katex_refused_equals_nothing():
    gold = table_gold([['x']])
    assert cells(score(table_reading(r'<tr><td>\(x\)</td></tr>'), gold, '1', rendered={}))['exact'] == 0


def test_tables_take_the_reading_that_fits_them_without_reuse():
    gold = parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': [
        {'kind': 'table', 'partial': None, 'rows': [{'section': 'tbody', 'cells': [{'tag': 'td', 'text_md': 'first', 'math': []}]}]},
        {'kind': 'table', 'partial': None, 'rows': [{'section': 'tbody', 'cells': [{'tag': 'td', 'text_md': 'second', 'math': []}]}]}]})
    both = ('::: {#b01 .table bbox="1 1 2 2"}\n<table><tr><td>second</td></tr></table>\n:::\n\n::: {#b02 .table bbox="1 1 2 2"}\n<table><tr><td>first</td></tr></table>\n:::\n')
    result = score(both, gold, '1')
    assert [table['reader_block'] for table in result.table['tables']] == ['b02', 'b01'] and result.table['exact'] == 2
    one = '::: {#b01 .table bbox="1 1 2 2"}\n<table><tr><td>second</td></tr></table>\n:::\n'
    result = score(one, gold, '1')
    assert [table['lost'] for table in result.table['tables']] == [True, False]


def test_a_partial_table_says_so_and_counts_the_rows_on_this_page():
    data = [{'section': 'tbody', 'cells': [{'tag': 'td', 'text_md': 'a', 'math': []}]}]
    gold = parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': [{'kind': 'table', 'partial': {'rows_kept': [0], 'rows_total': 12}, 'rows': data}]})
    table = cells(score(table_reading('<tr><td>a</td></tr>'), gold, '1'))
    assert table['partial'] and table['cells'] == 1 and table['exact'] == 1


RASTER_GOLD = parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': [
    {'kind': 'table', 'partial': None, 'rows': [{'section': 'tbody', 'cells': [{'tag': 'td', 'text_md': '$915.00', 'math': []}]}]},
    {'kind': 'image', 'partial': None, 'alt': 'Line one: January 3, 2019; 915; Blank. Line two: 2,079; 21.'},
]})


def test_a_raster_table_counts_through_the_numbers_of_its_alt_text():
    real = '::: {#b01 .table bbox="1 1 2 2"}\n<table><tr><td>$915.00</td></tr></table>\n:::\n\n'
    raster = '::: {#b02 .table raster=1 bbox="1 1 2 2"}\n<table><tr><td>2019<br>Jan. 3</td><td>915</td><td>2,079</td><td>21</td></tr></table>\n:::\n'
    result = score(real + raster, RASTER_GOLD, '1')
    assert (result.table['raster_values'], result.table['raster_found']) == (5, 5)
    wrong = raster.replace('2,079', '2,097')
    assert score(real + wrong, RASTER_GOLD, '1').table['raster_found'] == 4


def test_a_lost_raster_counts_as_all_its_values_missing_and_a_real_table_cannot_stand_in():
    real = '::: {#b01 .table bbox="1 1 2 2"}\n<table><tr><td>$915.00</td></tr></table>\n:::\n'
    assert score(real, RASTER_GOLD, '1').table['raster_found'] == 0


def test_a_raster_read_as_a_figure_still_counts():
    real = '::: {#b01 .table bbox="1 1 2 2"}\n<table><tr><td>$915.00</td></tr></table>\n:::\n\n'
    figure = '::: {#b02 .figure kind=other bbox="1 1 2 2"}\n2019 Jan. 3\n915\n2,079\n21\n:::\n'
    assert score(real + figure, RASTER_GOLD, '1').table['raster_found'] == 5


def test_a_page_without_tables_has_no_table_score():
    gold = parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': [{'kind': 'para', 'partial': None, 'text_md': 'words', 'math': []}]})
    assert score('::: {#b01 .paragraph bbox="1 1 2 2"}\nwords\n:::\n', gold, '1').table is None


# ---------------------------------------------------------------- page label and furniture

def test_the_printed_label_is_compared_as_printed():
    assert score(label='190').page_label == {'gold': '190', 'read': '190', 'ok': True}
    assert not score(label='204').page_label['ok']


def test_a_page_without_a_printed_label_is_read_as_none():
    gold = parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': None, 'blocks': []})
    assert score('::: {#b01 .paragraph bbox="1 1 2 2"}\nwords\n:::\n', gold, 'none').page_label['ok']


HEADER = '::: {#b90 .page_header bbox="1 1 2 2"}\n7 • Time Value of Money I: Single Payment Value\n:::\n\n'
FOLIO = '::: {#b91 .page_number bbox="1 1 2 2"}\n190\n:::\n\n'
FOOTER = '::: {#b92 .page_footer bbox="1 1 2 2"}\nAccess for free at openstax.org\n:::\n'


def test_furniture_in_its_own_classes_passes_and_stays_out_of_the_prose():
    result = score(HEADER + FOLIO + PERFECT + FOOTER)
    assert (result.furniture['tests'], result.furniture['passed'], result.furniture['failed']) == (3, 3, [])
    assert (result.prose['recall'], result.prose['precision'], result.prose['similarity']) == (1.0, 1.0, 1.0)


def test_a_running_head_in_a_paragraph_fails_the_absence_test():
    as_body = HEADER.replace('.page_header', '.paragraph') + PERFECT
    result = score(as_body)
    assert result.furniture['failed'] == ['header'] and result.prose['precision'] < 1


def test_a_running_foot_in_a_paragraph_fails_the_absence_test():
    as_body = PERFECT + FOOTER.replace('.page_footer', '.paragraph')
    assert score(as_body).furniture['failed'] == ['footer']


def test_a_slightly_misread_running_head_still_fails():
    as_body = '::: {#b90 .paragraph bbox="1 1 2 2"}\n7 Time Value of Money l: Single Payment Value\n:::\n\n' + PERFECT
    assert score(as_body).furniture['failed'] == ['header']


def test_a_folio_alone_in_a_body_block_fails_and_a_figure_in_a_sentence_does_not():
    assert score(FOLIO.replace('.page_number', '.paragraph') + PERFECT).furniture['failed'] == ['folio']
    assert score(PERFECT.replace('each year.', 'each year, 190 in all.', 1)).furniture['failed'] == []


def test_a_running_head_the_body_also_holds_tests_nothing():
    gold = parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '753', 'pdf_header': '13.3 • Prepare Journal Entries 753',
                       'blocks': [{'kind': 'heading', 'partial': None, 'text_md': '13.3 Prepare Journal Entries', 'math': []}]})
    result = score('::: {#b01 .heading bbox="1 1 2 2"}\n13.3 Prepare Journal Entries\n:::\n', gold, '753')
    assert 'header' not in result.furniture['failed'] and result.furniture['tests'] == 1  # only the folio is left to test


def test_rewriting_is_reported_only_where_there_is_prose_gold():
    paper = parse_gold({'pdf': 'p.pdf', 'pdf_page': 1, 'printed_page': '1', 'formulas': [
        {'kind': 'display', 'label': '1', 'placed_by': 'printed label', 'latex': 'a', 'latex_origin': 'preview', 'mathml': '<math><mi>a</mi></math>'}]})
    result = score('::: {#b01 .paragraph bbox="1 1 2 2"}\nAny words at all, in place of the paper.\n:::\n\n::: {#b02 .formula label="1" bbox="1 1 2 2"}\na\n:::\n', paper, '1')
    assert result.prose is None and result.rewriting is None and result.table is None and result.formula['exact'] == 1


def test_a_paper_formula_says_how_it_was_placed():
    paper = parse_gold({'pdf': 'p.pdf', 'pdf_page': 1, 'printed_page': '1', 'formulas': [
        {'kind': 'inline', 'label': None, 'placed_by': 'after', 'latex': 'a', 'latex_origin': 'preview', 'mathml': '<math><msup><mi>a</mi><mn>2</mn></msup></math>'}]})
    assert score('::: {#b01 .paragraph bbox="1 1 2 2"}\nNothing here.\n:::\n', paper, '1').formula['items'][0]['placed_by'] == 'after'


# ---------------------------------------------------------------- many pages

def test_a_score_holds_no_page_text_and_stores_as_json():
    record = score(HEADER + FOLIO + PERFECT + FOOTER).as_dict()
    stored = json.dumps(record)
    for words in ('reflects', 'compounding', 'Moody', 'Aaa', 'Compound Interest', 'Schmidt', 'Time Value', 'FV'):
        assert words not in stored, words
    assert record['formula']['items'][0]['label'] == '7.9'


def test_summarize_counts_per_class_over_items():
    good = score()
    bad = score(FIRST + SECOND.replace(r'\(n = 10\)', r'\(n = 11\)').replace(SENTENCE + ' ', '') + HEADING + CAPTION.replace('of=b05', 'of="@prev"') + NOTE, label='9')
    paper = parse_gold({'pdf': 'p.pdf', 'pdf_page': 1, 'printed_page': '1', 'formulas': [
        {'kind': 'display', 'label': '1', 'placed_by': 'printed label', 'latex': 'a', 'latex_origin': 'preview', 'mathml': '<math><mi>a</mi></math>'}]})
    third = score('::: {#b01 .formula label="1" bbox="1 1 2 2"}\na\n:::\n', paper, '1')
    summary = summarize([good, bad, third])
    assert summary['pages'] == 3
    assert (summary['formula']['gold'], summary['formula']['exact'], summary['formula']['missing']) == (7, 5, 1)
    assert (summary['formula']['display'], summary['formula']['display_exact'], summary['formula']['inline']) == (3, 2, 4)
    assert summary['formula']['exact_rate'] == round(5 / 7, 4)
    assert summary['prose']['pages'] == 2 and summary['prose']['recall'] < 1 and summary['prose']['precision'] <= 1
    assert (summary['table']['pages'], summary['table']['tables'], summary['table']['lost'], summary['table']['cells'], summary['table']['exact']) == (2, 2, 1, 12, 6)
    assert (summary['page_label']['pages'], summary['page_label']['ok']) == (3, 2)
    assert summary['rewriting']['pages'] == 2
    json.dumps(summary)


def test_summarize_of_nothing_is_empty_not_a_crash():
    summary = summarize([])
    assert summary['pages'] == 0 and summary['formula']['exact_rate'] is None and summary['prose']['recall'] is None


def test_a_malformed_reading_is_scored_without_a_crash():
    page = parse(FRONT.format(label='190') + FIRST + '::: {#b02 .nonsense bbox="1 1 2 2"}\nwords\n:::\n', 'markdown')
    assert not page.valid
    result = score_reading(page, GOLD_PAGE, {})
    assert not result.valid and result.formula['exact'] == 0


# ---------------------------------------------------------------- the self-check, on literal gold

def page_with_latex(*rows: tuple[str, str]) -> publisher_gold.PageGold:
    """Display formulas, each with its own LaTeX and MathML."""
    blocks = [{'kind': 'equation', 'eq_number': str(index), 'partial': None, 'text_md': None,
               'math': [{'latex_preview': latex, 'mathml': mathml, 'display': 'block'}]} for index, (latex, mathml) in enumerate(rows, 1)]
    return parse_gold({'id': 'g', 'pdf': 'x.pdf', 'pdf_page': 1, 'printed_page': '1', 'blocks': blocks})


def test_the_self_check_reports_agreement_and_every_disagreement():
    gold = page_with_latex(('a + b', '<math><mi>a</mi><mo>+</mo><mi>b</mi></math>'), ('a + c', '<math><mi>a</mi><mo>+</mo><mi>d</mi></math>'))
    report = reader_scoring.self_check([gold])
    assert (report['formulas'], report['rendered'], report['agreed'], report['agreement_rate']) == (2, 2, 1, 0.5)
    assert report['by_origin'] == {'preview': {'formulas': 2, 'rendered': 2, 'agreed': 1}}
    wrong = report['disagreements'][0]
    assert (wrong['page'], wrong['label'], wrong['latex']) == ('g', '2', 'a + c') and wrong['katex'] != wrong['gold'] and wrong['similarity'] < 1


def test_the_self_check_reports_latex_katex_refuses_and_plants_misreadings():
    gold = page_with_latex((r'\frac{a}{', '<math><mi>a</mi></math>'), ('x^{2} + 1 = (y)', '<math><msup><mi>x</mi><mn>2</mn></msup><mo>+</mo><mn>1</mn><mo>=</mo><mo>(</mo><mi>y</mi><mo>)</mo></math>'))
    report = reader_scoring.self_check([gold])
    assert report['rendered'] == 1 and report['agreed'] == 1 and len(report['render_failed']) == 1 and report['render_failed'][0]['error']
    planted = report['mutations']
    assert {'digit', 'sign', 'exponent', 'relation', 'dropped_term', 'dropped_bracket'} <= set(planted)
    assert all(row['detected'] == row['tried'] > 0 and row['missed'] == [] for row in planted.values())


def test_the_self_check_of_no_pages_is_empty():
    report = reader_scoring.self_check([])
    assert report['formulas'] == 0 and report['agreement_rate'] is None and report['mutations'] == {}


def test_the_module_writes_its_report_before_it_prints(tmp_path, monkeypatch, capsys):
    out = tmp_path / 'report.json'
    monkeypatch.setattr(reader_scoring, 'self_check', lambda: {'formulas': 1, 'disagreements': [{'latex': 'a'}], 'render_failed': []})
    monkeypatch.setattr('sys.argv', ['reader_scoring', '--out', str(out)])
    reader_scoring.main()
    assert json.loads(out.read_text(encoding='utf-8'))['disagreements'] == [{'latex': 'a'}]
    printed = capsys.readouterr().out
    assert 'disagreements: 1, not rendered: 0' in printed and '"latex"' not in printed


# ---------------------------------------------------------------- the real gold, where it exists

def reading_of(gold: publisher_gold.PageGold) -> str:
    """The page file a perfect reader would write, built from the gold: the end-to-end check of parsing and scoring together."""
    def math(formula) -> str:
        return rf'\({reader_scoring.gold_latex_for_katex(formula.latex)}\)'

    def body(item) -> str:
        return ' '.join(value if kind == 'text' else math(value) for kind, value in item.segments)

    def cell(item) -> str:
        return html.escape(' '.join(value if kind == 'text' else math(value) for kind, value in item.segments), quote=False)

    blocks = []

    def add(attributes: str, text: str) -> None:
        blocks.append(f'::: {{#b{len(blocks) + 1:02d} {attributes} bbox="1 1 2 2"}}\n{text}\n:::\n')

    if gold.printed_label:
        add('.page_number', gold.printed_label)
    for block in gold.prose:
        attributes = {'list_item': '.list_item marker="1."', 'heading': '.heading', 'caption': '.caption of="@prev"', 'table_title': '.caption of="@next"'}.get(block.kind, '.paragraph')
        add(attributes, body(block))
    for formula in gold.display:
        add(f'.formula label="{formula.label}"' if formula.label else '.formula', reader_scoring.gold_latex_for_katex(formula.latex))
    # A paper's inline formulas have no text around them in the gold.
    if not gold.has_prose:
        for formula in gold.inline:
            add('.paragraph', f'In which {math(formula)} holds.')
    for table in gold.tables:
        rows = ''.join('<tr>' + ''.join(f'<td colspan="{item.colspan}" rowspan="{item.rowspan}">{cell(item)}</td>' for item in row) + '</tr>' for row in table.rows)
        add('.table', f'<table>{rows}</table>')
    for raster in gold.rasters:
        add('.table raster=1', '<table><tr>' + ''.join(f'<td>{value}</td>' for value in raster.values) + '</tr></table>')
    for block in gold.footnotes:
        add(f'.footnote marker="{block.marker}"', body(block))
    front = f'---\ncontract: page/1\nwork: w\npdf_page: {gold.pdf_page}\nimage_size: "1688x2184"\nprinted_label: "{gold.printed_label}"\npage_kind: body\n---\n\n'
    return front + '\n'.join(blocks)


@pytest.fixture(scope='module')
def real_scores():
    rows = []
    for gold in publisher_gold.all_gold():
        page = parse(reading_of(gold), 'markdown')
        rows.append((gold, reading_of(gold), score_reading(page, gold, verdicts(page))))
    return rows


@needs_gold
def test_the_comparator_agrees_with_the_gold_itself_and_catches_every_planted_misreading():
    report = reader_scoring.self_check()
    assert report['formulas'] == 125 and report['render_failed'] == []
    assert report['agreement_rate'] >= MIN_AGREEMENT, report['disagreements']
    assert report['by_origin']['author']['formulas'] == 39
    for name, planted in report['mutations'].items():
        assert planted['tried'] > 0 and planted['missed'] == [], (name, planted['missed'])
    assert sum(planted['tried'] for planted in report['mutations'].values()) >= 400


@needs_gold
def test_every_real_page_read_perfectly_scores_perfect(real_scores):
    assert len(real_scores) == 14
    for gold, _, result in real_scores:
        assert result.formula['exact'] == result.formula['gold'] and result.formula['reader_extra'] == 0, gold.gold_id
        assert result.formula['label_ok'] == result.formula['numbered'], gold.gold_id
        assert result.page_label['ok'] and result.furniture['failed'] == [], gold.gold_id
        if gold.has_prose:
            assert (result.prose['similarity'], result.prose['recall'], result.prose['precision']) == (1.0, 1.0, 1.0), gold.gold_id
        if result.table:
            assert result.table['exact'] == result.table['cells'] and result.table['raster_found'] == result.table['raster_values'], gold.gold_id


@needs_gold
def test_every_real_page_read_perfectly_is_a_valid_page(real_scores):
    assert {gold.gold_id: parse(text, 'markdown').errors for gold, text, _ in real_scores if not parse(text, 'markdown').valid} == {}


@needs_gold
def test_the_summary_of_the_real_gold_has_every_class_it_should(real_scores):
    summary = summarize([result for _, _, result in real_scores])
    assert summary['formula']['gold'] == 112 and summary['formula']['exact_rate'] == 1.0  # 125 less the 13 in table cells
    assert summary['prose']['pages'] == 10 and summary['table']['pages'] == 7 and summary['table']['cells'] == 224
    assert summary['table']['raster_values'] == 18 and summary['page_label']['rate'] == 1.0 and summary['furniture']['rate'] == 1.0


@needs_gold
def test_a_misreading_planted_in_a_real_page_costs_exactly_that_formula():
    gold = publisher_gold.load_gold('carta_conversano_kelly_criterion_2020.pdf', 5)
    text = reading_of(gold)
    assert 'M - R ] \\end{array}' in text
    changed = text.replace('{\\Sigma}^{- 1}', '{\\Sigma}^{1}')
    page = parse(changed, 'markdown')
    result = score_reading(page, gold, verdicts(page))
    assert result.formula['exact'] == result.formula['gold'] - 1
    item = next(item for item in result.formula['items'] if item['label'] == '12')
    assert not item['exact'] and item['similarity'] > 0.8


@needs_gold
def test_the_pdf_text_layer_read_as_prose_agrees_with_the_publisher():
    # The floor of the prose measure: the page's own text layer against the web edition. Without the page's math on either side.
    for path in sorted((publisher_gold.GOLD_ROOT / 'truth').glob('*.json')):
        if path.name.startswith('_'):
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        gold = parse_gold(data)
        layer = data['pdf_text_layer_body'] + ' ' + data['pdf_text_layer_footnotes']
        gold_tokens = [token for block in gold.prose + gold.footnotes for token in reader_scoring._words(block.text)]
        common = Counter(gold_tokens) & Counter(reader_scoring._words(layer))
        assert sum(common.values()) / len(gold_tokens) >= 0.95, gold.gold_id
