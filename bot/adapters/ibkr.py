from __future__ import annotations

from datetime import datetime
from typing import List

import pandas as pd

from bot.adapters.base import BrokerAdapter
from bot.core.clock import MarketClock, MarketClockConfig
from bot.core.types import Venue
from bot.core.types import AccountSummary, Order, OrderAck, OrderRequest, OrderSide, Position, SymbolRules


class IbkrAdapter(BrokerAdapter):
    def __init__(self, clock: MarketClock | None = None) -> None:
        self._connected = False
        self.clock = clock or MarketClock(MarketClockConfig())
        try:
            from ib_insync import IB  # type: ignore

            self._ib = IB()
        except Exception as exc:  # pragma: no cover - environment dependency
            raise ImportError("ib_insync is required for IBKR adapter") from exc

    def connect(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1) -> None:
        self._ib.connect(host, port, clientId=client_id)
        self._connected = True

    def reconnect(self) -> None:
        if not self._connected:
            self.connect()

    def get_account_summary(self) -> AccountSummary:
        self._ensure_connected()
        summary = {item.tag: item.value for item in self._ib.accountSummary()}
        cash = float(summary.get("AvailableFunds", 0.0))
        equity = float(summary.get("NetLiquidation", 0.0))
        base_currency = summary.get("Currency", "USD")
        return AccountSummary(cash=cash, equity=equity, base_currency=base_currency)

    def get_positions(self) -> List[Position]:
        self._ensure_connected()
        positions = []
        for position in self._ib.positions():
            positions.append(
                Position(
                    symbol=position.contract.symbol,
                    qty=float(position.position),
                    avg_price=float(position.avgCost),
                    unrealized_pnl=0.0,
                )
            )
        return positions

    def get_open_orders(self) -> List[Order]:
        self._ensure_connected()
        orders = []
        for trade in self._ib.openTrades():
            orders.append(
                Order(
                    id=str(trade.order.orderId),
                    symbol=trade.contract.symbol,
                    side=OrderSide(trade.order.action),
                    qty=float(trade.order.totalQuantity),
                    filled_qty=float(trade.orderStatus.filled),
                    status=trade.orderStatus.status,
                    limit_price=getattr(trade.order, "lmtPrice", None),
                    client_order_id=trade.order.orderRef,
                )
            )
        return orders

    def get_latest_price(self, symbol: str) -> float:
        self._ensure_connected()
        contract = self._stock_contract(symbol)
        ticker = self._ib.reqMktData(contract, "", False, False)
        self._ib.sleep(1)
        price = ticker.last if ticker.last else ticker.marketPrice()
        self._ib.cancelMktData(contract)
        if price is None:
            raise ValueError(f"Missing price for {symbol}")
        return float(price)

    def get_candles(self, symbol: str, timeframe: str, lookback_bars: int) -> pd.DataFrame:
        self._ensure_connected()
        contract = self._stock_contract(symbol)
        bar_size = _timeframe_to_bar_size(timeframe)
        duration = _bars_to_duration(lookback_bars, timeframe)
        bars = self._ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
        )
        if not bars:
            return pd.DataFrame()
        df = pd.DataFrame(
            [
                {
                    "timestamp": bar.date,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in bars
            ]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.set_index("timestamp")
        return df

    def place_order(self, order_request: OrderRequest) -> OrderAck:
        self._ensure_connected()
        contract = self._stock_contract(order_request.symbol)
        order = self._build_order(order_request)
        trade = self._ib.placeOrder(contract, order)
        status = trade.orderStatus.status if trade.orderStatus else "SUBMITTED"
        filled = float(trade.orderStatus.filled) if trade.orderStatus else 0.0
        avg_fill = float(trade.orderStatus.avgFillPrice) if trade.orderStatus else None
        return OrderAck(
            order_id=str(trade.order.orderId),
            status=status,
            filled_qty=filled,
            avg_fill_price=avg_fill,
            fee=0.0,
        )

    def cancel_order(self, order_id: str) -> bool:
        self._ensure_connected()
        for trade in self._ib.openTrades():
            if str(trade.order.orderId) == order_id:
                self._ib.cancelOrder(trade.order)
                return True
        return False

    def get_spread_bps(self, symbol: str) -> float:
        self._ensure_connected()
        contract = self._stock_contract(symbol)
        ticker = self._ib.reqMktData(contract, "", False, False)
        self._ib.sleep(1)
        bid = ticker.bid or 0.0
        ask = ticker.ask or 0.0
        self._ib.cancelMktData(contract)
        mid = (bid + ask) / 2 if bid and ask else None
        if not mid:
            return 0.0
        return ((ask - bid) / mid) * 10000

    def is_market_open(self, symbol: str, now_utc: datetime) -> bool:
        return self.clock.is_market_open(venue=Venue.IBKR, now_utc=now_utc)

    def symbol_rules(self, symbol: str) -> SymbolRules:
        return SymbolRules(min_qty=1.0, qty_step=1.0, tick_size=0.01, min_notional=1.0)

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError("IBKR adapter is not connected. Call connect() first.")

    def _stock_contract(self, symbol: str):
        from ib_insync import Stock  # type: ignore

        return Stock(symbol, "SMART", "USD")

    def _build_order(self, order_request: OrderRequest):
        from ib_insync import LimitOrder, MarketOrder  # type: ignore

        action = "BUY" if order_request.side.value == "BUY" else "SELL"
        if order_request.order_type.value == "LIMIT":
            order = LimitOrder(action, order_request.quantity, order_request.limit_price)
        else:
            order = MarketOrder(action, order_request.quantity)
        order.orderRef = order_request.client_order_id
        return order


def _timeframe_to_bar_size(timeframe: str) -> str:
    mapping = {"1m": "1 min", "5m": "5 mins", "15m": "15 mins"}
    return mapping.get(timeframe, "5 mins")


def _bars_to_duration(lookback_bars: int, timeframe: str) -> str:
    minutes_per_bar = {"1m": 1, "5m": 5, "15m": 15}.get(timeframe, 5)
    total_minutes = max(lookback_bars, 1) * minutes_per_bar
    total_days = max(int(total_minutes / 1440) + 1, 1)
    return f"{total_days} D"
