"""Estratégia = o método do Analista de um trader."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..models import Bar, Entry, Side


class Strategy(ABC):
    name: str = "estratégia"
    description: str = ""
    min_bars: int = 1  # candles necessários para decidir
    lookback: int = 0  # janela que a estratégia olha (0 = min_bars)
    has_exit: bool = False  # True quando a estratégia tem regra própria de saída (should_exit)
    day_trade: bool = False  # True = nunca dorme posicionado (zera antes do fim do pregão)

    @property
    def window(self) -> int:
        return max(self.lookback, self.min_bars)

    @abstractmethod
    def analyze(self, bars: Sequence[Bar]) -> str | None:
        """Olha os candles fechados (o último é o mais recente) e devolve o motivo
        de uma compra, ou None se não há entrada."""

    def should_exit(self, bars: Sequence[Bar]) -> bool:
        """Saída antecipada pela própria estratégia (além dos stops)."""
        return False

    # interface usada pela mesa e pelo backtest -----------------------------
    def prepare(self, bars: Sequence[Bar]) -> None:
        """Chamado com o histórico inteiro antes de decidir. Estratégias pesadas
        (vários tempos gráficos) calculam tudo aqui de uma vez, sem olhar o futuro."""

    def decide(self, bars: Sequence[Bar]) -> Entry | None:
        reason = self.analyze(bars)
        return Entry(reason) if reason else None

    def exit_signal(self, bars: Sequence[Bar], side: Side) -> bool:
        return self.should_exit(bars) if side is Side.LONG else False
