"""
Backtester for Market Wizards Strategy
Tests strategy performance on historical SPY data.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from strategy import MarketWizardsStrategy
from data_manager import DataManager
from config import SYMBOL, LOOKBACK_DAYS, INITIAL_CAPITAL


def calculate_metrics(trades_df, initial_capital=INITIAL_CAPITAL):
    """Calculate backtest performance metrics."""
    if len(trades_df) == 0:
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'profit_factor': 0,
            'total_pnl': 0,
            'total_pnl_pct': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'max_drawdown': 0,
        }

    trades = trades_df.copy()
    trades['pnl'] = trades['pnl'].fillna(0)

    winning_trades = trades[trades['pnl'] > 0]
    losing_trades = trades[trades['pnl'] < 0]

    total_wins = winning_trades['pnl'].sum()
    total_losses = abs(losing_trades['pnl'].sum())

    metrics = {
        'total_trades': len(trades),
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades),
        'win_rate': (len(winning_trades) / len(trades) * 100) if len(trades) > 0 else 0,
        'profit_factor': (total_wins / total_losses) if total_losses > 0 else 0,
        'total_pnl': trades['pnl'].sum(),
        'total_pnl_pct': (trades['pnl'].sum() / initial_capital * 100),
        'avg_win': trades[trades['pnl'] > 0]['pnl'].mean() if len(winning_trades) > 0 else 0,
        'avg_loss': trades[trades['pnl'] < 0]['pnl'].mean() if len(losing_trades) > 0 else 0,
        'best_trade': trades['pnl'].max(),
        'worst_trade': trades['pnl'].min(),
        'avg_days_held': trades['days_held'].mean() if 'days_held' in trades else 0,
    }

    return metrics


def run_backtest(use_synthetic=False):
    """Run full backtest."""
    # Fetch data
    data_manager = DataManager()
    df = data_manager.fetch_data(SYMBOL)

    # Fallback to synthetic data for demonstration
    if df is None or len(df) < 300:
        print("\n⚠️  Using synthetic data for demonstration")
        print("(In production, ensure network/API access is configured)")
        df = data_manager.create_synthetic_data(2000)
        use_synthetic = True

    if len(df) < 300:
        print("❌ Not enough data for backtesting")
        return None

    print(f"✅ Loaded {len(df)} candles")
    if use_synthetic:
        print("   (Note: Using synthetic data for demo)")
    print()

    # Run strategy
    print("Running backtest...")
    strategy = MarketWizardsStrategy(capital=INITIAL_CAPITAL)
    trades = strategy.backtest(df)

    if len(trades) == 0:
        print("⚠️  No trades generated during backtest")
        return None

    # Calculate metrics
    metrics = calculate_metrics(trades, INITIAL_CAPITAL)

    # Display results
    print("\n" + "="*60)
    print(f"BACKTEST RESULTS - {SYMBOL}")
    print("="*60)
    print(f"Period: {df.index[0].date()} to {df.index[-1].date()}")
    print(f"Starting Capital: ${INITIAL_CAPITAL:,.0f}")
    print(f"Ending Capital: ${INITIAL_CAPITAL + metrics['total_pnl']:,.0f}")
    print(f"\nTrade Statistics:")
    print(f"  Total Trades: {metrics['total_trades']}")
    print(f"  Winning Trades: {metrics['winning_trades']}")
    print(f"  Losing Trades: {metrics['losing_trades']}")
    print(f"  Win Rate: {metrics['win_rate']:.1f}%")
    print(f"  Profit Factor: {metrics['profit_factor']:.2f}")
    print(f"\nPerformance:")
    print(f"  Total P&L: ${metrics['total_pnl']:,.2f}")
    print(f"  Total P&L %: {metrics['total_pnl_pct']:.2f}%")
    print(f"  Average Win: ${metrics['avg_win']:,.2f}")
    print(f"  Average Loss: ${metrics['avg_loss']:,.2f}")
    print(f"  Best Trade: ${metrics['best_trade']:,.2f}")
    print(f"  Worst Trade: ${metrics['worst_trade']:,.2f}")
    print(f"  Average Days Held: {metrics['avg_days_held']:.1f}")
    print("="*60)

    # Compare to S&P 500 buy-and-hold
    spy_return = ((df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0]) * 100
    print(f"\nBuy & Hold SPY Return: {spy_return:.2f}%")
    print(f"Strategy Return vs B&H: {metrics['total_pnl_pct'] - spy_return:.2f}%")
    print("="*60 + "\n")

    return {
        'trades': trades,
        'metrics': metrics,
        'spy_buy_hold': spy_return,
        'df': df
    }


if __name__ == "__main__":
    results = run_backtest()

    if results:
        # Display top 10 trades
        print("Top 10 Trades by Profit:")
        print(results['trades'].nlargest(10, 'pnl')[
            ['entry_date', 'exit_date', 'entry_price', 'exit_price', 'pnl', 'pnl_pct']
        ].to_string(index=False))
