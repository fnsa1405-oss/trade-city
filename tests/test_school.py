import math
from datetime import datetime, timedelta, timezone

from trade_city.config import default_traders
from trade_city.data import resample
from trade_city.models import Bar
from trade_city.school import CANDIDATES, RISK_VARIANTS, evaluate, pick, report_markdown, timeframes_for

from conftest import make_bars


def test_resample_hours_to_4h_and_day():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [Bar(start + timedelta(hours=i), i, i + 1, i - 1, i + 0.5, 1) for i in range(48)]
    four = resample(bars, 4)
    assert len(four) == 12
    assert four[0].open == 0 and four[0].close == 3.5 and four[0].high == 4 and four[0].low == -1
    assert four[0].volume == 4
    assert len(resample(bars, 24)) == 2


def test_resample_drops_incomplete_block():
    start = datetime(2026, 1, 1, 2, tzinfo=timezone.utc)  # começa no meio do bloco das 0h
    bars = [Bar(start + timedelta(hours=i), 1, 1, 1, 1, 1) for i in range(10)]
    four = resample(bars, 4)
    assert [b.ts.hour for b in four] == [4, 8]  # o bloco das 0h tem só 2 velas


def test_school_runs_grid_and_reports():
    bia = default_traders()[0]
    closes = [100 * (1.0004 ** i) * (1 + 0.03 * math.sin(i / 9)) for i in range(2400)]
    series = timeframes_for(bia, make_bars(closes), "1h")
    assert set(series) == {"1h", "4h", "1d"}
    results = evaluate(bia, {"1h": series["1h"]}, candidates=CANDIDATES[:2], risks=RISK_VARIANTS[:1])
    assert len(results) == 2
    for r in results:
        assert all(t.opened_at >= series["1h"][int(len(series["1h"]) * 0.7)].ts for t in r.test.trades)
    best, _ = pick(results)
    assert best is not None
    text = report_markdown(bia, results)
    assert "Bia Satoshi" in text and "treino" in text and "prova" in text


def test_no_target_variant_only_for_strategies_with_exit():
    bia = default_traders()[0]
    bars = make_bars([100 + math.sin(i / 5) for i in range(400)])
    no_target = [rv for rv in RISK_VARIANTS if rv.reward_ratio >= 10]
    trend = [c for c in CANDIDATES if not c.make().has_exit][:1]
    turtle = [c for c in CANDIDATES if c.label.startswith("Turtle")][:1]
    assert evaluate(bia, {"1h": bars}, candidates=trend, risks=no_target) == []
    assert len(evaluate(bia, {"1h": bars}, candidates=turtle, risks=no_target)) == 1


def test_current_check_reports_the_live_strategy():
    from trade_city.config import default_traders
    from trade_city.school import current_check
    from conftest import make_bars
    import math

    rui = next(t for t in default_traders() if t.key == "rui")
    bars = make_bars([100 + 10 * math.sin(k / 15) + k * 0.05 for k in range(1500)])
    text = current_check(rui, {rui.timeframe: bars})
    assert "Estratégia atual" in text and ("continua aprovada" in text or "não passa mais" in text)
