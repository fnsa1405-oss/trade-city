from __future__ import annotations

from collections.abc import Sequence

from ..indicators import rsi, sma
from ..models import Bar
from .base import Strategy


class MeanReversion(Strategy):
    """Retorno à média: compra sobrevenda curta dentro de tendência de alta longa."""

    name = "retorno à média"
    description = "Compra quando o IFR({rsi_n}) cai abaixo de {threshold} com o preço acima da média de {trend} e sai acima da média de {exit_n}."

    def __init__(self, rsi_n: int = 2, threshold: float = 10.0, trend: int = 200, exit_n: int = 5):
        self.rsi_n, self.threshold, self.trend, self.exit_n = rsi_n, threshold, trend, exit_n
        self.min_bars = max(trend, rsi_n + 1, exit_n)
        self.description = self.description.format(rsi_n=rsi_n, threshold=threshold, trend=trend, exit_n=exit_n)

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        if len(bars) < self.min_bars:
            return None
        closes = [b.close for b in bars]
        trend, value = sma(closes, self.trend), rsi(closes, self.rsi_n)
        if trend is None or value is None:
            return None
        if closes[-1] > trend and value < self.threshold:
            return f"sobrevenda (IFR{self.rsi_n} = {value:.1f}) acima da média de {self.trend}"
        return None

    def should_exit(self, bars: Sequence[Bar]) -> bool:
        exit_avg = sma([b.close for b in bars], self.exit_n)
        return exit_avg is not None and bars[-1].close > exit_avg
