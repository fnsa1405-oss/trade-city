# Escritório 3D

O escritório 3D (pessoas Quaternius CC0, móveis Kenney CC0, Three.js) mora nesta pasta:
`index.html` + `app.js` + `assets/` + `lib/`. Ele abre de dois jeitos:

- **dentro do app**: `escritorio.js` coloca `index.html` num iframe no topo do app. O 3D usa
  o `window.TradeCity` da página principal (preços ao vivo inclusos) e esconde a própria barra.
- **tela cheia**: `escritorio/index.html` sozinho, com abas, barra e botão de pânico. Aí ele
  busca o `estado.json` dos branches da mesa direto (`aovivo.js`).

`estado.json` daqui define só a montagem da sala (quem senta onde, cores, equipe). Os números,
humor, posição, falas e a caminhada da ordem vêm da mesa de verdade (`aplicarAoVivo` em `app.js`):
a caminhada do Nico só acontece quando a mesa abre uma operação de verdade.

## Contrato antigo (para trocar o 3D por outro)

O app (`app/index.html`) tenta carregar `app/escritorio/escritorio.js` ao abrir.
Se o arquivo não existir, fica a cidade à noite feita em CSS. Para ligar o 3D,
basta criar esse arquivo (e o que mais ele precisar dentro desta pasta).

Contrato:

```js
// app/escritorio/escritorio.js
export async function montar(palco, tradeCity) {
  // palco: o <section id="escritorio"> do topo do app (16:10, cantos arredondados).
  //   Ponha um <canvas> ou um <div class="cena3d"> dentro dele; o CSS já estica
  //   os dois para ocupar o palco inteiro. O cartão "Resultado da mesa" fica por cima.
  // tradeCity.obter()      -> foto atual da mesa (abaixo)
  // tradeCity.assinar(fn)  -> fn(foto) a cada atualização (preços a cada 10 s,
  //                           estado da mesa a cada 1 min). Devolve a função para cancelar.
}
```

A foto da mesa:

```js
{
  travada: false,                 // botão de pânico acionado
  traders: [{
    key: "rui", nome: "Rui Xis", ativo: "XRP/USD", mesa: "swing" | "day",
    humor: "perigo" | "alerta" | "normal" | "confiante",
    capital, lucro, hoje: { vitorias, derrotas, resultado },
    preco,                        // preço ao vivo (cripto) ou null
    posicao: null | { lado, qtd, entrada, stop, alvo, desde },
    aoVivo: null | { ...posicao, agora, aberto }   // aberto = resultado em aberto
  }],
  eventos: [{ ts, trader, etapa, ok, detalhe }],   // analista, cérebro, guardião, auditor, placar
  operacoes: [{ trader, ativo, lado, entrada, saida, resultado, motivo, aberta_em, fechada_em }]
}
```

Regras do visual (pedido do Alexandre): pessoas humanas realistas, nada de robô
ou pixel, escritório completo à noite, e sem desfoque nas bordas.
