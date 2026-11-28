"""Backtest: roda a mesma linha de produção sobre candles históricos."""
from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from .auditor import AuditContext, Auditor
from .config import RiskConfig, TraderProfile, risk_for
from zoneinfo import ZoneInfo

from .models import AssetClass, Bar, ClosedTrade, Side, Signal, TradePlan
from .mood import compute_mood
from .risk import Guardian
from .scaling import SEM_ESCALA, Legs, Scaling
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
    def daily_pnl(self) -> dict:
        """Resultado de cada dia com operação (data de Nova York)."""
        out: dict = {}
        for t in self.trades:
            d = t.closed_at.astimezone(NY).date()
            out[d] = out.get(d, 0.0) + t.pnl
        return out

    @property
    def green_days(self) -> float:
        days = self.daily_pnl
        return sum(v > 0 for v in days.values()) / len(days) if days else 0.0

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
    first_entry: float
    opened_at: datetime
    features: tuple | None = None
    legs: Legs | None = None

    def __post_init__(self):
        plan = self.plan
        if self.legs is None:
            self.legs = Legs(SEM_ESCALA, plan.side.sign, plan.qty, plan.stop_loss, plan.take_profit, abs(plan.entry - plan.stop_loss))
        if not self.legs.fills:
            self.legs.fills.append((self.first_entry, self.legs.unit))

    @property
    def entry(self) -> float:
        return self.legs.avg

    @property
    def qty(self) -> float:
        return self.legs.qty


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
    fine: Sequence[Bar] | None = None,
    contract=None,
    scaling: Scaling | None = None,
) -> BacktestReport:
    """Entradas no preço de abertura do candle seguinte ao sinal. Se stop e alvo cabem no mesmo
    candle, conta o stop (hipótese pessimista). Day trade nunca dorme posicionado.

    `contract`: microcontrato futuro (futures.Micro). Os candles do ETF viram dólares por
    contrato, a quantidade é inteira (contratos), a derrapagem é de 1 tick e a corretagem é
    cobrada por contrato.

    `scaling`: preço médio para trás ou pirâmide (scaling.py). As entradas extras são ordens
    em níveis marcados na largada, conferidas minuto a minuto; o stop é um só para a posição
    inteira e o tamanho das pernas mantém o risco total fixo.

    `fine`: candles de 1 minuto do mesmo período. Com eles, entrada por ordem stop, stop e alvo
    são conferidos minuto a minuto dentro de cada candle, na ordem em que aconteceram."""
    risk = risk_for(trader, risk or RiskConfig())
    strategy = trader.strategy
    if fee_pct is None:
        fee_pct = 0.001 if trader.asset_class is AssetClass.CRYPTO else 0.0  # taxa da Binance por lado
    if slippage_pct is None:
        day_equity = strategy.day_trade and trader.asset_class is AssetClass.EQUITY
        slippage_pct = DAY_TRADE_EQUITY_SLIPPAGE if day_equity else 0.0005
    slip_abs = fee_abs = 0.0
    unit_margin = None
    if contract is not None:
        from .futures import to_contract

        bars, fine = to_contract(bars, contract), to_contract(fine, contract)
        slippage_pct, fee_pct = 0.0, 0.0
        slip_abs, fee_abs, unit_margin = contract.slip_value, contract.fee, contract.margin

    def fill_in(price: float, sign: int) -> float:
        return price * (1 + sign * slippage_pct) + sign * slip_abs

    def fill_out(price: float, sign: int) -> float:
        return price * (1 - sign * slippage_pct) - sign * slip_abs

    integer = contract is not None or trader.asset_class is AssetClass.EQUITY
    scale_info: dict[int, tuple[float, int]] = {}  # id do plano -> (tamanho da perna, entradas extras)

    def scale_plan(plan: TradePlan, capital: float) -> TradePlan:
        dist = abs(plan.entry - plan.stop_loss)
        unit, adds = scaling.size(plan.qty, integer, dist, capital * risk.max_contract_risk, capital, unit_margin)
        total_risk = unit * dist * scaling.risk_factor(adds)
        new = replace(plan, qty=unit, risk_amount=total_risk)
        scale_info[id(new)] = (unit, adds)
        return new

    def make_legs(plan: TradePlan, entry: float) -> Legs:
        sign = plan.side.sign
        dist = abs(plan.entry - plan.stop_loss)
        unit, adds = scale_info.pop(id(plan), (plan.qty, 0))
        sc = scaling if scaling is not None and adds > 0 else SEM_ESCALA
        # níveis medidos a partir do preço planejado, para não depender da derrapagem
        legs = Legs(sc, sign, unit, plan.stop_loss, plan.take_profit, dist, sc.levels(plan.entry, dist, sign, adds))
        return legs

    guardian, auditor = Guardian(risk), Auditor(risk)
    strategy.prepare(bars)
    report = BacktestReport(trader.name, trader.symbol, bars[0].ts if bars else None, bars[-1].ts if bars else None, trader.capital)

    pnls: list[tuple[datetime, float]] = []
    peak = equity = trader.capital
    position: _Position | None = None
    pending: TradePlan | None = None
    pending_features: tuple | None = None
    pending_trigger: float | None = None  # ordem stop: entra só se o preço passar deste nível
    pending_until = -1  # último candle em que a ordem stop vale

    def close(pos: _Position, price: float, ts: datetime, reason: str) -> None:
        nonlocal equity, peak
        qty, side = pos.qty, pos.plan.side
        # taxa sobre o valor de cada perna na entrada (média x quantidade) e na saída
        pnl = (price - pos.entry) * qty * side.sign - fee_pct * (pos.entry + price) * qty - 2 * fee_abs * qty
        report.trades.append(
            ClosedTrade(trader.key, trader.symbol, qty, pos.entry, price, pnl, pos.opened_at, ts, reason, side, pos.features, pos.legs.adds)
        )
        pnls.append((ts, pnl))
        equity += pnl
        peak = max(peak, equity)
        report.max_drawdown_pct = max(report.max_drawdown_pct, (peak - equity) / peak)

    fine_ts = [b.ts for b in fine] if fine else []
    step = (bars[1].ts - bars[0].ts) if len(bars) > 1 else None

    def path(i: int) -> list[Bar]:
        """Os candles de 1 minuto dentro do candle i, em ordem (ou o próprio candle, sem eles)."""
        if not fine:
            return [bars[i]]
        end_ts = bars[i + 1].ts if i + 1 < len(bars) else bars[i].ts + step
        if step is not None:
            end_ts = min(end_ts, bars[i].ts + step)
        lo, hi = bisect_left(fine_ts, bars[i].ts), bisect_left(fine_ts, end_ts)
        return list(fine[lo:hi]) or [bars[i]]

    for i in range(len(bars)):
        bar = bars[i]
        subs = path(i)
        first = 0  # primeiro minuto em que a posição já existe
        fill_k = None  # minuto da entrada por ordem stop: não dá para saber o que veio antes dentro dele
        if pending is not None:
            sign = pending.side.sign
            low, high = sorted((pending.stop_loss, pending.take_profit))
            if pending_trigger is None:  # ordem a mercado na abertura
                entry = fill_in(bar.open, sign)
                if low < entry < high:
                    position = _Position(pending, entry, bar.ts, pending_features, make_legs(pending, entry))
                pending = None
            else:
                long_order = pending.side is Side.LONG
                same_day = not strategy.day_trade or bar.ts.astimezone(NY).date() == pending.signal.ts.astimezone(NY).date()
                k_hit = None
                if same_day:
                    for k, sb in enumerate(subs):
                        if (sb.high >= pending_trigger) if long_order else (sb.low <= pending_trigger):
                            k_hit = k
                            break
                if k_hit is not None:
                    sb = subs[k_hit]
                    base = max(sb.open, pending_trigger) if long_order else min(sb.open, pending_trigger)
                    entry = fill_in(base, sign)
                    if low < entry < high:
                        position = _Position(pending, entry, sb.ts, pending_features, make_legs(pending, entry))
                        first = fill_k = k_hit
                    pending = None
                elif not same_day or i >= pending_until:
                    pending = None  # ordem stop venceu sem ser acionada

        if position is not None:
            plan = position.plan
            legs = position.legs
            long = plan.side is Side.LONG
            sign = plan.side.sign
            if strategy.day_trade and bar.ts.astimezone(NY).date() != position.opened_at.astimezone(NY).date():
                # faltou candle no fim do pregão: sai na abertura seguinte, nunca carrega a posição
                close(position, fill_out(bar.open, sign), bar.ts, "fim do pregão")
                position = None
            else:
                for k in range(first, len(subs)):
                    sb = subs[k]
                    added = False
                    while k != fill_k and legs.touched(sb.low, sb.high):
                        # entrada extra: ordem no nível marcado (pior entre ele e a abertura)
                        lvl = legs.next_level()
                        against = legs.scaling.mode == "media"
                        base = (min(sb.open, lvl) if long else max(sb.open, lvl)) if against else (max(sb.open, lvl) if long else min(sb.open, lvl))
                        legs.add(fill_in(base, sign))
                        added = True
                    stop, target = legs.stop, legs.target
                    if (sb.low <= stop) if long else (sb.high >= stop):
                        worst = min(sb.open, stop) if long else max(sb.open, stop)
                        if k == fill_k or added:
                            worst = stop  # a abertura veio antes da entrada; sai no stop
                        close(position, fill_out(worst, sign), sb.ts, "stop loss")
                        position = None
                        break
                    if k == fill_k or added:
                        continue  # no minuto de uma entrada, o alvo não conta (pessimista)
                    if (sb.high >= target) if long else (sb.low <= target):
                        best = max(sb.open, target) if long else min(sb.open, target)
                        close(position, best, sb.ts, "stop gain")
                        position = None
                        break
                if position is not None and strategy.exit_signal(bars[max(0, i + 1 - strategy.window) : i + 1], plan.side):
                    close(position, fill_out(bar.close, sign), bar.ts, "saída da estratégia")
                    position = None
            if position is not None or not strategy.day_trade:
                continue  # swing: espera o próximo candle; day trade pode entrar de novo

        if pending is not None or i + 1 >= len(bars) or i + 1 < strategy.min_bars:
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
        price = decision.trigger if decision.trigger is not None else bar.close
        signal = Signal(trader.key, trader.symbol, price, decision.reason, bar.ts, decision.side, decision.stop, decision.target)
        plan, _ = guardian.plan(signal, bars[max(0, i - risk.atr_period - 1) : i + 1], stats.capital, mood, trader.asset_class, unit_margin=unit_margin)
        if plan is None:
            report.rejected += 1
            continue
        if scaling is not None and scaling.active:
            plan = scale_plan(plan, stats.capital)
        ctx = AuditContext(
            capital=stats.capital,
            peak_capital=stats.peak_capital,
            day_losses=stats.day_losses,
            day_pnl=stats.day_pnl,
            has_open_position=False,
            buying_power=stats.capital,
            unit_margin=unit_margin,
            asset_class=trader.asset_class,
        )
        audit = auditor.review(plan, ctx)
        if audit.approved:
            pending = plan
            pending_trigger = decision.trigger
            pending_until = i + decision.valid_bars
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
