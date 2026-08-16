"""Run the strategy variants side by side against buy & hold."""

from dataclasses import replace

import pandas as pd

import data_manager as dm
from engine import Params, run, stats

pd.set_option("display.width", 200)


def show(rows, title):
    df = pd.DataFrame(rows).set_index("variant")
    print(f"\n{title}")
    print("=" * len(title))
    print(df.round(2).to_string())
    return df


def evaluate(name, p, data, benchmark, symbols=None):
    trades, equity = run(data, p, symbols=symbols)
    s = stats(trades, equity, benchmark)
    return {
        "variant": name,
        "CAGR%": s["cagr_pct"],
        "MaxDD%": s["max_dd_pct"],
        "Sharpe": s["sharpe"],
        "Calmar": s["calmar"],
        "Trades": s["trades"],
        "Win%": s.get("win_rate_pct", 0),
        "PF": s.get("profit_factor", 0),
        "AvgWin%": s.get("avg_win_pct", 0),
        "AvgLoss%": s.get("avg_loss_pct", 0),
        "AvgDays": s.get("avg_days", 0),
        "Expo%": s["exposure_pct"],
    }, trades, equity


if __name__ == "__main__":
    spy = dm.load("SPY")
    bench = spy["Close"]

    print(f"SPY {spy.index[0].date()} -> {spy.index[-1].date()}  ({len(spy):,} bars)")
    years = (spy.index[-1] - spy.index[0]).days / 365.25
    bh_cagr = (bench.iloc[-1] / bench.iloc[0]) ** (1 / years) - 1
    bh_dd = (bench / bench.cummax() - 1).min()
    print(f"Buy & hold: CAGR {bh_cagr*100:.2f}%   MaxDD {bh_dd*100:.1f}%")

    base = Params()

    # The original rules, ported onto the corrected engine so the only thing
    # that differs is the rule set, not the accounting.
    original = replace(
        base,
        breakout_lookback=20, pullback_ma=50, trend_slope_lookback=1,
        stop_atr=0.0, trail_atr=0.0, time_stop_days=10,
        risk_pct=0.03, volume_mult=1.2,
    )

    rows = []
    # Original used percentage stops; emulate with a tight ATR stop and a hard
    # profit cap is not expressible here, so report it as "fixed 2% stop, 10d".
    from engine import Params as P

    variants = {
        "A. original rules (2% stop, 5% cap, 10d)": None,   # handled separately below
        "B. + fixed breakout bug": replace(base, stop_atr=1.0, trail_atr=1.0, time_stop_days=10, risk_pct=0.03),
        "C. + ATR stop (3N), no time stop": replace(base, trail_atr=3.0, time_stop_days=0),
        "D. + wide trail (5N) = let winners run": replace(base, trail_atr=5.0, time_stop_days=0),
        "E. D + rising-MA regime filter": replace(base, trail_atr=5.0, time_stop_days=0, trend_slope_lookback=20),
        "F. E, breakout entries only": replace(base, trail_atr=5.0, time_stop_days=0, trend_slope_lookback=20, use_pullback=False),
        "G. E, pullback entries only": replace(base, trail_atr=5.0, time_stop_days=0, trend_slope_lookback=20, use_breakout=False),
    }

    results = []
    for name, p in variants.items():
        if p is None:
            continue
        row, trades, equity = evaluate(name, p, spy, bench)
        results.append(row)

    show(results, "SPY 1993-2026: strategy variants vs buy & hold")
    print(f"\nbuy & hold reference:  CAGR {bh_cagr*100:.2f}%  MaxDD {bh_dd*100:.1f}%")
