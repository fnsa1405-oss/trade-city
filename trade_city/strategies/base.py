"""Estratégia = o método do Analista de um trader."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..models import Bar


class Strategy(ABC):
    name: str = "estratégia"
    description: str = ""
    min_bars: int = 1  # candles necessários para decidir
    lookback: int = 0  # janela que a estratégia olha (0 = min_bars)
    has_exit: bool = False  # True quando a estratégia tem regra própria de saída (should_exit)

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
