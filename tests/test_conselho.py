import json
import math
import random
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from trade_city.backtest import run_backtest
from trade_city.conselho import (
    ADVISORS,
    build_dossiers,
    convene,
    data_quality,
    deflated_sharpe,
    effective_bets,
    half_life,
    hurst,
    neighbors,
    report_json,
    report_markdown,
    trials_for,
)
from trade_city.config import RiskConfig, default_traders
from trade_city.models import AssetClass, Bar
from trade_city.strategies.conselho import BearFilter, WeakSignalVote, ZScoreReversion, bear_case, bull_case

from conftest import make_bars

DAY = timedelta(days=1)


def _walk(n, seed, drift=0.0005, vol=0.02, base=None):
    rnd = random.Random(seed)
    price, out = 100.0, []
    for i in range(n):
        shock = rnd.gauss(0, vol) if base is None else 0.8 * base[i] + 0.2 * rnd.gauss(0, vol)
        price *= math.exp(drift + shock)
        out.append(price)
    return out


def _shocks(n, seed, vol=0.02):
    rnd = random.Random(seed)
    return [rnd.gauss(0, vol) for _ in range(n)]


def test_advisors_are_five_and_only_inspired():
    assert len(ADVISORS) == 5
    assert len({a.key for a in ADVISORS}) == 5
    for a in ADVISORS:
        assert a.principles and a.sources and a.inspired_by


def test_deflated_sharpe_penalizes_many_trials():
    rnd = random.Random(1)
    rets = [rnd.gauss(0.002, 0.01) for _ in range(200)]
    _, sr0_one, p_one = deflated_sharpe(rets, 1)
    _, sr0_many, p_many = deflated_sharpe(rets, 300)
    assert sr0_one == 0 and sr0_many > 0
    assert p_many < p_one


def test_hurst_and_half_life():
    walk = _walk(2000, 3, drift=0.0)
    h = hurst(walk)
    assert 0.4 < h < 0.6
    rnd = random.Random(4)
    x, ou = 0.0, []
    for _ in range(2000):
        x += -0.1 * x + rnd.gauss(0, 0.01)
        ou.append(100 * math.exp(x))
    assert hurst(ou) < 0.4
    hl, t = half_life(ou)
    assert 4 < hl < 12 and t < -2.86
    assert half_life(walk)[1] > -4


def test_effective_bets():
    assert abs(effective_bets([[1, 0], [0, 1]]) - 2) < 1e-9
    assert abs(effective_bets([[1, 1], [1, 1]]) - 1) < 1e-9


def test_data_quality_finds_problems():
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    bars = [Bar(start + i * DAY, 100, 101, 99, 100 + 0.3 * (i % 3), 1) for i in range(100)]
    bars[50] = Bar(bars[50].ts, 100, 99, 101, 100, 1)  # máxima abaixo da mínima
    bars = bars[:70] + bars[75:]  # buraco de 5 dias
    q = data_quality(bars, AssetClass.CRYPTO)
    assert q["impossíveis"] == 1 and q["buracos"] == 1


def test_proposal_strategies_trade():
    closes = _walk(1500, 7, drift=0.0008)
    bars = make_bars(closes, step=DAY)
    sol = next(t for t in default_traders() if t.key == "sol")
    for strat in (WeakSignalVote(), ZScoreReversion(10, 2.0), BearFilter(sol.strategy, 3)):
        rep = run_backtest(replace(sol, strategy=strat), bars, RiskConfig())
        assert rep.trades, strat.name
    assert len(bear_case(bars)) == len(bars)
    assert isinstance(bull_case(bars), list)


def test_bear_filter_only_removes_entries():
    closes = _walk(1500, 9, drift=0.0008)
    bars = make_bars(closes, step=DAY)
    sol = next(t for t in default_traders() if t.key == "sol")
    plain = run_backtest(sol, bars, RiskConfig())
    vetoed = run_backtest(replace(sol, strategy=BearFilter(type(sol.strategy)(sol.strategy.n), 1)), bars, RiskConfig())
    assert len(vetoed.trades) <= len(plain.trades)


def test_neighbors_and_trials():
    for t in default_traders():
        if t.approved:
            labels = [label for label, _ in neighbors(t)]
            assert labels[0] == "atual" and len(labels) >= 3
            assert trials_for(t) > 70


def test_convene_full_report():
    n = 1400
    base = _shocks(n, 11)
    series = {
        "sol": make_bars(_walk(n, 12, drift=0.0008), step=DAY),
        "teo": make_bars(_walk(n, 13, drift=0.0006, base=base), step=DAY),
        "lena": make_bars(_walk(n, 14, drift=0.0006, base=base), step=DAY),
    }
    traders = [t for t in default_traders() if t.key in series]
    dossiers = build_dossiers(traders, lambda t: series[t.key])
    factors = {"SPY": series["lena"], "BTC/USD": series["sol"]}
    opinions = convene(dossiers, factors)
    assert [o.advisor.key for o in opinions] == ["iris", "otto", "heitor", "lia", "rafa"]
    for o in opinions:
        assert o.speech
        assert o.findings
        assert not any("erro na revisão" in f.text for f in o.findings)
    otto = opinions[1]
    assert any("mesma aposta" in f.text for f in otto.findings)  # Teo e Lena andam juntos
    assert any(p.title == "Peso de risco por correlação" for p in otto.proposals)
    text = report_markdown(opinions)
    assert "Conselho de consultores" in text and "inspirad" in text
    data = json.loads(json.dumps(report_json(opinions), ensure_ascii=False))
    assert len(data["conselheiros"]) == 5
    assert all(c["fala"] for c in data["conselheiros"])
