"""Microcontratos futuros da CME para o day trade nos índices (padrão pedido pelo Alexandre
em 28/11/2026): MNQ (Nasdaq 100), MES (S&P 500), MYM (Dow Jones) e M2K (Russell 2000).

Os candles históricos são dos ETFs (QQQ, SPY, DIA, IWM), que andam junto com os futuros no
pregão. Para simular o contrato, o preço do ETF vira o valor em dólares de 1 contrato:
preço do ETF x (pontos do índice por US$1 do ETF) x (dólares por ponto). Assim 1 unidade
no backtest = 1 contrato, o resultado sai em dólares e o tick vira um valor fixo.

Custos por contrato e por lado: corretagem com taxas da bolsa (US$0,85, valor típico de
corretora de varejo) e 1 tick de derrapagem nas ordens a mercado e stop. Margem de day trade:
US$1.000 por contrato (conservador; muitas corretoras pedem menos).
Fonte das especificações: https://www.cmegroup.com/markets/equities/micro-e-mini-equity-futures.html
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .models import Bar


@dataclass(frozen=True)
class Micro:
    code: str
    etf: str
    ratio: float  # pontos do índice por US$1 do ETF (aproximado)
    multiplier: float  # dólares por ponto do índice
    tick: float  # menor variação, em pontos
    fee: float = 0.85  # US$ por contrato por lado
    margin: float = 1_000.0  # US$ de margem de day trade por contrato
    slip_ticks: float = 1.0

    @property
    def scale(self) -> float:
        return self.ratio * self.multiplier

    @property
    def tick_value(self) -> float:
        return self.tick * self.multiplier

    @property
    def slip_value(self) -> float:
        return self.slip_ticks * self.tick_value


MICROS: dict[str, Micro] = {
    "QQQ": Micro("MNQ", "QQQ", 41.0, 2.0, 0.25),
    "SPY": Micro("MES", "SPY", 10.0, 5.0, 0.25),
    "DIA": Micro("MYM", "DIA", 100.0, 0.5, 1.0),
    "IWM": Micro("M2K", "IWM", 10.0, 5.0, 0.1),
}


MICROS_BY_CODE: dict[str, Micro] = {m.code: m for m in MICROS.values()}


def to_contract(bars: Sequence[Bar] | None, micro: Micro) -> list[Bar] | None:
    """Candles do ETF em dólares por contrato do micro futuro."""
    if bars is None:
        return None
    k = micro.scale
    return [Bar(b.ts, b.open * k, b.high * k, b.low * k, b.close * k, b.volume) for b in bars]
