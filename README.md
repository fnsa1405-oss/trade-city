# Trade City

Mesa de operações com traders de IA. Cada trader é especialista num ativo, e toda ordem passa pela mesma linha de produção antes de chegar à corretora:

1. **Analista**: lê os candles do ativo e gera o sinal de compra.
2. **Guardião de Risco**: define stop loss (2 ATR), stop gain (2x o risco) e o tamanho, ajustado pelo humor do trader.
3. **Auditor**: confere todas as travas. Só o que ele aprova vira ordem.
4. **Execução**: envia a ordem para a Alpaca (conta **paper** por padrão).
5. **Placar**: registra vitória ou derrota e atualiza o humor.

> Trade é risco. Nada aqui garante lucro e nada aqui é recomendação de investimento.

## O elenco

| Trader | Ativo | Tempo gráfico | Estratégia |
| --- | --- | --- | --- |
| Bia Satoshi (`bia`) | BTC/USD | 1h | Seguidor de tendência: MM20 > MM50 e rompimento da máxima de 20 candles |
| Teo Chip (`teo`) | QQQ (Nasdaq 100) | 5 min | Rompimento da faixa dos primeiros 30 min, zera antes do fechamento |
| Dona Lena (`lena`) | SPY (S&P 500) | diário | Retorno à média: IFR(2) < 10 acima da MM200, sai acima da MM5 |

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
python -m trade_city backtest bia --dias 730
python -m trade_city backtest lena --dias 1100
python -m trade_city backtest teo --dias 730
python -m trade_city rodar --loop 60      # mesa rodando, um ciclo por minuto
python -m trade_city placar               # placar do dia
python -m trade_city panico               # zera e trava tudo
python -m trade_city destravar
```

Tudo que a mesa decide fica em `trade_city.db` (SQLite): cada sinal, cada recusa com o motivo e cada operação.

## Escola de traders (antes da conta real)

1. **Backtest** de pelo menos 2 anos: fator de lucro acima de 1,3, queda máxima abaixo de 15% e pelo menos 100 operações. O comando `backtest` já diz se o trader passou.
2. **Paper trading** por pelo menos 30 dias, com resultados perto do backtest.
3. **Conta real** com capital pequeno por mais 30 dias.

A conta real só abre com `TRADE_CITY_MODE=live` **e** `TRADE_CITY_LIVE=EU_ACEITO_O_RISCO` no `.env`. Sem as duas, o programa se recusa a iniciar.

## Testes

```bash
python -m pytest -q
```

## Pelo celular (GitHub Actions)

Dá para rodar o backtest sem computador, direto no GitHub:

1. Na Alpaca, na conta **Paper**, gere as chaves (API Key e Secret Key).
2. No GitHub, abra o repositório > **Settings** > **Secrets and variables** > **Actions** > **New repository secret** e cadastre `ALPACA_API_KEY` e `ALPACA_SECRET_KEY`.
3. Abra a aba **Actions** > **Backtest** > **Run workflow**, escolha o trader e confirme.
4. Quando terminar, abra a execução: o resultado aparece no resumo (Summary).
