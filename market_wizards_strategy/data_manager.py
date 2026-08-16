"""
Data Manager - fetches and caches real daily OHLCV data.

Uses Yahoo Finance's chart endpoint directly (the yfinance package's quote
endpoints are rate-limited in this environment; the chart endpoint is not).
Adjusts OHLC for splits and dividends so backtests reflect total return.
"""

import json
import os
import subprocess
import time
from datetime import datetime

import numpy as np
import pandas as pd

CACHE_DIR = os.environ.get("MW_CACHE_DIR", "/tmp/market_wizards_cache")
CHART_HOSTS = ("query1", "query2")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)


class DataError(RuntimeError):
    """Raised when real market data could not be obtained."""


def _cache_path(symbol):
    return os.path.join(CACHE_DIR, f"{symbol.upper()}_daily.pkl")


def _download_chart(symbol, start_ts, end_ts, retries=4):
    """Download the raw chart JSON to a temp file and return the parsed dict."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    raw_path = os.path.join(CACHE_DIR, f"{symbol.upper()}_raw.json")

    last_err = None
    for host in CHART_HOSTS:
        url = (
            f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}"
            f"?period1={start_ts}&period2={end_ts}&interval=1d&events=div%2Csplit"
        )
        cmd = [
            "curl", "-sS", "-o", raw_path, "-w", "%{http_code}",
            "--retry", str(retries), "--retry-delay", "8", "--retry-all-errors",
            "-H", f"User-Agent: {UA}",
            "-H", "Accept: application/json",
            url,
        ]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if out.stdout.strip() != "200":
                last_err = f"{host} returned HTTP {out.stdout.strip()}"
                continue
            with open(raw_path) as fh:
                payload = json.load(fh)
            if payload.get("chart", {}).get("error"):
                last_err = f"{host}: {payload['chart']['error']}"
                continue
            return payload
        except Exception as exc:  # noqa: BLE001 - report whatever curl/json raised
            last_err = f"{host}: {exc}"
            time.sleep(2)

    raise DataError(f"Could not download {symbol} chart data ({last_err})")


def _chart_to_frame(payload):
    """Convert Yahoo chart JSON into a split/dividend-adjusted OHLCV frame."""
    result = payload["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]

    df = pd.DataFrame(
        {
            "Open": quote["open"],
            "High": quote["high"],
            "Low": quote["low"],
            "Close": quote["close"],
            "Volume": quote["volume"],
        },
        index=pd.to_datetime(result["timestamp"], unit="s").tz_localize(None).normalize(),
    )

    adj = result["indicators"].get("adjclose")
    if adj and adj[0].get("adjclose"):
        df["AdjClose"] = adj[0]["adjclose"]
    else:
        df["AdjClose"] = df["Close"]

    df = df.dropna(subset=["Open", "High", "Low", "Close"])

    # Scale the whole bar by adjclose/close so highs, lows and opens stay
    # consistent with the adjusted close. Without this, a stop measured against
    # an unadjusted Low but an adjusted entry would fire on dividend gaps.
    factor = df["AdjClose"] / df["Close"]
    for col in ("Open", "High", "Low", "Close"):
        df[col] = df[col] * factor

    df = df.drop(columns=["AdjClose"])
    df["Volume"] = df["Volume"].fillna(0).astype("int64")

    # Guard against upstream glitches where the bar's range excludes O/C.
    df["High"] = df[["High", "Open", "Close"]].max(axis=1)
    df["Low"] = df[["Low", "Open", "Close"]].min(axis=1)

    return df[~df.index.duplicated(keep="last")].sort_index()


def load(symbol="SPY", start="1993-01-01", end=None, max_age_hours=12, refresh=False):
    """Return a daily OHLCV frame for `symbol`, cached on disk.

    Raises DataError if real data cannot be fetched and no cache exists. The
    backtester must never silently fall back to simulated prices - a backtest
    on synthetic data measures nothing.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(symbol)

    if not refresh and os.path.exists(path):
        age_hours = (time.time() - os.path.getmtime(path)) / 3600
        if age_hours < max_age_hours:
            return pd.read_pickle(path)

    start_ts = int(pd.Timestamp(start).timestamp())
    end_ts = int(pd.Timestamp(end or datetime.now()).timestamp()) + 86400

    try:
        df = _chart_to_frame(_download_chart(symbol, start_ts, end_ts))
    except DataError:
        if os.path.exists(path):
            return pd.read_pickle(path)
        raise

    df.to_pickle(path)
    return df


def add_atr(df, period=20):
    """Wilder's Average True Range, in price units."""
    prev_close = df["Close"].shift(1)
    true_range = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
