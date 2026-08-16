"""
Research harness for the questions the backtests have not yet answered.

Three things get tested here, in descending order of how much they could
change the conclusion:

1. Volatility targeting. Scaling exposure inversely to recent realised
   volatility is one of the better-replicated results in the literature
   (Moreira & Muir, "Volatility-Managed Portfolios"). It matters here because
   the only reliable edge found so far is a drawdown edge, and a drawdown edge
   is worth nothing on its own - it only becomes return if raising Sharpe lets
   you take more risk elsewhere.

2. Statistical significance of the drawdown edge itself. A single max-drawdown
   number from one 18-year path is a sample of one. Block-bootstrapping the
   monthly returns says whether "half SPY's drawdown" is a property of the
   strategy or an accident of this particular history.

3. Walk-forward validation. The earlier check split the sample once. Rolling
   the fit forward repeatedly is a much harder test and the one that decides
   whether the parameters were chosen or discovered.
"""

import numpy as np
import pandas as pd

TRADING_MONTHS = 12


def perf(returns, ppy=TRADING_MONTHS):
    """Annualised stats from a series of periodic returns."""
    r = pd.Series(returns).dropna()
    if len(r) < 2:
        return {}
    equity = (1 + r).cumprod()
    years = len(r) / ppy
    cagr = equity.iloc[-1] ** (1 / years) - 1
    dd = (equity / equity.cummax() - 1).min()
    vol = r.std() * np.sqrt(ppy)
    return {
        "cagr_pct": cagr * 100,
        "max_dd_pct": dd * 100,
        "vol_pct": vol * 100,
        "sharpe": (r.mean() * ppy) / vol if vol > 0 else 0.0,
        "calmar": cagr / abs(dd) if dd < 0 else 0.0,
    }


# ---------------------------------------------------------------------------
# 1. volatility targeting
# ---------------------------------------------------------------------------

def vol_target(returns, target_vol=0.12, lookback=6, max_leverage=1.0,
               ppy=TRADING_MONTHS):
    """Scale each period's exposure by target_vol / trailing realised vol.

    The scale for month t uses only returns through t-1, so there is no
    lookahead. `max_leverage` caps borrowing; at 1.0 the strategy can only
    de-risk, never gear up.
    """
    r = pd.Series(returns).dropna()
    realised = r.rolling(lookback).std() * np.sqrt(ppy)
    scale = (target_vol / realised.shift(1)).clip(upper=max_leverage).fillna(1.0)
    # Borrowed money is not free; charge it at a plausible short rate.
    financing = np.maximum(scale - 1.0, 0.0) * 0.04 / ppy
    return r * scale - financing, scale


# ---------------------------------------------------------------------------
# 2. block bootstrap
# ---------------------------------------------------------------------------

def block_bootstrap(returns, n_boot=2000, block=6, seed=0, ppy=TRADING_MONTHS):
    """Resample in blocks to preserve autocorrelation, and report the spread.

    Drawdown in particular depends on the *order* of returns, so shuffling
    single months would understate it badly. Blocks of six keep the local
    sequencing intact.
    """
    rng = np.random.default_rng(seed)
    r = pd.Series(returns).dropna().to_numpy()
    n = len(r)
    if n < block * 2:
        return pd.DataFrame()

    n_blocks = int(np.ceil(n / block))
    rows = []
    for _ in range(n_boot):
        starts = rng.integers(0, n - block, size=n_blocks)
        path = np.concatenate([r[s:s + block] for s in starts])[:n]
        rows.append(perf(path, ppy))
    return pd.DataFrame(rows)


def compare_bootstrap(a, b, n_boot=2000, block=6, seed=0, ppy=TRADING_MONTHS):
    """Paired bootstrap: resample both series on the SAME blocks.

    Pairing matters. Drawing independent samples would compare the strategy in
    one imagined history against the benchmark in a different one, which
    inflates the apparent difference.
    """
    rng = np.random.default_rng(seed)
    a = pd.Series(a).dropna()
    b = pd.Series(b).dropna()
    idx = a.index.intersection(b.index)
    a, b = a[idx].to_numpy(), b[idx].to_numpy()
    n = len(a)
    if n < block * 2:
        return pd.DataFrame()

    n_blocks = int(np.ceil(n / block))
    rows = []
    for _ in range(n_boot):
        starts = rng.integers(0, n - block, size=n_blocks)
        take = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        pa, pb = perf(a[take], ppy), perf(b[take], ppy)
        rows.append({
            "d_cagr": pa["cagr_pct"] - pb["cagr_pct"],
            "d_maxdd": pa["max_dd_pct"] - pb["max_dd_pct"],
            "d_sharpe": pa["sharpe"] - pb["sharpe"],
            "d_calmar": pa["calmar"] - pb["calmar"],
        })
    return pd.DataFrame(rows)


def summarise(df, label=""):
    """Median and 5-95% interval for every column, plus P(>0)."""
    out = []
    for col in df.columns:
        v = df[col].replace([np.inf, -np.inf], np.nan).dropna()
        out.append({
            "metric": f"{label}{col}",
            "p05": v.quantile(0.05),
            "median": v.median(),
            "p95": v.quantile(0.95),
            "P(>0)": (v > 0).mean(),
        })
    return pd.DataFrame(out).set_index("metric")


# ---------------------------------------------------------------------------
# 3. walk-forward
# ---------------------------------------------------------------------------

def walk_forward(monthly, param_grid, backtest_fn, train_years=5, test_years=2,
                 ppy=TRADING_MONTHS):
    """Repeatedly fit on `train_years`, trade the winner for `test_years`.

    Returns the stitched out-of-sample return series plus the parameter chosen
    in each window. If the chosen parameters jump around, the strategy is being
    fitted to noise even when the stitched curve looks acceptable.
    """
    train_m, test_m = int(train_years * ppy), int(test_years * ppy)
    oos, choices = [], []
    start = 0

    while start + train_m + test_m <= len(monthly):
        train_slice = (start, start + train_m)
        test_slice = (start + train_m, start + train_m + test_m)

        best, best_sharpe = None, -np.inf
        for params in param_grid:
            r = backtest_fn(monthly, params, train_slice)
            if r is None or len(r) < 12:
                continue
            s = perf(r, ppy).get("sharpe", -np.inf)
            if s > best_sharpe:
                best, best_sharpe = params, s

        if best is not None:
            r_oos = backtest_fn(monthly, best, test_slice)
            if r_oos is not None and len(r_oos):
                oos.append(r_oos)
                choices.append({"window_start": monthly.index[test_slice[0]].date(),
                                "params": best, "train_sharpe": best_sharpe})
        start += test_m

    stitched = pd.concat(oos) if oos else pd.Series(dtype=float)
    return stitched, pd.DataFrame(choices)
