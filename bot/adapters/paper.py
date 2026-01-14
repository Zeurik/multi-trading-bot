from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List
from uuid import uuid4

import pandas as pd

from bot.adapters.base import BrokerAdapter
from bot.core.types import (
    AccountSummary,
    Order,
    OrderAck,
    OrderRequest,
    OrderSide,
    Position,
    SymbolRules,
)


@dataclass
class PaperConfig:
    starting_cash: float = 100000.0
    slippage_bps: float = 1.0
    fee_bps: float = 0.5
    allow_short: bool = False


class PaperAdapter(BrokerAdapter):
    def __init__(self, underlying: BrokerAdapter, config: PaperConfig) -> None:
        self.underlying = underlying
        self.config = config
        self.cash = config.starting_cash
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}

    def get_account_summary(self) -> AccountSummary:
        equity = self.cash + sum(
            position.qty * self.get_latest_price(position.symbol) for position in self.positions.values()
        )
        return AccountSummary(cash=self.cash, equity=equity, base_currency="USD")

    def get_positions(self) -> List[Position]:
        return list(self.positions.values())

    def get_open_orders(self) -> List[Order]:
        return [order for order in self.orders.values() if order.status == "OPEN"]

    def get_latest_price(self, symbol: str) -> float:
        return self.underlying.get_latest_price(symbol)

    def get_spread_bps(self, symbol: str) -> float:
        return self.underlying.get_spread_bps(symbol)

    def get_candles(self, symbol: str, timeframe: str, lookback_bars: int) -> pd.DataFrame:
        return self.underlying.get_candles(symbol, timeframe, lookback_bars)

    def place_order(self, order_request: OrderRequest) -> OrderAck:
        last_price = self.get_latest_price(order_request.symbol)
        slippage = self.config.slippage_bps / 10000
        fill_price = last_price * (1 + slippage if order_request.side == OrderSide.BUY else 1 - slippage)
        fee = fill_price * order_request.quantity * self.config.fee_bps / 10000
        cost = fill_price * order_request.quantity
        position = self.positions.get(order_request.symbol)
        signed_qty = order_request.quantity if order_request.side == OrderSide.BUY else -order_request.quantity
        current_qty = position.qty if position else 0.0
        new_qty = current_qty + signed_qty
        realized_pnl = None

        if current_qty == 0 and signed_qty < 0 and not self.config.allow_short:
            return OrderAck(order_id=str(uuid4()), status="REJECTED", fee=0.0)

        if current_qty > 0 and new_qty < 0 and not self.config.allow_short:
            return OrderAck(order_id=str(uuid4()), status="REJECTED", fee=0.0)

        if current_qty < 0 and new_qty > 0 and not self.config.allow_short:
            return OrderAck(order_id=str(uuid4()), status="REJECTED", fee=0.0)

        if order_request.side == OrderSide.BUY:
            self.cash -= cost + fee
        else:
            self.cash += cost - fee

        if position:
            if current_qty > 0 and signed_qty < 0:
                closed_qty = min(abs(signed_qty), current_qty)
                realized_pnl = (fill_price - position.avg_price) * closed_qty
            elif current_qty < 0 and signed_qty > 0:
                closed_qty = min(signed_qty, abs(current_qty))
                realized_pnl = (position.avg_price - fill_price) * closed_qty

        if new_qty == 0:
            self.positions.pop(order_request.symbol, None)
        else:
            avg_price = position.avg_price if position else fill_price
            if position and (current_qty == 0 or (current_qty > 0) != (new_qty > 0)):
                avg_price = fill_price
            if position and (current_qty > 0 and signed_qty > 0) or (current_qty < 0 and signed_qty < 0):
                avg_price = ((abs(current_qty) * position.avg_price) + cost) / abs(new_qty)
            self.positions[order_request.symbol] = Position(
                symbol=order_request.symbol,
                qty=new_qty,
                avg_price=avg_price,
                unrealized_pnl=0.0,
            )

        order_id = str(uuid4())
        order = Order(
            id=order_id,
            symbol=order_request.symbol,
            side=order_request.side,
            qty=order_request.quantity,
            filled_qty=order_request.quantity,
            status="FILLED",
            limit_price=order_request.limit_price,
            client_order_id=order_request.client_order_id,
        )
        self.orders[order_id] = order
        return OrderAck(
            order_id=order_id,
            status="FILLED",
            filled_qty=order_request.quantity,
            avg_fill_price=fill_price,
            fee=fee,
            realized_pnl=realized_pnl,
        )

    def cancel_order(self, order_id: str) -> bool:
        order = self.orders.get(order_id)
        if not order:
            return False
        order.status = "CANCELED"
        return True

    def is_market_open(self, symbol: str, now_utc: datetime) -> bool:
        return self.underlying.is_market_open(symbol, now_utc)

    def symbol_rules(self, symbol: str) -> SymbolRules:
        return self.underlying.symbol_rules(symbol)
