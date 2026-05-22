from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class DecisionLog:
    symbol: str
    score: float | None
    decision: str
    reason: str
    notional: float | None
    estimated_cost: float | None
    order_id: str | None


class Journal:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with closing(self._connect()) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    score REAL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    notional REAL,
                    estimated_cost REAL,
                    order_id TEXT
                );

                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty REAL,
                    notional REAL,
                    estimated_cost REAL NOT NULL,
                    order_id TEXT,
                    status TEXT
                );

                CREATE TABLE IF NOT EXISTS daily_equity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    equity REAL NOT NULL,
                    cash REAL,
                    buying_power REAL
                );
                """
            )
            conn.commit()

    def log_decision(self, entry: DecisionLog) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO decisions (
                    timestamp, symbol, score, decision, reason, notional, estimated_cost, order_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utcnow(),
                    entry.symbol,
                    entry.score,
                    entry.decision,
                    entry.reason,
                    entry.notional,
                    entry.estimated_cost,
                    entry.order_id,
                ),
            )
            conn.commit()

    def log_trade(
        self,
        *,
        symbol: str,
        side: str,
        qty: float | None,
        notional: float | None,
        estimated_cost: float,
        order_id: str | None,
        status: str | None,
    ) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO trades (
                    timestamp, symbol, side, qty, notional, estimated_cost, order_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (_utcnow(), symbol, side, qty, notional, estimated_cost, order_id, status),
            )
            conn.commit()

    def log_daily_equity(self, *, equity: float, cash: float | None, buying_power: float | None) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO daily_equity (timestamp, equity, cash, buying_power)
                VALUES (?, ?, ?, ?)
                """,
                (_utcnow(), equity, cash, buying_power),
            )
            conn.commit()

    def get_day_start_equity(self) -> float | None:
        today = datetime.now(timezone.utc).date().isoformat()
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT equity
                FROM daily_equity
                WHERE substr(timestamp, 1, 10) = ?
                ORDER BY timestamp ASC
                LIMIT 1
                """,
                (today,),
            ).fetchone()
        return float(row[0]) if row else None


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()
