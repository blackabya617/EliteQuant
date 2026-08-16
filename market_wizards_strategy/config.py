"""Configuration. Strategy parameters live in the dataclasses they belong to
(engine.Params, rotation.RotationParams); this file holds only wiring."""

import os

from dotenv import load_dotenv

load_dotenv()

# --- what we trade ---------------------------------------------------------
BENCHMARK = "SPY"

# --- alerts ----------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT", "")

# --- paper broker ----------------------------------------------------------
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")

# Orders are only ever sent when this is explicitly true; the default is to
# print what would be traded and stop.
EXECUTE_PAPER_TRADES = os.getenv("EXECUTE_PAPER_TRADES", "false").lower() == "true"

STATE_DIR = os.getenv("MW_STATE_DIR", os.path.expanduser("~/.market_wizards"))
