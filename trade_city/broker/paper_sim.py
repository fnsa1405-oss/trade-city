"""Corretora de mentira, em memória, para testes."""
from __future__ import annotations

import itertools

from ..models import AssetClass, Bar, TradePlan
from .base import Broker, Fill, Position


class SimBroker(Broker):
    paper = True

    def __init__(self, cash: float = 100_000.0):
        self.cash = cash
        self.bars: dict[str, list[Bar]] = {}
        self.prices: dict[str, float] = {}
        self.positions: dict[str, Position] = {}
        self.market_open = True
        self.exits: dict[str, float] = {}
        self.sides: dict[str, int] = {}
        self._ids = itertools.count(1)

    def get_bars(self, symbol, asset_class, timeframe, lookback_days):
        return list(self.bars.get(symbol, []))

    def latest_price(self, symbol, asset_class):
        if symbol in self.prices:
            return self.prices[symbol]
        return self.bars[symbol][-1].close

    def buying_power(self):
        return self.cash

    def is_market_open(self, asset_class):
        return True if asset_class is AssetClass.CRYPTO else self.market_open

    def get_position(self, symbol):
        return self.positions.get(symbol)

    def submit_entry(self, plan: TradePlan, asset_class):
        price = plan.entry
        self.cash -= price * plan.qty
        self.sides[plan.signal.symbol] = plan.side.sign
        self.positions[plan.signal.symbol] = Position(plan.signal.symbol, plan.qty, price)
        return Fill(str(next(self._ids)), price, plan.qty)

    def close_position(self, symbol):
        pos = self.positions.pop(symbol)
        price = self.prices.get(symbol, pos.avg_entry_price)
        sign = self.sides.pop(symbol, 1)
        self.cash += pos.avg_entry_price * pos.qty + (price - pos.avg_entry_price) * pos.qty * sign
        self.exits[symbol] = price
        return Fill(str(next(self._ids)), price, pos.qty)

    def stop_out(self, symbol: str, price: float) -> None:
        """Simula a corretora executando um stop sozinha."""
        pos = self.positions.pop(symbol)
        self.cash += price * pos.qty
        self.exits[symbol] = price

    def last_exit_price(self, symbol):
        return self.exits.get(symbol)
