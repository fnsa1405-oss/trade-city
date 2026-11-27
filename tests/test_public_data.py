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
