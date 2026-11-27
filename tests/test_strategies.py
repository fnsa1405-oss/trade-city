from datetime import datetime, timedelta, timezone

from trade_city.models import Bar
from trade_city.strategies import MeanReversion, OpeningRangeBreakout, TrendFollower

from conftest import make_bars


def test_trend_breakout_fires_only_in_uptrend():
    strat = TrendFollower(fast=5, slow=10, breakout=5)
    up = make_bars([100 + i for i in range(30)])
    down = make_bars([130 - i for i in range(30)])
    assert strat.analyze(up) is not None
    assert strat.analyze(down) is None


def test_mean_reversion_dip_in_uptrend():
    strat = MeanReversion(rsi_n=2, threshold=10, trend=20, exit_n=3)
    closes = [100 + i for i in range(25)] + [122, 119]
    bars = make_bars(closes)
    assert strat.analyze(bars) is not None
    assert strat.should_exit(make_bars(closes + [125]))


def _session(day, closes):
    # 5 min a partir de 9:30 em Nova York (14:30 UTC no inverno)
    start = datetime(2026, 1, day, 14, 30, tzinfo=timezone.utc)
    return [Bar(start + timedelta(minutes=5 * i), c, c + 0.1, c - 0.1, c, 1000) for i, c in enumerate(closes)]


def test_opening_range_first_breakout_only():
    strat = OpeningRangeBreakout(range_minutes=30)
    opening = [100, 100.2, 100.1, 99.9, 100.0, 100.1]  # máxima da faixa: 100.3
    flat = _session(5, opening + [100.2])
    assert strat.analyze(flat) is None
    breakout = _session(5, opening + [100.2, 100.6])
    assert strat.analyze(breakout) is not None
    second = _session(5, opening + [100.2, 100.6, 100.1, 100.7])
    assert strat.analyze(second) is None


def test_opening_range_flat_before_close():
    strat = OpeningRangeBreakout()
    late = _session(5, [100] * 76)  # até 15:45 NY
    assert strat.should_exit(late)
    assert not strat.should_exit(late[:30])
