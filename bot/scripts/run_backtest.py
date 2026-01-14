from __future__ import annotations

from pathlib import Path

from bot.adapters.data_providers import CSVDataProvider
from bot.core.config import load_risk, load_runtime, load_symbols
from bot.core.engine import TradingEngine
from bot.core.logger import configure_logging, get_logger
from bot.core.metrics import compute_metrics
from bot.core.persistence import Persistence
from bot.core.risk import RiskManager
from bot.research.backtest import BacktestAdapter


def main() -> None:
    configure_logging()
    logger = get_logger(event="backtest")

    runtime = load_runtime("bot/config/runtime.yaml")
    symbols, allocations = load_symbols("bot/config/instruments.yaml")
    risk_config = load_risk("bot/config/risk.yaml")
    risk_manager = RiskManager(risk_config)

    data_provider = CSVDataProvider(Path("data"))
    candles_by_symbol = {
        symbol.symbol: data_provider.load_candles(symbol.symbol, runtime.timeframe)
        for symbol in symbols
    }

    allow_short_symbols = {
        symbol.symbol: bool(symbol.params.get("allow_short", False)) for symbol in symbols
    }
    adapter = BacktestAdapter(candles_by_symbol, allow_short_symbols=allow_short_symbols)
    Path("bot/state").mkdir(parents=True, exist_ok=True)
    persistence = Persistence("bot/state/backtest.db")

    engine = TradingEngine(
        adapter=adapter,
        risk_manager=risk_manager,
        persistence=persistence,
        symbols=symbols,
        allocations=allocations,
        runtime=runtime,
        logger=logger,
    )

    equity_curve = []
    for idx in range(len(next(iter(candles_by_symbol.values())))):
        adapter.set_index(idx)
        for symbol in symbols:
            engine.run_cycle(symbol)
        equity_curve.append(adapter.get_account_summary().equity)

    trade_pnls = adapter.realized_pnls
    total_trades = len(trade_pnls)
    wins = sum(1 for pnl in trade_pnls if pnl > 0)
    win_rate = wins / total_trades if total_trades else 0.0
    avg_trade = sum(trade_pnls) / total_trades if total_trades else 0.0
    metrics = compute_metrics(equity_curve, trades=total_trades, fees=0.0)
    trades_csv = Path("bot/state/backtest_trades.csv")
    lines = ["ts,venue,symbol,order_id,status,request_json\n"]
    for row in persistence.fetch_orders():
        lines.append(
            f"{row['ts']},{row['venue']},{row['symbol']},{row['order_id']},{row['status']},{row['request_json']}\n"
        )
    trades_csv.write_text("".join(lines), encoding="utf-8")

    logger.info(
        event="backtest_summary",
        details={
            "total_return": metrics.total_return,
            "max_drawdown": metrics.drawdown,
            "sharpe": metrics.sharpe,
            "win_rate": win_rate,
            "avg_trade": avg_trade,
        },
    )


if __name__ == "__main__":
    main()
