from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from bot.adapters.base import BrokerAdapter
import time

from bot.core.execution import create_order_request
from bot.core.intents import intent_to_dict
from bot.core.logger import get_logger
from bot.core.persistence import Persistence, risk_to_dict
from bot.core.portfolio import PortfolioSnapshot
from bot.core.risk import RiskManager
from bot.core.types import Intent, OrderRequest, OrderType, Position, Venue
import bot.strategies  # noqa: F401
from bot.strategies.base import STRATEGY_REGISTRY, StrategyContext


@dataclass
class SymbolConfig:
    venue: str
    symbol: str
    strategy: str
    params: Dict[str, Any]


@dataclass
class RuntimeConfig:
    timeframe: str
    lookback_bars: int
    loop_interval_seconds: int
    fill_timeout_seconds: int
    base_currency: str
    live_trading_enabled: bool
    allow_extended_hours: bool = False
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 1


@dataclass
class AllocationConfig:
    total_capital_usd: float


class TradingEngine:
    def __init__(
        self,
        adapter: BrokerAdapter,
        risk_manager: RiskManager,
        persistence: Persistence,
        symbols: List[SymbolConfig],
        allocations: Dict[str, AllocationConfig],
        runtime: RuntimeConfig,
        logger=None,
        alerter=None,
    ) -> None:
        self.adapter = adapter
        self.risk_manager = risk_manager
        self.persistence = persistence
        self.symbols = symbols
        self.allocations = allocations
        self.runtime = runtime
        self.logger = logger or get_logger(event="engine")
        self.alerter = alerter

    def run_cycle(self, symbol_config: SymbolConfig) -> None:
        now = datetime.now(timezone.utc)
        candles = self.adapter.get_candles(
            symbol_config.symbol, self.runtime.timeframe, self.runtime.lookback_bars
        )
        if candles.empty:
            return
        latest_ts = candles.index[-1].isoformat()
        if self.persistence.has_decision(
            symbol_config.venue, symbol_config.symbol, self.runtime.timeframe, latest_ts
        ):
            self.logger.info(
                event="idempotent_skip",
                symbol=symbol_config.symbol,
                venue=symbol_config.venue,
                candle_ts=latest_ts,
            )
            return

        position = self._position_for_symbol(symbol_config.symbol)
        strategy_cls = STRATEGY_REGISTRY[symbol_config.strategy]
        strategy = strategy_cls()
        context = StrategyContext(
            symbol=symbol_config.symbol,
            venue=symbol_config.venue,
            now=pd.Timestamp(now),
            params=symbol_config.params,
        )
        intent = strategy.generate_intent(candles, position, context)

        allocation = self._allocation_for_symbol(symbol_config)
        if allocation:
            intent = Intent(
                **{**intent.__dict__, "max_notional": allocation.total_capital_usd}
            )

        account = self.adapter.get_account_summary()
        positions = self.adapter.get_positions()
        portfolio = PortfolioSnapshot(account=account, positions=positions)
        gross_exposure = sum(
            abs(p.qty * self.adapter.get_latest_price(p.symbol)) for p in positions
        )
        spread_bps = self.adapter.get_spread_bps(symbol_config.symbol)
        volatility = self._compute_volatility(candles)
        market_open = self.adapter.is_market_open(symbol_config.symbol, now)

        risk = self.risk_manager.evaluate(
            intent=intent,
            now=now,
            equity=account.equity,
            gross_exposure=gross_exposure,
            market_open=market_open,
            spread_bps=spread_bps,
            volatility=volatility,
        )

        self.persistence.record_decision(
            timestamp=now,
            venue=symbol_config.venue,
            symbol=symbol_config.symbol,
            timeframe=self.runtime.timeframe,
            candle_ts=latest_ts,
            intent=intent_to_dict(intent),
            risk=risk_to_dict(risk),
        )

        if not risk.approved or not risk.adjusted_intent:
            self.logger.info(
                event="risk_rejected",
                symbol=symbol_config.symbol,
                venue=symbol_config.venue,
                details=risk.rejection_reason,
            )
            if self.alerter and risk.rejection_reason in {
                "KILL_SWITCH",
                "DAILY_LOSS_LIMIT",
                "MAX_DRAWDOWN",
            }:
                self.alerter.send(
                    f"Risk rejected {symbol_config.symbol} ({symbol_config.venue}): {risk.rejection_reason}"
                )
            return

        adjusted_intent = self._apply_exit_rules(
            risk.adjusted_intent, position, candles["close"].iloc[-1]
        )
        rules = self.adapter.symbol_rules(symbol_config.symbol)
        last_price = self.adapter.get_latest_price(symbol_config.symbol)
        time_in_force = "GTC" if symbol_config.venue == Venue.CRYPTO.value else "DAY"
        order_request = create_order_request(
            adjusted_intent,
            current_position=portfolio.positions_by_symbol().get(symbol_config.symbol),
            last_price=last_price,
            symbol_rules=rules,
            timeframe=self.runtime.timeframe,
            candle_ts=latest_ts,
            time_in_force=time_in_force,
        )
        if not order_request:
            self.logger.info(
                event="no_order",
                symbol=symbol_config.symbol,
                venue=symbol_config.venue,
            )
            return

        open_orders = self.adapter.get_open_orders()
        if any(order.client_order_id == order_request.client_order_id for order in open_orders):
            self.logger.info(
                event="open_order_exists",
                symbol=symbol_config.symbol,
                venue=symbol_config.venue,
            )
            return
        request_used = order_request
        ack = self.adapter.place_order(order_request)
        if ack.status != "FILLED" and order_request.order_type == OrderType.LIMIT:
            order_filled = self._wait_for_fill(ack.order_id)
            if not order_filled:
                self.adapter.cancel_order(ack.order_id)
                request_used = OrderRequest(
                    **{**order_request.__dict__, "order_type": OrderType.MARKET, "limit_price": None}
                )
                ack = self.adapter.place_order(request_used)
        if ack.status == "FILLED":
            self.risk_manager.record_trade(symbol_config.symbol)
            if ack.realized_pnl is not None:
                self.risk_manager.record_trade_result(ack.realized_pnl, now)
        self.persistence.record_order(
            timestamp=now,
            venue=symbol_config.venue,
            symbol=symbol_config.symbol,
            client_order_id=order_request.client_order_id,
            order_id=ack.order_id,
            request=request_used,
            status=ack.status,
            filled_qty=ack.filled_qty if ack.status == "FILLED" else 0.0,
            avg_fill_price=ack.avg_fill_price if ack.status == "FILLED" else None,
        )
        if ack.status == "FILLED":
            self.persistence.record_fill(
                timestamp=now,
                venue=symbol_config.venue,
                symbol=symbol_config.symbol,
                order_id=ack.order_id,
                qty=ack.filled_qty,
                price=ack.avg_fill_price or last_price,
                fee=ack.fee,
            )

        self.persistence.record_positions_snapshot(
            timestamp=now,
            venue=symbol_config.venue,
            equity=account.equity,
            cash=account.cash,
            positions=[p.__dict__ for p in positions],
        )

        self.logger.info(
            event="order_sent",
            symbol=symbol_config.symbol,
            venue=symbol_config.venue,
            details={"order_id": ack.order_id, "status": ack.status},
        )

    def _position_for_symbol(self, symbol: str) -> Position | None:
        for position in self.adapter.get_positions():
            if position.symbol == symbol:
                return position
        return None

    def _allocation_for_symbol(self, symbol_config: SymbolConfig) -> AllocationConfig | None:
        allocation = self.allocations.get(symbol_config.venue)
        if not allocation:
            return None
        venue_symbols = [s for s in self.symbols if s.venue == symbol_config.venue]
        if not venue_symbols:
            return allocation
        per_symbol = allocation.total_capital_usd / len(venue_symbols)
        return AllocationConfig(total_capital_usd=per_symbol)

    def _wait_for_fill(self, order_id: str) -> bool:
        timeout = self.runtime.fill_timeout_seconds
        start = time.time()
        while time.time() - start < timeout:
            open_orders = self.adapter.get_open_orders()
            if not any(order.id == order_id for order in open_orders):
                return True
            time.sleep(1)
        return False

    def _compute_volatility(self, candles: pd.DataFrame) -> float:
        method = self.risk_manager.config.volatility_method
        window = self.risk_manager.config.volatility_window
        if method == "std":
            return float(candles["close"].pct_change().rolling(window).std().iloc[-1])
        high_low = candles["high"] - candles["low"]
        high_close = (candles["high"] - candles["close"].shift()).abs()
        low_close = (candles["low"] - candles["close"].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window).mean().iloc[-1]
        return float(atr / candles["close"].iloc[-1])

    def _apply_exit_rules(
        self, intent: Intent, position: Position | None, last_close: float
    ) -> Intent:
        if not position:
            return intent
        stop_loss = intent.stop_loss_pct
        take_profit = intent.take_profit_pct
        if stop_loss is None and take_profit is None:
            return intent
        if position.qty > 0:
            stop_price = position.avg_price * (1 - (stop_loss or 0))
            take_price = position.avg_price * (1 + (take_profit or 0))
            if stop_loss is not None and last_close <= stop_price:
                return Intent(**{**intent.__dict__, "target_exposure": 0.0, "reason": "STOP_LOSS"})
            if take_profit is not None and last_close >= take_price:
                return Intent(**{**intent.__dict__, "target_exposure": 0.0, "reason": "TAKE_PROFIT"})
        if position.qty < 0:
            stop_price = position.avg_price * (1 + (stop_loss or 0))
            take_price = position.avg_price * (1 - (take_profit or 0))
            if stop_loss is not None and last_close >= stop_price:
                return Intent(**{**intent.__dict__, "target_exposure": 0.0, "reason": "STOP_LOSS"})
            if take_profit is not None and last_close <= take_price:
                return Intent(**{**intent.__dict__, "target_exposure": 0.0, "reason": "TAKE_PROFIT"})
        return intent
