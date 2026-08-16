#!/usr/bin/env python3
"""
Test Script - Demonstrates alert system with a forced signal
"""

from alerts import AlertSystem
from datetime import datetime


def test_breakout_alert():
    """Test alert system with a breakout signal."""
    print("\n" + "="*60)
    print("Testing BREAKOUT Signal Alert")
    print("="*60 + "\n")

    signal = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'price': 570.94,
        'entry_signal': 'BREAKOUT',
        'entry_price': 570.94,
        'stop_loss': 559.72,  # 2% below
        'take_profit': 599.49,  # 5% above
        'ma_200': 542.44,
        'ma_50': 513.63,
    }

    print("📊 Signal Details:")
    print(f"  Entry Signal: {signal['entry_signal']}")
    print(f"  Entry Price: ${signal['entry_price']:.2f}")
    print(f"  Stop Loss: ${signal['stop_loss']:.2f}")
    print(f"  Take Profit: ${signal['take_profit']:.2f}")
    print(f"  Risk/Reward: 1:{((signal['take_profit'] - signal['entry_price']) / (signal['entry_price'] - signal['stop_loss'])):.2f}\n")

    # Send alerts (Telegram would send if configured, email would send if configured)
    alert_system = AlertSystem()
    alert_system.send_all_alerts(signal)

    print("\n✅ Test complete!")
    print("   (Telegram/Email alerts would be sent here if configured)")


def test_pullback_alert():
    """Test alert system with a pullback signal."""
    print("\n" + "="*60)
    print("Testing PULLBACK Signal Alert")
    print("="*60 + "\n")

    signal = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'price': 510.00,
        'entry_signal': 'PULLBACK',
        'entry_price': 513.63,  # At 50-day MA
        'stop_loss': 503.36,  # 2% below
        'take_profit': 539.31,  # 5% above
        'ma_200': 542.44,
        'ma_50': 513.63,
    }

    print("📊 Signal Details:")
    print(f"  Entry Signal: {signal['entry_signal']}")
    print(f"  Entry Price: ${signal['entry_price']:.2f} (at 50-day MA)")
    print(f"  Stop Loss: ${signal['stop_loss']:.2f}")
    print(f"  Take Profit: ${signal['take_profit']:.2f}")
    print(f"  Risk/Reward: 1:{((signal['take_profit'] - signal['entry_price']) / (signal['entry_price'] - signal['stop_loss'])):.2f}\n")

    # Send alerts
    alert_system = AlertSystem()
    alert_system.send_all_alerts(signal)

    print("\n✅ Test complete!")
    print("   (Telegram/Email alerts would be sent here if configured)")


if __name__ == "__main__":
    print("\n🚀 MARKET WIZARDS - ALERT SYSTEM TEST\n")
    test_breakout_alert()
    test_pullback_alert()
