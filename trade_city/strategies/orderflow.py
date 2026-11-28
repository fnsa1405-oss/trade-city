"""Estratégias de fluxo de ordens (order flow).

Em cripto o fluxo é real (volume de agressão da Binance, livro e contratos em aberto dos
futuros). Nos índices o delta é estimado pela classificação de volume em bloco (ver
`trade_city/orderflow.py`). Tudo é calculado uma vez em `prepare`, sem olhar o futuro: o
valor do candle i usa só o que já existia no fechamento dele.

Ideias e fontes:
- Delta e CVD (delta acumulado): o saldo das agressões mostra quem está com pressa.
  Rompimento com agressão a favor tende a seguir; rompimento sem agressão costuma falhar.
- Divergência e absorção: o preço faz nova mínima mas o CVD não (ou a venda agressiva é
  enorme e o preço não cai): alguém grande está comprando passivamente.
- Desequilíbrio do livro: Cont, Kukanov e Stoikov (2014), "The Price Impact of Order Book
  Events", Journal of Financial Econometrics (https://doi.org/10.1093/jjfinec/nbt003);
  Cartea, Donnelly e Jaimungal (2018), "Enhancing trading strategies with order book
  signals", Applied Mathematical Finance (https://doi.org/10.1080/1350486X.2018.1434009).
- Contratos em aberto: alta com contratos em aberto subindo = posições novas entrando (a
  tendência tem combustível); queda forte com contratos em aberto despencando = liquidação
  forçada, que costuma marcar fundo de curto prazo.
"""
from __future__ import annotations

import copy
from collections.abc import Sequence

from ..indicators import ema_series
from ..intraday import OPEN_MIN, Timeline
from ..models import Bar, Entry, Side
from ..orderflow import buy_volumes
from .base import Strategy
from .daytrade import DayTradeStrategy

LONG, SHORT = Side.LONG, Side.SHORT


class _FlowStrategy(Strategy):
    """Base: calcula delta, CVD e médias uma vez para o histórico inteiro."""

    has_exit = True
    uses_flow = True  # a mesa busca candles com o volume de agressão
    needs: str | None = None  # "book" ou "oi" quando precisa do livro ou dos contratos em aberto
    lookback = 260

    def __init__(self):
        self._idx: dict = {}
        self._bars: list[Bar] = []

    def prepare(self, bars: Sequence[Bar]) -> None:
        bars = list(bars)
        self._bars = bars
        self._idx = {b.ts: i for i, b in enumerate(bars)}
        buys, self.real = buy_volumes(bars)
        n = len(bars)
        self.vol = [b.volume for b in bars]
        self.delta = [2 * buys[i] - self.vol[i] for i in range(n)]
        self.ratio = [self.delta[i] / self.vol[i] if self.vol[i] > 0 else 0.0 for i in range(n)]
        cvd, run = [], 0.0
        for d in self.delta:
            run += d
            cvd.append(run)
        self.cvd = cvd
        self.closes = [b.close for b in bars]
        self.ema50 = ema_series(self.closes, 50) if n >= 50 else []
        self._compute()

    def _compute(self) -> None:
        pass

    def _i(self, bars: Sequence[Bar]) -> int | None:
        if not bars:
            return None
        i = self._idx.get(bars[-1].ts)
        if i is None or self._bars[i] is not bars[-1]:
            self.prepare(bars)
            i = self._idx.get(bars[-1].ts)
        return i

    # ajudas ----------------------------------------------------------------
    def _avg(self, values, i, n):
        lo = max(0, i - n)
        seg = values[lo:i]
        return sum(seg) / len(seg) if seg else 0.0

    def _std(self, values, i, n):
        lo = max(0, i - n)
        seg = values[lo:i]
        if len(seg) < 2:
            return 0.0
        m = sum(seg) / len(seg)
        return (sum((x - m) ** 2 for x in seg) / len(seg)) ** 0.5

    def _ema50(self, i):
        # ema_series começa no candle 50 (índice 49)
        j = i - 49
        return self.ema50[j] if self.ema50 and 0 <= j < len(self.ema50) else None

    def analyze(self, bars):
        i = self._i(bars)
        if i is None or i < self.min_bars:
            return None
        return self._entry(i)

    def should_exit(self, bars):
        i = self._i(bars)
        if i is None:
            return False
        return self._exit(i)

    def _entry(self, i: int) -> str | None:
        raise NotImplementedError

    def _exit(self, i: int) -> bool:
        return False


class DeltaBreakout(_FlowStrategy):
    """Rompimento confirmado pela agressão: fecha acima da máxima de `n` candles com o delta
    do candle a favor (pelo menos `min_ratio` do volume) e volume acima de 1,5x a média.
    Sai como o Turtle, na perda da mínima de n/2 candles."""

    def __init__(self, n: int = 20, min_ratio: float = 0.10):
        super().__init__()
        self.n, self.min_ratio = n, min_ratio
        self.name = f"Rompimento com agressão ({n})"
        self.description = f"Rompe a máxima de {n} com delta ≥ {min_ratio:.0%} do volume e volume 1,5x a média; sai na mínima de {n // 2}."
        self.min_bars = max(n, 50) + 2

    def _entry(self, i):
        b = self._bars[i]
        prior = max(x.high for x in self._bars[i - self.n : i])
        if b.close > prior and self.ratio[i] >= self.min_ratio and self.vol[i] > 1.5 * self._avg(self.vol, i, 50):
            return f"rompeu a máxima de {self.n} com agressão de compra ({self.ratio[i]:+.0%} do volume)"
        return None

    def _exit(self, i):
        m = self.n // 2
        if i < m + 1:
            return False
        return self._bars[i].close < min(x.low for x in self._bars[i - m : i])


class CVDDivergence(_FlowStrategy):
    """Divergência: o preço fecha na menor mínima de `n` candles, mas o CVD subiu nesses n
    candles (a venda não acompanhou a queda). Sai quando o preço fecha acima da média de n
    ou depois de 2n candles."""

    def __init__(self, n: int = 20):
        super().__init__()
        self.n = n
        self.name = f"Divergência de CVD ({n})"
        self.description = f"Nova mínima de {n} com o CVD subindo; sai acima da média de {n}."
        self.min_bars = max(n, 50) + 2
        self._opened: int | None = None

    def _entry(self, i):
        lows = [x.close for x in self._bars[i - self.n : i]]
        if self.closes[i] < min(lows) and self.cvd[i] - self.cvd[i - self.n] > 0:
            self._opened = i
            return f"nova mínima de {self.n} sem venda agressiva (CVD subiu)"
        return None

    def _exit(self, i):
        avg = sum(self.closes[i - self.n + 1 : i + 1]) / self.n
        return self.closes[i] > avg


class Absorption(_FlowStrategy):
    """Absorção: venda agressiva extrema (delta abaixo de `z` desvios da média de 100) no
    candle que faz a mínima de 10, mas o fechamento fica na metade de cima do candle: as
    ofertas de compra seguraram. Sai acima da MME50 ou na perda da mínima do candle."""

    def __init__(self, z: float = 2.0):
        super().__init__()
        self.z = z
        self.name = f"Absorção da venda (z {z:g})"
        self.description = f"Venda agressiva extrema ({z:g} desvios) na mínima de 10 com fechamento na metade de cima; sai na média."
        self.min_bars = 102

    def _entry(self, i):
        b = self._bars[i]
        sd = self._std(self.ratio, i, 100)
        if sd <= 0 or b.high <= b.low:
            return None
        zscore = (self.ratio[i] - self._avg(self.ratio, i, 100)) / sd
        new_low = b.low < min(x.low for x in self._bars[i - 10 : i])
        upper_half = (b.close - b.low) / (b.high - b.low) >= 0.5
        if zscore <= -self.z and new_low and upper_half:
            return f"absorção: venda agressiva de {zscore:.1f} desvios sem o preço fechar embaixo"
        return None

    def _exit(self, i):
        e = self._ema50(i)
        return e is not None and self.closes[i] > e


class CVDTrend(_FlowStrategy):
    """Tendência do fluxo: o delta somado de `n` candles vira positivo com o preço acima da
    média de n. Sai quando o delta somado fica negativo e o preço perde a média."""

    def __init__(self, n: int = 28):
        super().__init__()
        self.n = n
        self.name = f"Tendência do CVD ({n})"
        self.description = f"Delta de {n} candles vira positivo com preço acima da média de {n}; sai quando os dois viram."
        self.min_bars = max(n, 50) + 2

    def _flow(self, i):
        return self.cvd[i] - self.cvd[i - self.n]

    def _entry(self, i):
        avg = sum(self.closes[i - self.n + 1 : i + 1]) / self.n
        if self._flow(i) > 0 >= self._flow(i - 1) and self.closes[i] > avg:
            return f"delta de {self.n} candles virou comprador com preço acima da média"
        return None

    def _exit(self, i):
        avg = sum(self.closes[i - self.n + 1 : i + 1]) / self.n
        return self._flow(i) < 0 and self.closes[i] < avg


class BookImbalance(_FlowStrategy):
    """Livro de ofertas: a média do desequilíbrio a 1% do preço passa de `th` (mais dinheiro
    esperando para comprar do que para vender), com delta do candle positivo e preço acima
    da MME50. Sai quando o desequilíbrio vira para o lado vendedor."""

    needs = "book"

    def __init__(self, th: float = 0.15, band: str = "imb1"):
        super().__init__()
        self.th, self.band = th, band
        pct = "1%" if band == "imb1" else "5%"
        self.name = f"Livro desequilibrado a {pct} (> {th:.0%})"
        self.description = f"Ofertas de compra a {pct} superam as de venda em {th:.0%}, delta positivo, acima da MME50; sai quando o livro vira."
        self.min_bars = 52

    def _compute(self):
        self.imb = [getattr(b, self.band, None) for b in self._bars]

    def _entry(self, i):
        v, prev = self.imb[i], self.imb[i - 1]
        e = self._ema50(i)
        if v is None or prev is None or e is None:
            return None
        if v > self.th >= prev and self.delta[i] > 0 and self.closes[i] > e:
            return f"livro com {v:+.0%} a favor da compra e agressão compradora"
        return None

    def _exit(self, i):
        v = self.imb[i]
        return v is not None and v < 0


class OpenInterestTrend(_FlowStrategy):
    """Contratos em aberto: o preço rompe a máxima de `n` com os contratos em aberto subindo
    mais de 3% em n candles e mais agressão de compra que de venda nos futuros (razão > 1).
    Sai quando os contratos em aberto caem e o preço perde a mínima de n/2."""

    needs = "oi"

    def __init__(self, n: int = 20):
        super().__init__()
        self.n = n
        self.name = f"Rompimento com contratos em aberto subindo ({n})"
        self.description = f"Rompe a máxima de {n} com contratos em aberto +3% e agressores comprando; sai na mínima de {n // 2}."
        self.min_bars = max(n, 50) + 2

    def _compute(self):
        self.oi = [getattr(b, "oi", None) for b in self._bars]
        self.tr = [getattr(b, "taker_ratio", None) for b in self._bars]

    def _entry(self, i):
        now, past = self.oi[i], self.oi[i - self.n]
        ratios = [r for r in self.tr[i - 3 : i + 1] if r is not None]
        if not now or not past or not ratios:
            return None
        prior = max(x.high for x in self._bars[i - self.n : i])
        if self.closes[i] > prior and now / past - 1 > 0.03 and sum(ratios) / len(ratios) > 1.0:
            return f"rompeu a máxima de {self.n} com contratos em aberto {now / past - 1:+.0%}"
        return None

    def _exit(self, i):
        m = self.n // 2
        return self.closes[i] < min(x.low for x in self._bars[i - m : i])


class LiquidationFlush(_FlowStrategy):
    """Liquidação forçada: queda de mais de 3 ATR em `n` candles com os contratos em aberto
    caindo mais de `oi_drop` e o candle fechando com delta positivo (a venda forçada acabou).
    Sai acima da MME50 ou depois de 3n candles."""

    needs = "oi"

    def __init__(self, n: int = 12, oi_drop: float = 0.08):
        super().__init__()
        self.n, self.oi_drop = n, oi_drop
        self.name = f"Fim de liquidação ({n} candles, contratos -{oi_drop:.0%})"
        self.description = f"Queda de 3 ATR em {n} candles com contratos em aberto -{oi_drop:.0%} e delta virando positivo; sai na MME50."
        self.min_bars = 64

    def _compute(self):
        self.oi = [getattr(b, "oi", None) for b in self._bars]
        bars = self._bars
        tr = [0.0] + [max(b.high, bars[k - 1].close) - min(b.low, bars[k - 1].close) for k, b in enumerate(bars) if k > 0]
        self.atr = [sum(tr[max(1, k - 13) : k + 1]) / max(1, len(tr[max(1, k - 13) : k + 1])) for k in range(len(tr))]

    def _entry(self, i):
        now, past = self.oi[i], self.oi[i - self.n]
        if not now or not past:
            return None
        drop = self.closes[i - self.n] - self.closes[i]
        if drop > 3 * self.atr[i] and now / past - 1 < -self.oi_drop and self.delta[i] > 0:
            return f"liquidação: contratos em aberto {now / past - 1:+.0%} e compra voltando"
        return None

    def _exit(self, i):
        e = self._ema50(i)
        return e is not None and self.closes[i] > e


class FlowFilter(Strategy):
    """Filtro de fluxo sobre outra estratégia: só entra quando o delta somado dos últimos `n`
    candles está a favor. A saída é a da estratégia original."""

    uses_flow = True

    def __init__(self, inner: Strategy, n: int = 20):
        self.inner = inner
        self.n = n
        self.name = f"{inner.name} + fluxo a favor ({n})"
        self.description = f"{inner.description} Só entra com o delta de {n} candles positivo."
        self.min_bars = max(inner.min_bars, n + 2)
        self.lookback = max(inner.window, n + 2)
        self.has_exit = inner.has_exit
        self._flow = _CVD()

    def prepare(self, bars):
        self.inner.prepare(bars)
        self._flow.prepare(bars)

    def decide(self, bars):
        entry = self.inner.decide(bars)
        if entry is None or entry.side is not LONG:
            return None
        i = self._flow._i(bars)
        if i is None or i < self.n:
            return None
        if self._flow.cvd[i] - self._flow.cvd[i - self.n] <= 0:
            return None
        return Entry(entry.reason + f" (delta de {self.n} a favor)", entry.side, entry.stop, entry.trigger, entry.valid_bars)

    def analyze(self, bars):
        e = self.decide(bars)
        return e.reason if e else None

    def should_exit(self, bars):
        return self.inner.should_exit(bars)

    def exit_signal(self, bars, side):
        return self.inner.exit_signal(bars, side)

    def __deepcopy__(self, memo):
        return FlowFilter(copy.deepcopy(self.inner, memo), self.n)


class _CVD(_FlowStrategy):
    name = "cvd"

    def _entry(self, i):
        return None


# day trade nos índices (delta estimado) ----------------------------------------

class _FlowDay(DayTradeStrategy):
    """Base do day trade com fluxo: delta (estimado nos ETFs) e CVD do dia."""

    def _compute(self, tl: Timeline) -> None:
        buys, self.real = buy_volumes(tl.bars)
        self.delta = [2 * buys[i] - b.volume for i, b in enumerate(tl.bars)]
        day_cvd, run, cur = [], 0.0, None
        for i, d in enumerate(self.delta):
            if tl.dates[i] != cur:
                run, cur = 0.0, tl.dates[i]
            run += d
            day_cvd.append(run)
        self.day_cvd = day_cvd
        self.day_vol = []
        run, cur = 0.0, None
        for i, b in enumerate(tl.bars):
            if tl.dates[i] != cur:
                run, cur = 0.0, tl.dates[i]
            run += b.volume
            self.day_vol.append(run)


class ORBDelta(_FlowDay):
    """ORB com fluxo: o lado do primeiro candle de `range_minutes` do pregão só vale se o delta
    desses minutos concordar com pelo menos `min_ratio` do volume. Stop no outro extremo,
    zera no fim do dia (Zarattini e Aziz, 2023, com o filtro de agressão)."""

    def __init__(self, range_minutes: int = 5, min_ratio: float = 0.2, **kw):
        super().__init__(**kw)
        self.range_minutes, self.min_ratio = range_minutes, min_ratio
        self.name = f"ORB {range_minutes} min + delta ≥ {min_ratio:.0%}"
        self.description = f"Lado do primeiro candle de {range_minutes} min, só com agressão a favor; stop no outro extremo."
        self.context_days = 1

    def _entry(self, tl, i):
        if tl.end_min[i] != OPEN_MIN + self.range_minutes:
            return None
        start = i - tl.day_index[i]
        if tl.start_min[start] != OPEN_MIN:
            return None
        group = tl.bars[start : i + 1]
        vol = sum(b.volume for b in group)
        if vol <= 0:
            return None
        ratio = self.day_cvd[i] / vol
        opn, close = group[0].open, group[-1].close
        high, low = max(b.high for b in group), min(b.low for b in group)
        if close > opn and ratio >= self.min_ratio:
            return Entry(f"ORB de alta com agressão compradora ({ratio:+.0%})", LONG, low)
        if close < opn and ratio <= -self.min_ratio:
            return Entry(f"ORB de baixa com agressão vendedora ({ratio:+.0%})", SHORT, high)
        return None


class VWAPDeltaTrend(_FlowDay):
    """Tendência do dia pelo fluxo: depois das 10h, preço acima da VWAP, CVD do dia acima de
    `min_ratio` do volume do dia e rompimento da máxima dos últimos 6 candles = compra (o
    espelho vende). Stop na VWAP; sai quando o preço cruza a VWAP ou o CVD do dia vira."""

    def __init__(self, min_ratio: float = 0.1, **kw):
        super().__init__(**kw)
        self.min_ratio = min_ratio
        self.name = f"VWAP + CVD do dia ≥ {min_ratio:.0%}"
        self.description = "A favor da VWAP e do delta acumulado do dia, no rompimento de 6 candles; sai no cruzamento da VWAP."
        self.context_days = 1

    def _entry(self, tl, i):
        if tl.end_min[i] < OPEN_MIN + 30 or tl.day_index[i] < 6:
            return None
        b, vwap = tl.bars[i], tl.vwap[i]
        vol = self.day_vol[i]
        if vol <= 0:
            return None
        ratio = self.day_cvd[i] / vol
        prior = tl.bars[i - 6 : i]
        if b.close > vwap and ratio >= self.min_ratio and b.close > max(x.high for x in prior):
            return Entry(f"acima da VWAP com CVD do dia {ratio:+.0%}", LONG, vwap)
        if b.close < vwap and ratio <= -self.min_ratio and b.close < min(x.low for x in prior):
            return Entry(f"abaixo da VWAP com CVD do dia {ratio:+.0%}", SHORT, vwap)
        return None

    def _exit(self, tl, i, side):
        b, vwap = tl.bars[i], tl.vwap[i]
        if side is LONG:
            return b.close < vwap or self.day_cvd[i] < 0
        return b.close > vwap or self.day_cvd[i] > 0


class DayAbsorption(_FlowDay):
    """Absorção no extremo do dia: o candle faz a mínima (ou máxima) do dia com agressão
    extrema contra (delta abaixo de `z` desvios dos últimos 100 candles), mas fecha na metade
    de cima (de baixo). Compra (vende) com stop no extremo; sai na VWAP."""

    def __init__(self, z: float = 2.5, **kw):
        super().__init__(**kw)
        self.z = z
        self.name = f"Absorção no extremo do dia (z {z:g})"
        self.description = "Agressão extrema contra no extremo do dia sem o preço fechar lá; alvo na VWAP."
        self.context_days = 2

    def _compute(self, tl):
        super()._compute(tl)
        self.ratio = [d / b.volume if b.volume > 0 else 0.0 for d, b in zip(self.delta, tl.bars)]

    def _entry(self, tl, i):
        if i < 100 or tl.day_index[i] < 3:
            return None
        seg = self.ratio[i - 100 : i]
        m = sum(seg) / len(seg)
        sd = (sum((x - m) ** 2 for x in seg) / len(seg)) ** 0.5
        if sd <= 0:
            return None
        z = (self.ratio[i] - m) / sd
        b = tl.bars[i]
        if b.high <= b.low:
            return None
        start = i - tl.day_index[i]
        day = tl.bars[start:i]
        pos = (b.close - b.low) / (b.high - b.low)
        if z <= -self.z and b.low < min(x.low for x in day) and pos >= 0.5 and b.close < tl.vwap[i]:
            return Entry(f"absorção na mínima do dia (venda de {z:.1f} desvios)", LONG, b.low)
        if z >= self.z and b.high > max(x.high for x in day) and pos <= 0.5 and b.close > tl.vwap[i]:
            return Entry(f"absorção na máxima do dia (compra de {z:.1f} desvios)", SHORT, b.high)
        return None

    def _exit(self, tl, i, side):
        b, vwap = tl.bars[i], tl.vwap[i]
        return b.close >= vwap if side is LONG else b.close <= vwap
