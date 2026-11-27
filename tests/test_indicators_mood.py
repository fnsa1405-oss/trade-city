from trade_city.indicators import atr, highest, rsi, sma
from trade_city.mood import Mood, compute_mood

from conftest import make_bars


def test_sma_and_highest():
    assert sma([1, 2, 3, 4], 2) == 3.5
    assert sma([1], 2) is None
    assert highest([1, 5, 3], 2) == 5


def test_atr_constant_range():
    bars = make_bars([100] * 20, spread=0.01)
    assert abs(atr(bars, 14) - 2.0) < 1e-9


def test_rsi_extremes():
    assert rsi([1, 2, 3], 2) == 100.0
    assert rsi([3, 2, 1], 2) == 0.0


def test_mood_rules():
    assert compute_mood([False, False, False], 0) is Mood.PERIGO
    assert compute_mood([True, False], -10) is Mood.ALERTA
    assert compute_mood([True, True, True], 50) is Mood.CONFIANTE
    assert compute_mood([True, False], 5) is Mood.NORMAL
    assert Mood.PERIGO.size_multiplier < Mood.NORMAL.size_multiplier < Mood.CONFIANTE.size_multiplier
