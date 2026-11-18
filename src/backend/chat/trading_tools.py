"""The two calculation tools (phase 7): the knowledge base explains a concept, these apply it to the
user's own numbers.

- `performance_metrics`: Sharpe ratio, maximum drawdown, volatility and total return of a series of
  returns or account values.
- `position_size`: a position size by fixed fractional risk (account, risk per trade, stop), and
  the Kelly fraction with half-Kelly (win probability, win/loss ratio).
A cited source is opened by the search server's `open_page` since decision 98.c, no longer here.

Both are deterministic: no model call inside, tested offline like any function. Each result
names its formula and where the corpus explains it. Bad input raises `ToolInputError` with a message
that says how to fix it; the agent gets that message back (`handle_tool_error`) instead of a crash.

`explain` writes what the user reads about a calculation, from the result alone (decided with the operator,
2026-10-01): the agent's own explanation once read "you should risk 25 % of your capital", personal
advice the generator's rules forbid. A rule in the agent's prompt would make that less likely; code
makes it impossible, as code already sets the quotes, citations and disclaimer of a knowledge answer.
"""

import math
import statistics
from typing import Literal

SHARPE_SOURCE = ('Principles of Finance 2e, 15.4 Applications in Performance Measurement, p. 456 (PDF p. 470); '
                 'Sharpe ratio (Wikipedia), Definition')
DRAWDOWN_SOURCE = 'Drawdown (economics) (Wikipedia), 1. How low it goes (the magnitude)'
KELLY_SOURCE = 'Kelly criterion (Wikipedia), Formula; Carta and Conversano (2020), 2.1. Background'


class ToolInputError(ValueError):
    """Input a tool cannot work with; the message says what to pass instead."""


def performance_metrics(values: list[float], kind: Literal['returns', 'equity'] = 'returns',
                        periods_per_year: int = 252, risk_free_rate: float = 0.0) -> dict:
    """Sharpe ratio, maximum drawdown, volatility and total return of a series.

    Args:
        values: Period returns as decimals (0.02 for 2 %), or account values (kind='equity').
        kind: 'returns' or 'equity'.
        periods_per_year: 252 for daily, 52 weekly, 12 monthly; used to annualise.
        risk_free_rate: The yearly risk-free rate as a decimal.
    """
    if kind == 'equity':
        if len(values) < 3 or any(v <= 0 for v in values):
            raise ToolInputError('pass at least three positive account values, oldest first')
        returns = [b / a - 1 for a, b in zip(values, values[1:])]
    else:
        returns = list(values)
        if len(returns) < 2:
            raise ToolInputError('pass at least two period returns')
        if any(abs(r) >= 1 for r in returns):
            raise ToolInputError('the returns look like percentages; pass decimals, e.g. 0.02 for 2 %')
    mean, deviation = statistics.fmean(returns), statistics.stdev(returns)
    excess = mean - risk_free_rate / periods_per_year
    equity, peak, worst = 1.0, 1.0, 0.0
    for r in returns:
        equity *= 1 + r
        peak = max(peak, equity)
        worst = max(worst, (peak - equity) / peak)
    return {
        'periods': len(returns),
        'mean_return_per_period': round(mean, 6),
        'volatility_per_year': round(deviation * math.sqrt(periods_per_year), 6),
        'sharpe_ratio_per_year': round(excess / deviation * math.sqrt(periods_per_year), 4) if deviation > 0 else None,
        'max_drawdown': round(worst, 6),
        'total_return': round(equity - 1, 6),
        'formulas': {
            'sharpe_ratio': '(mean period return - risk-free rate per period) / standard deviation of period returns'
                            ' × sqrt(periods per year)',
            'max_drawdown': 'the largest fall from a running peak of the equity curve, as a share of that peak',
        },
        'sources': {'sharpe_ratio': SHARPE_SOURCE, 'max_drawdown': DRAWDOWN_SOURCE},
    }


def position_size(account_size: float | None = None, risk_percent: float | None = None,
                  entry_price: float | None = None, stop_price: float | None = None,
                  win_probability: float | None = None, win_loss_ratio: float | None = None) -> dict:
    """A position size by fixed fractional risk, and/or the Kelly fraction.

    Args:
        account_size, risk_percent, entry_price, stop_price: For the fixed fractional size: the
            account in money, the risk per trade in percent (1 for 1 %), entry and stop price.
        win_probability, win_loss_ratio: For Kelly: the chance of a win (0.55 for 55 %) and the
            average win divided by the average loss.
    """
    fixed = (account_size, risk_percent, entry_price, stop_price)
    kelly = (win_probability, win_loss_ratio)
    if all(v is None for v in fixed + kelly):
        raise ToolInputError('pass account_size, risk_percent, entry_price and stop_price, '
                             'or win_probability and win_loss_ratio, or both')
    result = {}
    if any(v is not None for v in fixed):
        if any(v is None for v in fixed):
            raise ToolInputError('a fixed fractional size needs account_size, risk_percent, entry_price and stop_price')
        if account_size <= 0 or not 0 < risk_percent <= 100 or entry_price <= 0 or stop_price <= 0:
            raise ToolInputError('account size and prices must be positive, risk_percent between 0 and 100')
        if entry_price == stop_price:
            raise ToolInputError('the stop must differ from the entry price')
        risk_amount = account_size * risk_percent / 100
        units = risk_amount / abs(entry_price - stop_price)
        result['fixed_fractional'] = {
            'risk_amount': round(risk_amount, 2), 'stop_distance': round(abs(entry_price - stop_price), 10),
            'units': round(units, 4), 'position_value': round(units * entry_price, 2),
            'formula': 'units = account × risk % / |entry - stop|'}
    if any(v is not None for v in kelly):
        if any(v is None for v in kelly):
            raise ToolInputError('a Kelly fraction needs win_probability and win_loss_ratio')
        if not 0 < win_probability < 1 or win_loss_ratio <= 0:
            raise ToolInputError('win_probability must lie between 0 and 1 (0.55 for 55 %), win_loss_ratio above 0')
        fraction = win_probability - (1 - win_probability) / win_loss_ratio
        result['kelly'] = {
            'kelly_fraction': round(fraction, 4), 'half_kelly': round(fraction / 2, 4),
            'edge': fraction > 0,
            'formula': 'f* = p - (1 - p) / b, with p the win probability and b the win/loss ratio',
            'source': KELLY_SOURCE,
            'note': 'no edge: Kelly says do not take the bet' if fraction <= 0 else
                    'fractional Kelly (e.g. half) is the usual practice: lower drawdowns, less risk of ruin'}
    return result


METRICS = {  # performance_metrics' measures: the result key, how it is shown, and whether it is annualised
    'sharpe_ratio': ('sharpe_ratio_per_year', 'Sharpe ratio, per year', True),
    'max_drawdown': ('max_drawdown', 'Maximum drawdown', False),
    'volatility': ('volatility_per_year', 'Volatility, per year', True),
    'total_return': ('total_return', 'Total return', False),
}
INLINE = {'sharpe_ratio': 'Sharpe ratio {} per year', 'max_drawdown': 'maximum drawdown {}',
          'volatility': 'volatility {} per year', 'total_return': 'total return {}'}


def _percent(value: float, digits: int = 2) -> str:
    return f'{value * 100:.{digits}f} %'


def _number(value: float) -> str:
    """A number as a person writes it: no trailing zeros, thousands separated."""
    if float(value).is_integer():
        return f'{int(value):,}'
    return f'{value:,.6f}'.rstrip('0').rstrip('.')


def _metric(key: str, result: dict) -> str:
    value = result[METRICS[key][0]]
    if value is None:
        return '— (the series does not vary)'
    return f'{value:.2f}' if key == 'sharpe_ratio' else _percent(value)


def explain(name: str, args: dict, result: dict) -> str:
    """What the user reads about a calculation: the numbers, the formula, its source, the tool's note.

    Written from the tool's result alone, never by a model, so it can only say what was computed. The
    measure the user asked about (`focus`) comes first; the rest of the same series follows.
    """
    if name == 'performance_metrics':
        return _explain_metrics(args, result)
    if name == 'position_size':
        return _explain_position(args, result)
    raise ValueError(f'no explanation for {name!r}')


def _formula(key: str, result: dict) -> list[str]:
    if key not in result['formulas']:
        return []
    label = METRICS[key][1].split(',')[0]
    return [f"**{label}** = {result['formulas'][key]}. *Source: {result['sources'][key]}.*"]


def _explain_metrics(args: dict, result: dict) -> str:
    """With a focus: that measure, its basis, the others in one line, its formula. Without: the table."""
    focus = args.get('focus') if args.get('focus') in METRICS else None
    basis = (f"{result['periods']} returns between the account values" if args.get('kind') == 'equity'
             else f"{result['periods']} period returns")
    assumption = (f"The per-year figures assume {args.get('periods_per_year') or 252} periods per year (252 for "
                  f"daily, 52 for weekly, 12 for monthly values) and a risk-free rate of "
                  f"{_percent(args.get('risk_free_rate') or 0, 1)}.")
    if focus is None:
        lines = [f'Measures of the {basis}:', '', '| Measure | Value |', '|---|---:|',
                 *[f'| {METRICS[key][1]} | {_metric(key, result)} |' for key in METRICS],
                 f"| Mean return per period | {_percent(result['mean_return_per_period'], 3)} |", '',
                 assumption, '', *_formula('sharpe_ratio', result), '', *_formula('max_drawdown', result)]
        return '\n'.join(lines)
    others = ', '.join(INLINE[key].format(_metric(key, result)) for key in METRICS if key != focus)
    basis_line = (f'From {basis}. {assumption} Also: {others}.' if METRICS[focus][2]
                  else f'From {basis}. Also: {others}. {assumption}')
    return '\n'.join([f'**{METRICS[focus][1]}: {_metric(focus, result)}**', '', basis_line, '',
                      *_formula(focus, result)]).rstrip()


def _explain_position(args: dict, result: dict) -> str:
    lines = []
    if 'fixed_fractional' in result:
        fixed = result['fixed_fractional']
        lines += [f"**Fixed fractional size:** risking {_number(args['risk_percent'])} % of "
                  f"{_number(args['account_size'])} between entry {_number(args['entry_price'])} and stop "
                  f"{_number(args['stop_price'])}:", '',
                  '| | |', '|---|---:|',
                  f"| Risk amount | {fixed['risk_amount']:,.2f} |",
                  f"| Stop distance | {_number(fixed['stop_distance'])} |",
                  f"| Units | {_number(fixed['units'])} |",
                  f"| Position value | {fixed['position_value']:,.2f} |", '',
                  f"Formula: {fixed['formula']}."]
    if 'kelly' in result:
        kelly = result['kelly']
        if lines:
            lines.append('')
        lines += [f"**Kelly fraction** for a win probability of {_percent(args['win_probability'], 0)} and a "
                  f"win/loss ratio of {_number(args['win_loss_ratio'])}:", '',
                  '| | |', '|---|---:|',
                  f"| Kelly fraction f* | {_percent(kelly['kelly_fraction'], 1)}"
                  f"{' of capital' if kelly['edge'] else ' (no edge)'} |"]
        if kelly['edge']:
            lines.append(f"| Half Kelly | {_percent(kelly['half_kelly'], 1)} of capital |")
        lines += ['', f"{kelly['note'][0].upper()}{kelly['note'][1:]}.", '',
                  f"Formula: {kelly['formula']}. *Source: {kelly['source']}.*"]
    return '\n'.join(lines)

