from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from bot.core.types import Intent, RiskDecision


@dataclass
class RiskConfig:
    max_notional_per_symbol: float
    max_portfolio_gross_exposure: float
    max_trades_per_day: int
    max_trades_per_day_per_symbol: int
    daily_loss_limit_pct: float
    max_drawdown_pct: float
    cooldown_minutes_after_n_losses: int
    loss_streak_threshold: int
    max_spread_bps: float
    max_volatility: Optional[float]
    volatility_method: str
    volatility_window: int
    min_equity_required: float
    kill_switch_path: str = "./KILL_SWITCH"


@dataclass
class RiskState:
    current_day: Optional[str] = None
    trades_today: int = 0
    trades_today_by_symbol: Dict[str, int] = field(default_factory=dict)
    loss_streak: int = 0
    last_loss_time: Optional[datetime] = None
    day_start_equity: Optional[float] = None
    peak_equity: Optional[float] = None


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config
        self.state = RiskState()

    def _reset_day(self, day_key: str, equity: float) -> None:
        self.state.current_day = day_key
        self.state.trades_today = 0
        self.state.trades_today_by_symbol = {}
        self.state.loss_streak = 0
        self.state.last_loss_time = None
        self.state.day_start_equity = equity
        self.state.peak_equity = equity

    def _update_daily_state(self, now: datetime, equity: float) -> None:
        day_key = now.strftime("%Y-%m-%d")
        if self.state.current_day != day_key:
            self._reset_day(day_key, equity)
        if self.state.peak_equity is None:
            self.state.peak_equity = equity
        self.state.peak_equity = max(self.state.peak_equity, equity)

    def record_trade_result(self, pnl: float, now: datetime) -> None:
        if pnl < 0:
            self.state.loss_streak += 1
            self.state.last_loss_time = now
        else:
            self.state.loss_streak = 0

    def evaluate(
        self,
        intent: Intent,
        now: datetime,
        equity: float,
        gross_exposure: float,
        market_open: bool,
        spread_bps: float,
        volatility: Optional[float],
    ) -> RiskDecision:
        self._update_daily_state(now, equity)

        risk_tags = []
        if not market_open:
            return RiskDecision(False, None, "MARKET_CLOSED", ["MARKET_CLOSED"])

        if Path(self.config.kill_switch_path).exists():
            return RiskDecision(False, None, "KILL_SWITCH", ["KILL_SWITCH"])

        if equity < self.config.min_equity_required:
            return RiskDecision(False, None, "MIN_EQUITY", ["MIN_EQUITY"])

        day_start_equity = self.state.day_start_equity or equity
        if (equity - day_start_equity) / day_start_equity <= -self.config.daily_loss_limit_pct:
            return RiskDecision(False, None, "DAILY_LOSS_LIMIT", ["DAILY_LOSS_LIMIT"])

        peak_equity = self.state.peak_equity or equity
        if (equity - peak_equity) / peak_equity <= -self.config.max_drawdown_pct:
            return RiskDecision(False, None, "MAX_DRAWDOWN", ["MAX_DRAWDOWN"])

        if self.state.loss_streak >= self.config.loss_streak_threshold:
            if self.state.last_loss_time and now < self.state.last_loss_time + timedelta(
                minutes=self.config.cooldown_minutes_after_n_losses
            ):
                return RiskDecision(False, None, "COOLDOWN", ["COOLDOWN"])

        if self.state.trades_today >= self.config.max_trades_per_day:
            return RiskDecision(False, None, "MAX_TRADES_DAY", ["MAX_TRADES_DAY"])

        trades_symbol = self.state.trades_today_by_symbol.get(intent.symbol, 0)
        if trades_symbol >= self.config.max_trades_per_day_per_symbol:
            return RiskDecision(False, None, "MAX_TRADES_SYMBOL", ["MAX_TRADES_SYMBOL"])

        if spread_bps > self.config.max_spread_bps:
            return RiskDecision(False, None, "SPREAD_TOO_WIDE", ["SPREAD_TOO_WIDE"])

        if self.config.max_volatility is not None and volatility is not None:
            if volatility > self.config.max_volatility:
                return RiskDecision(False, None, "VOLATILITY_TOO_HIGH", ["VOLATILITY_TOO_HIGH"])

        if gross_exposure > self.config.max_portfolio_gross_exposure:
            return RiskDecision(False, None, "MAX_GROSS_EXPOSURE", ["MAX_GROSS_EXPOSURE"])

        adjusted = intent
        if intent.max_notional > self.config.max_notional_per_symbol:
            adjusted = Intent(
                **{**intent.__dict__, "max_notional": self.config.max_notional_per_symbol}
            )
            risk_tags.append("MAX_NOTIONAL_RESIZED")

        return RiskDecision(True, adjusted, None, risk_tags)

    def record_trade(self, symbol: str) -> None:
        self.state.trades_today += 1
        self.state.trades_today_by_symbol[symbol] = self.state.trades_today_by_symbol.get(symbol, 0) + 1
