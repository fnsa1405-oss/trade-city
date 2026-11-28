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
from .strategies import (
    ConnorsRSI2,
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
    NoiseAreaMomentum,
    OpeningRangeDayTrade,
    PontoContinuo,
    Stormer123,
    StormerIFR2,
    Strategy,
    StructureFailure,
    Supertrend,
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
) -> list[Result]:
    """`fine`: candles de 1 minuto, usados por dentro dos tempos gráficos maiores para saber
    em que ordem entrada, stop e alvo aconteceram."""
    if candidates is None:
        candidates = DAY_CANDIDATES if trader.day_trade else CANDIDATES
    if risks is None:
        risks = DAY_RISK_VARIANTS if trader.day_trade else RISK_VARIANTS
    results = []
    for tf, bars in series.items():
        if len(bars) < 300:
            continue
        split = int(len(bars) * rules.train_share)
        train_bars = bars[:split]
        sub = fine if fine and tf != "1min" else None
        for cand in candidates:
            for rv in risks:
                if rv.reward_ratio >= 10 and not cand.make().has_exit:
                    continue  # sem alvo e sem regra de saída, a operação só termina no stop
                risk = replace(base_risk, atr_stop_multiple=rv.atr_stop_multiple, reward_ratio=rv.reward_ratio)
                student = replace(trader, strategy=cand.make(), timeframe=tf, atr_stop_multiple=None, reward_ratio=None)
                train = run_backtest(student, train_bars, risk, fine=sub)
                warmup = max(student.strategy.window, risk.atr_period + 2)
                test_full = run_backtest(replace(student, strategy=cand.make()), bars[max(0, split - warmup) :], risk, fine=sub)
                test = _only_after(test_full, bars[split].ts)
                results.append(Result(trader, tf, cand.label, rv.label, train, test))
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
        f"Melhor no treino: **{best.candidate}**, {best.timeframe}, {best.risk}",
        "",
        "| Etapa | Período | Operações | Acerto | Fator de lucro | Resultado | Queda máx. |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, rep in (("treino", best.train), ("prova", best.test)):
        period = f"{rep.start:%Y-%m-%d} a {rep.end:%Y-%m-%d}" if rep.start and rep.end else "-"
        lines.append(
            f"| {name} | {period} | {len(rep.trades)} | {rep.win_rate:.0%} | {_pf(rep.profit_factor)} | "
            f"{rep.total_pnl / rep.base_capital:+.1%} | {rep.max_drawdown_pct:.1%} |"
        )
    lines.append("")
    return "\n".join(lines)
