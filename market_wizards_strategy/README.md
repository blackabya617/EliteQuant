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

## Individual stocks: testing the one anomaly the earlier work never touched

Every test above was an index or a basket of indices, and a portfolio that owns
SPY-like exposure cannot out-earn SPY. Picking individual names can, because
the spread between the best and worst index members is enormous. Cross-sectional
momentum is also the most replicated anomaly in the academic literature and
what the *Stock Market Wizards* traders (Minervini, Okumus, Lescarbeau) were
doing under the name "relative strength".

`stocks.py` combines several traders' ideas rather than copying one: relative
strength ranking, a 12-1 or 6-1 momentum window, Minervini's stage-2 trend
template, Jones's index-level regime filter, and Dennis/Eckhardt volatility-
scaled sizing.

### Survivorship: what is and is not fixed

Two different biases get conflated. The severe one is **look-ahead membership**
— backtesting 2005 with today's index list, so the strategy "knows" which
companies would later become members. `universe.py` fixes this completely by
reading membership point-in-time from the historical record.

The other is **delisting bias**. Of 1,205 companies that were ever in the index
since 1996, **461 (38%) have since left it**. Free data does not carry their
prices: of a 20-name sample of delisted tickers, Yahoo returned usable history
for none — and the three that appeared to work were later companies reusing the
ticker, which would inject wrong prices. Coverage of the point-in-time index:

| year | 2000 | 2005 | 2010 | 2015 | 2020 | 2026 |
|---|---|---|---|---|---|---|
| coverage | 59% | 64% | 70% | 76% | 87% | 98% |

Everything below is therefore **optimistic**, most severely in the early years.
Conclusions lean on 2015+ where coverage is 76-98%.

### Results

| 2000-2026 | CAGR% | MaxDD% | Vol% | Sharpe | Calmar |
|---|---|---|---|---|---|
| momentum, no filters | 9.68 | -62.2 | 21.4 | 0.54 | 0.16 |
| + Minervini trend template | 8.62 | -44.2 | 18.6 | 0.54 | 0.19 |
| + Jones regime filter | 8.83 | -26.2 | 15.2 | 0.64 | 0.34 |
| SPY buy & hold | 8.56 | -50.8 | 15.1 | 0.62 | 0.17 |

Raw momentum beats SPY on return — 9.68% against 8.56%. That is the first thing
tested here that does. But it runs 21.4% volatility against SPY's 15.1%, and
its Sharpe is *lower*. Which raises the only question that matters.

### Is it alpha, or is it leverage?

Regressing the strategy's monthly returns on SPY's separates skill from simply
holding more risk. A t-statistic below 2 means the alpha cannot be told apart
from luck.

| 2000-2026 | CAGR% | beta | alpha% | t-stat |
|---|---|---|---|---|
| top5, 6-1 momentum | 14.12 | 0.98 | +5.09 | **0.93** |
| top10, 6-1 momentum | 11.93 | 0.93 | +4.10 | **0.97** |
| top20, 6-1 momentum | 10.60 | 0.86 | +3.08 | **0.90** |
| top50, 12-1 momentum | 8.77 | 0.80 | +0.80 | **0.33** |

| 2015-2026 (better coverage) | CAGR% | beta | alpha% | t-stat |
|---|---|---|---|---|
| top5, 6-1 momentum | 22.68 | **1.23** | +0.58 | 0.06 |
| top10, 6-1 momentum | 17.88 | 1.14 | **-1.91** | -0.26 |
| top20, 12-1 momentum | 12.31 | 0.98 | **-4.08** | -0.64 |
| top50, 12-1 momentum | 10.38 | 0.88 | **-4.32** | -1.14 |
| SPY buy & hold | 14.32 | 1.00 | 0.00 | - |

**Not a single configuration produces statistically significant alpha.** Every
t-stat is below 1. In the period with trustworthy data coverage the alpha is
mostly *negative*, and SPY's Sharpe (0.97) beats every variant.

The concentrated portfolios look impressive — top5 returns 22.68% a year since
2015 — but they carry beta 1.23. That return is available by holding SPY on
1.23x margin, without the single-name risk, and it is measured on data biased
in the strategy's favour.

This is consistent with the published record rather than contrary to it:
documented anomalies decay sharply after publication, and momentum's edge was
established largely on pre-2000 data.

---

## Statistical validation, and the tax problem

### Is the drawdown edge real, or one lucky path?

A single max-drawdown number from one 18-year history is a sample of one.
Block-bootstrapping the monthly returns (4,000 paths, six-month blocks to
preserve sequencing, resampling strategy and benchmark on the *same* blocks so
both live in the same imagined history):

| | P(rotation better) |
|---|---|
| shallower drawdown | **96.7%** |
| higher Calmar | 88.5% |
| higher Sharpe | 81.1% |
| higher CAGR | **55.0%** |

The drawdown edge clears significance. The return edge is a coin flip, and
always has been. Anyone claiming this strategy "beats the market" is reading
the 55% column as though it were the 96.7% one.

### Walk-forward

Refitting every two years on the prior five and trading the winner out of
sample — the hardest test in the repo, because nothing is chosen with
hindsight:

| | CAGR% | MaxDD% | Sharpe | Calmar |
|---|---|---|---|---|
| walk-forward rotation | 11.60 | **-15.45** | 0.94 | **0.75** |
| SPY, same window | 13.52 | -23.93 | 0.98 | 0.57 |

More important than the curve: the optimiser chose a **9-month lookback and
eight slots in five of seven windows.** Parameters that keep being rediscovered
on unseen data are worth far more than parameters that merely win one sweep.
The defaults changed from (3 months, five slots) to (9, 8) on that basis.

### Volatility capping

Scaling exposure down when realised volatility runs hot. Applied *on top of*
rotation it does not raise return, but it buys drawdown cheaply:

| config | CAGR% | MaxDD% | Sharpe | Calmar |
|---|---|---|---|---|
| 9mo/top8, no cap | 12.35 | -20.89 | 0.97 | 0.59 |
| **9mo/top8, 10% vol cap** | **10.66** | **-17.84** | **1.03** | **0.60** |
| 9mo/top8, 6% vol cap | 7.42 | -15.61 | 0.96 | 0.48 |
| SPY buy & hold | 12.00 | -46.32 | 0.81 | 0.26 |

Sharpe 1.03 is the highest figure anywhere in this project. Note it is bought
with 1.7pp of CAGR, not conjured.

### Leverage converts the Sharpe edge into return — before tax

| | CAGR% | MaxDD% | Sharpe |
|---|---|---|---|
| rotation, vol-matched to SPY (1.21x) | **13.67** | -25.02 | 0.90 |
| SPY buy & hold | 12.00 | -46.32 | 0.81 |

Median bootstrap edge +1.75pp, P(higher CAGR) 71%. Financing charged at 5%.

### And then tax eats it

The rotation turns over ~33% a month, average holding **3.1 months**, so
essentially every gain is short-term and taxed as ordinary income each year.
Buy-and-hold defers capital gains until sale and compounds on money it has not
yet handed over. That deferral is itself a return, and it is the largest
structural advantage index investing holds over any active strategy.

| bracket | rotation | rotation 1.21x | SPY B&H | edge |
|---|---|---|---|---|
| 22% + state | 8.86 | 9.87 | 10.65 | **-0.78** |
| 24% + state | 8.62 | 9.60 | 10.65 | **-1.05** |
| 32% + state | 7.64 | 8.52 | 10.65 | **-2.13** |
| 35% + NIIT + state | 6.80 | 7.60 | 10.06 | **-2.47** |

Pre-tax the levered rotation beats SPY by 1.69pp. After tax it loses by 0.78 to
2.47pp depending on bracket. **In a taxable account the strategy does not beat
buy-and-hold, and the higher the bracket the worse it gets.**

The same strategy in a tax-sheltered account keeps the entire pre-tax result,
because none of the annual realisations are taxed. That single fact is worth
more than every parameter decision in this repository combined.

---

## Session 3: factor ETFs, and testing "cut losses short, let winners run" literally

The rotation strategy rebalances on a calendar - every month it holds whatever
ranks in the top N, full stop. It does not know whether a position is up 40%
or down 2%; it drops a winner from the ranking exactly as readily as a loser.
That is not "cut losses short, let winners run," it is "trade the calendar."
`swing.py` builds the literal version: cross-sectional ranking for entries,
combined with engine.py's per-position ATR stop and chandelier trail (already
validated as honest in that module) for exits, so positions leave the book by
hitting their own stop or continue running as long as their trend holds -
independent of any calendar.

### Factor ETFs added to the rotation universe: no improvement

MTUM, QUAL, USMV, VLUE, SIZE, SPLV added to the existing 20-ETF universe,
tested over the window where all of them have data (2013-2026):

| config | CAGR% | MaxDD% | Sharpe |
|---|---|---|---|
| 9mo/top8, +6 factor ETFs | 10.11 | -11.43 | 0.97 |
| 9mo/top10, +6 factor ETFs | 11.00 | -11.08 | 1.06 |
| 9mo/top8, original 20 | 11.22 | -12.11 | **1.07** |
| SPY buy & hold (same window) | 14.29 | -23.93 | 1.00 |

The original universe is at least as good as the expanded one. Adding factor
ETFs did not help - a negative result, logged rather than pursued further.

### Individual stocks with real trade-level risk management

Two bugs surfaced building this and are worth naming, because they explain
early nonsense results: (1) daily price panels built from a dict of Series
were not forward-filled, so one ETF's data gap turned a held position's mark
into NaN that silently poisoned every equity value from that day forward; (2)
the first version force-exited every position the instant SPY dipped below its
200-day average, which is a market-wide flatten disguised as a stop - it
flattened winners still trending fine exactly as readily as losers, the
opposite of the instruction. Both fixed: prices are ffilled, and the regime
filter now only gates new entries, never forces an existing position out.

**On the ETF universe** (validates the mechanism on clean data first): still
loses to SPY across every configuration tested, 3.8-5.6% CAGR against SPY's
14.3%. ETFs are already diversified baskets - there is no fat right tail for
"let winners run" to capture, because a fund's own diversification has already
averaged away the individual-name dispersion the mechanism depends on.

**On individual stocks** (point-in-time S&P membership, same delisting-data
caveat as the earlier momentum test - optimistic, more so before 2015):

| config | CAGR% | MaxDD% | Sharpe | Win% | PF | Best trade | Avg win/loss |
|---|---|---|---|---|---|---|---|
| pure momentum, 15 positions | 5.20 | -47.48 | 0.32 | 35.2% | 1.14 | **+313.5%** | +19.4% / -8.3% |
| SPY buy & hold | 13.99 | -33.72 | 0.83 | - | - | - | - |

**The mechanism produces exactly the asymmetric shape asked for** - a 313%
winner, average win 2.3x average loss, positive expectancy despite a 35% win
rate. That is real, and it is what "cut losses short, let winners run" is
supposed to look like.

**It does not survive contact with drawdown.** -47.5% is worse than SPY's own
-33.7%, and CAGR is a third of SPY's. Diagnosing the losses: 30% of losing
trades lost more than 10% despite a 2.5-ATR stop - real overnight gaps through
the stop (NKTR on a trial failure, MRNA's volatility, SMCI's 2024 accounting
scandal, a semiconductor cluster in July 2026, TSLA on an earnings miss), not
a backtest artifact.

Neither obvious fix works:
- **More diversification** (15 -> 30 positions, tighter per-name caps): barely
  moves the needle, -43% to -48% regardless of position count. The risk is
  systemic, not concentration - momentum-selected stocks are high-beta and
  correlated, so a broad selloff hits most open positions at once. Diversifying
  the *names* does not diversify that.
- **Tighter stops** (1.5N instead of 2.5N): makes it worse (CAGR -0.7%, DD
  -54%). Tighter stops just generate more whipsaw without the gap risk going
  away, since gaps blow through any stop level once the move is violent enough.
- **A portfolio-level volatility throttle** on new entries (distinct from the
  per-position stop): best case gets drawdown to -39.6%, still worse than SPY,
  CAGR still stuck at 3.8%. It only slows new entries; it cannot protect
  existing positions from a fast, correlated gap.

**Blending it as a small satellite next to the rotation core also fails.**
Correlation to SPY is 0.52 - not low enough to offset how much worse its
risk-adjusted return is. Sharpe falls monotonically at every satellite weight
tested from 0% to 20%; there is no allocation where adding it helps.

**Verdict: individual-stock trade-level trend following, built correctly with
real cut-losses-short/let-winners-run mechanics, does not fit a 10-15%
drawdown budget and does not beat SPY on return, in this real backtest.**
Rejected, not shelved for later tuning - the failure mode (systemic, gap-driven
drawdown) is not something more parameter search fixes.

### Hardening what did work: cost realism and parameter robustness

Robinhood is commission-free, so the 10bps round-trip cost assumed everywhere
else may be pessimistic:

| cost | CAGR% | Sharpe |
|---|---|---|
| 10 bps (assumed throughout) | 10.66 | 1.03 |
| 5 bps | 10.84 | 1.05 |
| 2 bps (near-zero, Robinhood-realistic) | 10.95 | 1.06 |

Barely moves. The strategy is not fee-sensitive, so Robinhood's zero
commission is a small tailwind, not a load-bearing assumption.

Perturbing the walk-forward-chosen (9-month, top 8) by +/-2 months and +/-2
slots:

| lookback \ top_n | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|
| 7 | 0.78 | 0.80 | 0.85 | 0.84 | 0.83 |
| 8 | 0.92 | 0.91 | 0.94 | 0.98 | 0.99 |
| **9** | 0.91 | 0.95 | **1.03** | 1.04 | 1.04 |
| 10 | 0.86 | 0.99 | 0.99 | 1.01 | 1.06 |
| 11 | 0.86 | 0.91 | 0.93 | 0.95 | 0.96 |

Sharpe forms a smooth plateau (0.78-1.06) across the whole neighbourhood, no
cliff, and (9,8) sits near the top of it rather than on an isolated spike -
the signature of a real, broad optimum rather than curve-fitting to one cell.

### Where this leaves things

The rotation strategy (9-month lookback, 8 slots, 10% volatility cap) remains
the only validated result in this project. Nothing tested today improved on
it, and one serious attempt at literally implementing "cut losses short, let
winners run" produced a real asymmetric payoff structure that was nonetheless
strictly worse on every portfolio-level metric that matters. That is not a
failure of the instruction - the payoff shape it asked for is visibly present
in the trade statistics - it is a failure of individual-stock dispersion to
survive being aggregated into a portfolio without correlated crash risk
swamping it.

---

## A precise after-tax answer, and why tax engineering doesn't fix it

The earlier tax estimate used an annual-aggregate approximation - lump the
year's gain together and tax it at one rate. `rotation_tax_aware.py` tracks
every position's real entry date, real dollar size, and classifies every exit
as short- or long-term at the moment it actually happens, netting short
against short and long against long the way the US tax code does, with loss
carryforward.

**The precise number is worse than the earlier estimate, not better:**

| | pretax CAGR | after-tax CAGR (22%+state) | after-tax CAGR (35%+NIIT) |
|---|---|---|---|
| rotation (9,8, vol-capped) | 10.66% | **8.57%** | 6.86% |
| SPY buy & hold | 12.00% | **10.12%** | - |

A 1.5-3pp gap even in the lowest bracket tested. Only 7.2% of all closed
positions ever reach long-term status - the strategy's own 3-month average
holding period means most positions never get close to a year.

### Two tax-engineering ideas, both tested, both fail

**Hold near-1-year winners a little past their normal cutoff** ("buffer") to
let them cross into long-term treatment - the tax-optimized version of "let
winners run," realizing losses immediately but stretching gains toward the
better rate:

| buffer | pct long-term | after-tax CAGR (22%+state) | improvement |
|---|---|---|---|
| 0 (none) | 7.2% | 8.57% | - |
| 4 slots | 9.1% | 8.63% | **+0.05pp** |

Negligible. There is simply not enough opportunity - so few positions ever
approach the one-year mark that giving them a grace period barely moves the
mix.

**Rebalance quarterly instead of monthly**, trading pretax quality for lower
turnover:

| | pretax CAGR | pretax Sharpe | pct long-term | after-tax (22%+state) |
|---|---|---|---|---|
| monthly | 10.66% | 1.03 | 7.2% | **8.65%** |
| quarterly | 7.89% | 0.79 | 17.7% | **7.78%** |

Quarterly more than doubles the long-term share, but the pretax cost (Sharpe
1.03 -> 0.79, drawdown -17.8% -> -25.2%) is larger than the tax saved. Worse
after-tax at every bracket tested, not better.

### The honest conclusion

**No tax-engineering trick closes this gap, because the problem is turnover
itself, not the absence of a clever holding-period rule around it.** Every
lever that reduces turnover enough to matter also reduces the pretax
Sharpe by more than it saves in tax. In a taxable Robinhood account, the
rotation strategy - the only strategy in this entire project that beat SPY on
risk-adjusted return - loses to plain buy-and-hold once tax is applied
correctly.

This is not a reason to abandon the strategy; it is a reason to hold it in a
account where the comparison flips entirely: none of this drag exists in a
Roth or traditional IRA, because nothing is realized as taxable income along
the way. The single highest-value decision left in this project is which
account this money sits in, not which parameter set trades it.

---

## Session 4: macro timing and earnings-surprise drift - two more angles tested

Two directions genuinely different from everything else in this project:
macro regime data (what the global-macro wizards actually traded on) and
fundamental earnings surprises (post-earnings drift, distinct from price
momentum). Both tested on real data via free sources - FRED for macro,
Alpha Vantage for earnings, budget-constrained by the latter's 25
requests/day free cap.

### Macro timing: the yield curve, tested honestly

`macro.py` pulls Fed funds rate, 10-year yield, the 10y-2y curve slope, CPI,
unemployment and real GDP from FRED (unlimited, no key). The yield curve
inversion is the most famous recession-timing signal in macro finance -
worth testing rather than assuming.

**As a standalone SPY timing signal** (exit while inverted, both a hard 0/1
version and a graduated exposure scale):

| | CAGR% | MaxDD% | Sharpe |
|---|---|---|---|
| exit while inverted | 9.06 | -55.19 | 0.58 |
| graduated exposure scale | 8.47 | -54.49 | 0.60 |
| SPY buy & hold | 10.92 | **-55.19** | 0.65 |

**Identical drawdown to buy & hold - it provided zero crash protection** while
giving up return and Sharpe. The mechanism: the curve typically *un-inverts*
before the actual crash, because the Fed cuts rates in response to
deteriorating data, which steepens the curve right as the real damage is
about to happen. 2006's inversions preceded the best pre-crisis year
(SPY +14-22% forward); 2019's inversion preceded a +22.4% year before COVID
hit outside the test window. Lead times of 6-24+ months with no consistency
make this a bad tactical trigger even though it is a real structural warning.

**As an overlay on the validated rotation strategy** (halving exposure while
inverted, or cutting 30% while the Fed is hiking):

| | CAGR% | MaxDD% | Sharpe |
|---|---|---|---|
| rotation, no macro gate | 10.66 | -17.84 | 1.03 |
| + halved while curve inverted | 10.10 | **-17.84** | 1.04 |
| + reduced 30% while Fed hiking | 9.99 | **-17.84** | 1.06 |

Drawdown is identical to the third decimal in all three - the macro gate adds
nothing the price-based filter was not already doing, and costs a bit of
return. This makes sense: price aggregates everyone's macro view in real
time, and updates daily; a policy-rate or yield-curve series updates on its
own much slower schedule and is, in this comparison, strictly redundant with
what price already captured faster.

### Post-earnings-announcement drift (PEAD)

Distinct mechanism from everything else here: the signal is a fundamental
surprise (actual EPS vs analyst estimate), not a price or volume pattern, and
it is one of the most replicated anomalies in the academic literature
(Bernard & Thomas 1989 and hundreds of successors) - markets are documented to
underreact to earnings surprises, with price continuing to drift toward the
"correct" level for weeks afterward.

**Real data constraint, stated plainly:** Alpha Vantage's earnings-surprise
history is free but capped at 25 requests/day, one call per symbol. That
budget bought earnings data for 4 large caps - AAPL, MSFT, JPM, XOM, chosen
for sector spread (tech x2, financials, energy) rather than randomly, which is
itself a selection choice worth naming. ~300 quarterly events across 4
companies, entries at T+1 day after the report, benchmarked against each
stock's own typical N-day return (so "drift" means excess over baseline, not
just a positive number):

| holding period | big-beat mean excess | t-stat | big-miss mean excess | t-stat |
|---|---|---|---|---|
| 20 trading days | -0.12% | -0.23 | -1.36% | -1.08 |
| 60 trading days | +0.14% | 0.16 | -2.61% | -1.39 |
| 90 trading days | -1.27% | -0.98 | +1.04% | 0.48 |

**No significant drift at any horizon - every t-stat is near zero, several
have the wrong sign entirely.** On its own this would read as "PEAD does not
hold," but that conclusion needs a real caveat: AAPL, MSFT, JPM and XOM are
among the most heavily analyst-covered, most liquid, most efficiently-priced
stocks that exist. The academic literature is explicit that PEAD is strongest
in small and thinly-covered names, precisely because thin coverage is what
lets a surprise go underreacted-to for weeks - and weakest to nonexistent in
mega-caps, where dozens of analysts and systematic funds react within minutes.
Testing PEAD on four of the most-followed stocks on earth is closer to testing
it in the one place theory says it should already be arbitraged away.

**This is a genuinely open question, not a closed one.** A real test needs a
broader, less mega-cap-heavy universe - which needs either a paid Alpha
Vantage tier or a different earnings-surprise data source. Flagged as the
clearest remaining unexplored thread in this project, not dismissed.

### Where this leaves the running total

Six mechanisms tested against the validated rotation strategy this session
and last: factor ETFs, literal cut-losses-short/let-winners-run trade
management, two tax-engineering ideas, yield-curve timing (standalone and as
an overlay), and Fed-policy timing. All six returned negative or negligible
results. The one open thread - PEAD on a proper, less concentrated universe -
remains untested for a data-access reason, not because the idea failed.

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
