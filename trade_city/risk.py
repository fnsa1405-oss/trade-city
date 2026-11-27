"""Guardião de Risco: transforma um sinal em plano com stop loss, stop gain e tamanho."""
from __future__ import annotations

import math
from collections.abc import Sequence

from .config import RiskConfig
from .indicators import atr
from .models import AssetClass, Bar, Side, Signal, TradePlan
from .mood import Mood


def round_qty(qty: float, asset_class: AssetClass) -> float:
    if asset_class is AssetClass.EQUITY:
        return float(math.floor(qty))  # ordens com stop na corretora exigem ações inteiras
    return math.floor(qty * 1e6) / 1e6


class Guardian:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def plan(
        self,
        signal: Signal,
        bars: Sequence[Bar],
        capital: float,
        mood: Mood,
        asset_class: AssetClass,
    ) -> tuple[TradePlan | None, str]:
        cfg = self.cfg
        volatility = atr(bars, cfg.atr_period)
        if volatility is None or volatility <= 0:
            return None, "sem histórico suficiente para medir a volatilidade"
        if signal.side is Side.SHORT and asset_class is AssetClass.CRYPTO:
            return None, "cripto à vista: só compra, sem venda a descoberto"
        entry, sign = signal.price, signal.side.sign
        if signal.stop is not None:
            # stop do gráfico (fundo/topo que invalida a ideia), com distância mínima
            # para o ruído do candle não tirar a operação
            stop_distance = (entry - signal.stop) * sign
            if stop_distance <= 0:
                return None, "o preço já passou do stop do gráfico"
            stop_distance = max(stop_distance, 0.25 * volatility, entry * 0.0005)
        else:
            stop_distance = cfg.atr_stop_multiple * volatility
        stop = entry - sign * stop_distance
        take = entry + sign * cfg.reward_ratio * stop_distance
        if stop <= 0 or take <= 0:
            return None, "stop ou alvo ficariam abaixo de zero"

        risk_budget = capital * cfg.risk_per_trade * mood.size_multiplier
        risk_budget = min(risk_budget, capital * cfg.risk_per_trade * Mood.CONFIANTE.size_multiplier)
        qty = risk_budget / stop_distance
        qty = min(qty, capital / entry)  # sem alavancagem
        qty = round_qty(qty, asset_class)
        if qty <= 0:
            return None, "capital insuficiente para o tamanho mínimo"

        if asset_class is AssetClass.EQUITY:
            stop, take = round(stop, 2), round(take, 2)
        return (
            TradePlan(
                signal=signal,
                qty=qty,
                stop_loss=stop,
                take_profit=take,
                risk_amount=qty * abs(entry - stop),
                mood=mood.label,
            ),
            f"{signal.side.value}: stop {stop:.2f}, alvo {take:.2f}, {qty:g} unidades, humor {mood.label}",
        )
