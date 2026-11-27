from datetime import datetime, timedelta, timezone

import pytest

from conftest import make_bars

from trade_city.backtest import run_backtest
from trade_city.intraday import NY
from trade_city.config import RiskConfig, TraderProfile
from trade_city.models import AssetClass
from trade_city.strategies import DonchianEnsemble, DowSwing, HeikinAshiTrend, MondayAsiaOpen, Supertrend


def trader(strategy, tf="1d"):
    return TraderProfile("bia", "Bia", "teste", "BTC/USD", AssetClass.CRYPTO, tf, strategy, capital=10_000)


def wave(n=900):
    import math

    # ondas longas com recuos curtos (zigue-zague de 6 candles) no meio
    return [100 + 30 * math.sin(i / 25) + i * 0.02 + 2.5 * math.sin(i * math.pi / 3) for i in range(n)]


@pytest.mark.parametrize(
    "strategy",
    [DonchianEnsemble((5, 10, 20, 60)), Supertrend(10, 3.0), HeikinAshiTrend(), DowSwing(3)],
    ids=["donchian", "supertrend", "heikin-ashi", "dow"],
)
def test_crypto_trend_strategies_catch_waves(strategy):
    bars = make_bars(wave(), step=timedelta(days=1), spread=0.01)
    report = run_backtest(trader(strategy), bars, RiskConfig(atr_stop_multiple=3.0, reward_ratio=50.0))
    assert len(report.trades) >= 3
    assert report.total_pnl > 0


def test_donchian_same_result_in_window_and_full_history():
    bars = make_bars(wave(), step=timedelta(days=1))
    full = DonchianEnsemble((5, 10, 20, 60))
    full.prepare(bars)
    windowed = DonchianEnsemble((5, 10, 20, 60))
    i = 700
    assert full._score[bars[i].ts][1] == pytest.approx(windowed._get(bars[: i + 1])[1])


def test_monday_asia_open_enters_sunday_7pm_new_york_and_holds_24h():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = make_bars([100 + i * 0.01 for i in range(24 * 60)], start=start, step=timedelta(hours=1))
    report = run_backtest(trader(MondayAsiaOpen(), "1h"), bars, RiskConfig(atr_stop_multiple=20.0, reward_ratio=50.0))
    assert len(report.trades) >= 5
    for t in report.trades:
        assert t.opened_at.astimezone(NY).strftime("%a %H") == "Sun 19"
        assert t.closed_at - t.opened_at == timedelta(hours=23)
