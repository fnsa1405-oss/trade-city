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
| Teo Chip (`teo`) | QQQ (Nasdaq 100) | swing, diário | Turtle 20/10 (Richard Dennis) | aprovado em 28/11/2026 (prova: fator de lucro 1,42) |
| Dona Lena (`lena`) | SPY (S&P 500) | swing, diário | Turtle 20/10 (Richard Dennis) | aprovada em 28/11/2026 (prova: fator de lucro 1,59) |
| Bia Satoshi (`bia`) | BTC/USD | 4h | Rompimento de 55 com agressão de compra (fluxo de ordens) | aprovada em 28/11/2026 na escola de fluxo (prova: fator de lucro 1,25) |
| Edu Éter (`edu`) | ETH/USD | - | - | na escola |
| Sol Ventura (`sol`) | SOL/USD | diário | Momento de série temporal 28 | aprovada em 28/11/2026 (prova: fator de lucro 1,62) |
| Dora Doge (`dora`) | DOGE/USD | 4h | Rompimento de 20 com agressão de compra (fluxo de ordens) | aprovada em 28/11/2026 na escola de fluxo (prova: fator de lucro 1,82; antes Donchian, 1,17) |
| Davi Dow (`davi`) | DIA (Dow Jones) | swing, diário | Turtle 20/10 (Richard Dennis) | aprovado em 28/11/2026 (prova: fator de lucro 2,21) |
| Ivo Miúdo (`ivo`) | IWM (Russell 2000) | day trade, gatilho 1 min | ORB 5 min, alvo 2x | na escola (o cérebro tenta filtrar) |

Com 2 anos de candles de 1 min (Massive), nenhuma estratégia de day trade passou na prova (27/11/2026). A aprovação anterior de Teo e Lena, feita com só 43 pregões, era sorte de amostra pequena e foi desfeita. Cada um ficou com a melhor estratégia do treino, e o cérebro tenta torná-la lucrativa.

## Fluxo de ordens (order flow)

Delta (agressão de compra menos de venda), CVD, absorção, livro de ofertas e contratos em aberto (`trade_city/orderflow.py`, `trade_city/strategies/orderflow.py`).

- **Criptos, de graça**: os arquivos públicos da Binance ([data.binance.vision](https://data.binance.vision)) trazem o volume de agressão de cada candle desde 2017-2020, os contratos em aberto dos futuros a cada 5 min desde 2021 e o livro dos futuros (faixas de 1% a 5%) a cada ~30 s desde 2023. **Actions > Escola de fluxo** baixa e completa esse histórico no branch `dados-fluxo` e roda a escola com as mesmas regras e custos.
- **Livro ao vivo**: **Actions > Coleta do livro** fotografa o livro completo da Coinbase e soma as agressões da Coinbase e da Binance a cada 15 s, uma linha por minuto (`dados-fluxo/livro/`), em turnos encadeados.
- **Índices (MNQ, MES, MYM, M2K)**: o fluxo real da CME é pago (Databento, Rithmic, CQG) e o plano da Massive não inclui negócios. O delta é **estimado** pelos candles de 1 e 5 min (classificação de volume em bloco, Easley, López de Prado e O'Hara, 2012).
- A API principal da Binance e a da Bybit bloqueiam os servidores do GitHub (EUA); o `data-api.binance.vision` funciona e é o que a mesa usa ao vivo.

Escola de fluxo (28/11/2026): aprovadas Bia (BTC, rompimento 55 com agressão, 4h) e Dora (DOGE, rompimento 20 com agressão, 4h, trocou o Donchian). Sol e Rui também passaram, mas ficaram atrás das estratégias atuais e seguem com elas. No day trade com microcontratos, o ORB de 15 min com delta passou no SPY/MES (prova: 54 operações, fator de lucro 1,23); o encaixe na mesa de day trade fica com o trabalho dos microcontratos.

## Gestão de carteira

`python -m trade_city carteira` (ou **Actions > Carteira**), em `trade_city/carteira.py`:

- **Correlação** dos resultados diários: QQQ, SPY e DIA formam um grupo (até 0,63); as criptos quase não se correlacionam entre si nem com os índices.
- **Paridade de risco**: cada grupo recebe a mesma fatia de risco e, dentro dele, o inverso da volatilidade. Resultado: cada cripto com peso 1,4 e cada índice com 0,47 (o risco por operação é multiplicado pelo peso). Com os pesos, a carteira rendeu +6,5% ao ano no treino e +1,8% na prova, contra +4,8% e +1,0% com todos iguais.
- **Risco por operação**: calibrado de 0,25% a 2% com o backtest completo. 0,5% continua o escolhido: acima disso a trava de queda de 10% para Rui e Bia (o trader volta para a escola). A queda da carteira inteira fica pequena (até 8% em 2%), então o limite hoje é a trava por trader, não a carteira.
- **Limites da carteira** no Auditor: risco aberto somado até 3% do capital total e até 1,5% por grupo correlacionado.
- **Fim de semana** (pedido do Alexandre): no sábado e domingo de Nova York, com a bolsa fechada, as criptos operam com 1,5x o risco (`weekend_crypto_boost`). Na calibração com Bia e Dora novas, 1,5x subiu a prova de +1,8% para +2,3% ao ano com queda de 2,6%; 2x piorou o retorno por queda no treino.

## App da mesa ao vivo (celular)

A pasta `app/` é um app web instalável (PWA), publicado no GitHub Pages pelo workflow **Publicar o app**:
https://fnsa1405-oss.github.io/trade-city/ (no celular: menu do navegador > *Adicionar à tela inicial*).

- Lê o `estado.json` que cada rodada da mesa grava nos branches `mesa-dados` e `mesa-daytrade` (`python -m trade_city painel`).
- Preço ao vivo das criptos pela Coinbase (a cada 10 s) e o resultado em aberto das posições.
- Feed com cada passo da linha de produção (analista, cérebro, guardião, auditor, placar) e das rodadas no GitHub Actions.
- **Botão de pânico**: dispara o workflow **Botão de pânico** (`panico.yml`), que grava a ordem no branch `controle` e trava a mesa swing na hora. A mesa de day trade confere a ordem a cada minuto do pregão. Sem chave, o botão abre a página do workflow; com uma chave *fine-grained* (só Actions, só este repositório) salva em *Ajustes*, dispara em um toque.
- O escritório 3D entra no topo do app: ver `app/escritorio/LEIAME.md`.

## Cérebros (rede neural de cada trader)

`python -m trade_city cerebros` (ou **Actions** > **Treino dos cérebros**, todo sábado) dá a cada trader uma rede neural pequena (`trade_city/brain.py`). A estratégia continua achando as oportunidades. O cérebro olha o clima do gráfico na hora (tendência, volatilidade, distância das médias, IFR, volume, horário, lado) e estima a chance de dar certo. Abaixo do limite, o trader deixa passar.

- Treina nos 70% iniciais das operações e escolhe o limite numa validação dentro do treino.
- Só é **promovido** se, nos 30% finais (que nunca viu), filtrar melhor que operar sem ele: fator de lucro pelo menos 5% maior e acima de 1,1, resultado positivo e pelo menos 30% das operações mantidas.
- Trader com cérebro promovido entra na mesa simulada, mesmo sem aprovação da escola. Se a configuração do trader mudar, o cérebro antigo deixa de valer.
- Ele nunca mexe nas travas: stop, tamanho, perdas do dia e botão de pânico continuam com o Guardião e o Auditor.
- Técnica: *meta-labeling* (Marcos López de Prado, *Advances in Financial Machine Learning*, 2018).

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

**Pesquisa de 28/11/2026** (anomalias com estudos publicados e replicados):

| Estratégia | Estudo | Regra |
| --- | --- | --- |
| Momento de série temporal 28/56 | Moskowitz, Ooi e Pedersen (2012); Liu e Tsyvinski (2021) nas criptos | Compra quando o retorno de N candles vira positivo, acima da média de N; sai quando fica negativo |
| Virada do mês | Lakonishok e Smidt (1988); McConnell e Xu (2008) | Compra no último pregão do mês, sai no 3º pregão do mês seguinte |
| IBS < 0,2 | Pagonidis (2014, NAAIM) | Fechamento nos 20% de baixo do candle, acima da MM200; sai nos 20% de cima |
| IFR(2) acumulado | Connors e Alvarez (2008) | Acima da MM200, soma do IFR(2) de 2 dias abaixo de 35; sai com IFR(2) acima de 65 |

### Escola de day trade (QQQ, SPY, DIA, IWM)

Leitura em vários tempos gráficos: o 60 min dá o contexto e a decisão, o 15 min confirma e o gatilho sai no candle de 15, 5 ou 1 minuto (a escola testa os três). Opera comprado e vendido, o stop vem do gráfico (fundo ou topo do gatilho), não abre nada depois das 15h e zera tudo às 15h50 de Nova York. Custo: 0,01% por lado (spread e corretagem de ETF líquido).

| Estratégia | Origem | Regra | Fonte |
| --- | --- | --- | --- |
| ORB 5 min e 15 min | Zarattini e Aziz (2023) | Lado do primeiro candle do pregão; stop no outro extremo; alvo 10x ou fim do dia | [SSRN](https://papers.ssrn.com/abstract=4416622) |
| Área de ruído + VWAP | Zarattini, Aziz e Barbon (2024) | Nas meias horas, fora da área de ruído de 14 dias e da VWAP; stop móvel no limite/VWAP | [CXO Advisory](https://www.cxoadvisory.com/momentum-investing/complex-intraday-time-series-momentum-strategy-applied-to-spy/) |
| Heikin-Ashi + MME 9/21 | Dan Valcu (HA) | 60 min com MME9 > MME21 e HA a favor, 15 min acima da MME21, gatilho na virada do HA após recuo, VWAP a favor | [Investopedia](https://www.investopedia.com/trading/heikin-ashi-better-candlestick/) |
| Teoria de Dow em 3 tempos | Charles Dow | 60 e 15 min com topos e fundos a favor; gatilho no rompimento do último topo/fundo | [Investopedia](https://www.investopedia.com/terms/d/dowtheory.asp) |
| Dow 60 min + gatilho Heikin-Ashi | combinação pedida | Tendência de Dow no 60 min, gatilho na virada do HA, VWAP a favor | - |

**Setups de traders conhecidos** (só regras publicadas abertamente; versões "+ 60 min" só operam a favor da MME9 x MME21 do gráfico de 60 min). Entram por ordem stop: o setup arma no fechamento do candle e só entra se o preço romper a máxima (compra) ou a mínima (venda) dele.

| Setup | Quem ensina | Regra | Fonte |
| --- | --- | --- | --- |
| 9.1, 9.2 e 9.3 | Larry Williams (popularizados no Brasil) | Virada da MME9 (9.1), recuo de 1 candle (9.2) ou 2 fechamentos contra (9.3) com a MME9 a favor; sai quando a MME9 vira | [TradingView](https://www.tradingview.com/script/z4ElukQB/) |
| 123 | Stormer (Alexandre Wolwacz) | MME8 acima da MME80, fundo de 3 candles acima da MME8; stop no fundo | [TradingView](https://br.tradingview.com/script/r7dHB8Ir-J2S-Backtest-123-Stormer-Strategy) |
| Ponto Contínuo | Stormer | MME21 subindo, toque na média com fechamento acima; sai ao fechar do outro lado | [TradingView](https://id.tradingview.com/script/9gJmFKz3-Continuous-Point-zauoyds) |
| IFR2 | Stormer (Larry Connors no original) | A favor do 60 min, compra com IFR2 < 5 e sai com IFR2 > 70 | [SmarttBot](https://smarttbot.com/assets/data/Ebook-IFR2) |
| Falha de estrutura (2B) | Victor Sperandeo | 15 min em tendência de Dow; o gatilho perde o último fundo e volta; entra a favor | [Bulkowski](https://www.thepatternsite.com/2B.html) |
| Fibonacci 38-62% | retração clássica | 60 e 15 min a favor; recuo à zona de 38,2-61,8% do último impulso; stop em 78,6% | [Investopedia](https://www.investopedia.com/terms/f/fibonacciretracement.asp) |

**Wyckoff** (apostila enviada pelo Alexandre em 28/11/2026, regras em `strategies/wyckoff.py`): spring/upthrust (com e sem volume baixo), SOS + LPS e clímax (SC/BC) com absorção. Faixa = máxima/mínima de 40 candles com altura até 6 ATR; barra larga = 1,8x a amplitude média; volume alto = 1,5x a média de 60 candles, ultra-alto = 2x. Ficaram de fora as partes subjetivas (rotular as fases A a E, linhas desenhadas à mão, Market Profile).

**A favor das médias (pedido do Alexandre em 28/11/2026, `strategies/medias.py`):** só compra quando, em cada tempo de contexto, MME9 > MMA20 > MMA50 > MMA200 (inverso para vender). A escola testa três combinações de contexto (60/15/5, 60/15 e 15/5 min). O gatilho sai no gráfico de 2 minutos, num candle que toca a MME9 ou a MMA20: Ponto Contínuo, PFR (mínima abaixo da anterior e fechamento acima do anterior), engolfo, martelo ou candle de força (corpo de 70% e amplitude de 1,5x a média). Entra no rompimento do candle gatilho, stop no outro extremo, e sai se o 2 min fechar do outro lado da MMA20. Os candles de 2, 5, 15 e 60 min são montados a partir do 1 min.

**Swing nos índices:** os mesmos setups também rodam em swing (60 min e diário, pode dormir posicionado). A confluência passa a ser o tempo gráfico de cima: o diário para o 60 min e o semanal para o diário. Para testar: Actions > Escola > modo `swing`.

Nos gatilhos de 5 e 15 min, a escola confere entrada, stop e alvo minuto a minuto com os candles de 1 min. Sem isso, num candle que fez a mínima e depois rompeu a máxima, não dá para saber se o stop veio antes da entrada.

**Microcontratos (padrão do day trade desde 28/11/2026):** a escola e o backtest simulam MNQ (Nasdaq), MES (S&P 500), MYM (Dow) e M2K (Russell) em vez dos ETFs. O preço do ETF vira o valor de 1 contrato, a quantidade é sempre de contratos inteiros, a derrapagem é de 1 tick e a corretagem é de US$0,85 por contrato por lado. A margem é de US$1.000 por contrato. Se nem 1 contrato cabe no risco normal (0,5%), a escola aceita 1 contrato com risco de até 1% do capital; acima disso, recusa a operação (`trade_city/futures.py`).

Uma réplica independente do ORB com custos ([mql5, 2026](https://www.mql5.com/en/blogs/post/776235)) mostrou que a vantagem bruta quase some depois dos custos. Por isso a escola cobra custos e exige a prova fora da amostra.

**Histórico intradiário:** o Yahoo só guarda 60 dias de 5 min e 30 dias de 1 min, pouco para a escola (que pede 30 operações no treino). Duas saídas:

1. O workflow **Coleta de candles** guarda os candles de 5 e 1 min todo dia útil no branch `dados-intraday`. O histórico cresce sozinho. Desde 28/11/2026 também guarda o Ibovespa (`IBOV`, que o mini índice WIN acompanha) e o BOVA11 (com volume), no pregão da B3, para a escola testar o WIN quando houver meses de histórico (não há 2 anos de 1 min do WIN de graça).
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

### Relógio (agenda)

O agendador (cron) do GitHub não dispara neste repositório. O workflow **Relógio** faz esse papel: fica ligado em turnos de ~5h40, confere a agenda a cada minuto e dispara Mesa day trade (dias úteis, pregão), Coleta de candles (dias úteis, 18h20 de Brasília), Treino dos cérebros (sábado, 9h) e Escola (domingo, 9h). No fim de cada turno ele chama o próximo. Se um dia parar, basta abrir Actions > Relógio > Run workflow.

### Mesa simulada (30 dias antes de qualquer dinheiro real)

O workflow **Mesa simulada** roda sozinho a cada 30 minutos com os traders aprovados na escola. Para ver como está:

1. Aba **Actions** > **Mesa simulada** > a rodada mais recente.
2. O resumo (Summary) mostra o que cada trader fez e o placar.

O livro de registros e o placar ficam no branch `mesa-dados` (arquivo `placar.txt`).

O day trade tem uma mesa própria, **Mesa day trade**: roda durante o pregão de Nova York, olha o mercado a cada minuto e decide a cada candle de 5 minutos fechado. O pregão é dividido em duas rodadas (até 12h45 e até o fechamento), porque um job do GitHub dura no máximo 6 horas. O placar fica no branch `mesa-daytrade`. Para rodar na hora, use **Run workflow**.

Conta real só depois de 30 dias de mesa simulada aprovados e com liberação explícita do dono.

Os candles vêm de fontes públicas: Coinbase para o Bitcoin e Yahoo Finance para QQQ e SPY. O Yahoo só guarda 60 dias de candles de 5 minutos, então o backtest do Teo cobre só esse período.
