from __future__ import annotations

from collections.abc import Sequence

from ..indicators import highest, sma
from ..models import Bar
from .base import Strategy


class TrendFollower(Strategy):
    """Seguidor de tendência: média rápida acima da lenta e rompimento da máxima recente."""

    name = "seguidor de tendência"
    description = "Compra quando a média de {fast} está acima da de {slow} e o preço rompe a máxima de {breakout} candles."

    def __init__(self, fast: int = 20, slow: int = 50, breakout: int = 20):
        if fast >= slow:
            raise ValueError("a média rápida precisa ser menor que a lenta")
        self.fast, self.slow, self.breakout = fast, slow, breakout
        self.min_bars = max(slow, breakout + 1)
        self.description = self.description.format(fast=fast, slow=slow, breakout=breakout)

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        if len(bars) < self.min_bars:
            return None
        closes = [b.close for b in bars]
        fast, slow = sma(closes, self.fast), sma(closes, self.slow)
        prior_high = highest([b.high for b in bars[:-1]], self.breakout)
        if fast is None or slow is None or prior_high is None:
            return None
        if fast > slow and closes[-1] > prior_high:
            return f"tendência de alta (MM{self.fast} > MM{self.slow}) e rompimento da máxima de {self.breakout} candles"
        return None
