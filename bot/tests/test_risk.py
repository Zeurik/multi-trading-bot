from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bot.core.risk import RiskConfig, RiskManager
from bot.core.types import Intent, OrderType, Venue


def _intent() -> Intent:
    return Intent(
        symbol="SPY",
        venue=Venue.IBKR,
        timestamp=datetime.now(timezone.utc),
        target_exposure=0.5,
        max_notional=20000,
        order_type_preference=OrderType.LIMIT,
        limit_offset_bps=5.0,
        stop_loss_pct=None,
        take_profit_pct=None,
        time_stop_minutes=None,
        reason="test",
        features={},
    )


def test_risk_resizes_max_notional(tmp_path: Path) -> None:
    risk = RiskManager(
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
    decision = risk.evaluate(
        intent=_intent(),
        now=datetime.now(timezone.utc),
        equity=100000,
        gross_exposure=0,
        market_open=True,
        spread_bps=0,
        volatility=None,
    )
    assert decision.approved
    assert decision.adjusted_intent is not None
    assert decision.adjusted_intent.max_notional == 10000


def test_risk_kill_switch(tmp_path: Path) -> None:
    kill_path = tmp_path / "KILL_SWITCH"
    kill_path.write_text("stop", encoding="utf-8")
    risk = RiskManager(
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
            kill_switch_path=str(kill_path),
        )
    )
    decision = risk.evaluate(
        intent=_intent(),
        now=datetime.now(timezone.utc),
        equity=100000,
        gross_exposure=0,
        market_open=True,
        spread_bps=0,
        volatility=None,
    )
    assert not decision.approved
    assert decision.rejection_reason == "KILL_SWITCH"
