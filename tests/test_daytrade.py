import random
import sqlite3
from datetime import date, datetime, time, timedelta, timezone

import pytest

from trade_city.backtest import run_backtest
from trade_city.broker.paper import PaperBroker
from trade_city.config import RiskConfig, TraderProfile
from trade_city.intraday import NY, Timeline, dow_structure, heikin_ashi, higher_timeframe, regular_session
from trade_city.ledger import Ledger
from trade_city.models import AssetClass, Bar, Side, Signal, TradePlan
from trade_city.mood import Mood
from trade_city.risk import Guardian
from trade_city.school import DAY_CANDIDATES, DAY_RISK_VARIANTS, evaluate
from trade_city.strategies import NoiseAreaMomentum, OpeningRangeDayTrade


def session_bars(days=30, step=5, seed=1, start=date(2026, 3, 2), drift=None):
    """Pregões sintéticos de 9h30 às 16h de Nova York (dias úteis)."""
    rng = random.Random(seed)
    bars, price, d = [], 100.0, start
    while len(bars) < days * (390 // step):
        if d.weekday() < 5:
            trend = drift(d) if drift else rng.choice([-1, 1]) * 0.0004
            t = datetime.combine(d, time(9, 30), tzinfo=NY)
            for k in range(390 // step):
                o = price
                price = max(1.0, price * (1 + trend + rng.gauss(0, 0.001)))
                hi, lo = max(o, price) * 1.0005, min(o, price) * 0.9995
                bars.append(Bar((t + timedelta(minutes=k * step)).astimezone(timezone.utc), o, hi, lo, price, 1000))
        d += timedelta(days=1)
    return bars


def day_trader(strategy, symbol="SPY"):
    return TraderProfile("davi", "Davi", "teste", symbol, AssetClass.EQUITY, "5min", strategy, capital=10_000, day_trade=True)


def test_timeline_and_higher_timeframe_have_no_lookahead():
    bars = session_bars(days=2)
    tl = Timeline.build(bars)
    assert tl.step == 5 and tl.start_min[0] == 570 and tl.day_index[78] == 0
    h1 = higher_timeframe(tl, 60)
    assert len(h1.bars) == 14  # 6 candles de 60 min + o de 15h30-16h, por dia
    # o candle de 9h30-10h30 só conta como fechado no candle de 5 min que termina às 10h30
    assert h1.done_at[10] == 0 and h1.done_at[11] == 1
    assert h1.bars[0].high == max(b.high for b in bars[:12])
    m15 = higher_timeframe(tl, 15)
    assert len(m15.bars) == 52


def test_regular_session_filters_extended_hours():
    t = datetime(2026, 3, 2, 8, 0, tzinfo=NY)
    bars = [Bar((t + timedelta(minutes=30 * k)).astimezone(timezone.utc), 1, 1, 1, 1) for k in range(20)]
    kept = regular_session(bars)
    assert [b.ts.astimezone(NY).time() for b in kept][0] == time(9, 30)
    assert all(time(9, 30) <= b.ts.astimezone(NY).time() < time(16) for b in kept)


def test_heikin_ashi_and_dow():
    up = [Bar(datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i), p, p + 1, p - 1, p + 0.5) for i, p in
          enumerate([10, 12, 11, 14, 13, 16, 15, 18, 17, 20, 19, 22])]
    ha = heikin_ashi(up)
    assert ha[-1].close > ha[-1].open
    st = dow_structure(up, 1)
    assert st.trend[-1] == "alta"
    down = [Bar(b.ts, -b.open + 40, -b.low + 40, -b.high + 40, -b.close + 40) for b in up]
    assert dow_structure(down, 1).trend[-1] == "baixa"


def test_guardian_uses_chart_stop_and_supports_short():
    bars = session_bars(days=1)
    g = Guardian(RiskConfig(reward_ratio=2.0))
    sig = Signal("davi", "SPY", 100.0, "teste", bars[-1].ts, Side.SHORT, 101.0)
    plan, _ = g.plan(sig, bars[-20:], 10_000, Mood.NORMAL, AssetClass.EQUITY)
    assert plan.stop_loss == pytest.approx(101.0) and plan.take_profit == pytest.approx(98.0)
    assert plan.reward_ratio == pytest.approx(2.0)
    crypto = Signal("bia", "BTC/USD", 100.0, "teste", bars[-1].ts, Side.SHORT)
    assert g.plan(crypto, bars[-20:], 10_000, Mood.NORMAL, AssetClass.CRYPTO)[0] is None


def test_orb_trades_both_sides_and_never_holds_overnight():
    bars = session_bars(days=30, seed=3)
    report = run_backtest(day_trader(OpeningRangeDayTrade(5)), bars, RiskConfig(reward_ratio=10.0))
    assert len(report.trades) >= 20
    assert {t.side for t in report.trades} == {Side.LONG, Side.SHORT}
    for t in report.trades:
        assert t.opened_at.astimezone(NY).date() == t.closed_at.astimezone(NY).date()
        assert t.opened_at.astimezone(NY).time() == time(9, 35)
        assert t.closed_at.astimezone(NY).time() <= time(15, 50)


def test_short_profits_when_price_falls():
    bars = session_bars(days=10, seed=5, drift=lambda d: -0.0008)
    report = run_backtest(day_trader(OpeningRangeDayTrade(5)), bars, RiskConfig(reward_ratio=50.0))
    shorts = [t for t in report.trades if t.side is Side.SHORT]
    assert shorts and sum(t.pnl for t in shorts) > 0


def test_noise_area_needs_history_then_trades():
    bars = session_bars(days=30, seed=7, drift=lambda d: 0.0006 if d.day % 2 else -0.0006)
    report = run_backtest(day_trader(NoiseAreaMomentum(14)), bars, RiskConfig(reward_ratio=50.0))
    assert report.trades
    first_day = bars[0].ts.astimezone(NY).date()
    days_before = {b.ts.astimezone(NY).date() for b in bars if b.ts <= report.trades[0].opened_at}
    assert len(days_before) >= 12 and min(days_before) == first_day
    assert all(t.closed_at.astimezone(NY).date() == t.opened_at.astimezone(NY).date() for t in report.trades)


@pytest.mark.parametrize("step", [5, 1])
def test_all_day_candidates_run_in_school(step):
    bars = session_bars(days=20 if step == 5 else 6, step=step, seed=11)
    results = evaluate(day_trader(OpeningRangeDayTrade(5)), {f"{step}min": bars})
    # sem regra de saída própria, os alvos distantes (10x e saída da estratégia) não são testados
    expected = sum(len(DAY_RISK_VARIANTS) if c.make().has_exit else sum(r.reward_ratio < 10 for r in DAY_RISK_VARIANTS) for c in DAY_CANDIDATES)
    assert len(results) == expected


def test_paper_broker_short_cash_and_stop():
    from test_paper_broker import Clock, FakeFeed, T0

    feed, clock = FakeFeed(price=100.0), Clock(T0)
    broker = PaperBroker(sqlite3.connect(":memory:"), feed=feed, initial_cash=10_000, clock=clock, slippage=0.0)
    sig = Signal("davi", "SPY", 100.0, "teste", T0, Side.SHORT, 102.0)
    plan = TradePlan(sig, 10, 102.0, 96.0, 20.0, "normal")
    broker.submit_entry(plan, AssetClass.EQUITY)
    assert broker.buying_power() == pytest.approx(9_000)
    feed.price = 97.0
    fill = broker.close_position("SPY")
    assert fill.price == pytest.approx(97.0)
    assert broker.buying_power() == pytest.approx(10_030)
    broker.submit_entry(plan, AssetClass.EQUITY)
    feed.bars = [Bar(T0 + timedelta(hours=1), 100, 103, 99, 101)]
    feed.price = 100.5
    clock.now = T0 + timedelta(hours=2)
    assert broker.get_position("SPY") is None
    assert broker.last_exit_price("SPY") == pytest.approx(102.0)


def test_ledger_short_pnl_and_old_books():
    conn_path = ":memory:"
    ledger = Ledger(conn_path)
    tid = ledger.open_trade("davi", "SPY", 10, 100.0, 102.0, 96.0, datetime(2026, 3, 2, tzinfo=timezone.utc), side=Side.SHORT)
    assert ledger.open_trade_for("davi").side is Side.SHORT
    assert ledger.close_trade(tid, 97.0, datetime(2026, 3, 2, 1, tzinfo=timezone.utc), "teste") == pytest.approx(30.0)


def test_desk_day_trade_flattens_before_close_and_groups():
    from trade_city.__main__ import _desk
    from trade_city.broker import SimBroker
    from trade_city.desk import Desk

    class Clock:
        def __init__(self, now):
            self.now = now

        def __call__(self):
            return self.now

    bars = session_bars(days=6, seed=3)
    broker = SimBroker()
    broker.bars["SPY"] = bars
    clock = Clock(datetime(2026, 3, 9, 15, 56, tzinfo=NY))
    trader = day_trader(OpeningRangeDayTrade(5))
    ledger = Ledger(":memory:")
    desk = Desk([trader], broker, ledger, RiskConfig(), clock=clock)
    ledger.open_trade("davi", "SPY", 10, 100.0, 98.0, 110.0, clock.now, side=Side.LONG)
    broker.positions["SPY"] = __import__("trade_city.broker.base", fromlist=["Position"]).Position("SPY", 10, 100.0)
    broker.prices["SPY"] = 101.0
    events = desk.run_once()
    assert any("fim do pregão" in e for e in events), events
    assert ledger.open_trade_for("davi") is None

    day = {t.key for t in _desk(":memory:", grupo="day").traders}
    swing = {t.key for t in _desk(":memory:", grupo="swing").traders}
    assert day == set() and swing == {"rui", "teo", "lena", "davi", "sol", "dora", "bia"}  # Bia aprovada na escola de fluxo (28/11/2026)
