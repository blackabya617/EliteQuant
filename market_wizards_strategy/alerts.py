"""
Alert System for Market Wizards Strategy
Sends alerts via Telegram, Email, and displays on dashboard.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import json
from datetime import datetime
from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT, SMTP_SERVER, SMTP_PORT
)


class AlertSystem:
    def __init__(self):
        self.alerts_log = []

    def send_telegram_alert(self, signal):
        """Send alert via Telegram."""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print("⚠️  Telegram not configured")
            return False

        if not signal.get('entry_signal'):
            return False

        message = self._format_message(signal)

        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }

            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                print(f"✅ Telegram alert sent: {signal['entry_signal']}")
                return True
            else:
                print(f"❌ Telegram error: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Telegram error: {e}")
            return False

    def send_email_alert(self, signal):
        """Send alert via Email."""
        if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECIPIENT:
            print("⚠️  Email not configured")
            return False

        if not signal.get('entry_signal'):
            return False

        try:
            subject = f"🚨 Market Wizards Alert: {signal['entry_signal']}"
            message = self._format_message(signal, html=True)

            msg = MIMEMultipart()
            msg['From'] = EMAIL_SENDER
            msg['To'] = EMAIL_RECIPIENT
            msg['Subject'] = subject
            msg.attach(MIMEText(message, 'html'))

            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
                server.starttls()
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.send_message(msg)

            print(f"✅ Email alert sent: {signal['entry_signal']}")
            return True

        except Exception as e:
            print(f"❌ Email error: {e}")
            return False

    def log_signal(self, signal):
        """Log signal to file for dashboard."""
        self.alerts_log.append({
            'timestamp': datetime.now().isoformat(),
            'signal': signal
        })

        # Save to JSON file
        try:
            with open('/tmp/market_wizards_alerts.json', 'w') as f:
                json.dump(self.alerts_log[-100:], f)  # Keep last 100 alerts
        except Exception as e:
            print(f"Warning: Could not save alert log: {e}")

    def _format_message(self, signal, html=False):
        """Format alert message."""
        if not signal.get('entry_signal'):
            return ""

        entry_type = signal['entry_signal']
        price = signal.get('entry_price', 0)
        stop = signal.get('stop_loss', 0)
        target = signal.get('take_profit', 0)
        ma200 = signal.get('ma_200', 0)
        ma50 = signal.get('ma_50', 0)

        if html:
            msg = f"""
            <b>🚀 Market Wizards Trade Alert</b><br>
            <b>Signal:</b> {entry_type}<br>
            <b>Symbol:</b> SPY<br>
            <b>Date:</b> {signal.get('date', 'N/A')}<br>
            <b>Entry Price:</b> ${price:.2f}<br>
            <b>Stop Loss:</b> ${stop:.2f} ({abs((stop/price - 1) * 100):.2f}%)<br>
            <b>Take Profit:</b> ${target:.2f} ({(target/price - 1) * 100:.2f}%)<br>
            <br>
            <b>Technical Levels:</b><br>
            MA200: ${ma200:.2f}<br>
            MA50: ${ma50:.2f}<br>
            Current Price: ${signal.get('price', 0):.2f}<br>
            <br>
            <i>Risk/Reward Ratio: 1:{((target - price)/(price - stop)):.2f}</i>
            """
        else:
            msg = f"""
🚀 MARKET WIZARDS TRADE ALERT

Signal: {entry_type}
Symbol: SPY
Date: {signal.get('date', 'N/A')}
Entry Price: ${price:.2f}
Stop Loss: ${stop:.2f} ({abs((stop/price - 1) * 100):.2f}%)
Take Profit: ${target:.2f} ({(target/price - 1) * 100:.2f}%)

Technical Levels:
MA200: ${ma200:.2f}
MA50: ${ma50:.2f}
Current Price: ${signal.get('price', 0):.2f}

Risk/Reward Ratio: 1:{((target - price)/(price - stop)):.2f}
            """

        return msg.strip()

    def send_all_alerts(self, signal):
        """Send alert through all configured channels."""
        if not signal.get('entry_signal'):
            return

        print(f"\n📢 Sending alerts for {signal['entry_signal']} signal...")

        self.send_telegram_alert(signal)
        self.send_email_alert(signal)
        self.log_signal(signal)

        print(f"✅ Alert sent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
