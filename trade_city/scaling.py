"""Preço médio inteligente (pedido do Alexandre em 28/11/2026), para trás e para frente.

Para trás ("média"): a ideia dá entrada e o preço vai um pouco contra antes de virar. Em
vez de usar um stop curto, a posição é dividida em pernas: a 1ª entra no sinal e as outras
só entram se o preço for contra até níveis marcados ANTES (frações do caminho até o stop).
Três travas impedem o preço médio de virar a "martingale" que quebra contas:
  1. número máximo de entradas, definido na largada;
  2. um stop único para a posição inteira, que nunca sai do lugar;
  3. o tamanho de cada perna é calculado para que, se TODAS entrarem e o stop for
     atingido, a perda total seja o mesmo risco fixo de uma operação comum (0,5% do capital).
Funciona em estratégias de retorno à média (bandas da VWAP, IFR2, Fibonacci), onde ir
contra um pouco é parte do plano. Em rompimentos, ir contra é sinal de erro: lá não se usa.

Para frente ("pirâmide"): a operação deu certo e o preço andou a favor; a cada nível
(frações do risco inicial R) entra mais uma perna do mesmo tamanho e o stop da posição
inteira sobe até o ponto em que a perda total nunca passa do risco inicial. Ou seja, quem
paga a nova perna é o lucro já conquistado. É o que Jesse Livermore e os Turtles faziam
(Curtis Faith, "Way of the Turtle", 2007: até 4 unidades, uma a cada 1/2 N a favor).
Funciona em estratégias de tendência e rompimento (ORB, médias, área de ruído).

Fontes: Van K. Tharp, "Trade Your Way to Financial Freedom" (2006), cap. sobre tamanho de
posição; Curtis Faith, "Way of the Turtle" (2007); Larry Connors e Cesar Alvarez, "High
Probability ETF Trading" (2009), que testam compras em escala ("scale-in") no IFR2 com
número fixo de entradas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

NONE, MEDIA, PIRAMIDE = "nenhum", "media", "piramide"


@dataclass(frozen=True)
class Scaling:
    mode: str = NONE
    max_adds: int = 0  # entradas extras além da primeira
    step: float = 0.5  # distância entre entradas, em frações do risco inicial R
    target: str = "original"  # média: "medio" = alvo refeito a partir do preço médio
    target_r: float = 1.0  # alvo "medio": preço médio + target_r x R

    def __post_init__(self):
        if self.mode == MEDIA and self.step * self.max_adds >= 0.95:
            raise ValueError("as entradas do preço médio precisam ficar antes do stop")

    @property
    def active(self) -> bool:
        return self.mode != NONE and self.max_adds > 0

    @property
    def label(self) -> str:
        if not self.active:
            return "sem preço médio"
        step = f"{self.step:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        if self.mode == MEDIA:
            alvo = f", alvo no médio + {self.target_r:g}R" if self.target == "medio" else ""
            return f"preço médio para trás: até {self.max_adds} entradas extras a cada {step}R contra{alvo}"
        return f"pirâmide: até {self.max_adds} entradas extras a cada {step}R a favor"

    def risk_factor(self, adds: int) -> float:
        """Perda total, em múltiplos de (1 perna x R), se as `adds` entradas extras entrarem
        e o stop for atingido."""
        if self.mode == MEDIA:
            return 1 + sum(1 - self.step * k for k in range(1, adds + 1))
        return 1.0  # pirâmide: o stop sobe para manter a perda no risco inicial

    def size(
        self,
        qty: float,
        integer: bool,
        stop_distance: float,
        max_unit_risk: float,
        capital: float,
        unit_margin: float | None,
    ) -> tuple[float, int]:
        """Tamanho de cada perna e quantas entradas extras cabem.

        `qty`: o tamanho de uma operação comum (já calculado pelo Guardião para o risco fixo).
        `max_unit_risk`: risco máximo aceito quando o tamanho é de 1 contrato inteiro."""
        if not self.active:
            return qty, 0
        for adds in range(self.max_adds, -1, -1):
            f = self.risk_factor(adds)
            u = qty / f
            if integer:
                u = float(math.floor(u + 1e-9))
                if u == 0 and f * stop_distance <= max_unit_risk:
                    u = 1.0
            if u <= 0:
                continue
            if unit_margin and u * (1 + adds) * unit_margin > capital:
                continue
            return u, adds
        return qty, 0

    def levels(self, entry: float, stop_distance: float, sign: int, adds: int) -> list[float]:
        """Preços em que cada entrada extra entra (ordem de acionamento)."""
        if adds <= 0:
            return []
        direction = -sign if self.mode == MEDIA else sign
        return [entry + direction * self.step * k * stop_distance for k in range(1, adds + 1)]


SEM_ESCALA = Scaling()


@dataclass
class Legs:
    """A posição em pernas: preço médio, stop e alvo da posição inteira."""

    scaling: Scaling
    sign: int
    unit: float
    stop: float
    target: float
    stop_distance: float  # R da 1ª entrada
    pending: list[float] = field(default_factory=list)  # próximos níveis de entrada
    fills: list[tuple[float, float]] = field(default_factory=list)  # (preço, quantidade)

    @property
    def qty(self) -> float:
        return sum(q for _, q in self.fills)

    @property
    def avg(self) -> float:
        return sum(p * q for p, q in self.fills) / self.qty

    @property
    def adds(self) -> int:
        return len(self.fills) - 1

    @property
    def risk0(self) -> float:
        return self.fills[0][1] * self.stop_distance

    def next_level(self) -> float | None:
        return self.pending[0] if self.pending else None

    def touched(self, low: float, high: float) -> bool:
        lvl = self.next_level()
        if lvl is None:
            return False
        against = self.scaling.mode == MEDIA
        if (self.sign > 0) == against:
            return low <= lvl  # compra com preço médio / venda em pirâmide: preço caindo
        return high >= lvl

    def add(self, price: float) -> None:
        self.pending.pop(0)
        self.fills.append((price, self.unit))
        if self.scaling.mode == PIRAMIDE:
            # stop da posição inteira onde a perda total = risco da 1ª perna (nunca recua)
            new = self.avg - self.sign * self.risk0 / self.qty
            self.stop = max(self.stop, new) if self.sign > 0 else min(self.stop, new)
        elif self.scaling.target == "medio":
            self.target = self.avg + self.sign * self.scaling.target_r * self.stop_distance
