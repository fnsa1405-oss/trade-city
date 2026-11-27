"""Candles históricos de fontes públicas, sem conta em corretora.

- Cripto (BTC/USD): API pública da Coinbase Exchange.
- Ações e ETFs (QQQ, SPY): Yahoo Finance via yfinance. Atenção: o Yahoo só
  entrega candles de 5 min dos últimos ~60 dias.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .models import AssetClass, Bar

COINBASE_URL = "https://api.exchange.coinbase.com/products/{product}/candles"
COINBASE_GRANULARITY = {"1min": 60, "5min": 300, "15min": 900, "1h": 3600, "1d": 86400}
COINBASE_MAX_CANDLES = 300
YAHOO_INTERVAL = {"1min": "1m", "5min": "5m", "15min": "15m", "1h": "1h", "1d": "1d"}
YAHOO_INTRADAY_MAX_DAYS = {"1m": 7, "5m": 59, "15m": 59, "1h": 729}


def _http_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "trade-city-backtest"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def parse_coinbase(rows: list[list[float]]) -> list[Bar]:
    """Linhas da Coinbase: [tempo, mínima, máxima, abertura, fechamento, volume]."""
    return [
        Bar(datetime.fromtimestamp(r[0], tz=timezone.utc), float(r[3]), float(r[2]), float(r[1]), float(r[4]), float(r[5]))
        for r in rows
    ]


def coinbase_bars(symbol: str, timeframe: str, days: int, fetch=_http_json, pause: float = 0.2) -> list[Bar]:
    gran = COINBASE_GRANULARITY[timeframe]
    product = symbol.replace("/", "-")
    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=days)
    step = timedelta(seconds=gran * COINBASE_MAX_CANDLES)
    bars: dict[datetime, Bar] = {}
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + step, end)
        query = urllib.parse.urlencode(
            {"granularity": gran, "start": cursor.isoformat(), "end": chunk_end.isoformat()}
        )
        for bar in parse_coinbase(fetch(COINBASE_URL.format(product=product) + "?" + query)):
            bars[bar.ts] = bar
        cursor = chunk_end
        if pause:
            time.sleep(pause)
    span = timedelta(seconds=gran)
    now = datetime.now(timezone.utc)
    return sorted((b for b in bars.values() if b.ts + span <= now), key=lambda b: b.ts)


def coinbase_latest(symbol: str, fetch=_http_json) -> float:
    data = fetch(f"https://api.exchange.coinbase.com/products/{symbol.replace('/', '-')}/ticker")
    return float(data["price"])


def yahoo_latest(symbol: str) -> float:
    import yfinance as yf

    try:
        return float(yf.Ticker(symbol).fast_info["last_price"])
    except Exception:
        bars = yahoo_bars(symbol, "1h", 5)
        if not bars:
            raise
        return bars[-1].close


def latest_price(symbol: str, asset_class: AssetClass) -> float:
    if asset_class is AssetClass.CRYPTO:
        return coinbase_latest(symbol)
    return yahoo_latest(symbol)


def yahoo_bars(symbol: str, timeframe: str, days: int) -> list[Bar]:
    import yfinance as yf

    interval = YAHOO_INTERVAL[timeframe]
    limit = YAHOO_INTRADAY_MAX_DAYS.get(interval)
    if limit is not None and days > limit:
        print(f"aviso: o Yahoo só tem {limit} dias de candles de {timeframe}; usando {limit} dias")
        days = limit
    start = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    frame = yf.Ticker(symbol).history(start=start.isoformat(), interval=interval, auto_adjust=True)
    bars = []
    for ts, row in frame.iterrows():
        when = ts.to_pydatetime()
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        bars.append(Bar(when.astimezone(timezone.utc), float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), float(row["Volume"])))
    if interval == "1d" and bars:
        # o candle diário de hoje só fecha às 16h de Nova York: até lá ele está incompleto
        from zoneinfo import ZoneInfo

        ny_now = datetime.now(ZoneInfo("America/New_York"))
        if ny_now.hour < 17:
            bars = [b for b in bars if b.ts.astimezone(ZoneInfo("America/New_York")).date() < ny_now.date()]
    if interval != "1d" and bars:
        span = timedelta(minutes=int(interval[:-1]) * (60 if interval.endswith("h") else 1))
        now = datetime.now(timezone.utc)
        bars = [b for b in bars if b.ts + span <= now]
    return bars


def public_bars(symbol: str, asset_class: AssetClass, timeframe: str, days: int) -> list[Bar]:
    if asset_class is AssetClass.CRYPTO:
        if timeframe == "4h":  # a Coinbase não tem 4h: junta candles de 1h
            from .data import resample

            return resample(coinbase_bars(symbol, "1h", days), 4)
        return coinbase_bars(symbol, timeframe, days)
    return yahoo_bars(symbol, timeframe, days)
