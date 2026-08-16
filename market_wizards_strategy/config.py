import os
from dotenv import load_dotenv

load_dotenv()

# Trading Strategy Parameters
SYMBOL = "SPY"
LOOKBACK_DAYS = 2000  # 8+ years of data for backtesting

# Technical Analysis Parameters
MA_200_PERIOD = 200  # Trend filter
MA_50_PERIOD = 50    # Pullback entry
BREAKOUT_PERIOD = 20 # Breakout entry (20-day high)

# Entry Conditions
BREAKOUT_VOLUME_MULTIPLIER = 1.2  # Volume must be 20% above average
PULLBACK_TOLERANCE = 0.02  # Allow entry 2% above 50-day MA

# Exit Conditions
STOP_LOSS_PCT = 0.02  # 2% stop loss
TAKE_PROFIT_PCT = 0.05  # 5% take profit target
TIME_STOP_DAYS = 10   # Exit if in trade for 10+ days

# Position Sizing
RISK_PCT_PER_TRADE = 0.03  # Risk 3% per trade (aggressive for fun account)
INITIAL_CAPITAL = 10000

# Telegram Alert Settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Email Alert Settings
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "")

# Backtest Parameters
BACKTEST_START_DATE = None  # None = auto (8+ years ago)
BACKTEST_END_DATE = None    # None = today
BACKTEST_COMMISSIONS = 0.001  # 0.1% commission per trade
