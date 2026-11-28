"""Retorno à VWAP pelas bandas de desvio padrão: o setup clássico para preço médio para trás.

A VWAP (preço médio ponderado pelo volume do dia) é onde os grandes executam as ordens; o
preço costuma voltar a ela depois de se esticar. As bandas são a VWAP mais ou menos k
desvios padrão do preço do dia em volta dela (o mesmo cálculo das plataformas). Quando o
candle fecha abaixo da banda inferior (passou do esticado), compra; acima da superior,
vende. Alvo: a própria VWAP (saída da estratégia). Stop: 1,5 desvio além da entrada, um
só para a posição inteira, o que deixa espaço para as entradas extras do preço médio.

Filtro opcional de tendência: só compra se o 60 min estiver em alta (MME9 > MME21) e só
vende em baixa, para não "pegar faca caindo" em dia de tendência forte contra.
Fontes: Brian Shannon, "Maximum Trading Gains with Anchored VWAP" (2023); Andrew Aziz,
"How to Day Trade for a Living" (2016), cap. de VWAP.
"""
from __future__ import annotations

import math

from ..intraday import OPEN_MIN, ema_aligned, higher_timeframe
from ..models import Entry, Side
from .daytrade import DayTradeStrategy

LONG, SHORT = Side.LONG, Side.SHORT


class VwapBands(DayTradeStrategy):
    def __init__(self, k: float = 2.0, stop_k: float = 1.5, trend: bool = False, **kw):
        super().__init__(**kw)
        self.k, self.stop_k, self.trend = k, stop_k, trend
        tag = " + 60 min" if trend else ""
        self.name = f"Bandas da VWAP {k:g} desvios{tag}"
        self.description = f"Fecha além de {k:g} desvios da VWAP e volta para ela; stop {stop_k:g} desvio além."
        self.context_days = 3 if trend else 1

    def _compute(self, tl):
        n = len(tl.bars)
        self.sigma: list[float | None] = [None] * n
        cur = None
        w = wx2 = 0.0
        for i, b in enumerate(tl.bars):
            if tl.dates[i] != cur:
                cur, w, wx2 = tl.dates[i], 0.0, 0.0
            typical = (b.high + b.low + b.close) / 3
            vol = b.volume if b.volume > 0 else 1.0
            w += vol
            wx2 += vol * typical * typical
            var = wx2 / w - tl.vwap[i] ** 2
            self.sigma[i] = math.sqrt(var) if var > 0 else None
        self.side60: list[Side | None] = [None] * n
        if self.trend:
            h = higher_timeframe(tl, 60)
            closes = [x.close for x in h.bars]
            e9, e21 = ema_aligned(closes, 9), ema_aligned(closes, 21)
            for i in range(n):
                j = h.last(i)
                if j is not None and e9[j] is not None and e21[j] is not None:
                    self.side60[i] = LONG if e9[j] > e21[j] else SHORT

    def _entry(self, tl, i):
        if tl.end_min[i] < OPEN_MIN + 30 or tl.day_index[i] == 0:
            return None  # a VWAP precisa de meia hora para ter desvio
        s, ps = self.sigma[i], self.sigma[i - 1]
        if s is None or ps is None:
            return None
        b, prev = tl.bars[i], tl.bars[i - 1]
        vwap, pvwap = tl.vwap[i], tl.vwap[i - 1]
        lower, upper = vwap - self.k * s, vwap + self.k * s
        want = self.side60[i] if self.trend else None
        if self.trend and want is None:
            return None
        if b.close < lower and prev.close >= pvwap - self.k * ps and want in (None, LONG):
            return Entry(f"fechou abaixo de {self.k:g} desvios da VWAP ({vwap:.2f})", LONG, b.close - self.stop_k * s)
        if b.close > upper and prev.close <= pvwap + self.k * ps and want in (None, SHORT):
            return Entry(f"fechou acima de {self.k:g} desvios da VWAP ({vwap:.2f})", SHORT, b.close + self.stop_k * s)
        return None

    def _exit(self, tl, i, side):
        close, vwap = tl.bars[i].close, tl.vwap[i]
        return close >= vwap if side is LONG else close <= vwap
