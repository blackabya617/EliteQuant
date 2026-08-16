#!/usr/bin/env python3
"""
Market Wizards Strategy - Main Entry Point
Runs daily scans for trading signals and sends alerts.
"""

import yfinance as yf
from datetime import datetime, timedelta
from strategy import get_strategy_signals
from alerts import AlertSystem
from config import SYMBOL


def get_latest_data(symbol, days=200):
    """Fetch latest OHLCV data."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    df = yf.download(symbol, start=start_date, end=end_date, progress=False)
    return df


def run_daily_scan():
    """Run daily market scan and send alerts if signals trigger."""
    print(f"\n{'='*60}")
    print(f"Market Wizards Daily Scan - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Fetch latest data
    print(f"Fetching {SYMBOL} data...")
    df = get_latest_data(SYMBOL)

    if len(df) < 200:
        print("❌ Not enough data")
        return

    # Get signals
    print(f"Analyzing signals...")
    signal = get_strategy_signals(df)

    if not signal:
        print("⚠️  No signal generated")
        return

    # Display signal
    print(f"\nSignal for {signal['date']}:")
    print(f"  Price: ${signal['price']:.2f}")
    print(f"  Trend Filter (above MA200): {signal['trend_filter_pass']}")
    print(f"  MA200: ${signal['ma_200']:.2f}")
    print(f"  MA50: ${signal['ma_50']:.2f}")

    if signal['entry_signal']:
        print(f"  ✅ ENTRY SIGNAL: {signal['entry_signal']}")
        print(f"     Entry: ${signal['entry_price']:.2f}")
        print(f"     Stop Loss: ${signal['stop_loss']:.2f}")
        print(f"     Take Profit: ${signal['take_profit']:.2f}")

        # Send alerts
        alert_system = AlertSystem()
        alert_system.send_all_alerts(signal)
    else:
        print(f"  ⏸️  No entry signal (waiting for setup)")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    run_daily_scan()
