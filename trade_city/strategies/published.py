"""Estratégias que traders conhecidos divulgaram publicamente, com regras objetivas.

Adaptações comuns a todas: só compra (sem venda a descoberto), a entrada é na
abertura do candle seguinte ao sinal, e o Guardião de Risco sempre coloca um
stop loss, mesmo quando o autor original não usava.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..indicators import adx_series, ema_series, highest, lowest, sma
from ..models import Bar
from .base import Strategy


class TurtleBreakout(Strategy):
    """Turtle (Richard Dennis): rompimento de N candles, saída na mínima de M candles.
    Sistema 1 = 20/10, Sistema 2 = 55/20.
    Fonte: https://www.ig.com/uk/trading-strategies/turtle-trading--what-is-it-and-what-are-the-rules--180904"""

    def __init__(self, entry: int = 20, exit: int = 10):
        self.entry_n, self.exit_n = entry, exit
        self.name = f"Turtle {entry}/{exit}"
        self.description = f"Compra no rompimento da máxima de {entry} candles e sai na perda da mínima de {exit}."
        self.min_bars = max(entry, exit) + 1

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        if len(bars) < self.min_bars:
            return None
        prior_high = highest([b.high for b in bars[:-1]], self.entry_n)
        if prior_high is not None and bars[-1].close > prior_high:
            return f"Turtle: rompeu a máxima de {self.entry_n} candles"
        return None

    def should_exit(self, bars: Sequence[Bar]) -> bool:
        prior_low = lowest([b.low for b in bars[:-1]], self.exit_n)
        return prior_low is not None and bars[-1].close < prior_low


class ConnorsRSI2(Strategy):
    """Larry Connors, RSI(2): acima da MM200, compra com IFR(2) <= 5, sai acima da MM5.
    Fonte: https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2"""

    name = "Connors RSI(2)"
    description = "Acima da média de 200, compra com IFR(2) até 5 e sai quando fecha acima da média de 5."

    def __init__(self, threshold: float = 5.0):
        from .mean_reversion import MeanReversion

        self._inner = MeanReversion(rsi_n=2, threshold=threshold + 1e-9, trend=200, exit_n=5)
        self.min_bars = self._inner.min_bars

    def analyze(self, bars):
        reason = self._inner.analyze(bars)
        return f"Connors RSI(2): {reason}" if reason else None

    def should_exit(self, bars):
        return self._inner.should_exit(bars)


class DoubleSevens(Strategy):
    """Larry Connors, Double 7s: acima da MM200, compra no menor fechamento de 7 dias,
    sai no maior fechamento de 7 dias.
    Fonte: https://therighttrader.com/learn/trading-strategies/double-sevens-strategy"""

    name = "Connors Double 7s"
    description = "Acima da média de 200, compra no menor fechamento de 7 candles e sai no maior de 7."
    min_bars = 200

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        if len(bars) < self.min_bars:
            return None
        closes = [b.close for b in bars]
        trend = sma(closes, 200)
        if trend is not None and closes[-1] > trend and closes[-1] <= min(closes[-7:]):
            return "Double 7s: menor fechamento de 7 candles, acima da média de 200"
        return None

    def should_exit(self, bars: Sequence[Bar]) -> bool:
        closes = [b.close for b in bars]
        return len(closes) >= 7 and closes[-1] >= max(closes[-7:])


class HolyGrail(Strategy):
    """Linda Raschke, Holy Grail: tendência forte (ADX(14) acima de 30), o preço recua até a
    MME20 e a compra acontece quando rompe a máxima do candle anterior. Saída: perda da
    mínima dos últimos 5 candles (aproximação do stop móvel no fundo mais recente).
    Adaptações: o ADX "subindo" é verificado no início da tendência (o ADX costuma cair
    durante o recuo), e exigimos a MME20 subindo para garantir que a tendência é de alta.
    Fonte: https://therighttrader.com/learn/trading-strategies/holy-grail-setup"""

    name = "Raschke Holy Grail"
    description = "ADX(14) > 30 após subir, recuo até a MME20 e rompimento da máxima anterior."
    min_bars = 60

    def __init__(self, adx_min: float = 30.0, ema_n: int = 20, trail: int = 5):
        self.adx_min, self.ema_n, self.trail = adx_min, ema_n, trail
        self.lookback = 120

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        if len(bars) < self.min_bars:
            return None
        adx = adx_series(bars, 14)
        emas = ema_series([b.close for b in bars], self.ema_n)
        if len(adx) < 2 or len(emas) < 2:
            return None
        prev, cur = bars[-2], bars[-1]
        trending_up = emas[-1] > emas[-6] if len(emas) >= 6 else False
        adx_rose = len(adx) >= 11 and max(adx[-11:]) > adx[-11]
        if adx[-1] > self.adx_min and adx_rose and trending_up and prev.low <= emas[-2] and cur.close > prev.high:
            return f"Holy Grail: ADX {adx[-1]:.0f}, recuo na MME{self.ema_n} e rompimento"
        return None

    def should_exit(self, bars: Sequence[Bar]) -> bool:
        prior_low = lowest([b.low for b in bars[:-1]], self.trail)
        return prior_low is not None and bars[-1].close < prior_low


class WilliamsBreakout(Strategy):
    """Larry Williams, rompimento de volatilidade: compra quando o preço passa da abertura
    mais k vezes a amplitude do candle anterior. Aqui o sinal exige o fechamento acima
    desse nível, e a saída é no fim do candle seguinte (saída por tempo).
    Fonte: https://www.luxalgo.com/library/concept/volatility-breakout/"""

    min_bars = 2

    def __init__(self, k: float = 0.5):
        self.k = k
        self.name = f"Williams rompimento k={k}"
        self.description = f"Compra quando fecha acima da abertura + {k} x amplitude do candle anterior; sai no candle seguinte."

    def analyze(self, bars: Sequence[Bar]) -> str | None:
        if len(bars) < 2:
            return None
        prev, cur = bars[-2], bars[-1]
        level = cur.open + self.k * (prev.high - prev.low)
        if prev.high > prev.low and cur.close > level:
            return f"Williams: fechou acima de abertura + {self.k} x amplitude anterior"
        return None

    def should_exit(self, bars: Sequence[Bar]) -> bool:
        return True
