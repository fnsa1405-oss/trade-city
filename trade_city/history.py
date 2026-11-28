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


# B3 --------------------------------------------------------------------------
# O mini índice (WIN) não tem histórico intradiário gratuito. O Yahoo tem o próprio
# Ibovespa (^BVSP), que o WIN acompanha no pregão, e o BOVA11 (ETF do Ibovespa), que traz
# volume de verdade. O coletor guarda os dois todo dia útil para a escola testar o WIN
# quando houver meses de histórico.
B3_SYMBOLS = {"^BVSP": "IBOV", "BOVA11.SA": "BOVA11"}
B3_SESSION = (10 * 60, 18 * 60)  # pregão de São Paulo, em minutos do dia


def b3_session(bars: list[Bar]) -> list[Bar]:
    from zoneinfo import ZoneInfo

    sp = ZoneInfo("America/Sao_Paulo")
    lo, hi = B3_SESSION
    out = []
    for b in bars:
        t = b.ts.astimezone(sp)
        if t.weekday() < 5 and lo <= t.hour * 60 + t.minute < hi:
            out.append(b)
    return out


def collect_b3(folder: str = "dados", log=print, fetch=None) -> None:
    """Coletor da B3: junta os candles recentes do Ibovespa e do BOVA11 ao que já está guardado."""
    if fetch is None:
        from .public_data import yahoo_bars as fetch

    os.makedirs(folder, exist_ok=True)
    for symbol, name in B3_SYMBOLS.items():
        for tf in DAY_TIMEFRAMES:
            path = csv_path(folder, name, tf)
            found: dict = {}
            if os.path.exists(path):
                _merge(found, load_csv(path))
            before = len(found)
            try:
                _merge(found, b3_session(fetch(symbol, tf, 59)))
            except Exception as exc:
                log(f"aviso: Yahoo falhou para {symbol} {tf}: {exc}")
                continue
            if found:
                save_csv(path, [found[k] for k in sorted(found)])
            log(f"{name} {tf}: {len(found)} candles guardados (+{len(found) - before})")
