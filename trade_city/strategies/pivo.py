"""Pivô v2, o operacional do Levy (dossiê de 26/11/2026), traduzido em regras objetivas.

O que veio do dossiê (FATO, regras do próprio Levy):
- Gráfico de 2 minutos (ou 1) do futuro do Nasdaq; uma média aritmética de 20 (M20).
- Sequência: 1) swing, 2) rompimento por fechamento, 3) reteste, 4) gatilho. Sem a sequência
  completa, não há trade.
- Swing: candle com máxima (mínima) maior (menor) que a dos 2 candles de cada lado.
- Rompimento: um candle FECHA além do swing (acima do topo na compra, abaixo do fundo na venda).
- Reteste: o preço volta ao nível rompido.
- Gatilho: o preço rompe o novo topo (compra) ou novo fundo (venda) formado depois do
  rompimento. Entrada no fechamento do candle do gatilho.
- Stop A: 1 tick além da mínima (compra) ou máxima (venda) do reteste que antecede o gatilho.
- Alvos fixos na entrada, pela projeção de Fibonacci do movimento anterior: continuação
  61%, 100% e 161%; correção 50% e 61,8%. Sem break-even. Hoje sai sempre no alvo 1.
- Continuação = a favor da M20; correção = contra a M20.
- Camada 3 = só o padrão (o backtest dele); camada 2 = padrão alinhado à M20.
- Sessão de Nova York: da abertura até 16h de Brasília.

O que o dossiê NÃO define e aqui virou premissa (está escrito para o Levy conferir):
- "Movimento anterior" da projeção: A = menor mínima entre o swing rompido e o candle do
  rompimento (onde a perna começou) e B = maior máxima depois do rompimento (o novo topo).
  O movimento A -> B é projetado a partir de B: alvo = B + k x (B - A), e o alvo 2 (100%) é o
  "espelho do movimento". Conferência: com essa leitura, o alvo 1 fica em ~0,3R a 1,5R
  (mediana 0,7R) nos candles do QQQ, perto do 0,52R a 2,42R (mediana 1R) do backtest dele.
  A outra leitura possível (extensão a partir do reteste, C + k x (B - A)) daria mediana de
  0,3R e quase 2/3 dos alvos atrás da entrada, o que não bate com os números dele.
- Gatilho por fechamento acima do novo topo (o dossiê diz "rompe" e "entrada quando o
  candle do gatilho fecha").
- O reteste vale com o toque no nível (mínima <= nível na compra). Um fechamento abaixo de A
  (compra) cancela o padrão: a estrutura quebrou para o outro lado.
- Alinhado à M20: o fechamento do gatilho está do lado da operação (acima da M20 na compra).
  Modo: continuação se a M20 aponta a favor (comparada com 10 candles antes); senão, correção.
- Os swings e o padrão recomeçam a cada pregão (só há candles do pregão regular).
- Ficaram de fora, por não terem regra objetiva: viés do dia, regiões, filtro de
  lateralidade (linhas desenhadas à mão) e "stop caro".
- A sessão da Ásia (22h às 0h de Brasília) não tem histórico aqui: a escola usa os candles
  do ETF QQQ (pregão regular), convertidos para o micro MNQ.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

from ..intraday import NY, higher_timeframe
from ..models import Entry, Side
from .daytrade import DayTradeStrategy
from .medias import sma_aligned

LONG, SHORT = Side.LONG, Side.SHORT
SP = ZoneInfo("America/Sao_Paulo")
CONT_LEVELS = (0.618, 1.0, 1.618)  # alvos 1, 2 e 3 na continuação (61%, 100%, 161%)
CORR_LEVELS = (0.5, 0.618)  # alvos 1 e 2 na correção (50% e 61,8%)
TICK_FRAC = 0.25 / 21_000  # 1 tick do NQ/MNQ (0,25 ponto) em fração do preço
LAYERS = {3: "camada 3 (só o padrão)", 2: "camada 2 (alinhado à M20)"}


class _Setup:
    """Um padrão em andamento num lado: rompido -> reteste -> gatilho."""

    def __init__(self, level: float, origin: float):
        self.level = level  # nível do swing rompido
        self.a = origin  # início da perna (A da projeção)
        self.b: float | None = None  # novo topo/fundo depois do rompimento (B)
        self.c: float | None = None  # extremo do reteste (C)


class PivotV2(DayTradeStrategy):
    """Pivô v2 do Levy: swing, rompimento por fechamento, reteste e gatilho, com stop A e
    alvo na projeção de Fibonacci. `target` = 1, 2 ou 3 (alvo de saída); `layer` = 3 (só o
    padrão) ou 2 (alinhado à M20); `chart` = minutos do gráfico (2 ou 1)."""

    valid_bars = 1

    def __init__(self, target: int = 1, layer: int = 3, chart: int = 2, last_entry_sp: int = 16 * 60, **kw):
        super().__init__(**kw)
        self.target, self.layer, self.chart = target, layer, chart
        self.last_entry_sp = last_entry_sp
        self.name = f"Pivô v2 do Levy ({chart} min, {LAYERS[layer]}, alvo {target})"
        self.description = "Swing, rompimento por fechamento, reteste e gatilho; stop A; alvo pela projeção de Fibonacci."
        self.context_days = 2

    # cálculo antecipado, sem olhar o futuro: cada sinal usa só candles já fechados
    def _compute(self, tl):
        self.ok = tl.step == 1
        if not self.ok:
            return
        self.h = higher_timeframe(tl, self.chart)
        bars = self.h.bars
        closes = [b.close for b in bars]
        m20 = sma_aligned(closes, 20)
        self.signals: dict[int, tuple] = {}
        day = None
        swings_hi: list[tuple[int, float]] = []
        swings_lo: list[tuple[int, float]] = []
        res = sup = None  # último swing ainda não rompido: (índice, preço)
        up = dn = None  # padrões em andamento
        start = 0
        for j, b in enumerate(bars):
            d = b.ts.astimezone(NY).date()
            if d != day:  # novo pregão: recomeça a leitura
                day, start = d, j
                swings_hi, swings_lo, res, sup, up, dn = [], [], None, None, None, None
            # swing confirmado agora (2 candles de cada lado, todos do mesmo pregão)
            k = j - 2
            if k - 2 >= start:
                hk, lk = bars[k].high, bars[k].low
                around = bars[k - 2 : k] + bars[k + 1 : j + 1]
                if all(hk > x.high for x in around):
                    swings_hi.append((k, hk))
                    res = (k, hk)
                if all(lk < x.low for x in around):
                    swings_lo.append((k, lk))
                    sup = (k, lk)
            sig = None
            # ---- compra ----
            if up is not None:
                if b.close < up.a:
                    up = None  # quebrou a estrutura para baixo
                elif up.c is None:
                    up.b = max(up.b, b.high)
                    if b.low <= up.level:
                        up.c = b.low  # voltou ao nível rompido: reteste
                else:
                    if b.close > up.b:
                        sig = self._signal(LONG, b.close, up, m20, j)
                        up = None
                    else:
                        up.c = min(up.c, b.low)
            elif res is not None and j > res[0] and b.close > res[1] >= bars[j - 1].close:
                origin = min(x.low for x in bars[res[0] : j + 1])
                up = _Setup(res[1], origin)
                up.b = b.high
                res = None
            # ---- venda ----
            if dn is not None:
                if b.close > dn.a:
                    dn = None
                elif dn.c is None:
                    dn.b = min(dn.b, b.low)
                    if b.high >= dn.level:
                        dn.c = b.high
                else:
                    if b.close < dn.b:
                        s2 = self._signal(SHORT, b.close, dn, m20, j)
                        sig = None if sig is not None else s2  # os dois lados no mesmo candle: fica de fora
                        dn = None
                    else:
                        dn.c = max(dn.c, b.high)
            elif sup is not None and j > sup[0] and b.close < sup[1] <= bars[j - 1].close:
                origin = max(x.high for x in bars[sup[0] : j + 1])
                dn = _Setup(sup[1], origin)
                dn.b = b.low
                sup = None
            if sig is not None:
                self.signals[j] = sig

    def _signal(self, side: Side, close: float, s: _Setup, m20, j):
        sign = side.sign
        leg = abs(s.b - s.a)
        if leg <= 0:
            return None
        stop = s.c - sign * TICK_FRAC * close
        avg, before = m20[j], m20[j - 10] if j >= 10 else None
        aligned = avg is not None and (close - avg) * sign > 0
        favour = avg is not None and before is not None and (avg - before) * sign > 0
        mode = "continuação" if favour else "correção"
        levels = CONT_LEVELS if favour else CORR_LEVELS
        targets = [s.b + sign * k * leg for k in levels]
        if (targets[0] - close) * sign <= 0:
            return None  # alvo 1 atrás da entrada: a projeção não dá trade
        return side, stop, targets, aligned, mode

    def _closed(self, tl, i) -> int | None:
        if i < 1 or self.h.done_at[i] == self.h.done_at[i - 1]:
            return None
        return self.h.last(i)

    def _entry(self, tl, i):
        if not self.ok:
            return None
        j = self._closed(tl, i)
        if j is None or j not in self.signals:
            return None
        ts = tl.bars[i].ts.astimezone(SP)
        if ts.hour * 60 + ts.minute + 1 > self.last_entry_sp:
            return None  # depois das 16h de Brasília: fora da janela dele
        sig = self.signals[j]
        if sig is None:
            return None
        side, stop, targets, aligned, mode = sig
        if self.layer == 2 and not aligned:
            return None
        n = min(self.target, len(targets))
        word = "compra" if side is LONG else "venda"
        pct = (CONT_LEVELS if mode == "continuação" else CORR_LEVELS)[n - 1]
        reason = f"Pivô: rompeu, retestou e deu gatilho ({word}, {mode}); stop A, alvo {n} ({pct:.1%} da perna)"
        return Entry(reason, side, stop, None, 1, targets[n - 1])
