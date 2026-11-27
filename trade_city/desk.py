"""A mesa: roda a linha de produção (Analista, Guardião, Auditor, Execução, Placar) para cada trader."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from .auditor import AuditContext, Auditor
from .broker import Broker
from .config import RiskConfig, TraderProfile, risk_for
from .ledger import Ledger, OpenTrade
from .models import AssetClass, Signal
from .mood import Mood, compute_mood
from .risk import Guardian
from .stats import TraderStats, compute_stats, day_start


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Desk:
    def __init__(
        self,
        traders: list[TraderProfile],
        broker: Broker,
        ledger: Ledger,
        risk: RiskConfig | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ):
        self.traders = traders
        self.broker = broker
        self.ledger = ledger
        self.risk = risk or RiskConfig()
        self.clock = clock

    # placar ---------------------------------------------------------------
    def stats(self, trader: TraderProfile) -> TraderStats:
        now = self.clock()
        return compute_stats(
            trader.capital,
            self.ledger.closed_pnls(trader.key),
            self.ledger.closed_pnls(trader.key, since=day_start(now, self.risk.timezone)),
        )

    def mood(self, stats: TraderStats) -> Mood:
        return compute_mood(stats.recent_outcomes, stats.day_pnl)

    # ciclo ----------------------------------------------------------------
    def run_once(self) -> list[str]:
        events: list[str] = []
        for trader in self.traders:
            try:
                events.extend(self._run_trader(trader))
            except Exception as exc:  # um trader com problema não derruba os outros
                events.append(f"[{trader.name}] erro: {exc}")
                self.ledger.record_decision(self.clock(), trader.key, trader.symbol, "erro", False, str(exc))
        return events

    def panic(self) -> list[str]:
        """Botão de pânico: trava a mesa e zera todas as posições abertas."""
        self.ledger.kill_switch = True
        events = ["botão de pânico acionado: mesa travada"]
        for trader in self.traders:
            trade = self.ledger.open_trade_for(trader.key)
            if trade is None:
                continue
            if self.broker.get_position(trader.symbol) is not None:
                fill = self.broker.close_position(trader.symbol)
                price = fill.price
            else:
                price = self.broker.last_exit_price(trader.symbol) or trade.entry_price
            pnl = self.ledger.close_trade(trade.id, price, self.clock(), "pânico")
            events.append(f"[{trader.name}] posição zerada, resultado {pnl:+.2f}")
        return events

    def _run_trader(self, trader: TraderProfile) -> list[str]:
        now = self.clock()
        open_trade = self.ledger.open_trade_for(trader.key)
        bars = self.broker.get_bars(trader.symbol, trader.asset_class, trader.timeframe, trader.data_lookback_days)
        if open_trade is not None:
            return self._manage(trader, open_trade, bars)
        if not bars:
            return []

        # 1. Analista: uma decisão por candle fechado
        last_key = f"last_bar:{trader.key}"
        bar_id = bars[-1].ts.isoformat()
        if self.ledger.flag(last_key) == bar_id:
            return []
        self.ledger.set_flag(last_key, bar_id)
        window = bars[-trader.strategy.window :]
        reason = trader.strategy.analyze(window)
        if reason is None:
            return []
        signal = Signal(trader.key, trader.symbol, self.broker.latest_price(trader.symbol, trader.asset_class), reason, now)
        self.ledger.record_decision(now, trader.key, trader.symbol, "analista", True, reason)
        events = [f"[{trader.name}] sinal: {reason}"]

        # 2. Guardião de Risco
        stats = self.stats(trader)
        mood = self.mood(stats)
        risk = risk_for(trader, self.risk)
        plan, detail = Guardian(risk).plan(signal, bars, stats.capital, mood, trader.asset_class)
        self.ledger.record_decision(now, trader.key, trader.symbol, "guardião", plan is not None, detail)
        if plan is None:
            return events + [f"[{trader.name}] guardião recusou: {detail}"]

        # 3. Auditor
        ctx = AuditContext(
            capital=stats.capital,
            peak_capital=stats.peak_capital,
            day_losses=stats.day_losses,
            day_pnl=stats.day_pnl,
            has_open_position=self.broker.get_position(trader.symbol) is not None,
            buying_power=self.broker.buying_power(),
            kill_switch=self.ledger.kill_switch,
            market_open=self.broker.is_market_open(trader.asset_class),
        )
        audit = Auditor(risk).review(plan, ctx)
        self.ledger.record_decision(
            now, trader.key, trader.symbol, "auditor", audit.approved, "; ".join(audit.reasons) or "aprovado"
        )
        if not audit.approved:
            return events + [f"[{trader.name}] auditor reprovou: {'; '.join(audit.reasons)}"]

        # 4. Execução
        fill = self.broker.submit_entry(plan, trader.asset_class)
        qty = fill.qty or plan.qty
        self.ledger.open_trade(
            trader.key, trader.symbol, qty, fill.price, plan.stop_loss, plan.take_profit, now, fill.order_id
        )
        mode = "paper" if self.broker.paper else "REAL"
        return events + [
            f"[{trader.name}] comprou {qty:g} {trader.symbol} a {fill.price:.2f} ({mode}), "
            f"stop {plan.stop_loss:.2f}, alvo {plan.take_profit:.2f}"
        ]

    def _manage(self, trader: TraderProfile, trade: OpenTrade, bars) -> list[str]:
        """5. Placar: acompanha a posição aberta e registra o resultado quando ela fecha."""
        now = self.clock()
        position = self.broker.get_position(trader.symbol)
        if position is None:
            # a corretora executou o stop loss ou o stop gain
            price = self.broker.last_exit_price(trader.symbol) or trade.entry_price
            reason = "stop gain" if price >= trade.take_profit else "stop loss" if price <= trade.stop_loss else "corretora"
            return [self._close(trader, trade, price, now, reason)]

        price = self.broker.latest_price(trader.symbol, trader.asset_class)
        reason = None
        if trader.asset_class is AssetClass.CRYPTO:
            if price <= trade.stop_loss:
                reason = "stop loss"
            elif price >= trade.take_profit:
                reason = "stop gain"
        if reason is None and bars and trader.strategy.should_exit(bars[-trader.strategy.window :]):
            if trader.asset_class is AssetClass.CRYPTO or self.broker.is_market_open(trader.asset_class):
                reason = "saída da estratégia"
        if reason is None:
            return []
        fill = self.broker.close_position(trader.symbol)
        return [self._close(trader, trade, fill.price, now, reason)]

    def _close(self, trader: TraderProfile, trade: OpenTrade, price: float, now: datetime, reason: str) -> str:
        pnl = self.ledger.close_trade(trade.id, price, now, reason)
        self.ledger.record_decision(now, trader.key, trader.symbol, "placar", pnl > 0, f"{reason}: {pnl:+.2f}")
        result = "vitória" if pnl > 0 else "derrota"
        return f"[{trader.name}] {result} por {reason}: {pnl:+.2f} (saída a {price:.2f})"
