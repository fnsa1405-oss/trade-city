"""Corretora simulada da própria mesa: preços reais de fontes públicas, dinheiro de mentira.

Não precisa de conta nem de chave e funciona de qualquer país. Emula ordens com
stop loss e stop gain na corretora (como uma ordem OCO): a cada ciclo, confere os
candles de 1h desde a última verificação e executa o stop ou o alvo que o preço
tocou, mesmo que a mesa estivesse desligada naquela hora.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ..models import AssetClass, Bar, Side, TradePlan
from .base import Broker, Fill, Position

NY = ZoneInfo("America/New_York")

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_account (id INTEGER PRIMARY KEY CHECK (id = 1), cash REAL NOT NULL);
CREATE TABLE IF NOT EXISTS paper_positions (
    symbol TEXT PRIMARY KEY,
    asset_class TEXT NOT NULL,
    qty REAL NOT NULL,
    entry REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    opened_at TEXT NOT NULL,
    last_check TEXT NOT NULL,
    side TEXT NOT NULL DEFAULT 'compra'
);
CREATE TABLE IF NOT EXISTS paper_exits (id INTEGER PRIMARY KEY, symbol TEXT NOT NULL, price REAL NOT NULL, ts TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS paper_orders (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, qty REAL NOT NULL, price REAL NOT NULL);
"""


class PublicFeed:
    """Preços das fontes públicas (Coinbase e Yahoo Finance)."""

    def get_bars(self, symbol: str, asset_class: AssetClass, timeframe: str, days: int) -> list[Bar]:
        from ..public_data import public_bars

        return public_bars(symbol, asset_class, timeframe, days)

    def latest_price(self, symbol: str, asset_class: AssetClass) -> float:
        from ..public_data import latest_price

        return latest_price(symbol, asset_class)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PaperBroker(Broker):
    paper = True

    def __init__(
        self,
        conn: sqlite3.Connection,
        feed=None,
        initial_cash: float = 30_000.0,
        clock: Callable[[], datetime] = _utcnow,
        crypto_fee: float = 0.001,
        slippage: float = 0.0005,
    ):
        self.conn = conn
        self.feed = feed or PublicFeed()
        self.clock = clock
        self.crypto_fee = crypto_fee
        self.slippage = slippage
        conn.executescript(SCHEMA)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(paper_positions)")}
        if "side" not in cols:
            conn.execute("ALTER TABLE paper_positions ADD COLUMN side TEXT NOT NULL DEFAULT 'compra'")
        conn.execute("INSERT OR IGNORE INTO paper_account (id, cash) VALUES (1, ?)", (initial_cash,))
        conn.commit()

    # custos -------------------------------------------------------------
    def _cost(self, asset_class: AssetClass) -> float:
        return self.slippage + (self.crypto_fee if asset_class is AssetClass.CRYPTO else 0.0)

    def _cash(self) -> float:
        return float(self.conn.execute("SELECT cash FROM paper_account WHERE id = 1").fetchone()[0])

    def _add_cash(self, amount: float) -> None:
        self.conn.execute("UPDATE paper_account SET cash = cash + ? WHERE id = 1", (amount,))

    def _order(self, symbol: str, side: str, qty: float, price: float) -> str:
        cur = self.conn.execute(
            "INSERT INTO paper_orders (ts, symbol, side, qty, price) VALUES (?, ?, ?, ?, ?)",
            (self.clock().isoformat(), symbol, side, qty, price),
        )
        return f"paper-{cur.lastrowid}"

    # Broker -------------------------------------------------------------
    def get_bars(self, symbol, asset_class, timeframe, lookback_days):
        return self.feed.get_bars(symbol, asset_class, timeframe, lookback_days)

    def latest_price(self, symbol, asset_class):
        return float(self.feed.latest_price(symbol, asset_class))

    def buying_power(self):
        return self._cash()

    def is_market_open(self, asset_class):
        if asset_class is AssetClass.CRYPTO:
            return True
        now = self.clock().astimezone(NY)
        return now.weekday() < 5 and time(9, 30) <= now.time() < time(16, 0)

    def get_position(self, symbol):
        row = self.conn.execute(
            "SELECT symbol, asset_class, qty, entry, stop_loss, take_profit, opened_at, last_check, side"
            " FROM paper_positions WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if row is None:
            return None
        if self._settle(row):
            return None
        return Position(symbol, row[2], row[3])

    def submit_entry(self, plan: TradePlan, asset_class):
        symbol = plan.signal.symbol
        if self.conn.execute("SELECT 1 FROM paper_positions WHERE symbol = ?", (symbol,)).fetchone():
            raise RuntimeError(f"já existe posição simulada em {symbol}")
        if plan.side is Side.SHORT and asset_class is AssetClass.CRYPTO:
            raise RuntimeError("cripto à vista não aceita venda a descoberto")
        sign = plan.side.sign
        price = self.latest_price(symbol, asset_class) * (1 + sign * self._cost(asset_class))
        cost = price * plan.qty  # na venda a descoberto, é a margem reservada
        if cost > self._cash() + 1e-6:
            raise RuntimeError("saldo simulado insuficiente")
        now = self.clock().isoformat()
        self._add_cash(-cost)
        self.conn.execute(
            "INSERT INTO paper_positions (symbol, asset_class, qty, entry, stop_loss, take_profit, opened_at, last_check, side)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (symbol, asset_class.value, plan.qty, price, plan.stop_loss, plan.take_profit, now, now, plan.side.value),
        )
        order_id = self._order(symbol, plan.side.value, plan.qty, price)
        self.conn.commit()
        return Fill(order_id, price, plan.qty)

    def close_position(self, symbol):
        row = self.conn.execute("SELECT asset_class, qty, side FROM paper_positions WHERE symbol = ?", (symbol,)).fetchone()
        if row is None:
            raise RuntimeError(f"sem posição simulada em {symbol}")
        asset_class, qty, sign = AssetClass(row[0]), row[1], Side(row[2]).sign
        price = self.latest_price(symbol, asset_class) * (1 - sign * self._cost(asset_class))
        order_id = self._exit(symbol, qty, price, "fechamento pela mesa")
        return Fill(order_id, price, qty)

    def last_exit_price(self, symbol):
        row = self.conn.execute(
            "SELECT price FROM paper_exits WHERE symbol = ? ORDER BY id DESC LIMIT 1", (symbol,)
        ).fetchone()
        return float(row[0]) if row else None

    # stops emulados ------------------------------------------------------
    def _exit(self, symbol: str, qty: float, price: float, reason: str) -> str:
        entry, side = self.conn.execute("SELECT entry, side FROM paper_positions WHERE symbol = ?", (symbol,)).fetchone()
        side = Side(side)
        self.conn.execute("DELETE FROM paper_positions WHERE symbol = ?", (symbol,))
        # devolve o que foi reservado na entrada mais o resultado
        self._add_cash(entry * qty + (price - entry) * qty * side.sign)
        self.conn.execute(
            "INSERT INTO paper_exits (symbol, price, ts, reason) VALUES (?, ?, ?, ?)",
            (symbol, price, self.clock().isoformat(), reason),
        )
        order_id = self._order(symbol, "zerou " + side.value, qty, price)
        self.conn.commit()
        return order_id

    def _settle(self, row) -> bool:
        """Executa stop ou alvo tocados desde a última verificação. True se a posição foi fechada."""
        symbol, asset_value, qty, _entry, stop, take, _opened, last_check, side_value = row
        asset_class = AssetClass(asset_value)
        sign = Side(side_value).sign
        long = sign > 0
        cost = self._cost(asset_class)
        since = datetime.fromisoformat(last_check)
        now = self.clock()
        # ações: candles de 1 min (day trade); cripto: 1 h (a Coinbase pagina de 300 em 300)
        timeframe = "1min" if asset_class is AssetClass.EQUITY else "1h"
        bars = self.feed.get_bars(symbol, asset_class, timeframe, (now - since).days + 2)
        for bar in bars:
            if bar.ts < since:
                continue  # candle começou antes da entrada ou já foi conferido
            if (bar.low <= stop) if long else (bar.high >= stop):
                worst = min(bar.open, stop) if long else max(bar.open, stop)
                self._exit(symbol, qty, worst * (1 - sign * cost), "stop loss")
                return True
            if (bar.high >= take) if long else (bar.low <= take):
                best = max(bar.open, take) if long else min(bar.open, take)
                self._exit(symbol, qty, best * (1 - sign * cost), "stop gain")
                return True
        price = self.latest_price(symbol, asset_class)
        if (price - stop) * sign <= 0:
            self._exit(symbol, qty, price * (1 - sign * cost), "stop loss")
            return True
        if (price - take) * sign >= 0:
            self._exit(symbol, qty, take * (1 - sign * cost), "stop gain")
            return True
        self.conn.execute("UPDATE paper_positions SET last_check = ? WHERE symbol = ?", (now.isoformat(), symbol))
        self.conn.commit()
        return False
