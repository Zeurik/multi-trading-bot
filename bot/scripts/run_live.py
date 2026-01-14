from __future__ import annotations

import sys
import time
from pathlib import Path

from bot.adapters.coinbase import CoinbaseAdapter
from bot.adapters.ibkr import IbkrAdapter
from bot.adapters.router import MultiVenueAdapter
from bot.core.alerts import TelegramAlerter, TelegramConfig
from bot.core.clock import MarketClock, MarketClockConfig
from bot.core.config import load_risk, load_runtime, load_symbols, load_yaml
from bot.core.engine import TradingEngine
from bot.core.logger import configure_logging, get_logger
from bot.core.persistence import Persistence
from bot.core.risk import RiskManager


def main() -> None:
    configure_logging()
    logger = get_logger(event="live")

    runtime = load_runtime("bot/config/runtime.yaml")
    if not runtime.live_trading_enabled:
        logger.error(event="live_disabled", details="Set live_trading_enabled: true in runtime.yaml")
        sys.exit(1)

    symbols, allocations = load_symbols("bot/config/instruments.yaml")
    risk_config = load_risk("bot/config/risk.yaml")
    risk_manager = RiskManager(risk_config)

    runtime_yaml = load_yaml("bot/config/runtime.yaml")
    alerts_cfg = runtime_yaml.get("telegram_alerts", {})
    alerter = TelegramAlerter(
        TelegramConfig(
            enabled=bool(alerts_cfg.get("enabled", False)),
            bot_token=str(alerts_cfg.get("bot_token", "")),
            chat_id=str(alerts_cfg.get("chat_id", "")),
        )
    )

    symbol_to_adapter = {}
    for symbol in symbols:
        if symbol.venue == "CRYPTO":
            base_adapter = CoinbaseAdapter()
        else:
            clock = MarketClock(MarketClockConfig(allow_extended_hours=runtime.allow_extended_hours))
            base_adapter = IbkrAdapter(clock=clock)
            try:
                base_adapter.connect(
                    host=runtime.ibkr_host,
                    port=runtime.ibkr_port,
                    client_id=runtime.ibkr_client_id,
                )
            except Exception as exc:
                logger.error(event="ibkr_connect_failed", symbol=symbol.symbol, details=str(exc))
                alerter.send(f"IBKR connect failed for {symbol.symbol}: {exc}")
        symbol_to_adapter[symbol.symbol] = base_adapter

    adapter = MultiVenueAdapter(symbol_to_adapter)
    Path("bot/state").mkdir(parents=True, exist_ok=True)
    persistence = Persistence("bot/state/live.db")

    engine = TradingEngine(
        adapter=adapter,
        risk_manager=risk_manager,
        persistence=persistence,
        symbols=symbols,
        allocations=allocations,
        runtime=runtime,
        logger=logger,
        alerter=alerter,
    )

    logger.info(event="live_start", details={"symbols": [s.symbol for s in symbols]})

    while True:
        for symbol in symbols:
            try:
                engine.run_cycle(symbol)
            except Exception as exc:
                logger.error(event="cycle_error", symbol=symbol.symbol, details=str(exc))
                alerter.send(f"Live cycle error for {symbol.symbol}: {exc}")
        time.sleep(runtime.loop_interval_seconds)


if __name__ == "__main__":
    main()
