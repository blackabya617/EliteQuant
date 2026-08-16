"""
Post-earnings-announcement drift (PEAD).

Distinct from every price-only strategy tested elsewhere in this project:
the signal is a fundamental surprise (actual EPS vs analyst estimate), not a
price or volume pattern. PEAD is one of the most replicated anomalies in the
academic literature (Bernard & Thomas, 1989, and hundreds of follow-ups): the
market underreacts to earnings surprises, and price keeps drifting toward
the "correct" level for weeks to months afterward.

Data: Alpha Vantage's EARNINGS endpoint, which is free but capped at 25
requests/day. That budget did not stretch to a proper cross-sectional
universe - this covers 4 large caps (AAPL, MSFT, JPM, XOM), picked for sector
spread (tech x2, financials, energy) rather than randomly, which is itself a
form of selection. Treat every number here as a proof-of-concept pointer, not
a validated result: ~300 quarterly events across 4 companies is a real sample
for an event study, but events from the same company in adjacent quarters are
not independent, and 4 companies cannot represent cross-sectional dispersion
the way even 20-30 would start to.
"""

import glob
import json
import os

import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "earnings_data")


def load_surprises():
    """{symbol: DataFrame(reported_date, surprise_pct)} for every cached symbol."""
    out = {}
    for path in glob.glob(os.path.join(DATA_DIR, "*.json")):
        symbol = os.path.basename(path)[:-5]
        with open(path) as fh:
            raw = json.load(fh)
        if isinstance(raw, dict):  # a couple of files still hold the full API blob
            raw = [{"reportedDate": q["reportedDate"], "surprisePercentage": q["surprisePercentage"]}
                   for q in raw.get("quarterlyEarnings", [])
                   if q.get("surprisePercentage") not in (None, "None")]
        df = pd.DataFrame(raw)
        df["reportedDate"] = pd.to_datetime(df["reportedDate"])
        df["surprisePercentage"] = pd.to_numeric(df["surprisePercentage"], errors="coerce")
        out[symbol] = df.dropna().sort_values("reportedDate")
    return out


def event_study(prices, surprises, hold_days=60, surprise_threshold=5.0,
                entry_lag_days=1):
    """Forward return after each earnings event, split by surprise direction.

    `prices` is {symbol: Close series}. Entry is `entry_lag_days` trading days
    after the report date (a conservative stand-in for "next open" without
    tracking pre/post-market report time per event), exit is `hold_days`
    trading days after entry. Every return is benchmarked against what a
    same-length, same-stock holding period earns on average, so "drift" means
    excess return over the stock's own baseline, not just a positive number.
    """
    rows = []
    for symbol, events in surprises.items():
        if symbol not in prices:
            continue
        px = prices[symbol]
        baseline = px.pct_change(hold_days).mean()  # this stock's typical N-day return

        for _, ev in events.iterrows():
            loc = px.index.searchsorted(ev.reportedDate)
            entry_loc = loc + entry_lag_days
            exit_loc = entry_loc + hold_days
            if entry_loc >= len(px) or exit_loc >= len(px):
                continue
            entry_px, exit_px = px.iloc[entry_loc], px.iloc[exit_loc]
            fwd_return = exit_px / entry_px - 1

            direction = ("big_beat" if ev.surprisePercentage >= surprise_threshold else
                        "big_miss" if ev.surprisePercentage <= -surprise_threshold else
                        "in_line")
            rows.append({
                "symbol": symbol, "report_date": ev.reportedDate,
                "surprise_pct": ev.surprisePercentage, "direction": direction,
                "fwd_return_pct": fwd_return * 100,
                "excess_vs_baseline_pct": (fwd_return - baseline) * 100,
            })
    return pd.DataFrame(rows)


def summarise(events):
    """Mean/median forward return and a paired t-test-style stat per bucket."""
    out = []
    for direction, grp in events.groupby("direction"):
        n = len(grp)
        mean_excess = grp.excess_vs_baseline_pct.mean()
        se = grp.excess_vs_baseline_pct.std() / np.sqrt(n) if n > 1 else np.nan
        t_stat = mean_excess / se if se and se > 0 else np.nan
        out.append({
            "direction": direction, "n_events": n,
            "mean_fwd_return_pct": grp.fwd_return_pct.mean(),
            "mean_excess_vs_baseline_pct": mean_excess,
            "win_rate_pct": (grp.fwd_return_pct > 0).mean() * 100,
            "t_stat": t_stat,
        })
    return pd.DataFrame(out).set_index("direction")
