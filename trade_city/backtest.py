"""Backtest: roda a mesma linha de produção sobre candles históricos."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from .auditor import AuditContext, Auditor
from .config import RiskConfig, TraderProfile
from .models import AssetClass, Bar, ClosedTrade, Signal, TradePlan
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


def run_backtest(
    trader: TraderProfile,
    bars: Sequence[Bar],
    risk: RiskConfig | None = None,
    fee_pct: float | None = None,
    slippage_pct: float = 0.0005,
) -> BacktestReport:
    """Entradas no preço de abertura do candle seguinte ao sinal. Se stop e alvo cabem no mesmo
    candle, conta o stop (hipótese pessimista)."""
    risk = risk or RiskConfig()
    if fee_pct is None:
        fee_pct = 0.001 if trader.asset_class is AssetClass.CRYPTO else 0.0  # taxa da Binance por lado
    guardian, auditor = Guardian(risk), Auditor(risk)
    strategy = trader.strategy
    report = BacktestReport(trader.name, trader.symbol, bars[0].ts if bars else None, bars[-1].ts if bars else None, trader.capital)

    pnls: list[tuple[datetime, float]] = []
    peak = equity = trader.capital
    position: _Position | None = None
    pending: TradePlan | None = None

    def close(pos: _Position, price: float, ts: datetime, reason: str) -> None:
        nonlocal equity, peak
        qty = pos.plan.qty
        pnl = (price - pos.entry) * qty - fee_pct * (pos.entry + price) * qty
        report.trades.append(ClosedTrade(trader.key, trader.symbol, qty, pos.entry, price, pnl, pos.opened_at, ts, reason))
        pnls.append((ts, pnl))
        equity += pnl
        peak = max(peak, equity)
        report.max_drawdown_pct = max(report.max_drawdown_pct, (peak - equity) / peak)

    for i in range(len(bars)):
        bar = bars[i]
        if pending is not None:
            entry = bar.open * (1 + slippage_pct)
            if pending.stop_loss < entry < pending.take_profit:
                position = _Position(pending, entry, bar.ts)
            pending = None

        if position is not None:
            plan = position.plan
            if bar.low <= plan.stop_loss:
                close(position, min(bar.open, plan.stop_loss) * (1 - slippage_pct), bar.ts, "stop loss")
                position = None
            elif bar.high >= plan.take_profit:
                close(position, max(bar.open, plan.take_profit), bar.ts, "stop gain")
                position = None
            elif strategy.should_exit(bars[max(0, i + 1 - strategy.window) : i + 1]):
                close(position, bar.close * (1 - slippage_pct), bar.ts, "saída da estratégia")
                position = None
            continue

        if i + 1 >= len(bars) or i + 1 < strategy.min_bars:
            continue
        window = bars[max(0, i + 1 - strategy.window) : i + 1]
        reason = strategy.analyze(window)
        if reason is None:
            continue
        today = day_start(bar.ts, risk.timezone)
        stats = compute_stats(trader.capital, [p for _, p in pnls], [p for ts, p in pnls if ts >= today])
        mood = compute_mood(stats.recent_outcomes, stats.day_pnl)
        signal = Signal(trader.key, trader.symbol, bar.close, reason, bar.ts)
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
        elif any("escola" in r for r in audit.reasons):
            report.halted_at = bar.ts
            break
        else:
            report.rejected += 1
    return report
