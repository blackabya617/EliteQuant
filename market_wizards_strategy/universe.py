"""
Point-in-time S&P 500 membership.

Two different biases get confused with each other, and they are not equally
fixable here:

  Look-ahead membership bias - backtesting 2005 using today's index list, so
  the strategy "knows" which companies would go on to become index members.
  This is the severe one, and this module fixes it completely: membership is
  read as of each date from the historical record.

  Delisting/survivorship bias - the 469 companies (42% of everything that was
  ever in the index) that have since been acquired or gone bankrupt. Free data
  sources do not carry their prices; Yahoo returned usable history for none of
  a 20-name sample, and the few that "worked" were later companies reusing the
  ticker, which would inject wrong prices. This one is NOT fixed. Results are
  therefore optimistic, and `coverage()` reports by how much.

Source: fja05680/sp500 historical components, which tags departed names with
their exit date (AAMRQ-201312).
"""

import os
import re
import subprocess

import pandas as pd

CACHE = os.environ.get("MW_CACHE_DIR", "/tmp/market_wizards_cache")
HIST_URL = ("https://raw.githubusercontent.com/fja05680/sp500/master/"
            "S%26P%20500%20Historical%20Components%20%26%20Changes.csv")
CHANGES_URL = ("https://raw.githubusercontent.com/fja05680/sp500/master/"
               "sp500_changes_since_2019.csv")

DELISTED_TAG = re.compile(r"-\d{6}$")


def _fetch(url, name):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        subprocess.run(["curl", "-sS", "-L", "-o", path, "--retry", "3",
                        "--retry-delay", "5", url], check=True, timeout=300)
    return path


def membership():
    """Return {date -> set(tickers)} for every snapshot in the record.

    Tickers keep their raw form; use `is_delisted` to tell whether a name had
    already left the index by the end of the source data.
    """
    hist = pd.read_csv(_fetch(HIST_URL, "sp500_hist.csv"))
    hist["date"] = pd.to_datetime(hist["date"])
    snapshots = {row.date: set(row.tickers.split(",")) for row in hist.itertuples()}

    # The components file stops in early 2019; roll it forward with the
    # add/remove log so the recent decade is not simply missing.
    last_date = max(snapshots)
    current = set(snapshots[last_date])
    changes = pd.read_csv(_fetch(CHANGES_URL, "sp500_changes.csv"))
    changes["date"] = pd.to_datetime(changes["date"])
    for row in changes.sort_values("date").itertuples():
        if row.date <= last_date:
            continue
        for t in str(row.remove).split(","):
            current.discard(t.strip().strip('"'))
        for t in str(row.add).split(","):
            t = t.strip().strip('"')
            if t and t != "nan":
                current.add(t)
        snapshots[row.date] = set(current)

    return dict(sorted(snapshots.items()))


def is_delisted(ticker):
    return bool(DELISTED_TAG.search(ticker))


def base_ticker(ticker):
    """Strip the delisting suffix: 'AAMRQ-201312' -> 'AAMRQ'."""
    return DELISTED_TAG.sub("", ticker)


def members_on(snapshots, date):
    """Index membership as it stood on `date`, as plain tickers."""
    applicable = [d for d in snapshots if d <= pd.Timestamp(date)]
    if not applicable:
        return set()
    return {base_ticker(t) for t in snapshots[max(applicable)]}


def tradable_universe(snapshots):
    """Every distinct ticker that was ever a member, and whether it survived."""
    seen = {}
    for members in snapshots.values():
        for t in members:
            seen[base_ticker(t)] = seen.get(base_ticker(t), False) or is_delisted(t)
    return seen


def coverage(snapshots, available, dates=None):
    """How much of the point-in-time index we can actually price.

    `available` is the set of tickers for which price data was obtained. The
    gap is the survivorship hole, and it is almost entirely composed of names
    that were removed from the index - i.e. disproportionately losers.
    """
    dates = dates or pd.date_range("2000-01-01", "2026-01-01", freq="YS")
    rows = []
    for d in dates:
        members = members_on(snapshots, d)
        if not members:
            continue
        have = members & set(available)
        rows.append({"date": d.date(), "members": len(members),
                     "priced": len(have), "coverage_pct": len(have) / len(members) * 100})
    return pd.DataFrame(rows)
