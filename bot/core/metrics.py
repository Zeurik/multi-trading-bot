from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np


@dataclass
class PerformanceMetrics:
    equity_curve: List[float]
    drawdown: float
    total_return: float
    sharpe: float
    num_trades: int
    fees: float


def compute_metrics(equity_curve: List[float], trades: int, fees: float) -> PerformanceMetrics:
    if not equity_curve:
        return PerformanceMetrics([], 0.0, 0.0, 0.0, trades, fees)
    equity = np.array(equity_curve)
    returns = np.diff(equity) / equity[:-1]
    total_return = (equity[-1] / equity[0]) - 1
    running_max = np.maximum.accumulate(equity)
    drawdown = float(np.min((equity - running_max) / running_max)) if equity.size else 0.0
    sharpe = float(np.mean(returns) / (np.std(returns) + 1e-9) * np.sqrt(252)) if returns.size else 0.0
    return PerformanceMetrics(
        equity_curve=list(equity),
        drawdown=drawdown,
        total_return=total_return,
        sharpe=sharpe,
        num_trades=trades,
        fees=fees,
    )
