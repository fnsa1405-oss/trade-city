"""Estratégias de cripto que estão em uso e foram publicadas com regras objetivas.

Só compra (cripto à vista, sem venda a descoberto), entrada na abertura do candle
seguinte e stop loss sempre na corretora.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from zoneinfo import ZoneInfo

from ..indicators import atr, ema_series, sma
from ..intraday import dow_structure, heikin_ashi
from .base import Strategy

NY = ZoneInfo("America/New_York")


class DonchianEnsemble(Strategy):
    """Zarattini, Pagani e Barbon, "Catching Crypto Trends" (2025): vários canais de
    Donchian com períodos diferentes votam juntos. Cada canal fica comprado depois que o
    preço fecha acima da máxima do período e sai quando perde o meio do canal (stop
    móvel). A operação abre quando a maioria dos canais está comprada e fecha quando a
    maioria sai. O artigo relata Sharpe acima de 1,5 líquido de taxas desde 2015.
    Fonte: https://concretumgroup.com/catching-crypto-trends-a-tactical-approach-for-bitcoin-and-altcoins/"""

    has_exit = True

    def __init__(self, lookbacks: Sequence[int] = (5, 10, 20, 30, 60, 90, 150, 250, 360), majority: float = 0.5):
        self.lookbacks = tuple(lookbacks)
        self.majority = majority
        self.name = "Donchian em conjunto (Zarattini/Pagani/Barbon)"
        self.description = f"Canais de {', '.join(map(str, self.lookbacks))} candles votam; compra com a maioria."
        self.min_bars = max(self.lookbacks) + 2
        self.lookback = self.min_bars + 200  # tempo para os canais chegarem ao estado certo
        self._score: dict = {}

    def prepare(self, bars):
        highs, lows, closes = [b.high for b in bars], [b.low for b in bars], [b.close for b in bars]
        state = {n: False for n in self.lookbacks}
        prev_score = 0.0
        self._score = {}
        for i, b in enumerate(bars):
            for n in self.lookbacks:
                if i < n:
                    continue
                hi, lo = max(highs[i - n : i]), min(lows[i - n : i])
                if not state[n] and closes[i] > hi:
                    state[n] = True
                elif state[n] and closes[i] < (hi + lo) / 2:
                    state[n] = False
            score = sum(state.values()) / len(self.lookbacks) if i >= self.min_bars else 0.0
            self._score[b.ts] = (prev_score, score)
            prev_score = score

    def _get(self, bars):
        if bars[-1].ts not in self._score:
            self.prepare(bars)
        return self._score[bars[-1].ts]

    def analyze(self, bars):
        if len(bars) < self.min_bars:
            return None
        prev, score = self._get(bars)
        if prev < self.majority <= score:
            return f"Donchian: {score:.0%} dos canais comprados"
        return None

    def should_exit(self, bars):
        return bool(bars) and self._get(bars)[1] < self.majority


class Supertrend(Strategy):
    """Supertrend (Olivier Seban): faixa de ATR em volta do preço que vira de lado quando
    é rompida. Compra quando vira para alta, sai quando vira para baixa. Muito usado em
    cripto nos gráficos de 4h e diário.
    Fonte: https://www.investopedia.com/supertrend-indicator-7976167"""

    has_exit = True

    def __init__(self, period: int = 10, multiplier: float = 3.0):
        self.period, self.multiplier = period, multiplier
        self.name = f"Supertrend {period}/{multiplier:g}"
        self.description = f"Supertrend ATR {period} x {multiplier:g}: compra na virada para alta, sai na virada para baixa."
        self.min_bars = period + 3
        self.lookback = 150

    def prepare(self, bars):
        self._up: dict = {}
        upper = lower = None
        trend = True
        prev = None
        for i in range(self.period, len(bars)):
            a = atr(bars[i - self.period : i + 1], self.period)
            mid = (bars[i].high + bars[i].low) / 2
            bu, bl = mid + self.multiplier * a, mid - self.multiplier * a
            prev_close = bars[i - 1].close
            upper = bu if upper is None or bu < upper or prev_close > upper else upper
            lower = bl if lower is None or bl > lower or prev_close < lower else lower
            if trend and bars[i].close < lower:
                trend = False
            elif not trend and bars[i].close > upper:
                trend = True
            self._up[bars[i].ts] = (prev, trend)
            prev = trend

    def _get(self, bars):
        if bars[-1].ts not in getattr(self, "_up", {}):
            self.prepare(bars)
        return self._up.get(bars[-1].ts, (None, None))

    def analyze(self, bars):
        if len(bars) < self.min_bars:
            return None
        prev, now = self._get(bars)
        if now and prev is False:
            return f"Supertrend {self.period}/{self.multiplier:g} virou para alta"
        return None

    def should_exit(self, bars):
        return self._get(bars)[1] is False


class HeikinAshiTrend(Strategy):
    """Heikin-Ashi com filtro de tendência (Dan Valcu, 2004): acima da MME50, compra quando
    o Heikin-Ashi vira verde depois de dois candles vermelhos; sai no primeiro vermelho.
    Fonte: https://www.investopedia.com/trading/heikin-ashi-better-candlestick/"""

    has_exit = True
    name = "Heikin-Ashi + MME50"
    description = "Acima da MME50, compra na virada do Heikin-Ashi para verde e sai no primeiro vermelho."
    min_bars = 60
    lookback = 120

    def analyze(self, bars):
        if len(bars) < self.min_bars:
            return None
        ha = heikin_ashi(bars)
        trend = ema_series([b.close for b in bars], 50)
        green = [c.close > c.open for c in ha[-3:]]
        if trend and bars[-1].close > trend[-1] and green == [False, False, True]:
            return "Heikin-Ashi virou verde acima da MME50"
        return None

    def should_exit(self, bars):
        ha = heikin_ashi(bars[-30:])
        return bool(ha) and ha[-1].close < ha[-1].open


class DowSwing(Strategy):
    """Teoria de Dow: com topos e fundos ascendentes, compra no rompimento do último topo;
    sai quando o preço perde o último fundo (fim da tendência de alta).
    Fonte: https://www.investopedia.com/terms/d/dowtheory.asp"""

    has_exit = True
    name = "Teoria de Dow (topos e fundos)"
    description = "Topos e fundos ascendentes; compra no rompimento do último topo, sai na perda do último fundo."
    min_bars = 40
    lookback = 150

    def __init__(self, k: int = 3):
        self.k = k

    def prepare(self, bars):
        st = dow_structure(bars, self.k)
        self._st = {}
        for i in range(1, len(bars)):
            breakout = (
                st.higher_low[i - 1]
                and st.last_high[i - 1] is not None
                and st.last_low[i - 1] is not None
                and bars[i - 1].close <= st.last_high[i - 1] < bars[i].close
            )
            lost = st.last_low[i] is not None and bars[i].close < st.last_low[i]
            self._st[bars[i].ts] = (breakout, lost)

    def _get(self, bars):
        if bars[-1].ts not in getattr(self, "_st", {}):
            self.prepare(bars)
        return self._st.get(bars[-1].ts, (False, False))

    def analyze(self, bars):
        if len(bars) < self.min_bars:
            return None
        return "Dow: fundo mais alto e rompimento do último topo" if self._get(bars)[0] else None

    def should_exit(self, bars):
        return self._get(bars)[1]


class MondayAsiaOpen(Strategy):
    """Concretum Research, "Seasonality in Bitcoin Intraday Trend Trading" (2025): o
    melhor trecho da semana vai de domingo 19h de Nova York (abertura de Tóquio) até as 24
    horas seguintes. Compra no domingo às 19h se o preço estiver acima da média de 20 dias
    e vende 24 horas depois. Só no gráfico de 1h.
    Fonte: https://concretumgroup.com/seasonality-in-bitcoin-intraday-trend-trading/"""

    has_exit = True
    name = "Abertura da Ásia na segunda (Concretum)"
    description = "Compra domingo 19h de Nova York, acima da média de 20 dias; vende 24 horas depois."
    min_bars = 481
    lookback = 481

    @staticmethod
    def _end(bars) -> tuple:
        b = bars[-1]
        step = bars[-1].ts - bars[-2].ts if len(bars) > 1 else timedelta(hours=1)
        local = (b.ts + step).astimezone(NY)
        return local, step

    def analyze(self, bars):
        if len(bars) < self.min_bars:
            return None
        local, step = self._end(bars)
        if step != timedelta(hours=1) or local.weekday() != 6 or local.hour != 19 or local.minute:
            return None
        trend = sma([b.close for b in bars], 480)
        if trend is not None and bars[-1].close > trend:
            return "domingo 19h de Nova York (abertura da Ásia), acima da média de 20 dias"
        return None

    def should_exit(self, bars):
        if len(bars) < 2:
            return False
        local, _ = self._end(bars)
        return local.weekday() == 0 and local.hour >= 19
