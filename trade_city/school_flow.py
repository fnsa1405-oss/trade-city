"""Escola de fluxo de ordens: as mesmas regras da escola (treino nos 70% iniciais, prova nos
30% finais, custos reais), com estratégias que leem delta, CVD, livro e contratos em aberto.

- Criptos: fluxo real da Binance (15 min dos últimos 3 anos, 1h, 4h e diário desde 2017-2020).
  Estratégias que precisam do livro (desde 2023) ou dos contratos em aberto (desde 2021)
  usam só o trecho do histórico em que esses dados existem.
- Índices: day trade com microcontratos (MNQ, MES, MYM, M2K) e delta ESTIMADO a partir dos
  candles de 1 e 5 min dos ETFs (o fluxo real da CME é pago).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from .config import TraderProfile
from .models import Bar
from .school import DAY_RISK_VARIANTS, RISK_VARIANTS, Candidate, Result, SchoolRules, evaluate, pick, _pf
from .strategies import DonchianEnsemble, TimeSeriesMomentum, TurtleBreakout
from .strategies.orderflow import (
    Absorption,
    BookImbalance,
    CVDDivergence,
    CVDTrend,
    DayAbsorption,
    DeltaBreakout,
    FlowFilter,
    LiquidationFlush,
    OpenInterestTrend,
    ORBDelta,
    VWAPDeltaTrend,
)

FLOW_CANDIDATES: list[Candidate] = [
    Candidate("Rompimento com agressão 20", lambda: DeltaBreakout(20)),
    Candidate("Rompimento com agressão 55", lambda: DeltaBreakout(55)),
    Candidate("Divergência de CVD 20", lambda: CVDDivergence(20)),
    Candidate("Divergência de CVD 50", lambda: CVDDivergence(50)),
    Candidate("Absorção da venda z 2", lambda: Absorption(2.0)),
    Candidate("Absorção da venda z 2,5", lambda: Absorption(2.5)),
    Candidate("Tendência do CVD 28", lambda: CVDTrend(28)),
    Candidate("Tendência do CVD 56", lambda: CVDTrend(56)),
    Candidate("Livro desequilibrado a 1% (>15%)", lambda: BookImbalance(0.15, "imb1")),
    Candidate("Livro desequilibrado a 5% (>10%)", lambda: BookImbalance(0.10, "imb5")),
    Candidate("Rompimento com contratos em aberto subindo", lambda: OpenInterestTrend(20)),
    Candidate("Fim de liquidação", lambda: LiquidationFlush(12, 0.08)),
    Candidate("Donchian em conjunto + fluxo a favor", lambda: FlowFilter(DonchianEnsemble(), 20)),
    Candidate("Momento 28 + fluxo a favor", lambda: FlowFilter(TimeSeriesMomentum(28), 28)),
    Candidate("Turtle 20/10 + fluxo a favor", lambda: FlowFilter(TurtleBreakout(20, 10), 20)),
]

FLOW_DAY_CANDIDATES: list[Candidate] = [
    Candidate("ORB 5 min + delta", lambda: ORBDelta(5, 0.2)),
    Candidate("ORB 15 min + delta", lambda: ORBDelta(15, 0.2)),
    Candidate("VWAP + CVD do dia 10%", lambda: VWAPDeltaTrend(0.1)),
    Candidate("VWAP + CVD do dia 20%", lambda: VWAPDeltaTrend(0.2)),
    Candidate("Absorção no extremo do dia z 2,5", lambda: DayAbsorption(2.5)),
    Candidate("Absorção no extremo do dia z 3", lambda: DayAbsorption(3.0)),
]


def _trim(bars: Sequence[Bar], needs: str | None) -> list[Bar]:
    """Começa a série no primeiro candle que tem o dado de que a estratégia precisa."""
    if needs is None:
        return list(bars)
    field = "imb1" if needs == "book" else "oi"
    for k, b in enumerate(bars):
        if getattr(b, field, None) is not None:
            return list(bars[k:])
    return []


def evaluate_flow(
    trader: TraderProfile,
    series: dict[str, list[Bar]],
    rules: SchoolRules = SchoolRules(),
    candidates: Sequence[Candidate] | None = None,
    day: bool = False,
    fine=None,
) -> list[Result]:
    if day:
        from .futures import MICROS

        student = replace(trader, day_trade=True)
        return evaluate(student, series, rules, candidates or FLOW_DAY_CANDIDATES, DAY_RISK_VARIANTS, fine=fine, contract=MICROS.get(trader.symbol))
    out: list[Result] = []
    groups: dict[str | None, list[Candidate]] = {}
    for c in candidates or FLOW_CANDIDATES:
        groups.setdefault(getattr(c.make(), "needs", None), []).append(c)
    for needs, cands in groups.items():
        trimmed = {tf: _trim(b, needs) for tf, b in series.items()}
        out += evaluate(trader, trimmed, rules, cands, RISK_VARIANTS, contract=None)
    return out


def ranking_markdown(results: Sequence[Result], rules: SchoolRules = SchoolRules(), top: int = 5) -> str:
    """As melhores no treino, com a prova ao lado, para mostrar o que quase passou."""
    best = sorted(
        (r for r in results if len(r.train.trades) >= rules.train_min_trades),
        key=lambda r: r.train.profit_factor,
        reverse=True,
    )[:top]
    if not best:
        return ""
    lines = ["", "| Estratégia | Tempo | Ajuste | Treino (op., FL) | Prova (op., FL, resultado) | Passou? |", "| --- | --- | --- | --- | --- | --- |"]
    for r in best:
        ok = "sim" if r.train_ok(rules) and r.test_ok(rules) else ("só no treino" if r.train_ok(rules) else "não")
        lines.append(
            f"| {r.candidate} | {r.timeframe} | {r.risk} | {len(r.train.trades)}, {_pf(r.train.profit_factor)} | "
            f"{len(r.test.trades)}, {_pf(r.test.profit_factor)}, {r.test.total_pnl / r.test.base_capital:+.1%} | {ok} |"
        )
    return "\n".join(lines) + "\n"


__all__ = ["FLOW_CANDIDATES", "FLOW_DAY_CANDIDATES", "evaluate_flow", "ranking_markdown", "pick"]
