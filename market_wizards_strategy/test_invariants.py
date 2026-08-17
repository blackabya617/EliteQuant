#!/usr/bin/env python3
"""
Regression tests for the live-vs-backtest invariants.

Three separate bugs in this project were all the same shape: `backtest()` was
correct, and the live trading path reimplemented the same decision slightly
differently, so the strategy actually running was not the strategy the README
describes. Each was found by hand, one per session. These tests pin the
invariants so a fourth gets caught automatically.

    python test_invariants.py

Deliberately dependency-free (no pytest in this environment) and safe to run
anywhere - it reads cached market data and a scratch account, and never
touches the real paper_state.json.
"""

import sys
import tempfile

import numpy as np
import pandas as pd

import papertrade
from rotation import (RotationParams, backtest, last_complete_month,
                      month_end_prices, select, target_weights)

FAILURES = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f"\n         {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


# ---------------------------------------------------------------------------
# 1. the live signal must be the strategy that was backtested
# ---------------------------------------------------------------------------

def test_signal_anchor_matches_backtest():
    """Session 8's bug: target_weights() anchored on the running partial month.

    backtest() picks holdings with select(as_of=<completed month>). The live
    signal must use that same anchor, or the traded strategy differs from the
    validated one - and, because a partial month's data changes daily, the
    holdings would depend on which day the scheduler fired.
    """
    m = month_end_prices()
    p = RotationParams()

    anchor = last_complete_month(m)
    check("anchor is not the running month",
          anchor == len(m) - 2,
          f"anchor index {anchor}, panel length {len(m)}")

    live = set(target_weights(p)["holdings"])
    convention = set(select(m, p, as_of=m.index[anchor]))
    check("live holdings == backtest-convention holdings",
          live == convention,
          f"live-only={sorted(live - convention)} convention-only={sorted(convention - live)}")


def test_exposure_uses_raw_returns():
    """Session 6's bug: the vol estimate was fed its own already-scaled output.

    Scaling exposure down damps the recorded return, so feeding that back in
    understates volatility and lets exposure creep back up - the sizing model
    undoing its own risk cut using evidence the cut manufactured. The log must
    therefore carry an unscaled series, and it must actually differ from the
    scaled one whenever any exposure cut has occurred.
    """
    m = month_end_prices()
    _, log = backtest(m, RotationParams())

    check("backtest log exposes raw_return_pct",
          "raw_return_pct" in log.columns)

    cut = log[log["exposure"] < 0.999]
    check("raw and scaled returns differ where exposure was cut",
          len(cut) > 0 and not np.allclose(cut["raw_return_pct"], cut["return_pct"]),
          f"{len(cut)} months had exposure < 1.0")

    # scaled == raw * exposure, everywhere
    check("scaled return equals raw * exposure",
          np.allclose(log["return_pct"], log["raw_return_pct"] * log["exposure"], atol=1e-9))


# ---------------------------------------------------------------------------
# 2. the live account must not silently cost more than the backtest assumes
# ---------------------------------------------------------------------------

def test_round_trip_cost_matches_backtest():
    """Session 7's bug: papertrade charged full COST_BPS on *each* leg.

    cost_bps is a round-trip convention everywhere else in the project, so a
    full swap of one holding for another must cost COST_BPS total, not 2x.
    """
    state = papertrade.new_account(10_000.0)
    state["cash"] = 0.0
    state["shares"] = {"A": 100.0}
    prices = {"A": 100.0, "B": 100.0}

    papertrade.rebalance(state, {"B": 1.0}, prices)
    final = papertrade.equity(state, prices)
    implied_bps = (10_000.0 - final) / 10_000.0 * 10_000

    check("full round-trip costs COST_BPS, not 2x",
          abs(implied_bps - papertrade.COST_BPS) < 0.01,
          f"implied {implied_bps:.2f} bps, expected {papertrade.COST_BPS:.2f}")


# ---------------------------------------------------------------------------
# 3. general safety properties
# ---------------------------------------------------------------------------

def test_weights_never_exceed_capital():
    p = RotationParams()
    signal = target_weights(p)
    total = sum(signal["holdings"].values())
    check("target weights sum to <= 1.0",
          total <= 1.0 + 1e-9,
          f"weights summed to {total:.6f}")
    check("cash weight is consistent with holdings",
          abs(signal["cash_weight"] - (1.0 - total)) < 1e-9)


def test_rebalance_refuses_to_margin():
    """The guard added after the sizing audit: never silently overdraw cash."""
    state = papertrade.new_account(10_000.0)
    prices = {"A": 100.0, "B": 100.0}
    try:
        papertrade.rebalance(state, {"A": 0.75, "B": 0.75}, prices)
        check("malformed target (sums to 1.5) is refused", False,
              "rebalance accepted weights summing above 1.0")
    except RuntimeError:
        check("malformed target (sums to 1.5) is refused", True)


def test_no_lookahead_in_select():
    """select() must not consult any data after its as_of date."""
    m = month_end_prices()
    p = RotationParams()
    cutoff = m.index[-6]

    full = select(m, p, as_of=cutoff)
    truncated = select(m[m.index <= cutoff], p, as_of=cutoff)
    check("select() ignores data after as_of",
          set(full) == set(truncated),
          f"full={sorted(full)} truncated={sorted(truncated)}")


def test_step_is_idempotent():
    """Running the daily step twice must not double-trade."""
    with tempfile.TemporaryDirectory() as tmp:
        papertrade.step(directory=tmp)
        _, _, second = papertrade.step(directory=tmp)
        check("second same-day step places no trades",
              second == [],
              f"second run produced {len(second)} actions")


if __name__ == "__main__":
    print("\nLive-vs-backtest invariants\n" + "=" * 60)
    for fn in [
        test_signal_anchor_matches_backtest,
        test_exposure_uses_raw_returns,
        test_round_trip_cost_matches_backtest,
        test_weights_never_exceed_capital,
        test_rebalance_refuses_to_margin,
        test_no_lookahead_in_select,
        test_step_is_idempotent,
    ]:
        print(f"\n{fn.__name__}:")
        fn()

    print("\n" + "=" * 60)
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
        sys.exit(1)
    print("all invariants hold")
