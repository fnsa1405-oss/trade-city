"""Gestão de carteira: como dividir o risco entre os traders aprovados.

1. Correlação: cada trader vira uma série diária de resultado (o resultado de cada operação
   espalhado pelos dias em que ela ficou aberta). Traders com correlação de 0,4 ou mais
   formam um grupo (ex.: QQQ, SPY e DIA andam juntos e contam quase como uma aposta só).
2. Paridade de risco: cada grupo recebe a mesma fatia de risco e, dentro do grupo, cada
   trader recebe na proporção inversa da volatilidade dos seus resultados. Não usa o lucro
   passado para dar peso (isso premiaria sorte). O peso multiplica o risco por operação.
3. Calibração do risco por operação: testa de 0,25% a 2% rodando o backtest de verdade (com
   todas as travas, inclusive a de queda que manda o trader de volta à escola). Escolhe o
   MAIOR risco em que, no treino (70% iniciais do período comum), a carteira: não teve trader
   parado pela trava de queda, teve queda máxima de até 12%, e a simulação de 2.000 anos
   embaralhados (blocos de 20 dias) tem queda de até 15% em 95% dos casos. Depois confere na
   prova (30% finais).
4. Limites da carteira (Auditor): risco aberto somado de todos os traders e de cada grupo,
   em % do capital total. Uma ordem nova que passaria do limite é recusada.
"""
from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta

from .backtest import run_backtest
from .config import RiskConfig, TraderProfile
from .models import AssetClass, ClosedTrade

WEEKEND_BOOSTS = (1.0, 1.5, 2.0)  # risco das criptos no fim de semana (bolsa fechada)
RISK_GRID = (0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02)
CLUSTER_CORR = 0.4
MAX_TRAIN_DD = 0.12
MAX_MC_DD = 0.15
MAX_PORTFOLIO_RISK = 0.03  # risco aberto somado: até 3% do capital total
MAX_CLUSTER_RISK = 0.015  # risco aberto de um grupo correlacionado: até 1,5% do capital total


def daily_series(trades: Sequence[ClosedTrade], start: date, end: date) -> list[float]:
    """Resultado diário (em dólar), com cada operação espalhada pelos dias em que ficou aberta."""
    n = (end - start).days + 1
    out = [0.0] * n
    for t in trades:
        a, b = t.opened_at.date(), t.closed_at.date()
        days = max(1, (b - a).days + 1)
        for k in range(days):
            idx = (a - start).days + k
            if 0 <= idx < n:
                out[idx] += t.pnl / days
    return out


def corr(x: Sequence[float], y: Sequence[float]) -> float:
    n = len(x)
    if n < 3:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return 0.0
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def std(x: Sequence[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    m = sum(x) / n
    return math.sqrt(sum((a - m) ** 2 for a in x) / (n - 1))


def clusters(keys: Sequence[str], matrix: dict[tuple[str, str], float], th: float = CLUSTER_CORR) -> list[list[str]]:
    """Grupos ligados por correlação >= th (componentes conexos)."""
    groups: list[list[str]] = []
    seen: set[str] = set()
    for k in keys:
        if k in seen:
            continue
        stack, comp = [k], []
        seen.add(k)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for o in keys:
                if o not in seen and matrix.get((cur, o), 0.0) >= th:
                    seen.add(o)
                    stack.append(o)
        groups.append(sorted(comp, key=list(keys).index))
    return groups


def risk_parity(groups: Sequence[Sequence[str]], vols: dict[str, float]) -> dict[str, float]:
    """Peso de cada trader (média 1): grupos com a mesma fatia, inverso da volatilidade dentro."""
    n = sum(len(g) for g in groups)
    weights: dict[str, float] = {}
    for g in groups:
        inv = {k: 1.0 / vols[k] if vols.get(k) else 0.0 for k in g}
        total = sum(inv.values()) or 1.0
        for k in g:
            share = inv[k] / total if sum(inv.values()) else 1.0 / len(g)
            weights[k] = share / len(groups) * n
    return weights


def max_drawdown(returns: Sequence[float]) -> float:
    """Queda máxima de uma série de retornos diários (fração do capital, soma simples)."""
    eq = peak = 1.0
    dd = 0.0
    for r in returns:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, (peak - eq) / peak)
    return dd


def monte_carlo_dd(returns: Sequence[float], sims: int = 2000, horizon: int = 365, block: int = 20, q: float = 0.95, seed: int = 7) -> float:
    """Queda máxima no pior 5% de `sims` anos montados com blocos de `block` dias sorteados."""
    if len(returns) < block * 2:
        return max_drawdown(returns)
    rnd = random.Random(seed)
    dds = []
    for _ in range(sims):
        path: list[float] = []
        while len(path) < horizon:
            s = rnd.randrange(0, len(returns) - block)
            path.extend(returns[s : s + block])
        dds.append(max_drawdown(path[:horizon]))
    dds.sort()
    return dds[min(len(dds) - 1, int(q * len(dds)))]


@dataclass
class Level:
    risk: float
    train_ret: float
    train_dd: float
    mc_dd: float
    test_ret: float
    test_dd: float
    halted: list[str]
    ok: bool


def _annual(returns: Sequence[float]) -> float:
    years = len(returns) / 365
    return sum(returns) / years if years > 0 else 0.0


def evaluate_levels(
    runs: dict[float, dict[str, list[ClosedTrade]]],
    halts: dict[float, list[str]],
    capital: float,
    start: date,
    end: date,
    split: date,
) -> list[Level]:
    levels = []
    cut = (split - start).days
    for r, by_trader in sorted(runs.items()):
        port = [0.0] * ((end - start).days + 1)
        for trades in by_trader.values():
            for k, v in enumerate(daily_series(trades, start, end)):
                port[k] += v / capital
        train, test = port[:cut], port[cut:]
        halted_train = [k for k, when in halts.get(r, []) if when < split]
        tdd, mdd = max_drawdown(train), monte_carlo_dd(train)
        ok = not halted_train and tdd <= MAX_TRAIN_DD and mdd <= MAX_MC_DD
        levels.append(Level(r, _annual(train), tdd, mdd, _annual(test), max_drawdown(test), [k for k, _ in halts.get(r, [])], ok))
    return levels


def _bars_for(trader: TraderProfile, days: int):
    from .public_data import public_bars

    if trader.asset_class is AssetClass.CRYPTO and getattr(trader.strategy, "uses_flow", False):
        from datetime import datetime, timezone

        from .orderflow import binance_symbol, vision_klines

        today = datetime.now(timezone.utc).date()
        interval = {"1h": "1h", "4h": "4h", "1d": "1d"}[trader.timeframe]
        return vision_klines(binance_symbol(trader.symbol), interval, today - timedelta(days=days), today - timedelta(days=1))
    if trader.asset_class is AssetClass.CRYPTO:
        return public_bars(trader.symbol, trader.asset_class, trader.timeframe, days)
    return public_bars(trader.symbol, trader.asset_class, trader.timeframe, max(days, 3650))


def portfolio_report(traders: Sequence[TraderProfile], days: int = 2900, bars_for=_bars_for) -> tuple[str, dict]:
    # pesos e grupos atuais ficam de fora: a carteira recalcula tudo do zero
    approved = [replace(t, risk_weight=1.0, group="") for t in traders if t.approved]
    bars = {t.key: bars_for(t, days) for t in approved}
    approved = [t for t in approved if bars.get(t.key)]
    names = {t.key: t.name for t in approved}
    # período comum: do início mais tardio ao fim mais cedo
    start = max(bars[t.key][0].ts.date() for t in approved) + timedelta(days=60)
    end = min(bars[t.key][-1].ts.date() for t in approved)
    split = start + timedelta(days=int((end - start).days * 0.7))

    base = RiskConfig(weekend_crypto_boost=1.0)  # o reforço de fim de semana é testado à parte
    base_runs = {t.key: run_backtest(t, bars[t.key], base) for t in approved}
    series = {k: daily_series(rep.trades, start, split - timedelta(days=1)) for k, rep in base_runs.items()}
    keys = [t.key for t in approved]
    matrix = {(a, b): corr(series[a], series[b]) for a in keys for b in keys}
    groups = clusters(keys, matrix)
    vols = {k: std(series[k]) for k in keys}
    weights = risk_parity(groups, vols)

    runs: dict[float, dict[str, list[ClosedTrade]]] = {}
    halts: dict[float, list] = {}
    for r in RISK_GRID:
        runs[r], halts[r] = {}, []
        for t in approved:
            cfg = replace(base, risk_per_trade=r * weights[t.key])
            rep = run_backtest(t, bars[t.key], cfg)
            runs[r][t.key] = rep.trades
            if rep.halted_at:
                halts[r].append((t.key, rep.halted_at.date()))
    capital = sum(t.capital for t in approved)
    levels = evaluate_levels(runs, halts, capital, start, end, split)
    passing = [lv for lv in levels if lv.ok]
    chosen = max(passing, key=lambda lv: lv.risk) if passing else min(levels, key=lambda lv: lv.risk)
    # comparação: o mesmo risco sem os pesos (todos com peso 1)
    runs_eq, halts_eq = {}, []
    for t in approved:
        rep = run_backtest(t, bars[t.key], replace(base, risk_per_trade=chosen.risk))
        runs_eq[t.key] = rep.trades
        if rep.halted_at:
            halts_eq.append((t.key, rep.halted_at.date()))
    equal = evaluate_levels({chosen.risk: runs_eq}, {chosen.risk: halts_eq}, capital, start, end, split)[0]
    use_weights = equal.ok is False or (
        chosen.ok and chosen.test_ret / max(chosen.test_dd, 0.01) >= equal.test_ret / max(equal.test_dd, 0.01) * 0.9
        and chosen.train_ret / max(chosen.train_dd, 0.01) >= equal.train_ret / max(equal.train_dd, 0.01)
    )
    if not use_weights:
        weights = {k: 1.0 for k in keys}

    lines = [
        "## Gestão de carteira",
        "",
        f"Período comum: {start:%d/%m/%Y} a {end:%d/%m/%Y}. Treino até {split:%d/%m/%Y}, prova depois. Capital total simulado: US$ {capital:,.0f}.",
        "",
        "### Correlação dos resultados diários (treino)",
        "",
        "| | " + " | ".join(names[k] for k in keys) + " |",
        "| --- |" + " --- |" * len(keys),
    ]
    for a in keys:
        lines.append(f"| {names[a]} | " + " | ".join(f"{matrix[(a, b)]:+.2f}" for b in keys) + " |")
    lines += ["", "### Grupos e pesos (paridade de risco)", ""]
    for g in groups:
        lines.append("- " + ", ".join(f"{names[k]} (peso {weights[k]:.2f})" for k in g))
    lines += [
        "",
        "### Risco por operação",
        "",
        "Retorno por ano e queda máxima da carteira inteira (sobre o capital total). Queda em 95% dos anos simulados = simulação de 2.000 anos com blocos de 20 dias sorteados do treino.",
        "",
        "| Risco por operação | Treino: retorno/ano | Treino: queda máx. | Queda em 95% dos anos | Prova: retorno/ano | Prova: queda máx. | Trava de queda | Passa? |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for lv in levels:
        mark = " **(escolhido)**" if lv is chosen else ""
        halted = ", ".join(names[k] for k in lv.halted) or "-"
        lines.append(
            f"| {lv.risk:.2%}{mark} | {lv.train_ret:+.1%} | {lv.train_dd:.1%} | {lv.mc_dd:.1%} | {lv.test_ret:+.1%} | {lv.test_dd:.1%} | {halted} | {'sim' if lv.ok else 'não'} |"
        )
    lines.append(
        f"| {equal.risk:.2%} sem pesos (todos iguais) | {equal.train_ret:+.1%} | {equal.train_dd:.1%} | {equal.mc_dd:.1%} | {equal.test_ret:+.1%} | {equal.test_dd:.1%} | "
        f"{', '.join(names[k] for k in equal.halted) or '-'} | {'sim' if equal.ok else 'não'} |"
    )
    lines += [
        "",
        f"Pesos da paridade de risco: {'mantidos' if use_weights else 'descartados (todos iguais foi melhor)'}. Ficam só se o retorno por queda no treino for pelo menos igual e a prova não piorar mais que 10%.",
        "",
        f"Critério: maior risco sem trader parado pela trava de queda no treino, queda máxima no treino até {MAX_TRAIN_DD:.0%} e até {MAX_MC_DD:.0%} em 95% dos anos simulados.",
        f"Limites da carteira no Auditor: risco aberto somado até {MAX_PORTFOLIO_RISK:.1%} do capital total e até {MAX_CLUSTER_RISK:.1%} por grupo correlacionado.",
        "",
    ]
    # fim de semana: com a bolsa fechada, só as criptos operam. Testa dar mais risco a elas
    # nesses dias, no risco escolhido; só liga se melhorar o treino sem quebrar os critérios
    # e não piorar a prova (retorno por unidade de queda)
    boost_rows = []
    for boost in WEEKEND_BOOSTS:
        runs_b, halts_b = {}, []
        for t in approved:
            cfg = replace(base, risk_per_trade=chosen.risk * weights[t.key], weekend_crypto_boost=boost)
            rep = run_backtest(t, bars[t.key], cfg)
            runs_b[t.key] = rep.trades
            if rep.halted_at:
                halts_b.append((t.key, rep.halted_at.date()))
        lv = evaluate_levels({chosen.risk: runs_b}, {chosen.risk: halts_b}, capital, start, end, split)[0]
        boost_rows.append((boost, lv))

    def score(lv):
        return lv.train_ret / max(lv.train_dd, 0.01)

    def test_score(lv):
        return lv.test_ret / max(lv.test_dd, 0.01)

    plain = boost_rows[0][1]
    best_boost = 1.0
    for boost, lv in boost_rows[1:]:
        if lv.ok and score(lv) > score(plain) and test_score(lv) >= test_score(plain) and lv.train_ret > plain.train_ret:
            best_boost = boost
    lines += [
        "### Fim de semana: prioridade às criptos",
        "",
        f"No risco escolhido ({chosen.risk:.2%}), com o risco das criptos multiplicado nos sábados e domingos (horário de Nova York):",
        "",
        "| Reforço | Treino: retorno/ano | Treino: queda máx. | Queda em 95% dos anos | Prova: retorno/ano | Prova: queda máx. | Passa? |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for boost, lv in boost_rows:
        mark = " **(escolhido)**" if boost == best_boost else ""
        lines.append(f"| {boost:g}x{mark} | {lv.train_ret:+.1%} | {lv.train_dd:.1%} | {lv.mc_dd:.1%} | {lv.test_ret:+.1%} | {lv.test_dd:.1%} | {'sim' if lv.ok else 'não'} |")
    lines += ["", "Só liga se passar nos critérios, ganhar mais no treino com melhor retorno por queda e não piorar a prova.", ""]

    group_of = {k: i for i, g in enumerate(groups) for k in g}
    alloc = {
        "risk_per_trade": chosen.risk,
        "weights": {k: round(weights[k], 3) for k in keys},
        "groups": {k: f"grupo{group_of[k] + 1}" for k in keys},
        "max_portfolio_risk": MAX_PORTFOLIO_RISK,
        "max_cluster_risk": MAX_CLUSTER_RISK,
        "weekend_crypto_boost": best_boost,
    }
    return "\n".join(lines), alloc
