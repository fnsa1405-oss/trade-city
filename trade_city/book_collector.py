"""Coletor do livro de ofertas e dos negócios das criptos, ao vivo.

A cada `intervalo` segundos fotografa o livro completo da Coinbase (a mesma corretora dos
preços da mesa simulada) e junta os negócios novos da Coinbase e da Binance com o lado do
agressor. Grava uma linha por minuto e por ativo em `pasta/PAR/AAAA-MM-DD.csv`:

- mid e spread (em pontos-base);
- dinheiro esperando no livro, de cada lado, até 0,1%, 0,5%, 1% e 2% do preço;
- volume comprado e vendido por agressão (Coinbase e Binance), número de negócios da
  Binance e o maior negócio do minuto (em dólar).

Os arquivos públicos da Binance já trazem anos de agressão e o livro dos futuros. Este
coletor forma o histórico do livro do mercado à vista, minuto a minuto, que ninguém
publica de graça.
"""
from __future__ import annotations

import csv
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

BANDS = (0.001, 0.005, 0.01, 0.02)
COLUMNS = (
    ["ts", "mid", "spread_bps"]
    + [f"{side}_{b * 100:g}pct" for b in BANDS for side in ("bid", "ask")]
    + ["cb_buy", "cb_sell", "bn_buy", "bn_sell", "bn_trades", "max_trade_usd", "fotos"]
)


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "trade-city"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def book_features(book: dict) -> dict | None:
    """Livro nível 2 da Coinbase -> mid, spread e dinheiro por faixa de preço."""
    bids = [(float(p), float(q)) for p, q, *_ in book.get("bids", [])]
    asks = [(float(p), float(q)) for p, q, *_ in book.get("asks", [])]
    if not bids or not asks:
        return None
    best_bid, best_ask = bids[0][0], asks[0][0]
    mid = (best_bid + best_ask) / 2
    out = {"mid": mid, "spread_bps": (best_ask - best_bid) / mid * 1e4}
    for b in BANDS:
        out[f"bid_{b * 100:g}pct"] = sum(p * q for p, q in bids if p >= mid * (1 - b))
        out[f"ask_{b * 100:g}pct"] = sum(p * q for p, q in asks if p <= mid * (1 + b))
    return out


class _Pair:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.cb = symbol.replace("/", "-")
        self.bn = symbol.split("/")[0] + "USDT"
        self.cb_last = 0
        self.bn_last = 0
        self.reset()

    def reset(self):
        self.snaps: list[dict] = []
        self.flow = {"cb_buy": 0.0, "cb_sell": 0.0, "bn_buy": 0.0, "bn_sell": 0.0, "bn_trades": 0, "max_trade_usd": 0.0}

    def poll(self, get=_get) -> None:
        try:
            f = book_features(get(f"https://api.exchange.coinbase.com/products/{self.cb}/book?level=2"))
            if f:
                self.snaps.append(f)
        except Exception:
            pass
        try:
            trades = get(f"https://api.exchange.coinbase.com/products/{self.cb}/trades?limit=1000")
            for t in trades:
                tid = int(t["trade_id"])
                if tid <= self.cb_last or not self.cb_last:
                    continue  # a primeira leitura só marca o ponto de partida
                qty, px = float(t["size"]), float(t["price"])
                # na Coinbase "side" é o lado de quem estava no livro: "sell" = o agressor comprou
                self.flow["cb_buy" if t["side"] == "sell" else "cb_sell"] += qty
                self.flow["max_trade_usd"] = max(self.flow["max_trade_usd"], qty * px)
            if trades:
                self.cb_last = max(self.cb_last, max(int(t["trade_id"]) for t in trades))
        except Exception:
            pass
        try:
            url = f"https://data-api.binance.vision/api/v3/aggTrades?symbol={self.bn}&limit=1000"
            for _ in range(5):
                rows = get(url + (f"&fromId={self.bn_last + 1}" if self.bn_last else ""))
                for r in rows:
                    qty, px = float(r["q"]), float(r["p"])
                    if self.bn_last:  # a primeira leitura só marca o ponto de partida
                        # "m" = o comprador estava no livro, então o agressor vendeu
                        self.flow["bn_sell" if r["m"] else "bn_buy"] += qty
                        self.flow["bn_trades"] += 1
                        self.flow["max_trade_usd"] = max(self.flow["max_trade_usd"], qty * px)
                if rows:
                    self.bn_last = int(rows[-1]["a"])
                if len(rows) < 1000:
                    break
        except Exception:
            pass

    def row(self, minute: datetime) -> list | None:
        if not self.snaps:
            return None
        avg = {k: sum(s[k] for s in self.snaps) / len(self.snaps) for k in self.snaps[0]}
        avg["mid"] = self.snaps[-1]["mid"]
        out = [minute.isoformat()] + [round(avg[c], 6) for c in COLUMNS[1:3]]
        out += [round(avg[c], 2) for c in COLUMNS[3 : 3 + 2 * len(BANDS)]]
        out += [round(self.flow[c], 6) for c in ("cb_buy", "cb_sell", "bn_buy", "bn_sell")]
        out += [self.flow["bn_trades"], round(self.flow["max_trade_usd"], 2), len(self.snaps)]
        return out


def _write(folder: str, pair: _Pair, row: list) -> None:
    day = row[0][:10]
    d = os.path.join(folder, pair.bn)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{day}.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(COLUMNS)
        w.writerow(row)


def run_collector(symbols, folder: str, minutes: float, interval: float = 15, get=_get, clock=time.time, sleep=time.sleep) -> int:
    """Coleta por `minutes` minutos. Devolve quantas linhas gravou."""
    pairs = [_Pair(s) for s in symbols]
    end = clock() + minutes * 60
    cur_min = None
    written = 0
    print(f"coletando livro e negócios de {', '.join(symbols)} por {minutes:g} min", flush=True)
    while clock() < end:
        t0 = clock()
        minute = datetime.fromtimestamp(t0, tz=timezone.utc).replace(second=0, microsecond=0)
        if cur_min is not None and minute != cur_min:
            for p in pairs:
                row = p.row(cur_min)
                if row:
                    _write(folder, p, row)
                    written += 1
                p.reset()
        cur_min = minute
        for p in pairs:
            p.poll(get)
        sleep(max(0.0, interval - (clock() - t0)))
    print(f"coleta encerrada: {written} linhas", flush=True)
    return written
