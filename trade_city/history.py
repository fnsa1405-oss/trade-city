"""Histórico intradiário para a escola de day trade.

As fontes gratuitas guardam pouco: o Yahoo só tem ~60 dias de 5 min e ~30 dias de
1 min. Por isso o histórico junta três coisas, nesta ordem de preferência:

1. o que o coletor já guardou (pasta `dados/`, que cresce todo dia útil);
2. a Massive (antiga Polygon.io), se houver a chave MASSIVE_API_KEY: ~2 anos de 1 min;
3. o Yahoo Finance (os últimos dias).

Só entra o pregão regular (9h30 às 16h de Nova York).
"""
from __future__ import annotations

import os

from .data import load_csv, save_csv
from .intraday import regular_session
from .models import Bar

DAY_TIMEFRAMES = ("5min", "1min")
MIN_SESSIONS_BEFORE_MASSIVE = 300  # com mais que isso guardado, não precisa baixar de novo


def _sessions(found: dict) -> int:
    from .intraday import NY

    return len({ts.astimezone(NY).date() for ts in found})


def csv_path(folder: str, symbol: str, timeframe: str) -> str:
    return os.path.join(folder, f"{symbol.replace('/', '-')}_{timeframe}.csv")


def _merge(into: dict, bars: list[Bar]) -> None:
    for b in bars:
        into.setdefault(b.ts, b)


def massive_key() -> str:
    return os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY") or ""


def intraday_history(symbol: str, timeframe: str, folder: str = "dados", days: int = 730, log=print) -> list[Bar]:
    found: dict = {}
    path = csv_path(folder, symbol, timeframe)
    if os.path.exists(path):
        _merge(found, load_csv(path))
        log(f"  {symbol} {timeframe}: {len(found)} candles guardados pelo coletor")
    key = massive_key()
    if key and _sessions(found) < MIN_SESSIONS_BEFORE_MASSIVE:
        from .public_data import massive_bars

        try:
            bars = massive_bars(symbol, timeframe, days, key)
            _merge(found, bars)
            log(f"  {symbol} {timeframe}: {len(bars)} candles da Massive")
        except Exception as exc:
            log(f"  aviso: Massive falhou para {symbol} {timeframe}: {exc}")
    from .public_data import yahoo_bars

    try:
        _merge(found, yahoo_bars(symbol, timeframe, days))
    except Exception as exc:
        log(f"  aviso: Yahoo falhou para {symbol} {timeframe}: {exc}")
    return regular_session([found[k] for k in sorted(found)])


def collect(symbols: list[str], folder: str = "dados", log=print) -> None:
    """Coletor: junta os candles recentes do Yahoo ao que já está guardado."""
    from .public_data import yahoo_bars

    os.makedirs(folder, exist_ok=True)
    for symbol in symbols:
        for tf in DAY_TIMEFRAMES:
            path = csv_path(folder, symbol, tf)
            found: dict = {}
            if os.path.exists(path):
                _merge(found, load_csv(path))
            before = len(found)
            key = massive_key()
            if key and _sessions(found) < MIN_SESSIONS_BEFORE_MASSIVE:
                from .public_data import massive_bars

                try:  # primeira vez: busca ~2 anos na Massive (antiga Polygon.io)
                    _merge(found, regular_session(massive_bars(symbol, tf, 730, key)))
                except Exception as exc:
                    log(f"aviso: Massive falhou para {symbol} {tf}: {exc}")
            _merge(found, regular_session(yahoo_bars(symbol, tf, 59)))
            save_csv(path, [found[k] for k in sorted(found)])
            log(f"{symbol} {tf}: {len(found)} candles guardados (+{len(found) - before})")
