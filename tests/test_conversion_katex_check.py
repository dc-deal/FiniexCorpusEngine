import pytest

from backend.conversion.checks import katex_check


def test_valid_latex_renders_and_broken_latex_is_rejected():
    results = katex_check.check_many([
        (r'\text{Average} = \frac{\$20{,}000 + \$30{,}000}{2} = \$25{,}000', True),
        (r'\begin{aligned} E[r^S] &= \mu > 0 \\ \sigma_p &= \sqrt{w^\top \Sigma w} \end{aligned}', True),
        (r'\sigma', False),
        (r'\frac{\$100{,}000}{\$25{,}000', True),
        (r'\frac{a}{b}}', True),
        (r'\fraq{a}{b}', True),
        (r'\left( a + b', True),
        ('\x0crac{a}{b}', True),
        (r'\frac{$100}{2}', True),
    ])
    assert [result.ok for result in results] == [True, True, True, False, False, False, False, False, False]
    assert '<math' in results[0].mathml and 'mfrac' in results[0].mathml
    assert results[3].mathml is None and results[3].error


def test_nothing_to_check_starts_nothing():
    assert katex_check.check_many([]) == []


def test_a_failed_child_says_so_rather_than_passing_the_formulas(monkeypatch):
    monkeypatch.setattr(katex_check.subprocess, 'run',
                        lambda *args, **kwargs: type('Done', (), {'returncode': 1, 'stderr': 'no V8'})())
    with pytest.raises(katex_check.KatexUnavailable):
        katex_check.check_many([('x', False)])
