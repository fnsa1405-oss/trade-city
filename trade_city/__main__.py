"""Linha de comando do Trade City.

  python -m trade_city traders
  python -m trade_city backtest bia --dias 730          (dados públicos, sem conta)
  python -m trade_city backtest bia --fonte alpaca      (dados da Alpaca)
  python -m trade_city backtest lena --csv spy_diario.csv
  python -m trade_city rodar                            (um ciclo)
  python -m trade_city rodar --loop 60                  (a cada 60 s)
  python -m trade_city rodar --loop 60 --minutos 55 --painel estado.json
  python -m trade_city placar
  python -m trade_city panico
  python -m trade_city destravar
  python -m trade_city painel --mesa swing --saida estado.json   (estado para o app)
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


def _remote_lock(spec: str | None) -> bool | None:
    """Lê o botão de pânico do app: arquivo no branch "controle" (spec = "ramo:arquivo").

    True = travar, False = liberada, None = não deu para ler (segue como está)."""
    if not spec:
        return None
    import subprocess

    ref, _, path = spec.partition(":")
    try:
        subprocess.run(["git", "fetch", "-q", "--depth=1", "origin", ref], check=True, timeout=60, capture_output=True)
        text = subprocess.run(
            ["git", "show", f"FETCH_HEAD:{path}"], check=True, timeout=30, capture_output=True, text=True
        ).stdout
    except Exception:
        return None
    first = (text.strip().split() or [""])[0].lower()
    if first == "travar":
        return True
    if first == "liberar":
        return False
    return None


def _trader(key: str):
    for t in default_traders():
        if t.key == key:
            return t
    sys.exit(f"trader desconhecido: {key} (use: {', '.join(t.key for t in default_traders())})")


def _desk(db: str, corretora: str = "simulada", grupo: str = "todos"):
    from .brain import setup_of
    from .desk import Desk

    traders = {t.key: t for t in default_traders()}
    # cérebro treinado com outra configuração não vale
    brains = {k: b for k, b in _load_brains().items() if k in traders and b.setup == setup_of(traders[k])}
    # opera quem passou na escola, ou quem tem cérebro promovido (passou na prova filtrando)
    approved = [t for t in traders.values() if t.approved or (t.key in brains and brains[t.key].promoted)]
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
    return Desk(approved, broker, ledger, brains=brains)


def _load_brains(folder: str = "cerebros") -> dict:
    import os

    from .brain import Brain

    brains = {}
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if name.endswith(".json"):
                with open(os.path.join(folder, name)) as fh:
                    brain = Brain.from_json(fh.read())
                brains[brain.trader] = brain
    return brains


def _trader_bars(trader, dados: str, days: int = 1095):
    from .models import AssetClass
    from .public_data import public_bars

    if trader.asset_class is AssetClass.EQUITY and trader.strategy.day_trade:
        from .history import intraday_history

        return intraday_history(trader.symbol, trader.timeframe, dados)
    return public_bars(trader.symbol, trader.asset_class, trader.timeframe, days)


def _train_brains(traders, dados: str, folder: str) -> str:
    import os

    from .brain import FEATURE_NAMES, setup_of, train_brain

    os.makedirs(folder, exist_ok=True)
    lines = [
        "## Treino dos cérebros",
        "",
        "Cada cérebro é uma rede neural pequena que estima a chance de cada oportunidade dar certo, "
        "olhando o clima do gráfico. Treina nos 70% iniciais e só é promovido se filtrar melhor que "
        "operar sem ele nos 30% finais. Nunca mexe nas travas de risco.",
        "",
        f"O que ele olha: {', '.join(FEATURE_NAMES)}.",
        "",
        "| Trader | Situação | Prova sem cérebro | Prova com cérebro | Limite |",
        "| --- | --- | --- | --- | --- |",
    ]
    for trader in traders:
        try:
            bars = _trader_bars(trader, dados)
            report = run_backtest(trader, bars, RiskConfig(), record_features=True)
            brain = train_brain(trader.key, report.trades)
        except Exception as exc:  # um trader com problema não derruba os outros
            lines.append(f"| {trader.name} | erro: {exc} | - | - | - |")
            continue
        path = os.path.join(folder, f"{trader.key}.json")
        if brain is None:
            if os.path.exists(path):
                os.remove(path)
            lines.append(f"| {trader.name} | poucas operações ({len(report.trades)}; mínimo 150) | - | - | - |")
            continue
        brain.setup = setup_of(trader)
        with open(path, "w") as fh:
            fh.write(brain.to_json())
        r = brain.report
        sem, com = r["prova sem cérebro"], r["prova com cérebro"]
        status = "PROMOVIDO" if brain.promoted else "em treinamento (não melhorou a prova)"
        lines.append(
            f"| {trader.name} | {status} | {sem['operações']} op., FL {sem['fator de lucro']}, {sem['resultado']:+.0f} "
            f"| {com['operações']} op., FL {com['fator de lucro']}, {com['resultado']:+.0f} | {brain.threshold:.0%} |"
        )
    return "\n".join(lines) + "\n"


def _flow_school(trader, args) -> str:
    """Escola de fluxo de ordens de um trader (ver school_flow.py)."""
    from .models import AssetClass
    from .orderflow import binance_symbol, flow_series
    from .school import report_markdown
    from .school_flow import evaluate_flow, ranking_markdown

    if trader.asset_class is AssetClass.CRYPTO:
        series = flow_series(binance_symbol(trader.symbol), args.fluxo)
        if not series:
            return f"### {trader.name} ({trader.symbol})\n\nSem histórico de fluxo (rode fluxo-historico).\n"
        results = evaluate_flow(trader, series)
        note = "Fluxo real da Binance: " + "; ".join(f"{tf} {len(b)} candles desde {b[0].ts:%m/%Y}" for tf, b in series.items() if b) + ". Custo: 0,1% de taxa + 0,05% de derrapagem por lado.\n"
        return report_markdown(trader, results) + ranking_markdown(results) + note
    from .history import DAY_TIMEFRAMES, intraday_history
    from .school import with_15min

    series = {tf: intraday_history(trader.symbol, tf, args.dados) for tf in DAY_TIMEFRAMES}
    note = _history_note(series) + "Delta ESTIMADO pelos candles (classificação de volume em bloco); microcontratos com corretagem e 1 tick de derrapagem.\n"
    series = with_15min(series)
    results = evaluate_flow(trader, series, day=True, fine=series.get("1min"))
    return report_markdown(trader, results) + ranking_markdown(results) + note


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
    esc.add_argument("--modo", choices=["normal", "swing", "scalp", "fluxo"], default="normal", help="swing = índices em swing (60 min e diário); scalp = criptos em 1 e 5 min; fluxo = estratégias de fluxo de ordens")
    esc.add_argument("--fluxo", default="fluxo", help="pasta com o histórico de fluxo das criptos (fluxo-historico)")
    esc.add_argument("--dias", type=int, default=1095, help="dias de histórico para cripto e para o diário de ações")
    esc.add_argument("--saida", help="salva o relatório em Markdown neste arquivo")
    esc.add_argument("--dados", default="dados", help="pasta com os candles guardados pelo coletor")
    cer = sub.add_parser("cerebros", help="treina o cérebro (rede neural) de cada trader aprovado")
    cer.add_argument("--dados", default="dados")
    cer.add_argument("--pasta", default="cerebros")
    cer.add_argument("--saida", help="salva o relatório em Markdown neste arquivo")
    flh = sub.add_parser("fluxo-historico", help="baixa/atualiza o histórico de fluxo das criptos (Binance, grátis)")
    flh.add_argument("--pasta", default="fluxo")
    flh.add_argument("--desde", default="2017-01-01")
    liv = sub.add_parser("coletar-livro", help="fotografa o livro de ofertas e os negócios das criptos ao vivo")
    liv.add_argument("--pasta", default="livro")
    liv.add_argument("--minutos", type=float, default=340)
    liv.add_argument("--intervalo", type=float, default=15, help="segundos entre fotos")
    car = sub.add_parser("carteira", help="divide o risco entre os aprovados e calibra o risco por operação")
    car.add_argument("--dias", type=int, default=2900)
    car.add_argument("--saida", help="salva o relatório em Markdown neste arquivo")
    car.add_argument("--json", help="salva a alocação recomendada neste arquivo")
    col = sub.add_parser("coletar", help="guarda os candles de 5 e 1 min dos traders de day trade e do Ibovespa (B3)")
    col.add_argument("--dados", default="dados")
    run = sub.add_parser("rodar", help="roda a mesa (corretora simulada por padrão)")
    run.add_argument("--loop", type=int, default=0, help="segundos entre ciclos (0 = um ciclo só)")
    run.add_argument("--desde", help="HH:MM de Nova York: espera até esse horário para começar")
    run.add_argument("--ate", help="HH:MM de Nova York: para o loop nesse horário")
    run.add_argument("--minutos", type=float, default=0, help="para o loop depois de tantos minutos (0 = sem limite)")
    run.add_argument("--painel", help="grava o estado da mesa para o app neste arquivo a cada ciclo")
    run.add_argument("--trava-git", help='botão de pânico remoto, ex.: "controle:trava.txt" (conferido a cada ciclo)')
    pain = sub.add_parser("painel", help="grava o estado da mesa em JSON para o app")
    pain.add_argument("--mesa", default="swing", help="nome da mesa no app (swing ou day)")
    pain.add_argument("--saida", default="estado.json")
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
        from .school import current_check, evaluate, report_markdown, timeframes_for, with_15min

        traders = default_traders() if args.trader == "todos" else [_trader(args.trader)]
        parts = ["## Escola de traders", "", "Estratégia escolhida no treino (70% iniciais do histórico) e conferida na prova (30% finais).", ""]
        for trader in traders:
            print(f"escola: {trader.name} ({trader.symbol})...", flush=True)
            try:
                note = ""
                if args.modo == "fluxo":
                    section = _flow_school(trader, args)
                    print(section, flush=True)
                    parts.append(section)
                    continue
                if trader.asset_class is AssetClass.CRYPTO and args.modo == "scalp":
                    from .school import SCALP_RISK_VARIANTS, SCALP_SETUPS

                    series = {
                        "1min": public_bars(trader.symbol, trader.asset_class, "1min", 90),
                        "5min": public_bars(trader.symbol, trader.asset_class, "5min", 365),
                    }
                    note = "Modo scalp: " + "; ".join(f"{tf} {len(b)} candles" for tf, b in series.items()) + ". Custo: 0,1% de taxa + 0,05% de derrapagem por lado.\n"
                    section = report_markdown(trader, evaluate(trader, series, candidates=SCALP_SETUPS, risks=SCALP_RISK_VARIANTS)) + note
                    print(section, flush=True)
                    parts.append(section)
                    continue
                if trader.asset_class is AssetClass.CRYPTO:
                    series = timeframes_for(trader, public_bars(trader.symbol, trader.asset_class, "1h", args.dias), "1h")
                elif trader.day_trade and args.modo == "swing":
                    from dataclasses import replace as _replace

                    from .school import CANDIDATES, SWING_SETUPS

                    swing = _replace(trader, day_trade=False)
                    series = {
                        "1d": public_bars(trader.symbol, trader.asset_class, "1d", max(args.dias, 3650)),
                        "1h": public_bars(trader.symbol, trader.asset_class, "1h", 729),
                    }
                    note = "Modo swing: pode dormir posicionado; confluência com o tempo gráfico de cima.\n"
                    section = report_markdown(swing, evaluate(swing, series, candidates=CANDIDATES + SWING_SETUPS)) + note
                    print(section, flush=True)
                    parts.append(section)
                    continue
                elif trader.day_trade:
                    from .history import DAY_TIMEFRAMES, intraday_history

                    series = {tf: intraday_history(trader.symbol, tf, args.dados) for tf in DAY_TIMEFRAMES}
                    note = _history_note(series)
                    series = with_15min(series)
                else:
                    series = {
                        "1d": public_bars(trader.symbol, trader.asset_class, "1d", max(args.dias, 3650)),
                        "1h": public_bars(trader.symbol, trader.asset_class, "1h", 729),
                    }
                section = report_markdown(trader, evaluate(trader, series, fine=series.get("1min"))) + note
                if trader.approved:
                    section += current_check(trader, series, fine=series.get("1min"))
            except Exception as exc:  # um ativo com problema não derruba os outros
                section = f"### {trader.name} ({trader.symbol})\n\nErro ao testar: {exc}\n"
            print(section, flush=True)
            parts.append(section)
        if args.saida:
            with open(args.saida, "w") as fh:
                fh.write("\n".join(parts))
        return

    if args.cmd == "fluxo-historico":
        from datetime import date

        from .orderflow import binance_symbol, update_history
        from .models import AssetClass

        since = date.fromisoformat(args.desde)
        for t in default_traders():
            if t.asset_class is AssetClass.CRYPTO:
                update_history(binance_symbol(t.symbol), args.pasta, since)
        return

    if args.cmd == "coletar-livro":
        from .book_collector import run_collector
        from .models import AssetClass

        pairs = sorted({t.symbol for t in default_traders() if t.asset_class is AssetClass.CRYPTO})
        run_collector(pairs, args.pasta, args.minutos, args.intervalo)
        return

    if args.cmd == "carteira":
        from .carteira import portfolio_report

        text, alloc = portfolio_report(default_traders(), args.dias)
        print(text)
        if args.saida:
            with open(args.saida, "w") as fh:
                fh.write(text)
        if args.json:
            import json

            with open(args.json, "w") as fh:
                json.dump(alloc, fh, indent=2, ensure_ascii=False)
        return

    if args.cmd == "cerebros":
        text = _train_brains(default_traders(), args.dados, args.pasta)
        print(text)
        if args.saida:
            with open(args.saida, "w") as fh:
                fh.write(text)
        return

    if args.cmd == "coletar":
        from .history import collect, collect_b3

        collect(sorted({t.symbol for t in default_traders() if t.day_trade}), args.dados)
        collect_b3(args.dados)
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
    elif args.cmd == "painel":
        from .painel import write_state

        state = write_state(desk, args.mesa, args.saida)
        print(f"estado da mesa {args.mesa} gravado em {args.saida} ({len(state['traders'])} traders na mesa)")
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
        lock = _remote_lock(args.trava_git)
        if lock is True and not desk.ledger.kill_switch:
            print("botão de pânico do app está acionado")
            for event in desk.panic():
                print(event, flush=True)
        elif lock is False and desk.ledger.kill_switch:
            desk.ledger.kill_switch = False
            print("mesa liberada pelo app")
        if args.ate and ny_minutes() >= hm(args.ate):
            print("fora do horário desta rodada")
            return
        if args.desde:
            while ny_minutes() < hm(args.desde):
                time.sleep(20)
        inicio = time.monotonic()

        def painel() -> None:
            if args.painel:
                from .painel import write_state

                try:
                    write_state(desk, args.grupo if args.grupo != "todos" else "swing", args.painel)
                except Exception as exc:  # o app nunca derruba a mesa
                    print(f"painel: {exc}", flush=True)

        while True:
            for event in desk.run_once():
                print(event, flush=True)
            painel()
            if not args.loop or (args.ate and ny_minutes() >= hm(args.ate)):
                break
            if args.minutos and time.monotonic() - inicio + args.loop > args.minutos * 60:
                break
            time.sleep(args.loop)
            if _remote_lock(args.trava_git) is True and not desk.ledger.kill_switch:
                print("botão de pânico do app acionado", flush=True)
                for event in desk.panic():
                    print(event, flush=True)
                painel()


if __name__ == "__main__":
    main()
