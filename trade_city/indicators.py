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
