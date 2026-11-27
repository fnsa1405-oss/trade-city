"""Carregar e salvar candles em CSV (ts,open,high,low,close,volume)."""
from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import datetime, timezone

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
