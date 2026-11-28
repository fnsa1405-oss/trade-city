import math
from datetime import date, datetime, timedelta, timezone

from tests.conftest import make_bars
from trade_city.carteira import clusters, corr, daily_series, max_drawdown, monte_carlo_dd, portfolio_report, risk_parity
from trade_city.config import default_traders
from trade_city.models import ClosedTrade


def test_daily_series_spreads_pnl():
    t = ClosedTrade("a", "X", 1, 1, 2, 30.0, datetime(2024, 1, 2, tzinfo=timezone.utc), datetime(2024, 1, 4, tzinfo=timezone.utc), "x")
    s = daily_series([t], date(2024, 1, 1), date(2024, 1, 5))
    assert s == [0, 10, 10, 10, 0]


def test_clusters_and_parity():
    keys = ["teo", "lena", "rui"]
    m = {(a, b): 1.0 if a == b else 0.0 for a in keys for b in keys}
    m[("teo", "lena")] = m[("lena", "teo")] = 0.9
    g = clusters(keys, m)
    assert g == [["teo", "lena"], ["rui"]]
    w = risk_parity(g, {"teo": 1.0, "lena": 1.0, "rui": 2.0})
    assert abs(sum(w.values()) - 3) < 1e-9
    assert abs(w["rui"] - 1.5) < 1e-9 and abs(w["teo"] - 0.75) < 1e-9


def test_drawdown_and_monte_carlo():
    assert abs(max_drawdown([0.1, -0.11, 0.05]) - 0.1) < 1e-9
    rets = [0.01 if i % 3 else -0.015 for i in range(400)]
    mc = monte_carlo_dd(rets, sims=200)
    assert 0 < mc < 1
    assert corr([1, 2, 3], [2, 4, 6]) > 0.99


def test_portfolio_report_with_fake_data():
    start = datetime(2019, 1, 1, tzinfo=timezone.utc)

    def bars_for(trader, days):
        step = timedelta(hours=4) if trader.timeframe == "4h" else timedelta(days=1)
        n = 3000 if trader.timeframe == "4h" else 1500
        phase = hash(trader.symbol) % 7
        closes = [100 * (1.0006 ** i) * (1 + 0.08 * math.sin(i / (25 + phase))) for i in range(n)]
        return make_bars(closes, start=start, step=step)

    text, alloc = portfolio_report(default_traders(), 1000, bars_for=bars_for)
    assert "Gestão de carteira" in text and "escolhido" in text
    assert set(alloc["weights"]) == {t.key for t in default_traders() if t.approved}
    assert abs(sum(alloc["weights"].values()) - len(alloc["weights"])) < 0.01
    assert alloc["risk_per_trade"] in (0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02)


def test_weekend_boost_only_for_crypto_on_weekends():
    from trade_city.config import RiskConfig, weekend_multiplier
    from trade_city.models import AssetClass

    cfg = RiskConfig(weekend_crypto_boost=1.5)
    sat = datetime(2026, 11, 28, 15, tzinfo=timezone.utc)
    mon = datetime(2026, 11, 30, 15, tzinfo=timezone.utc)
    assert weekend_multiplier(cfg, AssetClass.CRYPTO, sat) == 1.5
    assert weekend_multiplier(cfg, AssetClass.CRYPTO, mon) == 1.0
    assert weekend_multiplier(cfg, AssetClass.EQUITY, sat) == 1.0
    assert weekend_multiplier(RiskConfig(weekend_crypto_boost=1.0), AssetClass.CRYPTO, sat) == 1.0
