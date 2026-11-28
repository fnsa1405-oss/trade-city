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
    traded = sum(bool(run_backtest(day_trader(c.make()), bars, RiskConfig()).trades) for c in DAY_CANDIDATES)
    assert traded >= len(DAY_CANDIDATES) // 2


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
