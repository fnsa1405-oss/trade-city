"""Tipos básicos que circulam pela linha de produção."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    EQUITY = "equity"


class Side(str, Enum):
    LONG = "compra"
    SHORT = "venda"  # venda a descoberto: ganha quando o preço cai (só em ações)

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1


@dataclass(frozen=True)
class Entry:
    """Decisão do Analista: o lado, o motivo e, se o gráfico mostrar, onde fica o stop
    (fundo ou topo que invalida a ideia). Sem stop, o Guardião usa o ATR."""

    reason: str
    side: Side = Side.LONG
    stop: float | None = None
    trigger: float | None = None  # ordem stop: entra quando o preço romper este nível
    valid_bars: int = 1  # por quantos candles a ordem stop vale


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
    side: Side = Side.LONG
    stop: float | None = None  # stop sugerido pelo gráfico


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
    def side(self) -> Side:
        return self.signal.side

    @property
    def notional(self) -> float:
        return self.qty * self.entry

    @property
    def reward_ratio(self) -> float:
        sign = self.side.sign
        risk = (self.entry - self.stop_loss) * sign
        return (self.take_profit - self.entry) * sign / risk if risk > 0 else 0.0


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
    side: Side = Side.LONG
    features: tuple | None = None  # "clima" do gráfico na entrada, para o cérebro aprender

    @property
    def won(self) -> bool:
        return self.pnl > 0
