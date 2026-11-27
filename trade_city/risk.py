"""Guardião de Risco: transforma um sinal em plano com stop loss, stop gain e tamanho."""
from __future__ import annotations

import math
from collections.abc import Sequence

from .config import RiskConfig
from .indicators import atr
from .models import AssetClass, Bar, Signal, TradePlan
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
        entry = signal.price
        stop_distance = cfg.atr_stop_multiple * volatility
        stop = entry - stop_distance
        if stop <= 0:
            return None, "stop ficaria abaixo de zero"
        take = entry + cfg.reward_ratio * stop_distance

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
                risk_amount=qty * (entry - stop),
                mood=mood.label,
            ),
            f"stop {stop:.2f}, alvo {take:.2f}, {qty:g} unidades, humor {mood.label}",
        )
