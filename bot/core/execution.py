from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import copysign, floor
from typing import Optional

from bot.core.types import Intent, OrderRequest, OrderSide, OrderType, Position, SymbolRules, Venue


@dataclass
class ExecutionConfig:
    limit_offset_bps: float
    fill_timeout_seconds: int
    time_in_force: str


def generate_client_order_id(
    venue: Venue, symbol: str, timeframe: str, candle_ts: str, side: OrderSide
) -> str:
    raw = f"{venue.value}-{symbol}-{timeframe}-{candle_ts}-{side.value}"
    return sha256(raw.encode()).hexdigest()


def create_order_request(
    intent: Intent,
    current_position: Optional[Position],
    last_price: float,
    symbol_rules: SymbolRules,
    timeframe: str,
    candle_ts: str,
    time_in_force: str,
) -> Optional[OrderRequest]:
    target_notional = intent.max_notional * intent.target_exposure
    target_qty = target_notional / last_price if last_price else 0.0
    if symbol_rules.min_notional and abs(target_notional) < symbol_rules.min_notional:
        return None
    current_qty = current_position.qty if current_position else 0.0
    delta_qty = target_qty - current_qty

    if symbol_rules.qty_step:
        step = symbol_rules.qty_step
        delta_qty = copysign(floor(abs(delta_qty) / step) * step, delta_qty)

    if abs(delta_qty) < symbol_rules.min_qty:
        return None

    side = OrderSide.BUY if delta_qty > 0 else OrderSide.SELL
    order_type = intent.order_type_preference
    limit_price = None
    if order_type == OrderType.LIMIT:
        offset = intent.limit_offset_bps / 10000
        if side == OrderSide.BUY:
            limit_price = last_price * (1 - offset)
        else:
            limit_price = last_price * (1 + offset)
        if symbol_rules.tick_size:
            limit_price = (limit_price // symbol_rules.tick_size) * symbol_rules.tick_size

    client_order_id = generate_client_order_id(intent.venue, intent.symbol, timeframe, candle_ts, side)

    return OrderRequest(
        symbol=intent.symbol,
        venue=intent.venue,
        side=side,
        quantity=abs(delta_qty),
        order_type=order_type,
        limit_price=limit_price,
        client_order_id=client_order_id,
        time_in_force=time_in_force,
    )
