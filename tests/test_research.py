from datetime import datetime, timedelta, timezone

from trade_city.intraday import NY
from trade_city.models import Bar
from trade_city.strategies import CumulativeRSI, IBSReversion, TimeSeriesMomentum, TurnOfMonth


def days(closes, start=datetime(2025, 1, 2), weekdays_only=True, bar=None):
    out, d = [], start
    for c in closes:
        while weekdays_only and d.weekday() >= 5:
            d += timedelta(days=1)
        lo, hi = bar(c) if bar else (c * 0.99, c * 1.01)
        out.append(Bar(datetime(d.year, d.month, d.day, tzinfo=NY).astimezone(timezone.utc), c, hi, lo, c, 1000))
        d += timedelta(days=1)
    return out


def test_time_series_momentum_enters_on_turn_and_exits_when_negative():
    s = TimeSeriesMomentum(5)
    closes = [100 - k for k in range(10)] + [91, 92, 93, 96, 100]
    bars = days(closes)
    hits = [k for k in range(7, len(bars)) if s.analyze(bars[: k + 1])]
    assert hits and all(bars[k].close > bars[k - 5].close for k in hits)
    assert len(hits) == 1  # só na virada, não a cada candle
    assert s.should_exit(days(closes + [80]))


def test_turn_of_month_last_trading_day_and_exit_on_third():
    # 2025-01-31 é sexta, último pregão de janeiro
    bars = days([100] * 40, start=datetime(2024, 12, 20))
    s = TurnOfMonth()
    signals = [b.ts.astimezone(NY).date() for k, b in enumerate(bars) if k >= 5 and s.analyze(bars[: k + 1])]
    assert datetime(2024, 12, 31).date() in signals and datetime(2025, 1, 31).date() in signals
    assert len(signals) == 2
    jan = [k for k, b in enumerate(bars) if b.ts.astimezone(NY).month == 1]
    assert not s.should_exit(bars[: jan[1] + 1]) and s.should_exit(bars[: jan[2] + 1])


def test_ibs_and_cumulative_rsi():
    up = [100 + k * 0.5 for k in range(210)]
    bars = days(up)
    weak = bars[:-1] + [Bar(bars[-1].ts, up[-1], up[-1] + 2, up[-1] - 0.1, up[-1], 1000)]
    s = IBSReversion()
    assert s.analyze(weak) is not None  # fechou perto da mínima, acima da MM200
    assert s.analyze(bars) is None
    strong = bars[:-1] + [Bar(bars[-1].ts, up[-1], up[-1] + 0.1, up[-1] - 2, up[-1], 1000)]
    assert s.should_exit(strong)

    dip = up[:-2] + [up[-3] - 1, up[-3] - 2]
    c = CumulativeRSI()
    assert c.analyze(days(dip)) is not None
    assert c.analyze(days(up)) is None
