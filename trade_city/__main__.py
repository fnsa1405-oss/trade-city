"""Linha de comando do Trade City.

  python -m trade_city traders
  python -m trade_city backtest bia --dias 730          (dados públicos, sem conta)
  python -m trade_city backtest bia --fonte alpaca      (dados da Alpaca)
  python -m trade_city backtest lena --csv spy_diario.csv
  python -m trade_city rodar                            (um ciclo)
  python -m trade_city rodar --loop 60                  (a cada 60 s)
  python -m trade_city placar
  python -m trade_city panico
  python -m trade_city destravar
"""
from __future__ import annotations

import argparse
import sys
import time

from .backtest import run_backtest
from .config import RiskConfig, default_traders
from .data import load_csv, save_csv
from .ledger import Ledger


def _load_env_file(path: str = ".env") -> None:
    import os

    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
    except FileNotFoundError:
        pass


def _trader(key: str):
    for t in default_traders():
        if t.key == key:
            return t
    sys.exit(f"trader desconhecido: {key} (use: {', '.join(t.key for t in default_traders())})")


def _desk(db: str):
    from .broker.alpaca import AlpacaBroker
    from .desk import Desk

    return Desk(default_traders(), AlpacaBroker.from_env(), Ledger(db))


def main(argv: list[str] | None = None) -> None:
    _load_env_file()
    parser = argparse.ArgumentParser(prog="trade_city", description="Trade City: mesa de traders de IA")
    parser.add_argument("--db", default="trade_city.db", help="arquivo SQLite do livro de registros")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("traders", help="lista os traders e suas estratégias")
    bt = sub.add_parser("backtest", help="roda o backtest de um trader")
    bt.add_argument("trader")
    bt.add_argument("--csv", help="candles em CSV (senão baixa da internet)")
    bt.add_argument("--fonte", choices=["publica", "alpaca"], default="publica", help="de onde baixar os candles")
    bt.add_argument("--dias", type=int, default=730)
    bt.add_argument("--salvar", help="salva os candles baixados neste CSV")
    run = sub.add_parser("rodar", help="roda a mesa ligada à Alpaca")
    run.add_argument("--loop", type=int, default=0, help="segundos entre ciclos (0 = um ciclo só)")
    sub.add_parser("placar", help="mostra o placar do dia")
    sub.add_parser("panico", help="trava a mesa e zera todas as posições")
    sub.add_parser("destravar", help="libera a mesa depois do pânico")
    args = parser.parse_args(argv)

    if args.cmd == "traders":
        for t in default_traders():
            print(f"{t.key:6} {t.name:12} {t.symbol:8} {t.timeframe:5} {t.strategy.name}: {t.strategy.description}")
            print(f"       {t.persona}")
        return

    if args.cmd == "backtest":
        trader = _trader(args.trader)
        if args.csv:
            bars = load_csv(args.csv)
        else:
            print(f"baixando {args.dias} dias de {trader.symbol} ({trader.timeframe}), fonte {args.fonte}...")
            if args.fonte == "alpaca":
                from .broker.alpaca import AlpacaBroker

                bars = AlpacaBroker.from_env().get_bars(trader.symbol, trader.asset_class, trader.timeframe, args.dias)
            else:
                from .public_data import public_bars

                bars = public_bars(trader.symbol, trader.asset_class, trader.timeframe, args.dias)
            if not bars:
                sys.exit("nenhum candle baixado")
            if args.salvar:
                save_csv(args.salvar, bars)
        print(run_backtest(trader, bars, RiskConfig()).summary())
        return

    if args.cmd == "destravar":
        Ledger(args.db).kill_switch = False
        print("mesa destravada")
        return

    desk = _desk(args.db)
    if args.cmd == "placar":
        from .scoreboard import render

        print(render(desk))
    elif args.cmd == "panico":
        print("\n".join(desk.panic()))
    elif args.cmd == "rodar":
        print(f"mesa rodando em modo {'paper' if desk.broker.paper else 'REAL'}")
        while True:
            for event in desk.run_once():
                print(event, flush=True)
            if not args.loop:
                break
            time.sleep(args.loop)


if __name__ == "__main__":
    main()
