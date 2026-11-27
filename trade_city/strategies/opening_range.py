from __future__ import annotations

from collections.abc import Sequence
from datetime import time
from zoneinfo import ZoneInfo

from ..models import Bar
from .base import Strategy

NY = ZoneInfo("America/New_York")


class OpeningRangeBreakout(Strategy):
    """Rompimento da faixa de abertura do pregão americano (candles intradiários)."""

    has_exit = True
    name = "rompimento da faixa de abertura"
    description = "Marca a máxima dos primeiros {minutes} minutos do pregão e compra no primeiro fechamento acima dela."

    def __init__(
        self,
        range_minutes: int = 30,
        last_entry: time = time(15, 0),
        flat_after: time = time(15, 45),
        lookback: int = 120,
    ):
        self.range_minutes = range_minutes
        self.open_time = time(9, 30)
        start = 9 * 60 + 30 + range_minutes
        self.range_end = time(start // 60, start % 60)
        self.last_entry = last_entry
        self.flat_after = flat_after  # zera antes do fim do pregão, nunca dorme posicionado
        self.min_bars = 2
        self.lookback = lookback
        self.description = self.description.format(minutes=range_minutes)

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        if len(bars) < self.min_bars:
            return None
        last_local = bars[-1].ts.astimezone(NY)
        today = [b for b in bars if b.ts.astimezone(NY).date() == last_local.date()]
        opening = [b for b in today if self.open_time <= b.ts.astimezone(NY).time() < self.range_end]
        after = [b for b in today if b.ts.astimezone(NY).time() >= self.range_end]
        if not opening or not after or after[-1] is not bars[-1]:
            return None
        if opening[0].ts.astimezone(NY).time() != self.open_time:
            return None  # faixa incompleta (faltou o primeiro candle)
        if last_local.time() >= self.last_entry:
            return None
        range_high = max(b.high for b in opening)
        if bars[-1].close <= range_high:
            return None
        if any(b.close > range_high for b in after[:-1]):
            return None  # só o primeiro rompimento do dia
        return f"rompeu a máxima dos primeiros {self.range_minutes} min ({range_high:.2f})"

    def should_exit(self, bars: Sequence[Bar]) -> bool:
        return bool(bars) and bars[-1].ts.astimezone(NY).time() >= self.flat_after
