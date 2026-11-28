"""Day trade a favor das médias móveis, como o Alexandre pediu em 28/11/2026.

Médias: aritméticas de 200, 50 e 20 e exponencial de 9. Os tempos de contexto (60, 15 e
5 min) dizem o lado: só compra quando, em cada um, MME9 > MMA20 > MMA50 > MMA200 (médias
empilhadas para cima), e só vende no inverso. O gatilho sai no gráfico de 2 minutos, num
candle que parte das médias (a mínima toca a MME9 ou a MMA20 do 2 min na compra; a máxima,
na venda):

- Ponto Contínuo (Stormer): toca a média e fecha de volta a favor dela.
- PFR, preço de fechamento de reversão: faz mínima abaixo da anterior e fecha acima do
  fechamento anterior (na compra).
- Engolfo: o corpo engole o corpo do candle anterior, que era contra.
- Martelo: sombra contra de pelo menos 2 vezes o corpo e fechamento no terço a favor.
- Candle de força: corpo de pelo menos 70% do candle, amplitude de 1,5 vez a média dos
  últimos 20 candles e fechamento a favor.

Entrada por rompimento da máxima do candle gatilho (mínima na venda), valendo por 1 candle
de 2 min; stop no outro extremo. Saída da estratégia: o 2 min fecha do outro lado da MMA20.

A estratégia recebe candles de 1 minuto e monta por dentro os de 2, 5, 15 e 60 minutos,
usando só candles já fechados (sem olhar o futuro).
Fontes: Ponto Contínuo e PFR são setups que Alexandre Wolwacz (Stormer) ensina em aulas
abertas; aqui viraram as regras objetivas acima. Padrões de candle: Steve Nison,
"Japanese Candlestick Charting Techniques" (1991).
"""
from __future__ import annotations

from math import ceil

from ..intraday import SESSION_MIN, Higher, ema_aligned, higher_timeframe
from ..models import Entry, Side
from .daytrade import DayTradeStrategy

LONG, SHORT = Side.LONG, Side.SHORT

TRIGGERS = {
    "pc": "Ponto Contínuo",
    "pfr": "PFR",
    "engolfo": "engolfo",
    "martelo": "martelo",
    "forca": "candle de força",
}


def sma_aligned(values, n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= n:
            total -= values[i - n]
        if i >= n - 1:
            out[i] = total / n
    return out


class _Averages:
    def __init__(self, h: Higher):
        closes = [b.close for b in h.bars]
        self.h = h
        self.e9 = ema_aligned(closes, 9)
        self.s20 = sma_aligned(closes, 20)
        self.s50 = sma_aligned(closes, 50)
        self.s200 = sma_aligned(closes, 200)

    def stack(self, j: int) -> Side | None:
        e9, s20, s50, s200 = self.e9[j], self.s20[j], self.s50[j], self.s200[j]
        if None in (e9, s20, s50, s200):
            return None
        if e9 > s20 > s50 > s200:
            return LONG
        if e9 < s20 < s50 < s200:
            return SHORT
        return None


class MovingAverageTrend(DayTradeStrategy):
    """Opera só a favor das médias empilhadas nos tempos de `align` (minutos), com o
    candle gatilho `trigger` no gráfico de 2 minutos partindo da MME9 ou da MMA20."""

    has_exit = True
    valid_bars = 2  # 1 candle de 2 min, em candles de 1 min

    def __init__(self, trigger: str = "pc", align: tuple[int, ...] = (60, 15, 5), **kw):
        super().__init__(**kw)
        self.trigger = trigger
        self.align = tuple(align)
        tfs = "/".join(str(a) for a in self.align)
        self.name = f"Médias 200/50/20/9 ({tfs} min) + {TRIGGERS[trigger]} no 2 min"
        self.description = f"Médias empilhadas a favor em {tfs} min; gatilho {TRIGGERS[trigger]} no 2 min partindo da MME9/MMA20."
        biggest = max(self.align + (2,))
        self.context_days = ceil(200 / (SESSION_MIN / biggest)) + 2

    def _compute(self, tl):
        self.ok = tl.step == 1
        if not self.ok:
            return
        self.m2 = higher_timeframe(tl, 2)
        self.a2 = _Averages(self.m2)
        self.ctx = [_Averages(higher_timeframe(tl, m)) for m in self.align]
        spans = [b.high - b.low for b in self.m2.bars]
        self.avg_span = sma_aligned(spans, 20)

    def _closed_2min(self, tl, i) -> int | None:
        """Índice do candle de 2 min que fechou exatamente no candle de 1 min i."""
        if i < 1 or self.m2.done_at[i] == self.m2.done_at[i - 1]:
            return None
        return self.m2.last(i)

    def _bias(self, i) -> Side | None:
        side = None
        for a in self.ctx:
            j = a.h.last(i)
            s = None if j is None else a.stack(j)
            if s is None or (side is not None and s is not side):
                return None
            side = s
        return side

    def _entry(self, tl, i):
        if not self.ok or tl.day_index[i] < 3:
            return None
        j = self._closed_2min(tl, i)
        if j is None or j < 1:
            return None
        side = self._bias(i)
        if side is None:
            return None
        bars, a = self.m2.bars, self.a2
        b, p = bars[j], bars[j - 1]
        e9, s20 = a.e9[j], a.s20[j]
        if e9 is None or s20 is None:
            return None
        rng = b.high - b.low
        if rng <= 0:
            return None
        body = abs(b.close - b.open)
        long = side is LONG
        # parte das médias: toca a MME9 ou a MMA20 do 2 min
        touch = (b.low <= max(e9, s20)) if long else (b.high >= min(e9, s20))
        if not touch:
            return None
        if long and b.close <= s20 or not long and b.close >= s20:
            return None  # fechou do lado errado da MMA20
        t = self.trigger
        if t == "pc":
            hit = any((b.low <= m < b.close) if long else (b.high >= m > b.close) for m in (e9, s20))
        elif t == "pfr":
            hit = (b.low < p.low and b.close > p.close) if long else (b.high > p.high and b.close < p.close)
        elif t == "engolfo":
            if long:
                hit = p.close < p.open and b.close > b.open and b.close >= p.open and b.open <= p.close
            else:
                hit = p.close > p.open and b.close < b.open and b.close <= p.open and b.open >= p.close
        elif t == "martelo":
            lower = min(b.open, b.close) - b.low
            upper = b.high - max(b.open, b.close)
            pos = (b.close - b.low) / rng
            hit = (lower >= 2 * body and pos >= 2 / 3) if long else (upper >= 2 * body and pos <= 1 / 3)
        else:  # candle de força
            avg = self.avg_span[j - 1]
            strong = avg is not None and rng >= 1.5 * avg and body >= 0.7 * rng
            hit = strong and ((b.close > b.open) if long else (b.close < b.open))
        if not hit:
            return None
        word = "compra" if long else "venda"
        reason = f"médias a favor em {'/'.join(map(str, self.align))} min; {TRIGGERS[t]} no 2 min ({word})"
        return Entry(reason, side, b.low if long else b.high, b.high if long else b.low, self.valid_bars)

    def _exit(self, tl, i, side):
        if not self.ok:
            return False
        j = self._closed_2min(tl, i)
        if j is None or self.a2.s20[j] is None:
            return False
        c = self.m2.bars[j].close
        return c < self.a2.s20[j] if side is LONG else c > self.a2.s20[j]
