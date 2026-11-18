from backend.ingestion.clean_sections.html_sections import PROFILES, parse_sections

WIKIPEDIA = """<html><body>
<section data-mw-section-id="0"><p>Lead text<sup class="mw-ref">[1]</sup>.</p></section>
<section data-mw-section-id="1"><h2 id="Definition">Definition</h2>
  <p>The ratio is <math alttext="{\\displaystyle S={\\frac {E[R]}{\\sigma }}}"><mi>S</mi></math> here.</p>
  <section><h3 id="Variants">Variants</h3><ul><li>one</li><li>two <p>nested</p></li></ul></section>
</section>
<section data-mw-section-id="2"><h2 id="References">References</h2>
  <ol><li>Sharpe, W. (1966)</li></ol>
  <section><h3 id="Notes">Notes</h3><p>a note inside the dropped section</p></section>
</section>
<div class="navbox"><p>navigation</p></div>
</body></html>"""

SRE = """<html><body><main><div id="maia-main">
<h2>Chapter 6 - Monitoring</h2>
<section id="chapter_monitoring"><p>Intro.</p>
  <section id="definitions"><h1>Definitions</h1><p>Monitoring means...</p></section>
</section>
<div class="footer"><p>footer text</p></div>
</div></main></body></html>"""

GUTENBERG = """<html><body>
<header id="pg-header"><h2 id="pg-header-heading">The Project Gutenberg eBook</h2><p>licence</p></header>
<h1>REMINISCENCES</h1>
<h2 id="CONTENTS">CONTENTS</h2><p>I ... 1</p><p>II ... 20</p>
<h2 id="I">I</h2><p>I went to work <span class="pagenum">[Pg 1]</span>as a boy.</p>
<section id="pg-footer"><p>End of the Project Gutenberg eBook</p></section>
</body></html>"""


def parse(html, profile, title='Doc'):
    return parse_sections(html, PROFILES[profile], 'src', 'https://example.org/page', title)


def test_wikipedia_sections_carry_their_anchor_and_drop_reference_lists():
    sections = parse(WIKIPEDIA, 'wikipedia', 'Sharpe ratio')
    assert [s.heading_path for s in sections] == [
        ['Sharpe ratio'], ['Sharpe ratio', 'Definition'], ['Sharpe ratio', 'Definition', 'Variants']]
    assert sections[1].url == 'https://example.org/page#Definition'
    assert sections[0].anchor is None and sections[0].url == 'https://example.org/page'
    text = ' '.join(s.text for s in sections)
    assert 'Sharpe, W.' not in text and 'a note inside' not in text  # subsection dropped with it
    assert 'navigation' not in text and '[1]' not in text


def test_wikipedia_drops_a_combined_notes_and_references_heading():
    # Found 2026-09-30 in Double-entry bookkeeping: 8 chunks of citations reached q02's top 10.
    html = """<html><body><section data-mw-section-id="0"><p>Lead.</p></section>
    <section data-mw-section-id="1"><h2 id="Notes_and_references">Notes and references</h2>
      <ol><li>Horngren, Charles T. (2013). Accounting.</li></ol></section></body></html>"""
    text = ' '.join(s.text for s in parse(html, 'wikipedia'))
    assert 'Lead.' in text and 'Horngren' not in text


def test_wikipedia_math_becomes_its_latex_source():
    definition = parse(WIKIPEDIA, 'wikipedia')[1]
    assert 'S={\\frac {E[R]}{\\sigma }}' in definition.text
    assert 'displaystyle' not in definition.text


def test_nested_blocks_are_read_once():
    variants = parse(WIKIPEDIA, 'wikipedia')[2]
    assert variants.text.count('nested') == 1


def test_sre_takes_the_chapter_title_from_the_first_heading_and_anchors_via_the_section():
    sections = parse(SRE, 'sre')
    assert sections[0].heading_path == ['Chapter 6 - Monitoring']
    assert sections[1].heading_path == ['Chapter 6 - Monitoring', 'Definitions']
    assert sections[1].anchor == 'definitions'
    assert 'footer text' not in ' '.join(s.text for s in sections)


def test_gutenberg_drops_licence_contents_and_print_page_numbers():
    sections = parse(GUTENBERG, 'gutenberg')
    assert [s.heading_path for s in sections] == [['REMINISCENCES', 'I']]
    assert sections[0].text == 'I went to work as a boy.'
    assert sections[0].url.endswith('#I')


def test_a_heading_that_borrows_an_earlier_heading_s_anchor_links_to_itself_by_a_text_fragment():
    html = """<html><body><main><div id="maia-main">
<h2>Chapter 1 - Introduction</h2>
<section id="what-is-sre"><h1>What is SRE?</h1><p>An approach.</p>
  <h2>DevOps or SRE?</h2><p>A comparison.</p>
</section></div></main></body></html>"""
    first, second = parse_sections(html, PROFILES['sre'], 'sre', 'https://sre.google/x/', 'SRE')
    assert first.url == 'https://sre.google/x/#what-is-sre'
    assert second.url == 'https://sre.google/x/#what-is-sre:~:text=DevOps%20or%20SRE%3F'
    assert second.anchor == 'what-is-sre'


def body(inner: str) -> str:
    return f'<html><body><section><h2 id="S">S</h2>{inner}</section></body></html>'


def test_the_text_reads_as_a_browser_shows_it_without_a_space_at_an_inline_edge():
    # decision 155.a: "the Sortino ratio , which" and "( m − d ) ÷ σ ," in every quote before loader 4
    text = parse(body('<p>Roy\'s ratio is related to the <a href="/wiki/Sortino_ratio">Sortino ratio</a>, which uses '
                      '(<i>m</i> − <i>d</i>) ÷ <i>σ</i>, the Federal Reserve<b>\'s</b> rule.</p>'), 'wikipedia')[0].text
    assert text == "Roy's ratio is related to the Sortino ratio, which uses (m − d) ÷ σ, the Federal Reserve's rule."


def test_a_line_break_a_block_and_a_superscript_still_part_words():
    sections = parse(body('<p>Sloss<sup>6</sup>Edited by Beyer</p><p>1.1<sup>6</sup> − 1</p>'
                          '<ul><li>item<ul><li>sub</li></ul></li></ul><p>one<br>two</p>'), 'wikipedia')
    assert sections[0].text.split('\n') == ['Sloss 6 Edited by Beyer', '1.1 6 − 1', 'item sub', 'one two']


def test_a_stray_closing_br_is_read_as_a_line_break_as_a_browser_reads_it():
    # SRE writes nine of them; html.parser drops the tag, and "Winkel" and "Edited" would fuse
    assert parse(body('<p>Written by JC van Winkel</br>Edited by Betsy Beyer</p>'), 'wikipedia')[0].text == \
        'Written by JC van Winkel Edited by Betsy Beyer'


def test_a_formula_is_delimited_as_a_pdf_page_writes_it():
    text = parse(body(r'<p>where <math alttext="{\displaystyle R_{a}}"><mi>R</mi></math> is the return,</p>'
                      r'<p><math display="block" alttext="{\displaystyle S={\frac {a}{b}}}"><mi>S</mi></math></p>'),
                 'wikipedia')[0].text
    assert text.split('\n') == [r'where \(R_{a}\) is the return,', r'\[ S={\frac {a}{b}} \]']
