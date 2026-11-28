from datetime import datetime, timedelta, timezone

import pytest

from trade_city.backtest import run_backtest
from trade_city.config import RiskConfig
from trade_city.futures import MICROS, to_contract
from trade_city.intraday import NY
from trade_city.models import Bar

from test_setups import ArmOnce, flat_day
from test_daytrade import day_trader


def test_micro_specs_and_conversion():
    mnq = MICROS["QQQ"]
    assert mnq.code == "MNQ" and mnq.tick_value == 0.5 and mnq.slip_value == 0.5
    assert MICROS["SPY"].tick_value == 1.25 and MICROS["DIA"].tick_value == 0.5 and MICROS["IWM"].tick_value == 0.5
    b = Bar(datetime(2026, 3, 2, tzinfo=timezone.utc), 500, 501, 499, 500.5, 10)
    c = to_contract([b], mnq)[0]
    assert c.open == pytest.approx(500 * 41 * 2) and c.volume == 10


def test_backtest_trades_whole_contracts_with_tick_and_fee_costs():
    bars = flat_day(price=500.0)
    k = 25
    bars[k] = Bar(bars[k].ts, 500, 505, 499.9, 504, 1000)
    for j in range(k + 1, len(bars)):
        bars[j] = Bar(bars[j].ts, 504, 504.2, 503.8, 504, 1000)
    mnq = MICROS["QQQ"]
    # o setup calcula gatilho e stop nos candles já convertidos (dólares por contrato)
    trader = day_trader(ArmOnce(at=11 * 60 + 35, trigger=501.0 * 82, stop=500.5 * 82), symbol="QQQ")
    rep = run_backtest(trader, bars, RiskConfig(), contract=mnq)
    assert len(rep.trades) == 1
    t = rep.trades[0]
    assert t.qty == int(t.qty) and t.qty >= 1
    # entrada no gatilho + 1 tick; corretagem de ida e volta por contrato
    assert t.entry_price == pytest.approx(501.0 * mnq.scale + mnq.slip_value)
    gross = (t.exit_price - t.entry_price) * t.qty
    assert t.pnl == pytest.approx(gross - 2 * mnq.fee * t.qty)


def test_one_contract_only_when_it_fits_the_max_risk():
    bars = flat_day(price=500.0)
    bars[25] = Bar(bars[25].ts, 500, 505, 499.9, 504, 1000)
    # stop de 20 pontos do ETF = 20 * 82 = US$1.640 por contrato: acima de 1% de 10 mil
    trader = day_trader(ArmOnce(at=11 * 60 + 35, trigger=501.0 * 82, stop=481.0 * 82), symbol="QQQ")
    rep = run_backtest(trader, bars, RiskConfig(), contract=MICROS["QQQ"])
    assert rep.trades == [] and rep.rejected == 1
