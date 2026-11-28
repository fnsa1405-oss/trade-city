"""Método Wyckoff (com leitura de volume do VSA), a partir da apostila que o Alexandre enviou
em 28/11/2026 e do esquema de acumulação/distribuição da Wyckoff Analytics.

O que a apostila deixa objetivo e virou regra:
- Faixa de negociação (lateralização): máxima e mínima dos últimos `range_bars` candles, desde
  que a altura caiba em `max_width_atr` ATRs (senão é tendência, não faixa).
- Barra larga (WRB): amplitude de pelo menos 1,8 vez a média dos últimos 40 candles.
- Volume alto: acima de 1,5 vez a média de 60 candles; ultra-alto: acima de 2 vezes.
- Fechamento perto da máxima (ou mínima): nos 30% de cima (ou de baixo) do candle.
- Spring/Upthrust: perde o suporte (ou passa da resistência) da faixa e fecha de volta dentro.
- SOS + LPS (o "Jump Across the Creek"): rompe a resistência com barra larga, volume alto e
  fechamento perto da máxima; depois recua com volume baixo até a metade do candle do SOS
  sem fechar abaixo da resistência. O LPS é a compra.
- Clímax (SC/BC): barra larga de baixa com volume ultra-alto na mínima da faixa, fechando
  longe da mínima (absorção). Compra no rompimento dela.

Em todos, a entrada é por rompimento (ordem stop) do candle do sinal, com stop no outro
extremo, e o gerenciamento é o da apostila: alvo 1x, 2x ou 3x o risco.

O que ficou de fora por ser subjetivo: rotular cada fase (A a E), o "homem composto", as
linhas de tendência desenhadas à mão, o Market Profile e o volume do mini índice "olhando o
histórico" (a apostila diz que não há número fixo; usamos múltiplos da média).
"""
from __future__ import annotations

from ..models import Entry, Side
from .setups import _Setup

LONG, SHORT = Side.LONG, Side.SHORT


class _Wyckoff(_Setup):
    has_exit = False  # sai no alvo, no stop ou no fim do dia (day trade)
    valid_bars = 2

    def __init__(self, range_bars: int = 40, max_width_atr: float = 6.0, **kw):
        self.range_bars = range_bars
        self.max_width_atr = max_width_atr
        super().__init__(**kw)

    def _setup_extra(self, tl):
        bars = tl.bars
        n = len(bars)
        N = self.range_bars
        spread = [b.high - b.low for b in bars]
        vol = [b.volume for b in bars]
        tr = [spread[0]] + [max(bars[k].high - bars[k].low, abs(bars[k].high - bars[k - 1].close), abs(bars[k].low - bars[k - 1].close)) for k in range(1, n)]
        self.atr = _mean_before(tr, 14)
        self.avg_spread = _mean_before(spread, 40)
        self.avg_vol = _mean_before(vol, 60)
        self.r_hi: list[float | None] = [None] * n
        self.r_lo: list[float | None] = [None] * n
        for k in range(N, n):
            hi = max(b.high for b in bars[k - N : k])
            lo = min(b.low for b in bars[k - N : k])
            a = self.atr[k]
            if a and hi - lo <= self.max_width_atr * a:
                self.r_hi[k], self.r_lo[k] = hi, lo
        self._wyckoff_extra(tl)

    def _wyckoff_extra(self, tl):
        pass

    # leitura de barra (VSA) ------------------------------------------------
    def _wide(self, i: int) -> bool:
        a = self.avg_spread[i]
        b = self._tl.bars[i]
        return a is not None and a > 0 and b.high - b.low >= 1.8 * a

    def _vol(self, i: int, mult: float) -> bool:
        a = self.avg_vol[i]
        return a is not None and a > 0 and self._tl.bars[i].volume >= mult * a

    def _low_vol(self, i: int) -> bool:
        a = self.avg_vol[i]
        return a is not None and a > 0 and self._tl.bars[i].volume < a

    def _close_pos(self, i: int) -> float:
        b = self._tl.bars[i]
        return (b.close - b.low) / (b.high - b.low) if b.high > b.low else 0.5


class WyckoffSpring(_Wyckoff):
    """Spring (compra) e Upthrust (venda): rompimento falso da faixa de negociação.
    `low_volume=True` exige volume abaixo da média no candle do spring ("teste com baixo
    volume", sem oferta)."""

    name = "Wyckoff spring/upthrust"
    description = "Perde o suporte da faixa e fecha de volta dentro; compra no rompimento do candle."

    def __init__(self, low_volume: bool = False, **kw):
        self.low_volume = low_volume
        super().__init__(**kw)
        if low_volume:
            self.name = self.name.replace("upthrust", "upthrust com volume baixo", 1)

    def _entry(self, tl, i):
        lo, hi = self.r_lo[i], self.r_hi[i]
        if lo is None or not self._today(tl, i, 1):
            return None
        if self.low_volume and not self._low_vol(i):
            return None
        b = tl.bars[i]
        if b.low < lo < b.close:
            return self._arm(tl, i, LONG, b.low, "Wyckoff: spring (perdeu o suporte da faixa e voltou)")
        if b.high > hi > b.close:
            return self._arm(tl, i, SHORT, b.high, "Wyckoff: upthrust (passou da resistência da faixa e voltou)")
        return None


class WyckoffSOSLPS(_Wyckoff):
    """Sinal de força (SOS, o salto do riacho) e compra no último ponto de suporte (LPS);
    inverso para venda: sinal de fraqueza (SOW) e venda no LPSY."""

    name = "Wyckoff SOS + LPS"
    description = "Rompe a faixa com força e volume; compra no recuo com volume baixo."
    wait = 10  # candles em que o LPS ainda vale depois do SOS

    def _wyckoff_extra(self, tl):
        bars = tl.bars
        self.lps: list[tuple | None] = [None] * len(bars)
        sos = None  # (lado, índice, riacho, metade do candle do SOS)
        for i, b in enumerate(bars):
            hi, lo = self.r_hi[i], self.r_lo[i]
            strong = self._wide(i) and self._vol(i, 1.5)
            if hi is not None and strong and b.close > hi and self._close_pos(i) >= 0.7:
                sos = (LONG, i, hi, (b.high + b.low) / 2)
                continue
            if lo is not None and strong and b.close < lo and self._close_pos(i) <= 0.3:
                sos = (SHORT, i, lo, (b.high + b.low) / 2)
                continue
            if sos is None:
                continue
            side, k, creek, mid = sos
            if i - k > self.wait or (side is LONG and b.close < creek) or (side is SHORT and b.close > creek):
                sos = None  # o rompimento falhou ou o recuo demorou demais
                continue
            if not self._low_vol(i):
                continue
            if side is LONG and b.low <= mid and b.close >= creek:
                self.lps[i] = (LONG, b.low)
                sos = None
            elif side is SHORT and b.high >= mid and b.close <= creek:
                self.lps[i] = (SHORT, b.high)
                sos = None

    def _entry(self, tl, i):
        got = self.lps[i]
        if got is None or not self._today(tl, i, 1):
            return None
        side, stop = got
        reason = "Wyckoff: LPS (recuo com volume baixo depois do sinal de força)" if side is LONG else "Wyckoff: LPSY (repique com volume baixo depois do sinal de fraqueza)"
        return self._arm(tl, i, side, stop, reason)


class WyckoffClimax(_Wyckoff):
    """Venda climática (SC) com absorção: barra larga de baixa, volume ultra-alto, na mínima da
    faixa e fechando longe da mínima; compra no rompimento da máxima dela. Inverso para a
    compra climática (BC)."""

    name = "Wyckoff clímax (SC/BC)"
    description = "Barra larga com volume ultra-alto no extremo, fechando longe dele; entra contra."

    def __init__(self, **kw):
        kw.setdefault("max_width_atr", 1e9)  # o clímax vem no fim da tendência, não numa faixa
        super().__init__(**kw)

    def _entry(self, tl, i):
        lo, hi = self.r_lo[i], self.r_hi[i]
        if lo is None or i < 1 or not self._today(tl, i, 1):
            return None
        if not (self._wide(i) and self._vol(i, 2.0)):
            return None
        b, prev = tl.bars[i], tl.bars[i - 1]
        pos = self._close_pos(i)
        if b.close < prev.close and b.low <= lo and pos >= 0.4:
            return self._arm(tl, i, LONG, b.low, "Wyckoff: venda climática com absorção")
        if b.close > prev.close and b.high >= hi and pos <= 0.6:
            return self._arm(tl, i, SHORT, b.high, "Wyckoff: compra climática com oferta")
        return None


def _mean_before(values, n: int) -> list[float | None]:
    """Média dos n valores anteriores ao candle i (o próprio candle fica de fora)."""
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        if i >= n:
            out[i] = total / n
            total -= values[i - n]
        total += v
    return out
