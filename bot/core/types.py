from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Venue(str, Enum):
    IBKR = "IBKR"
    CRYPTO = "CRYPTO"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass
class Intent:
    symbol: str
    venue: Venue
    timestamp: datetime
    target_exposure: float
    max_notional: float
    order_type_preference: OrderType
    limit_offset_bps: float
    stop_loss_pct: Optional[float]
    take_profit_pct: Optional[float]
    time_stop_minutes: Optional[int]
    reason: str
    features: Dict[str, Any]


@dataclass
class RiskDecision:
    approved: bool
    adjusted_intent: Optional[Intent]
    rejection_reason: Optional[str]
    risk_tags: List[str] = field(default_factory=list)


@dataclass
class OrderRequest:
    symbol: str
    venue: Venue
    side: OrderSide
    quantity: float
    order_type: OrderType
    limit_price: Optional[float]
    client_order_id: str
    time_in_force: str


@dataclass
class AccountSummary:
    cash: float
    equity: float
    base_currency: str


@dataclass
class Position:
    symbol: str
    qty: float
    avg_price: float
    unrealized_pnl: float


@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    qty: float
    filled_qty: float
    status: str
    limit_price: Optional[float]
    client_order_id: Optional[str] = None


@dataclass
class OrderAck:
    order_id: str
    status: str
    filled_qty: float = 0.0
    avg_fill_price: Optional[float] = None
    fee: float = 0.0
    realized_pnl: Optional[float] = None


@dataclass
class SymbolRules:
    min_qty: float
    qty_step: float
    tick_size: float
    min_notional: Optional[float] = None
