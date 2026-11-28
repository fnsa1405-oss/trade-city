from datetime import datetime

from trade_city.backtest import run_backtest
from trade_city.config import RiskConfig
from trade_city.intraday import NY
from trade_city.models import Side
from trade_city.school import MEDIAS_DAY
from trade_city.strategies import MovingAverageTrend
from trade_city.strategies.medias import TRIGGERS, sma_aligned

from test_daytrade import day_trader, session_bars


def up(_d):
    return 0.0003


def down(_d):
    return -0.0003


def test_sma_aligned():
    assert sma_aligned([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]


def test_school_has_every_trigger_and_alignment_only_on_1min():
    assert len(MEDIAS_DAY) == 15 and all(c.timeframes == ("1min",) for c in MEDIAS_DAY)
    assert {c.make().trigger for c in MEDIAS_DAY} == set(TRIGGERS)


def test_trades_only_with_the_averages():
    """Em alta só compra; em queda só vende; e sempre zera no mesmo dia."""
    for drift, side in ((up, Side.LONG), (down, Side.SHORT)):
        bars = session_bars(days=8, step=1, seed=3, drift=drift)
        sides = set()
        for t in TRIGGERS:
            rep = run_backtest(day_trader(MovingAverageTrend(t, (15, 5))), bars, RiskConfig())
            for tr in rep.trades:
                sides.add(tr.side)
                assert tr.opened_at.astimezone(NY).date() == tr.closed_at.astimezone(NY).date()
                assert tr.closed_at.astimezone(NY).time() <= datetime(2026, 1, 1, 15, 55).time()
        assert sides == {side}


def test_needs_1min_bars_and_does_not_look_ahead():
    bars5 = session_bars(days=20, step=5, seed=3, drift=up)
    assert run_backtest(day_trader(MovingAverageTrend("pc", (15, 5))), bars5, RiskConfig()).trades == []
    bars = session_bars(days=8, step=1, seed=3, drift=up)
    full = MovingAverageTrend("pc", (15, 5))
    full.prepare(bars)
    for n in range(len(bars) - 400, len(bars), 7):
        part = MovingAverageTrend("pc", (15, 5))
        a, b = full.decide(bars[:n]), part.decide(bars[:n])
        assert (a is None) == (b is None) and (a is None or (a.side, a.stop, a.trigger) == (b.side, b.stop, b.trigger))
