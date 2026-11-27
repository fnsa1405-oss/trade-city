import math

from trade_city.indicators import adx_series, ema
from trade_city.strategies import ConnorsRSI2, DoubleSevens, HolyGrail, TurtleBreakout, WilliamsBreakout

from conftest import make_bars


def test_ema_and_adx_behave():
    assert abs(ema([1.0] * 30, 10) - 1.0) < 1e-12
    trend = make_bars([100 + 2 * i for i in range(80)])
    flat = make_bars([100 + math.sin(i) for i in range(80)])
    assert adx_series(trend)[-1] > 40
    assert adx_series(flat)[-1] < adx_series(trend)[-1]


def test_turtle_entry_and_exit():
    t = TurtleBreakout(20, 10)
    up = make_bars([100 + i for i in range(30)])
    assert t.analyze(up) is not None
    drop = make_bars([100 + i for i in range(30)] + [100])
    assert t.should_exit(drop)


def test_connors_rsi2_needs_trend_and_dip():
    closes = [100 + 0.2 * i for i in range(220)] + [140, 138, 136]
    assert ConnorsRSI2().analyze(make_bars(closes)) is not None
    assert ConnorsRSI2().analyze(make_bars([200 - 0.2 * i for i in range(223)])) is None


def test_double_sevens():
    closes = [100 + 0.2 * i for i in range(210)] + [141, 140.5]
    s = DoubleSevens()
    assert s.analyze(make_bars(closes)) is not None
    assert s.should_exit(make_bars(closes + [150]))


def test_holy_grail_pullback_in_strong_trend():
    closes = [100 + 1.5 * i + 3 * math.sin(i) for i in range(70)]
    top = closes[-1]
    bars = make_bars(closes + [top - 7, top - 14, top - 5.6], spread=0.002)  # recuo até a MME20 e retomada
    s = HolyGrail()
    assert s.analyze(bars) is not None
    assert s.analyze(bars[:-1]) is None  # ainda no recuo, sem rompimento
    assert s.analyze(make_bars(closes, spread=0.002)) is None  # sem recuo até a média


def test_williams_breakout_time_exit():
    s = WilliamsBreakout(0.5)
    bars = make_bars([100, 101, 104])
    assert s.analyze(bars) is not None
    assert s.should_exit(bars)
