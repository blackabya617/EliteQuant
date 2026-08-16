"""Alert delivery: Telegram, email, and a local JSON log."""

import json
import os
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime
from email.mime.text import MIMEText

import config


def _format(target, actions=None):
    lines = [
        "MARKET WIZARDS - monthly rotation",
        f"as of {target['as_of']}",
        "",
        "Target portfolio:",
    ]
    if target["holdings"]:
        lines += [f"  {s}  {w:.0%}" for s, w in target["holdings"].items()]
    else:
        lines.append("  ALL CASH - nothing above its 10-month average")
    if target["cash_weight"] > 0.001:
        lines.append(f"  CASH  {target['cash_weight']:.0%}")

    if actions:
        lines += ["", "Rebalance:"]
        for a in actions:
            if a["action"] == "close":
                lines.append(f"  CLOSE {a['symbol']}")
            else:
                lines.append(f"  {a['action'].upper()} {a['symbol']} ${a['notional']:,.0f}")
    return "\n".join(lines)


def send_telegram(text):
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return False, "telegram not configured"
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": config.TELEGRAM_CHAT_ID, "text": text}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15) as r:
            return r.status == 200, f"HTTP {r.status}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def send_email(text, subject="Market Wizards rotation signal"):
    if not (config.EMAIL_SENDER and config.EMAIL_PASSWORD and config.EMAIL_RECIPIENT):
        return False, "email not configured"
    msg = MIMEText(text)
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_SENDER
    msg["To"] = config.EMAIL_RECIPIENT
    try:
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT, timeout=20) as s:
            s.starttls()
            s.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
            s.send_message(msg)
        return True, "sent"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def log(target, actions=None):
    os.makedirs(config.STATE_DIR, exist_ok=True)
    path = os.path.join(config.STATE_DIR, "alerts.jsonl")
    with open(path, "a") as fh:
        fh.write(json.dumps({"ts": datetime.now().isoformat(),
                             "target": target, "actions": actions}) + "\n")
    return path


def dispatch(target, actions=None):
    """Send the signal everywhere that is configured. Returns a status dict."""
    text = _format(target, actions)
    tg_ok, tg_msg = send_telegram(text)
    em_ok, em_msg = send_email(text)
    return {"telegram": (tg_ok, tg_msg), "email": (em_ok, em_msg), "log": log(target, actions)}
