import math

import pytest

from backend.chat import trading_tools


def test_performance_metrics_compute_sharpe_drawdown_and_volatility_by_their_formulas():
    returns = [0.02, -0.01, 0.03, -0.04, 0.015, 0.005]
    result = trading_tools.performance_metrics(returns, periods_per_year=12)
    mean = sum(returns) / 6
    sd = math.sqrt(sum((r - mean) ** 2 for r in returns) / 5)
    assert result['sharpe_ratio_per_year'] == pytest.approx(mean / sd * math.sqrt(12), abs=1e-4)
    assert result['volatility_per_year'] == pytest.approx(sd * math.sqrt(12), abs=1e-6)
    # peak after +2 %, -1 %, +3 %; then -4 % is the deepest fall from that peak
    assert result['max_drawdown'] == pytest.approx(0.04, abs=1e-6)
    assert 'Principles of Finance' in result['sources']['sharpe_ratio']


def test_account_values_become_returns_and_percentages_are_refused():
    result = trading_tools.performance_metrics([10000, 10400, 9800, 10900], kind='equity')
    assert result['max_drawdown'] == pytest.approx(600 / 10400, abs=1e-6)
    with pytest.raises(trading_tools.ToolInputError, match='decimals'):
        trading_tools.performance_metrics([2, -1, 3])


def test_fixed_fractional_size_risks_the_chosen_share_of_the_account():
    result = trading_tools.position_size(account_size=20000, risk_percent=1, entry_price=1.1, stop_price=1.095)
    assert result['fixed_fractional']['risk_amount'] == 200
    assert result['fixed_fractional']['units'] == pytest.approx(40000)


def test_kelly_fraction_and_half_kelly_and_no_edge():
    kelly = trading_tools.position_size(win_probability=0.55, win_loss_ratio=1.5)['kelly']
    assert kelly['kelly_fraction'] == pytest.approx(0.25) and kelly['half_kelly'] == pytest.approx(0.125)
    assert trading_tools.position_size(win_probability=0.4, win_loss_ratio=1.0)['kelly']['edge'] is False


def test_position_size_explains_what_is_missing():
    with pytest.raises(trading_tools.ToolInputError, match='needs account_size'):
        trading_tools.position_size(account_size=1000, risk_percent=1)
    with pytest.raises(trading_tools.ToolInputError, match='between 0 and 1'):
        trading_tools.position_size(win_probability=55, win_loss_ratio=1.5)


RETURNS = [0.02, -0.01, 0.03, -0.04, 0.015, 0.005]


def test_the_measure_asked_for_comes_first_with_only_its_own_formula():
    result = trading_tools.performance_metrics(RETURNS, periods_per_year=12)
    text = trading_tools.explain('performance_metrics', {'values': RETURNS, 'periods_per_year': 12,
                                                         'focus': 'sharpe_ratio'}, result)
    assert text.startswith(f"**Sharpe ratio, per year: {result['sharpe_ratio_per_year']:.2f}**")
    assert 'assume 12 periods per year' in text and 'maximum drawdown 4.00 %' in text
    assert '**Sharpe ratio** =' in text and '**Maximum drawdown** =' not in text  # only the asked measure's formula
    assert '|' not in text  # no table when a measure was asked for


def test_a_drawdown_on_account_values_names_the_assumption_behind_the_annualised_figures():
    values = [10000, 10400, 9800, 10900, 10100]
    result = trading_tools.performance_metrics(values, kind='equity')
    text = trading_tools.explain('performance_metrics', {'values': values, 'kind': 'equity',
                                                         'focus': 'max_drawdown'}, result)
    assert text.startswith('**Maximum drawdown: 7.34 %**')
    assert 'From 4 returns between the account values' in text and 'assume 252 periods per year' in text


def test_without_a_focus_every_measure_is_listed_with_both_formulas():
    result = trading_tools.performance_metrics(RETURNS, periods_per_year=12)
    text = trading_tools.explain('performance_metrics', {'values': RETURNS, 'periods_per_year': 12}, result)
    assert '| Maximum drawdown | 4.00 % |' in text and '| Mean return per period |' in text
    assert '**Sharpe ratio** =' in text and '**Maximum drawdown** =' in text


def test_a_position_is_shown_as_a_person_writes_numbers_and_kelly_without_an_edge_says_so():
    fixed = {'account_size': 20000, 'risk_percent': 1, 'entry_price': 1.1, 'stop_price': 1.095}
    text = trading_tools.explain('position_size', fixed, trading_tools.position_size(**fixed))
    assert '| Units | 40,000 |' in text and 'risking 1 % of 20,000' in text
    no_edge = {'win_probability': 0.35, 'win_loss_ratio': 1.2}
    text = trading_tools.explain('position_size', no_edge, trading_tools.position_size(**no_edge))
    assert '(no edge)' in text and 'Half Kelly' not in text and 'No edge: Kelly says do not take the bet.' in text


def test_no_explanation_ever_tells_the_user_what_to_do():
    texts = [trading_tools.explain('position_size', a, trading_tools.position_size(**a))
             for a in ({'win_probability': 0.55, 'win_loss_ratio': 1.5}, {'win_probability': 0.35, 'win_loss_ratio': 1.2},
                       {'account_size': 20000, 'risk_percent': 1, 'entry_price': 1.1, 'stop_price': 1.095})]
    for text in texts:
        assert not any(word in text.lower() for word in ('you should', 'we recommend', 'you must', 'buy ', 'sell '))
