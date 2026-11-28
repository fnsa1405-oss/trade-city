"""Sondagem: quais fontes de fluxo de ordens respondem de dentro do GitHub Actions."""
import os, urllib.request, json

KEY = os.environ.get("MASSIVE_API_KEY", "")
URLS = [
    "https://data.binance.vision/data/spot/monthly/klines/XRPUSDT/4h/XRPUSDT-4h-2024-01.zip",
    "https://data.binance.vision/data/spot/daily/aggTrades/XRPUSDT/XRPUSDT-aggTrades-2024-06-01.zip",
    "https://data.binance.vision/data/futures/um/daily/bookDepth/XRPUSDT/XRPUSDT-bookDepth-2024-06-01.zip",
    "https://data.binance.vision/data/futures/um/daily/bookDepth/XRPUSDT/XRPUSDT-bookDepth-2023-01-10.zip",
    "https://data.binance.vision/data/futures/um/daily/metrics/XRPUSDT/XRPUSDT-metrics-2022-01-10.zip",
    "https://data.binance.vision/data/futures/um/daily/bookTicker/XRPUSDT/XRPUSDT-bookTicker-2023-06-01.zip",
    "https://api.binance.com/api/v3/depth?symbol=XRPUSDT&limit=100",
    "https://data-api.binance.vision/api/v3/depth?symbol=XRPUSDT&limit=100",
    "https://data-api.binance.vision/api/v3/klines?symbol=XRPUSDT&interval=4h&limit=2",
    "https://fapi.binance.com/fapi/v1/depth?symbol=XRPUSDT&limit=100",
    "https://api.binance.us/api/v3/depth?symbol=XRPUSD&limit=100",
    "https://api.exchange.coinbase.com/products/XRP-USD/book?level=2",
    "https://api.exchange.coinbase.com/products/XRP-USD/trades?limit=5",
    "https://public.bybit.com/trading/XRPUSDT/XRPUSDT2024-06-01.csv.gz",
    "https://api.bybit.com/v5/market/orderbook?category=linear&symbol=XRPUSDT&limit=50",
    "https://www.okx.com/api/v5/market/books?instId=XRP-USDT&sz=50",
    "https://api.kraken.com/0/public/Depth?pair=XRPUSD&count=50",
    "https://hub.databento.com/v0/metadata.list_datasets",
    f"https://api.massive.com/v3/trades/QQQ?limit=2&apiKey={KEY}",
    f"https://api.massive.com/v3/quotes/QQQ?limit=2&apiKey={KEY}",
    f"https://api.massive.com/futures/vX/contracts?limit=2&apiKey={KEY}",
]
for u in URLS:
    shown = u.split("apiKey=")[0]
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "trade-city"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            print(f"{r.status} {len(body):>9} {shown}  {body[:160]!r}" if not u.endswith('.zip') and not u.endswith('.gz') else f"{r.status} {len(body):>9} {shown}")
    except urllib.error.HTTPError as e:
        print(f"{e.code} {shown} {e.read()[:200]!r}")
    except Exception as e:
        print(f"ERRO {shown} {e}")
