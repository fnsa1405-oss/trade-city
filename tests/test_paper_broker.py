import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from trade_city.broker.paper import PaperBroker
from trade_city.models import AssetClass, Bar, Signal, TradePlan

T0 = datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)  # quarta-feira, 10h em NY


class FakeFeed:
    def __init__(self, price=100.0):
        self.price = price
        self.bars: list[Bar] = []

    def get_bars(self, symbol, asset_class, timeframe, days):
        return list(self.bars)

    def latest_price(self, symbol, asset_class):
        return self.price


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def plan(symbol="XRP/USD", qty=10.0, stop=95.0, take=110.0):
    sig = Signal("rui", symbol, 100.0, "teste", T0)
    return TradePlan(sig, qty, stop, take, risk_amount=50.0, mood="normal")


def make(feed=None, cash=10_000.0, now=T0):
    clock = Clock(now)
    feed = feed or FakeFeed()
    broker = PaperBroker(sqlite3.connect(":memory:"), feed=feed, initial_cash=cash, clock=clock, crypto_fee=0.001, slippage=0.0)
    return broker, feed, clock


def bar(ts, o, h, l, c):
    return Bar(ts, o, h, l, c)


def test_entry_debits_cash_with_fee():
    broker, _, _ = make()
    fill = broker.submit_entry(plan(), AssetClass.CRYPTO)
    assert fill.price == pytest.approx(100.1)
    assert broker.buying_power() == pytest.approx(10_000 - 1001)
    assert broker.get_position("XRP/USD").qty == 10


def test_insufficient_cash_and_duplicate():
    broker, _, _ = make(cash=500)
    with pytest.raises(RuntimeError):
        broker.submit_entry(plan(), AssetClass.CRYPTO)
    broker, _, _ = make()
    broker.submit_entry(plan(), AssetClass.CRYPTO)
    with pytest.raises(RuntimeError):
        broker.submit_entry(plan(), AssetClass.CRYPTO)


def test_stop_hit_in_hourly_bar_while_desk_was_off():
    broker, feed, clock = make()
    broker.submit_entry(plan(), AssetClass.CRYPTO)
    feed.bars = [
        bar(T0 - timedelta(hours=1), 100, 101, 80, 100),  # antes da entrada: ignorado
        bar(T0 + timedelta(hours=1), 100, 108, 94, 96),  # toca stop e não o alvo
    ]
    feed.price = 99  # preço já voltou
    clock.now = T0 + timedelta(hours=3)
    assert broker.get_position("XRP/USD") is None
    assert broker.last_exit_price("XRP/USD") == pytest.approx(95 * 0.999)


def test_stop_wins_when_bar_hits_both():
    broker, feed, clock = make()
    broker.submit_entry(plan(), AssetClass.CRYPTO)
    feed.bars = [bar(T0 + timedelta(hours=1), 100, 112, 90, 100)]
    clock.now = T0 + timedelta(hours=2)
    assert broker.get_position("XRP/USD") is None
    assert broker.last_exit_price("XRP/USD") == pytest.approx(95 * 0.999)


def test_target_hit_and_gap_fills_at_open():
    broker, feed, clock = make()
    broker.submit_entry(plan(), AssetClass.CRYPTO)
    feed.bars = [bar(T0 + timedelta(hours=1), 115, 118, 112, 116)]
    clock.now = T0 + timedelta(hours=2)
    assert broker.get_position("XRP/USD") is None
    assert broker.last_exit_price("XRP/USD") == pytest.approx(115 * 0.999)


def test_position_kept_and_close_by_desk():
    broker, feed, clock = make()
    broker.submit_entry(plan(), AssetClass.CRYPTO)
    feed.bars = [bar(T0 + timedelta(hours=1), 100, 105, 97, 104)]
    feed.price = 104
    clock.now = T0 + timedelta(hours=2)
    assert broker.get_position("XRP/USD") is not None
    fill = broker.close_position("XRP/USD")
    assert fill.price == pytest.approx(104 * 0.999)
    assert broker.get_position("XRP/USD") is None
    assert broker.buying_power() == pytest.approx(10_000 - 1001 + 1038.96)


def test_market_hours():
    broker, _, clock = make()
    assert broker.is_market_open(AssetClass.CRYPTO)
    assert broker.is_market_open(AssetClass.EQUITY)
    clock.now = T0 + timedelta(hours=7)  # 17h em NY
    assert not broker.is_market_open(AssetClass.EQUITY)
    clock.now = datetime(2026, 11, 28, 15, 0, tzinfo=timezone.utc)  # sábado
    assert not broker.is_market_open(AssetClass.EQUITY)
    assert broker.is_market_open(AssetClass.CRYPTO)


def test_equity_has_no_crypto_fee():
    broker, _, _ = make()
    fill = broker.submit_entry(plan("QQQ", qty=5), AssetClass.EQUITY)
    assert fill.price == pytest.approx(100.0)


def test_desk_runs_on_paper_broker():
    from conftest import make_bars

    from trade_city.config import RiskConfig, TraderProfile
    from trade_city.desk import Desk
    from trade_city.ledger import Ledger
    from trade_city.strategies import TrendFollower

    ledger = Ledger(":memory:")
    feed = FakeFeed(price=139.0)
    feed.bars = make_bars([100 + i for i in range(40)])
    clock = Clock(T0)
    broker = PaperBroker(ledger.conn, feed=feed, initial_cash=10_000, clock=clock)
    trader = TraderProfile("rui", "Rui", "teste", "XRP/USD", AssetClass.CRYPTO, "1h", TrendFollower(5, 10, 5), capital=10_000)
    desk = Desk([trader], broker, ledger, RiskConfig(), clock=clock)
    events = desk.run_once()
    assert any("comprou" in e for e in events), events
    assert broker.get_position("XRP/USD") is not None
    assert broker.buying_power() < 10_000

    # preço despenca abaixo do stop: a corretora simulada executa e a mesa registra
    trade = ledger.open_trade_for("rui")
    feed.price = trade.stop_loss * 0.98
    clock.now = T0 + timedelta(minutes=30)
    events = desk.run_once()
    assert ledger.open_trade_for("rui") is None, events
