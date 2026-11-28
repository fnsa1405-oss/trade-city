"""A mesa: roda a linha de produção (Analista, Guardião, Auditor, Execução, Placar) para cada trader."""
from __future__ import annotations

from collections.abc import Callable
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .auditor import AuditContext, Auditor
from .broker import Broker
from .config import RiskConfig, TraderProfile, risk_for
from .ledger import Ledger, OpenTrade
from .models import AssetClass, Side, Signal
from .mood import Mood, compute_mood
from .risk import Guardian
from .scaling import MEDIA
from .stats import TraderStats, compute_stats, day_start


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


DAY_TRADE_FORCE_FLAT = 15 * 60 + 55  # 15h55 de Nova York


def _ny_minutes(ts: datetime) -> int:
    from .intraday import NY

    local = ts.astimezone(NY)
    return local.hour * 60 + local.minute


class Desk:
    def __init__(
        self,
        traders: list[TraderProfile],
        broker: Broker,
        ledger: Ledger,
        risk: RiskConfig | None = None,
        clock: Callable[[], datetime] = _utcnow,
        brains: dict | None = None,
    ):
        self.traders = traders
        self.brains = brains or {}  # cérebros promovidos na escola, por trader
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
            self.ledger.set_flag(f"legs:{trader.key}", "")
            events.append(f"[{trader.name}] posição zerada, resultado {pnl:+.2f}")
        return events

    def _run_trader(self, trader: TraderProfile) -> list[str]:
        now = self.clock()
        open_trade = self.ledger.open_trade_for(trader.key)
        bars = self._bars(trader)
        if open_trade is not None:
            return self._manage(trader, open_trade, bars)
        if not bars:
            return []

        # 0. ordem stop armada antes: entra se o preço romper o nível, cancela quando vence
        pend_key = f"pending:{trader.key}"
        raw = self.ledger.flag(pend_key)
        if raw:
            order = json.loads(raw)
            side = Side(order["side"])
            price = self.broker.latest_price(trader.symbol, trader.asset_class)
            if now >= datetime.fromisoformat(order["expires"]):
                self.ledger.set_flag(pend_key, "")
                self.ledger.record_decision(now, trader.key, trader.symbol, "analista", False, "ordem stop venceu sem romper")
            elif (price - order["trigger"]) * side.sign >= 0:
                self.ledger.set_flag(pend_key, "")
                signal = Signal(trader.key, trader.symbol, price, order["reason"], now, side, order["stop"], order.get("target"))
                return self._execute(trader, signal, bars, [f"[{trader.name}] rompeu {order['trigger']:.2f}: {order['reason']}"])
            else:
                return []

        # mercado fechado: o candle fica para ser analisado na abertura (como no backtest,
        # que entra na abertura do candle seguinte), em vez de ser descartado
        if trader.asset_class is not AssetClass.CRYPTO and not self.broker.is_market_open(trader.asset_class):
            return []

        # 1. Analista: uma decisão por candle fechado
        last_key = f"last_bar:{trader.key}"
        bar_id = bars[-1].ts.isoformat()
        if self.ledger.flag(last_key) == bar_id:
            return []
        self.ledger.set_flag(last_key, bar_id)
        window = bars[-trader.strategy.window :]
        trader.strategy.prepare(window)
        decision = trader.strategy.decide(window)
        if decision is None:
            return []
        reason = decision.reason
        brain = self.brains.get(trader.key)
        if brain is not None and brain.promoted:
            ok, p = brain.allows(bars[-81:], decision.side)
            detail = f"chance estimada {p:.0%}, mínimo {brain.threshold:.0%}" if p is not None else "sem histórico para avaliar"
            self.ledger.record_decision(now, trader.key, trader.symbol, "cérebro", ok, detail)
            if not ok:
                return [f"[{trader.name}] cérebro deixou passar: {reason} ({detail})"]
            reason = f"{reason} (cérebro: {detail})"
        self.ledger.record_decision(now, trader.key, trader.symbol, "analista", True, reason)
        events = [f"[{trader.name}] sinal: {reason}"]
        if decision.trigger is not None:
            step = bars[-1].ts - bars[-2].ts if len(bars) > 1 else timedelta(minutes=5)
            expires = bars[-1].ts + step * (1 + decision.valid_bars)
            order = {"side": decision.side.value, "trigger": decision.trigger, "stop": decision.stop, "target": decision.target, "reason": reason, "expires": expires.isoformat()}
            self.ledger.set_flag(pend_key, json.dumps(order))
            verb = "compra acima de" if decision.side is Side.LONG else "venda abaixo de"
            return events + [f"[{trader.name}] ordem stop armada: {verb} {decision.trigger:.2f}"]
        price = self.broker.latest_price(trader.symbol, trader.asset_class)
        signal = Signal(trader.key, trader.symbol, price, reason, now, decision.side, decision.stop, decision.target)
        return self._execute(trader, signal, bars, events)

    def _execute(self, trader: TraderProfile, signal: Signal, bars, events: list[str]) -> list[str]:
        """2. Guardião, 3. Auditor e 4. Execução."""
        now = self.clock()

        # 2. Guardião de Risco
        stats = self.stats(trader)
        mood = self.mood(stats)
        risk = risk_for(trader, self.risk)
        micro = self.broker.contract_for(trader.symbol)
        margin = micro.margin if micro is not None else None
        plan, detail = Guardian(risk).plan(signal, bars, stats.capital, mood, trader.asset_class, unit_margin=margin)
        self.ledger.record_decision(now, trader.key, trader.symbol, "guardião", plan is not None, detail)
        if plan is None:
            return events + [f"[{trader.name}] guardião recusou: {detail}"]
        legs_state = None
        sc = trader.scaling
        if sc is not None and sc.active:
            # preço médio/pirâmide: pernas menores e risco total fixo (scaling.py)
            dist = abs(plan.entry - plan.stop_loss)
            integer = micro is not None or trader.asset_class is AssetClass.EQUITY
            unit, adds = sc.size(plan.qty, integer, dist, stats.capital * risk.max_contract_risk, stats.capital, margin)
            plan = replace(plan, qty=unit, risk_amount=unit * dist * sc.risk_factor(adds))
            if adds:
                legs_state = {"unit": unit, "dist": dist, "levels": sc.levels(plan.entry, dist, plan.side.sign, adds)}

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
            asset_class=trader.asset_class,
            **self._portfolio_risk(trader),
            unit_margin=margin,
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
            trader.key, trader.symbol, qty, fill.price, plan.stop_loss, plan.take_profit, now, fill.order_id, plan.side
        )
        self.ledger.set_flag(f"legs:{trader.key}", json.dumps(legs_state) if legs_state else "")
        mode = "simulado" if self.broker.paper else "REAL"
        verb = "comprou" if plan.side is Side.LONG else "vendeu a descoberto"
        what = f"{micro.code} (microcontrato)" if micro is not None else trader.symbol
        if legs_state:
            kind = "preço médio" if sc.mode == MEDIA else "pirâmide"
            levels = ", ".join(f"{x:.2f}" for x in legs_state["levels"])
            events.append(f"[{trader.name}] {kind} armado: entradas extras em {levels}")
        return events + [
            f"[{trader.name}] {verb} {qty:g} {what} a {fill.price:.2f} ({mode}), "
            f"stop {plan.stop_loss:.2f}, alvo {plan.take_profit:.2f}"
        ]

    def _bars(self, trader: TraderProfile):
        """Candles do trader. Estratégia de fluxo em cripto: candles da Binance com o volume de
        agressão (o mesmo dado da escola de fluxo); se falhar, os candles da corretora."""
        if getattr(trader.strategy, "uses_flow", False) and trader.asset_class is AssetClass.CRYPTO:
            try:
                from .orderflow import live_flow_bars

                bars = live_flow_bars(trader.symbol, trader.timeframe, max(trader.strategy.window + 50, 300))
                if bars:
                    return bars
            except Exception:
                pass
        return self.broker.get_bars(trader.symbol, trader.asset_class, trader.timeframe, trader.data_lookback_days)

    def _portfolio_risk(self, trader: TraderProfile) -> dict:
        """Risco aberto (até o stop) de toda a mesa e do grupo correlacionado do trader."""
        total = group = 0.0
        for other in self.traders:
            trade = self.ledger.open_trade_for(other.key)
            if trade is None:
                continue
            risk = abs(trade.entry_price - trade.stop_loss) * trade.qty
            total += risk
            if trader.group and other.group == trader.group:
                group += risk
        capital = sum(t.capital for t in self.traders)
        return {"portfolio_capital": capital, "portfolio_open_risk": total, "group_open_risk": group}

    def _manage(self, trader: TraderProfile, trade: OpenTrade, bars) -> list[str]:
        """5. Placar: acompanha a posição aberta e registra o resultado quando ela fecha."""
        now = self.clock()
        position = self.broker.get_position(trader.symbol)
        if position is None:
            # a corretora executou o stop loss ou o stop gain
            price = self.broker.last_exit_price(trader.symbol) or trade.entry_price
            sign = trade.side.sign
            if (price - trade.take_profit) * sign >= 0:
                reason = "stop gain"
            elif (price - trade.stop_loss) * sign <= 0:
                reason = "stop loss"
            else:
                reason = "corretora"
            return [self._close(trader, trade, price, now, reason)]

        price = self.broker.latest_price(trader.symbol, trader.asset_class)
        sign = trade.side.sign
        events = self._scale(trader, trade, price)
        if events:
            trade = self.ledger.open_trade_for(trader.key) or trade
        reason = None
        if trader.strategy.day_trade and _ny_minutes(now) >= DAY_TRADE_FORCE_FLAT:
            reason = "fim do pregão"  # rede de segurança: day trade nunca dorme posicionado
        if trader.asset_class is AssetClass.CRYPTO:
            if (price - trade.stop_loss) * sign <= 0:
                reason = "stop loss"
            elif (price - trade.take_profit) * sign >= 0:
                reason = "stop gain"
        if reason is None and bars:
            window = bars[-trader.strategy.window :]
            trader.strategy.prepare(window)
            if trader.strategy.exit_signal(window, trade.side):
                if trader.asset_class is AssetClass.CRYPTO or self.broker.is_market_open(trader.asset_class):
                    reason = "saída da estratégia"
        if reason is None:
            return events
        fill = self.broker.close_position(trader.symbol)
        return events + [self._close(trader, trade, fill.price, now, reason)]

    def _scale(self, trader: TraderProfile, trade: OpenTrade, price: float) -> list[str]:
        """Entradas extras do preço médio ou da pirâmide, nos níveis marcados na entrada."""
        raw = self.ledger.flag(f"legs:{trader.key}")
        sc = trader.scaling
        if not raw or sc is None or not sc.active or not hasattr(self.broker, "add_to_position"):
            return []
        st = json.loads(raw)
        levels = st.get("levels") or []
        if not levels:
            return []
        sign = trade.side.sign
        against = sc.mode == MEDIA
        moved = (price - levels[0]) * sign
        if (moved > 0) if against else (moved < 0):
            return []  # o preço ainda não chegou no próximo nível
        unit, dist = st["unit"], st["dist"]
        fill = self.broker.add_to_position(trader.symbol, unit)
        qty = trade.qty + unit
        avg = (trade.entry_price * trade.qty + fill.price * unit) / qty
        stop, target = trade.stop_loss, trade.take_profit
        if against:
            if sc.target == "medio":
                target = avg + sign * sc.target_r * dist
        else:
            # pirâmide: stop da posição inteira onde a perda total = risco da 1ª perna (nunca recua)
            new = avg - sign * unit * dist / qty
            stop = max(stop, new) if sign > 0 else min(stop, new)
        self.broker.set_stops(trader.symbol, stop, target)
        self.ledger.scale_trade(trade.id, qty, avg, stop, target)
        st["levels"] = levels[1:]
        self.ledger.set_flag(f"legs:{trader.key}", json.dumps(st))
        kind = "preço médio" if against else "pirâmide"
        self.ledger.record_decision(self.clock(), trader.key, trader.symbol, kind, True, f"+{unit:g} a {fill.price:.2f}")
        return [
            f"[{trader.name}] {kind}: +{unit:g} a {fill.price:.2f}; "
            f"agora {qty:g} a {avg:.2f}, stop {stop:.2f}, alvo {target:.2f}"
        ]

    def _close(self, trader: TraderProfile, trade: OpenTrade, price: float, now: datetime, reason: str) -> str:
        pnl = self.ledger.close_trade(trade.id, price, now, reason)
        self.ledger.set_flag(f"legs:{trader.key}", "")
        self.ledger.record_decision(now, trader.key, trader.symbol, "placar", pnl > 0, f"{reason}: {pnl:+.2f}")
        result = "vitória" if pnl > 0 else "derrota"
        return f"[{trader.name}] {result} por {reason}: {pnl:+.2f} (saída a {price:.2f})"
