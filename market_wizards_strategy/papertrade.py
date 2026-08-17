"""
Broker-free paper trading.

An Alpaca paper account simulates fills against real prices. So does this, with
no API keys, no account, and nothing that can leak. The portfolio state lives in
a JSON file committed alongside the code, so the forward record is auditable and
survives any machine.

The point of this file is evidence, not convenience. Every performance table in
the README is a backtest, and a backtest is chosen after seeing the data. What
gets written here is chosen before, which makes it the only honest measure of
whether the strategy works.

Fills are modelled at the next open after the signal, with 10bps of round-trip
cost, matching the backtest's assumptions so the two are comparable. That cost
is charged as COST_BPS/2 on each leg (sell the old position, buy the new one)
so a full swap nets to COST_BPS round-trip - charging the full rate on each
leg independently would double it, which is exactly the bug this comment
replaced: this file used to do that, quietly running the live paper account
at 2x the cost drag the backtest assumes for the same turnover.
"""

import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import data_manager as dm
from rotation import DEFAULT_UNIVERSE, RotationParams, target_weights

STATE_FILE = "paper_state.json"
COST_BPS = 10.0  # round-trip; each leg below charges half of this


def _path(directory=None):
    directory = directory or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(directory, STATE_FILE)


def new_account(capital=10_000.0):
    return {
        "created": datetime.now(timezone.utc).date().isoformat(),
        "initial_capital": capital,
        "cash": capital,
        "shares": {},
        "history": [],
        "rebalances": [],
    }


def load(directory=None):
    path = _path(directory)
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return new_account()


def save(state, directory=None):
    with open(_path(directory), "w") as fh:
        json.dump(state, fh, indent=2)


MAX_PRICE_STALENESS_DAYS = 6   # covers a long weekend plus a holiday


def _latest_prices(symbols):
    """Latest close per symbol, plus each symbol's own as-of date.

    Returns per-symbol dates rather than a single max: a max hides a stale
    symbol behind fresh ones, which is precisely the case worth catching.
    """
    prices, asof = {}, {}
    for s in symbols:
        try:
            close = dm.load(s)["Close"]
            prices[s] = float(close.iloc[-1])
            asof[s] = close.index[-1]
        except Exception:  # noqa: BLE001 - collected and reported by the caller
            continue
    return prices, asof


def equity(state, prices, strict=True):
    """Mark the book to `prices`.

    Strict by default, because the lenient version is a trap: summing only the
    holdings that happen to be present in `prices` values any unpriceable
    position at exactly zero. A single failed download would post a phantom
    loss the size of that position into a forward record that gets committed
    to git and never revisited. Refusing to produce a number is much better
    than producing a confidently wrong one.
    """
    missing = [s for s in state["shares"] if s not in prices]
    if missing and strict:
        raise RuntimeError(
            f"cannot price held position(s) {sorted(missing)} - refusing to "
            f"mark the book rather than value them at zero."
        )
    held = sum(qty * prices[s] for s, qty in state["shares"].items() if s in prices)
    return state["cash"] + held


def _check_data_health(state, target, prices, asof, now=None):
    """Refuse to trade or mark on missing or stale data.

    A missed day's observation is recoverable. A wrong one, committed to the
    permanent record, quietly corrupts the only evidence in this project that
    was not selected with hindsight.
    """
    now = pd.Timestamp(now or datetime.now(timezone.utc).date())

    unpriced_holdings = [s for s in state["shares"] if s not in prices]
    if unpriced_holdings:
        raise RuntimeError(f"held position(s) with no price: {sorted(unpriced_holdings)}")

    unpriced_targets = [s for s in target if s not in prices]
    if unpriced_targets:
        raise RuntimeError(
            f"target position(s) with no price: {sorted(unpriced_targets)} - "
            f"trading anyway would silently under-invest."
        )

    relevant = set(state["shares"]) | set(target) | {"SPY"}
    stale = {s: asof[s].date() for s in relevant
             if s in asof and (now - asof[s]).days > MAX_PRICE_STALENESS_DAYS}
    if stale:
        raise RuntimeError(
            f"price data stale by more than {MAX_PRICE_STALENESS_DAYS} days: "
            f"{stale} (today {now.date()})"
        )


def rebalance(state, target_weights, prices, note=""):
    """Move the book to `target_weights`. Fractional shares, cost on every trade.

    Two distinct failure modes are handled separately here, because they mean
    different things:

    A target whose weights sum above 1.0 is a bug upstream - a bad top_n, a
    duplicate symbol, an exposure cap that stopped capping. That is refused
    loudly, because silently trading into implicit margin is far worse than a
    crash.

    A target that sums to exactly 1.0 is legitimate but still cannot be filled
    at face value: selling $10,000 of one holding yields slightly less than
    $10,000 after costs, while the replacement buy is sized against pre-cost
    equity. The shortfall is precisely the transaction cost. Buys are
    therefore clamped to cash actually on hand. Without this the strategy
    would refuse to trade - and so halt - on any month the volatility cap
    allowed full exposure.
    """
    weight_sum = sum(target_weights.values())
    if weight_sum > 1.0 + 1e-9:
        raise RuntimeError(
            f"target weights sum to {weight_sum:.4f} (> 1.0), which implies "
            f"margin. Refusing to trade - fix the signal upstream."
        )

    total = equity(state, prices)
    actions = []

    for symbol in list(state["shares"]):
        if symbol not in target_weights and symbol in prices:
            qty = state["shares"].pop(symbol)
            proceeds = qty * prices[symbol] * (1 - COST_BPS / 2 / 10_000)
            state["cash"] += proceeds
            actions.append({"action": "sell", "symbol": symbol, "qty": qty,
                            "price": prices[symbol], "value": proceeds})

    for symbol, weight in target_weights.items():
        if symbol not in prices:
            continue
        target_value = total * weight
        current_qty = state["shares"].get(symbol, 0.0)
        current_value = current_qty * prices[symbol]
        drift = target_value - current_value
        if abs(drift) < total * 0.01:      # ignore sub-1% drift, as a broker would
            continue
        if drift > 0:
            # Never spend more than is actually on hand, cost included. The
            # gap is normally just the round-trip cost on a fully-invested
            # target; the weight-sum check above has already ruled out the
            # pathological case.
            affordable = state["cash"] / (1 + COST_BPS / 2 / 10_000)
            drift = min(drift, max(affordable, 0.0))
            if drift <= 0:
                continue

        qty_delta = drift / prices[symbol]
        cost = abs(drift) * COST_BPS / 2 / 10_000
        state["cash"] -= drift + cost
        new_qty = current_qty + qty_delta
        if new_qty <= 1e-9:
            state["shares"].pop(symbol, None)
        else:
            state["shares"][symbol] = new_qty
        actions.append({"action": "buy" if drift > 0 else "sell", "symbol": symbol,
                        "qty": abs(qty_delta), "price": prices[symbol],
                        "value": abs(drift)})

    if actions:
        state["rebalances"].append({
            "date": datetime.now(timezone.utc).date().isoformat(),
            "note": note,
            "target": target_weights,
            "actions": actions,
        })
    return actions


def mark(state, prices, spy_price, asof):
    """Record one daily observation. Idempotent per date.

    `asof` is a {symbol: date} map; the recorded `price_asof` is the OLDEST
    date among the priced symbols, not the newest. The oldest is the honest
    description of how current the mark actually is - a newest-date summary
    would read as fresh even when one leg of the book was days behind.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    relevant = [asof[s] for s in set(state["shares"]) | {"SPY"} if s in asof]
    price_asof = min(relevant).date().isoformat() if relevant else None

    state["history"] = [h for h in state["history"] if h["date"] != today]
    state["history"].append({
        "date": today,
        "price_asof": price_asof,
        "equity": equity(state, prices),
        "spy": spy_price,
        "holdings": {s: round(q, 6) for s, q in state["shares"].items()},
    })
    state["history"].sort(key=lambda h: h["date"])


def step(directory=None, capital=10_000.0, force_rebalance=False):
    """One daily cycle: price the book, rebalance if the month turned, record."""
    state = load(directory)
    if not state["history"] and state["cash"] == state["initial_capital"]:
        state["initial_capital"] = capital
        state["cash"] = capital

    # Use target_weights so the live book carries the same volatility cap the
    # backtest applies. Deriving weights as 1/top_n here would silently run the
    # account at full exposure while the tested strategy runs de-risked.
    params = RotationParams()
    signal = target_weights(params)
    target = signal["holdings"]

    symbols = sorted(set(DEFAULT_UNIVERSE) | set(state["shares"]) | {"SPY"})
    prices, asof = _latest_prices(symbols)
    if not prices:
        raise RuntimeError("No prices available; cannot mark the book.")
    _check_data_health(state, target, prices, asof)

    # Gate on the signal's ANCHOR month (the last completed month), not the
    # running calendar month. Same once-a-month cadence either way, but the
    # tag now names the month whose close actually determined these holdings,
    # so the rebalance log says what drove the trade rather than merely when
    # it happened.
    last = state["rebalances"][-1]["note"] if state["rebalances"] else None
    signal_month = signal["as_of"][:7]
    should = force_rebalance or (last != signal_month)

    actions = rebalance(state, target, prices, note=signal_month) if should else []
    mark(state, prices, prices.get("SPY"), asof)
    save(state, directory)
    return state, target, actions


def report(state=None, directory=None):
    state = state or load(directory)
    hist = state.get("history", [])
    if len(hist) < 2:
        return {"observations": len(hist),
                "message": "Needs at least two daily marks before it means anything."}

    df = pd.DataFrame(hist)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")

    strat = df["equity"] / df["equity"].iloc[0] - 1
    spy = df["spy"] / df["spy"].iloc[0] - 1
    days = (df.index[-1] - df.index[0]).days

    out = {
        "since": df.index[0].date().isoformat(),
        "observations": len(df),
        "days_live": days,
        "equity": df["equity"].iloc[-1],
        "strategy_return_pct": strat.iloc[-1] * 100,
        "spy_return_pct": spy.iloc[-1] * 100,
        "excess_pct": (strat.iloc[-1] - spy.iloc[-1]) * 100,
        "strategy_max_dd_pct": (df["equity"] / df["equity"].cummax() - 1).min() * 100,
        "spy_max_dd_pct": (df["spy"] / df["spy"].cummax() - 1).min() * 100,
    }
    if days < 365:
        out["caveat"] = (f"{days} days live. The backtest edge is a drawdown edge, "
                         f"which only shows up in a real selloff. Until one happens "
                         f"this number says nothing either way.")
    return out
