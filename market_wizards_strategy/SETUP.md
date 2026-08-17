# Running this

## The live path (already running, no setup needed)

The rotation strategy is paper trading right now, broker-free: no API keys,
no account, nothing that can leak. A GitHub Actions workflow
(`.github/workflows/paper-trade.yml`) runs `python main.py run` every weekday
after the close, prices the simulated book against real closes, rebalances if
the signal changed, and commits the result to `paper_state.json` so the
record is auditable in the repo's own history.

To check on it yourself:

```bash
cd market_wizards_strategy
pip install -r requirements.txt

python main.py run       # price the book, rebalance if needed, record a mark
python main.py track     # forward performance vs SPY since day one
python main.py signal    # what the strategy wants to hold right now
python main.py backtest  # re-run the validated 2008-2026 table
```

`run` is idempotent - safe to call as often as you like, it only acts when
something has actually changed. It's also what you'd run locally if you
wanted a mark between scheduled workflow runs, or if you moved the schedule
to your own machine instead of GitHub's.

## Optional: a real Alpaca paper account instead

`main.py paper` and `paper_broker.py` exist as an alternative if you want
actual simulated *broker* fills (order acknowledgements, a real account
dashboard) rather than the self-contained simulation `run` uses. This is not
what's currently deployed - `run` is - so treat this section as "how to switch
to it," not "how it currently works."

1. Sign up free at <https://app.alpaca.markets/signup>, no funding needed.
   Switch to **Paper Trading** and generate an API key pair.
2. `cp .env.example .env`, then add `ALPACA_API_KEY` / `ALPACA_API_SECRET`.
   Leave `EXECUTE_PAPER_TRADES=false` for the first run.
3. `python main.py paper` prints the orders it would send and stops. If the
   target looks right, set `EXECUTE_PAPER_TRADES=true` and run again to place
   them for real (in the paper account - no real money is ever at risk here).

### Where the keys would live

Never paste an API key into a chat, an issue, or a commit - including to an
assistant. If you ever do by accident, rotate it immediately from the Alpaca
dashboard; regenerating takes seconds and instantly invalidates the old pair.

Locally, `.env` is enough and the keys never leave your machine. To run this
path on a schedule without your machine being on, GitHub's encrypted repo
secrets (Settings -> Secrets and variables -> Actions) work the same way -
store `ALPACA_API_KEY` and `ALPACA_API_SECRET` there, never in a workflow file
or the repo itself. Note EliteQuant is a public repo, so even with secrets
masked, switching to this path makes the fact that you're running it (though
not the keys) visible in public Actions logs.

## What to expect

Based on the 2008-2026 backtest: roughly SPY's return with roughly half its
drawdown, pretax. Read the README before trusting any of this for real money -
in particular, the after-tax analysis there found the strategy currently
*loses* to plain buy-and-hold in a taxable account, because of how often it
rebalances.

If the live numbers start beating SPY by a wide margin, be suspicious rather
than pleased - that isn't what the backtest predicts, and it's more likely a
bug than a discovery. (This project has found several of exactly that kind of
bug already; see the README's running list.)
