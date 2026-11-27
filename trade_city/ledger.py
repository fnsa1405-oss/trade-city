"""Livro de registros (SQLite): decisões, operações e travas."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class OpenTrade:
    id: int
    trader: str
    symbol: str
    qty: float
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: datetime


SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    trader TEXT NOT NULL,
    symbol TEXT NOT NULL,
    stage TEXT NOT NULL,
    approved INTEGER NOT NULL,
    detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY,
    trader TEXT NOT NULL,
    symbol TEXT NOT NULL,
    qty REAL NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    opened_at TEXT NOT NULL,
    broker_order_id TEXT,
    closed_at TEXT,
    exit_price REAL,
    pnl REAL,
    exit_reason TEXT
);
CREATE TABLE IF NOT EXISTS flags (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text)


class Ledger:
    def __init__(self, path: str = "trade_city.db"):
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # decisões -----------------------------------------------------------
    def record_decision(self, ts: datetime, trader: str, symbol: str, stage: str, approved: bool, detail: str) -> None:
        self.conn.execute(
            "INSERT INTO decisions (ts, trader, symbol, stage, approved, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (_iso(ts), trader, symbol, stage, int(approved), detail),
        )
        self.conn.commit()

    def decisions(self, trader: str | None = None, limit: int = 50) -> list[tuple]:
        sql = "SELECT ts, trader, symbol, stage, approved, detail FROM decisions"
        args: tuple = ()
        if trader:
            sql += " WHERE trader = ?"
            args = (trader,)
        sql += " ORDER BY id DESC LIMIT ?"
        return list(self.conn.execute(sql, (*args, limit)))

    # operações ----------------------------------------------------------
    def open_trade(
        self,
        trader: str,
        symbol: str,
        qty: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        opened_at: datetime,
        broker_order_id: str | None = None,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO trades (trader, symbol, qty, entry_price, stop_loss, take_profit, opened_at, broker_order_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (trader, symbol, qty, entry_price, stop_loss, take_profit, _iso(opened_at), broker_order_id),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def open_trade_for(self, trader: str) -> OpenTrade | None:
        row = self.conn.execute(
            "SELECT id, trader, symbol, qty, entry_price, stop_loss, take_profit, opened_at"
            " FROM trades WHERE trader = ? AND closed_at IS NULL ORDER BY id DESC LIMIT 1",
            (trader,),
        ).fetchone()
        if row is None:
            return None
        return OpenTrade(*row[:7], opened_at=_dt(row[7]))

    def close_trade(self, trade_id: int, exit_price: float, closed_at: datetime, reason: str) -> float:
        qty, entry = self.conn.execute("SELECT qty, entry_price FROM trades WHERE id = ?", (trade_id,)).fetchone()
        pnl = (exit_price - entry) * qty
        self.conn.execute(
            "UPDATE trades SET closed_at = ?, exit_price = ?, pnl = ?, exit_reason = ? WHERE id = ?",
            (_iso(closed_at), exit_price, pnl, reason, trade_id),
        )
        self.conn.commit()
        return pnl

    def closed_pnls(self, trader: str, since: datetime | None = None) -> list[float]:
        """Resultados das operações fechadas, da mais antiga à mais nova."""
        sql = "SELECT pnl FROM trades WHERE trader = ? AND closed_at IS NOT NULL"
        args: tuple = (trader,)
        if since is not None:
            sql += " AND closed_at >= ?"
            args = (trader, _iso(since))
        sql += " ORDER BY closed_at, id"
        return [row[0] for row in self.conn.execute(sql, args)]

    # travas -------------------------------------------------------------
    def set_flag(self, name: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO flags (name, value) VALUES (?, ?)", (name, value))
        self.conn.commit()

    def flag(self, name: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM flags WHERE name = ?", (name,)).fetchone()
        return row[0] if row else default

    @property
    def kill_switch(self) -> bool:
        return self.flag("kill_switch") == "on"

    @kill_switch.setter
    def kill_switch(self, on: bool) -> None:
        self.set_flag("kill_switch", "on" if on else "off")
