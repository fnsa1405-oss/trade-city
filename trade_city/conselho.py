"""Conselho de consultores da Trade City.

Cinco consultores, cada um *inspirado* no que é público sobre uma referência do mercado
quantitativo (livros, artigos, documentação). Nenhum deles é, fala por ou representa
essas pessoas ou empresas: são personagens nossos, com o método que elas tornaram público.

Uma vez por semana (workflow Conselho) eles revisam a mesa com os dados mais recentes:

- Íris Valente (inspirada na Renaissance Technologies / Jim Simons): qualidade dos dados e
  se o resultado de cada trader é estatisticamente sólido ou pode ser sorte.
- Otto Barreto (inspirado em Two Sigma, Citadel e D.E. Shaw): risco da carteira inteira,
  correlação entre os traders e exposição a fatores.
- Heitor Mendes (inspirado nos livros de Ernest P. Chan): regime de cada ativo (tendência ou
  reversão), meia-vida, Kelly e custo de transação.
- Lia Furtado (inspirada nos projetos abertos TradingAgents e AI Hedge Fund): debate entre
  um pesquisador touro e um urso antes de cada entrada.
- Rafa Lemos (inspirado no QuantConnect / LEAN): robustez de parâmetros, prova de avanço
  (walk-forward) e excesso de testes (overfitting).

Regras do conselho:
1. Toda proposta de estratégia passa pela escola, com as mesmas regras e o mesmo custo.
   A escolha entre a atual e a proposta é feita só no treino; a prova só confirma.
2. O conselho nunca afrouxa travas de risco, nunca liga dinheiro real e nunca muda a mesa
   sozinho: ele recomenda, e a troca é feita depois, com o relatório na mão.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from statistics import NormalDist

from .backtest import BacktestReport, run_backtest
from .config import RiskConfig, TraderProfile, risk_for
from .models import AssetClass, Bar, ClosedTrade

OK, ATENCAO, ALERTA = "ok", "atenção", "alerta"


@dataclass(frozen=True)
class Advisor:
    key: str
    name: str
    inspired_by: str
    role: str
    look: str  # aparência no escritório 3D
    gender: str  # "a" ou "o", para o texto ("inspirada", "inspirado")
    principles: tuple[str, ...]
    sources: tuple[str, ...]


ADVISORS: tuple[Advisor, ...] = (
    Advisor(
        key="iris",
        gender="a",
        name="Íris Valente",
        inspired_by="Renaissance Technologies e Jim Simons",
        role="Estatística e qualidade dos dados",
        look="matemática de óculos, cabelo grisalho preso, cardigã azul-marinho",
        principles=(
            "Dados limpos antes de tudo: buracos, duplicatas e preços absurdos estragam qualquer modelo.",
            "Uma vantagem pequena, repetida muitas vezes, vale mais que um palpite grande: a firma lucraria em pouco mais de 50% das operações.",
            "Só confiar no que é estatisticamente significativo e descontar quantas combinações foram testadas.",
            "Muitos sinais fracos e diferentes, combinados, em vez de um sinal só.",
            "Nunca passar por cima do modelo na emoção; mudar só com pesquisa.",
        ),
        sources=(
            "Gregory Zuckerman, The Man Who Solved the Market (2019)",
            "Bailey e López de Prado, The Deflated Sharpe Ratio (Journal of Portfolio Management, 2014)",
            "https://en.wikipedia.org/wiki/Renaissance_Technologies",
            "https://medium.com/swlh/the-data-science-behind-the-man-who-solved-the-market-1398ed6ed35e",
        ),
    ),
    Advisor(
        key="otto",
        gender="o",
        name="Otto Barreto",
        inspired_by="Two Sigma, Citadel e D.E. Shaw",
        role="Risco da carteira e diversificação",
        look="gestor de risco alto, terno cinza sem gravata, tablet na mão",
        principles=(
            "O risco é da carteira inteira, não de cada trader: posições correlacionadas são a mesma aposta.",
            "Medir a exposição a poucos fatores independentes (ortogonais), como ações e cripto.",
            "Contar as apostas de verdade (número efetivo de apostas), não o número de traders.",
            "Dar menos risco a quem repete a aposta de outro; nunca dar mais risco do que as travas permitem.",
            "Engenharia e dados como base: tudo medido, registrado e reproduzível.",
        ),
        sources=(
            "Two Sigma, Introducing the Two Sigma Factor Lens (2018): https://www.twosigma.com/articles/introducing-the-two-sigma-factor-lens/",
            "Choueifaty e Coignard, Toward Maximum Diversification (Journal of Portfolio Management, 2008)",
            "Meucci, Managing Diversification (Risk, 2009)",
        ),
    ),
    Advisor(
        key="heitor",
        gender="o",
        name="Heitor Mendes",
        inspired_by="Ernest P. Chan (livros Quantitative Trading, Algorithmic Trading e Machine Trading)",
        role="Regime do mercado, custos e tamanho da posição",
        look="professor de camisa social clara com mangas dobradas, caderno de anotações",
        principles=(
            "Estratégia simples primeiro; desconfiar de backtest bonito demais.",
            "Testar se o ativo tende a seguir tendência ou voltar à média (expoente de Hurst, teste ADF, meia-vida).",
            "Usar a meia-vida de reversão como janela, em vez de escolher o parâmetro pelo resultado.",
            "Custo de transação e derrapagem decidem se a estratégia sobrevive.",
            "Tamanho pela fórmula de Kelly, sempre usando no máximo meio Kelly.",
            "Cuidado com olhar o futuro (look-ahead), viés de sobrevivência e mudança de regime.",
        ),
        sources=(
            "Ernest P. Chan, Quantitative Trading (Wiley, 2008; 2ª ed. 2021)",
            "Ernest P. Chan, Algorithmic Trading: Winning Strategies and Their Rationale (Wiley, 2013)",
            "Ernest P. Chan, Machine Trading (Wiley, 2017)",
        ),
    ),
    Advisor(
        key="lia",
        gender="a",
        name="Lia Furtado",
        inspired_by="projetos abertos TradingAgents (Tauric Research) e AI Hedge Fund (virattt)",
        role="Debate touro contra urso e revisão da linha de produção",
        look="pesquisadora jovem de blazer verde-oliva, notebook aberto, fone no pescoço",
        principles=(
            "Uma equipe de agentes com papéis claros: analistas, pesquisadores, trader, risco e gestor.",
            "Antes de comprar, um pesquisador touro e um urso debatem; quem argumenta melhor vence.",
            "Os agentes trocam relatórios estruturados, não conversa solta, para não perder informação.",
            "Gestor de risco e gestor da carteira têm a palavra final e podem vetar.",
            "Tudo é educacional e testado em simulação antes de qualquer dinheiro real.",
        ),
        sources=(
            "Xiao, Sun, Luo e Wang, TradingAgents: Multi-Agents LLM Financial Trading Framework (arXiv 2412.20138, 2024)",
            "https://github.com/TauricResearch/TradingAgents",
            "https://github.com/virattt/ai-hedge-fund",
        ),
    ),
    Advisor(
        key="rafa",
        gender="o",
        name="Rafa Lemos",
        inspired_by="QuantConnect e o motor LEAN",
        role="Robustez dos testes e engenharia do backtest",
        look="engenheiro de moletom cinza e tênis, dois monitores, caneca de café",
        principles=(
            "Hipótese primeiro: causa e efeito antes de rodar o teste.",
            "Contar os testes: 0 a 30 provavelmente sem excesso de ajuste, 30 a 70 talvez, mais de 70 provavelmente.",
            "Poucos parâmetros (até 10) e resultado que se mantém quando os parâmetros mudam um pouco (platô, não pico).",
            "Prova de avanço (walk-forward): escolher com o passado, conferir no período seguinte, várias vezes.",
            "Modelar a realidade: preenchimento, derrapagem, taxas e o mesmo código no teste e na mesa.",
        ),
        sources=(
            "QuantConnect, Research Guide: https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/research-guide",
            "Bailey, Borwein, López de Prado e Zhu, The Probability of Backtest Overfitting (2015)",
            "https://github.com/QuantConnect/Lean",
        ),
    ),
)


@dataclass
class Finding:
    level: str
    text: str
    trader: str | None = None


@dataclass
class Proposal:
    trader: str
    title: str
    status: str  # "recomendada", "reserva", "reprovada", "sem dados"
    detail: str


@dataclass
class Opinion:
    advisor: Advisor
    findings: list[Finding] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    speech: str = ""  # fala curta para o balão no escritório 3D


@dataclass
class Dossier:
    """O que o conselho recebe de cada trader: os candles do tempo gráfico dele e o
    backtest da estratégia atual no histórico inteiro."""

    trader: TraderProfile
    bars: list[Bar]
    report: BacktestReport | None = None


# --------------------------------------------------------------------------- contas


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _pf(trades: Sequence[ClosedTrade]) -> float:
    gains = sum(t.pnl for t in trades if t.pnl > 0)
    losses = -sum(t.pnl for t in trades if t.pnl <= 0)
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _fmt_pf(v: float) -> str:
    return "∞" if v == float("inf") else f"{v:.2f}"


def trade_returns(report: BacktestReport) -> list[float]:
    return [t.pnl / report.base_capital for t in report.trades]


def deflated_sharpe(returns: Sequence[float], trials: int) -> tuple[float, float, float]:
    """Sharpe por operação, o Sharpe que o melhor de `trials` testes daria por puro acaso e a
    probabilidade de o Sharpe verdadeiro ser maior que esse (Deflated Sharpe Ratio de
    Bailey e López de Prado, 2014). Devolve (sharpe, sharpe_do_acaso, probabilidade)."""
    n = len(returns)
    if n < 3:
        return 0.0, 0.0, 0.0
    sd = _std(returns)
    if sd == 0:
        return 0.0, 0.0, 0.0
    m = _mean(returns)
    sr = m / sd
    z = [(r - m) / sd for r in returns]
    skew = _mean([x**3 for x in z])
    kurt = _mean([x**4 for x in z])
    nd = NormalDist()
    trials = max(1, trials)
    if trials == 1:
        sr0 = 0.0
    else:
        gamma = 0.5772156649
        v = 1.0 / (n - 1)  # variância do Sharpe estimado quando não há vantagem nenhuma
        sr0 = math.sqrt(v) * ((1 - gamma) * nd.inv_cdf(1 - 1 / trials) + gamma * nd.inv_cdf(1 - 1 / (trials * math.e)))
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    if denom <= 0:
        return sr, sr0, 0.0
    return sr, sr0, nd.cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(denom))


def data_quality(bars: Sequence[Bar], asset_class: AssetClass) -> dict:
    """Buracos, duplicatas, candles impossíveis e saltos absurdos de preço."""
    out = {"candles": len(bars), "buracos": 0, "duplicados": 0, "impossíveis": 0, "saltos": 0}
    if len(bars) < 3:
        return out
    steps = sorted((bars[i].ts - bars[i - 1].ts).total_seconds() for i in range(1, len(bars)))
    step = steps[len(steps) // 2]
    # ações não negociam no fim de semana nem nos feriados: só conta buraco acima de 4 dias
    limit = step * 1.5 if asset_class is AssetClass.CRYPTO else max(step * 1.5, 4 * 86400)
    for i in range(1, len(bars)):
        gap = (bars[i].ts - bars[i - 1].ts).total_seconds()
        if gap <= 0:
            out["duplicados"] += 1
        elif gap > limit:
            out["buracos"] += 1
    out["impossíveis"] = sum(1 for b in bars if min(b.open, b.high, b.low, b.close) <= 0 or b.high < max(b.open, b.close, b.low) or b.low > min(b.open, b.close))
    rets = [math.log(bars[i].close / bars[i - 1].close) for i in range(1, len(bars)) if bars[i - 1].close > 0 and bars[i].close > 0]
    if len(rets) > 20:
        med = sorted(rets)[len(rets) // 2]
        mad = sorted(abs(r - med) for r in rets)[len(rets) // 2] * 1.4826
        if mad > 0:
            out["saltos"] = sum(1 for r in rets if abs(r - med) / mad > 15)
    return out


def hurst(closes: Sequence[float], max_lag: int = 100) -> float | None:
    """Expoente de Hurst pela variância das diferenças: ~0,5 passeio aleatório, acima de 0,5
    tendência, abaixo de 0,5 reversão à média (Chan, Algorithmic Trading, cap. 2)."""
    logs = [math.log(c) for c in closes if c > 0]
    max_lag = min(max_lag, len(logs) // 4)
    if max_lag < 4:
        return None
    pts = []
    for lag in range(2, max_lag):
        diffs = [logs[i] - logs[i - lag] for i in range(lag, len(logs))]
        sd = _std(diffs)
        if sd > 0:
            pts.append((math.log(lag), math.log(sd)))
    if len(pts) < 3:
        return None
    mx, my = _mean([p[0] for p in pts]), _mean([p[1] for p in pts])
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx if sxx else None


def half_life(closes: Sequence[float]) -> tuple[float, float]:
    """Meia-vida da reversão (regressão de Ornstein-Uhlenbeck: Δy = a + b·y anterior) e a
    estatística t de b, que é o teste ADF simples. Meia-vida infinita = não reverte."""
    y = [math.log(c) for c in closes if c > 0]
    if len(y) < 30:
        return math.inf, 0.0
    x, d = y[:-1], [y[i] - y[i - 1] for i in range(1, len(y))]
    mx, md = _mean(x), _mean(d)
    sxx = sum((v - mx) ** 2 for v in x)
    if sxx == 0:
        return math.inf, 0.0
    b = sum((x[i] - mx) * (d[i] - md) for i in range(len(x))) / sxx
    a = md - b * mx
    resid = [d[i] - a - b * x[i] for i in range(len(x))]
    se = math.sqrt(sum(r * r for r in resid) / (len(x) - 2) / sxx)
    t = b / se if se else 0.0
    return (-math.log(2) / b if b < 0 else math.inf), t


def kelly_multiple(returns: Sequence[float]) -> float:
    """Kelly para apostas repetidas: f* = média / variância dos retornos por operação. Como
    os retornos já vêm com o risco atual (0,5% por operação), f* diz quantas vezes o tamanho
    atual seria o Kelly cheio."""
    if len(returns) < 10:
        return 0.0
    var = _std(returns) ** 2
    return _mean(returns) / var if var > 0 else 0.0


def daily_returns(bars: Sequence[Bar]) -> dict:
    """Retorno (log) por dia UTC, a partir do último fechamento de cada dia."""
    last: dict = {}
    for b in bars:
        last[b.ts.date()] = b.close
    days = sorted(last)
    return {days[i]: math.log(last[days[i]] / last[days[i - 1]]) for i in range(1, len(days)) if last[days[i - 1]] > 0}


def correlation(a: dict, b: dict, min_days: int = 60) -> float | None:
    common = sorted(set(a) & set(b))
    if len(common) < min_days:
        return None
    xa, xb = [a[d] for d in common], [b[d] for d in common]
    sa, sb = _std(xa), _std(xb)
    if sa == 0 or sb == 0:
        return None
    ma, mb = _mean(xa), _mean(xb)
    return sum((xa[i] - ma) * (xb[i] - mb) for i in range(len(common))) / ((len(common) - 1) * sa * sb)


def effective_bets(matrix: Sequence[Sequence[float]]) -> float:
    """Número efetivo de apostas: (soma dos autovalores)² / soma dos quadrados (Meucci).
    n traders independentes = n; todos iguais = 1."""
    import numpy as np

    m = np.array(matrix, dtype=float)
    if m.size == 0:
        return 0.0
    eig = np.clip(np.linalg.eigvalsh(m), 0, None)
    return float(eig.sum() ** 2 / (eig**2).sum()) if (eig**2).sum() > 0 else 0.0


def portfolio_curve(reports: dict[str, BacktestReport], weights: dict[str, float], start=None) -> tuple[float, float]:
    """Resultado total e queda máxima (em dólares) da carteira somando as operações de cada
    trader, fechadas a partir de `start`, com o tamanho multiplicado pelo peso."""
    events = []
    for key, rep in reports.items():
        w = weights.get(key, 1.0)
        events += [(t.closed_at, t.pnl * w) for t in rep.trades if start is None or t.opened_at >= start]
    events.sort(key=lambda e: e[0])
    equity = peak = dd = 0.0
    for _, pnl in events:
        equity += pnl
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    return equity, dd


def _bt(trader: TraderProfile, bars, risk: RiskConfig | None = None, **kw) -> BacktestReport:
    """Backtest igual ao da escola: day trade de índices sempre em microcontratos."""
    if trader.day_trade and "contract" not in kw:
        from .futures import MICROS

        kw["contract"] = MICROS.get(trader.symbol)
    return run_backtest(trader, bars, risk or RiskConfig(), **kw)


def trials_for(trader: TraderProfile) -> int:
    """Quantas combinações a escola testou até escolher a estratégia deste trader."""
    from .school import CANDIDATES, DAY_CANDIDATES, DAY_RISK_VARIANTS, RISK_VARIANTS, SWING_SETUPS

    if trader.day_trade:
        pairs = sum(1 for c in DAY_CANDIDATES for rv in DAY_RISK_VARIANTS if not (rv.reward_ratio >= 10 and not c.make().has_exit))
        return pairs * 3  # gatilho de 1, 5 e 15 min
    if trader.asset_class is AssetClass.CRYPTO:
        cands, tfs = CANDIDATES, 3
    else:
        cands, tfs = CANDIDATES + SWING_SETUPS, 2
    pairs = sum(1 for c in cands for rv in RISK_VARIANTS if not (rv.reward_ratio >= 10 and not c.make().has_exit))
    return pairs * tfs


def neighbors(trader: TraderProfile) -> list[tuple[str, TraderProfile]]:
    """A estratégia atual e vizinhas com parâmetros um pouco diferentes (e stops 1,5 e 2,5 ATR)."""
    from .strategies import DonchianEnsemble, TimeSeriesMomentum, TurtleBreakout

    s = trader.strategy
    out: list[tuple[str, TraderProfile]] = [("atual", trader)]
    variants = []
    if isinstance(s, TurtleBreakout):
        e, x = s.entry_n, s.exit_n
        for fe, fx in ((0.75, 0.75), (1.25, 1.25), (1.5, 1.5), (1.0, 0.5), (1.0, 1.5)):
            ne, nx = max(2, round(e * fe)), max(2, round(x * fx))
            variants.append((f"Turtle {ne}/{nx}", TurtleBreakout(ne, nx)))
    elif isinstance(s, TimeSeriesMomentum):
        for f in (0.5, 0.75, 1.25, 1.5):
            n = max(3, round(s.n * f))
            variants.append((f"momento {n}", TimeSeriesMomentum(n)))
    elif isinstance(s, DonchianEnsemble):
        for f in (0.75, 1.25):
            lbs = tuple(max(2, round(n * f)) for n in s.lookbacks)
            variants.append((f"canais x{f:g}", DonchianEnsemble(lbs, s.majority)))
        for maj in (0.4, 0.6):
            variants.append((f"maioria {maj:.0%}", DonchianEnsemble(s.lookbacks, maj)))
    for label, strat in variants:
        out.append((label, replace(trader, strategy=strat)))
    base = trader.atr_stop_multiple or RiskConfig().atr_stop_multiple
    for m in (base * 0.75, base * 1.25):
        out.append((f"stop {m:g} ATR", replace(trader, strategy=copy.deepcopy(s), atr_stop_multiple=m)))
    return out


def walk_forward(runs: dict[str, BacktestReport], start, end, folds: int = 5, min_trades: int = 5) -> tuple[list[ClosedTrade], list[str]]:
    """Prova de avanço ancorada: em cada etapa escolhe, só com o passado, a vizinha de maior
    fator de lucro e usa as operações dela no bloco seguinte. Aproveita os backtests feitos
    no histórico inteiro (as estratégias não olham o futuro)."""
    span = (end - start) / folds
    oos: list[ClosedTrade] = []
    chosen: list[str] = []
    for k in range(1, folds):
        cut, nxt = start + span * k, start + span * (k + 1)
        best, best_pf = None, -1.0
        for label, rep in runs.items():
            past = [t for t in rep.trades if t.opened_at < cut]
            if len(past) < min_trades:
                continue
            pf = _pf(past)
            pf = 99.0 if pf == float("inf") else pf
            if pf > best_pf:
                best, best_pf = label, pf
        if best is None:
            continue
        chosen.append(best)
        oos += [t for t in runs[best].trades if cut <= t.opened_at < nxt]
    return oos, chosen


def periods(report: BacktestReport, start, end, n: int = 5) -> list[float]:
    span = (end - start) / n
    return [sum(t.pnl for t in report.trades if start + span * k <= t.opened_at < start + span * (k + 1)) for k in range(n)]


def school_duel(trader: TraderProfile, bars: Sequence[Bar], proposal, label: str) -> Proposal:
    """Atual contra proposta, nas regras da escola (treino 70%, prova 30%, custo real).
    Recomendada só se passar no treino e na prova E vencer a atual no treino."""
    from .school import Candidate, RiskVariant, SchoolRules, evaluate

    rules = SchoolRules()
    base = RiskConfig()
    rv = RiskVariant("atual", trader.atr_stop_multiple or base.atr_stop_multiple, trader.reward_ratio or base.reward_ratio)
    cur = Candidate("atual", lambda: copy.deepcopy(trader.strategy))
    new = Candidate(label, proposal)
    res = evaluate(trader, {trader.timeframe: list(bars)}, rules, candidates=[cur, new], risks=[rv])
    if len(res) < 2:
        return Proposal(trader.key, label, "sem dados", "histórico curto demais para a escola")
    a, p = res
    detail = (
        f"treino: proposta FL {_fmt_pf(p.train.profit_factor)} em {len(p.train.trades)} op. contra a atual FL "
        f"{_fmt_pf(a.train.profit_factor)} em {len(a.train.trades)} op.; prova: proposta FL {_fmt_pf(p.test.profit_factor)}, "
        f"{p.test.total_pnl / p.test.base_capital:+.1%} em {len(p.test.trades)} op. (atual FL {_fmt_pf(a.test.profit_factor)}, "
        f"{a.test.total_pnl / a.test.base_capital:+.1%})"
    )
    passed = p.train_ok(rules) and p.test_ok(rules)
    if not passed:
        return Proposal(trader.key, label, "reprovada", detail)
    better = (p.train.profit_factor, len(p.train.trades)) > (a.train.profit_factor, len(a.train.trades))
    return Proposal(trader.key, label, "recomendada" if better else "reserva", detail)


# --------------------------------------------------------------------------- consultores


def review_iris(dossiers: Sequence[Dossier]) -> Opinion:
    from .strategies.conselho import WeakSignalVote

    op = Opinion(ADVISORS[0])
    weakest = None
    for d in dossiers:
        q = data_quality(d.bars, d.trader.asset_class)
        bad = q["duplicados"] + q["impossíveis"]
        if bad or q["buracos"] > 0.01 * q["candles"] or q["saltos"] > 0.005 * q["candles"]:
            op.findings.append(Finding(ATENCAO if not bad else ALERTA, f"dados de {d.trader.symbol} ({d.trader.timeframe}): {q['candles']} candles, {q['buracos']} buracos, {q['duplicados']} duplicados, {q['impossíveis']} impossíveis, {q['saltos']} saltos fora do normal", d.trader.key))
        else:
            op.findings.append(Finding(OK, f"dados de {d.trader.symbol} ({d.trader.timeframe}) limpos: {q['candles']} candles, {q['buracos']} buracos, {q['saltos']} movimentos extremos (reais, como quedas de crise)", d.trader.key))
        if d.report is None:
            continue
        rets = trade_returns(d.report)
        n = trials_for(d.trader)
        if len(rets) < 10:
            op.findings.append(Finding(ATENCAO, f"{d.trader.name}: só {len(rets)} operações no histórico que o conselho consegue baixar ({len(d.bars)} candles). Pouco para medir; quem decide é a escola dele.", d.trader.key))
            continue
        sr, sr0, prob = deflated_sharpe(rets, n)
        level = OK if prob >= 0.95 else ATENCAO if prob >= 0.5 else ALERTA
        op.findings.append(Finding(
            level,
            f"{d.trader.name}: {len(rets)} operações no histórico, acerto {d.report.win_rate:.0%}. Sharpe por operação {sr:.2f}; "
            f"o melhor de {n} testes daria {sr0:.2f} só por sorte. Chance de a vantagem ser real: {prob:.0%}.",
            d.trader.key,
        ))
        if weakest is None or prob < weakest[1]:
            weakest = (d.trader.name, prob, len(rets))
        if not d.trader.day_trade:  # as propostas são de swing; o day trade tem escola própria
            op.proposals.append(school_duel(d.trader, d.bars, lambda: WeakSignalVote(), "Votação de sinais fracos"))
    if weakest:
        op.speech = f"A vantagem de {weakest[0]} ainda pode ser sorte ({weakest[1]:.0%} de confiança, {weakest[2]} operações)." if weakest[1] < 0.95 else "Os números dos traders estão estatisticamente sólidos."
    return op


def review_otto(dossiers: Sequence[Dossier], factors: dict[str, list[Bar]]) -> Opinion:
    op = Opinion(ADVISORS[1])
    rets = {d.trader.key: daily_returns(d.bars[-2000:]) for d in dossiers}
    # últimos 365 dias de calendário
    for key, r in rets.items():
        if r:
            last = max(r)
            rets[key] = {k: v for k, v in r.items() if (last - k).days <= 365}
    names = {d.trader.key: d.trader.name for d in dossiers}
    short = [k for k, r in rets.items() if len(r) < 60]
    if short:
        op.findings.append(Finding(ATENCAO, f"{', '.join(names[k] for k in short)}: menos de 60 dias de histórico baixado, ficam fora da conta de correlação.", None))
    keys = [k for k in rets if k not in short]
    matrix = [[1.0 if a == b else (correlation(rets[a], rets[b]) or 0.0) for b in keys] for a in keys]
    eff = effective_bets(matrix) if keys else 0.0
    if keys:
        op.findings.append(Finding(ATENCAO if eff < len(keys) / 2 else OK, f"{len(keys)} traders na mesa, mas só {eff:.1f} apostas independentes de verdade (correlação dos retornos diários do último ano).", None))
    groups, seen = [], set()
    for i, a in enumerate(keys):
        if a in seen:
            continue
        grp = [a] + [b for j, b in enumerate(keys) if j != i and b not in seen and matrix[i][j] >= 0.7]
        seen.update(grp)
        if len(grp) > 1:
            groups.append(grp)
            avg = _mean([matrix[keys.index(x)][keys.index(y)] for x in grp for y in grp if x != y])
            op.findings.append(Finding(ALERTA if len(grp) >= 3 else ATENCAO, f"{', '.join(names[k] for k in grp)} fazem praticamente a mesma aposta (correlação média {avg:.2f}). Se um perde, os outros tendem a perder junto.", None))
    # lente de fatores: ações (SPY) e cripto (BTC, sem a parte explicada pelas ações)
    spy = daily_returns(factors.get("SPY", []))
    btc = daily_returns(factors.get("BTC/USD", []))
    if spy and btc:
        common = set(spy) & set(btc)
        b_on_s = _beta({d: btc[d] for d in common}, spy)
        btc_orth = {d: btc[d] - b_on_s * spy[d] for d in common}
        for key in keys:
            bs = _beta(rets[key], spy)
            bc = _beta(rets[key], btc_orth)
            op.findings.append(Finding(OK, f"{names[key]}: exposição a ações {bs:+.2f}, a cripto (além das ações) {bc:+.2f}", key))
    # pesos de risco: menos risco para quem repete a aposta de outro (nunca mais que 1)
    raw = {k: 1 / math.sqrt(sum(max(matrix[i][j], 0.0) for j in range(len(keys)))) for i, k in enumerate(keys)}
    top = max(raw.values()) if raw else 1.0
    weights = {k: round(v / top, 2) for k, v in raw.items()}
    reports = {d.trader.key: d.report for d in dossiers if d.report is not None}
    if reports and weights:
        start = max(r.start for r in reports.values() if r.start)
        eq_pnl, eq_dd = portfolio_curve(reports, {}, start)
        w_pnl, w_dd = portfolio_curve(reports, weights, start)
        eq_ratio = eq_pnl / eq_dd if eq_dd else 0.0
        w_ratio = w_pnl / w_dd if w_dd else 0.0
        detail = (
            "pesos " + ", ".join(f"{names[k]} {w:.2f}" for k, w in weights.items())
            + f". Carteira desde {start:%d/%m/%Y}: pesos iguais {eq_pnl:+,.0f} com queda máxima {eq_dd:,.0f} (razão {eq_ratio:.2f}); "
            f"com os pesos {w_pnl:+,.0f}, queda {w_dd:,.0f} (razão {w_ratio:.2f})."
        )
        status = "melhorou" if w_ratio > eq_ratio * 1.05 else "não melhorou"
        op.proposals.append(Proposal("carteira", "Peso de risco por correlação", status, detail))
    op.speech = (f"Temos {len(keys)} traders, mas só {eff:.1f} apostas de verdade." if keys else "Sem traders na mesa.")
    return op


def _beta(y: dict, x: dict) -> float:
    common = sorted(set(y) & set(x))
    if len(common) < 30:
        return 0.0
    xs, ys = [x[d] for d in common], [y[d] for d in common]
    mx, my = _mean(xs), _mean(ys)
    sxx = sum((v - mx) ** 2 for v in xs)
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(len(xs))) / sxx if sxx else 0.0


TREND_WORDS = ("Turtle", "Donchian", "Momento", "tendência", "Supertrend")


def review_heitor(dossiers: Sequence[Dossier]) -> Opinion:
    from .strategies.conselho import ZScoreReversion

    op = Opinion(ADVISORS[2])
    notes = []
    for d in dossiers:
        closes = [b.close for b in d.bars[-1500:]]
        h = hurst(closes)
        hl, t = half_life(closes)
        regime = "tendência" if h and h > 0.55 else "reversão à média" if h and h < 0.45 else "quase aleatório"
        is_trend = any(w in d.trader.strategy.name for w in TREND_WORDS)
        mismatch = is_trend and h is not None and h < 0.45
        hl_txt = "não reverte" if hl == math.inf else f"{hl:.0f} candles"
        op.findings.append(Finding(
            ALERTA if mismatch else OK,
            f"{d.trader.symbol} ({d.trader.timeframe}): Hurst {h:.2f} ({regime}), meia-vida {hl_txt}, teste ADF t={t:.1f} "
            f"({'reverte com confiança' if t < -2.86 else 'sem reversão confiável'})."
            + (" A estratégia é de tendência e o ativo está revertendo: atenção." if mismatch else ""),
            d.trader.key,
        ))
        if d.report is not None and d.report.trades:
            k = kelly_multiple(trade_returns(d.report))
            if k > 0:
                kt = f"{k:.1f}x" if k < 10 else "mais de 10x"
                op.findings.append(Finding(OK, f"{d.trader.name}: o Kelly cheio seria {kt} o tamanho atual. Seguimos no tamanho atual, bem abaixo de meio Kelly.", d.trader.key))
            else:
                stop = f" (o histórico parou na trava de queda em {d.report.halted_at:%d/%m/%Y})" if d.report.halted_at else ""
                op.findings.append(Finding(ALERTA, f"{d.trader.name}: Kelly negativo, a média das operações no histórico é negativa{stop}.", d.trader.key))
            fee = 0.002 if d.trader.asset_class is AssetClass.CRYPTO else 0.0
            stress = _bt(replace(d.trader, strategy=copy.deepcopy(d.trader.strategy)), d.bars, fee_pct=fee, slippage_pct=0.0015)
            pf0, pf1 = d.report.profit_factor, stress.profit_factor
            level = OK if pf1 >= 1.1 and stress.total_pnl > 0 else ALERTA
            op.findings.append(Finding(level, f"{d.trader.name} com custo dobrado e derrapagem triplicada: fator de lucro {_fmt_pf(pf0)} → {_fmt_pf(pf1)}.", d.trader.key))
            if level == ALERTA:
                notes.append(d.trader.name)
        lookback = 20 if hl == math.inf else min(60, max(5, round(hl)))
        if not d.trader.day_trade:  # as propostas são de swing; o day trade tem escola própria
            op.proposals.append(school_duel(d.trader, d.bars, lambda n=lookback: ZScoreReversion(n, 2.0), f"Reversão por z-score ({lookback} candles)"))
    op.speech = f"O lucro de {', '.join(notes)} some se o custo subir." if notes else "Os traders aguentam custo dobrado. Seguimos com menos de meio Kelly."
    return op


def review_lia(dossiers: Sequence[Dossier]) -> Opinion:
    from .strategies.conselho import BearFilter, bear_case, bull_case

    op = Opinion(ADVISORS[3])
    op.findings.append(Finding(OK, "Linha de produção comparada ao TradingAgents: analista (sim), pesquisadores touro e urso (agora com o debate da Lia), trader (sim), equipe de risco (Guardião e Auditor), gestor com veto (botão de pânico e trava de queda).", None))
    op.findings.append(Finding(ATENCAO, "Falta um analista de notícias e sentimento. Fica como pendência: precisa de uma fonte gratuita com histórico longo para passar pela escola.", None))
    bears = 0
    for d in dossiers:
        if len(d.bars) < 210 or d.trader.day_trade:
            continue
        bull = bull_case(d.bars)
        bear = bear_case(d.bars)[-1]
        winner = "touro" if len(bull) > len(bear) else "urso" if len(bear) > len(bull) else "empate"
        bears += winner == "urso"
        op.findings.append(Finding(
            ALERTA if len(bear) >= 3 else OK,
            f"Debate de {d.trader.name} agora: touro ({len(bull)}) {'; '.join(bull) or 'nenhum argumento'}. Urso ({len(bear)}) {'; '.join(bear) or 'nenhum argumento'}. Vence: {winner}.",
            d.trader.key,
        ))
        strat = d.trader.strategy
        if not d.trader.day_trade:  # as propostas são de swing; o day trade tem escola própria
            op.proposals.append(school_duel(d.trader, d.bars, lambda s=strat: BearFilter(copy.deepcopy(s), 3), "Veto do urso (3+ argumentos contra)"))
    op.speech = f"O urso está vencendo o debate em {bears} de {len(dossiers)} ativos." if bears else "O touro vence o debate na maioria dos ativos."
    return op


def review_rafa(dossiers: Sequence[Dossier]) -> Opinion:
    op = Opinion(ADVISORS[4])
    fragile = []
    for d in dossiers:
        n = trials_for(d.trader)
        level = OK if n <= 30 else ATENCAO if n <= 70 else ALERTA
        op.findings.append(Finding(level, f"{d.trader.name}: a escola testou {n} combinações até escolher (guia do QuantConnect: acima de 70 provavelmente há excesso de ajuste). Por isso a prova e a prova de avanço contam mais que o treino.", d.trader.key))
        if d.report is None or not d.report.start:
            continue
        runs = {}
        for label, prof in neighbors(d.trader):
            runs[label] = d.report if label == "atual" else _bt(prof, d.bars)
        good = [k for k, r in runs.items() if r.profit_factor >= 1.1 and r.total_pnl > 0]
        share = len(good) / len(runs)
        worst = min(runs.items(), key=lambda kv: kv[1].profit_factor if kv[1].trades else 0)
        op.findings.append(Finding(
            OK if share >= 0.75 else ATENCAO if share >= 0.5 else ALERTA,
            f"{d.trader.name}: {len(good)} de {len(runs)} vizinhas (parâmetros um pouco diferentes) continuam lucrativas, "
            f"{'é um platô' if share >= 0.75 else 'é um pico estreito'}. Pior vizinha: {worst[0]}, FL {_fmt_pf(worst[1].profit_factor)}.",
            d.trader.key,
        ))
        start, end = d.report.start, d.report.end
        oos, chosen = walk_forward(runs, start, end)
        if oos:
            pf = _pf(oos)
            pnl = sum(t.pnl for t in oos)
            op.findings.append(Finding(
                OK if pf >= 1.1 and pnl > 0 else ALERTA,
                f"{d.trader.name}, prova de avanço (4 etapas, escolhendo só com o passado): {len(oos)} operações fora da amostra, FL {_fmt_pf(pf)}, {pnl / d.report.base_capital:+.1%}. Escolhas: {', '.join(chosen)}.",
                d.trader.key,
            ))
        per = periods(d.report, start, end)
        pos = sum(p > 0 for p in per)
        op.findings.append(Finding(OK if pos >= 4 else ATENCAO if pos >= 3 else ALERTA, f"{d.trader.name}: lucro em {pos} de 5 períodos do histórico ({', '.join(f'{p / d.report.base_capital:+.0%}' for p in per)}).", d.trader.key))
        if share < 0.75 or pos < 3:
            fragile.append(d.trader.name)
        if d.report.halted_at:
            op.findings.append(Finding(ALERTA, f"{d.trader.name}: no histórico inteiro a trava de queda de 10% foi acionada em {d.report.halted_at:%d/%m/%Y}.", d.trader.key))
    op.speech = f"{', '.join(fragile)} {'dependem' if len(fragile) > 1 else 'depende'} demais dos parâmetros exatos ou do período." if fragile else "As estratégias aguentam mudar um pouco os parâmetros."
    return op


def convene(dossiers: Sequence[Dossier], factors: dict[str, list[Bar]] | None = None) -> list[Opinion]:
    """Reunião do conselho: cada consultor revisa e propõe. Um consultor com erro não
    derruba os outros."""
    out = []
    for fn in (review_iris, lambda d: review_otto(d, factors or {}), review_heitor, review_lia, review_rafa):
        try:
            out.append(fn(dossiers))
        except Exception as exc:  # pragma: no cover - proteção da rodada semanal
            idx = len(out)
            out.append(Opinion(ADVISORS[idx], [Finding(ALERTA, f"erro na revisão: {exc}")], speech="Não consegui terminar a revisão desta semana."))
    return out


# --------------------------------------------------------------------------- relatório


ICON = {OK: "🟢", ATENCAO: "🟡", ALERTA: "🔴"}
STATUS = {
    "recomendada": "RECOMENDADA (passou na escola e venceu a atual no treino)",
    "reserva": "na reserva (passou na escola, mas a atual é melhor no treino)",
    "reprovada": "reprovada na escola",
    "sem dados": "sem dados",
    "melhorou": "RECOMENDADA (melhorou a razão resultado/queda da carteira em mais de 5%)",
    "não melhorou": "não melhorou a carteira o bastante (fica em observação)",
}


def report_markdown(opinions: Sequence[Opinion], when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    lines = [
        "## Conselho de consultores",
        "",
        f"Revisão de {when:%d/%m/%Y %H:%M} UTC. Os consultores são personagens da Trade City *inspirados* no que é público "
        "sobre cada referência; não são, nem falam por, essas pessoas ou empresas. Nenhuma proposta entra na mesa sem passar "
        "pela escola, e o conselho nunca mexe nas travas de risco nem em dinheiro real.",
        "",
    ]
    rec = [(o.advisor, p) for o in opinions for p in o.proposals if p.status in ("recomendada", "melhorou")]
    lines += ["### Resumo", ""]
    lines += [f"- **{o.advisor.name}**: {o.speech}" for o in opinions]
    lines.append(f"- Propostas recomendadas nesta revisão: **{len(rec)}**" + (": " + "; ".join(f"{p.title} para {p.trader} ({a.name})" for a, p in rec) if rec else "."))
    lines.append("")
    for o in opinions:
        a = o.advisor
        lines += [f"### {a.name}: {a.role}", "", f"*Inspirad{a.gender} em: {a.inspired_by}.*", ""]
        lines += [f"- {ICON.get(f.level, '')} {f.text}" for f in o.findings]
        if o.proposals:
            lines += ["", "| Proposta | Para | Situação | Detalhe |", "| --- | --- | --- | --- |"]
            lines += [f"| {p.title} | {p.trader} | {STATUS.get(p.status, p.status)} | {p.detail} |" for p in o.proposals]
        lines.append("")
    return "\n".join(lines)


def report_json(opinions: Sequence[Opinion], when: datetime | None = None) -> dict:
    when = when or datetime.now(timezone.utc)
    return {
        "gerado_em": when.isoformat(timespec="seconds"),
        "aviso": "Personagens inspirados no que é público sobre cada referência; não são essas pessoas ou empresas.",
        "conselheiros": [
            {
                "chave": o.advisor.key,
                "nome": o.advisor.name,
                "inspirado_em": o.advisor.inspired_by,
                "papel": o.advisor.role,
                "visual": o.advisor.look,
                "principios": list(o.advisor.principles),
                "fontes": list(o.advisor.sources),
                "fala": o.speech,
                "achados": [asdict(f) for f in o.findings],
                "propostas": [asdict(p) for p in o.proposals],
                "alertas": sum(f.level == ALERTA for f in o.findings),
            }
            for o in opinions
        ],
    }


def build_dossiers(traders: Sequence[TraderProfile], fetch) -> list[Dossier]:
    """`fetch(trader)` devolve os candles do tempo gráfico do trader (histórico longo)."""
    out = []
    for t in traders:
        bars = fetch(t)
        if not bars:
            continue
        report = _bt(replace(t, strategy=copy.deepcopy(t.strategy)), bars) if len(bars) > 300 else None
        out.append(Dossier(t, bars, report))
    return out
