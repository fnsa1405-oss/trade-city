"""Estratégias propostas pelo Conselho de consultores (trade_city/conselho.py).

Nenhuma delas entra na mesa direto: cada uma é testada pela escola, com as mesmas regras
(treino nos 70% iniciais, prova nos 30% finais, custo real), contra a estratégia atual.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

from ..models import Bar
from .base import Strategy


def _sma_series(values: Sequence[float], n: int) -> list[float | None]:
    out: list[float | None] = []
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= n:
            total -= values[i - n]
        out.append(total / n if i >= n - 1 else None)
    return out


def _atr_series(bars: Sequence[Bar], n: int = 14) -> list[float | None]:
    trs = []
    for i, b in enumerate(bars):
        prev = bars[i - 1].close if i else b.close
        trs.append(max(b.high - b.low, abs(b.high - prev), abs(b.low - prev)))
    return _sma_series(trs, n)


def _rsi_series(closes: Sequence[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    gain = loss = 0.0
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        g, l = max(ch, 0.0), max(-ch, 0.0)
        if i <= n:
            gain += g / n
            loss += l / n
            if i < n:
                continue
        else:  # média de Wilder
            gain = (gain * (n - 1) + g) / n
            loss = (loss * (n - 1) + l) / n
        out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


class _Scored(Strategy):
    """Base das estratégias que calculam tudo no `prepare` (um valor por candle, sem olhar
    o futuro) e só consultam pelo horário do último candle."""

    has_exit = True

    def __init__(self):
        self._cache: dict = {}

    def _compute(self, bars: Sequence[Bar]) -> dict:
        raise NotImplementedError

    def prepare(self, bars):
        self._cache = self._compute(bars)

    def _get(self, bars):
        if bars[-1].ts not in self._cache:
            self.prepare(bars)
        return self._cache.get(bars[-1].ts)


class WeakSignalVote(_Scored):
    """Proposta da Íris (inspirada na Renaissance Technologies): em vez de um sinal forte,
    vários sinais fracos e diferentes votam juntos. Oito "eleitores": preço acima das médias
    de 20, 50, 100 e 200; retorno positivo em 14, 28 e 56 candles; preço acima do meio do
    canal de 20 candles. Compra quando pelo menos `enter` dos votos são de alta e sai quando
    caem abaixo de `leave`. A ideia (muitas pequenas vantagens somadas, cada uma pouco acima
    do acaso) é a que Gregory Zuckerman descreve em "The Man Who Solved the Market" (2019)."""

    SMAS = (20, 50, 100, 200)
    MOMENTA = (14, 28, 56)

    def __init__(self, enter: float = 0.75, leave: float = 0.5):
        super().__init__()
        self.enter, self.leave = enter, leave
        self.name = f"Votação de sinais fracos ({enter:.0%}/{leave:.0%})"
        self.description = f"8 sinais fracos votam; compra com {enter:.0%} de votos de alta e sai abaixo de {leave:.0%}."
        self.min_bars = 202
        self.lookback = 260

    def _compute(self, bars):
        closes = [b.close for b in bars]
        smas = {n: _sma_series(closes, n) for n in self.SMAS}
        out, prev = {}, 0.0
        for i, b in enumerate(bars):
            if i < self.min_bars:
                out[b.ts] = (0.0, 0.0)
                continue
            votes = [closes[i] > smas[n][i] for n in self.SMAS]
            votes += [closes[i] > closes[i - n] for n in self.MOMENTA]
            hi = max(x.high for x in bars[i - 20 : i])
            lo = min(x.low for x in bars[i - 20 : i])
            votes.append(closes[i] > (hi + lo) / 2)
            score = sum(votes) / len(votes)
            out[b.ts] = (prev, score)
            prev = score
        return out

    def analyze(self, bars):
        if len(bars) < self.min_bars:
            return None
        prev, score = self._get(bars) or (0.0, 0.0)
        if prev < self.enter <= score:
            return f"votação: {score:.0%} dos sinais fracos de alta"
        return None

    def should_exit(self, bars):
        got = self._get(bars) if bars else None
        return bool(got) and got[1] < self.leave


class ZScoreReversion(_Scored):
    """Proposta do Caio (inspirado em Ernest P. Chan, "Algorithmic Trading", 2013, cap. 2-3):
    reversão linear à média. Calcula o z-score do preço numa janela igual à meia-vida de
    reversão do ativo (regressão de Ornstein-Uhlenbeck); compra quando o z-score fica abaixo
    de -`entry_z` e sai quando volta a zero. Chan recomenda usar a meia-vida como janela para
    não escolher o parâmetro olhando o resultado."""

    def __init__(self, lookback: int = 20, entry_z: float = 2.0):
        super().__init__()
        self.n = max(5, int(lookback))
        self.entry_z = entry_z
        self.name = f"Reversão por z-score ({self.n} candles, z<-{entry_z:g})"
        self.description = f"Compra quando o preço fica {entry_z:g} desvios abaixo da média de {self.n} e sai na média."
        self.min_bars = self.n + 2

    def _compute(self, bars):
        closes = [b.close for b in bars]
        out, prev = {}, 0.0
        for i, b in enumerate(bars):
            if i < self.n:
                out[b.ts] = (0.0, 0.0)
                continue
            win = closes[i - self.n + 1 : i + 1]
            mean = sum(win) / self.n
            sd = math.sqrt(sum((x - mean) ** 2 for x in win) / self.n)
            z = (closes[i] - mean) / sd if sd > 0 else 0.0
            out[b.ts] = (prev, z)
            prev = z
        return out

    def analyze(self, bars):
        if len(bars) < self.min_bars:
            return None
        prev, z = self._get(bars) or (0.0, 0.0)
        if z < -self.entry_z <= prev:
            return f"z-score {z:.1f}: preço muito abaixo da média de {self.n}"
        return None

    def should_exit(self, bars):
        got = self._get(bars) if bars else None
        return bool(got) and got[1] >= 0


BEAR_POINTS = (
    "IFR(14) acima de 75 (sobrecomprado)",
    "preço mais de 3 ATR acima da média de 20 (esticado)",
    "volatilidade entre as 10% maiores do último ano",
    "média de 50 caindo",
    "preço abaixo da média de 200",
)


def bear_case(bars: Sequence[Bar]) -> list[list[str]]:
    """Os argumentos do "urso" em cada candle (sem olhar o futuro)."""
    closes = [b.close for b in bars]
    rsi = _rsi_series(closes, 14)
    sma20, sma50, sma200 = _sma_series(closes, 20), _sma_series(closes, 50), _sma_series(closes, 200)
    atr = _atr_series(bars, 14)
    atr_pct = [a / c if a is not None and c else None for a, c in zip(atr, closes)]
    out = []
    for i in range(len(bars)):
        pts = []
        if rsi[i] is not None and rsi[i] > 75:
            pts.append(BEAR_POINTS[0])
        if sma20[i] is not None and atr[i] and closes[i] - sma20[i] > 3 * atr[i]:
            pts.append(BEAR_POINTS[1])
        hist = [x for x in atr_pct[max(0, i - 250) : i] if x is not None]
        if len(hist) >= 100 and atr_pct[i] is not None:
            rank = sum(x < atr_pct[i] for x in hist) / len(hist)
            if rank >= 0.9:
                pts.append(BEAR_POINTS[2])
        if i >= 10 and sma50[i] is not None and sma50[i - 10] is not None and sma50[i] < sma50[i - 10]:
            pts.append(BEAR_POINTS[3])
        if sma200[i] is not None and closes[i] < sma200[i]:
            pts.append(BEAR_POINTS[4])
        out.append(pts)
    return out


def bull_case(bars: Sequence[Bar]) -> list[str]:
    """Os argumentos do "touro" no último candle."""
    closes = [b.close for b in bars]
    pts = []
    sma50, sma200 = _sma_series(closes, 50)[-1], _sma_series(closes, 200)[-1]
    if sma200 is not None and closes[-1] > sma200:
        pts.append("preço acima da média de 200 (tendência de fundo de alta)")
    if sma50 is not None and sma200 is not None and sma50 > sma200:
        pts.append("média de 50 acima da de 200")
    if len(closes) > 28 and closes[-1] > closes[-29]:
        pts.append(f"retorno de 28 candles positivo ({closes[-1] / closes[-29] - 1:+.1%})")
    if len(bars) > 21 and closes[-1] >= max(b.high for b in bars[-21:-1]):
        pts.append("rompeu a máxima de 20 candles")
    rsi = _rsi_series(closes, 14)[-1]
    if rsi is not None and 50 <= rsi <= 70:
        pts.append(f"IFR(14) {rsi:.0f}: força sem exagero")
    return pts


class BearFilter(Strategy):
    """Proposta da Lia (inspirada no TradingAgents, Xiao et al. 2024, e no AI Hedge Fund):
    antes de cada entrada, um "pesquisador urso" levanta os argumentos contra a compra.
    Se ele juntar `max_points` ou mais, a entrada é vetada. A saída e as travas continuam
    as mesmas da estratégia original."""

    def __init__(self, inner: Strategy, max_points: int = 3):
        self.inner = inner
        self.max_points = max_points
        self.name = f"{inner.name} + veto do urso ({max_points}+ pontos)"
        self.description = f"{inner.description} Não entra quando o urso junta {max_points} ou mais argumentos contra."
        self.min_bars = inner.min_bars
        self.lookback = max(inner.window, 270)
        self.has_exit = inner.has_exit
        self.day_trade = inner.day_trade
        self._bear: dict = {}

    def prepare(self, bars):
        self.inner.prepare(bars)
        self._bear = {b.ts: len(p) for b, p in zip(bars, bear_case(bars))}

    def decide(self, bars):
        entry = self.inner.decide(bars)
        if entry is None:
            return None
        if bars[-1].ts not in self._bear:
            self._bear = {b.ts: len(p) for b, p in zip(bars, bear_case(bars))}
        if self._bear.get(bars[-1].ts, 0) >= self.max_points:
            return None
        return entry

    def analyze(self, bars):  # não é usado: a decisão passa por decide()
        entry = self.decide(bars)
        return entry.reason if entry else None

    def exit_signal(self, bars, side):
        return self.inner.exit_signal(bars, side)

    def should_exit(self, bars):
        return self.inner.should_exit(bars)
