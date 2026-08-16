"""
Market Wizards Hybrid Strategy
Combines trend following (Paul Tudor Jones), breakout trading (Richard Dennis),
and strict risk management (all wizards).
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from config import (
    MA_200_PERIOD, MA_50_PERIOD, BREAKOUT_PERIOD,
    BREAKOUT_VOLUME_MULTIPLIER, PULLBACK_TOLERANCE,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, TIME_STOP_DAYS,
    RISK_PCT_PER_TRADE
)


class MarketWizardsStrategy:
    def __init__(self, capital=10000):
        self.capital = capital
        self.position = None
        self.entry_price = None
        self.entry_date = None
        self.stop_loss = None
        self.take_profit = None
        self.trades = []

    def calculate_indicators(self, df):
        """Calculate all technical indicators."""
        df['MA_200'] = df['Close'].rolling(window=MA_200_PERIOD).mean()
        df['MA_50'] = df['Close'].rolling(window=MA_50_PERIOD).mean()

        # 20-day high/low for breakout
        df['High_20'] = df['High'].rolling(window=BREAKOUT_PERIOD).max()
        df['Low_20'] = df['Low'].rolling(window=BREAKOUT_PERIOD).min()

        # Average volume for confirmation
        df['Volume_MA_20'] = df['Volume'].rolling(window=BREAKOUT_PERIOD).mean()

        return df

    def check_trend_filter(self, row):
        """Rule 1: Price must be above 200-day MA (we're in uptrend)."""
        if pd.isna(row['MA_200']):
            return False
        return row['Close'] > row['MA_200']

    def check_breakout_entry(self, row, prev_row):
        """Rule 2: Breakout above 20-day high with volume confirmation."""
        if pd.isna(row['High_20']) or pd.isna(prev_row['High_20']):
            return False

        # Price breaks above 20-day high
        breakout = row['Close'] > row['High_20'] and prev_row['Close'] <= prev_row['High_20']

        # Volume confirmation
        volume_confirmed = row['Volume'] > row['Volume_MA_20'] * BREAKOUT_VOLUME_MULTIPLIER

        return breakout and volume_confirmed

    def check_pullback_entry(self, row):
        """Rule 3: Pullback to 50-day MA while 200-day MA is up (lower-risk re-entry)."""
        if pd.isna(row['MA_50']) or pd.isna(row['MA_200']):
            return False

        # Price is at/near 50-day MA (within 2%)
        at_ma50 = abs(row['Close'] - row['MA_50']) / row['MA_50'] <= PULLBACK_TOLERANCE

        # 200-day MA still pointing up
        ma200_up = row['MA_200'] > row['Close'] - (row['Close'] * 0.05)  # Price reasonably close to MA200

        return at_ma50 and ma200_up

    def check_exit(self, row, trade_day_count):
        """Check for stop loss, take profit, or time stop."""
        if self.entry_price is None:
            return None

        # Stop loss: 2% below entry
        if row['Low'] <= self.entry_price * (1 - STOP_LOSS_PCT):
            return ("STOP_LOSS", self.entry_price * (1 - STOP_LOSS_PCT))

        # Take profit: 5% above entry
        if row['High'] >= self.entry_price * (1 + TAKE_PROFIT_PCT):
            return ("TAKE_PROFIT", self.entry_price * (1 + TAKE_PROFIT_PCT))

        # Time stop: exit if in trade for 10+ days
        if trade_day_count >= TIME_STOP_DAYS:
            return ("TIME_STOP", row['Close'])

        return None

    def calculate_position_size(self, price):
        """Position size based on risk management."""
        # Risk 3% per trade
        risk_amount = self.capital * RISK_PCT_PER_TRADE
        stop_distance = price * STOP_LOSS_PCT
        position_size = int(risk_amount / stop_distance)
        return position_size

    def backtest(self, df):
        """Run backtest on historical data."""
        df = self.calculate_indicators(df.copy())
        df = df.dropna()

        trade_day_count = 0
        results = []

        for i in range(1, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            date = row.name if isinstance(row.name, str) else row.name.strftime('%Y-%m-%d')

            # Check for exit condition
            if self.position is not None:
                trade_day_count += 1
                exit_signal = self.check_exit(row, trade_day_count)

                if exit_signal:
                    exit_type, exit_price = exit_signal
                    pnl = (exit_price - self.entry_price) * self.position
                    pnl_pct = ((exit_price - self.entry_price) / self.entry_price) * 100

                    trade_record = {
                        'entry_date': self.entry_date,
                        'exit_date': date,
                        'entry_price': self.entry_price,
                        'exit_price': exit_price,
                        'exit_type': exit_type,
                        'shares': self.position,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'days_held': trade_day_count
                    }

                    self.trades.append(trade_record)
                    self.capital += pnl
                    results.append(trade_record)

                    # Clear position
                    self.position = None
                    self.entry_price = None
                    self.entry_date = None
                    self.stop_loss = None
                    self.take_profit = None
                    trade_day_count = 0

            # Check for entry conditions (only if not in position)
            if self.position is None:
                # Rule 1: Trend filter must pass
                if not self.check_trend_filter(row):
                    continue

                entry_signal = None
                entry_price = None

                # Rule 2: Breakout entry (preferred)
                if self.check_breakout_entry(row, prev_row):
                    entry_signal = "BREAKOUT"
                    entry_price = row['Close']

                # Rule 3: Pullback entry (lower risk)
                elif self.check_pullback_entry(row):
                    entry_signal = "PULLBACK"
                    entry_price = row['MA_50']  # Enter at MA50 level

                if entry_signal and entry_price:
                    self.position = self.calculate_position_size(entry_price)
                    self.entry_price = entry_price
                    self.entry_date = date
                    self.stop_loss = entry_price * (1 - STOP_LOSS_PCT)
                    self.take_profit = entry_price * (1 + TAKE_PROFIT_PCT)

        return pd.DataFrame(results)


def get_strategy_signals(df):
    """Get today's signals without backtesting. Used for live alerts."""
    strategy = MarketWizardsStrategy()
    df = strategy.calculate_indicators(df.copy())

    if len(df) < 2:
        return None

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    signal = {
        'date': latest.name if isinstance(latest.name, str) else latest.name.strftime('%Y-%m-%d'),
        'price': latest['Close'],
        'entry_signal': None,
        'ma_200': latest['MA_200'],
        'ma_50': latest['MA_50'],
        'trend_filter_pass': strategy.check_trend_filter(latest),
        'breakout_entry': strategy.check_breakout_entry(latest, prev),
        'pullback_entry': strategy.check_pullback_entry(latest),
    }

    if signal['trend_filter_pass']:
        if signal['breakout_entry']:
            signal['entry_signal'] = 'BREAKOUT'
            signal['entry_price'] = latest['Close']
            signal['stop_loss'] = latest['Close'] * (1 - STOP_LOSS_PCT)
            signal['take_profit'] = latest['Close'] * (1 + TAKE_PROFIT_PCT)
        elif signal['pullback_entry']:
            signal['entry_signal'] = 'PULLBACK'
            signal['entry_price'] = latest['MA_50']
            signal['stop_loss'] = latest['MA_50'] * (1 - STOP_LOSS_PCT)
            signal['take_profit'] = latest['MA_50'] * (1 + TAKE_PROFIT_PCT)

    return signal
