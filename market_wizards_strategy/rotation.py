"""
Dual-momentum rotation - the one variant in this repo that survived validation.

Mechanism (Antonacci-style dual momentum, applied to an ETF universe):

  relative momentum : rank the universe by trailing N-month total return
  absolute momentum : only hold a name trading above its 10-month average
  hold the top K eligible names, equal weight, rebalanced monthly
  hold cash for any slot with no eligible name

Why this and not the breakout/trend system: on real SPY data 1993-2026 the
trend system returns 5.9% against buy & hold's 10.9% at the same Sharpe - it is
simply SPY with 60% exposure. Rotation is the only tested variant whose
risk-adjusted edge held up out of sample. See README for the full table.

It does NOT reliably beat SPY on return. Its edge is drawdown: roughly SPY's
return for roughly two-thirds of SPY's peak-to-trough loss.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

import data_manager as dm

DEFAULT_UNIVERSE = [
    "SPY", "QQQ", "IWM", "EFA", "EEM",       # equity
    "TLT", "IEF", "LQD", "HYG",              # fixed income
    "GLD", "SLV", "USO", "DBC",              # commodities
    "IYR", "XLE", "XLK", "XLF", "XLV", "XLU", "XLP",   # real estate + sectors
]


@dataclass
class RotationParams:
    """Defaults are the parameters walk-forward validation kept choosing.

    Refitting every two years on the prior five picked a 9-month lookback and
    eight slots in five of seven windows. Parameters that keep being rediscovered
    on data the fit has not seen are a much better sign than parameters that
    merely score well once. The earlier defaults (3 months, five slots) were the
    best cell in a single sweep, which is a weaker basis.
    """
    lookback_months: int = 9        # relative-momentum window
    top_n: int = 8                  # slots held
    abs_ma_months: int = 10         # absolute-momentum filter
    cost_bps: float = 10.0          # round-trip cost per switched slot
    initial_capital: float = 10_000.0

    # Cap portfolio volatility by holding cash when recent realised vol runs
    # hot. This does not raise return - it trades about 1.7pp of CAGR for
    # roughly 3pp of drawdown, which is the right trade for a small account
    # that has to actually sit through the loss.
    vol_cap: float = 0.10           # annualised; None disables
    vol_lookback: int = 6


def month_end_prices(universe=None, start="2007-04-11"):
    """Month-end panel. NOTE the final row is the CURRENT, still-running month:
    resample labels it with the month's end date but fills it with the latest
    available price. That is what you want for marking a portfolio to market,
    and emphatically not what you want for computing a signal - see
    last_complete_month().
    """
    universe = universe or DEFAULT_UNIVERSE
    px = pd.DataFrame({s: dm.load(s)["Close"] for s in universe}).ffill()
    return px[px.index >= start].resample("M").last()


def last_complete_month(monthly, as_of=None):
    """Index of the last fully-elapsed month in `monthly`.

    The signal must be anchored on a month that has actually finished. Anchoring
    on the running month instead makes the live strategy differ from the
    validated one in two ways: it uses a different momentum window than every
    backtested number here, and it makes the holdings depend on *which day the
    scheduler happened to run* - the partial month's data changes daily, so the
    ranking churns underneath it. Measured over 47 months, a partial-month
    anchor disagreed with this convention on an average of 1.4 of 8 positions
    on the first trading day of the month, rising to 1.9 by the tenth.
    """
    if as_of is None:
        as_of = dm.load("SPY").index[-1]
    as_of = pd.Timestamp(as_of)
    for i in range(len(monthly) - 1, -1, -1):
        label = monthly.index[i]
        if (as_of.year, as_of.month) > (label.year, label.month):
            return i
    return -1


def select(monthly, p: RotationParams, as_of=None):
    """Return the holdings for the month following `as_of`.

    Uses only data up to and including `as_of`, so the list is what you would
    have known at that month's close and traded on the next open.
    """
    as_of = as_of or monthly.index[-1]
    hist = monthly.loc[:as_of]
    if len(hist) < max(p.lookback_months, p.abs_ma_months) + 1:
        return []

    momentum = hist.iloc[-1] / hist.iloc[-1 - p.lookback_months] - 1
    trend_ma = hist.rolling(p.abs_ma_months).mean().iloc[-1]
    last = hist.iloc[-1]

    ranked = momentum.dropna().sort_values(ascending=False)
    eligible = [s for s in ranked.index if last[s] > trend_ma[s]]
    return eligible[: p.top_n]


def _exposure(history, p: RotationParams):
    """Fraction of capital to deploy, from trailing realised volatility.

    Uses returns strictly before the month being sized, so the scale for month
    t is knowable at the end of month t-1.
    """
    if not p.vol_cap or len(history) < p.vol_lookback:
        return 1.0
    realised = float(np.std(history[-p.vol_lookback:], ddof=1) * np.sqrt(12))
    if realised <= 0:
        return 1.0
    return float(min(1.0, p.vol_cap / realised))


def backtest(monthly, p: RotationParams, start_idx=None):
    """Equal-weight monthly rotation. Returns (equity, holdings log).

    The log's `return_pct` is the realised (post-exposure) return, since that
    is what an equity curve needs. `raw_return_pct` carries the pre-exposure
    return specifically so any downstream vol-targeting decision - including
    the live signal in target_weights() - measures the strategy's natural
    volatility rather than a series already damped by a previous exposure cut.
    Feeding the damped series back into the vol estimate is a circularity
    bug: a genuinely volatile stretch gets exposure cut, the cut suppresses
    the recorded return's volatility, and the suppressed volatility then
    reads as calm enough to raise exposure again - the sizing model
    unwinding its own risk cut.
    """
    warmup = max(p.lookback_months, p.abs_ma_months) + 1
    start_idx = start_idx or warmup

    equity = [p.initial_capital]
    dates = [monthly.index[start_idx - 1]]
    held = set()
    log = []
    raw_history = []

    for i in range(start_idx, len(monthly)):
        picks = select(monthly, p, as_of=monthly.index[i - 1])
        if picks:
            step = float(np.mean([monthly[s].iloc[i] / monthly[s].iloc[i - 1] - 1 for s in picks]))
        else:
            step = 0.0

        current = set(picks)
        turnover = len(current ^ held) / max(len(current | held), 1)
        step -= (p.cost_bps / 10_000) * turnover

        exposure = _exposure(raw_history, p)
        raw_history.append(step)
        scaled_step = step * exposure

        equity.append(equity[-1] * (1 + scaled_step))
        dates.append(monthly.index[i])
        log.append({"date": monthly.index[i], "holdings": ",".join(picks) or "CASH",
                    "return_pct": scaled_step * 100, "raw_return_pct": step * 100,
                    "exposure": exposure})
        held = current

    return pd.Series(equity, index=dates), pd.DataFrame(log)


def metrics(equity, periods_per_year=12):
    """Annualised stats for a monthly equity series."""
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1
    dd = (equity / equity.cummax() - 1).min()
    r = equity.pct_change().dropna()
    vol = r.std() * np.sqrt(periods_per_year)
    return {
        "cagr_pct": cagr * 100,
        "max_dd_pct": dd * 100,
        "vol_pct": vol * 100,
        "sharpe": (r.mean() * periods_per_year) / vol if vol > 0 else 0.0,
        "calmar": cagr / abs(dd) if dd < 0 else 0.0,
        "final_equity": equity.iloc[-1],
    }


def target_weights(p: RotationParams = None, universe=None):
    """Live signal: what the portfolio should hold right now.

    Weights are scaled by the same volatility cap the backtest applies, so the
    live book and the tested book are the same strategy.
    """
    p = p or RotationParams()
    monthly = month_end_prices(universe)

    # Anchor on the last COMPLETE month, exactly as backtest() does when it
    # calls select(as_of=monthly.index[i - 1]). Using monthly.index[-1] would
    # anchor on the running month and quietly trade a different strategy than
    # the one every number in the README describes.
    anchor = last_complete_month(monthly)
    picks = select(monthly, p, as_of=monthly.index[anchor])

    exposure = 1.0
    if p.vol_cap:
        _, log = backtest(monthly, p)
        # Same reasoning for the volatility history: drop the running month,
        # whose partial return is not comparable to the full-month returns the
        # annualisation assumes. And raw_return_pct, not return_pct, so the
        # estimate sees the strategy's natural pre-exposure volatility.
        log = log[log["date"] <= monthly.index[anchor]]
        if len(log) >= p.vol_lookback:
            recent = (log["raw_return_pct"] / 100).tolist()
            exposure = _exposure(recent, p)

    weight = (1.0 / p.top_n) * exposure if p.top_n else 0.0
    return {
        "as_of": monthly.index[anchor].date().isoformat(),
        "priced_through": monthly.index[-1].date().isoformat(),
        "holdings": {s: weight for s in picks},
        "cash_weight": 1.0 - weight * len(picks),
        "exposure": exposure,
        "universe_size": monthly.shape[1],
    }
