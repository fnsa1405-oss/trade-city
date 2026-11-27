from datetime import timezone

from trade_city.public_data import coinbase_bars, parse_coinbase


def test_parse_coinbase_columns():
    bar = parse_coinbase([[1700000000, 9.0, 12.0, 10.0, 11.0, 5.0]])[0]
    assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (10.0, 12.0, 9.0, 11.0, 5.0)
    assert bar.ts.tzinfo == timezone.utc


def test_coinbase_paginates_and_dedupes():
    calls = []

    def fake_fetch(url):
        calls.append(url)
        # mesma vela devolvida em todas as páginas: deve aparecer uma vez só
        return [[1700000000, 9.0, 12.0, 10.0, 11.0, 5.0]]

    bars = coinbase_bars("BTC/USD", "1h", days=30, fetch=fake_fetch, pause=0)
    assert len(calls) == 3  # 30 dias de 1h = 720 velas, 300 por página
    assert "BTC-USD" in calls[0] and "granularity=3600" in calls[0]
    assert len(bars) == 1


def test_massive_paginates_and_keeps_key():
    from trade_city.public_data import massive_bars

    calls = []
    pages = {
        0: {"results": [{"t": 1767225600000, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10}], "next_url": "https://api.massive.com/next?cursor=abc"},
        1: {"results": [{"t": 1767225660000, "o": 1.5, "h": 2, "l": 1, "c": 1.8, "v": 5}]},
    }

    def fetch(url):
        calls.append(url)
        return pages[len(calls) - 1]

    bars = massive_bars("SPY", "1min", 10, "KEY", fetch=fetch, pause=0)
    assert [b.close for b in bars] == [1.5, 1.8]
    assert all("apiKey=KEY" in u for u in calls) and "/range/1/minute/" in calls[0]


def test_intraday_history_merges_collected_csv(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    from trade_city import public_data
    from trade_city.data import save_csv
    from trade_city.history import csv_path, intraday_history
    from trade_city.models import Bar

    old = Bar(datetime(2026, 3, 2, 14, 30, tzinfo=timezone.utc), 1, 1, 1, 1)  # 9h30 em NY
    night = Bar(datetime(2026, 3, 2, 23, 0, tzinfo=timezone.utc), 1, 1, 1, 1)  # fora do pregão
    new = Bar(datetime(2026, 3, 3, 14, 30, tzinfo=timezone.utc), 2, 2, 2, 2)
    save_csv(csv_path(str(tmp_path), "SPY", "5min"), [old, night])
    monkeypatch.setattr(public_data, "yahoo_bars", lambda s, tf, d: [new])
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    bars = intraday_history("SPY", "5min", str(tmp_path), log=lambda *_: None)
    assert [b.close for b in bars] == [1, 2]
