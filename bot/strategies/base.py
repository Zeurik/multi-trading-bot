from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd

from bot.core.types import Intent, Position


@dataclass
class StrategyContext:
    symbol: str
    venue: str
    now: pd.Timestamp
    params: Dict[str, Any]


class Strategy(ABC):
    @abstractmethod
    def generate_intent(
        self, candles: pd.DataFrame, position: Position | None, context: StrategyContext
    ) -> Intent:
        raise NotImplementedError


STRATEGY_REGISTRY: Dict[str, type[Strategy]] = {}


def register_strategy(name: str) -> Any:
    def decorator(cls: type[Strategy]) -> type[Strategy]:
        STRATEGY_REGISTRY[name] = cls
        return cls

    return decorator
