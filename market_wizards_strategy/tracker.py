"""
Forward performance log.

Everything else in this repo is a backtest, and backtests are the weakest form
of evidence there is - the strategy was chosen after seeing the data. This
records what actually happens from the day paper trading starts, against SPY
over the identical window, which is the only evidence that was not selected
with hindsight.
"""

import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

import config
import data_manager as dm

LOG = "forward_log.jsonl"


def _path():
    os.makedirs(config.STATE_DIR, exist_ok=True)
    return os.path.join(config.STATE_DIR, LOG)


def record(equity, holdings, source="paper", note=""):
    """Append one observation. Safe to call daily; one row per day is kept."""
    today = datetime.now().date().isoformat()
    rows = load_raw()
    rows = [r for r in rows if r.get("date") != today]

    spy = dm.load("SPY")["Close"]
    rows.append({
        "date": today,
        "equity": float(equity),
        "spy": float(spy.iloc[-1]),
        "holdings": holdings,
        "source": source,
        "note": note,
    })
    with open(_path(), "w") as fh:
        for r in sorted(rows, key=lambda x: x["date"]):
            fh.write(json.dumps(r) + "\n")
    return len(rows)


def load_raw():
    if not os.path.exists(_path()):
        return []
    with open(_path()) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def report():
    """Strategy vs SPY since tracking began."""
    rows = load_raw()
    if len(rows) < 2:
        return {"observations": len(rows),
                "message": "Not enough history yet - need at least two days."}

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")

    strat = df["equity"] / df["equity"].iloc[0] - 1
    bench = df["spy"] / df["spy"].iloc[0] - 1
    days = (df.index[-1] - df.index[0]).days

    out = {
        "observations": len(df),
        "since": df.index[0].date().isoformat(),
        "days_live": days,
        "strategy_return_pct": strat.iloc[-1] * 100,
        "spy_return_pct": bench.iloc[-1] * 100,
        "excess_pct": (strat.iloc[-1] - bench.iloc[-1]) * 100,
        "strategy_max_dd_pct": ((df["equity"] / df["equity"].cummax() - 1).min()) * 100,
        "spy_max_dd_pct": ((df["spy"] / df["spy"].cummax() - 1).min()) * 100,
    }

    # A few weeks of data proves nothing; say so rather than implying otherwise.
    if days < 180:
        out["caveat"] = (f"{days} days is far too short to judge. Monthly rotation "
                         f"turns over ~12 times a year; a year is a small sample, "
                         f"and this is much less than that.")
    return out
