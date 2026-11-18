import pytest

from backend.ingestion import audit


def chunk(source, text, heading_path='Chapter > Section', chunk_id='x'):
    return {'id': chunk_id, 'source_id': source, 'text': text, 'metadata': {'heading_path': heading_path}}


def test_known_noise_is_counted_per_source():
    counts = audit.count_noise([
        chunk('a', 'text\nAccess for free at openstax.org'),
        chunk('a', 'I went [Pg 12] home'),
        chunk('b', 'clean text'),
    ])
    assert counts['a']['openstax attribution line'] == 1
    assert counts['a']['print-edition page marker [Pg n]'] == 1
    assert counts['b']['openstax attribution line'] == 0
    assert counts['a']['chunks'] == 2


def test_the_preface_may_quote_the_attribution_line():
    counts = audit.count_noise([chunk('a', 'retain: "Access for free at openstax.org."', 'Preface > About OpenStax')])
    assert counts['a']['openstax attribution line'] == 0
    assert audit.defects(counts) == []


def test_a_running_footer_that_slipped_through_is_a_defect():
    counts = audit.count_noise([chunk('a', 'body\n456     15 • How to Think about Investing')])
    assert ('a', 'running footer (page no. + chapter)', 1) in audit.defects(counts)


def test_only_the_formula_wrapper_counts_as_a_math_leftover():
    counts = audit.count_noise([
        chunk('a', 'x \\mapsto \\displaystyle {\\frac {1}{2}}'),   # LaTeX the article itself uses
        chunk('b', 'the ratio {\\displaystyle S={\\frac {E}{\\sigma }}}'),  # the wrapper, not removed
    ])
    assert counts['a']['MathML leftovers (displaystyle)'] == 0
    assert counts['b']['MathML leftovers (displaystyle)'] == 1


def test_signals_are_counted_but_are_not_defects():
    counts = audit.count_noise([chunk('a', 'see https://example.org [3]\n42\nshort')])
    assert counts['a']['URL'] == 1 and counts['a']['footnote marker [n]'] == 1
    assert counts['a']['line of digits only'] == 1
    assert audit.defects(counts) == []


def test_long_lines_repeated_across_many_chunks_are_reported():
    furniture = 'This line looks like a leftover running header'
    chunks = [chunk('a', f'{furniture}\nbody {n}', chunk_id=str(n)) for n in range(audit.REPEATED_IN_CHUNKS)]
    assert audit.repeated_lines(chunks)['a'] == [(audit.REPEATED_IN_CHUNKS, furniture)]


def test_the_sample_is_reproducible(tmp_path):
    chunks = [chunk('a', f'text {n}', chunk_id=str(n)) for n in range(20)]
    audit.write_sample(chunks, 3, 7, tmp_path / 'one.md')
    audit.write_sample(chunks, 3, 7, tmp_path / 'two.md')
    body = lambda p: p.read_text(encoding='utf-8').split('\n', 3)[3]  # skip the timestamp line
    assert body(tmp_path / 'one.md') == body(tmp_path / 'two.md')


@pytest.mark.corpus
def test_the_built_index_has_none_of_the_known_noise():
    if not audit.DATABASE.exists():
        pytest.skip('no index yet - run python -m backend.ingestion.build')
    assert audit.defects(audit.count_noise(audit.load_chunks(audit.DATABASE))) == []
