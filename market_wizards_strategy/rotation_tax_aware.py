"""
A tax-aware variant of the rotation rebalance, and a real per-lot after-tax
comparison against the vanilla version.

tax.py's earlier estimate treated every gain in a year as realized at the same
rate, which overstates the drag: a monthly rebalance realizes a mix of
short-term losses (which offset ordinary income at the full marginal rate) and
occasional long-term gains (positions that happened to survive 12+ months in
the ranking), not one undifferentiated short-term pile.

This module tracks each holding's actual entry date, so every exit is
classified as short- or long-term at the moment it happens, and adds one
real lever: when a currently-held position has an unrealized GAIN and is
close to but under a year old, hold it a little past its normal cutoff -
`buffer` extra ranking slots - to let it cross into long-term treatment before
being sold. Losing positions get no such grace: the philosophy is "cut losses
short, let winners run," and that is exactly the asymmetry a tax-aware
overlay wants too - realize losses fast at the ordinary rate, defer gains past
the long-term threshold when the ranking allows it.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from rotation import RotationParams, _exposure, month_end_prices, select

LONG_TERM_DAYS = 366


@dataclass
class TaxAwareParams(RotationParams):
    buffer: int = 0          # extra ranking slots a young winner may hold past cutoff
    grace_days: int = 60     # only extend within this many days of the 1-year mark


def backtest_with_lots(monthly, p: TaxAwareParams, start_idx=None):
    """Like rotation.backtest, but returns a per-position lot log with real
    entry/exit dates, entry/exit DOLLAR amounts, and short/long classification.

    Dollar amounts matter here in a way they do not for the plain backtest:
    a lot's tax bill depends on how many actual dollars were committed to it,
    not just its percentage return, and that dollar amount is a growing
    fraction of a compounding account, not a fixed slice of starting capital.
    """
    warmup = max(p.lookback_months, p.abs_ma_months) + 1
    start_idx = start_idx or warmup

    equity = [p.initial_capital]
    dates = [monthly.index[start_idx - 1]]
    lots = {}          # symbol -> {"entry_date", "entry_price", "dollars"}
    closed_lots = []
    log = []
    raw_history = []

    for i in range(start_idx, len(monthly)):
        today = monthly.index[i]
        prev_day = monthly.index[i - 1]
        ranked_full = _ranked(monthly, p, as_of=prev_day)
        strict = ranked_full[: p.top_n]

        held = set(lots)
        target = set(strict)

        if p.buffer:
            extended = set(ranked_full[: p.top_n + p.buffer])
            for sym in held - target:
                if sym not in extended:
                    continue
                lot = lots[sym]
                age_days = (today - lot["entry_date"]).days
                unrealised_gain = monthly[sym].loc[prev_day] > lot["entry_price"]
                near_long_term = (LONG_TERM_DAYS - p.grace_days) <= age_days < LONG_TERM_DAYS
                if unrealised_gain and near_long_term:
                    target.add(sym)   # buy a little time to cross into long-term

        equity_now = equity[-1]

        # ---- exits: anything held but no longer in target ------------------
        for sym in held - target:
            lot = lots.pop(sym)
            exit_price = monthly[sym].loc[today]
            gain_pct = exit_price / lot["entry_price"] - 1
            days = (today - lot["entry_date"]).days
            closed_lots.append({
                "symbol": sym, "entry_date": lot["entry_date"], "exit_date": today,
                "entry_price": lot["entry_price"], "exit_price": exit_price,
                "gain_pct": gain_pct * 100, "days_held": days,
                "term": "long" if days >= LONG_TERM_DAYS else "short",
                "entry_dollars": lot["dollars"],
                "dollar_gain": lot["dollars"] * gain_pct,
            })

        # ---- entries: anything in target but not held ----------------------
        # Equal-weighted over whatever is actually held this month, at the
        # current account value - matches how the return series is computed.
        per_slot = equity_now / max(len(target), 1)
        for sym in target - held:
            lots[sym] = {"entry_date": today, "entry_price": monthly[sym].loc[today],
                        "dollars": per_slot}

        # ---- return for the month, equal-weighted over target --------------
        if target:
            step = float(np.mean([monthly[s].loc[today] / monthly[s].loc[prev_day] - 1
                                  for s in target]))
        else:
            step = 0.0
        turnover = len(target ^ held) / max(len(target | held), 1)
        step -= (p.cost_bps / 10_000) * turnover

        exposure = _exposure(raw_history, p)
        raw_history.append(step)
        step *= exposure

        equity.append(equity[-1] * (1 + step))
        dates.append(today)
        log.append({"date": today, "holdings": ",".join(sorted(target)) or "CASH",
                    "return_pct": step * 100, "exposure": exposure})

    return pd.Series(equity, index=dates), pd.DataFrame(log), pd.DataFrame(closed_lots)


def _ranked(monthly, p, as_of):
    hist = monthly.loc[:as_of]
    if len(hist) < max(p.lookback_months, p.abs_ma_months) + 1:
        return []
    momentum = hist.iloc[-1] / hist.iloc[-1 - p.lookback_months] - 1
    trend_ma = hist.rolling(p.abs_ma_months).mean().iloc[-1]
    last = hist.iloc[-1]
    ranked = momentum.dropna().sort_values(ascending=False)
    return [s for s in ranked.index if last[s] > trend_ma[s]]


def after_tax_from_lots(equity, lots, short_rate, long_rate):
    """Compound an after-tax equity curve using each lot's REAL dollar gain and
    REAL short/long classification (not an assumed all-short-term pile).

    Short and long gains net separately against same-term losses within a
    year per normal US rules; a net loss in one bucket offsets a net gain in
    the other; any remaining net loss carries forward. The tax owed each year
    is charged against the AFTER-TAX equity curve (so a tax bill this year
    genuinely shrinks next year's compounding base, the mechanism that drives
    the whole tax-drag result), while gains/losses are still measured in the
    (larger) dollar terms the pre-tax curve actually traded in - the natural
    assumption for a systematic rebalance that does not resize for taxes owed.
    """
    lots = lots.copy()
    lots["exit_year"] = pd.to_datetime(lots["exit_date"]).dt.year
    year_end = equity.groupby(equity.index.year).last()
    pretax_annual_return = year_end.pct_change()

    carry = 0.0
    after_tax_equity = equity.iloc[0]
    rows = []
    for year, grp in lots.groupby("exit_year"):
        st = grp[grp.term == "short"].dollar_gain.sum()
        lt = grp[grp.term == "long"].dollar_gain.sum()
        net = st + lt
        taxable = max(net - carry, 0.0)
        carry = max(carry - net, 0.0) if net < 0 else max(carry - max(net, 0), 0.0)

        if taxable > 0 and (max(st, 0) + max(lt, 0)) > 0:
            blend = (max(st, 0) * short_rate + max(lt, 0) * long_rate) / (max(st, 0) + max(lt, 0))
        else:
            blend = short_rate
        tax = taxable * blend

        yr_return = pretax_annual_return.get(year, 0.0)
        if pd.isna(yr_return):
            yr_return = 0.0
        after_tax_equity = after_tax_equity * (1 + yr_return) - tax
        rows.append({"year": year, "short_gain": st, "long_gain": lt, "net": net,
                     "tax": tax, "after_tax_equity": after_tax_equity})

    return pd.DataFrame(rows)
