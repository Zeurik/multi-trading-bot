from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from bot.core.intents import intent_to_dict
from bot.core.types import OrderRequest, RiskDecision


class Persistence:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self.ensure_tables()

    def ensure_tables(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                venue TEXT,
                symbol TEXT,
                timeframe TEXT,
                candle_ts TEXT,
                intent_json TEXT,
                risk_json TEXT,
                decision_hash TEXT
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                venue TEXT,
                symbol TEXT,
                client_order_id TEXT,
                order_id TEXT,
                request_json TEXT,
                status TEXT,
                filled_qty REAL,
                avg_fill_price REAL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS fills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                venue TEXT,
                symbol TEXT,
                order_id TEXT,
                qty REAL,
                price REAL,
                fee REAL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS positions_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                venue TEXT,
                equity REAL,
                cash REAL,
                positions_json TEXT
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def has_decision(self, venue: str, symbol: str, timeframe: str, candle_ts: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM decisions WHERE venue = ? AND symbol = ? AND timeframe = ? AND candle_ts = ?
            LIMIT 1
            """,
            (venue, symbol, timeframe, candle_ts),
        )
        return cursor.fetchone() is not None

    def record_decision(
        self,
        timestamp: datetime,
        venue: str,
        symbol: str,
        timeframe: str,
        candle_ts: str,
        intent: Optional[Dict[str, Any]],
        risk: Dict[str, Any],
    ) -> str:
        payload = {
            "intent": intent,
            "risk": risk,
            "symbol": symbol,
            "venue": venue,
            "timeframe": timeframe,
            "candle_ts": candle_ts,
        }
        decision_hash = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO decisions (ts, venue, symbol, timeframe, candle_ts, intent_json, risk_json, decision_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp.isoformat(),
                venue,
                symbol,
                timeframe,
                candle_ts,
                json.dumps(intent),
                json.dumps(risk),
                decision_hash,
            ),
        )
        self._conn.commit()
        return decision_hash

    def record_order(
        self,
        timestamp: datetime,
        venue: str,
        symbol: str,
        client_order_id: str,
        order_id: str,
        request: OrderRequest,
        status: str,
        filled_qty: float = 0.0,
        avg_fill_price: Optional[float] = None,
    ) -> None:
        request_payload = {
            "symbol": request.symbol,
            "venue": request.venue.value,
            "side": request.side.value,
            "quantity": request.quantity,
            "order_type": request.order_type.value,
            "limit_price": request.limit_price,
            "client_order_id": request.client_order_id,
            "time_in_force": request.time_in_force,
        }
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO orders (ts, venue, symbol, client_order_id, order_id, request_json, status, filled_qty, avg_fill_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp.isoformat(),
                venue,
                symbol,
                client_order_id,
                order_id,
                json.dumps(request_payload),
                status,
                filled_qty,
                avg_fill_price,
            ),
        )
        self._conn.commit()

    def record_fill(
        self,
        timestamp: datetime,
        venue: str,
        symbol: str,
        order_id: str,
        qty: float,
        price: float,
        fee: float,
    ) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO fills (ts, venue, symbol, order_id, qty, price, fee)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp.isoformat(),
                venue,
                symbol,
                order_id,
                qty,
                price,
                fee,
            ),
        )
        self._conn.commit()

    def record_positions_snapshot(
        self,
        timestamp: datetime,
        venue: str,
        equity: float,
        cash: float,
        positions: Iterable[Dict[str, Any]],
    ) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO positions_snapshots (ts, venue, equity, cash, positions_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                timestamp.isoformat(),
                venue,
                equity,
                cash,
                json.dumps(list(positions)),
            ),
        )
        self._conn.commit()

    def fetch_orders(self) -> Iterable[sqlite3.Row]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT ts, venue, symbol, order_id, status, request_json FROM orders")
        return cursor.fetchall()


def risk_to_dict(risk: RiskDecision) -> Dict[str, Any]:
    return {
        "approved": risk.approved,
        "adjusted_intent": intent_to_dict(risk.adjusted_intent) if risk.adjusted_intent else None,
        "rejection_reason": risk.rejection_reason,
        "risk_tags": risk.risk_tags,
    }
