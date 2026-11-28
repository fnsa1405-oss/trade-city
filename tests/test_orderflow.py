import math
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from tests.conftest import make_bars
from trade_city.auditor import AuditContext, Auditor
from trade_city.backtest import run_backtest
from trade_city.book_collector import book_features, run_collector
from trade_city.config import RiskConfig, default_traders, risk_for
from trade_city.models import AssetClass, Side, Signal, TradePlan
from trade_city.orderflow import (
    FlowBar,
    attach,
    binance_symbol,
    buy_volumes,
    estimated_buy_volume,
    flow_series,
    load_flow,
    parse_book_depth,
    parse_klines,
    parse_metrics,
    resample_flow,
    save_flow,
)
from trade_city.school_flow import FLOW_CANDIDATES, FLOW_DAY_CANDIDATES, evaluate_flow, ranking_markdown
from trade_city.strategies import DonchianEnsemble
from trade_city.strategies.orderflow import (
    Absorption,
    BookImbalance,
    CVDDivergence,
    CVDTrend,
    DeltaBreakout,
    FlowFilter,
    LiquidationFlush,
    OpenInterestTrend,
)

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)


def flow_bars(n=600, step=timedelta(hours=1), buy_share=None, book=None, oi=None):
    closes = [100 * (1.001 ** i) * (1 + 0.03 * math.sin(i / 9)) for i in range(n)]
    base = make_bars(closes, start=T0, step=step)
    out = []
    for i, b in enumerate(base):
        up = b.close >= b.open
        share = buy_share(i) if buy_share else (0.62 if up else 0.4)
        vol = 1000 * (1 + (i % 7 == 0))
        out.append(FlowBar(b.ts, b.open, b.high, b.low, b.close, vol, vol * share, 50,
                           oi(i) if oi else None, 1.1 if up else 0.9, book(i) if book else None, None))
    return out


def test_parse_klines_ms_and_us():
    ms = "1527811200000,0.61,0.62,0.60,0.61,1000,1527814799999,600,919,700,430,0"
    us = "1735689600000000,2.08,2.11,2.08,2.11,8000,1735693199999999,17000,33860,5000,10800,0"
    a, b = parse_klines(ms + "\n" + us)
    assert a.ts == datetime(2018, 6, 1, tzinfo=timezone.utc)
    assert b.ts == datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert a.buy_volume == 700 and a.trades == 919
    assert a.delta == 2 * 700 - 1000


def test_parse_metrics_and_book():
    m = parse_metrics(
        "create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio\n"
        "2025-06-01 00:05:00,XRPUSDT,1,500.5,2,1,2,0.85\n"
    )
    assert m[datetime(2025, 6, 1, 0, 5, tzinfo=timezone.utc)] == (500.5, 0.85)
    text = "timestamp,percentage,depth,notional\n" + "".join(
        f"2025-06-01 00:00:09,{p},1,{v}\n" for p, v in [(-5, 300), (-1, 60), (1, 40), (5, 100)]
    )
    bk = parse_book_depth(text)
    imb1, imb5 = bk[datetime(2025, 6, 1, 0, 0, 9, tzinfo=timezone.utc)]
    assert abs(imb1 - 0.2) < 1e-9 and abs(imb5 - 0.5) < 1e-9


def test_attach_uses_only_what_existed_at_close():
    bars = flow_bars(4, step=timedelta(minutes=15))
    metrics = {T0 + timedelta(minutes=10): (100.0, 1.2), T0 + timedelta(minutes=20): (200.0, 0.8)}
    book = {T0 + timedelta(minutes=1): (0.1, 0.0), T0 + timedelta(minutes=14): (0.3, 0.2), T0 + timedelta(minutes=16): (-0.5, 0.0)}
    out = attach(bars, metrics, book)
    assert out[0].oi == 100.0 and abs(out[0].imb1 - 0.2) < 1e-9
    assert out[1].oi == 200.0 and out[1].imb1 == -0.5


def test_resample_and_roundtrip(tmp_path):
    bars = flow_bars(96 * 3, step=timedelta(minutes=15))
    daily = resample_flow(bars, 1440)
    assert len(daily) == 3
    assert abs(daily[0].buy_volume - sum(b.buy_volume for b in bars[:96])) < 1e-6
    path = tmp_path / "f" / "XRPUSDT_15min.csv"
    save_flow(str(path), bars)
    back = load_flow(str(path))
    assert len(back) == len(bars) and back[5].buy_volume == bars[5].buy_volume and back[5].oi is None
    series = flow_series("XRPUSDT", str(tmp_path / "f"))
    assert set(series) == {"15min", "1h", "4h", "1d"}


def test_estimated_buy_volume_follows_the_move():
    bars = make_bars([100, 101, 102, 101, 100, 103], start=T0)
    est = estimated_buy_volume(bars)
    assert est[2] > 500 and est[4] < 500  # alta = mais compra, queda = mais venda
    _, real = buy_volumes(bars)
    assert real is False
    _, real = buy_volumes(flow_bars(60))
    assert real is True


def test_binance_symbol():
    assert binance_symbol("XRP/USD") == "XRPUSDT"


def test_flow_strategies_run_in_backtest():
    trader = next(t for t in default_traders() if t.key == "rui")
    bars = flow_bars(900, book=lambda i: 0.3 if (i // 20) % 2 else -0.2, oi=lambda i: 1e6 * (1 + 0.002 * i) if (i // 40) % 3 else 1e6 * (1 - 0.003 * (i % 40)))
    for strat in [DeltaBreakout(20), CVDDivergence(20), Absorption(1.5), CVDTrend(28), BookImbalance(0.1), OpenInterestTrend(20), LiquidationFlush(12, 0.05), FlowFilter(DonchianEnsemble(), 20)]:
        rep = run_backtest(replace(trader, strategy=strat, timeframe="1h", atr_stop_multiple=None, reward_ratio=None), bars, RiskConfig())
        assert rep.start is not None, strat.name
    # o rompimento com agressão entra em alta com compra agressiva
    rep = run_backtest(replace(trader, strategy=DeltaBreakout(20, 0.05), timeframe="1h"), bars, RiskConfig())
    assert rep.trades


def test_flow_filter_blocks_against_flow():
    trader = next(t for t in default_traders() if t.key == "rui")
    selling = flow_bars(900, buy_share=lambda i: 0.3)  # só venda agressiva
    rep = run_backtest(replace(trader, strategy=FlowFilter(DonchianEnsemble(), 20)), selling, RiskConfig())
    assert not rep.trades
    plain = run_backtest(replace(trader, strategy=DonchianEnsemble()), selling, RiskConfig())
    assert plain.trades


def test_evaluate_flow_crypto_and_day():
    trader = next(t for t in default_traders() if t.key == "rui")
    bars = flow_bars(700, book=lambda i: 0.2 if i > 300 else None)
    res = evaluate_flow(trader, {"1h": bars}, candidates=FLOW_CANDIDATES[:2] + FLOW_CANDIDATES[8:9])
    assert {r.candidate for r in res} >= {FLOW_CANDIDATES[0].label}
    book_res = [r for r in res if r.candidate == FLOW_CANDIDATES[8].label]
    assert all(r.train.start >= bars[301].ts for r in book_res)  # só o trecho com livro
    assert isinstance(ranking_markdown(res, top=3), str)

    from trade_city.intraday import NY

    day = []
    d = datetime(2025, 3, 3, 9, 30, tzinfo=NY)
    price = 500.0
    for k in range(8):
        for m in range(78):
            ts = (d + timedelta(days=k, minutes=5 * m)).astimezone(timezone.utc)
            o = price
            price *= 1 + 0.001 * math.sin(m / 5 + k)
            day.append(make_bars([o, price], start=ts, step=timedelta(minutes=5))[1])
    teo = next(t for t in default_traders() if t.key == "teo")
    res = evaluate_flow(teo, {"5min": day}, candidates=FLOW_DAY_CANDIDATES[:3], day=True)
    assert res and all(r.timeframe == "5min" for r in res)


def test_book_features_and_collector(tmp_path):
    book = {"bids": [["99.9", "10", 1], ["99.0", "5", 1]], "asks": [["100.1", "10", 1], ["101.5", "5", 1]]}
    f = book_features(book)
    assert abs(f["mid"] - 100.0) < 1e-9
    assert f["bid_0.1pct"] == 999.0 and f["ask_2pct"] == 100.1 * 10 + 101.5 * 5

    clock = {"t": 1_700_000_000.0}
    tid = {"cb": 10, "bn": 100}

    def get(url):
        if "/book" in url:
            return book
        if "coinbase" in url:
            tid["cb"] += 2
            return [{"trade_id": tid["cb"], "side": "sell", "size": "1", "price": "100"}, {"trade_id": tid["cb"] - 1, "side": "buy", "size": "2", "price": "100"}]
        tid["bn"] += 1
        return [{"a": tid["bn"], "p": "100", "q": "3", "m": False}]

    def sleep(s):
        clock["t"] += 15

    rows = run_collector(["XRP/USD"], str(tmp_path), 3, 15, get=get, clock=lambda: clock["t"], sleep=sleep)
    assert rows >= 2
    files = list((tmp_path / "XRPUSDT").iterdir())
    text = files[0].read_text().splitlines()
    assert text[0].startswith("ts,mid,spread_bps") and len(text) >= 3


def test_portfolio_limits_in_auditor_and_risk_weight():
    cfg = RiskConfig()
    sig = Signal("rui", "XRP/USD", 1.0, "x", T0, Side.LONG)
    plan = TradePlan(sig, 100.0, 0.5, 2.0, 50.0, "normal")
    base = dict(capital=10_000, peak_capital=10_000, day_losses=0, day_pnl=0, has_open_position=False, buying_power=1e9)
    assert Auditor(cfg).review(plan, AuditContext(**base)).approved
    full = AuditContext(**base, portfolio_capital=60_000, portfolio_open_risk=1_790, group_open_risk=0)
    res = Auditor(cfg).review(plan, full)
    assert not res.approved and "carteira" in res.reasons[0]
    grp = AuditContext(**base, portfolio_capital=60_000, portfolio_open_risk=0, group_open_risk=880)
    assert not Auditor(cfg).review(plan, grp).approved
    teo = next(t for t in default_traders() if t.key == "teo")
    assert abs(risk_for(replace(teo, risk_weight=0.5), cfg).risk_per_trade - cfg.risk_per_trade * 0.5) < 1e-12
