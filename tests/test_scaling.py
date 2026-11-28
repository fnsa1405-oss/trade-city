"""Preço médio inteligente: para trás (limitado) e pirâmide, no backtest, na corretora e na mesa."""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from trade_city.backtest import run_backtest
from trade_city.broker.paper import PaperBroker
from trade_city.config import RiskConfig, TraderProfile
from trade_city.desk import Desk
from trade_city.ledger import Ledger
from trade_city.models import AssetClass, Bar, Entry, Side, Signal, TradePlan
from trade_city.scaling import MEDIA, PIRAMIDE, SEM_ESCALA, Scaling
from trade_city.strategies.base import Strategy

T0 = datetime(2026, 3, 2, 15, tzinfo=timezone.utc)


class OneShot(Strategy):
    """Compra uma vez, no candle `at`, com stop fixo no preço `stop`."""

    name = "teste"
    min_bars = 16

    def __init__(self, at: int, stop: float, side: Side = Side.LONG):
        self.at, self.stop, self.side, self.done = at, stop, side, False

    def analyze(self, bars):
        return None

    def decide(self, bars):
        if len(bars) == self.at + 1 and not self.done:
            self.done = True
            return Entry("teste", self.side, self.stop)
        return None


def bars_from(path, start=T0):
    """Candles de 1 h; cada um vai de `o` a `c` com máxima/mínima exatas."""
    out, prev = [], path[0][0] if isinstance(path[0], tuple) else path[0]
    for i, p in enumerate(path):
        o, h, l, c = p if isinstance(p, tuple) else (prev, max(prev, p), min(prev, p), p)
        out.append(Bar(start + timedelta(hours=i), o, h, l, c, 1000))
        prev = c
    return out


def flat(n=16, price=100.0):
    return [(price, price + 0.5, price - 0.5, price)] * n


def trader(strategy, asset=AssetClass.CRYPTO, symbol="BTC/USD"):
    return TraderProfile("bia", "Bia", "teste", symbol, asset, "1h", strategy, capital=10_000)


RISK = RiskConfig(reward_ratio=2.0)


def run(path, scaling, side=Side.LONG, stop=90.0, asset=AssetClass.CRYPTO):
    t = trader(OneShot(15, stop, side), asset, "BTC/USD" if asset is AssetClass.CRYPTO else "SPY")
    return run_backtest(t, bars_from(path), RISK, fee_pct=0.0, slippage_pct=0.0, scaling=scaling)


def test_sizing_keeps_total_risk_fixed():
    sc = Scaling(MEDIA, 2, 0.33)
    unit, adds = sc.size(9.0, False, 10.0, 100.0, 10_000, None)
    assert adds == 2
    assert unit * 10.0 * sc.risk_factor(2) == pytest.approx(9.0 * 10.0)
    # contratos inteiros: 1 contrato por perna só se o risco total couber na trava
    unit, adds = sc.size(1.0, True, 10.0, 25.0, 10_000, 1_000)
    assert (unit, adds) == (1.0, 2)  # 2,01 x 10 = 20,1 <= 25
    unit, adds = sc.size(1.0, True, 10.0, 15.0, 10_000, 1_000)
    assert (unit, adds) == (1.0, 0)  # não cabe: opera sem preço médio
    # margem: 3 pernas de 1 contrato precisam de 3 x 1.000
    assert sc.size(1.0, True, 10.0, 25.0, 2_500, 1_000) == (1.0, 1)
    with pytest.raises(ValueError):
        Scaling(MEDIA, 3, 0.33)  # a última entrada ficaria em cima do stop


def test_average_down_with_all_legs_loses_the_same_fixed_risk():
    # entra a 100 com stop em 90; cai até 89: as duas entradas extras (96,7 e 93,4) entram e o stop sai
    path = flat() + [100, 98, 96, 94, 92, 89]
    plain = run(path, SEM_ESCALA)
    avg = run(path, Scaling(MEDIA, 2, 0.33))
    assert len(plain.trades) == len(avg.trades) == 1
    assert avg.trades[0].adds == 2
    assert avg.trades[0].exit_reason == "stop loss"
    assert plain.trades[0].pnl == pytest.approx(-50, rel=0.02)  # 0,5% de 10.000
    assert avg.trades[0].pnl == pytest.approx(plain.trades[0].pnl, rel=0.02)


def test_average_down_exits_on_the_average_target_when_price_turns():
    path = flat() + [100, 97, 95, 99, 103, 110]
    plain = run(path, SEM_ESCALA)
    avg = run(path, Scaling(MEDIA, 2, 0.33, "medio", 1.0))
    t = avg.trades[0]
    assert t.adds == 1 and t.exit_reason == "stop gain"
    # alvo = preço médio + 1R; sem o preço médio, o alvo (120) não é atingido
    assert t.exit_price == pytest.approx(t.entry_price + 10, abs=0.01)
    assert plain.trades == []  # sem preço médio, segue aberta esperando o alvo de 120


def test_pyramid_adds_in_favor_and_moves_the_stop_up():
    # entra a 100 (R = 10); sobe a 110 (1ª extra), cai: o stop da posição subiu de 90 para 100,
    # onde a perda das duas pernas juntas é o mesmo risco inicial de uma perna só
    path = flat() + [100, 105, 111, 106, 101, 99]
    pyr = run(path, Scaling(PIRAMIDE, 2, 1.0))
    t = pyr.trades[0]
    assert t.adds == 1 and t.exit_reason == "stop loss"
    assert t.exit_price == pytest.approx(100.0)
    assert t.pnl == pytest.approx(-50, rel=0.02)


def test_pyramid_wins_more_when_the_trend_runs():
    path = flat() + [100, 105, 111, 116, 121, 125]
    plain = run(path, SEM_ESCALA)
    pyr = run(path, Scaling(PIRAMIDE, 2, 0.5))
    assert plain.trades[0].exit_reason == pyr.trades[0].exit_reason == "stop gain"
    assert pyr.trades[0].adds == 2
    assert pyr.trades[0].pnl > plain.trades[0].pnl * 1.5


def test_short_side_mirrors():
    path = flat() + [100, 102, 104, 106, 108, 111]
    avg = run(path, Scaling(MEDIA, 2, 0.33), side=Side.SHORT, stop=110.0, asset=AssetClass.EQUITY)
    t = avg.trades[0]
    assert t.side is Side.SHORT and t.adds == 2 and t.exit_reason == "stop loss"
    assert t.qty == 6  # 5 ações numa operação comum viram 3 pernas de 2 (ações inteiras)
    assert -50.5 < t.pnl < -35


def test_daily_pnl_and_green_days():
    rep = run(flat() + [100, 105, 111, 116, 121, 125], SEM_ESCALA)
    assert list(rep.daily_pnl.values()) == [pytest.approx(rep.total_pnl)]
    assert rep.green_days == 1.0


# corretora simulada com micro futuro ----------------------------------------


class Feed:
    def __init__(self, price):
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


def test_paper_broker_adds_to_micro_position_with_margin_and_costs():
    from trade_city.futures import MICROS

    feed = Feed(440.0)  # DIA a 440 = MYM a 22.000 (US$0,50 por ponto)
    b = PaperBroker(sqlite3.connect(":memory:"), feed=feed, initial_cash=10_000, clock=Clock(T0), contracts={"DIA": MICROS["DIA"]})
    sig = Signal("mia", "DIA", 22_000.0, "teste", T0)
    fill = b.submit_entry(TradePlan(sig, 1.0, 21_900.0, 22_200.0, 50.0, "normal"), AssetClass.EQUITY)
    cost = 0.5 + 0.85  # 1 tick + corretagem, por contrato e por lado
    assert fill.price == pytest.approx(22_000 + cost)
    assert b.buying_power() == pytest.approx(9_000)
    feed.price = 441.0
    add = b.add_to_position("DIA", 1.0)
    assert add.price == pytest.approx(22_050 + cost)
    assert b.buying_power() == pytest.approx(8_000)
    pos = b.get_position("DIA")
    assert pos.qty == 2 and pos.avg_entry_price == pytest.approx(22_025 + cost)
    b.set_stops("DIA", 22_010.0, 22_300.0)
    feed.price = 440.0  # 22.000: abaixo do novo stop, a corretora zera as duas pernas
    assert b.get_position("DIA") is None
    assert b.last_exit_price("DIA") == pytest.approx(22_000 - cost)


def test_desk_averages_down_on_micro_and_keeps_one_stop():
    from conftest import make_bars

    from trade_city.strategies import TrendFollower

    ledger = Ledger(":memory:")
    feed = Feed(139.0)
    feed.bars = make_bars([100 + i for i in range(40)])
    clock = Clock(datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc))
    broker = PaperBroker(ledger.conn, feed=feed, initial_cash=50_000, clock=clock)
    t = TraderProfile(
        "rui", "Rui", "teste", "XRP/USD", AssetClass.CRYPTO, "1h", TrendFollower(5, 10, 5), capital=50_000,
        scaling=Scaling(MEDIA, 2, 0.33, "medio", 1.0),
    )
    desk = Desk([t], broker, ledger, RiskConfig(), clock=clock)
    events = desk.run_once()
    assert any("preço médio armado" in e for e in events), events
    trade = ledger.open_trade_for("rui")
    first_qty, stop = trade.qty, trade.stop_loss
    dist = trade.entry_price - stop
    # o preço vai 40% do caminho até o stop: entra a 1ª extra, o stop não muda e o alvo desce
    feed.price = trade.entry_price - 0.4 * dist
    clock.now += timedelta(minutes=1)
    events = desk.run_once()
    assert any("preço médio: +" in e for e in events), events
    trade2 = ledger.open_trade_for("rui")
    assert trade2.qty == pytest.approx(2 * first_qty)
    assert trade2.stop_loss == pytest.approx(stop)
    assert trade2.entry_price < trade.entry_price and trade2.take_profit < trade.take_profit
    # cai até o stop: zera tudo e a perda fica perto do risco fixo (0,5% de 50.000), com custos
    feed.price = stop * 0.999
    clock.now += timedelta(minutes=1)
    desk.run_once()
    assert ledger.open_trade_for("rui") is None
    assert -300 < sum(ledger.closed_pnls("rui")) < -150
