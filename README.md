# Multi-Asset Trading Bot (IBKR Stocks + Crypto)

Production-grade framework for a deterministic trading bot that can run **backtests**, **paper trading**, and **live trading** across US stocks (IBKR) and crypto (Coinbase Advanced Trade by default). The core engine is venue-agnostic and uses structured **intents** rather than direct order placement.

> **Warning:** This is a framework. You are responsible for compliance, configuration, and validation before any live use.

## Features
- Deterministic strategies (no LLM trade decisions).
- Venue-agnostic engine with interchangeable adapters (IBKR + crypto).
- Paper-first parity: same engine/strategy/risk for paper + live.
- Idempotent per-candle execution.
- SQLite persistence for decisions, orders, fills, and positions.
- Risk guardrails: max notional, max trades/day, daily loss kill switch, drawdown, spread/vol filters, cooldown, and manual kill switch file.
- JSON logs with structured context.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Optional dependencies:

```bash
pip install -e .[ibkr]
```

## Configuration

Configs live in `bot/config/`:
- `runtime.yaml`: runtime loop settings and Telegram alerts.
- `instruments.yaml`: per-symbol strategy parameters and allocations.
- `risk.yaml`: risk guardrails and kill switch path.

### Example

```yaml
# bot/config/runtime.yaml
mode: paper
live_trading_enabled: false
allow_extended_hours: false
loop_interval_seconds: 5
lookback_bars: 200
ibkr_host: 127.0.0.1
ibkr_port: 7497
ibkr_client_id: 1
```

```yaml
# bot/config/risk.yaml (excerpt)
cooldown_minutes_after_n_losses: 30
loss_streak_threshold: 2
volatility_method: atr_pct
volatility_window: 14
```

## Running

### Backtest
Backtests use CSVs from the `data/` directory (one file per symbol/timeframe).

```bash
python -m bot.scripts.run_backtest
```

Expected CSV filename format: `SYMBOL-TIMEFRAME.csv` (e.g., `SPY-5m.csv`, `BTC-USD-5m.csv`) with columns: `timestamp,open,high,low,close,volume`.

### Paper
```bash
python -m bot.scripts.run_paper
```

Paper mode uses real data adapters and a `PaperAdapter` for simulated fills.

### Live
```bash
python -m bot.scripts.run_live
```

Set `live_trading_enabled: true` in `runtime.yaml` first.

## Risk controls
- Max notional per symbol
- Max portfolio gross exposure
- Max trades/day (global + per symbol)
- Daily loss + max drawdown kill switches
- Cooldown after N-loss streak
- Max spread/volatility filters
- Min equity required
- Manual kill switch file: create `./KILL_SWITCH`

## Environment variables
- **IBKR**: connect via `ib_insync` (TWS or IB Gateway must be running).
- **Coinbase**: set API credentials via environment variables in your run wrapper (adapter uses Coinbase Advanced Trade public data endpoints; trading endpoints are stubbed in MVP).

## Repository layout

```
bot/
  config/
  core/
  adapters/
  strategies/
  research/
  scripts/
  tests/
```

## Notes
- Coinbase trading endpoints are stubbed in the MVP; use paper trading for order simulation.
- IBKR adapter includes minimal scaffolding and TODOs for live placement.
- Time-based stops are not implemented in the MVP; stop-loss/take-profit exits are evaluated on bar close.
