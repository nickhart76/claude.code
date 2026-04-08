"""Phantom trading portfolio backed by SQLite.

Keeps cash, open positions, and a full trade log. All trades are pretend —
no broker, no real money. Position cost basis is computed weighted-average.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional

from ..config import DB_PATH


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Trade:
    id: int
    ticker: str
    side: Side
    quantity: float
    price: float
    timestamp: datetime
    note: str = ""

    @property
    def notional(self) -> float:
        return self.quantity * self.price


@dataclass
class Position:
    ticker: str
    quantity: float
    avg_cost: float

    def market_value(self, last_price: float) -> float:
        return self.quantity * last_price

    def unrealized_pl(self, last_price: float) -> float:
        return (last_price - self.avg_cost) * self.quantity


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    ticker TEXT PRIMARY KEY,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    timestamp TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS realized_pnl (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    pnl REAL NOT NULL,
    timestamp TEXT NOT NULL
);
"""


class Portfolio:
    """SQLite-backed phantom portfolio."""

    def __init__(self, db_path: Path | str = DB_PATH, starting_cash: float = 100_000.0):
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        if self._get_meta("cash") is None:
            self._set_meta("cash", str(starting_cash))
            self._set_meta("starting_cash", str(starting_cash))

    # ---- meta helpers -------------------------------------------------

    def _get_meta(self, key: str) -> Optional[str]:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    @property
    def cash(self) -> float:
        return float(self._get_meta("cash") or 0.0)

    @property
    def starting_cash(self) -> float:
        return float(self._get_meta("starting_cash") or 0.0)

    # ---- position state ----------------------------------------------

    def position(self, ticker: str) -> Optional[Position]:
        row = self._conn.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE ticker = ?",
            (ticker.upper(),),
        ).fetchone()
        if not row or row["quantity"] == 0:
            return None
        return Position(
            ticker=row["ticker"],
            quantity=float(row["quantity"]),
            avg_cost=float(row["avg_cost"]),
        )

    def positions(self) -> list[Position]:
        rows = self._conn.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE quantity != 0"
        ).fetchall()
        return [
            Position(r["ticker"], float(r["quantity"]), float(r["avg_cost"])) for r in rows
        ]

    # ---- trading ------------------------------------------------------

    def buy(self, ticker: str, quantity: float, price: float, note: str = "") -> Trade:
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be positive")
        cost = quantity * price
        if cost > self.cash + 1e-9:
            raise ValueError(
                f"insufficient cash: need ${cost:,.2f}, have ${self.cash:,.2f}"
            )

        with closing(self._conn.cursor()) as cur:
            cur.execute("BEGIN")
            cur.execute("UPDATE meta SET value = ? WHERE key = 'cash'", (str(self.cash - cost),))

            existing = self.position(ticker)
            if existing:
                new_qty = existing.quantity + quantity
                new_cost = (
                    existing.avg_cost * existing.quantity + price * quantity
                ) / new_qty
                cur.execute(
                    "UPDATE positions SET quantity = ?, avg_cost = ? WHERE ticker = ?",
                    (new_qty, new_cost, ticker.upper()),
                )
            else:
                cur.execute(
                    "INSERT INTO positions(ticker, quantity, avg_cost) VALUES(?, ?, ?)",
                    (ticker.upper(), quantity, price),
                )
            ts = datetime.now(timezone.utc).isoformat()
            cur.execute(
                "INSERT INTO trades(ticker, side, quantity, price, timestamp, note) "
                "VALUES(?, 'BUY', ?, ?, ?, ?)",
                (ticker.upper(), quantity, price, ts, note),
            )
            trade_id = cur.lastrowid
            self._conn.commit()
        return Trade(trade_id, ticker.upper(), Side.BUY, quantity, price, datetime.fromisoformat(ts), note)

    def sell(self, ticker: str, quantity: float, price: float, note: str = "") -> Trade:
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be positive")
        existing = self.position(ticker)
        if existing is None or existing.quantity < quantity - 1e-9:
            have = existing.quantity if existing else 0.0
            raise ValueError(f"insufficient shares of {ticker}: want {quantity}, have {have}")

        proceeds = quantity * price
        realized = (price - existing.avg_cost) * quantity

        with closing(self._conn.cursor()) as cur:
            cur.execute("BEGIN")
            cur.execute("UPDATE meta SET value = ? WHERE key = 'cash'", (str(self.cash + proceeds),))

            remaining = existing.quantity - quantity
            if remaining < 1e-9:
                cur.execute("DELETE FROM positions WHERE ticker = ?", (ticker.upper(),))
            else:
                cur.execute(
                    "UPDATE positions SET quantity = ? WHERE ticker = ?",
                    (remaining, ticker.upper()),
                )

            ts = datetime.now(timezone.utc).isoformat()
            cur.execute(
                "INSERT INTO trades(ticker, side, quantity, price, timestamp, note) "
                "VALUES(?, 'SELL', ?, ?, ?, ?)",
                (ticker.upper(), quantity, price, ts, note),
            )
            trade_id = cur.lastrowid
            cur.execute(
                "INSERT INTO realized_pnl(ticker, pnl, timestamp) VALUES(?, ?, ?)",
                (ticker.upper(), realized, ts),
            )
            self._conn.commit()
        return Trade(trade_id, ticker.upper(), Side.SELL, quantity, price, datetime.fromisoformat(ts), note)

    # ---- reporting ----------------------------------------------------

    def trades(self) -> list[Trade]:
        rows = self._conn.execute(
            "SELECT id, ticker, side, quantity, price, timestamp, note "
            "FROM trades ORDER BY id"
        ).fetchall()
        return [
            Trade(
                id=r["id"],
                ticker=r["ticker"],
                side=Side(r["side"]),
                quantity=float(r["quantity"]),
                price=float(r["price"]),
                timestamp=datetime.fromisoformat(r["timestamp"]),
                note=r["note"] or "",
            )
            for r in rows
        ]

    def realized_pnl_total(self) -> float:
        row = self._conn.execute("SELECT COALESCE(SUM(pnl), 0.0) AS s FROM realized_pnl").fetchone()
        return float(row["s"])

    def equity(self, last_prices: dict[str, float]) -> float:
        total = self.cash
        for pos in self.positions():
            px = last_prices.get(pos.ticker.upper())
            if px is None:
                continue
            total += pos.market_value(px)
        return total

    def reset(self, starting_cash: Optional[float] = None) -> None:
        self._conn.execute("DELETE FROM positions")
        self._conn.execute("DELETE FROM trades")
        self._conn.execute("DELETE FROM realized_pnl")
        if starting_cash is not None:
            self._set_meta("starting_cash", str(starting_cash))
            self._set_meta("cash", str(starting_cash))
        else:
            self._set_meta("cash", self._get_meta("starting_cash") or "0.0")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Portfolio":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
