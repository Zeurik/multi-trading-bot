from __future__ import annotations

from datetime import datetime
from typing import List

import pandas as pd

from bot.adapters.base import BrokerAdapter
from bot.adapters.data_providers import CSVDataProvider
from bot.core.types import AccountSummary, Order, OrderAck, OrderRequest, Position, SymbolRules


class CSVAdapter(BrokerAdapter):
    def __init__(self, provider: CSVDataProvider) -> None:
        self.provider = provider

    def get_account_summary(self) -> AccountSummary:
        return AccountSummary(cash=0.0, equity=0.0, base_currency="USD")

    def get_positions(self) -> List[Position]:
        return []

    def get_open_orders(self) -> List[Order]:
        return []

    def get_latest_price(self, symbol: str) -> float:
        df = self.provider.load_candles(symbol, "5m", lookback_bars=1)
        return float(df.iloc[-1]["close"])

    def get_spread_bps(self, symbol: str) -> float:
        return 0.0

    def get_candles(self, symbol: str, timeframe: str, lookback_bars: int) -> pd.DataFrame:
        return self.provider.load_candles(symbol, timeframe, lookback_bars)

    def place_order(self, order_request: OrderRequest) -> OrderAck:
        return OrderAck(
            order_id=f"csv-{order_request.client_order_id}",
            status="REJECTED",
            filled_qty=0.0,
            avg_fill_price=None,
            fee=0.0,
        )

    def cancel_order(self, order_id: str) -> bool:
        return False

    def is_market_open(self, symbol: str, now_utc: datetime) -> bool:
        return True

    def symbol_rules(self, symbol: str) -> SymbolRules:
        return SymbolRules(min_qty=1.0, qty_step=1.0, tick_size=0.01, min_notional=1.0)
