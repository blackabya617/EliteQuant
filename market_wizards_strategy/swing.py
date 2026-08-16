"""
Cross-sectional selection + trade-level risk management.

rotation.py rebalances on a calendar: every month it holds whatever currently
ranks in the top N, full stop. It does not know or care whether an individual
position is up 40% or down 2% - it will drop a winner from the ranking exactly
as readily as a loser. That is not "cut losses short, let winners run"; it is
"trade the calendar."

This module is the literal version of that instruction, combined with
cross-sectional ranking so the asymmetric payoff has somewhere to come from:
a few large winners running as long as their trend holds, offset by many small
losses cut fast. Mechanically it is engine.py's per-position ATR stop and
chandelier trail (proven honest in that module), applied across a ranked
universe instead of one instrument, with new entries filling slots as old
positions exit - closer to how the Market Wizards actually traded than a
monthly rebalance is.

Universe options:
  ETFs (rotation.DEFAULT_UNIVERSE, or with factor ETFs added) - clean data,
    no survivorship bias, but only ~20-25 names so the payoff distribution has
    limited room to be fat-tailed.
  individual stocks, point-in-time S&P membership (universe.py) - much more
    room for a fat right tail, but carries the same delisting-data hole
    documented in stocks.py: results are optimistic, worse the further back
    the test runs.

"Quality" here is a systematic proxy, not fundamentals: low realised
volatility and small drawdown-from-high, which is what QUAL/USMV approximate
without a fundamentals feed. Real fundamentals (ROE, debt, earnings stability)
would be a better quality screen and are not attempted - flagged, not silently
assumed away.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from data_manager import add_atr

TRADING_DAYS = 252


@dataclass
class SwingParams:
    # ranking / entry
    momentum_lookback: int = 126     # ~6 months
    momentum_skip: int = 21          # skip most recent month
    quality_lookback: int = 126
    quality_weight: float = 0.5      # 0 = pure momentum, 1 = pure quality proxy
    max_positions: int = 10
    min_price: float = 5.0

    # exit: cut losses short, let winners run
    atr_period: int = 20
    stop_atr: float = 2.5            # initial stop, in ATRs below entry
    trail_atr: float = 4.0           # chandelier trail from highest close since entry
    regime_ma: int = 200             # SPY must be above this to open NEW positions

    # portfolio-level throttle: distinct from the per-position stop above.
    # Individual-stock momentum names are high-beta and correlated, so broad
    # selloffs hit most open positions at once regardless of how diversified
    # the picks are - diversifying the NAMES does not diversify that risk.
    # This scales new-entry size down (never forces an exit) when the book's
    # own trailing volatility runs hot, the same mechanism rotation.py uses.
    portfolio_vol_cap: float = None  # annualised: e.g. 0.15; None disables
    portfolio_vol_lookback: int = 20

    # sizing
    risk_pct: float = 0.02           # equity fraction risked per new position
    max_weight: float = 0.15         # cap per position, as equity fraction

    cost_bps: float = 5.0            # Robinhood is commission-free; this is slippage only
    initial_capital: float = 10_000.0


def _quality_score(close):
    """Low realised vol and small drawdown-from-high, both rank-normalised.

    Higher is "higher quality" in this proxy sense: steadier, less beaten down.
    """
    ret = close.pct_change()
    vol = ret.rolling(126).std() * np.sqrt(TRADING_DAYS)
    dd = close / close.rolling(126).max() - 1
    return (-vol.rank(axis=1, pct=True)) + dd.rank(axis=1, pct=True)


def rank_universe(close, p: SwingParams, regime_ok):
    """Composite momentum+quality score for every symbol, each trading day.

    Returns a frame aligned to `close`, NaN wherever a name is not eligible.
    """
    past = close.shift(p.momentum_skip)
    older = close.shift(p.momentum_skip + p.momentum_lookback)
    momentum = (past / older - 1).rank(axis=1, pct=True)
    quality = _quality_score(close)

    score = (1 - p.quality_weight) * momentum + p.quality_weight * quality
    eligible = (close >= p.min_price) & regime_ok.to_numpy()[:, None]
    return score.where(eligible)


def run(frames, p: SwingParams, benchmark="SPY", start="2010-01-01", end=None,
       universe_by_date=None):
    """Backtest. `universe_by_date(date) -> set(symbols)` restricts eligibility
    to point-in-time membership when supplied (see universe.py); omit for a
    fixed ETF universe where every symbol is always eligible.
    """
    # Forward-fill, not drop: a single ETF's data gap (late listing, one-off
    # holiday mismatch) must not turn a held position's mark into NaN, which
    # silently poisons every equity value from that day forward.
    close = pd.DataFrame({s: f["Close"] for s, f in frames.items()}).sort_index().ffill()
    high = pd.DataFrame({s: f["High"] for s, f in frames.items()}).reindex(close.index).ffill()
    low = pd.DataFrame({s: f["Low"] for s, f in frames.items()}).reindex(close.index).ffill()
    close, high, low = close.loc[start:end], high.loc[start:end], low.loc[start:end]

    atr = pd.DataFrame({s: add_atr(frames[s].loc[close.index[0]:close.index[-1]], p.atr_period)
                        for s in close.columns})

    bench = close[benchmark]
    regime_ok = bench > bench.rolling(p.regime_ma).mean()
    score = rank_universe(close, p, regime_ok)

    cash = p.initial_capital
    positions = {}          # symbol -> dict(shares, entry_price, stop, peak)
    closed = []
    curve = []

    warmup = max(p.momentum_lookback + p.momentum_skip, p.regime_ma, 126) + 5

    for i in range(warmup, len(close)):
        today = close.index[i]
        day_close, day_high, day_low, day_atr = close.iloc[i], high.iloc[i], low.iloc[i], atr.iloc[i]

        # ---- manage open positions: stop, then trail --------------------
        for sym in list(positions):
            if sym not in day_close.index or not np.isfinite(day_close[sym]):
                continue
            pos = positions[sym]
            exit_price = exit_reason = None

            # The position's own stop is the only forced exit. A market-wide
            # regime flag gating every position would flatten winners the
            # instant SPY dipped below its average even if the position itself
            # was still trending fine - the opposite of letting winners run.
            # Regime only gates new entries below.
            if day_low[sym] <= pos["stop"]:
                exit_price = min(day_close[sym], pos["stop"])
                exit_reason = "STOP"

            if exit_price is not None:
                fill = exit_price * (1 - p.cost_bps / 10_000)
                pnl = (fill - pos["entry_price"]) * pos["shares"]
                cash += pos["shares"] * fill
                closed.append({"symbol": sym, "entry_date": pos["entry_date"],
                               "exit_date": today, "entry_price": pos["entry_price"],
                               "exit_price": fill, "pnl": pnl,
                               "pnl_pct": (fill / pos["entry_price"] - 1) * 100,
                               "days_held": (today - pos["entry_date"]).days,
                               "exit_reason": exit_reason})
                del positions[sym]
                continue

            if np.isfinite(day_atr.get(sym, np.nan)):
                pos["peak"] = max(pos["peak"], day_close[sym])
                pos["stop"] = max(pos["stop"], pos["peak"] - p.trail_atr * day_atr[sym])

        # ---- portfolio-level exposure throttle (new entries only) --------
        port_scale = 1.0
        if p.portfolio_vol_cap and i >= p.portfolio_vol_lookback + warmup:
            recent_eq = pd.Series([c[1] for c in curve[-p.portfolio_vol_lookback:]])
            recent_r = recent_eq.pct_change().dropna()
            realised = recent_r.std() * np.sqrt(TRADING_DAYS)
            if realised > 0:
                port_scale = min(1.0, p.portfolio_vol_cap / realised)

        # ---- fill open slots from the ranking ----------------------------
        slots = p.max_positions - len(positions)
        if slots > 0 and regime_ok.iloc[i]:
            eligible_syms = set(score.columns)
            if universe_by_date is not None:
                eligible_syms &= universe_by_date(today)
            ranked = score.iloc[i].dropna()
            ranked = ranked[ranked.index.isin(eligible_syms)].sort_values(ascending=False)

            equity_now = cash + sum(pos["shares"] * day_close.get(s, 0.0)
                                    for s, pos in positions.items())
            for sym in ranked.index:
                if slots <= 0:
                    break
                if sym in positions or sym == benchmark:
                    continue
                px, a = day_close.get(sym), day_atr.get(sym)
                if not np.isfinite(px) or not np.isfinite(a) or a <= 0 or px < p.min_price:
                    continue

                stop = px * (1 - 0.0) - p.stop_atr * a
                risk_per_share = px - stop
                if risk_per_share <= 0:
                    continue
                shares = (equity_now * p.risk_pct * port_scale) / risk_per_share
                shares = min(shares, (equity_now * p.max_weight * port_scale) / px, cash / px)
                if shares <= 0:
                    continue

                fill = px * (1 + p.cost_bps / 10_000)
                cash -= shares * fill
                positions[sym] = {"shares": shares, "entry_price": fill,
                                  "entry_date": today, "stop": stop, "peak": fill}
                slots -= 1

        held = sum(pos["shares"] * day_close.get(s, 0.0) for s, pos in positions.items())
        curve.append((today, cash + held, len(positions)))

    curve_df = pd.DataFrame(curve, columns=["date", "equity", "positions"]).set_index("date")
    return pd.DataFrame(closed), curve_df


def metrics(trades, curve, benchmark=None):
    eq = curve["equity"]
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1
    r = eq.pct_change().dropna()
    vol = r.std() * np.sqrt(TRADING_DAYS)
    dd = (eq / eq.cummax() - 1).min()
    out = {
        "cagr_pct": cagr * 100, "max_dd_pct": dd * 100, "vol_pct": vol * 100,
        "sharpe": (r.mean() * TRADING_DAYS) / vol if vol > 0 else 0.0,
        "calmar": cagr / abs(dd) if dd < 0 else 0.0,
        "trades": len(trades), "final_equity": eq.iloc[-1],
    }
    if len(trades):
        wins, losses = trades[trades.pnl > 0], trades[trades.pnl <= 0]
        gl = abs(losses.pnl.sum())
        out.update({
            "win_rate_pct": len(wins) / len(trades) * 100,
            "profit_factor": wins.pnl.sum() / gl if gl > 0 else float("inf"),
            "avg_win_pct": wins.pnl_pct.mean() if len(wins) else 0.0,
            "avg_loss_pct": losses.pnl_pct.mean() if len(losses) else 0.0,
            "payoff": abs(wins.pnl_pct.mean() / losses.pnl_pct.mean())
                      if len(wins) and len(losses) and losses.pnl_pct.mean() else 0.0,
            "best_pct": trades.pnl_pct.max(), "worst_pct": trades.pnl_pct.min(),
            "avg_days": trades.days_held.mean(),
        })
    if benchmark is not None:
        b = benchmark.reindex(eq.index).ffill().dropna()
        by = max((b.index[-1] - b.index[0]).days / 365.25, 1e-9)
        br = b.pct_change().dropna()
        bvol = br.std() * np.sqrt(TRADING_DAYS)
        out.update({
            "bench_cagr_pct": ((b.iloc[-1] / b.iloc[0]) ** (1 / by) - 1) * 100,
            "bench_max_dd_pct": (b / b.cummax() - 1).min() * 100,
            "bench_sharpe": (br.mean() * TRADING_DAYS) / bvol if bvol > 0 else 0.0,
        })
    return out
