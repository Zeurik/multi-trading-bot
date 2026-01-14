from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import pandas as pd


@dataclass
class CSVDataProvider:
    data_dir: Path

    def load_candles(self, symbol: str, timeframe: str, lookback_bars: int | None = None) -> pd.DataFrame:
        filename = f"{symbol.replace('/', '-')}-{timeframe}.csv"
        path = self.data_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing candle CSV: {path}")
        df = pd.read_csv(path, parse_dates=["timestamp"])
        df = df.set_index("timestamp")
        df = df.sort_index()
        for column in ["open", "high", "low", "close", "volume"]:
            if column in df.columns:
                df[column] = pd.to_numeric(df[column], errors="coerce")
        if lookback_bars:
            df = df.iloc[-lookback_bars:]
        return df
