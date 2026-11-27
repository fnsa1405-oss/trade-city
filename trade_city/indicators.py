"""Indicadores técnicos simples, sem dependências externas."""
from __future__ import annotations

from collections.abc import Sequence

from .models import Bar


def sma(values: Sequence[float], n: int) -> float | None:
    if n <= 0 or len(values) < n:
        return None
    return sum(values[-n:]) / n


def highest(values: Sequence[float], n: int) -> float | None:
    if n <= 0 or len(values) < n:
        return None
    return max(values[-n:])


def lowest(values: Sequence[float], n: int) -> float | None:
    if n <= 0 or len(values) < n:
        return None
    return min(values[-n:])


def atr(bars: Sequence[Bar], n: int = 14) -> float | None:
    """Average True Range (média simples dos últimos n true ranges)."""
    if n <= 0 or len(bars) < n + 1:
        return None
    trs = []
    for prev, cur in zip(bars[-n - 1 : -1], bars[-n:]):
        trs.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
    return sum(trs) / n


def rsi(closes: Sequence[float], n: int) -> float | None:
    """RSI com médias simples das últimas n variações (0 a 100)."""
    if n <= 0 or len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for prev, cur in zip(closes[-n - 1 : -1], closes[-n:]):
        change = cur - prev
        if change > 0:
            gains += change
        else:
            losses -= change
    if losses == 0:
        return 100.0 if gains > 0 else 50.0
    rs = gains / losses
    return 100.0 - 100.0 / (1.0 + rs)


def ema_series(values: Sequence[float], n: int) -> list[float]:
    """Média móvel exponencial para toda a série (semente = média simples dos n primeiros)."""
    if n <= 0 or len(values) < n:
        return []
    k = 2.0 / (n + 1)
    out = [sum(values[:n]) / n]
    for v in values[n:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


def ema(values: Sequence[float], n: int) -> float | None:
    series = ema_series(values, n)
    return series[-1] if series else None


def adx_series(bars: Sequence[Bar], n: int = 14) -> list[float]:
    """ADX de Wilder. Devolve a série (vazia se não houver candles suficientes)."""
    if len(bars) < 2 * n + 1:
        return []
    trs, pdm, mdm = [], [], []
    for prev, cur in zip(bars[:-1], bars[1:]):
        up, down = cur.high - prev.high, prev.low - cur.low
        pdm.append(up if up > down and up > 0 else 0.0)
        mdm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close)))
    tr_s, p_s, m_s = sum(trs[:n]), sum(pdm[:n]), sum(mdm[:n])
    dxs = []
    for i in range(n, len(trs) + 1):
        if i > n:
            tr_s = tr_s - tr_s / n + trs[i - 1]
            p_s = p_s - p_s / n + pdm[i - 1]
            m_s = m_s - m_s / n + mdm[i - 1]
        pdi = 100 * p_s / tr_s if tr_s else 0.0
        mdi = 100 * m_s / tr_s if tr_s else 0.0
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0.0)
    if len(dxs) < n:
        return []
    adx = [sum(dxs[:n]) / n]
    for dx in dxs[n:]:
        adx.append((adx[-1] * (n - 1) + dx) / n)
    return adx
