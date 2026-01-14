from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional
from urllib.request import Request, urlopen

import pandas as pd

from bot.adapters.base import BrokerAdapter
from bot.core.types import AccountSummary, Order, OrderAck, OrderRequest, Position, SymbolRules


class CoinbaseAdapter(BrokerAdapter):
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None) -> None:
        self.api_key = api_key
        self.api_secret = api_secret

    def get_account_summary(self) -> AccountSummary:
        return AccountSummary(cash=0.0, equity=0.0, base_currency="USD")

    def get_positions(self) -> List[Position]:
        return []

    def get_open_orders(self) -> List[Order]:
        return []

    def get_latest_price(self, symbol: str) -> float:
        url = f"https://api.coinbase.com/api/v3/brokerage/products/{symbol}/ticker"
        with urlopen(Request(url, headers={"User-Agent": "multi-trading-bot"})) as response:
            data = json.loads(response.read().decode("utf-8"))
        price = data.get("price")
        if price is None:
            raise ValueError("Missing price in Coinbase response")
        return float(price)

    def get_candles(self, symbol: str, timeframe: str, lookback_bars: int) -> pd.DataFrame:
        granularity = _timeframe_to_seconds(timeframe)
        url = f"https://api.coinbase.com/api/v3/brokerage/products/{symbol}/candles?granularity={granularity}"
        with urlopen(Request(url, headers={"User-Agent": "multi-trading-bot"})) as response:
            data = json.loads(response.read().decode("utf-8"))
        candles = pd.DataFrame(data.get("candles", data))
        if candles.empty:
            return candles
        if "start" in candles.columns:
            candles = candles.rename(
                columns={
                    "start": "timestamp",
                    "low": "low",
                    "high": "high",
                    "open": "open",
                    "close": "close",
                    "volume": "volume",
                }
            )
        for column in ["open", "high", "low", "close", "volume"]:
            if column in candles.columns:
                candles[column] = pd.to_numeric(candles[column], errors="coerce")
        candles["timestamp"] = pd.to_datetime(candles["timestamp"], unit="s", utc=True)
        candles = candles.sort_values("timestamp")
        candles = candles.set_index("timestamp")
        return candles.iloc[-lookback_bars:]

    def place_order(self, order_request: OrderRequest) -> OrderAck:
        raise NotImplementedError("Coinbase trading endpoints are not implemented in MVP.")

    def cancel_order(self, order_id: str) -> bool:
        return False

    def get_spread_bps(self, symbol: str) -> float:
        url = f"https://api.coinbase.com/api/v3/brokerage/products/{symbol}/ticker"
        with urlopen(Request(url, headers={"User-Agent": "multi-trading-bot"})) as response:
            data = json.loads(response.read().decode("utf-8"))
        bid = float(data.get("bid", 0) or 0)
        ask = float(data.get("ask", 0) or 0)
        mid = (bid + ask) / 2 if (bid and ask) else None
        if not mid or mid == 0:
            return 0.0
        return ((ask - bid) / mid) * 10000

    def is_market_open(self, symbol: str, now_utc: datetime) -> bool:
        return True

    def symbol_rules(self, symbol: str) -> SymbolRules:
        return SymbolRules(min_qty=0.0001, qty_step=0.0001, tick_size=0.01, min_notional=5.0)


def _timeframe_to_seconds(timeframe: str) -> int:
    mapping = {"1m": 60, "5m": 300, "15m": 900}
    return mapping.get(timeframe, 300)
