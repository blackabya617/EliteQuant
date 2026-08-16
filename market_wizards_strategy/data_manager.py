"""
Data Manager - Handles fetching and caching historical data.
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import pickle
from config import SYMBOL, LOOKBACK_DAYS


class DataManager:
    def __init__(self, cache_dir="/tmp/market_wizards_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_file = os.path.join(cache_dir, f"{SYMBOL}_data.pkl")

    def fetch_data(self, symbol=SYMBOL, days_back=LOOKBACK_DAYS, force_refresh=False):
        """Fetch historical data with caching."""
        if not force_refresh and os.path.exists(self.cache_file):
            try:
                df = pd.read_pickle(self.cache_file)
                days_in_cache = (datetime.now() - df.index[-1]).days
                if days_in_cache < 1:  # Cache is fresh (less than 1 day old)
                    print(f"✅ Loaded {len(df)} candles from cache")
                    return df
            except:
                pass

        print(f"Fetching {symbol} data from Yahoo Finance...")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        try:
            # Retry logic for rate limiting
            df = None
            retries = 3
            for attempt in range(retries):
                try:
                    df = yf.download(symbol, start=start_date, end=end_date, progress=False)
                    break
                except Exception as e:
                    if attempt < retries - 1:
                        print(f"  Attempt {attempt+1} failed, retrying in 5s...")
                        import time
                        time.sleep(5)
                    else:
                        raise

            if df is None or len(df) == 0:
                raise Exception("No data returned")

            # Cache the data
            df.to_pickle(self.cache_file)
            print(f"✅ Fetched {len(df)} candles and cached")
            return df

        except Exception as e:
            print(f"❌ Failed to fetch data: {e}")
            # Try to return cached data if available
            if os.path.exists(self.cache_file):
                print("Using cached data (may be stale)")
                return pd.read_pickle(self.cache_file)
            return None

    def create_synthetic_data(self, days=2000):
        """Create synthetic OHLCV data for testing."""
        import numpy as np

        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
        prices = [420]  # Start at SPY ~420

        for _ in range(days - 1):
            change = np.random.normal(0.0005, 0.015)  # ~0.05% mean, 1.5% std dev
            prices.append(prices[-1] * (1 + change))

        data = {
            'Open': prices,
            'High': [p * (1 + abs(np.random.normal(0, 0.005))) for p in prices],
            'Low': [p * (1 - abs(np.random.normal(0, 0.005))) for p in prices],
            'Close': prices,
            'Volume': np.random.randint(50000000, 150000000, days),
            'Adj Close': prices
        }

        df = pd.DataFrame(data, index=dates)
        return df
