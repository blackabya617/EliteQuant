# Market Wizards Strategy

An honest attempt to build a Market Wizards-style swing system that beats the
S&P 500, and a record of what the data actually said when we tested it.

**Headline: nothing here out-earns buying and holding SPY, and for an account
funded by regular contributions SPY is clearly better.** One variant does beat
SPY on risk-adjusted terms - Sharpe 1.03 against 0.81, with a -17.8% worst
drawdown against -46.3% - but it earns less (10.66% CAGR against 12.12%), and
that gap widens rather than closes once contributions and taxes are modelled.

Read `contributions.py` before deciding anything: for someone paying in every
month, the drawdown protection that is this project's only validated edge is
worth *less than nothing*, because a contributor's next payment is supposed to
buy the dip. SPY ended ahead in 27 of 27 rolling start dates tested.

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

## Session 5: chasing PEAD harder - a real bug, caught before it was reported

Told to keep digging, the clearest remaining thread was PEAD tested properly:
a broad, mid-cap-tilted universe instead of 4 mega-caps, since the literature
says the effect is strongest in less-covered names. Nasdaq's public
earnings-surprise endpoint (unkeyed, no visible rate limit, unlike Alpha
Vantage's 25/day cap) made this possible: 402 companies, 1,600 quarterly
events, deliberately excluding the top 15% by liquidity to bias toward where
PEAD theory predicts a real effect.

### The exciting number, and why it was wrong

A long-only rolling basket - hold anything that reported a >=5% earnings beat
within the last 60 trading days, equal weight, daily rebalance - produced:

**34.9% CAGR, -7.0% max drawdown, Sharpe 2.32** against SPY's 23.0%/-8.9%/1.67
over the same window, survived a 10bps-cost check, and had beta 0.71 to SPY -
better return with less market exposure. The single best number in this
entire project. It was also wrong, and the process of finding out why is
worth recording in full because it is the same mistake in different clothes
as the position-sizing and lookahead bugs found earlier.

**The control that should have been run first, and was:** holding the entire
402-stock universe, equal-weighted, with zero earnings conditioning, produced
21.1% CAGR / Sharpe 1.62 - essentially identical to SPY. That ruled out "the
universe itself is just a hot basket" and made the earnings-conditioned
result look genuinely earnings-driven, not a selection artifact. It was the
wrong control to stop at.

**The actual bug:** basket eligibility required only `report_date <= prev`,
where `prev` is the trading day immediately before the return being computed.
For a stock that reported on day T, that allowed T to equal `prev`, so the
very first return captured for that position was `close[T+1] / close[T] - 1`
- the earnings reaction itself, not the drift that follows it. Checked
directly on Micron: reported 2026-06-24, closed that day at $1,048 (pre-
reaction), and the *very first day it entered the basket* captured the
close-to-close jump to $1,213 the next session - a +15.7% single-day return
that is the announcement reaction, not multi-week drift. That reaction is not
capturable in real trading: by the time you could act on a report, the gap
that produced it has already happened.

**The fix, and what it did to the result:** require the report date to be at
least `N` trading days before the basket-inclusion cutoff, so the reaction
itself is structurally excluded from every captured return:

| entry lag | CAGR% | MaxDD% | Sharpe |
|---|---|---|---|
| 0 days (the bug) | 39.28 | -6.93 | **2.59** |
| 1 day | 33.55 | -7.09 | 2.24 |
| 2 days | 31.28 | -7.52 | 2.13 |
| 3 days | 25.88 | -7.74 | 1.89 |
| 5 days | 23.24 | -7.98 | 1.72 |
| 10 days | 19.98 | -8.43 | 1.46 |
| 15 days | 21.65 | -9.20 | 1.54 |
| 20 days | 20.52 | -9.15 | 1.45 |
| **SPY, same window** | **23.05** | **-8.88** | **1.67** |

**Monotonic decay, converging exactly onto SPY by day 5 and staying there
through day 20.** There is no residual edge once the reaction itself is
excluded - the entire earlier result was the reaction, full stop. This
matches, and reinforces, the null result from the 4-mega-cap test earlier:
PEAD does not show up in this data once measured correctly, in either the
most-covered names or a broad mid-cap sample.

### Why this matters beyond this one result

This is the sharpest illustration in the whole project of the difference
between a fast backtest and a validated one. The number looked spectacular,
passed a real control, passed a transaction-cost check, and was still
completely wrong - caught only by tracing individual trades back to actual
prices on actual dates and asking whether the return being captured could
physically have been earned by a real order placed after the information was
public. Every number elsewhere in this repository has been checked the same
way; this is the case where it mattered most.

The one honest thing worth naming as a boundary, not a lead: the reaction
itself (lag=0, Sharpe 2.59) is real money on the table in the sense that the
reaction happens - it is simply not accessible after the fact. Trading it
would require holding a position *before* an earnings report specifically to
catch the reaction, which is a bet on a binary event with no demonstrated
forecasting edge, not a systematic strategy. Not pursued, and should not be.

### Where this leaves the search

Seven mechanisms now tested against the validated rotation strategy across
four sessions: factor ETFs, literal trade-level cut-losses-short/let-winners-
run, two tax-engineering approaches, yield-curve timing (standalone and
overlay), Fed-policy timing, and now PEAD on both a mega-cap and a broad
mid-cap universe. All seven negative, several caught only after a promising-
looking result turned out to be a bug. Rotation (9-month lookback, 8 slots,
10% volatility cap) remains the only validated result in this project.

---

## Session 6: the sizing bug that was actually there

Told to check the sizing rules directly, on the theory that something in how
positions get sized might be quietly suppressing every result. That
instinct was right, just not in the place it would have mattered most for the
backtest - it was in the live signal.

### What was wrong

`rotation.py`'s volatility-targeting exposure calculation (`_exposure()`)
needs the strategy's *natural*, pre-exposure return series to estimate how
volatile the strategy currently is. `backtest()` gets this right internally -
it tracks a separate `raw_history` of unscaled returns specifically for this
purpose. `target_weights()`, which computes the live signal that
`papertrade.py` actually trades, instead pulled `return_pct` out of
`backtest()`'s log - which is the *already-scaled* (post-exposure) return
series.

That is circular. If the strategy went through a genuinely volatile stretch,
exposure gets cut - correctly. But the cut also suppresses the *recorded*
return's volatility, since a smaller position produces a smaller move either
way. Feeding that dampened series back into the next volatility estimate
reads as "conditions have calmed down," so exposure gets raised again - the
model partially undoing its own risk cut, using evidence that the cut itself
manufactured.

### What it did to the actual numbers

| | using RAW history (correct) | using SCALED history (the bug) |
|---|---|---|
| exposure this test case | 0.5456 | 0.6710 |
| difference | | **+12.5 percentage points too aggressive** |

The live paper account had been running at **71.9% exposure when the correct
figure was 55.2%** - carrying meaningfully more risk than the validated
strategy actually calls for.

### What it did NOT do

`backtest()` was never affected - it always used the correct `raw_history`
internally. Every performance number in this README, the entire validated
9-month/8-slot/10%-vol-cap result, the walk-forward selection, the bootstrap
significance test - all of it went through `backtest()`, not the buggy path,
and none of it changes. This was a live-signal bug, not a backtest bug: the
gap between what was validated and what was actually being traded, not a gap
between what was validated and reality.

### Fixed, and the live account corrected

`backtest()`'s log now carries both `return_pct` (for the equity curve) and
`raw_return_pct` (for anything estimating volatility). `target_weights()` now
reads `raw_return_pct`. The live paper account was force-rebalanced the same
day to the corrected 55.2% exposure - trimmed each of its 8 positions from 9%
down to ~6.9%.

### The same bug, found again, in a strategy already rejected

`swing.py`'s portfolio-level volatility throttle has the identical pattern -
it estimates volatility from `curve`, the actual marked equity after every
stop, trail and prior sizing decision, rather than a raw pre-scaling series.
Worth naming for completeness and because it is a pattern worth watching for
elsewhere, but it doesn't change that strategy's verdict: individual-stock
trade-level momentum was already rejected on much stronger grounds (systemic
gap-driven drawdown that neither diversification nor this same throttle could
fix). `engine.py` doesn't have this class of bug at all - its position sizing
uses same-day equity for same-day decisions, with no retrospective volatility
window to be circular about.

### Deployment audit, same session

Fixing a real gap between "validated" and "actually trading" prompted a
closer look at the rest of the deployment path, which had its own drift:
`main.py track` was reading `tracker.py`'s state - a leftover from an earlier
Alpaca-based design that nothing has written to since `papertrade.py` (the
broker-free live path) replaced it. Running `track` would have silently
reported stale or empty history while the real account kept moving. Fixed to
read `papertrade.py`'s state, which is what the scheduled GitHub Actions
workflow actually updates. `SETUP.md` was rewritten to lead with the
broker-free path as primary - it previously documented Alpaca API keys as
the main setup, which stopped being true the session `papertrade.py` was
built, several sessions ago.

---

## Session 7: a second real bug, found by auditing the live cost model

Kept digging into the code rather than searching for new signals, on the
theory that the sizing-rule bug found last session might not be the only one.
It wasn't.

### The bug

Every cost assumption elsewhere in this project - `rotation.py`'s
`cost_bps`, the README's own text - treats `cost_bps=10.0` as a **round-trip**
figure: the total cost of replacing one holding with another. `papertrade.py`,
which is what the live paper account actually trades through, charged the
full `COST_BPS` independently on *each leg* of a swap - the sell of the old
position and the buy of the new one - which doubles it to an effective 20bps
round-trip for a full rotation:

| | cost for a full portfolio rotation |
|---|---|
| `backtest()` (validated numbers) | 10.00 bps |
| `papertrade.py` (the bug) | **20.00 bps** |

Verified directly: a account holding $10,000 in one name, rebalanced entirely
into another, should lose $10 to costs (10bps) and was losing $20 (0.2%)
before the fix.

### What it did and didn't affect

Checked the actual paper account: two rebalances since inception, ~$8,872
total traded, so the bug had cost about **$4.40** in excess fees - real but
immaterial at this account's age, and not worth a revisionist retroactive
correction (the historical record stays as it happened; the fix applies
going forward). Left uncorrected, the drag would have compounded to
something worth caring about over a full year of monthly rebalancing.

This did not touch any backtested number in this README - `backtest()` has
always used the correct turnover-based cost model. It is the same shape of
finding as the exposure bug in the previous session: a gap between what was
validated and what was actually trading, not a flaw in the validation.

### Fixed

`papertrade.py` now charges `COST_BPS / 2` on each leg, so a full round-trip
correctly nets to `COST_BPS` total, matching the convention used everywhere
else in the project.

---

## Session 8: the month-boundary bug - the live strategy was picking different assets

Continued the audit into rebalance timing, the one part of the live path not
yet stress-tested. This turned up the third live-vs-backtest gap, and the
most consequential of the three: the previous two changed *how much* was
held, this one changed *what* was held.

### The bug

`month_end_prices()` builds its panel with `.resample("M").last()`. That
labels every bucket with the month's end date but fills the final one with
whatever the latest available price is - so today the panel's last row reads
`2026-08-31` while actually containing data only through `2026-08-14`, ten of
August's ~21 trading days.

`backtest()` never anchors a signal there: it calls
`select(as_of=monthly.index[i - 1])`, always a completed month.
`target_weights()` - the live signal - called `select(monthly, p)`, which
defaults to `monthly.index[-1]`: the running, partial month.

So the live book was ranking on a 9-month momentum window anchored on a
half-finished August, while every validated number in this README describes a
window anchored on a completed July.

### It changed the actual holdings, and made them depend on the scheduler

Right now, the two conventions disagree on one of eight positions - live had
QQQ where the validated strategy holds XLV, 12.5% of the book in a different
asset. That is not a one-off. Rebuilding the panel as it would have stood on
various days of the month, across 47 months of history:

| anchor used | avg positions differing (of 8) | months matching the validated convention |
|---|---|---|
| 1st trading day of month | 1.36 | 23% |
| 3rd | 1.62 | 17% |
| 5th | 1.83 | 13% |
| 10th | 1.91 | **11%** |

Two separate problems in one. The obvious one: the live strategy is not the
strategy that was tested. The subtler one: a partial month's data changes
every day, so the ranking churns underneath the signal, which means **the
holdings depended on which day the scheduler happened to fire** - a workflow
run on the 2nd of the month would produce a materially different portfolio
than the same code run on the 9th. No amount of backtesting says anything
about a strategy whose output depends on cron timing.

### Fixed

Added `last_complete_month()`, and `target_weights()` now anchors there -
`select(as_of=monthly.index[anchor])`, exactly matching `backtest()`. The
volatility history feeding the exposure cap is truncated to the same anchor,
since a partial month's return is not comparable to the full-month returns
the `sqrt(12)` annualisation assumes. `papertrade.py`'s rebalance gate now
tags by the anchor month rather than the running calendar month - same
once-monthly cadence, but the log now names the month whose close actually
drove the trade.

The signal output gained a `priced_through` field alongside `as_of`, so the
distinction between "what determined these holdings" (July close) and "what
this is marked at" (latest price) is visible rather than implicit.

Verified after the fix: live holdings match the validated convention exactly,
exposure settled at 0.5456 - which is precisely the figure the previous
session's raw-history diagnostic had independently predicted as correct - and
the live account was corrected with two trades (sell QQQ, buy XLV). No
backtested number changed; `backtest()` was correct throughout.

### Three sessions, three bugs, same shape

All three were gaps between the validated strategy and the trading one, none
were flaws in the validation:

| session | bug | effect |
|---|---|---|
| 6 | vol estimate fed its own scaled output | live ran 71.9% exposure vs correct 55.2% |
| 7 | transaction cost charged per leg, not round-trip | 2x the intended cost drag |
| 8 | signal anchored on the running partial month | different assets held; output depended on cron timing |

Worth naming the pattern: a backtest can be entirely correct and still tell
you nothing useful if the live path reimplements the same decisions slightly
differently. The backtest was right every time. What needed auditing was
everything downstream of it.

---

## Session 8b: pinning the invariants, and one more latent bug they caught

Three bugs of the same shape, found one per session by hand, is a pattern
rather than bad luck. `test_invariants.py` converts each into an executable
assertion, so a fourth divergence fails loudly instead of waiting to be
noticed:

| invariant | the bug it pins |
|---|---|
| live holdings == backtest-convention holdings | session 8's partial-month anchor |
| backtest log exposes an unscaled return series, and `scaled == raw x exposure` | session 6's circular vol estimate |
| a full round-trip costs `COST_BPS`, not 2x | session 7's per-leg cost |
| target weights sum to <= 1.0, cash weight agrees | general safety |
| a malformed target is refused rather than margined | the guard added in session 7 |
| `select()` ignores data after its `as_of` | lookahead, the original sin of this project |
| a second same-day step places no trades | idempotency, since CI runs daily |

The suite is dependency-free (no pytest here), never touches the real
`paper_state.json`, and now runs as a **gate before the trade** in the
scheduled workflow. Skipping a day's rebalance is strictly better than
trading a strategy nobody has tested.

### Writing the tests immediately found a fourth bug

The round-trip cost test - a plain 100%-invested swap of one holding for
another - crashed on the margin guard. That was not a bad test. Selling
$10,000 of a holding returns $9,995 after costs, while the replacement buy is
still sized against the *pre-cost* $10,000 of equity. The shortfall is exactly
the transaction cost, so **any fully-invested target was unfillable**, and the
guard would have refused to trade at all.

It had never fired in production only because the volatility cap has kept
exposure near 55%. Any month calm enough to allow 100% exposure - or simply
running with `vol_cap=None` - would have halted the strategy outright.

Fixed by separating the two cases that the single guard had conflated. A
target summing above 1.0 is a genuine upstream bug and is still refused
loudly. A target summing to exactly 1.0 is legitimate, and its buys are now
clamped to cash actually on hand, absorbing the cost shortfall. Both
behaviours are pinned by tests.

That is four bugs from four consecutive audits, every one of them downstream
of a backtest that was correct the entire time.

---

## Session 9: the data layer could corrupt the forward record

The forward paper record is the only evidence in this project that was not
selected with hindsight, and it is committed to git daily - which makes a
wrong observation worse than a missing one, because it persists and gets
believed. Audited the data path on that basis.

### A single failed download would post a phantom loss

`_latest_prices()` collects prices per symbol and swallows failures.
`equity()` then summed `qty * price` **only over symbols present in that
dict** - so any held position that failed to download was valued at exactly
zero:

```
holdings: 50 shares of A @ $100, 50 shares of B @ $100
equity, all prices present : $10,000
equity, B failed to price  : $5,000
```

A transient network blip on one ETF would have written a 50% loss into the
permanent record, indistinguishable from a real one. Nothing would have
raised, and the workflow would have committed it and moved on.

### Staleness could hide behind fresh symbols

`_latest_prices()` returned a single `asof` computed as the **max** across
symbols, and `step()` only checked whether the price dict was entirely empty.
So one symbol stuck days or weeks behind - a delisting, a broken feed,
`data_manager.load()` silently falling back to an old cache after a failed
download - would be marked at its stale price while the summary date looked
current, because some other symbol was fresh.

### Fixed

`equity()` is now strict by default and refuses to mark a book containing an
unpriceable position. `_latest_prices()` returns per-symbol dates rather than
a max. A new `_check_data_health()` runs before anything is recorded and
rejects three distinct conditions: a held position with no price, a *target*
position with no price (trading anyway would silently under-invest), and any
relevant symbol staler than six calendar days (enough slack for a long
weekend plus a holiday). `price_asof` in the record now reports the **oldest**
priced leg rather than the newest, so the stored mark describes how current it
genuinely is.

The principle throughout: a missed day's observation is recoverable, a wrong
one committed to the record is not. Every one of these now fails loudly and
skips the day rather than writing a confident wrong number.

`data_manager.load()` still falls back to a stale cache when a download
fails, which is reasonable behaviour on its own - and is now caught
downstream by the staleness check rather than passing through unnoticed.

### Suite now at 17 assertions

The invariant tests grew to cover all of the above, and still gate the trade
in CI. Five bugs found across five consecutive audits, every one of them
downstream of a backtest that was correct throughout.

---

## Session 9b: the strategy is a poor fit for how this account is actually funded

Every backtest above assumes a lump sum invested once. This account is not
funded that way - it starts small and receives a contribution every paycheck -
and modelling that changes the conclusion rather than refining it.

A regular contributor has a different relationship with drawdowns than a
lump-sum investor. When prices fall, the lump-sum investor simply loses money.
The contributor's next payment buys more shares at the lower price. Drawdown
protection - the single edge that survived every test in this project - is
therefore worth much less to a contributor, and can be worth less than
nothing: avoiding the decline also means skipping the cheap shares.

Contributing $200/month from a $300 start, over the full 18.5-year window:

| | rotation (9mo/top8, vol cap) | SPY buy & hold |
|---|---|---|
| paid in | $44,700 | $44,700 |
| ended with | $150,373 | **$205,597** |
| multiple on money in | 3.36x | **4.60x** |
| worst drawdown along the way | **-11.2%** | -22.5% |

**SPY produced 37% more wealth on identical contributions.** Across 27 rolling
start dates the direction never reversed - SPY ended ahead in all 27, with the
edge ranging from 8% (shortest window) to 37% (longest). Those windows overlap
and share an end date, so that is a statement about consistency rather than 27
independent samples, but the mechanism is not subtle and the sign never flips.

### The actual trade being offered

The contributor gives up roughly a third of terminal wealth to halve the
drawdown experienced along the way: -11.2% instead of -22.5% at the worst
point. That is the whole proposition, stated plainly.

Whether it is worth taking is a genuine judgement call rather than a
calculation, and it depends on something no backtest can measure: the
drawdown you will actually sit through without selling. A -22.5% dip that
gets panic-sold at the bottom is far worse than either column above. A
strategy you can hold is better than a better strategy you cannot.

What the numbers do settle is that this is a *cost*, not a free improvement,
and a larger one than the lump-sum tables imply.

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
