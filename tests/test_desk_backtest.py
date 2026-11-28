import os
from datetime import datetime, timedelta, timezone

import pytest

from trade_city.backtest import run_backtest
from trade_city.config import RiskConfig, TraderProfile
from trade_city.desk import Desk
from trade_city.ledger import Ledger
from trade_city.models import AssetClass
from trade_city.broker import SimBroker
from trade_city.strategies import TrendFollower

from conftest import make_bars


def _trader(asset=AssetClass.CRYPTO, symbol="BTC/USD"):
    return TraderProfile("bia", "Bia Satoshi", "teste", symbol, asset, "1h", TrendFollower(5, 10, 5), capital=10_000)


class Clock:
    def __init__(self):
        self.now = datetime(2026, 3, 1, 15, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def _desk(trader, broker, clock):
    return Desk([trader], broker, Ledger(":memory:"), RiskConfig(), clock=clock)


def test_desk_full_line_then_stop_loss():
    trader, broker, clock = _trader(), SimBroker(), Clock()
    broker.bars["BTC/USD"] = make_bars([100 + i for i in range(40)])
    desk = _desk(trader, broker, clock)

    events = desk.run_once()
    assert any("comprou" in e for e in events), events
    trade = desk.ledger.open_trade_for("bia")
    assert trade is not None and trade.stop_loss < trade.entry_price < trade.take_profit

    # mesmo candle: não decide de novo
    assert desk.run_once() == []

    # preço cai abaixo do stop: a mesa (cripto) fecha sozinha
    broker.prices["BTC/USD"] = trade.stop_loss - 1
    events = desk.run_once()
    assert any("derrota por stop loss" in e for e in events), events
    assert desk.ledger.open_trade_for("bia") is None
    stats = desk.stats(trader)
    assert stats.day_losses == 1 and stats.capital < 10_000


def test_desk_records_broker_side_stop_gain():
    trader, broker, clock = _trader(AssetClass.EQUITY, "QQQ"), SimBroker(), Clock()
    broker.bars["QQQ"] = make_bars([100 + i for i in range(40)])
    desk = _desk(trader, broker, clock)
    desk.run_once()
    trade = desk.ledger.open_trade_for("bia")
    broker.stop_out("QQQ", trade.take_profit)  # a corretora executou o alvo
    events = desk.run_once()
    assert any("vitória por stop gain" in e for e in events), events


def test_desk_panic_closes_and_locks():
    trader, broker, clock = _trader(), SimBroker(), Clock()
    broker.bars["BTC/USD"] = make_bars([100 + i for i in range(40)])
    desk = _desk(trader, broker, clock)
    desk.run_once()
    events = desk.panic()
    assert desk.ledger.open_trade_for("bia") is None and desk.ledger.kill_switch
    broker.bars["BTC/USD"] = make_bars([100 + i for i in range(41)])
    events = desk.run_once()
    assert any("botão de pânico" in e for e in events), events
    assert not broker.positions


def test_desk_respects_closed_market():
    trader, broker, clock = _trader(AssetClass.EQUITY, "SPY"), SimBroker(), Clock()
    broker.bars["SPY"] = make_bars([100 + i for i in range(40)])
    broker.market_open = False
    desk = _desk(trader, broker, clock)
    assert desk.run_once() == []  # fechado: nem analisa, o candle fica para a abertura
    assert not broker.positions
    broker.market_open = True
    events = desk.run_once()
    assert any("sinal" in e for e in events), events
    assert broker.positions


def test_backtest_runs_and_respects_stops(uptrend):
    report = run_backtest(_trader(), uptrend, RiskConfig(), fee_pct=0.0)
    assert report.trades, "esperava operações na tendência de alta"
    for t in report.trades:
        assert t.closed_at >= t.opened_at
    # risco por operação nunca passa de ~0,625% do capital (humor confiante)
    worst = min(t.pnl for t in report.trades)
    assert worst > -10_000 * 0.00625 * 1.5
    assert "escola" in report.summary()


def test_live_mode_blocked_without_confirmation(monkeypatch):
    pytest.importorskip("alpaca")
    from trade_city.broker.alpaca import AlpacaBroker, LiveTradingBlocked

    monkeypatch.delenv("TRADE_CITY_LIVE", raising=False)
    with pytest.raises(LiveTradingBlocked):
        AlpacaBroker("k", "s", paper=False)
