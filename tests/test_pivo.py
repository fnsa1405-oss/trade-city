from dataclasses import replace
from datetime import datetime, timedelta, timezone

from trade_city.backtest import run_backtest
from trade_city.config import RiskConfig, default_traders, risk_for
from trade_city.intraday import NY
from trade_city.models import AssetClass, Bar, Side, Signal
from trade_city.mood import Mood
from trade_city.risk import Guardian
from trade_city.school import PIVO_DAY, SCHOOL_SETS, evaluate
from trade_city.strategies import PivotV2
from trade_city.strategies.pivo import TICK_FRAC

from test_daytrade import day_trader, session_bars

# swing de topo em 103 (candle 2), rompimento por fechamento (6), novo topo 104 (7),
# reteste no nível 103 (8), gatilho fechando acima de 104 (10)
PATTERN = [
    (101.0, 100.0, 100.5),
    (102.0, 100.5, 101.5),
    (103.0, 101.5, 102.0),
    (102.5, 101.0, 101.2),
    (102.0, 100.6, 100.8),
    (101.5, 100.2, 101.0),
    (103.2, 101.0, 103.1),
    (104.0, 103.0, 103.8),
    (103.9, 102.9, 103.1),
    (103.6, 102.95, 103.5),
    (104.5, 103.4, 104.3),
]
PREFIX = 25
TRIGGER = PREFIX + 10


def pattern_bars(pattern=PATTERN, after=True, flip=False):
    """Pregão de 1 min: 25 candles subindo devagar (M20 a favor), o padrão e depois o alvo."""
    t0 = datetime(2026, 1, 13, 9, 30, tzinfo=NY)
    rows = [(90 + 0.38 * k + 0.2, 90 + 0.38 * k - 0.2, 90 + 0.38 * k + 0.1) for k in range(PREFIX)]
    rows += pattern
    if after:
        rows += [(104.6 + 0.3 * k, 104.2 + 0.3 * k, 104.5 + 0.3 * k) for k in range(12)]
    bars, prev = [], rows[0][2]
    for k, (h, lo, c) in enumerate(rows):
        o = min(max(prev, lo), h)
        if flip:
            h, lo, c, o = 300 - lo, 300 - h, 300 - c, 300 - o
        bars.append(Bar((t0 + timedelta(minutes=k)).astimezone(timezone.utc), o, h, lo, c, 1000))
        prev = rows[k][2]
    return bars


def levy_like(strategy, **kw):
    t = replace(day_trader(strategy, "QQQ"), timeframe="1min", min_reward_ratio=0.5)
    return replace(t, **kw)


def test_full_sequence_gives_entry_stop_a_and_fibonacci_target():
    bars = pattern_bars()
    s = PivotV2(target=1, layer=3, chart=1)
    for n in range(PREFIX, TRIGGER + 1):
        assert s.decide(bars[:n]) is None  # sem a sequência completa, não há trade
    e = s.decide(bars[: TRIGGER + 1])
    assert e is not None and e.side is Side.LONG and e.trigger is None
    assert abs(e.stop - (102.9 - TICK_FRAC * 104.3)) < 1e-9  # 1 tick além da mínima do reteste
    leg = 104.0 - 100.2  # A = início da perna, B = novo topo
    assert abs(e.target - (104.0 + 0.618 * leg)) < 1e-9  # continuação: alvo 1 = 61%
    assert "continuação" in e.reason
    e3 = PivotV2(target=3, layer=3, chart=1).decide(bars[: TRIGGER + 1])
    assert abs(e3.target - (104.0 + 1.618 * leg)) < 1e-9


def test_no_retest_no_trade():
    no_retest = list(PATTERN)
    no_retest[7] = (104.0, 103.3, 103.8)
    no_retest[8] = (103.9, 103.5, 103.6)
    no_retest[9] = (103.8, 103.4, 103.7)
    bars = pattern_bars(no_retest)
    assert PivotV2(chart=1).decide(bars[: TRIGGER + 1]) is None


def test_sell_side_is_the_mirror():
    bars = pattern_bars(flip=True)
    e = PivotV2(chart=1).decide(bars[: TRIGGER + 1])
    assert e is not None and e.side is Side.SHORT
    assert abs(e.stop - (300 - 102.9 + TICK_FRAC * (300 - 104.3))) < 1e-9
    assert abs(e.target - (300 - 104.0 - 0.618 * 3.8)) < 1e-9


def test_layer_2_needs_the_m20():
    bars = pattern_bars()
    s = PivotV2(layer=2, chart=1)
    e = s.decide(bars[: TRIGGER + 1])
    assert e is not None  # o gatilho fechou acima da M20
    side, stop, targets, aligned, mode = s.signals[TRIGGER]
    assert aligned and mode == "continuação"


def test_backtest_exits_at_the_target_and_short_target_needs_lower_floor():
    bars = pattern_bars()
    rep = run_backtest(levy_like(PivotV2(chart=1)), bars, RiskConfig())
    assert len(rep.trades) == 1 and rep.trades[0].exit_reason == "stop gain" and rep.trades[0].pnl > 0
    # com o piso padrão do Auditor (alvo de 1,5x o risco), o alvo de ~1,46R seria recusado
    strict = run_backtest(levy_like(PivotV2(chart=1), min_reward_ratio=None), bars, RiskConfig())
    assert strict.trades == [] and strict.rejected == 1


def test_guardian_uses_chart_target_and_refuses_a_passed_one():
    g = Guardian(RiskConfig(min_reward_ratio=0.5))
    bars = pattern_bars()
    ts = bars[-1].ts
    plan, _ = g.plan(Signal("levy", "QQQ", 104.3, "x", ts, Side.LONG, 102.9, 105.5), bars, 25_000, Mood.NORMAL, AssetClass.EQUITY)
    assert plan is not None and plan.take_profit == 105.5
    plan, why = g.plan(Signal("levy", "QQQ", 106.0, "x", ts, Side.LONG, 102.9, 105.5), bars, 25_000, Mood.NORMAL, AssetClass.EQUITY)
    assert plan is None and "alvo" in why


def test_does_not_look_ahead_and_only_trades_the_session():
    bars = session_bars(days=6, step=1, seed=5)
    full = PivotV2()
    full.prepare(bars)
    for n in range(400, len(bars), 11):
        part = PivotV2()
        a, b = full.decide(bars[:n]), part.decide(bars[:n])
        assert (a is None) == (b is None) and (a is None or (a.side, a.stop, a.target) == (b.side, b.stop, b.target))
    rep = run_backtest(levy_like(PivotV2()), bars, RiskConfig())
    for tr in rep.trades:
        assert tr.opened_at.astimezone(NY).date() == tr.closed_at.astimezone(NY).date()


def test_levy_is_in_the_cast_with_his_own_school():
    levy = next(t for t in default_traders() if t.key == "levy")
    assert levy.micro and levy.day_trade and levy.symbol == "QQQ" and levy.capital == 25_000
    assert (levy.strategy.target, levy.strategy.layer, levy.strategy.chart) == (1, 3, 2)
    assert risk_for(levy, RiskConfig()).min_reward_ratio == 0.5
    assert risk_for(levy, RiskConfig()).risk_per_trade == RiskConfig().risk_per_trade  # travas da casa
    assert len(PIVO_DAY) == 12 and SCHOOL_SETS["pivo"][0] is PIVO_DAY
    bars = session_bars(days=12, step=1, seed=2)
    res = evaluate(levy, {"1min": bars})
    assert {r.candidate for r in res} == {c.label for c in PIVO_DAY}
