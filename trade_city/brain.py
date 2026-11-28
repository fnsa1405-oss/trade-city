"""Cérebro do trader: uma rede neural pequena que aprende com as operações do próprio trader.

Como funciona (em português simples):
- A estratégia aprovada na escola continua achando as oportunidades.
- Para cada oportunidade, o cérebro olha o "clima" do gráfico naquele momento
  (força da tendência, volatilidade, distância da média e da VWAP, horário...) e
  estima a chance de a operação dar certo. Abaixo do limite, o trader deixa passar.
- O cérebro treina com o histórico (as operações que a estratégia teria feito) e só
  é promovido se, numa parte final do histórico que ele nunca viu, filtrar melhor do
  que operar sem ele. Senão, o trader segue sem cérebro.
- Ele nunca mexe nas travas: stop, tamanho máximo, perdas do dia e botão de pânico
  continuam com o Guardião e o Auditor.

Técnica: "meta-labeling" (Marcos López de Prado, Advances in Financial Machine
Learning, 2018), com uma rede de uma camada escondida treinada em numpy.
"""
from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from zoneinfo import ZoneInfo

from .indicators import atr, ema, rsi
from .models import Bar, ClosedTrade, Side

NY = ZoneInfo("America/New_York")

FEATURE_NAMES = [
    "retorno 1 candle / ATR",
    "retorno 5 candles / ATR",
    "retorno 20 candles / ATR",
    "volatilidade (ATR %)",
    "distância da MME20 / ATR",
    "MME20 - MME50 / ATR",
    "IFR 14",
    "volume / média de 20",
    "amplitude do candle / ATR",
    "hora (seno)",
    "hora (cosseno)",
    "dia da semana",
    "lado (compra = 1, venda = -1)",
]
MIN_BARS = 60


def features(bars: Sequence[Bar], side: Side) -> list[float] | None:
    """O clima do gráfico no fechamento do último candle, sempre do ponto de vista do
    lado da operação (positivo = a favor)."""
    if len(bars) < MIN_BARS:
        return None
    window = bars[-MIN_BARS:]
    closes = [b.close for b in window]
    vol = atr(window, 14)
    if not vol or vol <= 0:
        return None
    s = side.sign
    last = window[-1]
    e20, e50 = ema(closes, 20), ema(closes, 50)
    r = rsi(closes, 14)
    volumes = [b.volume for b in window[-20:]]
    avg_v = sum(volumes) / len(volumes)
    local = last.ts.astimezone(NY)
    hour = local.hour + local.minute / 60
    clip = lambda x: max(-5.0, min(5.0, x))  # noqa: E731
    return [
        clip(s * (closes[-1] - closes[-2]) / vol),
        clip(s * (closes[-1] - closes[-6]) / vol),
        clip(s * (closes[-1] - closes[-21]) / vol),
        clip(100 * vol / closes[-1]),
        clip(s * (closes[-1] - e20) / vol),
        clip(s * (e20 - e50) / vol),
        (r - 50) / 50 * s if r is not None else 0.0,
        clip(last.volume / avg_v - 1) if avg_v > 0 else 0.0,
        clip((last.high - last.low) / vol),
        math.sin(2 * math.pi * hour / 24),
        math.cos(2 * math.pi * hour / 24),
        local.weekday() / 4 - 0.5,
        float(s),
    ]


# rede neural -----------------------------------------------------------------
@dataclass
class Brain:
    trader: str
    mean: list[float]
    std: list[float]
    w1: list[list[float]]
    b1: list[float]
    w2: list[float]
    b2: float
    threshold: float = 0.5
    promoted: bool = False
    trained_until: str = ""
    report: dict = field(default_factory=dict)
    setup: str = ""  # estratégia/tempo gráfico/alvo com que foi treinado
    def prob(self, x: Sequence[float]) -> float:
        import numpy as np

        z = (np.asarray(x, dtype=float) - np.asarray(self.mean)) / np.asarray(self.std)
        h = np.tanh(z @ np.asarray(self.w1) + np.asarray(self.b1))
        return float(1 / (1 + np.exp(-(h @ np.asarray(self.w2) + self.b2))))

    def allows(self, bars: Sequence[Bar], side: Side) -> tuple[bool, float | None]:
        x = features(bars, side)
        if x is None:
            return True, None  # sem histórico para avaliar: não atrapalha
        p = self.prob(x)
        return p >= self.threshold, p

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "Brain":
        return cls(**json.loads(text))


def fit(trader: str, xs: Sequence[Sequence[float]], ys: Sequence[int], hidden: int = 8, epochs: int = 400, l2: float = 1e-2, seed: int = 7) -> Brain:
    """Treina a rede (uma camada escondida, tanh, saída sigmoide) com Adam e regularização L2."""
    import numpy as np

    X = np.asarray(xs, dtype=float)
    y = np.asarray(ys, dtype=float)
    mean, std = X.mean(axis=0), X.std(axis=0)
    std[std < 1e-9] = 1.0
    Z = (X - mean) / std
    rng = np.random.default_rng(seed)
    n_in = Z.shape[1]
    params = {
        "w1": rng.normal(0, 1 / math.sqrt(n_in), (n_in, hidden)),
        "b1": np.zeros(hidden),
        "w2": rng.normal(0, 1 / math.sqrt(hidden), hidden),
        "b2": np.zeros(1),
    }
    m = {k: np.zeros_like(v) for k, v in params.items()}
    v = {k: np.zeros_like(val) for k, val in params.items()}
    lr, b1_, b2_, eps = 0.01, 0.9, 0.999, 1e-8
    n = len(y)
    for t in range(1, epochs + 1):
        h = np.tanh(Z @ params["w1"] + params["b1"])
        p = 1 / (1 + np.exp(-(h @ params["w2"] + params["b2"][0])))
        d_out = (p - y) / n
        grads = {
            "w2": h.T @ d_out + l2 * params["w2"],
            "b2": np.array([d_out.sum()]),
        }
        d_h = np.outer(d_out, params["w2"]) * (1 - h**2)
        grads["w1"] = Z.T @ d_h + l2 * params["w1"]
        grads["b1"] = d_h.sum(axis=0)
        for k in params:
            m[k] = b1_ * m[k] + (1 - b1_) * grads[k]
            v[k] = b2_ * v[k] + (1 - b2_) * grads[k] ** 2
            mh, vh = m[k] / (1 - b1_**t), v[k] / (1 - b2_**t)
            params[k] -= lr * mh / (np.sqrt(vh) + eps)
    return Brain(
        trader=trader,
        mean=mean.tolist(),
        std=std.tolist(),
        w1=params["w1"].tolist(),
        b1=params["b1"].tolist(),
        w2=params["w2"].tolist(),
        b2=float(params["b2"][0]),
    )


def setup_of(trader) -> str:
    """Identidade do que o cérebro aprendeu: se a configuração mudar, ele precisa treinar de novo."""
    return f"{trader.strategy.name}|{trader.timeframe}|{trader.atr_stop_multiple}|{trader.reward_ratio}"


# escola do cérebro --------------------------------------------------------------
@dataclass(frozen=True)
class BrainRules:
    min_trades: int = 150  # operações com "clima" registrado para começar a treinar
    train_share: float = 0.7
    min_kept_share: float = 0.3  # o cérebro precisa deixar passar pelo menos 30% das operações
    min_test_kept: int = 10
    min_gain: float = 1.05  # fator de lucro filtrado tem que ser 5% melhor que sem cérebro
    thresholds: tuple = (0.45, 0.5, 0.55, 0.6)


def _pf(pnls: Sequence[float]) -> float:
    gains = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p <= 0)
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _choose_threshold(brain: Brain, xs, pnls, rules: BrainRules) -> float:
    best, best_total = 0.5, -float("inf")
    for thr in rules.thresholds:
        kept = [p for x, p in zip(xs, pnls) if brain.prob(x) >= thr]
        if len(kept) < rules.min_kept_share * len(pnls):
            continue
        total = sum(kept)
        if total > best_total:
            best, best_total = thr, total
    return best


def train_brain(trader: str, trades: Sequence[ClosedTrade], rules: BrainRules = BrainRules()) -> Brain | None:
    """Treina com os 70% primeiros e prova nos 30% finais (que ele nunca viu).
    Devolve None quando não há operações suficientes."""
    data = [(t.features, t.pnl, t.closed_at) for t in trades if t.features]
    if len(data) < rules.min_trades:
        return None
    split = int(len(data) * rules.train_share)
    train, test = data[:split], data[split:]

    # limite escolhido numa validação dentro do treino (os 25% finais do treino)
    inner = int(len(train) * 0.75)
    probe = fit(trader, [d[0] for d in train[:inner]], [int(d[1] > 0) for d in train[:inner]])
    threshold = _choose_threshold(probe, [d[0] for d in train[inner:]], [d[1] for d in train[inner:]], rules)

    brain = fit(trader, [d[0] for d in train], [int(d[1] > 0) for d in train])
    brain.threshold = threshold
    kept = [p for x, p, _ in test if brain.prob(x) >= threshold]
    base = [p for _, p, _ in test]
    pf_base, pf_kept = _pf(base), _pf(kept)
    brain.promoted = (
        len(kept) >= rules.min_test_kept
        and len(kept) >= rules.min_kept_share * len(test)
        and sum(kept) > 0
        and pf_kept >= max(1.1, pf_base * rules.min_gain)
    )
    brain.trained_until = data[-1][2].isoformat()
    brain.report = {
        "operações no treino": len(train),
        "operações na prova": len(test),
        "limite": threshold,
        "prova sem cérebro": {"operações": len(base), "fator de lucro": round(pf_base, 2), "resultado": round(sum(base), 2)},
        "prova com cérebro": {"operações": len(kept), "fator de lucro": round(pf_kept, 2), "resultado": round(sum(kept), 2)},
    }
    # promovido: retreina com tudo, inclusive a prova, para operar com o que há de mais recente
    if brain.promoted:
        final = fit(trader, [d[0] for d in data], [int(d[1] > 0) for d in data])
        final.threshold, final.promoted, final.trained_until, final.report = threshold, True, brain.trained_until, brain.report
        return final
    return brain
