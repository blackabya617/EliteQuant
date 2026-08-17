"""
What the strategy does for someone who contributes every paycheck.

Every backtest elsewhere in this project assumes a lump sum invested once and
left alone. That is not how this account is being funded - it starts small and
receives regular contributions - and the difference is not cosmetic.

A regular contributor has a materially different relationship with drawdowns
than a lump-sum investor. When prices fall, the lump-sum investor simply loses
money; the contributor's next payment buys more shares at the lower price. So
the drawdown protection that is this strategy's only validated edge is worth
much less to a contributor, and can be worth less than nothing: avoiding the
decline also means skipping the cheap shares.

This module measures that directly rather than assuming either way.
"""

import numpy as np
import pandas as pd

from rotation import RotationParams, backtest, month_end_prices


def dca_path(returns, initial=300.0, monthly=200.0):
    """Balance path for a stream of contributions, and the total paid in."""
    balance, contributed, path = initial, initial, []
    for r in returns:
        balance = balance * (1 + r) + monthly
        contributed += monthly
        path.append(balance)
    return pd.Series(path, index=returns.index), contributed


def summarise(returns, initial=300.0, monthly=200.0):
    path, contributed = dca_path(returns, initial, monthly)
    final = path.iloc[-1]
    return {
        "contributed": contributed,
        "final": final,
        "gain": final - contributed,
        "multiple_on_money_in": final / contributed,
        "worst_drawdown_pct": (path / path.cummax() - 1).min() * 100,
    }


def aligned_returns():
    """Monthly returns for the strategy and SPY over a common window."""
    monthly = month_end_prices()
    equity, _ = backtest(monthly, RotationParams())
    strat = equity.pct_change().dropna()
    bench = monthly["SPY"].pct_change().dropna()
    common = strat.index.intersection(bench.index)
    return strat[common], bench[common]


def rolling_start_comparison(step_months=6, min_months=60,
                             initial=300.0, monthly=200.0):
    """Compare terminal wealth across many contribution start dates.

    Note these windows overlap and all end on the same date, so they are not
    independent samples - "N of N" here means the result is consistent, not
    that it carries N samples' worth of statistical weight.
    """
    strat, bench = aligned_returns()
    rows = []
    for k in range(0, len(strat) - min_months, step_months):
        s_final = dca_path(strat.iloc[k:], initial, monthly)[0].iloc[-1]
        b_final = dca_path(bench.iloc[k:], initial, monthly)[0].iloc[-1]
        rows.append({
            "start": strat.index[k].date(),
            "years": len(strat.iloc[k:]) / 12,
            "strategy_final": s_final,
            "spy_final": b_final,
            "spy_edge_pct": (b_final / s_final - 1) * 100,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    strat, bench = aligned_returns()

    print("\nContributing $200/month from a $300 start\n" + "=" * 58)
    for label, r in [("rotation (9mo/top8, vol cap)", strat), ("SPY buy & hold", bench)]:
        s = summarise(r)
        print(f"\n{label}")
        print(f"  paid in            ${s['contributed']:>12,.0f}")
        print(f"  ended with         ${s['final']:>12,.0f}")
        print(f"  multiple on money  {s['multiple_on_money_in']:>13.2f}x")
        print(f"  worst drawdown     {s['worst_drawdown_pct']:>12.1f}%")

    table = rolling_start_comparison()
    wins = (table.spy_final > table.strategy_final).sum()
    print(f"\n\nAcross {len(table)} rolling start dates, SPY ended ahead in {wins}.")
    print("Windows overlap and share an end date, so this shows consistency,")
    print("not independent statistical weight.")
