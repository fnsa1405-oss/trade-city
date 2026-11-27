"""Tipos básicos que circulam pela linha de produção."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    EQUITY = "equity"


@dataclass(frozen=True)
class Bar:
    ts: datetime  # horário de abertura do candle, com fuso (UTC)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class Signal:
    """Saída do Analista: uma ideia de compra, ainda sem stops nem tamanho."""

    trader: str
    symbol: str
    price: float
    reason: str
    ts: datetime


@dataclass(frozen=True)
class TradePlan:
    """Saída do Guardião de Risco: o sinal com stops e tamanho definidos."""

    signal: Signal
    qty: float
    stop_loss: float
    take_profit: float
    risk_amount: float  # quanto se perde se o stop for atingido
    mood: str

    @property
    def entry(self) -> float:
        return self.signal.price

    @property
    def notional(self) -> float:
        return self.qty * self.entry

    @property
    def reward_ratio(self) -> float:
        risk = self.entry - self.stop_loss
        return (self.take_profit - self.entry) / risk if risk > 0 else 0.0


@dataclass(frozen=True)
class AuditResult:
    """Saída do Auditor: aprovado ou não, e os motivos."""

    approved: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClosedTrade:
    trader: str
    symbol: str
    qty: float
    entry_price: float
    exit_price: float
    pnl: float
    opened_at: datetime
    closed_at: datetime
    exit_reason: str

    @property
    def won(self) -> bool:
        return self.pnl > 0
