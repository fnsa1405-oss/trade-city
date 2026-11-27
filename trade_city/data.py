"""Carregar e salvar candles em CSV (ts,open,high,low,close,volume)."""
from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone

from .models import Bar


def load_csv(path: str) -> list[Bar]:
    bars = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            ts = datetime.fromisoformat(row["ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            bars.append(Bar(ts, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), float(row.get("volume") or 0)))
    bars.sort(key=lambda b: b.ts)
    return bars


def save_csv(path: str, bars: Iterable[Bar]) -> None:
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ts", "open", "high", "low", "close", "volume"])
        for b in bars:
            writer.writerow([b.ts.isoformat(), b.open, b.high, b.low, b.close, b.volume])


def resample(bars: list[Bar], hours: int) -> list[Bar]:
    """Junta candles em blocos de `hours` horas (alinhados à meia-noite UTC).
    Blocos incompletos nas pontas são descartados."""
    if hours <= 0:
        raise ValueError("hours precisa ser positivo")
    if not bars:
        return []
    span = timedelta(hours=hours)
    base_step = bars[1].ts - bars[0].ts if len(bars) > 1 else span
    expected = max(1, round(span / base_step))
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    groups: dict[datetime, list[Bar]] = {}
    for b in bars:
        start = epoch + ((b.ts - epoch) // span) * span
        groups.setdefault(start, []).append(b)
    out = []
    for start in sorted(groups):
        g = groups[start]
        if len(g) < expected * 0.9:  # bloco incompleto ou com muitas falhas
            continue
        out.append(Bar(start, g[0].open, max(b.high for b in g), min(b.low for b in g), g[-1].close, sum(b.volume for b in g)))
    return out
