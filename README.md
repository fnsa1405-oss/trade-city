# Trade City

Mesa de operações com traders de IA. Cada trader é especialista num ativo, e toda ordem passa pela mesma linha de produção antes de chegar à corretora:

1. **Analista**: lê os candles do ativo e gera o sinal de compra.
2. **Guardião de Risco**: define stop loss (2 ATR), stop gain (2x o risco) e o tamanho, ajustado pelo humor do trader.
3. **Auditor**: confere todas as travas. Só o que ele aprova vira ordem.
4. **Execução**: envia a ordem para a corretora. Por padrão é a **corretora simulada** da própria mesa: preços reais (Coinbase e Yahoo Finance), dinheiro de mentira, sem conta e sem bloqueio de país.
5. **Placar**: registra vitória ou derrota e atualiza o humor.

> Trade é risco. Nada aqui garante lucro e nada aqui é recomendação de investimento.

## O elenco

| Trader | Ativo | Tempo gráfico | Estratégia | Situação |
| --- | --- | --- | --- | --- |
| Rui Xis (`rui`) | XRP/USD | 4h | Donchian em conjunto (Zarattini/Pagani/Barbon), stop 2 ATR | aprovado na escola |
| Teo Chip (`teo`) | QQQ (Nasdaq 100) | day trade: 60/15 min + gatilho 5 min | Heikin-Ashi + MME 9/21, stop no recuo, sai na virada do HA de 15 min | aprovado na escola de day trade |
| Dona Lena (`lena`) | SPY (S&P 500) | day trade: 60/15 min + gatilho 5 min | Heikin-Ashi + MME 9/21, stop no recuo, alvo 3x | aprovada na escola de day trade |
| Bia Satoshi (`bia`) | BTC/USD | - | - | na escola |
| Edu Éter (`edu`) | ETH/USD | - | - | na escola |
| Sol Ventura (`sol`) | SOL/USD | - | - | na escola |
| Dora Doge (`dora`) | DOGE/USD | - | - | na escola |
| Davi Dow (`davi`) | DIA (Dow Jones) | day trade 5/1 min | - | na escola de day trade |
| Ivo Miúdo (`ivo`) | IWM (Russell 2000) | day trade 5/1 min | - | na escola de day trade |

Atenção: Teo e Lena foram aprovados no day trade com só 43 pregões de histórico (o que o Yahoo guarda). É pouco. Os 30 dias de mesa simulada são o teste de verdade, e a escola roda de novo quando o histórico crescer.

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

**Stops na corretora:** toda compra já vai com stop loss e stop gain. Na corretora simulada eles funcionam como uma ordem OCO: a cada ciclo ela confere os candles de 1 hora desde a última verificação e executa o stop ou o alvo que o preço tocou, mesmo que a mesa estivesse desligada naquela hora. Se um candle tocou os dois, conta o stop. Custos simulados: 0,1% de taxa por lado em cripto e 0,05% de derrapagem em tudo.

## Como usar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m trade_city traders              # lista o elenco
python -m trade_city backtest bia --dias 730   # dados públicos, sem conta
python -m trade_city backtest lena --dias 1100
python -m trade_city backtest teo --dias 59
python -m trade_city rodar               # um ciclo na corretora simulada
python -m trade_city rodar --loop 60      # um ciclo por minuto
python -m trade_city placar               # placar do dia
python -m trade_city panico               # zera e trava tudo
python -m trade_city destravar
```

Tudo que a mesa decide fica em `trade_city.db` (SQLite): cada sinal, cada recusa com o motivo e cada operação.

## Escola de traders (antes da conta real)

`python -m trade_city escola` (ou a aba **Actions** > **Escola**) testa, para cada trader de cripto, 17 estratégias × até 4 ajustes de stop/alvo × tempos gráficos (1h, 4h e diário). Os traders de day trade testam 6 estratégias × 4 ajustes × gatilho de 5 ou 1 minuto. A combinação é escolhida nos 70% iniciais do histórico (treino: fator de lucro ≥ 1,3, queda ≤ 15%, ≥ 30 operações) e só é aprovada se confirmar nos 30% finais, que ela nunca viu (prova: fator de lucro ≥ 1,1, resultado positivo, ≥ 10 operações). 

Além das estratégias da casa, a escola testa estratégias que traders conhecidos divulgaram publicamente (`trade_city/strategies/published.py`):

| Estratégia | Autor | Regra (versão só compra) | Fonte |
| --- | --- | --- | --- |
| Turtle sistemas 1 e 2 | Richard Dennis | Rompe a máxima de 20 (ou 55) candles, sai na mínima de 10 (ou 20) | [IG](https://www.ig.com/uk/trading-strategies/turtle-trading--what-is-it-and-what-are-the-rules--180904) |
| RSI(2) | Larry Connors | Acima da MM200, IFR(2) ≤ 5, sai acima da MM5 | [StockCharts](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2) |
| Double 7s | Larry Connors | Acima da MM200, menor fechamento de 7, sai no maior de 7 | [The Right Trader](https://therighttrader.com/learn/trading-strategies/double-sevens-strategy) |
| Holy Grail | Linda Raschke | ADX(14) > 30, recuo até a MME20, rompe a máxima anterior | [The Right Trader](https://therighttrader.com/learn/trading-strategies/holy-grail-setup) |
| Rompimento de volatilidade | Larry Williams | Fecha acima de abertura + 0,5 × amplitude anterior, sai no candle seguinte | [LuxAlgo](https://www.luxalgo.com/library/concept/volatility-breakout/) |

Adaptações: só compra, entrada na abertura do candle seguinte e stop loss do Guardião sempre ligado, mesmo onde o autor não usava stop (Connors).

Estratégias atuais de cripto (pesquisa de 27/11/2026, `trade_city/strategies/crypto.py`):

| Estratégia | Autor | Regra (só compra) | Fonte |
| --- | --- | --- | --- |
| Donchian em conjunto | Zarattini, Pagani e Barbon (2025) | Canais de 5 a 360 candles votam; compra com a maioria, cada canal sai no meio do canal | [Concretum](https://concretumgroup.com/catching-crypto-trends-a-tactical-approach-for-bitcoin-and-altcoins/) |
| Supertrend 10/3 | Olivier Seban | Compra na virada do Supertrend para alta, sai na virada para baixa | [Investopedia](https://www.investopedia.com/supertrend-indicator-7976167) |
| Heikin-Ashi + MME50 | Dan Valcu | Acima da MME50, compra quando o HA vira verde após 2 vermelhos, sai no 1º vermelho | [Investopedia](https://www.investopedia.com/trading/heikin-ashi-better-candlestick/) |
| Teoria de Dow | Charles Dow | Fundo mais alto e rompimento do último topo; sai na perda do último fundo | [Investopedia](https://www.investopedia.com/terms/d/dowtheory.asp) |
| Abertura da Ásia na segunda | Concretum Research (2025) | Compra domingo 19h de Nova York acima da média de 20 dias, vende 24h depois | [Concretum](https://concretumgroup.com/seasonality-in-bitcoin-intraday-trend-trading/) |

### Escola de day trade (QQQ, SPY, DIA, IWM)

Leitura em vários tempos gráficos: o 60 min dá o contexto e a decisão, o 15 min confirma e o gatilho sai no candle de 5 ou 1 minuto (a escola testa os dois). Opera comprado e vendido, o stop vem do gráfico (fundo ou topo do gatilho), não abre nada depois das 15h e zera tudo às 15h50 de Nova York. Custo: 0,01% por lado (spread e corretagem de ETF líquido).

| Estratégia | Origem | Regra | Fonte |
| --- | --- | --- | --- |
| ORB 5 min e 15 min | Zarattini e Aziz (2023) | Lado do primeiro candle do pregão; stop no outro extremo; alvo 10x ou fim do dia | [SSRN](https://papers.ssrn.com/abstract=4416622) |
| Área de ruído + VWAP | Zarattini, Aziz e Barbon (2024) | Nas meias horas, fora da área de ruído de 14 dias e da VWAP; stop móvel no limite/VWAP | [CXO Advisory](https://www.cxoadvisory.com/momentum-investing/complex-intraday-time-series-momentum-strategy-applied-to-spy/) |
| Heikin-Ashi + MME 9/21 | Dan Valcu (HA) | 60 min com MME9 > MME21 e HA a favor, 15 min acima da MME21, gatilho na virada do HA após recuo, VWAP a favor | [Investopedia](https://www.investopedia.com/trading/heikin-ashi-better-candlestick/) |
| Teoria de Dow em 3 tempos | Charles Dow | 60 e 15 min com topos e fundos a favor; gatilho no rompimento do último topo/fundo | [Investopedia](https://www.investopedia.com/terms/d/dowtheory.asp) |
| Dow 60 min + gatilho Heikin-Ashi | combinação pedida | Tendência de Dow no 60 min, gatilho na virada do HA, VWAP a favor | - |

Uma réplica independente do ORB com custos ([mql5, 2026](https://www.mql5.com/en/blogs/post/776235)) mostrou que a vantagem bruta quase some depois dos custos. Por isso a escola cobra custos e exige a prova fora da amostra.

**Histórico intradiário:** o Yahoo só guarda 60 dias de 5 min e 30 dias de 1 min, pouco para a escola (que pede 30 operações no treino). Duas saídas:

1. O workflow **Coleta de candles** guarda os candles de 5 e 1 min todo dia útil no branch `dados-intraday`. O histórico cresce sozinho.
2. Com uma chave gratuita da [Massive](https://massive.com) (antiga Polygon.io) no segredo `MASSIVE_API_KEY` do repositório, a escola baixa cerca de 2 anos de candles de 1 min.

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

### Mesa simulada (30 dias antes de qualquer dinheiro real)

O workflow **Mesa simulada** roda sozinho a cada 30 minutos com os traders aprovados na escola. Para ver como está:

1. Aba **Actions** > **Mesa simulada** > a rodada mais recente.
2. O resumo (Summary) mostra o que cada trader fez e o placar.

O livro de registros e o placar ficam no branch `mesa-dados` (arquivo `placar.txt`).

O day trade tem uma mesa própria, **Mesa day trade**: roda durante o pregão de Nova York, olha o mercado a cada minuto e decide a cada candle de 5 minutos fechado. O pregão é dividido em duas rodadas (até 12h45 e até o fechamento), porque um job do GitHub dura no máximo 6 horas. O placar fica no branch `mesa-daytrade`. Para rodar na hora, use **Run workflow**.

Conta real só depois de 30 dias de mesa simulada aprovados e com liberação explícita do dono.

Os candles vêm de fontes públicas: Coinbase para o Bitcoin e Yahoo Finance para QQQ e SPY. O Yahoo só guarda 60 dias de candles de 5 minutos, então o backtest do Teo cobre só esse período.
