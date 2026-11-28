import random
from datetime import datetime, timedelta, timezone

from trade_city.brain import Brain, BrainRules, FEATURE_NAMES, features, fit, train_brain
from trade_city.models import ClosedTrade, Side

from conftest import make_bars

T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)


def trades(n, informative, seed=1):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        x = [rng.gauss(0, 1) for _ in FEATURE_NAMES]
        good = x[2] > 0 if informative else rng.random() < 0.45
        pnl = 100.0 if good else -80.0
        ts = T0 + timedelta(hours=i)
        out.append(ClosedTrade("teo", "QQQ", 1, 100, 100, pnl, ts, ts, "teste", Side.LONG, tuple(x)))
    return out


def test_brain_learns_a_real_pattern_and_is_promoted():
    brain = train_brain("teo", trades(400, informative=True))
    assert brain is not None and brain.promoted
    com, sem = brain.report["prova com cérebro"], brain.report["prova sem cérebro"]
    assert com["fator de lucro"] > sem["fator de lucro"]


def test_brain_is_not_promoted_on_noise():
    brain = train_brain("teo", trades(400, informative=False, seed=3))
    assert brain is not None and not brain.promoted


def test_needs_enough_trades():
    assert train_brain("teo", trades(50, informative=True), BrainRules()) is None


def test_json_round_trip_and_features():
    brain = fit("teo", [[0.0] * len(FEATURE_NAMES), [1.0] * len(FEATURE_NAMES)], [0, 1], epochs=5)
    again = Brain.from_json(brain.to_json())
    x = [0.5] * len(FEATURE_NAMES)
    assert abs(again.prob(x) - brain.prob(x)) < 1e-12
    bars = make_bars([100 + i * 0.1 for i in range(80)])
    f = features(bars, Side.LONG)
    assert f is not None and len(f) == len(FEATURE_NAMES)
    assert features(bars, Side.SHORT)[1] == -f[1]  # sempre do ponto de vista do lado
    assert features(bars[:30], Side.LONG) is None


def test_desk_respects_brain_veto():
    from trade_city.broker import SimBroker
    from trade_city.config import RiskConfig, TraderProfile
    from trade_city.desk import Desk
    from trade_city.ledger import Ledger
    from trade_city.models import AssetClass
    from trade_city.strategies import TrendFollower

    class Clock:
        now = datetime(2026, 3, 1, 15, tzinfo=timezone.utc)

        def __call__(self):
            return self.now

    trader = TraderProfile("bia", "Bia", "teste", "BTC/USD", AssetClass.CRYPTO, "1h", TrendFollower(5, 10, 5), capital=10_000)
    broker = SimBroker()
    broker.bars["BTC/USD"] = make_bars([100 + i for i in range(90)])
    veto = fit("bia", [[0.0] * len(FEATURE_NAMES)] * 2, [0, 0], epochs=50)
    veto.promoted, veto.threshold = True, 0.99
    desk = Desk([trader], broker, Ledger(":memory:"), RiskConfig(), clock=Clock(), brains={"bia": veto})
    events = desk.run_once()
    assert any("cérebro deixou passar" in e for e in events), events
    assert desk.ledger.open_trade_for("bia") is None


def test_promoted_brain_puts_trader_on_desk(tmp_path, monkeypatch):
    from trade_city import __main__ as cli
    from trade_city.brain import setup_of
    from trade_city.config import default_traders

    teo = next(t for t in default_traders() if t.key == "ivo")
    brain = fit("ivo", [[0.0] * len(FEATURE_NAMES), [1.0] * len(FEATURE_NAMES)], [0, 1], epochs=5)
    brain.promoted, brain.setup = True, setup_of(teo)
    folder = tmp_path / "cerebros"
    folder.mkdir()
    (folder / "ivo.json").write_text(brain.to_json())
    monkeypatch.chdir(tmp_path)
    assert "ivo" in {t.key for t in cli._desk(":memory:", grupo="day").traders}
    brain.setup = "outra configuração"
    (folder / "ivo.json").write_text(brain.to_json())
    assert "ivo" not in {t.key for t in cli._desk(":memory:", grupo="day").traders}


def test_paper_account_funds_new_traders():
    import sqlite3

    from trade_city.broker.paper import PaperBroker

    conn = sqlite3.connect(":memory:")
    PaperBroker(conn, initial_cash=10_000)
    assert PaperBroker(conn, initial_cash=30_000).buying_power() == 30_000
    assert PaperBroker(conn, initial_cash=30_000).buying_power() == 30_000
