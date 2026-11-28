"""Setups clássicos que traders conhecidos ensinam publicamente, para day trade.

Todos usam entrada por rompimento (ordem stop): o setup "arma" no fechamento de um
candle e a entrada só acontece se o preço passar da máxima (compra) ou da mínima
(venda) dele nos candles seguintes. O stop fica no outro extremo indicado pelo setup.

Confluência de tempos: as versões "com 60 min" só operam a favor da tendência do
gráfico de 60 minutos (MME9 acima da MME21 para comprar, abaixo para vender).
"""
from __future__ import annotations

from ..intraday import Higher, dow_structure, ema_aligned
from ..models import Bar, Entry, Side
from .daytrade import _MultiTimeframe

LONG, SHORT = Side.LONG, Side.SHORT


def _upper(tl) -> Higher:
    """Tempo gráfico de cima para o swing: diário a partir do 60 min, semanal a partir do
    diário. Um bloco só conta como fechado quando começa o seguinte (sem olhar o futuro)."""
    intraday = tl.step < 24 * 60 and len(set(tl.dates[:50])) < len(tl.dates[:50])
    key = (lambda d: d) if intraday else (lambda d: tuple(d.isocalendar())[:2])
    out: list[Bar] = []
    done_at: list[int] = []
    group: list[Bar] = []
    cur = None
    for i, b in enumerate(tl.bars):
        k = key(tl.dates[i])
        if k != cur and group:
            out.append(Bar(group[0].ts, group[0].open, max(x.high for x in group), min(x.low for x in group), group[-1].close, sum(x.volume for x in group)))
            group = []
        cur = k
        group.append(b)
        done_at.append(len(out))
    return Higher(out, done_at)


class _Setup(_MultiTimeframe):
    """Base: médias no gráfico de gatilho e tendência do 60 min para a confluência."""

    context_days = 5
    valid_bars = 1

    def __init__(self, confluence: bool = False, swing: bool = False, **kw):
        super().__init__(**kw)
        self.confluence = confluence
        self.swing = swing
        if swing:
            # swing: pode dormir posicionado; o tempo gráfico de cima é o diário (para o
            # 60 min) ou o semanal (para o diário)
            self.day_trade = False
            self.name = self.name.replace(" + 60 min", "").replace(" + 15 min", "").replace(" + 60/15 min", "")
            self.name = f"{self.name} swing" + (" + tempo de cima" if confluence else "")
        elif confluence:
            self.name = f"{self.name} + 60 min"

    @property
    def window(self) -> int:
        return 400 if self.swing else super().window

    def _compute(self, tl):
        if not self.swing:
            return super()._compute(tl)
        self.h1 = self.m15 = _upper(tl)
        self._extra(tl)

    def decide(self, bars):
        if not self.swing:
            return super().decide(bars)
        i = self._at(bars)
        return None if i is None else self._entry(self._tl, i)

    def exit_signal(self, bars, side):
        if not self.swing:
            return super().exit_signal(bars, side)
        i = self._at(bars)
        return False if i is None else self._exit(self._tl, i, side)

    def _extra(self, tl):
        closes = [b.close for b in tl.bars]
        self.ema9 = ema_aligned(closes, 9)
        self.ema21 = ema_aligned(closes, 21)
        h1 = [b.close for b in self.h1.bars]
        self.h1_e9, self.h1_e21 = ema_aligned(h1, 9), ema_aligned(h1, 21)
        self._setup_extra(tl)

    def _setup_extra(self, tl):
        pass

    def _h1_side(self, i: int) -> Side | None:
        j = self.h1.last(i)
        if j is None or self.h1_e9[j] is None or self.h1_e21[j] is None:
            return None
        return LONG if self.h1_e9[j] > self.h1_e21[j] else SHORT

    def _ok(self, i: int, side: Side) -> bool:
        return not self.confluence or self._h1_side(i) is side

    def _today(self, tl, i: int, n: int) -> bool:
        """Os últimos n candles são todos do dia de hoje (no swing, só precisa existir)."""
        if self.swing:
            return i >= n - 1
        return tl.day_index[i] >= n - 1

    def _arm(self, tl, i: int, side: Side, stop: float, reason: str) -> Entry | None:
        if not self._ok(i, side):
            return None
        b = tl.bars[i]
        trigger = b.high if side is LONG else b.low
        return Entry(reason, side, stop, trigger, self.valid_bars)

    def _ema_turned(self, i: int, ema, side: Side) -> bool:
        if i < 2 or ema[i - 2] is None:
            return False
        if side is LONG:
            return ema[i - 1] < ema[i - 2] and ema[i] > ema[i - 1]
        return ema[i - 1] > ema[i - 2] and ema[i] < ema[i - 1]

    def _exit(self, tl, i, side):
        # saída padrão: a MME9 do gatilho vira contra
        e = self.ema9
        if i < 1 or e[i - 1] is None:
            return False
        return e[i] < e[i - 1] if side is LONG else e[i] > e[i - 1]


class LarryWilliams91(_Setup):
    """Larry Williams, setup 9.1 (popular no Brasil): a MME9 vira; compra acima da máxima
    do candle que virou a média para cima (venda abaixo da mínima do que virou para baixo).
    Stop no outro extremo do candle. Sai quando a MME9 vira contra.
    Fonte: https://www.tradingview.com/script/z4ElukQB/"""

    name = "Larry Williams 9.1"
    description = "Virada da MME9; entra no rompimento do candle que virou a média."

    def _entry(self, tl, i):
        if not self._today(tl, i, 3):
            return None
        b = tl.bars[i]
        if self._ema_turned(i, self.ema9, LONG):
            return self._arm(tl, i, LONG, b.low, "9.1: MME9 virou para cima")
        if self._ema_turned(i, self.ema9, SHORT):
            return self._arm(tl, i, SHORT, b.high, "9.1: MME9 virou para baixo")
        return None


class LarryWilliams92(_Setup):
    """Larry Williams, setup 9.2: MME9 subindo e um candle fecha abaixo da mínima do
    anterior (recuo); compra acima da máxima dele, valendo também no candle seguinte.
    Stop na mínima do candle do setup. Inverso para venda.
    Fonte: https://www.tradingview.com/script/z4ElukQB/"""

    name = "Larry Williams 9.2"
    description = "MME9 a favor, candle fecha além do extremo do anterior; entra no rompimento."
    valid_bars = 2

    def _entry(self, tl, i):
        if not self._today(tl, i, 2) or self.ema9[i - 1] is None:
            return None
        b, prev = tl.bars[i], tl.bars[i - 1]
        if self.ema9[i] > self.ema9[i - 1] and b.close < prev.low:
            return self._arm(tl, i, LONG, b.low, "9.2: recuo com MME9 subindo")
        if self.ema9[i] < self.ema9[i - 1] and b.close > prev.high:
            return self._arm(tl, i, SHORT, b.high, "9.2: repique com MME9 caindo")
        return None


class LarryWilliams93(_Setup):
    """Larry Williams, setup 9.3: MME9 subindo e dois fechamentos seguidos abaixo do
    fechamento de referência; compra acima da máxima do último. Stop na menor mínima dos
    dois. Inverso para venda.
    Fonte: https://www.tradingview.com/script/z4ElukQB/"""

    name = "Larry Williams 9.3"
    description = "MME9 a favor, dois fechamentos contra; entra no rompimento do último."
    valid_bars = 2

    def _entry(self, tl, i):
        if not self._today(tl, i, 3) or self.ema9[i - 1] is None:
            return None
        c = [tl.bars[k].close for k in (i - 2, i - 1, i)]
        b, prev = tl.bars[i], tl.bars[i - 1]
        if self.ema9[i] > self.ema9[i - 1] and c[1] < c[0] and c[2] < c[0]:
            return self._arm(tl, i, LONG, min(b.low, prev.low), "9.3: dois fechamentos abaixo com MME9 subindo")
        if self.ema9[i] < self.ema9[i - 1] and c[1] > c[0] and c[2] > c[0]:
            return self._arm(tl, i, SHORT, max(b.high, prev.high), "9.3: dois fechamentos acima com MME9 caindo")
        return None


class Stormer123(_Setup):
    """Stormer (Alexandre Wolwacz), setup 123 de compra: com MME8 acima da MME80 e o preço
    acima da MME8, três candles em que o do meio tem a menor mínima (fundo), todos acima
    da MME8; compra acima da máxima do terceiro, stop na mínima do segundo, alvo 2x o risco.
    Inverso para venda.
    Fonte: https://br.tradingview.com/script/r7dHB8Ir-J2S-Backtest-123-Stormer-Strategy"""

    name = "Stormer 123"
    description = "Tendência pela MME8/MME80; fundo de 3 candles acima da MME8; entra no rompimento."

    def _setup_extra(self, tl):
        closes = [b.close for b in tl.bars]
        self.ema8, self.ema80 = ema_aligned(closes, 8), ema_aligned(closes, 80)

    def _entry(self, tl, i):
        if not self._today(tl, i, 3) or self.ema80[i] is None:
            return None
        a, b, c = tl.bars[i - 2], tl.bars[i - 1], tl.bars[i]
        e8 = self.ema8[i]
        if self.ema8[i] > self.ema80[i] and c.close > e8 and a.low > b.low < c.low and min(a.low, b.low, c.low) > e8:
            return self._arm(tl, i, LONG, b.low, "123 de compra acima da MME8")
        if self.ema8[i] < self.ema80[i] and c.close < e8 and a.high < b.high > c.high and max(a.high, b.high, c.high) < e8:
            return self._arm(tl, i, SHORT, b.high, "123 de venda abaixo da MME8")
        return None


class PontoContinuo(_Setup):
    """Ponto Contínuo (ensinado pelo Stormer): com a MME21 subindo, o preço recua e toca a
    média, mas fecha acima dela; compra acima da máxima desse candle, stop na mínima.
    Inverso para venda. Sai quando o preço fecha do outro lado da MME21.
    Fonte: https://id.tradingview.com/script/9gJmFKz3-Continuous-Point-zauoyds"""

    name = "Ponto Contínuo (MME21)"
    description = "Continuação de tendência: toque na MME21 a favor; entra no rompimento do candle."

    def _entry(self, tl, i):
        if not self._today(tl, i, 2) or i < 5 or self.ema21[i - 5] is None:
            return None
        b, e = tl.bars[i], self.ema21[i]
        rising, falling = e > self.ema21[i - 5], e < self.ema21[i - 5]
        if rising and b.low <= e < b.close:
            return self._arm(tl, i, LONG, b.low, "Ponto Contínuo: tocou a MME21 subindo")
        if falling and b.high >= e > b.close:
            return self._arm(tl, i, SHORT, b.high, "Ponto Contínuo: tocou a MME21 caindo")
        return None

    def _exit(self, tl, i, side):
        e = self.ema21[i]
        if e is None:
            return False
        return tl.bars[i].close < e if side is LONG else tl.bars[i].close > e


class StructureFailure(_Setup):
    """Falha de estrutura (2B de Victor Sperandeo, "Trader Vic"): com o 15 min em tendência
    de alta (Teoria de Dow), o gráfico de gatilho perde o último fundo e volta a fechar
    acima dele (o rompimento falhou); compra acima da máxima desse candle, stop na mínima.
    Inverso para venda.
    Fonte: https://www.thepatternsite.com/2B.html"""

    name = "Falha de estrutura (2B) + 15 min"
    description = "15 min em tendência; no gatilho, rompimento falso do último fundo/topo; entra a favor."

    def _setup_extra(self, tl):
        self.dow = dow_structure(tl.bars, 2)
        self.dow_m15 = dow_structure(self.m15.bars, 2)

    def _entry(self, tl, i):
        if not self._today(tl, i, 2):
            return None
        q = self.m15.last(i)
        if q is None:
            return None
        trend = self.dow_m15.trend[q]
        b = tl.bars[i]
        low, high = self.dow.last_low[i - 1], self.dow.last_high[i - 1]
        if trend == "alta" and low is not None and b.low < low < b.close:
            return self._arm(tl, i, LONG, b.low, "falha de estrutura: perdeu o fundo e voltou (15 min em alta)")
        if trend == "baixa" and high is not None and b.high > high > b.close:
            return self._arm(tl, i, SHORT, b.high, "falha de estrutura: passou do topo e voltou (15 min em baixa)")
        return None


class FibonacciPullback(_Setup):
    """Continuação com Fibonacci: com o 60 min em tendência (MME9 x MME21) e o 15 min com
    topos e fundos a favor, o preço do gatilho recua para a zona de 38,2% a 61,8% do último
    impulso e fecha a favor; compra acima da máxima do candle, stop abaixo de 78,6%.
    Inverso para venda.
    Fonte: https://www.investopedia.com/terms/f/fibonacciretracement.asp"""

    name = "Fibonacci 38-62% + 60/15 min"
    description = "Recuo até a zona de Fibonacci do último impulso, a favor do 60 e do 15 min."

    def _setup_extra(self, tl):
        self.dow = dow_structure(tl.bars, 2)
        self.dow_m15 = dow_structure(self.m15.bars, 2)

    def _entry(self, tl, i):
        if not self._today(tl, i, 2):
            return None
        side = self._h1_side(i)
        q = self.m15.last(i)
        if side is None or q is None:
            return None
        want = "alta" if side is LONG else "baixa"
        if self.dow_m15.trend[q] != want:
            return None
        lo, hi = self.dow.last_low[i], self.dow.last_high[i]
        if lo is None or hi is None or hi <= lo:
            return None
        size = hi - lo
        b = tl.bars[i]
        if side is LONG and b.close > b.open and hi - 0.618 * size <= b.low <= hi - 0.382 * size:
            return Entry("Fibonacci: recuo de 38-62% com 60 e 15 min em alta", LONG, hi - 0.786 * size, b.high, 2)
        if side is SHORT and b.close < b.open and lo + 0.382 * size <= b.high <= lo + 0.618 * size:
            return Entry("Fibonacci: repique de 38-62% com 60 e 15 min em baixa", SHORT, lo + 0.786 * size, b.low, 2)
        return None


class StormerIFR2(_Setup):
    """IFR2 do Stormer (Larry Connors no original): a favor do 60 min, compra quando o
    IFR de 2 períodos cai abaixo de 5 e vende quando passa de 70 (inverso para venda,
    acima de 95 e abaixo de 30). Entrada no fechamento, sem ordem stop.
    Fonte: https://smarttbot.com/assets/data/Ebook-IFR2"""

    name = "IFR2 (Stormer) + 60 min"
    description = "A favor do 60 min, compra com IFR2 abaixo de 5 e sai acima de 70."

    def _setup_extra(self, tl):
        from ..indicators import rsi

        closes = [b.close for b in tl.bars]
        self.rsi2 = [rsi(closes[max(0, k - 2) : k + 1], 2) if k >= 2 else None for k in range(len(closes))]

    def _entry(self, tl, i):
        r = self.rsi2[i]
        side = self._h1_side(i)
        if r is None or side is None or not self._today(tl, i, 3):
            return None
        if side is LONG and r < 5:
            return Entry(f"IFR2 em {r:.0f} a favor do 60 min", LONG)
        if side is SHORT and r > 95:
            return Entry(f"IFR2 em {r:.0f} a favor do 60 min", SHORT)
        return None

    def _exit(self, tl, i, side):
        r = self.rsi2[i]
        return r is not None and (r > 70 if side is LONG else r < 30)
