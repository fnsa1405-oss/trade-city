"""Escola de traders: cada trader testa várias estratégias e tempos gráficos.

A estratégia é escolhida só com a primeira parte do histórico (treino) e
precisa se confirmar na parte final, que ela nunca viu (prova). Assim a
escola evita premiar uma combinação que deu certo por sorte.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from .backtest import BacktestReport, run_backtest
from .config import RiskConfig, TraderProfile
from .data import resample
from .models import AssetClass, Bar, ClosedTrade
from .scaling import MEDIA, PIRAMIDE, SEM_ESCALA, Scaling
from .strategies import (
    ConnorsRSI2,
    CumulativeRSI,
    IBSReversion,
    TimeSeriesMomentum,
    TurnOfMonth,
    DonchianEnsemble,
    DoubleSevens,
    DowHeikinAshi,
    DowSwing,
    DowTheoryDayTrade,
    FibonacciPullback,
    HeikinAshiTrend,
    HeikinAshiTrendPullback,
    HolyGrail,
    LarryWilliams91,
    LarryWilliams92,
    LarryWilliams93,
    MeanReversion,
    MondayAsiaOpen,
    MovingAverageTrend,
    PivotV2,
    NoiseAreaMomentum,
    OpeningRangeDayTrade,
    PontoContinuo,
    Stormer123,
    StormerIFR2,
    Strategy,
    StructureFailure,
    Supertrend,
    VwapBands,
    TrendFollower,
    TurtleBreakout,
    WilliamsBreakout,
    WyckoffClimax,
    WyckoffSOSLPS,
    WyckoffSpring,
)


@dataclass(frozen=True)
class Candidate:
    label: str
    make: Callable[[], Strategy]
    timeframes: tuple[str, ...] | None = None  # só nestes tempos gráficos (None = todos)
    scale_kind: str | None = None  # "media" ou "piramide": que tipo de preço médio combina com ela


@dataclass(frozen=True)
class RiskVariant:
    label: str
    atr_stop_multiple: float
    reward_ratio: float


CANDIDATES: list[Candidate] = [
    Candidate("tendência 20/50", lambda: TrendFollower(20, 50, 20)),
    Candidate("tendência 10/30", lambda: TrendFollower(10, 30, 10)),
    Candidate("tendência 50/200", lambda: TrendFollower(50, 200, 55)),
    Candidate("retorno IFR2<10 MM200", lambda: MeanReversion(2, 10, 200, 5)),
    Candidate("retorno IFR2<5 MM100", lambda: MeanReversion(2, 5, 100, 5)),
    Candidate("retorno IFR3<20 MM200", lambda: MeanReversion(3, 20, 200, 5)),
    # estratégias publicadas por traders conhecidos (fontes nos docstrings)
    Candidate("Turtle sistema 1 (20/10)", lambda: TurtleBreakout(20, 10)),
    Candidate("Turtle sistema 2 (55/20)", lambda: TurtleBreakout(55, 20)),
    Candidate("Connors RSI(2)", lambda: ConnorsRSI2(5)),
    Candidate("Connors Double 7s", lambda: DoubleSevens()),
    Candidate("Raschke Holy Grail", lambda: HolyGrail()),
    Candidate("Williams rompimento k=0.5", lambda: WilliamsBreakout(0.5)),
    # estratégias atuais de cripto (pesquisa de 27/11/2026, fontes nos docstrings)
    Candidate("Donchian em conjunto (Zarattini/Pagani/Barbon)", lambda: DonchianEnsemble()),
    Candidate("Supertrend 10/3", lambda: Supertrend(10, 3.0)),
    Candidate("Heikin-Ashi + MME50", lambda: HeikinAshiTrend()),
    Candidate("Teoria de Dow (topos e fundos)", lambda: DowSwing(3)),
    Candidate("Abertura da Ásia na segunda (Concretum)", lambda: MondayAsiaOpen()),
    # pesquisa de 28/11/2026: anomalias com estudos publicados e replicados (fontes nos docstrings)
    Candidate("Momento de série temporal 28 (Moskowitz/Liu-Tsyvinski)", lambda: TimeSeriesMomentum(28)),
    Candidate("Momento de série temporal 56", lambda: TimeSeriesMomentum(56)),
    Candidate("Virada do mês (Lakonishok/McConnell)", lambda: TurnOfMonth()),
    Candidate("IBS < 0,2 acima da MM200 (Pagonidis)", lambda: IBSReversion()),
    Candidate("IFR(2) acumulado (Connors/Alvarez)", lambda: CumulativeRSI()),
]

# day trade em ações/ETFs: contexto 60 e 15 min, gatilho no candle de 5 ou 1 min
DAY_CANDIDATES: list[Candidate] = [
    Candidate("ORB 5 min (Zarattini/Aziz)", lambda: OpeningRangeDayTrade(5)),
    Candidate("ORB 15 min", lambda: OpeningRangeDayTrade(15)),
    Candidate("Área de ruído + VWAP (Zarattini/Aziz/Barbon)", lambda: NoiseAreaMomentum(14)),
    Candidate("Heikin-Ashi + MME 9/21 (60/15/gatilho)", lambda: HeikinAshiTrendPullback()),
    Candidate("Teoria de Dow (60/15/gatilho)", lambda: DowTheoryDayTrade()),
    Candidate("Dow 60 min + gatilho Heikin-Ashi", lambda: DowHeikinAshi()),
    # setups ensinados por traders conhecidos (fontes nos docstrings de strategies/setups.py)
    Candidate("Larry Williams 9.1", lambda: LarryWilliams91()),
    Candidate("Larry Williams 9.1 + 60 min", lambda: LarryWilliams91(confluence=True)),
    Candidate("Larry Williams 9.2", lambda: LarryWilliams92()),
    Candidate("Larry Williams 9.2 + 60 min", lambda: LarryWilliams92(confluence=True)),
    Candidate("Larry Williams 9.3", lambda: LarryWilliams93()),
    Candidate("Larry Williams 9.3 + 60 min", lambda: LarryWilliams93(confluence=True)),
    Candidate("Stormer 123", lambda: Stormer123()),
    Candidate("Stormer 123 + 60 min", lambda: Stormer123(confluence=True)),
    Candidate("Ponto Contínuo MME21", lambda: PontoContinuo()),
    Candidate("Ponto Contínuo MME21 + 60 min", lambda: PontoContinuo(confluence=True)),
    Candidate("Falha de estrutura 2B + 15 min", lambda: StructureFailure()),
    Candidate("Fibonacci 38-62% + 60/15 min", lambda: FibonacciPullback()),
    Candidate("IFR2 Stormer + 60 min", lambda: StormerIFR2()),
]

# os mesmos setups em swing (60 min e diário), confluência com o tempo gráfico de cima
SWING_SETUPS: list[Candidate] = [
    Candidate("Larry Williams 9.1 swing", lambda: LarryWilliams91(swing=True)),
    Candidate("Larry Williams 9.1 swing + tempo de cima", lambda: LarryWilliams91(confluence=True, swing=True)),
    Candidate("Larry Williams 9.2 swing", lambda: LarryWilliams92(swing=True)),
    Candidate("Larry Williams 9.2 swing + tempo de cima", lambda: LarryWilliams92(confluence=True, swing=True)),
    Candidate("Larry Williams 9.3 swing", lambda: LarryWilliams93(swing=True)),
    Candidate("Larry Williams 9.3 swing + tempo de cima", lambda: LarryWilliams93(confluence=True, swing=True)),
    Candidate("Stormer 123 swing", lambda: Stormer123(swing=True)),
    Candidate("Stormer 123 swing + tempo de cima", lambda: Stormer123(confluence=True, swing=True)),
    Candidate("Ponto Contínuo MME21 swing", lambda: PontoContinuo(swing=True)),
    Candidate("Ponto Contínuo MME21 swing + tempo de cima", lambda: PontoContinuo(confluence=True, swing=True)),
    Candidate("Falha de estrutura 2B swing + tempo de cima", lambda: StructureFailure(swing=True)),
    Candidate("Fibonacci 38-62% swing + tempo de cima", lambda: FibonacciPullback(swing=True)),
    Candidate("IFR2 Stormer swing + tempo de cima", lambda: StormerIFR2(swing=True)),
]

# scalp em cripto (gatilho de 1 e 5 min, tempo de cima de 60 min). Custo real da Binance:
# 0,1% de taxa por lado mais 0,05% de derrapagem, cobrados pelo backtest
SCALP_SETUPS: list[Candidate] = [
    Candidate("Larry Williams 9.1 scalp + 60 min", lambda: LarryWilliams91(confluence=True, upper_minutes=60)),
    Candidate("Larry Williams 9.2 scalp + 60 min", lambda: LarryWilliams92(confluence=True, upper_minutes=60)),
    Candidate("Larry Williams 9.3 scalp + 60 min", lambda: LarryWilliams93(confluence=True, upper_minutes=60)),
    Candidate("Stormer 123 scalp + 60 min", lambda: Stormer123(confluence=True, upper_minutes=60)),
    Candidate("Ponto Contínuo MME21 scalp + 60 min", lambda: PontoContinuo(confluence=True, upper_minutes=60)),
    Candidate("Falha de estrutura 2B scalp + 60 min", lambda: StructureFailure(upper_minutes=60)),
    Candidate("Fibonacci 38-62% scalp + 60 min", lambda: FibonacciPullback(upper_minutes=60)),
    Candidate("IFR2 scalp + 60 min", lambda: StormerIFR2(upper_minutes=60)),
]

SCALP_RISK_VARIANTS: list[RiskVariant] = [
    RiskVariant("stop do gráfico, alvo 1,5x", 1.5, 1.5),
    RiskVariant("stop do gráfico, alvo 2x", 1.5, 2.0),
    RiskVariant("stop do gráfico, alvo 3x", 1.5, 3.0),
    RiskVariant("stop do gráfico, saída do setup", 1.5, 50.0),
]

def _wyckoff(suffix: str, **kw) -> list[Candidate]:
    """Os quatro gatilhos de Wyckoff da apostila (spring, spring com volume baixo, SOS+LPS e
    clímax), com e sem a confluência do tempo gráfico de cima."""
    out = []
    for conf in (False, True):
        tag = suffix + (" + tempo de cima" if conf else "")
        out += [
            Candidate(f"Wyckoff spring/upthrust{tag}", lambda c=conf: WyckoffSpring(confluence=c, **kw)),
            Candidate(f"Wyckoff spring/upthrust volume baixo{tag}", lambda c=conf: WyckoffSpring(low_volume=True, confluence=c, **kw)),
            Candidate(f"Wyckoff SOS + LPS{tag}", lambda c=conf: WyckoffSOSLPS(confluence=c, **kw)),
            Candidate(f"Wyckoff clímax SC/BC{tag}", lambda c=conf: WyckoffClimax(confluence=c, **kw)),
        ]
    return out


WYCKOFF_DAY = _wyckoff("")
WYCKOFF_SWING = _wyckoff(" swing", swing=True)
DAY_CANDIDATES += WYCKOFF_DAY
SWING_SETUPS += WYCKOFF_SWING
CANDIDATES += WYCKOFF_SWING  # criptos (1h, 4h, diário) e índices em swing

# day trade a favor das médias (pedido de 28/11/2026): MMA 200/50/20 e MME9 empilhadas nos
# tempos de contexto e candle gatilho no 2 min (montado do 1 min) partindo da MME9/MMA20
MEDIAS_ALIGN = ((60, 15, 5), (60, 15), (15, 5))
MEDIAS_DAY: list[Candidate] = [
    Candidate(MovingAverageTrend(t, a).name, lambda t=t, a=a: MovingAverageTrend(t, a), ("1min",))
    for a in MEDIAS_ALIGN
    for t in ("pc", "pfr", "engolfo", "martelo", "forca")
]
DAY_CANDIDATES += MEDIAS_DAY

# Pivô v2 do Levy (dossiê de 26/11/2026): a regra oficial dele é 2 min, camada 3, alvo 1.
# A escola também testa o gráfico de 1 min, a camada 2 (alinhado à M20) e os alvos 2 e 3,
# escolhe no treino e confirma na prova, como faz com todo mundo.
PIVO_DAY: list[Candidate] = [
    Candidate(PivotV2(alvo, camada, grafico).name, lambda a=alvo, c=camada, g=grafico: PivotV2(a, c, g), ("1min",))
    for grafico in (2, 1)
    for camada in (3, 2)
    for alvo in (1, 2, 3)
]
# o stop e o alvo vêm do gráfico (stop A e projeção de Fibonacci); o ATR só entra se faltar
PIVO_RISK_VARIANTS: list[RiskVariant] = [RiskVariant("stop A, alvo pela projeção de Fibonacci", 2.0, 2.0)]
# trader com método próprio (TraderProfile.school): só as estratégias dele vão para a prova
SCHOOL_SETS = {"pivo": (PIVO_DAY, PIVO_RISK_VARIANTS)}

# preço médio inteligente (pedido de 28/11/2026). Cada estratégia só testa o tipo que
# combina com ela: retorno à média -> preço médio para trás; tendência -> pirâmide.
SCALE_CANDIDATES: list[Candidate] = [
    Candidate("ORB 5 min (Zarattini/Aziz)", lambda: OpeningRangeDayTrade(5), None, PIRAMIDE),
    Candidate("ORB 15 min", lambda: OpeningRangeDayTrade(15), None, PIRAMIDE),
    Candidate("Área de ruído + VWAP (Zarattini/Aziz/Barbon)", lambda: NoiseAreaMomentum(14), None, PIRAMIDE),
    Candidate("Médias 60/15/5 + candle de força (2 min)", lambda: MovingAverageTrend("forca", (60, 15, 5)), ("1min",), PIRAMIDE),
    Candidate("Médias 60/15/5 + Ponto Contínuo (2 min)", lambda: MovingAverageTrend("pc", (60, 15, 5)), ("1min",), PIRAMIDE),
    Candidate("Bandas da VWAP 2 desvios", lambda: VwapBands(2.0), None, MEDIA),
    Candidate("Bandas da VWAP 2,5 desvios", lambda: VwapBands(2.5), None, MEDIA),
    Candidate("Bandas da VWAP 2 desvios + 60 min", lambda: VwapBands(2.0, trend=True), None, MEDIA),
    Candidate("IFR2 Stormer + 60 min", lambda: StormerIFR2(), None, MEDIA),
    Candidate("Fibonacci 38-62% + 60/15 min", lambda: FibonacciPullback(), None, MEDIA),
]

SCALINGS: list[Scaling] = [
    SEM_ESCALA,
    Scaling(MEDIA, 2, 0.33),
    Scaling(MEDIA, 2, 0.33, "medio", 1.0),
    Scaling(MEDIA, 3, 0.25, "medio", 1.0),
    Scaling(PIRAMIDE, 1, 1.0),
    Scaling(PIRAMIDE, 2, 0.5),
    Scaling(PIRAMIDE, 3, 1.0),
]

RISK_VARIANTS: list[RiskVariant] = [
    RiskVariant("stop 2 ATR, alvo 2x", 2.0, 2.0),
    RiskVariant("stop 3 ATR, alvo 2x", 3.0, 2.0),
    RiskVariant("stop 1,5 ATR, alvo 3x", 1.5, 3.0),
    # alvo bem distante: quem decide a saída é a própria estratégia (Turtle, Double 7s...)
    RiskVariant("stop 2 ATR, saída da estratégia", 2.0, 50.0),
]

# no day trade o stop vem do gráfico (fundo/topo do gatilho); o ATR só entra se faltar
DAY_RISK_VARIANTS: list[RiskVariant] = [
    RiskVariant("stop do gráfico, alvo 2x", 2.0, 2.0),
    RiskVariant("stop do gráfico, alvo 3x", 2.0, 3.0),
    RiskVariant("stop do gráfico, alvo 10x (artigo do ORB)", 2.0, 10.0),
    RiskVariant("stop do gráfico, saída da estratégia ou fim do dia", 2.0, 50.0),
]


@dataclass(frozen=True)
class SchoolRules:
    train_share: float = 0.7
    train_min_trades: int = 30
    train_min_profit_factor: float = 1.3
    train_max_drawdown: float = 0.15
    test_min_trades: int = 10
    test_min_profit_factor: float = 1.1


@dataclass
class Result:
    trader: TraderProfile
    timeframe: str
    candidate: str
    risk: str
    train: BacktestReport
    test: BacktestReport
    scaling: str = SEM_ESCALA.label

    def train_ok(self, rules: SchoolRules) -> bool:
        t = self.train
        return (
            t.halted_at is None
            and len(t.trades) >= rules.train_min_trades
            and t.profit_factor >= rules.train_min_profit_factor
            and t.max_drawdown_pct <= rules.train_max_drawdown
        )

    def test_ok(self, rules: SchoolRules) -> bool:
        t = self.test
        return (
            t.halted_at is None
            and len(t.trades) >= rules.test_min_trades
            and t.profit_factor >= rules.test_min_profit_factor
            and t.total_pnl > 0
        )


def _only_after(report: BacktestReport, start) -> BacktestReport:
    """Mantém só as operações abertas a partir de `start` e recalcula a queda máxima."""
    trades: list[ClosedTrade] = [t for t in report.trades if t.opened_at >= start]
    out = BacktestReport(report.trader, report.symbol, start, report.end, report.base_capital, trades, report.rejected)
    out.halted_at = report.halted_at if report.halted_at and report.halted_at >= start else None
    equity = peak = report.base_capital
    for t in trades:
        equity += t.pnl
        peak = max(peak, equity)
        out.max_drawdown_pct = max(out.max_drawdown_pct, (peak - equity) / peak)
    return out


def timeframes_for(trader: TraderProfile, base_bars: Sequence[Bar], base_tf: str) -> dict[str, list[Bar]]:
    """Gera os tempos gráficos a partir dos candles baixados."""
    bars = list(base_bars)
    if trader.asset_class is AssetClass.CRYPTO and base_tf == "1h":
        return {"1h": bars, "4h": resample(bars, 4), "1d": resample(bars, 24)}
    return {base_tf: bars}


def with_15min(series: dict[str, list[Bar]]) -> dict[str, list[Bar]]:
    """Acrescenta o gatilho de 15 minutos, montado a partir dos candles de 5 minutos."""
    from .intraday import Timeline, higher_timeframe

    out = dict(series)
    if len(series.get("5min", [])) >= 300:
        out["15min"] = higher_timeframe(Timeline.build(series["5min"]), 15).bars
    return out


def evaluate(
    trader: TraderProfile,
    series: dict[str, list[Bar]],
    rules: SchoolRules = SchoolRules(),
    candidates: Sequence[Candidate] | None = None,
    risks: Sequence[RiskVariant] | None = None,
    base_risk: RiskConfig = RiskConfig(),
    fine: Sequence[Bar] | None = None,
    slippage_pct: float | None = None,
    contract="auto",
    scalings: Sequence[Scaling] = (SEM_ESCALA,),
) -> list[Result]:
    """`fine`: candles de 1 minuto, usados por dentro dos tempos gráficos maiores para saber
    em que ordem entrada, stop e alvo aconteceram."""
    if contract == "auto":
        # day trade nos índices: sempre com microcontratos futuros (pedido de 28/11/2026)
        from .futures import MICROS

        contract = MICROS.get(trader.symbol) if trader.day_trade else None
    own = SCHOOL_SETS.get(trader.school)
    if candidates is None:
        candidates = own[0] if own else DAY_CANDIDATES if trader.day_trade else CANDIDATES
    if risks is None:
        risks = own[1] if own else DAY_RISK_VARIANTS if trader.day_trade else RISK_VARIANTS
    results = []
    for tf, bars in series.items():
        if len(bars) < 300:
            continue
        split = int(len(bars) * rules.train_share)
        train_bars = bars[:split]
        sub = fine if fine and tf != "1min" else None
        for cand in candidates:
            if cand.timeframes is not None and tf not in cand.timeframes:
                continue
            for rv in risks:
                if rv.reward_ratio >= 10 and not cand.make().has_exit:
                    continue  # sem alvo e sem regra de saída, a operação só termina no stop
                for sc in scalings:
                    if sc.active and cand.scale_kind not in (None, sc.mode):
                        continue
                    risk = replace(base_risk, atr_stop_multiple=rv.atr_stop_multiple, reward_ratio=rv.reward_ratio)
                    student = replace(trader, strategy=cand.make(), timeframe=tf, atr_stop_multiple=None, reward_ratio=None)
                    train = run_backtest(student, train_bars, risk, fine=sub, slippage_pct=slippage_pct, contract=contract, scaling=sc)
                    warmup = max(student.strategy.window, risk.atr_period + 2)
                    test_full = run_backtest(
                        replace(student, strategy=cand.make()), bars[max(0, split - warmup) :], risk,
                        fine=sub, slippage_pct=slippage_pct, contract=contract, scaling=sc,
                    )
                    test = _only_after(test_full, bars[split].ts)
                    results.append(Result(trader, tf, cand.label, rv.label, train, test, sc.label))
    return results


def pick(results: Sequence[Result], rules: SchoolRules = SchoolRules()) -> tuple[Result | None, bool]:
    """A melhor no treino entre as que passaram nele; aprovada se também passar na prova."""
    passing = [r for r in results if r.train_ok(rules)]
    if not passing:
        enough = [r for r in results if len(r.train.trades) >= rules.train_min_trades] or list(results)
        best = max(enough, key=lambda r: (r.train.profit_factor if r.train.trades else 0), default=None)
        return best, False
    best = max(passing, key=lambda r: (r.train.profit_factor, len(r.train.trades)))
    return best, best.test_ok(rules)


def _pf(value: float) -> str:
    return "∞" if value == float("inf") else f"{value:.2f}"


def report_markdown(trader: TraderProfile, results: Sequence[Result], rules: SchoolRules = SchoolRules()) -> str:
    best, approved = pick(results, rules)
    passed_train = sum(r.train_ok(rules) for r in results)
    lines = [f"### {trader.name} ({trader.symbol})", ""]
    if best is None:
        return "\n".join(lines + ["Sem dados suficientes.", ""])
    verdict = "APROVADO para paper trading" if approved else "reprovado"
    lines += [
        f"**{verdict}.** {len(results)} combinações testadas, {passed_train} passaram no treino.",
        "",
        f"Melhor no treino: **{best.candidate}**, {best.timeframe}, {best.risk}"
        + (f", **{best.scaling}**" if best.scaling != SEM_ESCALA.label else ""),
        "",
        "| Etapa | Período | Operações | Acerto | Fator de lucro | Resultado | Queda máx. | Dias com lucro | Média por dia |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, rep in (("treino", best.train), ("prova", best.test)):
        period = f"{rep.start:%Y-%m-%d} a {rep.end:%Y-%m-%d}" if rep.start and rep.end else "-"
        days = rep.daily_pnl
        per_day = sum(days.values()) / len(days) if days else 0.0
        lines.append(
            f"| {name} | {period} | {len(rep.trades)} | {rep.win_rate:.0%} | {_pf(rep.profit_factor)} | "
            f"{rep.total_pnl / rep.base_capital:+.1%} | {rep.max_drawdown_pct:.1%} | {rep.green_days:.0%} | {per_day:+.2f} |"
        )
    lines.append("")
    if best.scaling != SEM_ESCALA.label:
        plain = next(
            (r for r in results if (r.timeframe, r.candidate, r.risk, r.scaling) == (best.timeframe, best.candidate, best.risk, SEM_ESCALA.label)),
            None,
        )
        if plain is not None:
            lines += [
                f"Mesma estratégia sem preço médio: treino FL {_pf(plain.train.profit_factor)} "
                f"({plain.train.total_pnl / plain.train.base_capital:+.1%}), prova FL {_pf(plain.test.profit_factor)} "
                f"({plain.test.total_pnl / plain.test.base_capital:+.1%}).",
                "",
            ]
    return "\n".join(lines)


def current_check(trader: TraderProfile, series: dict[str, list[Bar]], rules: SchoolRules = SchoolRules(), fine=None) -> str:
    """Confere a estratégia que o trader usa hoje nos mesmos dados (treino e prova), sem
    escolher nada: serve para ver se uma aprovação antiga continua de pé."""
    import copy

    bars = series.get(trader.timeframe)
    if not bars:
        return ""
    base = RiskConfig()
    rv = RiskVariant("atual", trader.atr_stop_multiple or base.atr_stop_multiple, trader.reward_ratio or base.reward_ratio)
    cand = Candidate(trader.strategy.name, lambda: copy.deepcopy(trader.strategy))
    res = evaluate(trader, {trader.timeframe: bars}, rules, candidates=[cand], risks=[rv], fine=fine)
    if not res:
        return ""
    r = res[0]
    ok = r.train_ok(rules) and r.test_ok(rules)
    if trader.approved:
        verdict = "continua aprovada" if ok else "não passa mais"
    else:
        verdict = "aprovada" if ok else "reprovada"
    if r.train.halted_at or r.test.halted_at:
        verdict += " (parada pela trava de queda de 10%)"
    return (
        f"Estratégia atual ({trader.strategy.name}, {trader.timeframe}): **{verdict}**. "
        f"Treino: {len(r.train.trades)} operações, fator de lucro {_pf(r.train.profit_factor)}; "
        f"prova: {len(r.test.trades)} operações, fator de lucro {_pf(r.test.profit_factor)}, "
        f"{r.test.total_pnl / r.test.base_capital:+.1%}.\n"
    )
