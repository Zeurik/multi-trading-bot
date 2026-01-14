from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List

import pandas as pd

from bot.adapters.base import BrokerAdapter
from bot.core.types import AccountSummary, Order, OrderAck, OrderRequest, Position, SymbolRules


@dataclass
class BacktestAdapter(BrokerAdapter):
    candles_by_symbol: Dict[str, pd.DataFrame]
    current_index: int = 0
    cash: float = 100000.0
    positions: Dict[str, Position] = None
    realized_pnls: List[float] = None
    allow_short_symbols: Dict[str, bool] = None

    def __post_init__(self) -> None:
        self.positions = {} if self.positions is None else self.positions
        self.realized_pnls = [] if self.realized_pnls is None else self.realized_pnls
        self.allow_short_symbols = (
            {} if self.allow_short_symbols is None else self.allow_short_symbols
        )

    def set_index(self, idx: int) -> None:
        self.current_index = idx

    def get_account_summary(self) -> AccountSummary:
        equity = self.cash + sum(
            position.qty * self.get_latest_price(position.symbol) for position in self.positions.values()
        )
        return AccountSummary(cash=self.cash, equity=equity, base_currency="USD")

    def get_positions(self) -> List[Position]:
        return list(self.positions.values())

    def get_open_orders(self) -> List[Order]:
        return []

    def get_latest_price(self, symbol: str) -> float:
        return float(self._slice(symbol).iloc[-1]["close"])

    def get_spread_bps(self, symbol: str) -> float:
        return 0.0

    def get_candles(self, symbol: str, timeframe: str, lookback_bars: int) -> pd.DataFrame:
        df = self._slice(symbol)
        return df.iloc[-lookback_bars:]

    def place_order(self, order_request: OrderRequest) -> OrderAck:
        price = self.get_latest_price(order_request.symbol)
        cost = price * order_request.quantity
        position = self.positions.get(order_request.symbol)
        signed_qty = order_request.quantity if order_request.side.value == "BUY" else -order_request.quantity
        current_qty = position.qty if position else 0.0
        new_qty = current_qty + signed_qty
        allow_short = self.allow_short_symbols.get(order_request.symbol, False)
        realized_pnl = None

        if current_qty == 0 and signed_qty < 0 and not allow_short:
            return OrderAck(order_id=f"bt-{order_request.client_order_id}", status="REJECTED")

        if current_qty > 0 and new_qty < 0 and not allow_short:
            return OrderAck(order_id=f"bt-{order_request.client_order_id}", status="REJECTED")

        if current_qty < 0 and new_qty > 0 and not allow_short:
            return OrderAck(order_id=f"bt-{order_request.client_order_id}", status="REJECTED")

        if order_request.side.value == "BUY":
            self.cash -= cost
        else:
            self.cash += cost

        if position:
            if current_qty > 0 and signed_qty < 0:
                closed_qty = min(abs(signed_qty), current_qty)
                realized_pnl = (price - position.avg_price) * closed_qty
            elif current_qty < 0 and signed_qty > 0:
                closed_qty = min(signed_qty, abs(current_qty))
                realized_pnl = (position.avg_price - price) * closed_qty
        if realized_pnl is not None:
            self.realized_pnls.append(realized_pnl)

        if new_qty == 0:
            self.positions.pop(order_request.symbol, None)
        else:
            avg_price = position.avg_price if position else price
            if position and (current_qty == 0 or (current_qty > 0) != (new_qty > 0)):
                avg_price = price
            if position and (current_qty > 0 and signed_qty > 0) or (current_qty < 0 and signed_qty < 0):
                avg_price = ((abs(current_qty) * position.avg_price) + cost) / abs(new_qty)
            self.positions[order_request.symbol] = Position(
                symbol=order_request.symbol,
                qty=new_qty,
                avg_price=avg_price,
                unrealized_pnl=0.0,
            )
        return OrderAck(
            order_id=f"bt-{order_request.client_order_id}",
            status="FILLED",
            filled_qty=order_request.quantity,
            avg_fill_price=price,
            fee=0.0,
            realized_pnl=realized_pnl,
        )

    def cancel_order(self, order_id: str) -> bool:
        return False

    def is_market_open(self, symbol: str, now_utc: datetime) -> bool:
        return True

    def symbol_rules(self, symbol: str) -> SymbolRules:
        return SymbolRules(min_qty=0.0001, qty_step=0.0001, tick_size=0.01, min_notional=1.0)

    def _slice(self, symbol: str) -> pd.DataFrame:
        df = self.candles_by_symbol[symbol]
        return df.iloc[: self.current_index + 1]
