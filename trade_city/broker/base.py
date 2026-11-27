"""Interface que a mesa usa para falar com qualquer corretora."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..models import AssetClass, Bar, TradePlan


@dataclass(frozen=True)
class Fill:
    order_id: str
    price: float
    qty: float


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: float
    avg_entry_price: float


class Broker(ABC):
    paper: bool = True

    @abstractmethod
    def get_bars(self, symbol: str, asset_class: AssetClass, timeframe: str, lookback_days: int) -> list[Bar]:
        """Candles fechados, do mais antigo ao mais novo."""

    @abstractmethod
    def latest_price(self, symbol: str, asset_class: AssetClass) -> float: ...

    @abstractmethod
    def buying_power(self) -> float: ...

    @abstractmethod
    def is_market_open(self, asset_class: AssetClass) -> bool: ...

    @abstractmethod
    def get_position(self, symbol: str) -> Position | None: ...

    @abstractmethod
    def submit_entry(self, plan: TradePlan, asset_class: AssetClass) -> Fill:
        """Envia a compra. Em ações, a ordem já leva stop loss e stop gain na corretora."""

    @abstractmethod
    def close_position(self, symbol: str) -> Fill:
        """Cancela ordens pendentes do ativo e zera a posição."""

    @abstractmethod
    def last_exit_price(self, symbol: str) -> float | None:
        """Preço da última venda executada (quando um stop da corretora fechou a posição)."""
