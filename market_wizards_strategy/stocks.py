"""
Cross-sectional momentum on individual S&P 500 members.

This is the one mechanism the earlier tests never touched. Everything before
was an index or a basket of indices; a strategy that owns SPY-like exposure
cannot out-earn SPY. Picking individual names can, because the dispersion
between the best and worst members of the index is enormous.

The rules combine what several traders in the books were doing, rather than
copying any one of them:

  relative strength ranking       Minervini, Okumus, Lescarbeau - and the
                                  single most replicated anomaly in the
                                  academic literature (Jegadeesh & Titman)
  12-1 momentum window            skip the most recent month, because very
                                  short-term momentum reverses
  trend template                  Minervini: price above its 50/150/200 MAs,
                                  those MAs stacked in order, the 200 rising,
                                  price near its 52-week high
  market regime filter            Paul Tudor Jones: no long exposure while the
                                  index itself is below its 200-day average
  volatility-scaled sizing        Dennis/Eckhardt: equal risk, not equal dollars
  let winners run                 no profit target; positions leave the book by
                                  falling out of the ranking

Membership is read point-in-time, so the backtest never knows which companies
would later join the index. It cannot correct for delisted names - see
universe.py - so returns here are optimistic by an unknown but real margin.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

import universe as U


@dataclass
class StockParams:
    lookback_months: int = 12       # momentum window
    skip_months: int = 1            # skip most recent month (reversal)
    top_n: int = 20                 # names held
    min_price: float = 5.0
    min_dollar_volume: float = 5e6  # liquidity floor, 60-day average

    use_trend_template: bool = True
    use_regime_filter: bool = True
    regime_ma: int = 200

    vol_target: bool = True         # size inversely to volatility
    vol_lookback: int = 60

    cost_bps: float = 10.0          # round trip per switched name
    initial_capital: float = 10_000.0


def build_panel(frames, benchmark="SPY"):
    """Assemble aligned close / volume panels from {symbol: OHLCV}."""
    close = pd.DataFrame({s: f["Close"] for s, f in frames.items()})
    volume = pd.DataFrame({s: f["Volume"] for s, f in frames.items()})
    close = close.sort_index()
    volume = volume.reindex(close.index)
    return close, volume


def trend_template(close, params: StockParams):
    """Minervini's stage-2 screen, as a boolean frame aligned to `close`."""
    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()
    hi52 = close.rolling(252).max()
    lo52 = close.rolling(252).min()

    return (
        (close > ma150) & (close > ma200)
        & (ma150 > ma200)
        & (ma200 > ma200.shift(21))          # 200-day rising over a month
        & (ma50 > ma150)
        & (close > ma50)
        & (close > lo52 * 1.30)              # 30% off the 52-week low
        & (close > hi52 * 0.75)              # within 25% of the 52-week high
    )


def run(frames, p: StockParams, snapshots=None, start="2000-01-01", end=None,
        benchmark="SPY"):
    """Monthly-rebalanced cross-sectional momentum. Returns (equity, log)."""
    close, volume = build_panel(frames)
    close = close.loc[start:end] if end else close.loc[start:]
    volume = volume.reindex(close.index)

    dollar_volume = (close * volume).rolling(60).mean()
    template = trend_template(close, p) if p.use_trend_template else None
    realised_vol = close.pct_change().rolling(p.vol_lookback).std() * np.sqrt(252)

    bench = close[benchmark] if benchmark in close else None
    bench_ma = bench.rolling(p.regime_ma).mean() if bench is not None else None

    month_ends = close.resample("M").last().index
    month_ends = [d for d in month_ends if d in close.index or True]
    # map each month end to the last actual trading day at or before it
    trading_month_ends = []
    for d in month_ends:
        prior = close.index[close.index <= d]
        if len(prior):
            trading_month_ends.append(prior[-1])
    trading_month_ends = sorted(set(trading_month_ends))

    lb = p.lookback_months * 21
    sk = p.skip_months * 21
    warmup = max(lb + sk, 252) + 5

    equity = p.initial_capital
    curve, log = [], []
    held = {}

    for i in range(1, len(trading_month_ends)):
        signal_day = trading_month_ends[i - 1]
        hold_start = trading_month_ends[i - 1]
        hold_end = trading_month_ends[i]

        loc = close.index.get_loc(signal_day)
        if loc < warmup:
            continue

        # ---- regime: flat while the index is below its own 200-day ---------
        risk_on = True
        if p.use_regime_filter and bench is not None:
            b, bm = bench.iloc[loc], bench_ma.iloc[loc]
            risk_on = bool(np.isfinite(bm) and b > bm)

        picks = {}
        if risk_on:
            # ---- eligible: in the index that day, liquid, priced ----------
            if snapshots is not None:
                members = U.members_on(snapshots, signal_day)
            else:
                members = set(close.columns)
            eligible = [s for s in close.columns if s in members]

            px_now = close.iloc[loc]
            eligible = [s for s in eligible
                        if np.isfinite(px_now.get(s, np.nan)) and px_now[s] >= p.min_price
                        and np.isfinite(dollar_volume.iloc[loc].get(s, np.nan))
                        and dollar_volume.iloc[loc][s] >= p.min_dollar_volume]

            if p.use_trend_template:
                row = template.iloc[loc]
                eligible = [s for s in eligible if bool(row.get(s, False))]

            # ---- rank by 12-1 momentum ------------------------------------
            past = close.iloc[loc - sk]
            older = close.iloc[loc - sk - lb]
            mom = {}
            for s in eligible:
                a, b = past.get(s, np.nan), older.get(s, np.nan)
                if np.isfinite(a) and np.isfinite(b) and b > 0:
                    mom[s] = a / b - 1
            ranked = sorted(mom, key=mom.get, reverse=True)[: p.top_n]

            if ranked:
                if p.vol_target:
                    inv = {}
                    for s in ranked:
                        v = realised_vol.iloc[loc].get(s, np.nan)
                        inv[s] = 1.0 / v if np.isfinite(v) and v > 0 else 0.0
                    total = sum(inv.values())
                    picks = ({s: inv[s] / total for s in ranked} if total > 0
                             else {s: 1 / len(ranked) for s in ranked})
                else:
                    picks = {s: 1 / len(ranked) for s in ranked}

        # ---- realise the month ---------------------------------------------
        start_px = close.loc[hold_start]
        end_px = close.loc[hold_end]
        period = 0.0
        for s, w in picks.items():
            a, b = start_px.get(s, np.nan), end_px.get(s, np.nan)
            if np.isfinite(a) and np.isfinite(b) and a > 0:
                period += w * (b / a - 1)

        turnover = sum(abs(picks.get(s, 0) - held.get(s, 0))
                       for s in set(picks) | set(held))
        period -= (p.cost_bps / 10_000) * turnover

        equity *= 1 + period
        curve.append((hold_end, equity, len(picks)))
        log.append({"date": hold_end, "n": len(picks), "return_pct": period * 100,
                    "risk_on": risk_on, "holdings": ",".join(list(picks)[:10])})
        held = picks

    curve_df = pd.DataFrame(curve, columns=["date", "equity", "positions"]).set_index("date")
    return curve_df["equity"], pd.DataFrame(log)


def metrics(equity, ppy=12):
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1
    dd = (equity / equity.cummax() - 1).min()
    r = equity.pct_change().dropna()
    vol = r.std() * np.sqrt(ppy)
    return {
        "cagr_pct": cagr * 100,
        "max_dd_pct": dd * 100,
        "vol_pct": vol * 100,
        "sharpe": (r.mean() * ppy) / vol if vol > 0 else 0.0,
        "calmar": cagr / abs(dd) if dd < 0 else 0.0,
        "final": equity.iloc[-1],
    }
