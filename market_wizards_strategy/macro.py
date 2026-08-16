"""
Macro regime data and signals - an information source nothing else in this
project touches. Every strategy tested so far, including the validated
rotation, reads only price. This reads the yield curve, policy rate, and
inflation/employment trend: what the global-macro wizards (Druckenmiller,
Kovner, Bacon, Soros) traded on, as distinct from the trend-followers and
stock-pickers everything else here is built from.

Source: FRED (Federal Reserve Economic Data), fetched as plain CSV, no key,
no rate limit - unlike Alpha Vantage's fundamentals/earnings endpoints, which
are capped at 25 free requests/day and reserved for the earnings-drift work
in earnings.py.

One real caveat, stated once here rather than caveated at every use site:
DFF (Fed funds), DGS10/T10Y2Y (Treasury yields) are market/policy data,
observed in real time with no revision - safe to backtest naively. CPIAUCSL
and GDPC1 are estimated then REVISED for months after first release; this
module's CSV pull has only the current, fully-revised values, not what was
actually known on each historical date. A backtest using CPI or GDP as a
trading signal therefore carries a small look-ahead bias baked into the data
itself, separate from and in addition to any bug in the backtest code. Where
that matters, it is flagged again at the point of use.
"""

import os
import subprocess

import numpy as np
import pandas as pd

CACHE_DIR = os.environ.get("MW_CACHE_DIR", os.path.join(os.path.dirname(__file__), "fred_data"))

SERIES = {
    "fed_funds": "DFF",         # daily, real-time, not revised
    "yield_10y": "DGS10",       # daily, real-time, not revised
    "yield_curve_10y2y": "T10Y2Y",  # daily, real-time, not revised
    "cpi": "CPIAUCSL",          # monthly, REVISED after first release
    "unemployment": "UNRATE",   # monthly, lightly revised
    "real_gdp": "GDPC1",        # quarterly, REVISED substantially after first release
}


def _fetch(fred_id):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"fred_{fred_id}.csv")
    if not os.path.exists(path) or os.path.getsize(path) < 200:
        subprocess.run(
            ["curl", "-sS", "-o", path,
             f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"],
            check=True, timeout=60,
        )
    return path


def load(name):
    """Daily series, forward-filled over weekends/holidays and missing '.'
    observations FRED uses for non-trading days."""
    fred_id = SERIES[name]
    df = pd.read_csv(_fetch(fred_id))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.set_index("date")["value"].sort_index()


def daily_panel(start="1990-01-01"):
    """All six series aligned to a daily calendar, ffilled to the query date."""
    series = {name: load(name) for name in SERIES}
    idx = pd.date_range(start=start, end=pd.Timestamp.now(), freq="D")
    panel = pd.DataFrame(index=idx)
    for name, s in series.items():
        panel[name] = s.reindex(idx).ffill()
    return panel.dropna(how="all")


def regime_signals(panel):
    """Derived signals, each usable as an entry/exposure filter on its own.

    inverted        yield curve (10y-2y) below zero - the textbook recession
                     precursor, historically leading downturns by 6-24 months
    curve_slope     the raw spread, continuous rather than a 0/1 flag
    hiking          Fed funds rate higher than 6 months ago
    real_rate       policy rate minus trailing 12-month CPI inflation
    """
    out = pd.DataFrame(index=panel.index)
    out["inverted"] = panel["yield_curve_10y2y"] < 0
    out["curve_slope"] = panel["yield_curve_10y2y"]
    out["hiking"] = panel["fed_funds"] > panel["fed_funds"].shift(126)
    cpi_yoy = panel["cpi"].pct_change(365) * 100
    out["real_rate"] = panel["fed_funds"] - cpi_yoy
    return out
