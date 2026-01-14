from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml

from bot.core.engine import AllocationConfig, RuntimeConfig, SymbolConfig
from bot.core.risk import RiskConfig


@dataclass
class AppConfig:
    runtime: RuntimeConfig
    risk: RiskConfig
    symbols: List[SymbolConfig]
    allocations: Dict[str, AllocationConfig]


def load_yaml(path: str | Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_runtime(path: str | Path) -> RuntimeConfig:
    data = load_yaml(path)
    return RuntimeConfig(
        timeframe=data["timeframe"],
        lookback_bars=int(data["lookback_bars"]),
        loop_interval_seconds=int(data["loop_interval_seconds"]),
        fill_timeout_seconds=int(data["fill_timeout_seconds"]),
        base_currency=data["base_currency"],
        live_trading_enabled=bool(data.get("live_trading_enabled", False)),
        allow_extended_hours=bool(data.get("allow_extended_hours", False)),
        ibkr_host=str(data.get("ibkr_host", "127.0.0.1")),
        ibkr_port=int(data.get("ibkr_port", 7497)),
        ibkr_client_id=int(data.get("ibkr_client_id", 1)),
    )


def load_symbols(path: str | Path) -> tuple[List[SymbolConfig], Dict[str, AllocationConfig]]:
    data = load_yaml(path)
    allocations = {
        venue: AllocationConfig(total_capital_usd=float(cfg["total_capital_usd"]))
        for venue, cfg in data.get("allocations", {}).items()
    }
    symbols = [
        SymbolConfig(
            venue=item["venue"],
            symbol=item["symbol"],
            strategy=item["strategy"],
            params=item.get("params", {}),
        )
        for item in data.get("symbols", [])
    ]
    return symbols, allocations


def load_risk(path: str | Path) -> RiskConfig:
    data = load_yaml(path)
    return RiskConfig(
        max_notional_per_symbol=float(data["max_notional_per_symbol"]),
        max_portfolio_gross_exposure=float(data["max_portfolio_gross_exposure"]),
        max_trades_per_day=int(data["max_trades_per_day"]),
        max_trades_per_day_per_symbol=int(data["max_trades_per_day_per_symbol"]),
        daily_loss_limit_pct=float(data["daily_loss_limit_pct"]),
        max_drawdown_pct=float(data["max_drawdown_pct"]),
        cooldown_minutes_after_n_losses=int(data["cooldown_minutes_after_n_losses"]),
        loss_streak_threshold=int(data.get("loss_streak_threshold", 1)),
        max_spread_bps=float(data["max_spread_bps"]),
        max_volatility=data.get("max_volatility"),
        volatility_method=str(data.get("volatility_method", "atr_pct")),
        volatility_window=int(data.get("volatility_window", 14)),
        min_equity_required=float(data["min_equity_required"]),
        kill_switch_path=data.get("kill_switch_path", "./KILL_SWITCH"),
    )
