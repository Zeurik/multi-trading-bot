from __future__ import annotations

from datetime import datetime
from typing import Dict, List

import pandas as pd

from bot.adapters.base import BrokerAdapter
from bot.core.types import AccountSummary, Order, OrderAck, OrderRequest, Position, SymbolRules


class MultiVenueAdapter(BrokerAdapter):
    def __init__(self, symbol_to_adapter: Dict[str, BrokerAdapter]) -> None:
        self.symbol_to_adapter = symbol_to_adapter

    def _adapter_for(self, symbol: str) -> BrokerAdapter:
        if symbol not in self.symbol_to_adapter:
            raise KeyError(f"No adapter for symbol {symbol}")
        return self.symbol_to_adapter[symbol]

    def get_account_summary(self) -> AccountSummary:
        summaries = [adapter.get_account_summary() for adapter in set(self.symbol_to_adapter.values())]
        cash = sum(summary.cash for summary in summaries)
        equity = sum(summary.equity for summary in summaries)
        base_currency = summaries[0].base_currency if summaries else "USD"
        return AccountSummary(cash=cash, equity=equity, base_currency=base_currency)

    def get_positions(self) -> List[Position]:
        positions: List[Position] = []
        for adapter in set(self.symbol_to_adapter.values()):
            positions.extend(adapter.get_positions())
        return positions

    def get_open_orders(self) -> List[Order]:
        orders: List[Order] = []
        for adapter in set(self.symbol_to_adapter.values()):
            orders.extend(adapter.get_open_orders())
        return orders

    def get_latest_price(self, symbol: str) -> float:
        return self._adapter_for(symbol).get_latest_price(symbol)

    def get_spread_bps(self, symbol: str) -> float:
        return self._adapter_for(symbol).get_spread_bps(symbol)

    def get_candles(self, symbol: str, timeframe: str, lookback_bars: int) -> pd.DataFrame:
        return self._adapter_for(symbol).get_candles(symbol, timeframe, lookback_bars)

    def place_order(self, order_request: OrderRequest) -> OrderAck:
        return self._adapter_for(order_request.symbol).place_order(order_request)

    def cancel_order(self, order_id: str) -> bool:
        for adapter in set(self.symbol_to_adapter.values()):
            if adapter.cancel_order(order_id):
                return True
        return False

    def is_market_open(self, symbol: str, now_utc: datetime) -> bool:
        return self._adapter_for(symbol).is_market_open(symbol, now_utc)

    def symbol_rules(self, symbol: str) -> SymbolRules:
        return self._adapter_for(symbol).symbol_rules(symbol)
