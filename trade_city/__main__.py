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


def _desk(db: str, corretora: str = "simulada", grupo: str = "todos"):
    from .desk import Desk

    approved = [t for t in default_traders() if t.approved]  # só quem passou na escola opera
    if grupo == "swing":
        approved = [t for t in approved if not t.strategy.day_trade]
    elif grupo == "day":
        approved = [t for t in approved if t.strategy.day_trade]
    ledger = Ledger(db)
    if corretora == "alpaca":
        from .broker.alpaca import AlpacaBroker

        broker = AlpacaBroker.from_env()
    else:
        from .broker.paper import PaperBroker

        broker = PaperBroker(ledger.conn, initial_cash=sum(t.capital for t in approved))
    return Desk(approved, broker, ledger)


def _history_note(series) -> str:
    from .intraday import NY

    parts = []
    for tf, bars in series.items():
        days = len({b.ts.astimezone(NY).date() for b in bars})
        span = f"{bars[0].ts:%d/%m/%Y} a {bars[-1].ts:%d/%m/%Y}" if bars else "sem dados"
        parts.append(f"{tf}: {days} pregões ({span})")
    return "Histórico de day trade: " + "; ".join(parts) + "\n"


def main(argv: list[str] | None = None) -> None:
    _load_env_file()
    parser = argparse.ArgumentParser(prog="trade_city", description="Trade City: mesa de traders de IA")
    parser.add_argument("--db", default="trade_city.db", help="arquivo SQLite do livro de registros")
    parser.add_argument(
        "--corretora",
        choices=["simulada", "alpaca"],
        default="simulada",
        help="simulada = corretora própria com preços reais e dinheiro de mentira (padrão)",
    )
    parser.add_argument(
        "--grupo",
        choices=["todos", "swing", "day"],
        default="todos",
        help="swing = cripto e operações de vários dias; day = day trade no pregão de Nova York",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("traders", help="lista os traders e suas estratégias")
    bt = sub.add_parser("backtest", help="roda o backtest de um trader")
    bt.add_argument("trader")
    bt.add_argument("--csv", help="candles em CSV (senão baixa da internet)")
    bt.add_argument("--fonte", choices=["publica", "alpaca"], default="publica", help="de onde baixar os candles")
    bt.add_argument("--dias", type=int, default=730)
    bt.add_argument("--salvar", help="salva os candles baixados neste CSV")
    esc = sub.add_parser("escola", help="testa várias estratégias e tempos gráficos por trader")
    esc.add_argument("trader", nargs="?", default="todos")
    esc.add_argument("--dias", type=int, default=1095, help="dias de histórico para cripto e para o diário de ações")
    esc.add_argument("--saida", help="salva o relatório em Markdown neste arquivo")
    esc.add_argument("--dados", default="dados", help="pasta com os candles guardados pelo coletor")
    col = sub.add_parser("coletar", help="guarda os candles de 5 e 1 min dos traders de day trade")
    col.add_argument("--dados", default="dados")
    run = sub.add_parser("rodar", help="roda a mesa (corretora simulada por padrão)")
    run.add_argument("--loop", type=int, default=0, help="segundos entre ciclos (0 = um ciclo só)")
    run.add_argument("--desde", help="HH:MM de Nova York: espera até esse horário para começar")
    run.add_argument("--ate", help="HH:MM de Nova York: para o loop nesse horário")
    sub.add_parser("placar", help="mostra o placar do dia")
    sub.add_parser("panico", help="trava a mesa e zera todas as posições")
    sub.add_parser("destravar", help="libera a mesa depois do pânico")
    args = parser.parse_args(argv)

    if args.cmd == "traders":
        for t in default_traders():
            status = "aprovado" if t.approved else "na escola"
            print(f"{t.key:6} {t.name:12} {t.symbol:8} {t.timeframe:5} [{status}] {t.strategy.name}: {t.strategy.description}")
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

    if args.cmd == "escola":
        from .models import AssetClass
        from .public_data import public_bars
        from .school import evaluate, report_markdown, timeframes_for

        traders = default_traders() if args.trader == "todos" else [_trader(args.trader)]
        parts = ["## Escola de traders", "", "Estratégia escolhida no treino (70% iniciais do histórico) e conferida na prova (30% finais).", ""]
        for trader in traders:
            print(f"escola: {trader.name} ({trader.symbol})...", flush=True)
            try:
                note = ""
                if trader.asset_class is AssetClass.CRYPTO:
                    series = timeframes_for(trader, public_bars(trader.symbol, trader.asset_class, "1h", args.dias), "1h")
                elif trader.day_trade:
                    from .history import DAY_TIMEFRAMES, intraday_history

                    series = {tf: intraday_history(trader.symbol, tf, args.dados) for tf in DAY_TIMEFRAMES}
                    note = _history_note(series)
                else:
                    series = {
                        "1d": public_bars(trader.symbol, trader.asset_class, "1d", max(args.dias, 3650)),
                        "1h": public_bars(trader.symbol, trader.asset_class, "1h", 729),
                    }
                section = report_markdown(trader, evaluate(trader, series)) + note
            except Exception as exc:  # um ativo com problema não derruba os outros
                section = f"### {trader.name} ({trader.symbol})\n\nErro ao testar: {exc}\n"
            print(section, flush=True)
            parts.append(section)
        if args.saida:
            with open(args.saida, "w") as fh:
                fh.write("\n".join(parts))
        return

    if args.cmd == "coletar":
        from .history import collect

        collect(sorted({t.symbol for t in default_traders() if t.day_trade}), args.dados)
        return

    if args.cmd == "destravar":
        Ledger(args.db).kill_switch = False
        print("mesa destravada")
        return

    desk = _desk(args.db, args.corretora, args.grupo)
    if args.cmd == "placar":
        from .scoreboard import render

        print(render(desk))
    elif args.cmd == "panico":
        print("\n".join(desk.panic()))
    elif args.cmd == "rodar":
        from datetime import datetime

        from .intraday import NY

        def ny_minutes() -> int:
            now = datetime.now(NY)
            return now.hour * 60 + now.minute

        def hm(text: str) -> int:
            h, m = text.split(":")
            return int(h) * 60 + int(m)

        print(f"mesa rodando em modo {'simulado (dinheiro de mentira)' if desk.broker.paper else 'REAL'}")
        if args.ate and ny_minutes() >= hm(args.ate):
            print("fora do horário desta rodada")
            return
        if args.desde:
            while ny_minutes() < hm(args.desde):
                time.sleep(20)
        while True:
            for event in desk.run_once():
                print(event, flush=True)
            if not args.loop or (args.ate and ny_minutes() >= hm(args.ate)):
                break
            time.sleep(args.loop)


if __name__ == "__main__":
    main()
