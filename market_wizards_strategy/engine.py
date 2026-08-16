"""
Backtest engine for the Market Wizards strategy.

Design rules this engine enforces, each one fixing a defect in the first draft:

1. No lookahead. Signals are computed from bars up to and including the close of
   day t; every fill happens at the open of day t+1. That matches how the live
   alert works - scan after the close, act next morning.
2. Fills happen at prices that actually traded. The first draft filled pullback
   entries at the 50-day average, a level the market may never have touched.
3. Stops are volatility-scaled (ATR), not a fixed percentage. A flat 2% stop on
   SPY sits inside one day's noise for much of the sample.
4. Winners are not capped. A fixed take-profit is replaced by a trailing stop,
   which is the entire mechanism trend following earns its return from.
5. Costs are charged on every fill (commission + slippage).
6. Position size is capped by available cash - no accidental leverage.
7. An equity curve is tracked mark-to-market, so drawdown, CAGR and Sharpe are
   real numbers rather than a sum of trade P&L.
"""

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from data_manager import add_atr

TRADING_DAYS = 252


@dataclass
class Params:
    # regime filter
    trend_ma: int = 200
    trend_slope_lookback: int = 20      # MA must be higher than it was N days ago

    # entries
    breakout_lookback: int = 50         # Donchian breakout of prior N-day high
    pullback_ma: int = 50               # re-entry when price reclaims this MA
    use_breakout: bool = True
    use_pullback: bool = True
    volume_mult: float = 0.0            # 0 disables the volume filter

    # exits
    atr_period: int = 20
    stop_atr: float = 3.0               # initial stop, in ATRs below entry
    trail_atr: float = 5.0              # chandelier trail from highest high since entry
    exit_on_regime_break: bool = True
    time_stop_days: int = 0             # 0 disables

    # sizing and costs
    risk_pct: float = 0.02              # equity fraction risked per position
    max_positions: int = 1
    max_weight: float = 1.0             # cap on notional per position, as equity fraction
    commission_bps: float = 1.0         # per side
    slippage_bps: float = 2.0           # per side
    initial_capital: float = 10_000.0


@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: int
    reason: str
    stop: float
    peak: float
    exit_date: pd.Timestamp = None
    exit_price: float = None
    exit_reason: str = None
    pnl: float = None
    pnl_pct: float = None
    days_held: int = None
    mae_pct: float = 0.0                # worst adverse excursion while open


def indicators(df, p: Params):
    """Attach every series the rules need. All are causal (no future data)."""
    out = df.copy()
    out["MA_trend"] = out["Close"].rolling(p.trend_ma).mean()
    out["MA_pull"] = out["Close"].rolling(p.pullback_ma).mean()
    out["ATR"] = add_atr(out, p.atr_period)
    # prior-N-day high, explicitly excluding today's bar
    out["Donchian"] = out["High"].shift(1).rolling(p.breakout_lookback).max()
    out["VolAvg"] = out["Volume"].shift(1).rolling(20).mean()
    out["MA_trend_prev"] = out["MA_trend"].shift(p.trend_slope_lookback)
    return out


def entry_signal(row, prev, p: Params):
    """Return an entry reason for the close of this bar, or None.

    Evaluated on bar t; the caller fills at the open of bar t+1.
    """
    if np.isnan(row.MA_trend) or np.isnan(row.ATR) or np.isnan(row.Donchian):
        return None
    if np.isnan(row.MA_trend_prev):
        return None

    # Regime: above the long trend line, and that line itself is rising.
    if row.Close <= row.MA_trend:
        return None
    if row.MA_trend <= row.MA_trend_prev:
        return None

    if p.volume_mult and not np.isnan(row.VolAvg) and row.Volume < row.VolAvg * p.volume_mult:
        return None

    if p.use_breakout and row.Close > row.Donchian:
        return "BREAKOUT"

    # Pullback: price closed back above the mid MA having been below it.
    if p.use_pullback and not np.isnan(row.MA_pull) and not np.isnan(prev.MA_pull):
        if prev.Close < prev.MA_pull and row.Close > row.MA_pull:
            return "PULLBACK"

    return None


def run(data, p: Params, symbols=None):
    """Run the strategy over {symbol: frame} and return (trades, equity curve).

    Positions are opened at the next open after a signal and marked to market
    every day, so the equity curve includes open-trade P&L.
    """
    if isinstance(data, pd.DataFrame):
        data = {"SPY": data}
    symbols = symbols or list(data)

    prepared = {s: indicators(data[s], p) for s in symbols}
    calendar = sorted(set().union(*(set(f.index) for f in prepared.values())))

    cash = p.initial_capital
    open_trades = {}
    pending = []                     # signals raised at yesterday's close
    closed = []
    equity_rows = []

    cost_in = 1 + (p.commission_bps + p.slippage_bps) / 10_000
    cost_out = 1 - (p.commission_bps + p.slippage_bps) / 10_000

    for today in calendar:
        # ---- 1. fill yesterday's signals at today's open -------------------
        for sym, reason in pending:
            if sym in open_trades or len(open_trades) >= p.max_positions:
                continue
            frame = prepared[sym]
            if today not in frame.index:
                continue
            bar = frame.loc[today]
            if np.isnan(bar.ATR) or bar.ATR <= 0:
                continue

            fill = bar.Open * cost_in
            stop = fill - p.stop_atr * bar.ATR
            risk_per_share = fill - stop
            if risk_per_share <= 0:
                continue

            equity_now = cash + sum(
                t.shares * prepared[s].loc[today].Open
                for s, t in open_trades.items()
                if today in prepared[s].index
            )
            shares = int((equity_now * p.risk_pct) / risk_per_share)
            shares = min(shares, int((equity_now * p.max_weight) / fill), int(cash / fill))
            if shares <= 0:
                continue

            cash -= shares * fill
            open_trades[sym] = Trade(
                symbol=sym, entry_date=today, entry_price=fill, shares=shares,
                reason=reason, stop=stop, peak=bar.High,
            )
        pending = []

        # ---- 2. manage open positions on today's bar -----------------------
        for sym in list(open_trades):
            frame = prepared[sym]
            if today not in frame.index:
                continue
            bar = frame.loc[today]
            trade = open_trades[sym]

            excursion = (bar.Low / trade.entry_price - 1) * 100
            trade.mae_pct = min(trade.mae_pct, excursion)

            exit_price = exit_reason = None

            # Stop is checked against the intraday low, using the stop level
            # that was already in force at yesterday's close.
            if bar.Low <= trade.stop:
                # Gap through the stop fills at the open, not the stop price.
                exit_price = min(bar.Open, trade.stop)
                exit_reason = "STOP"
            elif p.exit_on_regime_break and not np.isnan(bar.MA_trend) and bar.Close < bar.MA_trend:
                exit_price = bar.Close
                exit_reason = "REGIME"
            elif p.time_stop_days and (today - trade.entry_date).days >= p.time_stop_days:
                exit_price = bar.Close
                exit_reason = "TIME"

            if exit_price is not None:
                fill = exit_price * cost_out
                cash += trade.shares * fill
                trade.exit_date = today
                trade.exit_price = fill
                trade.exit_reason = exit_reason
                trade.pnl = (fill - trade.entry_price) * trade.shares
                trade.pnl_pct = (fill / trade.entry_price - 1) * 100
                trade.days_held = (today - trade.entry_date).days
                closed.append(trade)
                del open_trades[sym]
                continue

            # Ratchet the trailing stop up only.
            trade.peak = max(trade.peak, bar.High)
            if not np.isnan(bar.ATR):
                trade.stop = max(trade.stop, trade.peak - p.trail_atr * bar.ATR)

        # ---- 3. scan for tomorrow's entries --------------------------------
        if len(open_trades) < p.max_positions:
            for sym in symbols:
                if sym in open_trades:
                    continue
                frame = prepared[sym]
                if today not in frame.index:
                    continue
                loc = frame.index.get_loc(today)
                if loc == 0:
                    continue
                reason = entry_signal(frame.iloc[loc], frame.iloc[loc - 1], p)
                if reason:
                    pending.append((sym, reason))

        # ---- 4. mark to market ---------------------------------------------
        held = sum(
            t.shares * prepared[s].loc[today].Close
            for s, t in open_trades.items()
            if today in prepared[s].index
        )
        equity_rows.append((today, cash + held, len(open_trades)))

    equity = pd.DataFrame(equity_rows, columns=["date", "equity", "positions"]).set_index("date")
    trades = pd.DataFrame([t.__dict__ for t in closed])
    return trades, equity


def stats(trades, equity, benchmark=None):
    """Summarise a run. Returns a plain dict so it is easy to tabulate."""
    eq = equity["equity"]
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    total_return = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1

    daily = eq.pct_change().dropna()
    vol = daily.std() * np.sqrt(TRADING_DAYS)
    sharpe = (daily.mean() * TRADING_DAYS) / vol if vol > 0 else 0.0
    downside = daily[daily < 0].std() * np.sqrt(TRADING_DAYS)
    sortino = (daily.mean() * TRADING_DAYS) / downside if downside > 0 else 0.0
    max_dd = (eq / eq.cummax() - 1).min()

    out = {
        "final_equity": eq.iloc[-1],
        "total_return_pct": total_return * 100,
        "cagr_pct": cagr * 100,
        "max_dd_pct": max_dd * 100,
        "vol_pct": vol * 100,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": cagr / abs(max_dd) if max_dd < 0 else 0.0,
        "exposure_pct": (equity["positions"] > 0).mean() * 100,
        "trades": len(trades),
    }

    if len(trades):
        wins = trades[trades.pnl > 0]
        losses = trades[trades.pnl <= 0]
        gross_win = wins.pnl.sum()
        gross_loss = abs(losses.pnl.sum())
        out.update({
            "win_rate_pct": len(wins) / len(trades) * 100,
            "profit_factor": gross_win / gross_loss if gross_loss > 0 else float("inf"),
            "avg_win_pct": wins.pnl_pct.mean() if len(wins) else 0.0,
            "avg_loss_pct": losses.pnl_pct.mean() if len(losses) else 0.0,
            "payoff": abs(wins.pnl_pct.mean() / losses.pnl_pct.mean())
                      if len(wins) and len(losses) and losses.pnl_pct.mean() != 0 else 0.0,
            "best_pct": trades.pnl_pct.max(),
            "worst_pct": trades.pnl_pct.min(),
            "avg_days": trades.days_held.mean(),
            "max_days": trades.days_held.max(),
        })

    if benchmark is not None:
        bench = benchmark.reindex(eq.index).ffill().dropna()
        if len(bench) > 1:
            b_years = max((bench.index[-1] - bench.index[0]).days / 365.25, 1e-9)
            b_cagr = (bench.iloc[-1] / bench.iloc[0]) ** (1 / b_years) - 1
            b_dd = (bench / bench.cummax() - 1).min()
            b_daily = bench.pct_change().dropna()
            b_vol = b_daily.std() * np.sqrt(TRADING_DAYS)
            out.update({
                "bench_cagr_pct": b_cagr * 100,
                "bench_max_dd_pct": b_dd * 100,
                "bench_sharpe": (b_daily.mean() * TRADING_DAYS) / b_vol if b_vol > 0 else 0.0,
                "excess_cagr_pct": (cagr - b_cagr) * 100,
            })

    return out
