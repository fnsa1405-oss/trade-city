"""Backtest: roda a mesma linha de produção sobre candles históricos."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from .auditor import AuditContext, Auditor
from .config import RiskConfig, TraderProfile, risk_for
from zoneinfo import ZoneInfo

from .models import AssetClass, Bar, ClosedTrade, Side, Signal, TradePlan
from .mood import compute_mood
from .risk import Guardian
from .stats import compute_stats, day_start


@dataclass(frozen=True)
class SchoolCriteria:
    min_profit_factor: float = 1.3
    max_drawdown_pct: float = 0.15
    min_trades: int = 100


@dataclass
class BacktestReport:
    trader: str
    symbol: str
    start: datetime | None
    end: datetime | None
    base_capital: float
    trades: list[ClosedTrade] = field(default_factory=list)
    rejected: int = 0
    max_drawdown_pct: float = 0.0
    halted_at: datetime | None = None  # quando a trava de queda mandou o trader de volta à escola

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def win_rate(self) -> float:
        return sum(t.won for t in self.trades) / len(self.trades) if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        gains = sum(t.pnl for t in self.trades if t.pnl > 0)
        losses = -sum(t.pnl for t in self.trades if t.pnl <= 0)
        if losses == 0:
            return float("inf") if gains > 0 else 0.0
        return gains / losses

    def passes(self, criteria: SchoolCriteria = SchoolCriteria()) -> tuple[bool, list[str]]:
        problems = []
        if self.halted_at:
            problems.append("parado pela trava de queda")
        if len(self.trades) < criteria.min_trades:
            problems.append(f"{len(self.trades)} operações, mínimo {criteria.min_trades}")
        if self.profit_factor < criteria.min_profit_factor:
            problems.append(f"fator de lucro {self.profit_factor:.2f}, mínimo {criteria.min_profit_factor}")
        if self.max_drawdown_pct > criteria.max_drawdown_pct:
            problems.append(f"queda máxima {self.max_drawdown_pct:.1%}, limite {criteria.max_drawdown_pct:.0%}")
        return not problems, problems

    def summary(self, criteria: SchoolCriteria = SchoolCriteria()) -> str:
        ok, problems = self.passes(criteria)
        period = f"{self.start:%Y-%m-%d} a {self.end:%Y-%m-%d}" if self.start and self.end else "sem dados"
        lines = [
            f"Backtest de {self.trader} ({self.symbol}), {period}",
            f"  operações: {len(self.trades)}  (recusadas pelo guardião/auditor: {self.rejected})",
            f"  taxa de acerto: {self.win_rate:.1%}",
            f"  fator de lucro: {self.profit_factor:.2f}",
            f"  resultado: {self.total_pnl:+.2f} ({self.total_pnl / self.base_capital:+.1%} sobre {self.base_capital:.0f})",
            f"  queda máxima: {self.max_drawdown_pct:.1%}",
        ]
        if self.halted_at:
            lines.append(f"  parado pela trava de queda em {self.halted_at:%Y-%m-%d} (o resto do período não foi operado)")
        lines += [
            "  escola: APROVADO para paper trading" if ok else "  escola: reprovado (" + "; ".join(problems) + ")",
        ]
        return "\n".join(lines)


@dataclass
class _Position:
    plan: TradePlan
    entry: float
    opened_at: datetime
    features: tuple | None = None


NY = ZoneInfo("America/New_York")

# custo por lado. Day trade em ETF líquido (SPY, QQQ...): spread de 1 centavo e
# corretagem de ~US$0,0035 por ação somam menos de 0,005%; usamos 0,01% por segurança.
DAY_TRADE_EQUITY_SLIPPAGE = 0.0001


def run_backtest(
    trader: TraderProfile,
    bars: Sequence[Bar],
    risk: RiskConfig | None = None,
    fee_pct: float | None = None,
    slippage_pct: float | None = None,
    record_features: bool = False,
    brain=None,
) -> BacktestReport:
    """Entradas no preço de abertura do candle seguinte ao sinal. Se stop e alvo cabem no mesmo
    candle, conta o stop (hipótese pessimista). Day trade nunca dorme posicionado."""
    risk = risk_for(trader, risk or RiskConfig())
    strategy = trader.strategy
    if fee_pct is None:
        fee_pct = 0.001 if trader.asset_class is AssetClass.CRYPTO else 0.0  # taxa da Binance por lado
    if slippage_pct is None:
        day_equity = strategy.day_trade and trader.asset_class is AssetClass.EQUITY
        slippage_pct = DAY_TRADE_EQUITY_SLIPPAGE if day_equity else 0.0005
    guardian, auditor = Guardian(risk), Auditor(risk)
    strategy.prepare(bars)
    report = BacktestReport(trader.name, trader.symbol, bars[0].ts if bars else None, bars[-1].ts if bars else None, trader.capital)

    pnls: list[tuple[datetime, float]] = []
    peak = equity = trader.capital
    position: _Position | None = None
    pending: TradePlan | None = None
    pending_features: tuple | None = None

    def close(pos: _Position, price: float, ts: datetime, reason: str) -> None:
        nonlocal equity, peak
        qty, side = pos.plan.qty, pos.plan.side
        pnl = (price - pos.entry) * qty * side.sign - fee_pct * (pos.entry + price) * qty
        report.trades.append(
            ClosedTrade(trader.key, trader.symbol, qty, pos.entry, price, pnl, pos.opened_at, ts, reason, side, pos.features)
        )
        pnls.append((ts, pnl))
        equity += pnl
        peak = max(peak, equity)
        report.max_drawdown_pct = max(report.max_drawdown_pct, (peak - equity) / peak)

    for i in range(len(bars)):
        bar = bars[i]
        if pending is not None:
            sign = pending.side.sign
            entry = bar.open * (1 + sign * slippage_pct)
            low, high = sorted((pending.stop_loss, pending.take_profit))
            if low < entry < high:
                position = _Position(pending, entry, bar.ts, pending_features)
            pending = None

        if position is not None:
            plan = position.plan
            long = plan.side is Side.LONG
            sign = plan.side.sign
            if strategy.day_trade and bar.ts.astimezone(NY).date() != position.opened_at.astimezone(NY).date():
                # faltou candle no fim do pregão: sai na abertura seguinte, nunca carrega a posição
                close(position, bar.open * (1 - sign * slippage_pct), bar.ts, "fim do pregão")
                position = None
            elif (bar.low <= plan.stop_loss) if long else (bar.high >= plan.stop_loss):
                worst = min(bar.open, plan.stop_loss) if long else max(bar.open, plan.stop_loss)
                close(position, worst * (1 - sign * slippage_pct), bar.ts, "stop loss")
                position = None
            elif (bar.high >= plan.take_profit) if long else (bar.low <= plan.take_profit):
                best = max(bar.open, plan.take_profit) if long else min(bar.open, plan.take_profit)
                close(position, best, bar.ts, "stop gain")
                position = None
            elif strategy.exit_signal(bars[max(0, i + 1 - strategy.window) : i + 1], plan.side):
                close(position, bar.close * (1 - sign * slippage_pct), bar.ts, "saída da estratégia")
                position = None
            if position is not None or not strategy.day_trade:
                continue  # swing: espera o próximo candle; day trade pode entrar de novo

        if i + 1 >= len(bars) or i + 1 < strategy.min_bars:
            continue
        window = bars[max(0, i + 1 - strategy.window) : i + 1]
        decision = strategy.decide(window)
        if decision is None:
            continue
        recent = bars[max(0, i - 80) : i + 1]
        if brain is not None and not brain.allows(recent, decision.side)[0]:
            continue  # o cérebro deixou passar
        today = day_start(bar.ts, risk.timezone)
        stats = compute_stats(trader.capital, [p for _, p in pnls], [p for ts, p in pnls if ts >= today])
        mood = compute_mood(stats.recent_outcomes, stats.day_pnl)
        signal = Signal(trader.key, trader.symbol, bar.close, decision.reason, bar.ts, decision.side, decision.stop)
        plan, _ = guardian.plan(signal, bars[max(0, i - risk.atr_period - 1) : i + 1], stats.capital, mood, trader.asset_class)
        if plan is None:
            report.rejected += 1
            continue
        ctx = AuditContext(
            capital=stats.capital,
            peak_capital=stats.peak_capital,
            day_losses=stats.day_losses,
            day_pnl=stats.day_pnl,
            has_open_position=False,
            buying_power=stats.capital,
        )
        audit = auditor.review(plan, ctx)
        if audit.approved:
            pending = plan
            if record_features:
                from .brain import features

                f = features(recent, decision.side)
                pending_features = tuple(f) if f else None
        elif any("escola" in r for r in audit.reasons):
            report.halted_at = bar.ts
            break
        else:
            report.rejected += 1
    return report
