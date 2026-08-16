"""
The original Turtle system, implemented faithfully.

Source rules: Dennis/Eckhardt's 1983-84 curriculum as published by Curtis Faith
(Way of the Turtle) and the circulated "Original Turtle Trading Rules" document.

What makes this different from the trend system in engine.py, and why those
differences are the whole point:

  * It trades BOTH directions. A long-only trend follower sits out every bear
    market; the Turtles' best years came from short positions in falling
    markets. This is the single biggest structural gap in the earlier build.
  * It sizes by volatility, not by price. One "Unit" is the quantity for which
    a 1N move (N = 20-day ATR) equals 1% of equity, so a position in a quiet
    market and a position in a wild one carry identical risk.
  * It runs a futures-style margin account. Twenty-odd positions each risking
    1% implies gross notional well above equity - impossible in the cash
    account the earlier version modelled, and the reason its exposure was
    throttled to 60%.
  * It pyramids: up to 4 Units per market, added every 1/2 N in favour, with
    every stop moved up to 2N below the newest Unit.
  * It exits on the opposite Donchian extreme, not a trailing ATR stop.

Two systems, run side by side as the Turtles ran them:
  System 1: enter on 20-day breakout, exit on 10-day opposite extreme.
             Skipped if the previous S1 breakout in that market was a winner,
             unless price reaches the 55-day failsafe level.
  System 2: enter on 55-day breakout, exit on 20-day opposite extreme. Always
             taken.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from data_manager import add_atr

TRADING_DAYS = 252


@dataclass
class TurtleParams:
    # entries / exits
    s1_entry: int = 20
    s1_exit: int = 10
    s2_entry: int = 55
    s2_exit: int = 20
    use_s1: bool = True
    use_s2: bool = True
    use_skip_rule: bool = True

    # risk
    atr_period: int = 20
    risk_per_unit: float = 0.01      # 1N move == 1% of equity
    stop_atr: float = 2.0            # 2N stop
    pyramid_step_atr: float = 0.5    # add a Unit every 1/2 N in favour
    max_units_per_market: int = 4
    max_units_per_group: int = 6     # closely correlated markets
    max_units_per_direction: int = 12
    max_gross_leverage: float = 4.0  # futures-style; caps total notional/equity

    # costs
    cost_bps: float = 3.0            # commission + slippage, per side
    initial_capital: float = 10_000.0
    allow_shorts: bool = True


# Closely correlated groups, in the spirit of the Turtles' own groupings
# (heating oil/crude, gold/silver, the European currencies, and so on).
GROUPS = {
    "SPY": "equity", "QQQ": "equity", "IWM": "equity", "EFA": "equity", "EEM": "equity",
    "XLE": "energy", "USO": "energy", "UNG": "energy",
    "TLT": "rates", "IEF": "rates", "LQD": "rates", "HYG": "rates",
    "GLD": "metals", "SLV": "metals",
    "FXE": "fx", "FXY": "fx", "FXB": "fx", "FXF": "fx", "FXA": "fx", "UUP": "fx",
    "DBA": "ags", "CORN": "ags", "WEAT": "ags", "SOYB": "ags",
    "DBC": "commodity", "IYR": "realestate",
}


@dataclass
class Position:
    symbol: str
    direction: int                    # +1 long, -1 short
    units: list = field(default_factory=list)   # each: dict(price, qty, date)
    stop: float = 0.0
    last_add_price: float = 0.0
    entry_date: pd.Timestamp = None
    system: str = ""
    n_at_entry: float = 0.0

    @property
    def qty(self):
        return sum(u["qty"] for u in self.units)

    @property
    def avg_price(self):
        total = self.qty
        return sum(u["price"] * u["qty"] for u in self.units) / total if total else 0.0

    def unrealised(self, price):
        return (price - self.avg_price) * self.qty * self.direction


def prepare(df, p: TurtleParams):
    """Attach Donchian channels and N. All series exclude the current bar."""
    out = df.copy()
    out["N"] = add_atr(out, p.atr_period)
    prior_h, prior_l = out["High"].shift(1), out["Low"].shift(1)
    for window, tag in [(p.s1_entry, "s1e"), (p.s1_exit, "s1x"),
                        (p.s2_entry, "s2e"), (p.s2_exit, "s2x")]:
        out[f"hi_{tag}"] = prior_h.rolling(window).max()
        out[f"lo_{tag}"] = prior_l.rolling(window).min()
    return out


def run(data, p: TurtleParams, symbols=None):
    """Backtest the Turtle system across a dict of {symbol: OHLCV frame}."""
    symbols = symbols or list(data)
    frames = {s: prepare(data[s], p) for s in symbols}
    calendar = sorted(set().union(*(set(f.index) for f in frames.values())))

    equity = p.initial_capital
    realised = 0.0
    positions = {}
    pending = []
    last_breakout_won = {}            # per symbol: was the previous S1 breakout a winner
    closed, curve = [], []
    cost = p.cost_bps / 10_000

    def units_in_direction(direction):
        return sum(len(pos.units) for pos in positions.values() if pos.direction == direction)

    def units_in_group(group, direction):
        return sum(len(pos.units) for s, pos in positions.items()
                   if GROUPS.get(s, s) == group and pos.direction == direction)

    def gross_notional(day):
        total = 0.0
        for s, pos in positions.items():
            if day in frames[s].index:
                total += abs(pos.qty) * frames[s].loc[day, "Close"]
        return total

    for today in calendar:
        # ---- 1. act on yesterday's signals, at today's open -----------------
        for sym, direction, system, kind in pending:
            frame = frames[sym]
            if today not in frame.index:
                continue
            bar = frame.loc[today]
            n = bar.N
            if not np.isfinite(n) or n <= 0:
                continue

            pos = positions.get(sym)
            if pos and pos.direction != direction:
                continue
            if pos and len(pos.units) >= p.max_units_per_market:
                continue
            if units_in_direction(direction) >= p.max_units_per_direction:
                continue
            if units_in_group(GROUPS.get(sym, sym), direction) >= p.max_units_per_group:
                continue

            # One Unit: a 1N move equals risk_per_unit of equity.
            qty = (equity * p.risk_per_unit) / n
            fill = bar.Open * (1 + cost * direction)
            if qty <= 0 or fill <= 0:
                continue
            if gross_notional(today) + qty * fill > equity * p.max_gross_leverage:
                continue

            if pos is None:
                pos = Position(symbol=sym, direction=direction, entry_date=today,
                               system=system, n_at_entry=n)
                positions[sym] = pos
            pos.units.append({"price": fill, "qty": qty, "date": today})
            pos.last_add_price = fill
            # Every stop moves to 2N from the newest Unit.
            pos.stop = fill - direction * p.stop_atr * n
        pending = []

        # ---- 2. manage open positions --------------------------------------
        for sym in list(positions):
            frame = frames[sym]
            if today not in frame.index:
                continue
            bar = frame.loc[today]
            pos = positions[sym]
            d = pos.direction

            exit_price = exit_reason = None

            # 2N stop, checked against the intraday extreme.
            if d > 0 and bar.Low <= pos.stop:
                exit_price, exit_reason = min(bar.Open, pos.stop), "STOP"
            elif d < 0 and bar.High >= pos.stop:
                exit_price, exit_reason = max(bar.Open, pos.stop), "STOP"
            else:
                # Donchian exit on the opposite extreme.
                tag = "s1x" if pos.system == "S1" else "s2x"
                lo, hi = bar[f"lo_{tag}"], bar[f"hi_{tag}"]
                if d > 0 and np.isfinite(lo) and bar.Close < lo:
                    exit_price, exit_reason = bar.Close, "DONCHIAN"
                elif d < 0 and np.isfinite(hi) and bar.Close > hi:
                    exit_price, exit_reason = bar.Close, "DONCHIAN"

            if exit_price is not None:
                fill = exit_price * (1 - cost * d)
                pnl = (fill - pos.avg_price) * pos.qty * d
                realised += pnl
                won = pnl > 0
                if pos.system == "S1":
                    last_breakout_won[sym] = won
                closed.append({
                    "symbol": sym, "system": pos.system,
                    "direction": "LONG" if d > 0 else "SHORT",
                    "entry_date": pos.entry_date, "exit_date": today,
                    "entry_price": pos.avg_price, "exit_price": fill,
                    "units": len(pos.units), "qty": pos.qty,
                    "pnl": pnl, "pnl_pct": (fill / pos.avg_price - 1) * 100 * d,
                    "exit_reason": exit_reason,
                    "days_held": (today - pos.entry_date).days,
                })
                del positions[sym]
                continue

            # Pyramid: add a Unit every 1/2 N in favour of the position.
            if len(pos.units) < p.max_units_per_market and np.isfinite(bar.N) and bar.N > 0:
                trigger = pos.last_add_price + d * p.pyramid_step_atr * bar.N
                reached = bar.High >= trigger if d > 0 else bar.Low <= trigger
                if reached:
                    pending.append((sym, d, pos.system, "ADD"))

        # ---- 3. scan for new breakouts -------------------------------------
        for sym in symbols:
            frame = frames[sym]
            if today not in frame.index or sym in positions:
                continue
            bar = frame.loc[today]
            if not np.isfinite(bar.N) or bar.N <= 0:
                continue

            signal = None
            # System 2 takes precedence: it is never skipped.
            if p.use_s2:
                if np.isfinite(bar.hi_s2e) and bar.Close > bar.hi_s2e:
                    signal = (1, "S2")
                elif p.allow_shorts and np.isfinite(bar.lo_s2e) and bar.Close < bar.lo_s2e:
                    signal = (-1, "S2")

            if signal is None and p.use_s1:
                long_break = np.isfinite(bar.hi_s1e) and bar.Close > bar.hi_s1e
                short_break = p.allow_shorts and np.isfinite(bar.lo_s1e) and bar.Close < bar.lo_s1e
                if long_break or short_break:
                    # Skip rule: pass on the entry if the previous S1 breakout
                    # in this market was a winner.
                    if not (p.use_skip_rule and last_breakout_won.get(sym, False)):
                        signal = (1 if long_break else -1, "S1")
                    else:
                        last_breakout_won[sym] = False   # skipped once, arm the next

            if signal:
                pending.append((sym, signal[0], signal[1], "NEW"))

        # ---- 4. mark to market ---------------------------------------------
        unreal = 0.0
        for s, pos in positions.items():
            if today in frames[s].index:
                unreal += pos.unrealised(frames[s].loc[today, "Close"])
        equity = p.initial_capital + realised + unreal
        curve.append((today, equity, len(positions),
                      sum(len(x.units) for x in positions.values())))

    curve_df = pd.DataFrame(curve, columns=["date", "equity", "positions", "units"]).set_index("date")
    return pd.DataFrame(closed), curve_df


def stats(trades, curve, benchmark=None):
    eq = curve["equity"]
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1 if eq.iloc[-1] > 0 else -1.0
    r = eq.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    vol = r.std() * np.sqrt(TRADING_DAYS)
    dd = (eq / eq.cummax() - 1).min()

    out = {
        "cagr_pct": cagr * 100,
        "max_dd_pct": dd * 100,
        "vol_pct": vol * 100,
        "sharpe": (r.mean() * TRADING_DAYS) / vol if vol > 0 else 0.0,
        "calmar": cagr / abs(dd) if dd < 0 else 0.0,
        "final_equity": eq.iloc[-1],
        "trades": len(trades),
        "avg_units": curve["units"].mean(),
    }
    if len(trades):
        wins = trades[trades.pnl > 0]
        losses = trades[trades.pnl <= 0]
        gl = abs(losses.pnl.sum())
        out.update({
            "win_rate_pct": len(wins) / len(trades) * 100,
            "profit_factor": wins.pnl.sum() / gl if gl > 0 else float("inf"),
            "long_pct": (trades.direction == "LONG").mean() * 100,
            "short_pnl": trades[trades.direction == "SHORT"].pnl.sum(),
            "long_pnl": trades[trades.direction == "LONG"].pnl.sum(),
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
