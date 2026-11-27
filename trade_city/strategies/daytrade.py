"""Day trade no pregão americano (QQQ, SPY, DIA, IWM).

Leitura em vários tempos gráficos, como os traders fazem: o gráfico de 60 minutos dá o
contexto e a decisão, o de 15 minutos confirma, e o gatilho sai no gráfico menor
(5 ou 1 minuto; a escola testa os dois). Todas operam comprado e vendido, nunca
dormem posicionadas (zeram às 15h50 de Nova York) e não abrem nada depois das 15h.

Adaptações comuns: a entrada é na abertura do candle seguinte ao sinal, e o
Guardião de Risco sempre põe stop loss na corretora (o stop do gráfico, com uma
distância mínima contra o ruído).
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import time

from ..intraday import OPEN_MIN, Higher, Timeline, dow_structure, ema_aligned, heikin_ashi, higher_timeframe
from ..models import Bar, Entry, Side
from .base import Strategy

LONG, SHORT = Side.LONG, Side.SHORT


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


class DayTradeStrategy(Strategy):
    has_exit = True
    day_trade = True
    min_bars = 2
    context_days = 5  # pregões de histórico que a estratégia precisa olhar

    def __init__(self, allow_short: bool = True, last_entry: time = time(15, 0), flat_after: time = time(15, 50)):
        self.allow_short = allow_short
        self.last_entry = _minutes(last_entry)
        self.flat_after = _minutes(flat_after)
        self._tl: Timeline | None = None
        self._index: dict = {}

    @property
    def window(self) -> int:
        # em candles de 1 minuto, para servir aos dois gatilhos (5 min usa menos)
        return self.context_days * 390 + 10

    # cálculo antecipado ---------------------------------------------------
    def prepare(self, bars: Sequence[Bar]) -> None:
        self._tl = Timeline.build(bars)
        self._index = {b.ts: i for i, b in enumerate(self._tl.bars)}
        self._compute(self._tl)

    def _compute(self, tl: Timeline) -> None:
        """Subclasses calculam aqui os indicadores de cada tempo gráfico."""

    def _at(self, bars: Sequence[Bar]) -> int | None:
        if not bars:
            return None
        i = self._index.get(bars[-1].ts)
        if i is None or self._tl is None or self._tl.bars[i] is not bars[-1]:
            self.prepare(bars)
            i = self._index.get(bars[-1].ts)
        return i

    # interface ------------------------------------------------------------
    def decide(self, bars: Sequence[Bar]) -> Entry | None:
        i = self._at(bars)
        if i is None:
            return None
        tl = self._tl
        if not (OPEN_MIN < tl.end_min[i] <= self.last_entry):
            return None
        entry = self._entry(tl, i)
        if entry is not None and entry.side is SHORT and not self.allow_short:
            return None
        return entry

    def exit_signal(self, bars: Sequence[Bar], side: Side) -> bool:
        i = self._at(bars)
        if i is None:
            return False
        if self._tl.end_min[i] >= self.flat_after:
            return True  # day trade: zera antes do fim do pregão
        return self._exit(self._tl, i, side)

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        entry = self.decide(bars)
        return entry.reason if entry and entry.side is LONG else None

    def _entry(self, tl: Timeline, i: int) -> Entry | None:
        raise NotImplementedError

    def _exit(self, tl: Timeline, i: int, side: Side) -> bool:
        return False


class OpeningRangeDayTrade(DayTradeStrategy):
    """Zarattini e Aziz, "Can Day Trading Really Be Profitable?" (2023): a direção do
    primeiro candle de 5 minutos do pregão decide o lado. Candle de alta = compra na
    abertura do segundo candle, com stop na mínima do primeiro; de baixa = venda, stop na
    máxima. Alvo de 10x o risco ou zera no fim do dia. Uma réplica independente com
    custos (mql5, 2026) mostrou que a vantagem é pequena e some com custos altos: por isso
    a escola cobra custos e prova fora da amostra.
    Fontes: https://papers.ssrn.com/abstract=4416622 e https://www.mql5.com/en/blogs/post/776235"""

    def __init__(self, range_minutes: int = 5, **kw):
        super().__init__(**kw)
        self.range_minutes = range_minutes
        self.name = f"ORB {range_minutes} min (Zarattini/Aziz)"
        self.description = f"Lado do primeiro candle de {range_minutes} min; stop no outro extremo dele; zera no fim do dia."
        self.context_days = 1

    def _entry(self, tl, i):
        if tl.end_min[i] != OPEN_MIN + self.range_minutes:
            return None
        start = i - tl.day_index[i]
        if tl.start_min[start] != OPEN_MIN:
            return None  # faltou o primeiro candle do dia
        group = tl.bars[start : i + 1]
        opn, close = group[0].open, group[-1].close
        high, low = max(b.high for b in group), min(b.low for b in group)
        if close > opn:
            return Entry(f"ORB: primeiros {self.range_minutes} min de alta", LONG, low)
        if close < opn:
            return Entry(f"ORB: primeiros {self.range_minutes} min de baixa", SHORT, high)
        return None


class NoiseAreaMomentum(DayTradeStrategy):
    """Zarattini, Aziz e Barbon, "Beat the Market: An Effective Intraday Momentum Strategy
    for S&P500 ETF (SPY)" (2024). A "área de ruído" de cada horário é a variação média
    desde a abertura, naquele mesmo horário, nos últimos 14 pregões. Nas meias horas
    (HH:00 e HH:30), preço acima do limite superior e da VWAP = compra; abaixo do inferior
    e da VWAP = venda. Stop móvel no limite ou na VWAP, conferido nas meias horas; zera no
    fim do dia. Limites ajustados pelo gap da abertura, como no artigo.
    Fonte: https://www.cxoadvisory.com/momentum-investing/complex-intraday-time-series-momentum-strategy-applied-to-spy/"""

    def __init__(self, days: int = 14, **kw):
        super().__init__(**kw)
        self.days = days
        self.name = f"Área de ruído {days}d (Zarattini/Aziz/Barbon)"
        self.description = "Rompe a área de ruído do horário com a VWAP a favor; stop móvel no limite/VWAP."
        self.context_days = days + 1

    def _compute(self, tl):
        n = len(tl.bars)
        self.upper: list[float | None] = [None] * n
        self.lower: list[float | None] = [None] * n
        history: list[dict[int, float]] = []  # por dia: minuto de fechamento -> |variação desde a abertura|
        today: dict[int, float] = {}
        cur = None
        for i, b in enumerate(tl.bars):
            if tl.dates[i] != cur:
                if today:
                    history.append(today)
                today, cur = {}, tl.dates[i]
            m = tl.end_min[i]
            today[m] = abs(b.close / tl.day_open[i] - 1)
            past = [d[m] for d in history[-self.days :] if m in d]
            if len(past) < self.days * 0.8:
                continue
            sigma = sum(past) / len(past)
            ref_up = max(tl.day_open[i], tl.prev_close[i] or tl.day_open[i])
            ref_dn = min(tl.day_open[i], tl.prev_close[i] or tl.day_open[i])
            self.upper[i] = ref_up * (1 + sigma)
            self.lower[i] = ref_dn * (1 - sigma)

    def _check(self, tl, i) -> bool:
        return tl.end_min[i] % 30 == 0 and tl.end_min[i] >= OPEN_MIN + 30

    def _entry(self, tl, i):
        if not self._check(tl, i) or self.upper[i] is None:
            return None
        close, vwap = tl.bars[i].close, tl.vwap[i]
        if close > self.upper[i] and close > vwap:
            return Entry("acima da área de ruído e da VWAP", LONG, min(self.upper[i], vwap))
        if close < self.lower[i] and close < vwap:
            return Entry("abaixo da área de ruído e da VWAP", SHORT, max(self.lower[i], vwap))
        return None

    def _exit(self, tl, i, side):
        if not self._check(tl, i) or self.upper[i] is None:
            return False
        close, vwap = tl.bars[i].close, tl.vwap[i]
        if side is LONG:
            return close < max(self.upper[i], vwap)
        return close > min(self.lower[i], vwap)


class _MultiTimeframe(DayTradeStrategy):
    """Base: monta 60 min e 15 min a partir dos candles de gatilho."""

    context_days = 5

    def _compute(self, tl):
        self.h1: Higher = higher_timeframe(tl, 60)
        self.m15: Higher = higher_timeframe(tl, 15)
        self.ha = heikin_ashi(tl.bars)
        self.ha_h1 = heikin_ashi(self.h1.bars)
        self.ha_m15 = heikin_ashi(self.m15.bars)
        self._extra(tl)

    def _extra(self, tl):
        pass

    @staticmethod
    def _green(c: Bar) -> bool:
        return c.close > c.open

    def _ha_flip(self, i: int, side: Side, reds: int = 2) -> bool:
        """Heikin-Ashi do gatilho virou a favor depois de `reds` candles contra (fim do recuo)."""
        if i < reds or self._tl.day_index[i] < reds:
            return False
        want = side is LONG
        if self._green(self.ha[i]) != want:
            return False
        return all(self._green(self.ha[i - k]) != want for k in range(1, reds + 1))

    def _swing_stop(self, i: int, side: Side, n: int = 6) -> float:
        start = max(i - self._tl.day_index[i], i - n + 1)
        group = self._tl.bars[start : i + 1]
        return min(b.low for b in group) if side is LONG else max(b.high for b in group)

    def _ha15_against(self, i: int, side: Side) -> bool:
        j = self.m15.last(i)
        if j is None:
            return False
        return self._green(self.ha_m15[j]) != (side is LONG)


class HeikinAshiTrendPullback(_MultiTimeframe):
    """Tendência no 60 min (MME9 acima da MME21 e Heikin-Ashi de 60 min a favor), preço do
    lado certo da MME21 de 15 min, e gatilho quando o Heikin-Ashi do gráfico menor vira a
    favor depois de um recuo, com o preço do lado certo da VWAP. Stop no extremo do recuo.
    Sai quando o Heikin-Ashi de 15 min vira contra. Heikin-Ashi: Dan Valcu, "Using the
    Heikin-Ashi Technique" (Technical Analysis of Stocks & Commodities, 2004).
    Fonte: https://www.investopedia.com/trading/heikin-ashi-better-candlestick/"""

    name = "Heikin-Ashi + MME 9/21 (60/15/gatilho)"
    description = "60 min em tendência (MME9/21 e HA), 15 min confirma, gatilho na virada do HA após recuo."

    def _extra(self, tl):
        closes = [b.close for b in self.h1.bars]
        self.e9, self.e21 = ema_aligned(closes, 9), ema_aligned(closes, 21)
        self.e21_m15 = ema_aligned([b.close for b in self.m15.bars], 21)

    def _bias(self, i: int) -> Side | None:
        j, q = self.h1.last(i), self.m15.last(i)
        if j is None or q is None or self.e9[j] is None or self.e21[j] is None or self.e21_m15[q] is None:
            return None
        close = self._tl.bars[i].close
        if self.e9[j] > self.e21[j] and self._green(self.ha_h1[j]) and close > self.e21_m15[q]:
            return LONG
        if self.e9[j] < self.e21[j] and not self._green(self.ha_h1[j]) and close < self.e21_m15[q]:
            return SHORT
        return None

    def _entry(self, tl, i):
        side = self._bias(i)
        if side is None or not self._ha_flip(i, side):
            return None
        vwap_ok = tl.bars[i].close > tl.vwap[i] if side is LONG else tl.bars[i].close < tl.vwap[i]
        if not vwap_ok:
            return None
        word = "alta" if side is LONG else "baixa"
        return Entry(f"60 min de {word} (MME9/21 e HA), HA do gatilho virou após recuo", side, self._swing_stop(i, side))

    def _exit(self, tl, i, side):
        return self._ha15_against(i, side)


class DowTheoryDayTrade(_MultiTimeframe):
    """Teoria de Dow em três tempos: o 60 min e o 15 min precisam estar em tendência
    (topos e fundos ascendentes para comprar, descendentes para vender). Gatilho: no
    gráfico menor, depois de um fundo mais alto, o preço rompe o último topo (na venda,
    perde o último fundo depois de um topo mais baixo). Stop no último fundo/topo do
    gatilho. Sai quando o 15 min deixa de estar em tendência.
    Fonte: https://www.investopedia.com/terms/d/dowtheory.asp"""

    name = "Teoria de Dow (60/15/gatilho)"
    description = "60 e 15 min com topos e fundos a favor; gatilho no rompimento do último topo/fundo."

    def _extra(self, tl):
        self.dow = dow_structure(tl.bars, 2)
        self.dow_h1 = dow_structure(self.h1.bars, 2)
        self.dow_m15 = dow_structure(self.m15.bars, 2)

    def _trend(self, higher: Higher, state, i: int) -> str:
        j = higher.last(i)
        return state.trend[j] if j is not None else "lateral"

    def _entry(self, tl, i):
        if i < 1 or tl.day_index[i] < 1:
            return None
        h1, m15 = self._trend(self.h1, self.dow_h1, i), self._trend(self.m15, self.dow_m15, i)
        close, prev = tl.bars[i].close, tl.bars[i - 1].close
        top, bottom = self.dow.last_high[i - 1], self.dow.last_low[i - 1]
        if h1 == m15 == "alta" and top and bottom and self.dow.higher_low[i - 1] and prev <= top < close:
            return Entry("Dow: 60 e 15 min em alta, rompeu o último topo após fundo mais alto", LONG, bottom)
        if h1 == m15 == "baixa" and top and bottom and self.dow.lower_high[i - 1] and prev >= bottom > close:
            return Entry("Dow: 60 e 15 min em baixa, perdeu o último fundo após topo mais baixo", SHORT, top)
        return None

    def _exit(self, tl, i, side):
        want = "alta" if side is LONG else "baixa"
        return self._trend(self.m15, self.dow_m15, i) != want


class DowHeikinAshi(_MultiTimeframe):
    """Combinação pedida para a escola: a tendência vem da Teoria de Dow no 60 min, o
    gatilho é a virada do Heikin-Ashi no gráfico menor depois de um recuo, com a VWAP a
    favor. Stop no extremo do recuo; sai quando o Heikin-Ashi de 15 min vira contra."""

    name = "Dow 60 min + gatilho Heikin-Ashi"
    description = "Tendência de Dow no 60 min, gatilho na virada do HA após recuo, VWAP a favor."

    def _extra(self, tl):
        self.dow_h1 = dow_structure(self.h1.bars, 2)

    def _entry(self, tl, i):
        j = self.h1.last(i)
        if j is None:
            return None
        trend = self.dow_h1.trend[j]
        side = LONG if trend == "alta" else SHORT if trend == "baixa" else None
        if side is None or not self._ha_flip(i, side):
            return None
        close = tl.bars[i].close
        if (close > tl.vwap[i]) != (side is LONG):
            return None
        return Entry(f"Dow 60 min em {trend}, HA do gatilho virou após recuo", side, self._swing_stop(i, side))

    def _exit(self, tl, i, side):
        return self._ha15_against(i, side)
