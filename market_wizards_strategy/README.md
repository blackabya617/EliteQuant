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

## What the Turtles actually did, and what happened when we copied it

The earlier tests all shared a structural flaw: they were long-only, in equity
ETFs, in a cash account. That is not what any of the traders in the book were
doing. `turtle.py` implements the real 1983 curriculum:

| Turtles | earlier build here |
|---|---|
| long **and** short | long only |
| ~24 futures: FX, rates, metals, energy, grains, indices | 20 equity-heavy ETFs |
| futures margin, gross notional far above equity | cash-capped at 100% |
| pyramid to 4 Units at 1/2 N intervals | no pyramiding |
| Donchian exit (10-day S1 / 20-day S2) | ATR trailing stop |
| skip rule + 55-day failsafe | none |
| unit caps 4/market, 6/correlated group, 12/direction | position count only |

Implemented faithfully and run on 26 ETF futures-proxies (2007-2026, adding FX,
grains and energy to get genuine cross-asset diversification).

### First result was a bug, not a finding

The literal Turtle sizing rule - one Unit is the quantity for which a 1N move
equals 1% of equity - produces this in an ETF account:

| | price | N (ATR) | notional for ONE Unit | x equity |
|---|---|---|---|---|
| SPY | 776.34 | 7.94 | $9,780 | 0.98x |
| IEF | 93.04 | 0.35 | $26,254 | **2.63x** |
| UUP | 28.11 | 0.11 | $25,547 | **2.55x** |

A single Unit of a low-volatility instrument demands 2.6x equity in notional.
That is entirely normal in futures, where margin is ~5% of notional - you can
hold $250k of T-note futures against $10k. It is impossible in an equity
account. Run unmodified, the system posts a -99% drawdown, which is an
artefact of the translation, not a property of the rules.

### Scaled to achievable leverage, 2007-2026

| config | CAGR% | MaxDD% | Sharpe | Long P&L | Short P&L |
|---|---|---|---|---|---|
| 1.0x lev, 0.10% risk/unit | -1.32 | -39.7 | -0.06 | +$1,495 | **-$3,812** |
| 1.5x lev, 0.10% risk/unit | -1.87 | -39.9 | -0.10 | +$3,268 | **-$6,403** |
| 2.0x lev, 0.25% risk/unit | -2.21 | -63.1 | 0.02 | +$4,183 | **-$7,806** |
| SPY buy & hold | 11.00 | -55.2 | 0.63 | | |

Short P&L is negative in every configuration tested. That is the finding.

### Where the money went

| asset group | long | short | total |
|---|---|---|---|
| metals | +2,443 | -592 | **+1,851** |
| energy | -741 | +1,640 | **+900** |
| rates | +873 | -733 | +141 |
| real estate | +133 | -623 | -490 |
| commodity | -462 | -39 | -500 |
| FX | -178 | -1,024 | -1,202 |
| grains | -836 | -610 | -1,446 |
| equity | +261 | -1,833 | **-1,571** |

Shorting equities into a 19-year bull market with V-shaped recoveries was the
single largest loss. The one place shorting paid was energy, where USO and UNG
grind downward on contango.

The payoff ratios are healthy - longs win 22.9% of the time at 3.7:1, shorts
19.4% at 3.1:1. Trend following is supposed to look like that. The problem is
that 19.4% at 3.1:1 is a negative expectancy, and no amount of position sizing
fixes a negative edge.

### It is insurance, not an alpha engine

| period | Turtle CAGR% | SPY CAGR% | long P&L | short P&L |
|---|---|---|---|---|
| 2007-04..2009-12 GFC + crash | **+2.35** | **-7.74** | +30 | **+140** |
| 2010-01..2014-12 post-GFC | -2.01 | +14.99 | +314 | -1,797 |
| 2015-01..2019-12 low-vol grind | -2.73 | +11.59 | -451 | -926 |
| 2020-01..2022-12 COVID + inflation | +0.65 | +7.30 | +867 | -911 |
| 2023-01..2026-08 recent | -2.79 | +23.32 | +1,282 | -2,309 |

The system made money through the financial crisis while the index lost 7.7% a
year, and bled in every choppy bull market since. That is the documented
experience of the trend-following industry as a whole - 2011 and 2018 were
years when most constituents of the SG Trend Index finished red.

### Combining it with a core does not rescue it

Correlation to SPY is -0.09, which is a genuinely good diversifier property.
But a diversifier with negative expected return only trades return away for
drawdown one-for-one:

| blend | CAGR% | MaxDD% | Sharpe | Calmar |
|---|---|---|---|---|
| rotation 90% + turtle 10% | 10.18 | -21.4 | 0.77 | 0.48 |
| rotation only | 11.42 | -24.1 | 0.80 | 0.47 |
| SPY buy & hold | 12.00 | -46.3 | 0.81 | 0.26 |
| turtle only | -1.48 | -39.2 | -0.12 | -0.04 |

The Calmar improvement from adding the Turtle sleeve is 0.47 -> 0.48, which is
noise, and Sharpe falls.

### One thing the backtest cannot capture

The Turtles traded futures, which means they posted ~5-10% margin and **earned
T-bill interest on the entire collateral balance**. In 1983-1988 that was 8-10%
a year, risk-free, on top of trading P&L. None of the tests here include that,
and no ETF account earns it. A meaningful slice of the original returns came
from an interest-rate environment that no longer exists.

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
