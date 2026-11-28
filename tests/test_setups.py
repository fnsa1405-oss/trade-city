from datetime import datetime, timedelta, timezone

import pytest

from trade_city.backtest import run_backtest
from trade_city.config import RiskConfig
from trade_city.intraday import NY
from trade_city.models import Bar, Entry, Side
from trade_city.school import DAY_CANDIDATES, with_15min
from trade_city.strategies import DayTradeStrategy

from test_daytrade import day_trader, session_bars


class ArmOnce(DayTradeStrategy):
    """Arma uma compra acima de `trigger` no candle `at` (minuto do dia), stop em `stop`."""

    name = "teste"
    description = "teste"

    def __init__(self, at, trigger, stop, valid=1):
        super().__init__()
        self.at, self.trigger, self.stop, self.valid = at, trigger, stop, valid

    def _entry(self, tl, i):
        if tl.end_min[i] == self.at and tl.dates[i] == tl.dates[0]:
            return Entry("teste", Side.LONG, self.stop, self.trigger, self.valid)
        return None


def flat_day(step=5, price=100.0):
    t = datetime(2026, 3, 2, 9, 30, tzinfo=NY)
    return [Bar((t + timedelta(minutes=k * step)).astimezone(timezone.utc), price, price + 0.05, price - 0.05, price, 1000) for k in range(390 // step)]


def test_stop_order_fills_only_when_price_breaks_the_trigger():
    bars = flat_day()
    k = 25  # rompe no candle seguinte ao sinal (o sinal fecha às 11h35)
    bars[k] = Bar(bars[k].ts, 100, 101.5, 99.95, 101.4, 1000)
    trader = day_trader(ArmOnce(at=11 * 60 + 35, trigger=101.0, stop=99.0))
    rep = run_backtest(trader, bars, RiskConfig(), slippage_pct=0.0)
    assert len(rep.trades) == 1
    assert rep.trades[0].entry_price == pytest.approx(101.0)

    # sem rompimento dentro da validade, a ordem vence e nada acontece
    trader = day_trader(ArmOnce(at=11 * 60 + 35, trigger=101.0, stop=99.0))
    rep = run_backtest(trader, flat_day(), RiskConfig(), slippage_pct=0.0)
    assert rep.trades == []


def test_one_minute_path_decides_what_came_first():
    """Num candle de 5 min que fez a mínima antes de romper o gatilho, o stop não pode contar."""
    bars5 = flat_day(5)
    fine = flat_day(1)
    k = 25  # candle de 11h35 a 11h40 (o seguinte ao sinal)
    bars5[k] = Bar(bars5[k].ts, 100, 101.5, 98.5, 101.4, 1000)
    base = 25 * 5
    fine[base + 0] = Bar(fine[base].ts, 100, 100.05, 98.5, 98.8, 100)  # primeiro cai abaixo do stop
    fine[base + 1] = Bar(fine[base + 1].ts, 98.8, 100.5, 98.8, 100.4, 100)
    fine[base + 2] = Bar(fine[base + 2].ts, 100.4, 101.5, 100.3, 101.4, 100)  # depois rompe
    for j in range(base + 3, len(fine)):
        fine[j] = Bar(fine[j].ts, 101.4, 101.45, 101.35, 101.4, 100)
    for j in range(k + 1, len(bars5)):
        bars5[j] = Bar(bars5[j].ts, 101.4, 101.45, 101.35, 101.4, 1000)

    pessimistic = run_backtest(day_trader(ArmOnce(11 * 60 + 35, 101.0, 99.0)), bars5, RiskConfig(), slippage_pct=0.0)
    assert pessimistic.trades[0].exit_reason == "stop loss"  # sem o 1 min, conta o stop

    real = run_backtest(day_trader(ArmOnce(11 * 60 + 35, 101.0, 99.0)), bars5, RiskConfig(), slippage_pct=0.0, fine=fine)
    assert len(real.trades) == 1 and real.trades[0].exit_reason != "stop loss"
    assert real.trades[0].pnl > 0


@pytest.mark.parametrize("cand", [c for c in DAY_CANDIDATES if c.label.startswith(("Larry", "Stormer", "Ponto", "Falha", "Fibonacci", "IFR2"))], ids=lambda c: c.label)
def test_every_setup_runs_and_respects_day_trade(cand):
    bars = session_bars(days=12, seed=5)
    rep = run_backtest(day_trader(cand.make()), bars, RiskConfig())
    for t in rep.trades:
        assert t.opened_at.astimezone(NY).date() == t.closed_at.astimezone(NY).date()
        assert t.closed_at.astimezone(NY).time() <= datetime(2026, 1, 1, 15, 55).time()


def test_setups_trade_on_trending_days():
    bars = session_bars(days=12, seed=2)
    cands = [c for c in DAY_CANDIDATES if c.timeframes is None or "5min" in c.timeframes]
    traded = sum(bool(run_backtest(day_trader(c.make()), bars, RiskConfig()).trades) for c in cands)
    assert traded >= len(cands) // 2


def test_with_15min_builds_from_5min():
    bars = session_bars(days=5)
    series = with_15min({"5min": bars})
    assert len(series["15min"]) == 5 * 26
    first = series["15min"][0]
    assert first.high == max(b.high for b in bars[:3]) and first.close == bars[2].close


def test_desk_arms_stop_order_and_enters_on_break():
    from trade_city.broker import SimBroker
    from trade_city.desk import Desk
    from trade_city.ledger import Ledger

    class Clock:
        now = datetime(2026, 3, 2, 11, 36, tzinfo=NY)

        def __call__(self):
            return self.now

    bars = flat_day()
    broker = SimBroker()
    broker.bars["SPY"] = bars[:25]  # último candle fechado: 11h30-11h35
    broker.prices["SPY"] = 100.0
    clock = Clock()
    trader = day_trader(ArmOnce(at=11 * 60 + 35, trigger=101.0, stop=99.0))
    desk = Desk([trader], broker, Ledger(":memory:"), RiskConfig(), clock=clock)
    events = desk.run_once()
    assert any("ordem stop armada" in e for e in events), events
    assert desk.ledger.open_trade_for("davi") is None

    clock.now += timedelta(minutes=1)
    assert desk.run_once() == []  # ainda não rompeu

    broker.prices["SPY"] = 101.2
    clock.now += timedelta(minutes=1)
    events = desk.run_once()
    assert any("rompeu" in e for e in events), events
    assert desk.ledger.open_trade_for("davi") is not None


def daily_bars(n=600, seed=4):
    import random

    rng = random.Random(seed)
    out, price, d = [], 100.0, datetime(2020, 1, 6, 16, tzinfo=NY)
    while len(out) < n:
        if d.weekday() < 5:
            o = price
            price *= 1 + 0.0004 + rng.gauss(0, 0.01)
            out.append(Bar(d.astimezone(timezone.utc), o, max(o, price) * 1.004, min(o, price) * 0.996, price, 1e6))
        d += timedelta(days=1)
    return out


def test_swing_setups_hold_overnight_and_use_weekly_context():
    from dataclasses import replace

    from trade_city.intraday import Timeline
    from trade_city.school import SWING_SETUPS
    from trade_city.strategies.setups import _upper

    bars = daily_bars()
    up = _upper(Timeline.build(bars))
    assert 115 <= len(up.bars) <= 125  # semanas
    assert up.done_at[0] == 0  # a semana em andamento ainda não conta
    multi_day = 0
    for cand in SWING_SETUPS:
        strat = cand.make()
        assert not strat.day_trade and "swing" in strat.name
        trader = replace(day_trader(strat), day_trade=False, timeframe="1d")
        rep = run_backtest(trader, bars, RiskConfig())
        multi_day += sum(t.closed_at.date() != t.opened_at.date() for t in rep.trades)
    assert multi_day > 0


def test_scalp_setups_run_on_crypto_minutes_with_real_costs():
    import random
    from dataclasses import replace

    from trade_city.config import TraderProfile
    from trade_city.models import AssetClass
    from trade_city.school import SCALP_RISK_VARIANTS, SCALP_SETUPS, evaluate
    from trade_city.strategies.setups import _upper
    from trade_city.intraday import Timeline

    rng = random.Random(9)
    t0, price, bars = datetime(2026, 1, 1, tzinfo=timezone.utc), 100.0, []
    for k in range(3000):
        o = price
        price *= 1 + 0.00005 * (1 if (k // 300) % 2 == 0 else -1) + rng.gauss(0, 0.001)
        bars.append(Bar(t0 + timedelta(minutes=k), o, max(o, price) * 1.0005, min(o, price) * 0.9995, price, 10))
    up = _upper(Timeline.build(bars), 60)
    assert len(up.bars) == 49 and up.done_at[59] == 0 and up.done_at[60] == 1
    trader = TraderProfile("bia", "Bia", "teste", "BTC/USD", AssetClass.CRYPTO, "1min", SCALP_SETUPS[0].make(), capital=10_000)
    for cand in SCALP_SETUPS:
        s = cand.make()
        assert "scalp" in s.name and not s.day_trade and s.window >= 2000
    results = evaluate(trader, {"1min": bars}, candidates=SCALP_SETUPS, risks=SCALP_RISK_VARIANTS)
    assert results
    # taxa da Binance cobrada: nenhuma operação sai de graça
    for r in results:
        for t in r.train.trades:
            gross = (t.exit_price - t.entry_price) * t.qty
            assert t.pnl < gross


def _range_then(event):
    """30 candles diários numa faixa de 99 a 101; depois o candle `event`."""
    t = datetime(2025, 1, 6, 16, tzinfo=NY)
    bars = []
    for k in range(70):
        lo, hi = (99.0, 100.6) if k % 2 else (99.4, 101.0)
        bars.append(Bar((t + timedelta(days=k)).astimezone(timezone.utc), 100, hi, lo, 100.2 if k % 2 else 99.8, 1000))
    bars.append(Bar((t + timedelta(days=70)).astimezone(timezone.utc), *event))
    return bars


def test_wyckoff_spring_upthrust_and_volume_filter():
    from trade_city.strategies import WyckoffSpring

    spring = _range_then((99.5, 99.9, 98.0, 99.7, 500))  # perde 99 e volta, volume baixo
    s = WyckoffSpring(swing=True)
    s.prepare(spring)
    e = s.decide(spring)
    assert e.side is Side.LONG and e.trigger == 99.9 and e.stop == 98.0
    strong = WyckoffSpring(swing=True, low_volume=True)
    loud = _range_then((99.5, 99.9, 98.0, 99.7, 5000))
    strong.prepare(loud)
    assert strong.decide(loud) is None  # volume alto: não é o spring "sem oferta"
    up = _range_then((100.5, 102.5, 100.3, 100.8, 500))
    s = WyckoffSpring(swing=True)
    s.prepare(up)
    assert s.decide(up).side is Side.SHORT


def test_wyckoff_sos_then_lps_and_climax():
    from trade_city.strategies import WyckoffClimax, WyckoffSOSLPS

    bars = _range_then((100.5, 104.0, 100.4, 103.8, 3000))  # SOS: larga, volume, fecha no topo
    t = bars[-1].ts
    bars.append(Bar(t + timedelta(days=1), 103.5, 103.6, 102.0, 102.5, 400))  # recua até a metade, volume baixo
    s = WyckoffSOSLPS(swing=True)
    s.prepare(bars)
    e = s.decide(bars)
    assert e is not None and e.side is Side.LONG and e.stop == 102.0 and e.trigger == 103.6

    sc = _range_then((99.5, 99.6, 96.0, 98.5, 5000))  # clímax de venda com absorção
    c = WyckoffClimax(swing=True)
    c.prepare(sc)
    e = c.decide(sc)
    assert e is not None and e.side is Side.LONG and e.stop == 96.0
