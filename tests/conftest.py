import math
from datetime import datetime, timedelta, timezone

import pytest

from trade_city.models import Bar


def make_bars(closes, start=datetime(2026, 1, 1, tzinfo=timezone.utc), step=timedelta(hours=1), spread=0.002):
    bars = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        hi = max(o, c) * (1 + spread)
        lo = min(o, c) * (1 - spread)
        bars.append(Bar(start + i * step, o, hi, lo, c, 1000))
        prev = c
    return bars


@pytest.fixture
def uptrend():
    # tendência de alta com ondas, para gerar rompimentos
    closes = [100 * (1.002 ** i) * (1 + 0.02 * math.sin(i / 6)) for i in range(400)]
    return make_bars(closes)
