"""
After-tax comparison in a taxable account.

This matters more than it looks. A monthly rotation realises nearly all of its
gains inside twelve months, so they are taxed as ordinary income every year.
Buy-and-hold defers capital gains until sale, potentially for decades, and
compounds on money it has not yet paid to the government. That deferral is
itself a return - and it is the single biggest advantage index investing has
over any active strategy in a taxable account.

Modelled here:
  strategy   every realised gain taxed the year it occurs, at short-term rates
             when the holding period is under a year and long-term otherwise;
             losses offset gains within the year and carry forward
  benchmark  dividends taxed annually at qualified rates, capital gains
             deferred entirely until a final liquidation
"""

import numpy as np
import pandas as pd

# Federal brackets plus a typical state burden. Adjust to taste.
BRACKETS = {
    "22% fed (single ~$50-100k)": {"short": 0.22 + 0.05, "long": 0.15 + 0.05},
    "24% fed (single ~$100-190k)": {"short": 0.24 + 0.05, "long": 0.15 + 0.05},
    "32% fed (single ~$190-240k)": {"short": 0.32 + 0.05, "long": 0.15 + 0.05},
    "35%+ fed + NIIT": {"short": 0.35 + 0.038 + 0.05, "long": 0.20 + 0.038 + 0.05},
}


def after_tax_active(monthly_returns, short_rate, long_rate, avg_holding_months=4,
                     dividend_yield=0.015, qualified_rate=0.15):
    """Annual mark-to-market approximation for a high-turnover strategy.

    A rotation that turns its book over every few months realises essentially
    everything each year, so taxing the year's gain is a close approximation to
    tracking every lot. Holding periods under twelve months are taxed short.
    """
    r = pd.Series(monthly_returns).dropna()
    rate = short_rate if avg_holding_months < 12 else long_rate

    equity = 1.0
    carry_loss = 0.0
    net = []
    for year, group in r.groupby(r.index.year):
        gross = (1 + group).prod() - 1
        start = equity
        gain = start * gross

        if gain > 0:
            taxable = max(gain - carry_loss, 0.0)
            carry_loss = max(carry_loss - gain, 0.0)
            tax = taxable * rate
        else:
            carry_loss += -gain
            tax = 0.0

        # Dividends inside the sleeve are taxed too, mostly at qualified rates.
        tax += start * dividend_yield * qualified_rate

        equity = start + gain - tax
        net.append({"year": year, "gross_pct": gross * 100,
                    "tax": tax, "equity": equity})
    return pd.DataFrame(net)


def after_tax_buy_hold(monthly_returns, long_rate, dividend_yield=0.013,
                       qualified_rate=0.15, liquidate_at_end=True):
    """Buy and hold: dividends taxed yearly, gains deferred to a final sale."""
    r = pd.Series(monthly_returns).dropna()
    equity, basis = 1.0, 1.0
    rows = []
    for year, group in r.groupby(r.index.year):
        gross = (1 + group).prod() - 1
        start = equity
        equity = start * (1 + gross)
        div_tax = start * dividend_yield * qualified_rate
        equity -= div_tax
        basis += 0.0     # dividends are assumed spent on the tax, not reinvested
        rows.append({"year": year, "gross_pct": gross * 100,
                     "tax": div_tax, "equity": equity})

    if liquidate_at_end and equity > basis:
        rows[-1]["tax"] += (equity - basis) * long_rate
        equity -= (equity - basis) * long_rate
        rows[-1]["equity"] = equity
    return pd.DataFrame(rows)


def summarise(df, years):
    final = df["equity"].iloc[-1]
    return {
        "final_multiple": final,
        "cagr_pct": (final ** (1 / years) - 1) * 100,
        "total_tax": df["tax"].sum(),
    }
