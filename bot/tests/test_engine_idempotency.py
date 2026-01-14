from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from bot.adapters.base import BrokerAdapter
from bot.core.engine import AllocationConfig, RuntimeConfig, SymbolConfig, TradingEngine
from bot.core.persistence import Persistence
from bot.core.risk import RiskConfig, RiskManager
from bot.core.types import AccountSummary, Order, OrderAck, OrderRequest, Position, SymbolRules


class DummyAdapter(BrokerAdapter):
    def __init__(self, candles: pd.DataFrame) -> None:
        self.candles = candles
        self.orders: list[OrderRequest] = []

    def get_account_summary(self) -> AccountSummary:
        return AccountSummary(cash=100000, equity=100000, base_currency="USD")

    def get_positions(self) -> list[Position]:
        return []

    def get_open_orders(self) -> list[Order]:
        return []

    def get_latest_price(self, symbol: str) -> float:
        return float(self.candles.iloc[-1]["close"])

    def get_spread_bps(self, symbol: str) -> float:
        return 0.0

    def get_candles(self, symbol: str, timeframe: str, lookback_bars: int) -> pd.DataFrame:
        return self.candles

    def place_order(self, order_request: OrderRequest) -> OrderAck:
        self.orders.append(order_request)
        return OrderAck(order_id="1", status="FILLED")

    def cancel_order(self, order_id: str) -> bool:
        return False

    def is_market_open(self, symbol: str, now_utc: datetime) -> bool:
        return True

    def symbol_rules(self, symbol: str) -> SymbolRules:
        return SymbolRules(min_qty=1.0, qty_step=1.0, tick_size=0.01, min_notional=1.0)


def _candles() -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    prices = [1.0] * 20 + [1.5] * 5
    rows = []
    for idx, price in enumerate(prices):
        rows.append(
            {
                "timestamp": now + timedelta(minutes=5 * idx),
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 1,
            }
        )
    df = pd.DataFrame(rows).set_index("timestamp")
    return df


def test_engine_idempotency(tmp_path) -> None:
    candles = _candles()
    adapter = DummyAdapter(candles)
    risk_manager = RiskManager(
        RiskConfig(
            max_notional_per_symbol=10000,
            max_portfolio_gross_exposure=50000,
            max_trades_per_day=10,
            max_trades_per_day_per_symbol=5,
            daily_loss_limit_pct=0.5,
            max_drawdown_pct=0.5,
            cooldown_minutes_after_n_losses=0,
            loss_streak_threshold=1,
            max_spread_bps=100,
            max_volatility=None,
            volatility_method="atr_pct",
            volatility_window=14,
            min_equity_required=1,
            kill_switch_path=str(tmp_path / "KILL_SWITCH"),
        )
    )
    persistence = Persistence(tmp_path / "test.db")

    symbols = [
        SymbolConfig(
            venue="IBKR",
            symbol="SPY",
            strategy="sma_vol_filter",
            params={
                "fast_len": 5,
                "slow_len": 10,
                "atr_len": 3,
                "min_atr_pct": 0.0,
                "exposure": 0.25,
                "allow_short": False,
                "k1": 1.5,
                "k2": 3.0,
                "max_notional": 10000,
                "order_type_preference": "LIMIT",
                "limit_offset_bps": 5.0,
            },
        )
    ]
    engine = TradingEngine(
        adapter=adapter,
        risk_manager=risk_manager,
        persistence=persistence,
        symbols=symbols,
        allocations={"IBKR": AllocationConfig(total_capital_usd=10000)},
        runtime=RuntimeConfig(
            timeframe="5m",
            lookback_bars=200,
            loop_interval_seconds=5,
            fill_timeout_seconds=1,
            base_currency="USD",
            live_trading_enabled=False,
        ),
    )

    engine.run_cycle(symbols[0])
    engine.run_cycle(symbols[0])

    assert len(adapter.orders) == 1
