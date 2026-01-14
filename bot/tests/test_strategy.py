from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from bot.core.types import Venue
from bot.strategies.base import StrategyContext
from bot.strategies.sma_vol_filter import SmaVolFilterStrategy


def _make_candles(prices: list[float]) -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    rows = []
    for idx, price in enumerate(prices):
        ts = now + timedelta(minutes=5 * idx)
        rows.append({"timestamp": ts, "open": price, "high": price, "low": price, "close": price, "volume": 1})
    df = pd.DataFrame(rows).set_index("timestamp")
    return df


def test_sma_vol_filter_long_signal() -> None:
    prices = [1] * 50 + [1.2] * 10
    candles = _make_candles(prices)
    strategy = SmaVolFilterStrategy()
    context = StrategyContext(
        symbol="SPY",
        venue=Venue.IBKR.value,
        now=pd.Timestamp(datetime.now(timezone.utc)),
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
    intent = strategy.generate_intent(candles, None, context)
    assert intent.target_exposure > 0
    assert intent.reason == "FAST_ABOVE_SLOW"


def test_sma_vol_filter_flat_signal() -> None:
    prices = [1.0] * 60
    candles = _make_candles(prices)
    strategy = SmaVolFilterStrategy()
    context = StrategyContext(
        symbol="SPY",
        venue=Venue.IBKR.value,
        now=pd.Timestamp(datetime.now(timezone.utc)),
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
    intent = strategy.generate_intent(candles, None, context)
    assert intent.target_exposure == 0.0
    assert intent.reason == "NO_SIGNAL"
