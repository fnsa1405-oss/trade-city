"""Humor do trader: muda só o tamanho da posição, nunca as travas."""
from __future__ import annotations

from collections.abc import Sequence
from enum import Enum


class Mood(Enum):
    PERIGO = ("perigo", 0.25)
    ALERTA = ("alerta", 0.50)
    NORMAL = ("normal", 1.00)
    CONFIANTE = ("confiante", 1.25)

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def size_multiplier(self) -> float:
        return self.value[1]


def _streak(outcomes: Sequence[bool], won: bool) -> int:
    count = 0
    for outcome in reversed(outcomes):
        if outcome is not won:
            break
        count += 1
    return count


def compute_mood(recent_outcomes: Sequence[bool], pnl_today: float, streak: int = 3) -> Mood:
    """recent_outcomes: True para vitória, False para derrota, do mais antigo ao mais novo."""
    if _streak(recent_outcomes, won=False) >= streak:
        return Mood.PERIGO
    if pnl_today < 0:
        return Mood.ALERTA
    if _streak(recent_outcomes, won=True) >= streak:
        return Mood.CONFIANTE
    return Mood.NORMAL
