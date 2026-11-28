"""Estratégias da pesquisa de 28/11/2026: anomalias e regras com estudos publicados e
replicados, para os traders que ainda não passaram na escola (criptos e IWM).

Todas só compram (entrada na abertura do candle seguinte ao sinal) e o Guardião sempre
coloca stop loss.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from ..indicators import rsi, sma
from ..models import Bar
from .published import _WithExit


class TimeSeriesMomentum(_WithExit):
    """Momento de série temporal: compra quando o retorno dos últimos `n` candles é positivo
    e o preço está acima da média de `n`; sai quando o retorno fica negativo.
    Fontes: Moskowitz, Ooi e Pedersen (2012), "Time Series Momentum", JFE; Liu e Tsyvinski
    (2021), "Risks and Returns of Cryptocurrency", RFS (momento de 1 a 4 semanas nas criptos).
    https://doi.org/10.1016/j.jfineco.2011.11.003 e https://doi.org/10.1093/rfs/hhaa113"""

    def __init__(self, n: int = 28):
        self.n = n
        self.name = f"Momento de série temporal ({n} candles)"
        self.description = f"Compra com retorno de {n} candles positivo e preço acima da média de {n}; sai quando o retorno vira negativo."
        self.min_bars = n + 2

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        if len(bars) < self.min_bars:
            return None
        closes = [b.close for b in bars]
        avg = sma(closes, self.n)
        past = closes[-self.n - 1]
        prev_past = closes[-self.n - 2]
        now_up = closes[-1] > past and avg is not None and closes[-1] > avg
        was_up = closes[-2] > prev_past
        if now_up and not was_up:
            return f"momento: retorno de {self.n} candles virou positivo ({closes[-1] / past - 1:+.1%})"
        return None

    def should_exit(self, bars: Sequence[Bar]) -> bool:
        if len(bars) < self.n + 1:
            return False
        return bars[-1].close < bars[-self.n - 1].close


class TurnOfMonth(_WithExit):
    """Virada do mês: compra no último pregão do mês e sai no fechamento do 3º pregão do mês
    seguinte. Só no gráfico diário.
    Fontes: Lakonishok e Smidt (1988), RFS; McConnell e Xu (2008), "Equity Returns at the
    Turn of the Month", Financial Analysts Journal. https://doi.org/10.2469/faj.v64.n2.11"""

    name = "Virada do mês"
    description = "Compra no último pregão do mês e sai no 3º pregão do mês seguinte."
    min_bars = 5

    @staticmethod
    def _daily(bars: Sequence[Bar]) -> bool:
        return len(bars) >= 2 and bars[-1].ts - bars[-2].ts >= timedelta(hours=20)

    @staticmethod
    def _date(bars: Sequence[Bar], b: Bar):
        """Data do candle: em UTC nas criptos (que operam no fim de semana), em Nova York nas ações."""
        from datetime import timezone

        from ..intraday import NY

        crypto = any(x.ts.astimezone(timezone.utc).weekday() >= 5 for x in bars[-10:])
        return b.ts.astimezone(timezone.utc if crypto else NY).date(), crypto

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        if len(bars) < self.min_bars or not self._daily(bars):
            return None
        today, crypto = self._date(bars, bars[-1])
        nxt = today + timedelta(days=1)
        while not crypto and nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        if nxt.month != today.month:  # amanhã já é o mês seguinte: hoje é o último pregão
            return "virada do mês: último pregão"
        return None

    def should_exit(self, bars: Sequence[Bar]) -> bool:
        if not self._daily(bars):
            return False
        month = self._date(bars, bars[-1])[0].month
        count = 0
        for b in reversed(bars):
            if self._date(bars, b)[0].month != month:
                break
            count += 1
        return count >= 3


class IBSReversion(_WithExit):
    """Força interna do candle (IBS): compra quando o fechamento fica nos 20% de baixo do
    candle, acima da média de 200, e sai quando fecha nos 20% de cima.
    Fontes: Pagonidis (2014), "The IBS Effect: Mean Reversion in Equity ETFs", NAAIM; e
    Quantpedia, "Internal Bar Strength". https://www.naaim.org/wp-content/uploads/2014/04/00V_Alexander_Pagonidis_The-IBS-Effect-Mean-Reversion-in-Equity-ETFs-1.pdf"""

    def __init__(self, low: float = 0.2, high: float = 0.8, trend: int = 200):
        self.low, self.high, self.trend = low, high, trend
        self.name = f"IBS < {low:.1f} acima da MM{trend}"
        self.description = f"Compra com fechamento nos {low:.0%} de baixo do candle, a favor da média de {trend}; sai nos {1 - high:.0%} de cima."
        self.min_bars = trend + 1

    @staticmethod
    def _ibs(b: Bar) -> float:
        return (b.close - b.low) / (b.high - b.low) if b.high > b.low else 0.5

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        if len(bars) < self.min_bars:
            return None
        avg = sma([b.close for b in bars], self.trend)
        b = bars[-1]
        if avg is not None and b.close > avg and self._ibs(b) < self.low:
            return f"IBS em {self._ibs(b):.2f} acima da MM{self.trend}"
        return None

    def should_exit(self, bars: Sequence[Bar]) -> bool:
        return self._ibs(bars[-1]) > self.high


class CumulativeRSI(_WithExit):
    """IFR(2) acumulado de Connors e Alvarez: acima da MM200, compra quando a soma do IFR(2)
    dos 2 últimos candles fica abaixo de 35; sai com IFR(2) acima de 65.
    Fonte: Connors e Alvarez, "Short Term Trading Strategies That Work" (2008), resumido em
    https://www.quantifiedstrategies.com/cumulative-rsi-strategy/"""

    name = "IFR(2) acumulado (Connors/Alvarez)"
    description = "Acima da MM200, compra com IFR(2) de 2 dias somando menos de 35; sai com IFR(2) acima de 65."
    min_bars = 202

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        if len(bars) < self.min_bars:
            return None
        closes = [b.close for b in bars]
        avg = sma(closes, 200)
        r1, r0 = rsi(closes[:-1], 2), rsi(closes, 2)
        if avg is None or r1 is None or r0 is None or closes[-1] <= avg:
            return None
        if r0 + r1 < 35:
            return f"IFR(2) acumulado em {r0 + r1:.0f}"
        return None

    def should_exit(self, bars: Sequence[Bar]) -> bool:
        r = rsi([b.close for b in bars], 2)
        return r is not None and r > 65
