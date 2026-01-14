from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

import pandas as pd

from bot.core.types import AccountSummary, Order, OrderAck, OrderRequest, Position, SymbolRules


class BrokerAdapter(ABC):
    @abstractmethod
    def get_account_summary(self) -> AccountSummary:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> List[Position]:
        raise NotImplementedError

    @abstractmethod
    def get_open_orders(self) -> List[Order]:
        raise NotImplementedError

    @abstractmethod
    def get_latest_price(self, symbol: str) -> float:
        raise NotImplementedError

    @abstractmethod
    def get_spread_bps(self, symbol: str) -> float:
        raise NotImplementedError

    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str, lookback_bars: int) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order_request: OrderRequest) -> OrderAck:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_market_open(self, symbol: str, now_utc) -> bool:
        raise NotImplementedError

    @abstractmethod
    def symbol_rules(self, symbol: str) -> SymbolRules:
        raise NotImplementedError
