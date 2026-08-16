"""
Alpaca paper-trading adapter.

Alpaca's paper endpoint is free, needs no funding, and takes the same API as
live trading, so the only thing separating paper from real money is the base
URL and the key pair. This module deliberately refuses to talk to the live
endpoint: flipping that switch should be a human decision, not a config typo.

Set in .env:
    ALPACA_API_KEY=...
    ALPACA_API_SECRET=...

Get keys at https://app.alpaca.markets/paper/dashboard/overview (free signup).
"""

import json
import os
import urllib.error
import urllib.request

PAPER_BASE = "https://paper-api.alpaca.markets"


class BrokerError(RuntimeError):
    pass


class AlpacaPaper:
    def __init__(self, key=None, secret=None, base=PAPER_BASE):
        self.key = key or os.getenv("ALPACA_API_KEY", "")
        self.secret = secret or os.getenv("ALPACA_API_SECRET", "")
        if "paper-api" not in base:
            raise BrokerError(
                "This adapter only talks to Alpaca's paper endpoint. "
                "Point it at live trading deliberately, not by editing a default."
            )
        self.base = base.rstrip("/")

    @property
    def configured(self):
        return bool(self.key and self.secret)

    def _request(self, method, path, payload=None):
        if not self.configured:
            raise BrokerError("ALPACA_API_KEY / ALPACA_API_SECRET not set in environment")

        req = urllib.request.Request(
            f"{self.base}{path}",
            method=method,
            data=json.dumps(payload).encode() if payload else None,
            headers={
                "APCA-API-KEY-ID": self.key,
                "APCA-API-SECRET-KEY": self.secret,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            raise BrokerError(f"{method} {path} -> HTTP {exc.code}: {exc.read().decode()[:300]}")
        except urllib.error.URLError as exc:
            raise BrokerError(f"{method} {path} -> {exc.reason}")

    # ---- read -------------------------------------------------------------
    def account(self):
        return self._request("GET", "/v2/account")

    def positions(self):
        return self._request("GET", "/v2/positions")

    def clock(self):
        return self._request("GET", "/v2/clock")

    def equity(self):
        return float(self.account()["equity"])

    def current_weights(self):
        """Current portfolio weights by symbol, as a fraction of equity."""
        eq = self.equity()
        if eq <= 0:
            return {}
        return {p["symbol"]: float(p["market_value"]) / eq for p in self.positions()}

    # ---- write ------------------------------------------------------------
    def submit(self, symbol, notional=None, qty=None, side="buy"):
        order = {"symbol": symbol, "side": side, "type": "market", "time_in_force": "day"}
        if notional is not None:
            order["notional"] = round(float(notional), 2)
        elif qty is not None:
            order["qty"] = str(qty)
        else:
            raise BrokerError("submit() needs either notional or qty")
        return self._request("POST", "/v2/orders", order)

    def close_position(self, symbol):
        return self._request("DELETE", f"/v2/positions/{symbol}")

    def rebalance(self, target_weights, tolerance=0.02, dry_run=True):
        """Move the paper account toward `target_weights` ({symbol: fraction}).

        Positions not in the target are closed. Positions whose weight is
        already within `tolerance` of target are left alone, so a monthly
        rebalance does not churn on rounding.

        Returns the list of actions; with dry_run=True nothing is sent.
        """
        equity = self.equity()
        current = self.current_weights()
        actions = []

        for symbol in current:
            if symbol not in target_weights:
                actions.append({"action": "close", "symbol": symbol,
                                "from_weight": round(current[symbol], 4)})

        for symbol, target in target_weights.items():
            drift = target - current.get(symbol, 0.0)
            if abs(drift) < tolerance:
                continue
            actions.append({
                "action": "buy" if drift > 0 else "sell",
                "symbol": symbol,
                "notional": round(abs(drift) * equity, 2),
                "from_weight": round(current.get(symbol, 0.0), 4),
                "to_weight": round(target, 4),
            })

        if dry_run:
            return actions

        for act in actions:
            if act["action"] == "close":
                self.close_position(act["symbol"])
            else:
                self.submit(act["symbol"], notional=act["notional"], side=act["action"])
        return actions
