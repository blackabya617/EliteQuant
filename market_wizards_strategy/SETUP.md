# Paper trading setup

Three steps, about five minutes. Everything else is already wired.

## 1. Free Alpaca paper account

Sign up at <https://app.alpaca.markets/signup> — no funding, no card. Once in,
switch to **Paper Trading** (toggle, top-left) and generate an API key pair from
the dashboard. You get a Key ID and a Secret Key; the secret is shown once.

## 2. Add the keys

```bash
cd market_wizards_strategy
cp .env.example .env
```

Edit `.env`:

```
ALPACA_API_KEY=PK...
ALPACA_API_SECRET=...
EXECUTE_PAPER_TRADES=false
```

Leave `EXECUTE_PAPER_TRADES=false` for the first run.

## 3. Dry run, then arm it

```bash
python main.py paper
```

This prints the orders it *would* send and stops. If the list looks right
(five ETFs at 20% each), set `EXECUTE_PAPER_TRADES=true` and run it again to
actually place them.

## Where the keys live

The keys never need to be shared with anyone, including an assistant. Pick one:

**A. Your own machine.** Put them in `.env` as above and run it locally. The
keys never leave your computer. Simplest and safest.

**B. GitHub Actions** (`.github/workflows/paper-trade.yml`, already committed).
Runs after the close on weekdays without your machine being on. Set the keys
once:

> repo -> Settings -> Secrets and variables -> Actions -> New repository secret
>   `ALPACA_API_KEY`
>   `ALPACA_API_SECRET`

GitHub encrypts them, masks them in logs, and does not expose them to pull
requests from forks. Scheduled runs stay in dry run until you add a repository
*variable* `EXECUTE_PAPER_TRADES` set to `true`, or tick the box on a manual
"Run workflow".

One caution: **EliteQuant is a public repo**, so the workflow's logs are
world-readable. The secrets themselves stay masked and the account number is
truncated, but if that bothers you, move this code to a private repo before
arming it.

Never paste API keys into a chat window, an issue, or a commit. If you ever do
by accident, rotate them immediately from the Alpaca dashboard — regenerating
takes seconds and instantly invalidates the old pair.

## Running it on a schedule

The rotation rebalances monthly, so the meaningful run is the first trading day
of each month. Running daily is harmless — it no-ops when the account already
matches within 2%, and it records an equity observation for forward tracking.

```bash
crontab -e
# weekdays at 16:15 ET, after the close
15 16 * * 1-5 cd /path/to/market_wizards_strategy && /usr/bin/python3 main.py paper >> ~/mw.log 2>&1
```

## Checking how it is actually doing

```bash
python main.py track
```

This compares the paper account against SPY over the identical window, starting
the day you began. It is the only evidence in this project that was not
selected with hindsight — every table in the README is a backtest chosen after
seeing the data.

Expect it to prove nothing for a long while. The rotation turns over about
twelve times a year, so even a full year is a small sample. Do not conclude
anything from the first few months in either direction.

## What you should expect

Based on 2008-2026 backtests, roughly SPY's return with roughly half the
drawdown. Concretely: when SPY next falls 40%, this should fall about 20%. In a
straight-up year it will probably lag SPY somewhat.

If it starts consistently *beating* SPY by a wide margin, be suspicious rather
than pleased — that is not what the backtest predicts, and it more likely means
something is wrong with the implementation than that we found free money.
