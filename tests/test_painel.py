import json
from datetime import datetime, timezone

from trade_city.broker.paper import PaperBroker
from trade_city.config import default_traders
from trade_city.desk import Desk
from trade_city.ledger import Ledger
from trade_city.painel import build_state

T0 = datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc)


class FakeFeed:
    def get_bars(self, symbol, asset_class, timeframe, days):
        return []

    def latest_price(self, symbol, asset_class):
        return 2.0


def make_desk():
    ledger = Ledger(":memory:")
    rui = [t for t in default_traders() if t.key == "rui"]
    broker = PaperBroker(ledger.conn, feed=FakeFeed(), initial_cash=10_000, clock=lambda: T0)
    return Desk(rui, broker, ledger, clock=lambda: T0)


def test_estado_vazio_e_json_valido():
    state = build_state(make_desk(), "swing", now=T0)
    json.dumps(state)
    assert state["mesa"] == "swing"
    assert state["modo"] == "simulado"
    assert [t["key"] for t in state["traders"]] == ["rui"]
    assert state["traders"][0]["posicao"] is None
    assert {e["situacao"] for e in state["elenco"]} == {"na mesa", "na escola"}


def test_estado_mostra_operacoes_eventos_e_trava():
    desk = make_desk()
    led = desk.ledger
    tid = led.open_trade("rui", "XRP/USD", 100, 2.0, 1.9, 2.2, T0)
    led.close_trade(tid, 2.2, T0, "stop gain")
    led.open_trade("rui", "XRP/USD", 50, 2.1, 2.0, 2.3, T0)
    led.record_decision(T0, "rui", "XRP/USD", "auditor", True, "aprovado")
    led.record_decision(T0, "bia", "BTC/USD", "analista", True, "não está na mesa")
    led.kill_switch = True

    state = build_state(desk, "swing", now=T0)
    rui = state["traders"][0]
    assert rui["posicao"]["entrada"] == 2.1 and rui["posicao"]["alvo"] == 2.3
    assert rui["lucro"] == 20.0
    assert rui["ultimos"] == ["v"]
    assert len(state["operacoes"]) == 2 and state["operacoes"][1]["resultado"] == 20.0
    assert [e["trader"] for e in state["eventos"]] == ["rui"]  # só quem está na mesa
    assert state["resumo"] == {"operacoes": 1, "vitorias": 1, "resultado": 20.0}
    assert state["travada"] is True
