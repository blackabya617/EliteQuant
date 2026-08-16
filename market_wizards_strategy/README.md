# Market Wizards Strategy

An honest attempt to build a Market Wizards-style swing system that beats the
S&P 500, and a record of what the data actually said when we tested it.

**Headline: nothing here reliably out-earns buying and holding SPY.** One
variant matches SPY's risk-adjusted return with roughly half the drawdown.
That is a real result, and it is a smaller result than the one this project set
out to find.

---

## What the tests said

All numbers below come from real daily data (Yahoo Finance chart endpoint,
split- and dividend-adjusted), not simulation. Costs of 1bp commission + 2bp
slippage per side are charged on every fill. Signals are computed at the close
and filled at the **next** open, so there is no lookahead.

### The trend + breakout system, SPY, 1993-2026 (8,443 bars)

| variant | CAGR% | MaxDD% | Sharpe | Trades | Win% | PF |
|---|---|---|---|---|---|---|
| original rules, breakout bug fixed | 0.32 | -37.0 | 0.09 | 498 | 38.6 | 1.05 |
| + ATR stop (3N), no time stop | 1.89 | -14.0 | 0.44 | 187 | 47.6 | 1.55 |
| + wide trail (5N), let winners run | 3.24 | -14.6 | 0.67 | 99 | 45.5 | 2.53 |
| breakout entries only | 2.69 | -13.7 | 0.62 | 66 | 54.6 | 2.79 |
| pullback entries only | 2.00 | -14.3 | 0.47 | 87 | 43.7 | 2.12 |
| **SPY buy & hold** | **10.91** | **-55.2** | **0.65** | 1 | - | - |

The fixes helped a lot in relative terms — Sharpe went from 0.09 to 0.67, profit
factor from 1.05 to 2.53. It still loses badly to buy & hold on return, and its
Sharpe (0.67) is a rounding error away from just owning SPY (0.65).

The reason is structural: the system is in the market ~61% of the time, in the
same asset the benchmark holds 100% of the time. Raising risk-per-trade only
helps until position size hits 100% of equity (CAGR caps at 5.88%). Leverage
makes it worse — at 2x, financing plus volatility drag cut CAGR to 2.16% and
Sharpe to 0.26.

### Diversified ETF trend following, 20 markets, 2007-2026

| config | CAGR% | MaxDD% | Sharpe | Trades |
|---|---|---|---|---|
| 5 positions / 2% risk | 4.45 | -22.6 | 0.49 | 502 |
| 20 positions / 2% risk | 4.57 | -23.5 | 0.53 | 719 |
| **SPY buy & hold** | **11.11** | **-55.2** | **0.63** | 1 |

Also loses. Long-only trend following on a basket where most members went
sideways (commodities, bonds, precious metals over this window) cannot keep up
with the one member that compounded.

### Dual-momentum rotation, 20 ETFs, 2008-2026 — the one that held up

Rank the universe by 3-month return, hold the top 5 that are also above their
10-month average, equal weight, rebalance monthly, hold cash for any slot with
no eligible name.

| | rotation | SPY buy & hold |
|---|---|---|
| CAGR % | 11.42 | 12.12 |
| max drawdown % | **-24.05** | -46.32 |
| volatility % | 15.05 | 15.66 |
| Sharpe | 0.80 | 0.81 |
| Calmar | **0.47** | 0.26 |

Same Sharpe. Slightly *lower* return. Roughly half the peak-to-trough loss.

**Out-of-sample check.** Fitting on 2008-2017 and testing on 2018-2026:

| config | IS Sharpe | OOS CAGR% | OOS MaxDD% | OOS Sharpe | OOS Calmar |
|---|---|---|---|---|---|
| 3mo / top5 | 0.72 | 15.02 | -16.4 | 0.91 | 0.92 |
| 6mo / top5 | 0.68 | 12.52 | -16.3 | 0.79 | 0.77 |
| 12mo / top5 | 0.66 | 13.29 | -15.6 | 0.83 | 0.85 |
| SPY B&H | 0.67 | 14.83 | -23.9 | 0.93 | 0.62 |

The drawdown advantage survives out of sample and holds across every lookback
from 3 to 12 months and both basket sizes, which is what you want to see — the
result does not depend on one lucky parameter cell. The *return* advantage does
not survive: out of sample SPY's Sharpe (0.93) edges the best config (0.91).

---

## Bugs found in the first version

Worth listing, because they explain why the early backtests looked the way they
did:

1. **The breakout signal could never fire.** `High_20` was a rolling max that
   included the current bar, and the test was `Close > High_20`. Since
   `Close <= High <= max(High, 20)`, this was false on all 8,443 days. Every
   trade in every early backtest came from the pullback branch; the Richard
   Dennis half of the strategy was dead code.
2. **A 5% profit cap with a 2% stop.** This caps winners while letting the
   stop define losses — the exact inverse of "let your winners run," which is
   the one thing every trader in the book agrees on.
3. **Fixed percentage stops.** A flat 2% stop on SPY sits inside a single day's
   noise for much of the sample, which is why 71% of trades exited at exactly
   -2.00%. Replaced with ATR-scaled stops.
4. **Pullback fills at the 50-day average** — a price that frequently never
   traded that day. Fills now happen at the next open.
5. **Broken trend-slope check.** `MA_200 > Close - Close*0.05` does not measure
   the slope of anything. Replaced with a comparison against the MA's own value
   20 days earlier.
6. **Position sizing could exceed cash.** Risking 3% with a 2% stop implies
   1.5x notional, and nothing checked it against the balance.
7. **No costs, no equity curve, no drawdown.** `max_drawdown` appeared in the
   metrics dict and was never computed. Returns were summed, not compounded.

---

## Layout

```
data_manager.py   real daily OHLCV, split/dividend adjusted, cached to disk
engine.py         event-driven backtester: next-open fills, ATR stops, costs
rotation.py       the dual-momentum rotation strategy + its backtest
experiments.py    reproduces the trend-system comparison table above
paper_broker.py   Alpaca paper-trading adapter (paper endpoint only)
alerts.py         Telegram / email / JSON log delivery
main.py           signal | paper | backtest
```

## Use

```bash
pip install -r requirements.txt

python main.py backtest    # reproduce the rotation table
python main.py signal      # what to hold right now
python main.py paper       # reconcile an Alpaca paper account (dry run)
```

### Paper trading

1. Sign up free at <https://app.alpaca.markets/paper/dashboard/overview>.
2. Copy `.env.example` to `.env` and fill in `ALPACA_API_KEY` / `ALPACA_API_SECRET`.
3. `python main.py paper` prints the orders it would send and stops.
4. Set `EXECUTE_PAPER_TRADES=true` only when the dry run looks right.

The adapter refuses to construct against the live endpoint. Going live has to
be a deliberate code change, not an env var typo.

The rotation rebalances monthly, so run `paper` on the first trading day of the
month. Running it daily is harmless — it no-ops when the account already
matches within 2%.

---

## What this is and is not

It is a defensible risk-managed portfolio with a documented drawdown advantage
and an honest paper trail.

It is not an edge over the index. If the goal is to beat SPY's return, nothing
tested here does that, and the tests that looked like they did were measurement
errors — an annualisation bug briefly showed Sharpe 3.73 for the rotation; the
correct figure is 0.80.

Caveats that remain: 18 years is one macro regime (post-GFC, mostly falling
rates, US equities dominant). The ETF universe is chosen with hindsight about
which funds exist and stayed liquid. Monthly rebalancing in a taxable account
generates short-term gains. And a strategy validated on ~220 monthly
observations has wide error bars — the drawdown edge is the robust part, the
return numbers are not precise to the decimal.
