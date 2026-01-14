from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd


@dataclass
class WalkForwardResult:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    metrics: dict


def run_walkforward(candles: pd.DataFrame, window: int, step: int) -> List[WalkForwardResult]:
    results: List[WalkForwardResult] = []
    start = 0
    while start + window < len(candles):
        train = candles.iloc[start : start + window]
        test = candles.iloc[start + window : start + window + step]
        results.append(
            WalkForwardResult(
                train_start=train.index[0],
                train_end=train.index[-1],
                test_start=test.index[0],
                test_end=test.index[-1],
                metrics={"train_bars": len(train), "test_bars": len(test)},
            )
        )
        start += step
    return results
