# Market Wizards Trading Strategy

A **high-risk, high-reward swing trading system** based on principles from Jack Schwager's "Market Wizards" interviews with elite traders.

## Strategy Overview

This system combines three powerful strategies from the Market Wizards playbook:

### 1. **Trend Following** (Paul Tudor Jones)
- Price must be **above 200-day moving average** (uptrend confirmation)
- Filters out trades against the main trend
- Defense-first approach: "Don't lose money"

### 2. **Breakout Trading** (Richard Dennis / Turtle System)
- Buy when price breaks above **20-day high** with volume confirmation
- Captures momentum at trend start
- Primary entry signal

### 3. **Pullback Trading** (Risk Management)
- Buy dips to **50-day MA** while trend is up
- Lower-risk re-entry point
- Better risk/reward ratio than breakouts

## Exit Rules

**All trades follow strict risk management:**
- **Stop Loss:** 2% below entry (capital preservation)
- **Take Profit:** 5% above entry (ride the winners)
- **Time Stop:** Exit after 10 days (avoid dead money)
- **Position Sizing:** Risk 3% per trade (aggressive, adjust as needed)

## Key Metrics (Backtesting)

The strategy will show:
- Win Rate (target: 35-45%)
- Profit Factor (target: 1.5+)
- Average Win vs Average Loss
- Comparison to S&P 500 Buy & Hold

## Project Structure

```
market_wizards_strategy/
├── config.py              # Strategy parameters & alert settings
├── strategy.py            # Core trading logic
├── backtester.py          # Historical performance testing
├── data_manager.py        # Data fetching & caching
├── alerts.py              # Telegram + Email + Dashboard alerts
├── main.py                # Daily scanner & alert trigger
├── requirements.txt       # Python dependencies
├── .env.example           # Template for API credentials
└── README.md             # This file
```

## Installation

### 1. Clone & Setup

```bash
cd market_wizards_strategy
pip install -r requirements.txt
```

### 2. Configure Alerts

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

#### Telegram Setup
1. Create a bot with @BotFather on Telegram
2. Get your Chat ID from @userinfobot
3. Add to `.env`:
```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

#### Email Setup (Gmail)
1. Enable 2-Factor Authentication on Gmail
2. Generate an [App Password](https://support.google.com/accounts/answer/185833)
3. Add to `.env`:
```
EMAIL_SENDER=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECIPIENT=recipient@example.com
```

## Usage

### Run Backtest

Test strategy performance on historical data:

```bash
python backtester.py
```

**Output:**
- Total trades, win rate, profit factor
- Total P&L vs Buy & Hold comparison
- Individual trade breakdown

### Run Daily Scanner

Check for today's trading signals and send alerts:

```bash
python main.py
```

**Alerts Sent Via:**
- 🔔 Telegram (real-time notifications on phone)
- 📧 Email (confirmation)
- 📊 Dashboard (local JSON file for tracking)

### Automate Daily Scans

Run every day at 4 PM (market close):

#### Linux/Mac (crontab)
```bash
crontab -e
# Add this line:
0 16 * * 1-5 cd /path/to/market_wizards_strategy && python main.py
```

#### Windows (Task Scheduler)
- Create a scheduled task
- Run: `python.exe C:\path\to\main.py`
- Trigger: Daily at 4 PM

## Strategy Parameters

Edit `config.py` to adjust:

```python
# Technical Analysis
MA_200_PERIOD = 200           # Trend filter (larger = slower)
MA_50_PERIOD = 50             # Pullback entry level
BREAKOUT_PERIOD = 20          # Lookback for high/low

# Risk/Reward
STOP_LOSS_PCT = 0.02          # 2% stop loss (aggressive)
TAKE_PROFIT_PCT = 0.05        # 5% profit target
TIME_STOP_DAYS = 10           # Max days in trade

# Position Sizing
RISK_PCT_PER_TRADE = 0.03     # Risk 3% per trade (adjust for risk tolerance)
```

## Backtesting Results

The backtest will show realistic performance metrics. Key things to watch:

- **Win Rate:** 35-50% is normal for trend trading
- **Profit Factor:** 1.2+ means you win more than you lose
- **Avg Win > Avg Loss:** Winners should be 2-3x larger
- **vs Buy & Hold:** May underperform in bull markets, outperform in downturns

## Live Trading Considerations

⚠️ **This is a fun/experimental account strategy**

1. **Start Small:** Use position sizing to match your risk tolerance
2. **Paper Trade First:** Test alerts before risking real money
3. **Monitor:** Check alerts daily, don't go on autopilot
4. **Adjust:** Parameters may need tweaking based on market conditions
5. **Keep Records:** Log all trades for learning

## Troubleshooting

### Telegram alerts not working
- Verify bot token and chat ID in `.env`
- Check internet connection
- Run: `python -c "from alerts import AlertSystem; AlertSystem().send_telegram_alert({'entry_signal': 'TEST'})"`

### Email not sending
- Enable "Less secure app access" if not using App Password
- Check SMTP_PORT (usually 587 for Gmail)
- Verify credentials in `.env`

### No data / API errors
- Strategy falls back to synthetic data for testing
- For live trading, ensure network access to Yahoo Finance
- May need to wait 5+ seconds between API calls

## Market Wizards References

- **Paul Tudor Jones:** Uses 200-day MA as primary trend filter
- **Richard Dennis:** Developed Turtle System (breakout trading)
- **William Eckhardt:** Emphasizes 2% risk per trade max
- **All Wizards:** "Avoid losses > Capture gains"

## Next Steps

1. ✅ Backtest strategy
2. ⏳ Configure Telegram/Email alerts
3. ⏳ Run daily scanner (set up automation)
4. ⏳ Monitor signals for 1-2 weeks
5. ⏳ Adjust parameters based on real performance
6. ⏳ Consider adding to other symbols (individual stocks, other indexes)

---

**Note:** This strategy is based on market wizard principles but not a guarantee of profits. Always do your own research and risk only what you can afford to lose. Past performance ≠ future results.
