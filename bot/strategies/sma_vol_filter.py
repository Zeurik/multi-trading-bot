from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from bot.core.types import Intent, OrderType, Position, Venue
from bot.strategies.base import Strategy, StrategyContext, register_strategy


def _sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length).mean()


def _atr(candles: pd.DataFrame, length: int) -> pd.Series:
    high_low = candles["high"] - candles["low"]
    high_close = (candles["high"] - candles["close"].shift()).abs()
    low_close = (candles["low"] - candles["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(length).mean()


@register_strategy("sma_vol_filter")
class SmaVolFilterStrategy(Strategy):
    def generate_intent(
        self, candles: pd.DataFrame, position: Position | None, context: StrategyContext
    ) -> Intent:
        params = context.params
        fast_len = int(params["fast_len"])
        slow_len = int(params["slow_len"])
        atr_len = int(params["atr_len"])
        min_atr_pct = float(params["min_atr_pct"])
        exposure = float(params["exposure"])
        allow_short = bool(params.get("allow_short", False))
        k1 = float(params.get("k1", 1.5))
        k2 = float(params.get("k2", 3.0))

        candles = candles.copy()
        candles["fast_sma"] = _sma(candles["close"], fast_len)
        candles["slow_sma"] = _sma(candles["close"], slow_len)
        candles["atr"] = _atr(candles, atr_len)
        candles = candles.dropna()
        latest = candles.iloc[-1]
        prev = candles.iloc[-2] if len(candles) > 1 else latest

        fast_cross_up = prev["fast_sma"] <= prev["slow_sma"] and latest["fast_sma"] > latest["slow_sma"]
        fast_cross_down = prev["fast_sma"] >= prev["slow_sma"] and latest["fast_sma"] < latest["slow_sma"]
        vol_filter = (latest["atr"] / latest["close"]) > min_atr_pct

        target_exposure = 0.0
        reason = "NO_SIGNAL"
        if fast_cross_up and vol_filter:
            target_exposure = exposure
            reason = "FAST_ABOVE_SLOW"
        elif allow_short and fast_cross_down and vol_filter:
            target_exposure = -exposure
            reason = "FAST_BELOW_SLOW"

        stop_loss_pct = k1 * (latest["atr"] / latest["close"]) if target_exposure != 0 else None
        take_profit_pct = k2 * (latest["atr"] / latest["close"]) if target_exposure != 0 else None

        features: Dict[str, Any] = {
            "fast_sma": float(latest["fast_sma"]),
            "slow_sma": float(latest["slow_sma"]),
            "atr": float(latest["atr"]),
            "atr_pct": float(latest["atr"] / latest["close"]),
            "vol_filter": bool(vol_filter),
        }

        return Intent(
            symbol=context.symbol,
            venue=Venue(context.venue),
            timestamp=latest.name.to_pydatetime(),
            target_exposure=target_exposure,
            max_notional=float(params.get("max_notional", 0.0)),
            order_type_preference=OrderType(params.get("order_type_preference", "LIMIT")),
            limit_offset_bps=float(params.get("limit_offset_bps", 5.0)),
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            time_stop_minutes=int(params.get("time_stop_minutes", 0)) or None,
            reason=reason,
            features=features,
        )
