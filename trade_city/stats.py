"""Contas do placar, compartilhadas pela mesa ao vivo e pelo backtest."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class TraderStats:
    capital: float
    peak_capital: float
    day_wins: int
    day_losses: int
    day_pnl: float
    recent_outcomes: list[bool]
    realized_pnl: float


def day_start(now: datetime, tz: str) -> datetime:
    local = now.astimezone(ZoneInfo(tz))
    return datetime.combine(local.date(), time(0), tzinfo=ZoneInfo(tz))


def compute_stats(base_capital: float, all_pnls: Sequence[float], day_pnls: Sequence[float]) -> TraderStats:
    capital = peak = base_capital
    for pnl in all_pnls:
        capital += pnl
        peak = max(peak, capital)
    return TraderStats(
        capital=capital,
        peak_capital=peak,
        day_wins=sum(1 for p in day_pnls if p > 0),
        day_losses=sum(1 for p in day_pnls if p <= 0),
        day_pnl=sum(day_pnls),
        recent_outcomes=[p > 0 for p in all_pnls[-10:]],
        realized_pnl=capital - base_capital,
    )
