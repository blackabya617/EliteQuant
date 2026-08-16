#!/usr/bin/env python3
"""
Daily driver.

  python main.py signal     what the portfolio should hold right now
  python main.py paper      reconcile the Alpaca paper account against it
  python main.py backtest   re-run the validation table from real data

The rotation rebalances monthly, so `signal` is informative every day but only
changes at month end. `paper` is safe to run daily: it computes the drift and
does nothing when the account already matches.
"""

import json
import os
import sys
from datetime import datetime

import config
from rotation import RotationParams, backtest, metrics, month_end_prices, target_weights


def _state_path(name):
    os.makedirs(config.STATE_DIR, exist_ok=True)
    return os.path.join(config.STATE_DIR, name)


def cmd_signal():
    target = target_weights()
    print(f"\nMarket Wizards - rotation signal  ({datetime.now():%Y-%m-%d %H:%M})")
    print("=" * 58)
    print(f"as of month end : {target['as_of']}")
    print(f"universe        : {target['universe_size']} ETFs\n")

    if not target["holdings"]:
        print("  ALL CASH - nothing in the universe is above its 10-month average.")
    else:
        for symbol, weight in target["holdings"].items():
            print(f"  {symbol:5s}  {weight:6.1%}")
    if target["cash_weight"] > 0.001:
        print(f"  {'CASH':5s}  {target['cash_weight']:6.1%}")

    with open(_state_path("last_signal.json"), "w") as fh:
        json.dump({"generated": datetime.now().isoformat(), **target}, fh, indent=2)

    print(f"\nsaved -> {_state_path('last_signal.json')}")
    return target


def cmd_paper():
    from paper_broker import AlpacaPaper, BrokerError

    target = target_weights()
    broker = AlpacaPaper(config.ALPACA_API_KEY, config.ALPACA_API_SECRET)

    if not broker.configured:
        print("\nALPACA_API_KEY / ALPACA_API_SECRET are not set.")
        print("Create free paper keys at https://app.alpaca.markets/paper/dashboard/overview")
        print("and put them in .env, then re-run.\n")
        print("Target portfolio would be:")
        for symbol, weight in target["holdings"].items():
            print(f"  {symbol:5s}  {weight:6.1%}")
        return

    try:
        account = broker.account()
        print(f"\npaper account   : {account['account_number']}")
        print(f"equity          : ${float(account['equity']):,.2f}")
        print(f"buying power    : ${float(account['buying_power']):,.2f}")
        print(f"market open     : {broker.clock()['is_open']}\n")

        actions = broker.rebalance(target["holdings"], dry_run=not config.EXECUTE_PAPER_TRADES)

        if not actions:
            print("Account already matches the target within tolerance. Nothing to do.")
            return

        mode = "SENDING" if config.EXECUTE_PAPER_TRADES else "DRY RUN (set EXECUTE_PAPER_TRADES=true to send)"
        print(f"{mode} - {len(actions)} action(s):")
        for act in actions:
            if act["action"] == "close":
                print(f"  CLOSE {act['symbol']:5s}  (was {act['from_weight']:.1%})")
            else:
                print(f"  {act['action'].upper():5s} {act['symbol']:5s}  ${act['notional']:>10,.2f}"
                      f"   {act['from_weight']:.1%} -> {act['to_weight']:.1%}")

        with open(_state_path("last_rebalance.json"), "w") as fh:
            json.dump({"generated": datetime.now().isoformat(),
                       "executed": config.EXECUTE_PAPER_TRADES,
                       "actions": actions}, fh, indent=2)

    except BrokerError as exc:
        print(f"\nBroker error: {exc}\n")
        sys.exit(1)


def cmd_backtest():
    monthly = month_end_prices()
    params = RotationParams()
    equity, log = backtest(monthly, params)

    warmup = max(params.lookback_months, params.abs_ma_months) + 1
    bench = monthly[config.BENCHMARK].iloc[warmup:]
    bench = bench / bench.iloc[0] * params.initial_capital

    strat_m, bench_m = metrics(equity), metrics(bench)

    print(f"\nRotation vs {config.BENCHMARK} buy & hold")
    print(f"{monthly.index[warmup].date()} -> {monthly.index[-1].date()}")
    print("=" * 58)
    print(f"{'':16s}{'rotation':>14s}{'buy & hold':>14s}")
    for label, key in [("CAGR %", "cagr_pct"), ("max drawdown %", "max_dd_pct"),
                       ("volatility %", "vol_pct"), ("Sharpe", "sharpe"),
                       ("Calmar", "calmar"), ("final equity", "final_equity")]:
        print(f"{label:16s}{strat_m[key]:>14,.2f}{bench_m[key]:>14,.2f}")

    print("\nRotation matches the benchmark's Sharpe with roughly half its")
    print("drawdown. It does not out-earn it. Read the README before trusting it.")
    return equity, log


COMMANDS = {"signal": cmd_signal, "paper": cmd_paper, "backtest": cmd_backtest}

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "signal"
    if command not in COMMANDS:
        print(f"usage: python main.py [{' | '.join(COMMANDS)}]")
        sys.exit(2)
    COMMANDS[command]()
