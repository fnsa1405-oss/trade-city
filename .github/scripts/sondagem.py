"""Sondagem: formato dos arquivos públicos da Binance (data.binance.vision)."""
import io, urllib.request, zipfile

B = "https://data.binance.vision/data/"
FILES = [
    "spot/monthly/klines/XRPUSDT/1h/XRPUSDT-1h-2025-01.zip",
    "spot/monthly/klines/XRPUSDT/1h/XRPUSDT-1h-2018-06.zip",
    "spot/monthly/klines/DOGEUSDT/1h/DOGEUSDT-1h-2019-08.zip",
    "spot/monthly/klines/SOLUSDT/1h/SOLUSDT-1h-2020-09.zip",
    "futures/um/daily/bookDepth/XRPUSDT/XRPUSDT-bookDepth-2025-06-01.zip",
    "futures/um/daily/metrics/XRPUSDT/XRPUSDT-metrics-2025-06-01.zip",
    "spot/daily/aggTrades/XRPUSDT/XRPUSDT-aggTrades-2025-06-01.zip",
    "futures/um/monthly/bookDepth/XRPUSDT/XRPUSDT-bookDepth-2025-05.zip",
    "futures/um/monthly/metrics/XRPUSDT/XRPUSDT-metrics-2025-05.zip",
    "futures/um/daily/bookDepth/XRPUSDT/XRPUSDT-bookDepth-2022-06-01.zip",
    "futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2021-06-01.zip",
]
for f in FILES:
    try:
        raw = urllib.request.urlopen(B + f, timeout=60).read()
        z = zipfile.ZipFile(io.BytesIO(raw))
        text = z.read(z.namelist()[0]).decode()
        lines = text.splitlines()
        print(f"OK {f}: {len(lines)} linhas")
        for ln in lines[:4] + lines[-2:]:
            print("    ", ln)
    except Exception as e:
        print(f"ERRO {f}: {e}")
