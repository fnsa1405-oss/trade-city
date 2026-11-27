"""Ferramentas de day trade: pregão de Nova York, vários tempos gráficos, VWAP,
Heikin-Ashi e a estrutura de topos e fundos da Teoria de Dow.

Tudo aqui é calculado de uma vez sobre o histórico inteiro, mas sem olhar o futuro:
o valor guardado no candle i usa só o que já tinha acontecido no fechamento dele.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, time
from zoneinfo import ZoneInfo

from .models import Bar

NY = ZoneInfo("America/New_York")
OPEN_MIN = 9 * 60 + 30  # 9h30 em Nova York
CLOSE_MIN = 16 * 60  # 16h
SESSION_MIN = CLOSE_MIN - OPEN_MIN


def regular_session(bars: Sequence[Bar]) -> list[Bar]:
    """Só os candles do pregão regular (9h30 às 16h de Nova York)."""
    out = []
    for b in bars:
        local = b.ts.astimezone(NY)
        m = local.hour * 60 + local.minute
        if local.weekday() < 5 and OPEN_MIN <= m < CLOSE_MIN:
            out.append(b)
    return out


def bar_minutes(bars: Sequence[Bar]) -> int:
    """Tamanho do candle em minutos (o intervalo mais comum entre candles seguidos)."""
    counts: dict[int, int] = {}
    for a, b in zip(bars[:200], bars[1:201]):
        gap = int((b.ts - a.ts).total_seconds() // 60)
        if gap > 0:
            counts[gap] = counts.get(gap, 0) + 1
    return max(counts, key=counts.get) if counts else 5


def ema_aligned(values: Sequence[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if n <= 0 or len(values) < n:
        return out
    k = 2.0 / (n + 1)
    cur = sum(values[:n]) / n
    out[n - 1] = cur
    for i in range(n, len(values)):
        cur += k * (values[i] - cur)
        out[i] = cur
    return out


def heikin_ashi(bars: Sequence[Bar]) -> list[Bar]:
    """Candles Heikin-Ashi (média que filtra o ruído; verde = fechamento HA acima da abertura HA)."""
    out: list[Bar] = []
    for b in bars:
        close = (b.open + b.high + b.low + b.close) / 4
        opn = (out[-1].open + out[-1].close) / 2 if out else (b.open + b.close) / 2
        out.append(Bar(b.ts, opn, max(b.high, opn, close), min(b.low, opn, close), close, b.volume))
    return out


@dataclass
class DowState:
    """Teoria de Dow em cada candle: tendência (alta, baixa ou lateral) e os últimos topo e fundo."""

    trend: list[str] = field(default_factory=list)
    last_high: list[float | None] = field(default_factory=list)
    last_low: list[float | None] = field(default_factory=list)
    higher_low: list[bool] = field(default_factory=list)  # último fundo acima do anterior
    lower_high: list[bool] = field(default_factory=list)  # último topo abaixo do anterior


def dow_structure(bars: Sequence[Bar], k: int = 2) -> DowState:
    """Topos e fundos confirmados (k candles de cada lado). Alta = topos e fundos
    ascendentes; baixa = descendentes. A alta acaba quando o preço perde o último fundo
    (e a baixa quando passa do último topo), como na Teoria de Dow."""
    st = DowState()
    highs: list[float] = []
    lows: list[float] = []
    for i, b in enumerate(bars):
        j = i - k  # candle que pode ser confirmado agora como topo ou fundo
        if j >= k:
            hj, lj = bars[j].high, bars[j].low
            left, right = bars[j - k : j], bars[j + 1 : i + 1]
            if all(hj > x.high for x in left) and all(hj >= x.high for x in right):
                highs.append(hj)
            if all(lj < x.low for x in left) and all(lj <= x.low for x in right):
                lows.append(lj)
        trend = "lateral"
        hh = len(highs) >= 2 and highs[-1] > highs[-2]
        hl = len(lows) >= 2 and lows[-1] > lows[-2]
        lh = len(highs) >= 2 and highs[-1] < highs[-2]
        ll = len(lows) >= 2 and lows[-1] < lows[-2]
        if hh and hl and b.close >= lows[-1]:
            trend = "alta"
        elif lh and ll and b.close <= highs[-1]:
            trend = "baixa"
        st.trend.append(trend)
        st.last_high.append(highs[-1] if highs else None)
        st.last_low.append(lows[-1] if lows else None)
        st.higher_low.append(hl)
        st.lower_high.append(lh)
    return st


@dataclass
class Timeline:
    """O dia de pregão de cada candle de gatilho, já em horário de Nova York."""

    bars: list[Bar]
    step: int  # minutos por candle
    dates: list[date]
    start_min: list[int]  # minuto do dia em que o candle abre
    end_min: list[int]  # minuto do dia em que o candle fecha
    vwap: list[float]
    day_open: list[float]
    prev_close: list[float | None]
    day_index: list[int]  # posição do candle dentro do dia (0 = primeiro)

    @classmethod
    def build(cls, bars: Sequence[Bar]) -> "Timeline":
        bars = list(bars)
        step = bar_minutes(bars)
        dates, starts, ends, vwap, opens, prevs, pos = [], [], [], [], [], [], []
        cur_date = None
        pv = vol = 0.0
        n_today = 0
        day_open = 0.0
        last_close: float | None = None
        prev_day_close: float | None = None
        for b in bars:
            local = b.ts.astimezone(NY)
            d = local.date()
            m = local.hour * 60 + local.minute
            if d != cur_date:
                prev_day_close = last_close
                cur_date, pv, vol, n_today, day_open = d, 0.0, 0.0, 0, b.open
            typical = (b.high + b.low + b.close) / 3
            weight = b.volume if b.volume > 0 else 1.0
            pv += typical * weight
            vol += weight
            dates.append(d)
            starts.append(m)
            ends.append(m + step)
            vwap.append(pv / vol)
            opens.append(day_open)
            prevs.append(prev_day_close)
            pos.append(n_today)
            n_today += 1
            last_close = b.close
        return cls(bars, step, dates, starts, ends, vwap, opens, prevs, pos)


@dataclass
class Higher:
    """Tempo gráfico maior montado a partir dos candles de gatilho (ancorado às 9h30)."""

    bars: list[Bar]
    done_at: list[int]  # quantos candles maiores já estavam fechados no candle de gatilho i

    def last(self, i: int, back: int = 0) -> int | None:
        """Índice do candle maior fechado mais recente (back=1: o anterior) no candle i."""
        j = self.done_at[i] - 1 - back
        return j if j >= 0 else None


def higher_timeframe(tl: Timeline, minutes: int) -> Higher:
    out: list[Bar] = []
    done_at: list[int] = []
    cur: list[Bar] = []
    cur_key = None
    for i, b in enumerate(tl.bars):
        m = tl.start_min[i] - OPEN_MIN
        if 0 <= m < SESSION_MIN:
            key = (tl.dates[i], m // minutes)
            if key != cur_key:
                if cur:  # bloco anterior ficou incompleto (faltou candle): fecha assim mesmo
                    out.append(_merge(cur))
                cur, cur_key = [], key
            cur.append(b)
            bucket_end = min((key[1] + 1) * minutes, SESSION_MIN)
            if tl.end_min[i] - OPEN_MIN >= bucket_end:
                out.append(_merge(cur))
                cur = []
        done_at.append(len(out))
    return Higher(out, done_at)


def _merge(group: list[Bar]) -> Bar:
    return Bar(group[0].ts, group[0].open, max(b.high for b in group), min(b.low for b in group), group[-1].close, sum(b.volume for b in group))


def hhmm(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)

