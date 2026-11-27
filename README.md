# Trade City

Mesa de operações com traders de IA. Cada trader é especialista num ativo, e toda ordem passa pela mesma linha de produção antes de chegar à corretora:

1. **Analista**: lê os candles do ativo e gera o sinal de compra.
2. **Guardião de Risco**: define stop loss (2 ATR), stop gain (2x o risco) e o tamanho, ajustado pelo humor do trader.
3. **Auditor**: confere todas as travas. Só o que ele aprova vira ordem.
4. **Execução**: envia a ordem para a Alpaca (conta **paper** por padrão).
5. **Placar**: registra vitória ou derrota e atualiza o humor.

> Trade é risco. Nada aqui garante lucro e nada aqui é recomendação de investimento.

## O elenco

| Trader | Ativo | Tempo gráfico | Estratégia | Situação |
| --- | --- | --- | --- | --- |
| Rui Xis (`rui`) | XRP/USD | 4h | Tendência 10/30, stop 1,5 ATR, alvo 3x | aprovado na escola |
| Teo Chip (`teo`) | QQQ (Nasdaq 100) | diário | Turtle sistema 1 (20/10), saída na mínima de 10 dias | aprovado na escola |
| Dona Lena (`lena`) | SPY (S&P 500) | diário | Turtle sistema 1 (20/10), saída na mínima de 10 dias | aprovada na escola |
| Bia Satoshi (`bia`) | BTC/USD | - | - | na escola |
| Edu Éter (`edu`) | ETH/USD | - | - | na escola |
| Sol Ventura (`sol`) | SOL/USD | - | - | na escola |
| Dora Doge (`dora`) | DOGE/USD | - | - | na escola |

Só os aprovados operam na mesa (`rodar`). Os demais continuam sendo testados pela escola.

Elenco, capital e parâmetros ficam em `trade_city/config.py`.

## Travas (`RiskConfig`)

| Trava | Valor |
| --- | --- |
| Risco por operação | 0,5% do capital do trader |
| Stop loss | obrigatório, 2 ATR |
| Stop gain | 2x o risco (o Auditor recusa menos de 1,5x) |
| Derrotas no dia | 5, depois o trader para até amanhã |
| Perda no dia | 3% do capital do trader |
| Queda desde o pico | 10%, o trader volta para a escola |
| Alavancagem | nenhuma |
| Botão de pânico | `python -m trade_city panico` zera tudo e trava a mesa |

**Humor:** perigo (3 derrotas seguidas) opera com 25% do tamanho, alerta (dia negativo) com 50%, normal com 100%, confiante (3 vitórias seguidas) com 125%. O humor nunca mexe nas travas.

**Stops na corretora:** em ações (QQQ, SPY) a compra já vai com stop loss e stop gain anexados (ordem bracket), então a Alpaca protege a posição mesmo com a mesa desligada. Em cripto a Alpaca não aceita stops anexados, então a mesa vigia o preço a cada ciclo. Por isso a Bia precisa da mesa rodando sem parar.

## Como usar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # coloque as chaves da conta PAPER da Alpaca

python -m trade_city traders              # lista o elenco
python -m trade_city backtest bia --dias 730   # dados públicos, sem conta
python -m trade_city backtest lena --dias 1100
python -m trade_city backtest teo --dias 59
python -m trade_city rodar --loop 60      # mesa rodando, um ciclo por minuto
python -m trade_city placar               # placar do dia
python -m trade_city panico               # zera e trava tudo
python -m trade_city destravar
```

Tudo que a mesa decide fica em `trade_city.db` (SQLite): cada sinal, cada recusa com o motivo e cada operação.

## Escola de traders (antes da conta real)

`python -m trade_city escola` (ou a aba **Actions** > **Escola**) testa, para cada trader, 12 estratégias × até 4 ajustes de stop/alvo × tempos gráficos (1h, 4h e diário em cripto; 1h e diário em ações). A combinação é escolhida nos 70% iniciais do histórico (treino: fator de lucro ≥ 1,3, queda ≤ 15%, ≥ 30 operações) e só é aprovada se confirmar nos 30% finais, que ela nunca viu (prova: fator de lucro ≥ 1,1, resultado positivo, ≥ 10 operações). 

Além das estratégias da casa, a escola testa estratégias que traders conhecidos divulgaram publicamente (`trade_city/strategies/published.py`):

| Estratégia | Autor | Regra (versão só compra) | Fonte |
| --- | --- | --- | --- |
| Turtle sistemas 1 e 2 | Richard Dennis | Rompe a máxima de 20 (ou 55) candles, sai na mínima de 10 (ou 20) | [IG](https://www.ig.com/uk/trading-strategies/turtle-trading--what-is-it-and-what-are-the-rules--180904) |
| RSI(2) | Larry Connors | Acima da MM200, IFR(2) ≤ 5, sai acima da MM5 | [StockCharts](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2) |
| Double 7s | Larry Connors | Acima da MM200, menor fechamento de 7, sai no maior de 7 | [The Right Trader](https://therighttrader.com/learn/trading-strategies/double-sevens-strategy) |
| Holy Grail | Linda Raschke | ADX(14) > 30, recuo até a MME20, rompe a máxima anterior | [The Right Trader](https://therighttrader.com/learn/trading-strategies/holy-grail-setup) |
| Rompimento de volatilidade | Larry Williams | Fecha acima de abertura + 0,5 × amplitude anterior, sai no candle seguinte | [LuxAlgo](https://www.luxalgo.com/library/concept/volatility-breakout/) |

Adaptações: só compra, entrada na abertura do candle seguinte e stop loss do Guardião sempre ligado, mesmo onde o autor não usava stop (Connors).

O rompimento de abertura do Teo fica fora da escola, porque o Yahoo só tem 60 dias de candles de 5 min.

1. **Backtest** de pelo menos 2 anos: fator de lucro acima de 1,3, queda máxima abaixo de 15% e pelo menos 100 operações. O comando `backtest` já diz se o trader passou.
2. **Paper trading** por pelo menos 30 dias, com resultados perto do backtest.
3. **Conta real** com capital pequeno por mais 30 dias.

A conta real só abre com `TRADE_CITY_MODE=live` **e** `TRADE_CITY_LIVE=EU_ACEITO_O_RISCO` no `.env`. Sem as duas, o programa se recusa a iniciar.

## Testes

```bash
python -m pytest -q
```

## Pelo celular (GitHub Actions)

Dá para rodar o backtest sem computador e sem conta em corretora, direto no GitHub:

1. Abra a aba **Actions** > **Backtest** > **Run workflow**, escolha o trader e confirme.
2. Quando terminar, abra a execução: o resultado aparece no resumo (Summary).

Os candles vêm de fontes públicas: Coinbase para o Bitcoin e Yahoo Finance para QQQ e SPY. O Yahoo só guarda 60 dias de candles de 5 minutos, então o backtest do Teo cobre só esse período.
