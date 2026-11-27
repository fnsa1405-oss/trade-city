from dataclasses import replace
from datetime import datetime, timezone

from trade_city.auditor import AuditContext, Auditor
from trade_city.config import RiskConfig
from trade_city.models import AssetClass, Signal
from trade_city.mood import Mood
from trade_city.risk import Guardian

from conftest import make_bars

CFG = RiskConfig()
NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


def _plan(mood=Mood.NORMAL, asset=AssetClass.CRYPTO, capital=10_000):
    bars = make_bars([100] * 20, spread=0.01)  # ATR = 2
    signal = Signal("bia", "BTC/USD", 100.0, "teste", NOW)
    plan, _ = Guardian(CFG).plan(signal, bars, capital, mood, asset)
    return plan


def _ctx(**kw):
    base = dict(capital=10_000, peak_capital=10_000, day_losses=0, day_pnl=0.0, has_open_position=False, buying_power=50_000)
    base.update(kw)
    return AuditContext(**base)


def test_guardian_sets_stops_and_size():
    plan = _plan()
    assert plan.stop_loss == 96.0  # 2 ATR abaixo
    assert plan.take_profit == 108.0  # 2x o risco
    assert abs(plan.risk_amount - 50.0) < 1e-6  # 0,5% de 10.000
    assert abs(plan.qty - 12.5) < 1e-6


def test_mood_scales_size_only():
    normal, danger = _plan(Mood.NORMAL), _plan(Mood.PERIGO)
    assert abs(danger.qty - normal.qty * 0.25) < 1e-6
    assert danger.stop_loss == normal.stop_loss


def test_equity_whole_shares():
    plan = _plan(asset=AssetClass.EQUITY)
    assert plan.qty == 12.0


def test_no_leverage():
    plan = _plan(capital=1_000)
    assert plan.notional <= 1_000


def test_auditor_approves_clean_plan():
    assert Auditor(CFG).review(_plan(), _ctx()).approved


def test_auditor_blocks_bad_stops():
    bad = replace(_plan(), stop_loss=101.0)
    result = Auditor(CFG).review(bad, _ctx())
    assert not result.approved and any("incoerentes" in r for r in result.reasons)


def test_auditor_blocks_small_target():
    bad = replace(_plan(), take_profit=104.0)  # 1x o risco
    assert not Auditor(CFG).review(bad, _ctx()).approved


def test_auditor_daily_locks():
    auditor = Auditor(CFG)
    assert not auditor.review(_plan(), _ctx(day_losses=5)).approved
    assert not auditor.review(_plan(), _ctx(day_pnl=-300)).approved


def test_auditor_drawdown_sends_to_school():
    result = Auditor(CFG).review(_plan(), _ctx(capital=8_900, peak_capital=10_000))
    assert not result.approved and any("escola" in r for r in result.reasons)


def test_auditor_kill_switch_and_market():
    auditor = Auditor(CFG)
    assert not auditor.review(_plan(), _ctx(kill_switch=True)).approved
    assert not auditor.review(_plan(), _ctx(market_open=False)).approved
    assert not auditor.review(_plan(), _ctx(has_open_position=True)).approved
    assert not auditor.review(_plan(), _ctx(buying_power=10)).approved
