"""Fluxo de ordens (order flow): quem agrediu, quanto e como estava o livro de ofertas.

Profissionais de day trade procuram vantagem no fluxo: o saldo entre agressões de compra e
de venda (delta), o delta acumulado (CVD), absorção (muita agressão sem o preço andar) e o
desequilíbrio entre ofertas de compra e de venda no livro.

Fontes gratuitas que respondem de dentro do GitHub Actions (sondagem de 28/11/2026):

- Binance, arquivos públicos (https://data.binance.vision), sem conta e sem chave:
  * candles do mercado à vista com o volume comprado por agressão (taker buy) desde 2017-2020,
    o que dá o delta de cada candle em anos de histórico;
  * métricas dos futuros perpétuos a cada 5 min (contratos em aberto, razão compra/venda dos
    agressores) desde 2021;
  * profundidade do livro dos futuros a cada ~30 s, somada em faixas de 1% a 5% do preço,
    desde 2023.
- Ao vivo: data-api.binance.vision (livro e negócios do à vista), Coinbase, OKX e Kraken.
  A API principal da Binance e a da Bybit bloqueiam endereços dos EUA (onde roda o GitHub).

Índices (MNQ, MES, MYM, M2K): o fluxo real (negócio a negócio com o lado do agressor) da CME
é pago (Databento, Rithmic, CQG). O plano da Massive cadastrado não inclui negócios nem
cotações. Enquanto isso, o delta dos índices é ESTIMADO pela classificação de volume em bloco
(bulk volume classification, Easley, López de Prado e O'Hara, 2012), que reparte o volume de
cada candle entre compra e venda pelo tamanho do movimento.
"""
from __future__ import annotations

import csv
import io
import math
import os
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .models import Bar

VISION = "https://data.binance.vision/data/"
LIVE = "https://data-api.binance.vision/api/v3/"
FLOW_COLUMNS = ["ts", "open", "high", "low", "close", "volume", "buy_volume", "trades", "oi", "taker_ratio", "imb1", "imb5"]


@dataclass(frozen=True)
class FlowBar(Bar):
    """Candle com o fluxo: volume comprado por agressão, número de negócios e, quando há,
    contratos em aberto (futuros), razão compra/venda dos agressores (futuros) e
    desequilíbrio do livro a 1% e a 5% do preço (de -1 = só venda a +1 = só compra)."""

    buy_volume: float = 0.0
    trades: int = 0
    oi: float | None = None
    taker_ratio: float | None = None
    imb1: float | None = None
    imb5: float | None = None

    @property
    def delta(self) -> float:
        """Agressão de compra menos agressão de venda."""
        return 2 * self.buy_volume - self.volume


def binance_symbol(symbol: str) -> str:
    """"XRP/USD" -> "XRPUSDT" (o par mais negociado da Binance)."""
    base = symbol.split("/")[0].upper()
    return f"{base}USDT"


def _ts(raw: str) -> datetime:
    v = int(float(raw))
    # a partir de 2025 a Binance grava em microssegundos
    return datetime.fromtimestamp(v / 1e6 if v > 10**14 else v / 1e3, tz=timezone.utc)


def parse_klines(text: str) -> list[FlowBar]:
    """Linhas de candles da Binance: abertura, o, h, l, c, volume, fechamento, volume em
    dólar, negócios, volume comprado por agressão, ..."""
    out = []
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0][:1].isdigit():
            continue
        out.append(
            FlowBar(_ts(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]), float(row[9]), int(float(row[8])))
        )
    return out


def _get(url: str, attempts: int = 4) -> bytes | None:
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "trade-city"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def _unzip(raw: bytes | None) -> str | None:
    if not raw:
        return None
    z = zipfile.ZipFile(io.BytesIO(raw))
    return z.read(z.namelist()[0]).decode()


def _months(start: date, end: date) -> list[date]:
    out, cur = [], date(start.year, start.month, 1)
    while cur <= end:
        out.append(cur)
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    return out


def vision_klines(pair: str, interval: str, start: date, end: date, workers: int = 8) -> list[FlowBar]:
    """Candles do à vista com o volume de agressão, mês a mês (e o mês corrente dia a dia)."""
    today = datetime.now(timezone.utc).date()
    urls = []
    for m in _months(start, end):
        if (m.year, m.month) == (today.year, today.month):
            d = m
            while d < today:
                urls.append(f"{VISION}spot/daily/klines/{pair}/{interval}/{pair}-{interval}-{d:%Y-%m-%d}.zip")
                d += timedelta(days=1)
        else:
            urls.append(f"{VISION}spot/monthly/klines/{pair}/{interval}/{pair}-{interval}-{m:%Y-%m}.zip")
    found: dict[datetime, FlowBar] = {}
    with ThreadPoolExecutor(workers) as pool:
        for text in pool.map(lambda u: _unzip(_get(u)), urls):
            for b in parse_klines(text or ""):
                found[b.ts] = b
    return [found[k] for k in sorted(found)]


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def parse_metrics(text: str) -> dict[datetime, tuple[float, float]]:
    """Métricas de 5 min dos futuros: contratos em aberto (em dólar) e razão compra/venda dos agressores."""
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            ts = datetime.fromisoformat(row["create_time"]).replace(tzinfo=timezone.utc)
            out[ts] = (float(row["sum_open_interest_value"] or "nan"), float(row["sum_taker_long_short_vol_ratio"] or "nan"))
        except (KeyError, ValueError):
            continue
    return out


def parse_book_depth(text: str) -> dict[datetime, tuple[float, float]]:
    """Profundidade do livro: para cada foto (~30 s), desequilíbrio a 1% e a 5% do preço.
    Desequilíbrio = (compra - venda) / (compra + venda), com o valor em dólar das ofertas."""
    snaps: dict[datetime, dict[float, float]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            ts = datetime.fromisoformat(row["timestamp"]).replace(tzinfo=timezone.utc)
            snaps.setdefault(ts, {})[float(row["percentage"])] = float(row["notional"])
        except (KeyError, ValueError):
            continue
    out = {}
    for ts, lv in snaps.items():
        vals = []
        for p in (1.0, 5.0):
            bid, ask = lv.get(-p), lv.get(p)
            vals.append((bid - ask) / (bid + ask) if bid and ask and bid + ask > 0 else float("nan"))
        out[ts] = (vals[0], vals[1])
    return out


def vision_daily(pair: str, kind: str, start: date, end: date, workers: int = 8) -> dict[datetime, tuple[float, float]]:
    """Arquivos diários dos futuros: kind = "metrics" ou "bookDepth"."""
    parse = parse_metrics if kind == "metrics" else parse_book_depth
    urls = [f"{VISION}futures/um/daily/{kind}/{pair}/{pair}-{kind}-{d:%Y-%m-%d}.zip" for d in _days(start, end)]
    out: dict[datetime, tuple[float, float]] = {}
    with ThreadPoolExecutor(workers) as pool:
        for text in pool.map(lambda u: _unzip(_get(u)), urls):
            if text:
                out.update(parse(text))
    return out


def _bucket(ts: datetime, minutes: int) -> datetime:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    span = timedelta(minutes=minutes)
    return epoch + ((ts - epoch) // span) * span


def attach(bars: Sequence[FlowBar], metrics: dict, book: dict) -> list[FlowBar]:
    """Junta métricas e livro a cada candle, usando só o que já existia no fechamento dele
    (o último valor até o fim do candle; média do desequilíbrio dentro do candle)."""
    if not bars:
        return []
    step = bars[1].ts - bars[0].ts if len(bars) > 1 else timedelta(minutes=15)
    m_keys = sorted(metrics)
    b_keys = sorted(book)
    out, mi, bi = [], 0, 0
    for b in bars:
        end = b.ts + step
        oi = ratio = None
        while mi < len(m_keys) and m_keys[mi] < end:
            mi += 1
        if mi and m_keys[mi - 1] >= b.ts - step:
            oi, ratio = metrics[m_keys[mi - 1]]
        lo = bi
        while bi < len(b_keys) and b_keys[bi] < end:
            bi += 1
        inside = [book[k] for k in b_keys[lo:bi] if k >= b.ts]
        imb1 = _mean([x[0] for x in inside])
        imb5 = _mean([x[1] for x in inside])
        out.append(FlowBar(b.ts, b.open, b.high, b.low, b.close, b.volume, b.buy_volume, b.trades, _clean(oi), _clean(ratio), imb1, imb5))
    return out


def _clean(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def _mean(vals):
    vals = [v for v in vals if v is not None and not math.isnan(v)]
    return sum(vals) / len(vals) if vals else None


def resample_flow(bars: Sequence[FlowBar], minutes: int) -> list[FlowBar]:
    """Junta candles com fluxo em blocos de `minutes` (alinhados à meia-noite UTC)."""
    if not bars:
        return []
    base = bars[1].ts - bars[0].ts if len(bars) > 1 else timedelta(minutes=minutes)
    expected = max(1, round(timedelta(minutes=minutes) / base))
    groups: dict[datetime, list[FlowBar]] = {}
    for b in bars:
        groups.setdefault(_bucket(b.ts, minutes), []).append(b)
    out = []
    for start in sorted(groups):
        g = groups[start]
        if len(g) < expected * 0.9:
            continue
        out.append(
            FlowBar(
                start, g[0].open, max(b.high for b in g), min(b.low for b in g), g[-1].close,
                sum(b.volume for b in g), sum(b.buy_volume for b in g), sum(b.trades for b in g),
                g[-1].oi, _mean([b.taker_ratio for b in g]), _mean([b.imb1 for b in g]), _mean([b.imb5 for b in g]),
            )
        )
    return out


# guardar e abrir --------------------------------------------------------------

def save_flow(path: str, bars: Sequence[FlowBar]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(FLOW_COLUMNS)
        for b in bars:
            w.writerow([b.ts.isoformat(), b.open, b.high, b.low, b.close, b.volume, b.buy_volume, b.trades,
                        "" if b.oi is None else f"{b.oi:.0f}", "" if b.taker_ratio is None else f"{b.taker_ratio:.4f}",
                        "" if b.imb1 is None else f"{b.imb1:.4f}", "" if b.imb5 is None else f"{b.imb5:.4f}"])


def load_flow(path: str) -> list[FlowBar]:
    if not os.path.exists(path):
        return []

    def opt(v):
        return float(v) if v not in ("", None) else None

    out = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            out.append(FlowBar(datetime.fromisoformat(r["ts"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                               float(r["volume"]), float(r["buy_volume"]), int(float(r["trades"] or 0)),
                               opt(r.get("oi")), opt(r.get("taker_ratio")), opt(r.get("imb1")), opt(r.get("imb5"))))
    return out


def flow_path(folder: str, pair: str, timeframe: str) -> str:
    return os.path.join(folder, f"{pair}_{timeframe}.csv")


def update_history(pair: str, folder: str, since: date = date(2017, 1, 1), log=print) -> list[FlowBar]:
    """Base de 15 min com fluxo, guardada em `folder` e completada a cada chamada."""
    path = flow_path(folder, pair, "15min")
    have = load_flow(path)
    today = datetime.now(timezone.utc).date()
    if have:
        # refaz o último mês (o mês corrente vem em arquivos diários) e o que faltar de métricas/livro
        start = date(have[-1].ts.year, have[-1].ts.month, 1)
        keep = [b for b in have if b.ts.date() < start]
    else:
        start, keep = since, []
    fresh = vision_klines(pair, "15m", start, today - timedelta(days=1))
    m_start = max(start, date(2021, 1, 1))
    b_start = max(start, date(2023, 1, 1))
    metrics = vision_daily(pair, "metrics", m_start, today - timedelta(days=1))
    book = vision_daily(pair, "bookDepth", b_start, today - timedelta(days=1))
    merged = keep + attach(fresh, metrics, book)
    save_flow(path, merged)
    log(f"  {pair}: {len(merged)} candles de 15 min com fluxo ({merged[0].ts:%Y-%m-%d} a {merged[-1].ts:%Y-%m-%d})" if merged else f"  {pair}: sem dados")
    return merged


def flow_series(pair: str, folder: str, days: int | None = None) -> dict[str, list[FlowBar]]:
    """Tempos gráficos para a escola de fluxo: 15 min (últimos 3 anos), 1h, 4h e diário."""
    base = load_flow(flow_path(folder, pair, "15min"))
    if days and base:
        cut = base[-1].ts - timedelta(days=days)
        base = [b for b in base if b.ts >= cut]
    if not base:
        return {}
    recent = [b for b in base if b.ts >= base[-1].ts - timedelta(days=3 * 365)]
    return {"15min": recent, "1h": resample_flow(base, 60), "4h": resample_flow(base, 240), "1d": resample_flow(base, 1440)}


def live_flow_bars(symbol: str, timeframe: str, limit: int = 600, fetch=None) -> list[FlowBar]:
    """Candles com o volume de agressão ao vivo (data-api.binance.vision, aberto nos EUA).
    Só candles já fechados."""
    import json

    interval = {"15min": "15m", "1h": "1h", "4h": "4h", "1d": "1d", "5min": "5m", "1min": "1m"}[timeframe]
    url = f"{LIVE}klines?symbol={binance_symbol(symbol)}&interval={interval}&limit={min(limit, 1000)}"
    raw = fetch(url) if fetch else json.loads((_get(url) or b"[]").decode())
    now = datetime.now(timezone.utc)
    out = []
    for r in raw:
        if int(r[6]) / 1000 > now.timestamp():
            continue  # candle ainda aberto
        out.append(FlowBar(_ts(str(r[0])), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), float(r[9]), int(r[8])))
    return out


# delta estimado (índices) -------------------------------------------------------

def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def estimated_buy_volume(bars: Sequence[Bar], n: int = 50) -> list[float]:
    """Classificação de volume em bloco (Easley, López de Prado e O'Hara, 2012, "Flow Toxicity
    and Liquidity in a High Frequency World"): fração comprada = Φ(ΔP / σ(ΔP)), com σ dos
    últimos `n` candles (só o passado). https://doi.org/10.1093/rfs/hhs053"""
    out = []
    diffs: list[float] = []
    prev = None
    for b in bars:
        d = b.close - (prev if prev is not None else b.open)
        prev = b.close
        sigma = (sum(x * x for x in diffs[-n:]) / len(diffs[-n:])) ** 0.5 if diffs else 0.0
        frac = _phi(d / sigma) if sigma > 0 else 0.5
        out.append(b.volume * frac)
        diffs.append(d)
    return out


def buy_volumes(bars: Sequence[Bar]) -> tuple[list[float], bool]:
    """Volume comprado por agressão de cada candle. Real quando o candle traz o fluxo
    (FlowBar das criptos), estimado nos demais. Devolve (volumes, é_real)."""
    if bars and all(isinstance(b, FlowBar) for b in bars[:5]) and any(b.buy_volume for b in bars[:50]):
        return [b.buy_volume for b in bars], True
    return estimated_buy_volume(bars), False
