// Trade City ao vivo: lê o estado da mesa direto do GitHub e os preços da Coinbase.
// Nada aqui guarda dados no servidor. A única coisa que fica no celular é a chave
// opcional do botão de pânico (localStorage).

const REPO = "fnsa1405-oss/trade-city";
const RAW = `https://raw.githubusercontent.com/${REPO}`;
const API = `https://api.github.com/repos/${REPO}`;
const FONTES = {
  swing: `${RAW}/mesa-dados/estado.json`,
  day: `${RAW}/mesa-daytrade/estado.json`,
  trava: `${RAW}/controle/trava.txt`,
};
const PAGINA_PANICO = `https://github.com/${REPO}/actions/workflows/panico.yml`;
const FUSO = "America/Sao_Paulo";
const A_CADA = { estado: 60_000, precos: 10_000, rodadas: 120_000 };

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const dinheiro = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", currencyDisplay: "symbol" });
const fmtUSD = (v) => (v == null ? "–" : dinheiro.format(v).replace("US$", "US$ ").replace(/\s+/, " "));
const fmtSinal = (v) => (v == null ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + fmtUSD(Math.abs(v)));
const fmtPreco = (v) =>
  v == null ? "–" : v.toLocaleString("pt-BR", { minimumFractionDigits: v < 10 ? 4 : 2, maximumFractionDigits: v < 10 ? 4 : 2 });
const fmtPct = (v) => (v == null ? "–" : `${v > 0 ? "+" : ""}${v.toLocaleString("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}%`);
const classe = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
const hora = (iso) => new Date(iso).toLocaleTimeString("pt-BR", { timeZone: FUSO, hour: "2-digit", minute: "2-digit" });
const diaHora = (iso) => {
  const d = new Date(iso);
  const hoje = new Date().toLocaleDateString("pt-BR", { timeZone: FUSO });
  const dia = d.toLocaleDateString("pt-BR", { timeZone: FUSO });
  return dia === hoje ? hora(iso) : `${dia.slice(0, 5)} ${hora(iso)}`;
};
function haQuanto(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso)) / 1000);
  if (s < 60) return "agora";
  if (s < 3600) return `há ${Math.round(s / 60)} min`;
  if (s < 86400) return `há ${Math.round(s / 3600)} h`;
  return `há ${Math.round(s / 86400)} d`;
}
const iniciais = (nome) => nome.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();

// ------------------------------------------------------------------ estado
const estado = {
  mesas: {}, // swing, day
  trava: null, // { acao, em }
  precos: {}, // "XRP/USD" -> { preco, abertura24h, em }
  rodadas: [],
  erro: null,
  vistos: new Set(),
  primeiraCarga: true,
};
const ouvintes = new Set();

async function buscar(url, comoTexto = false) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 12_000);
  try {
    const sep = url.includes("?") ? "&" : "?";
    const r = await fetch(`${url}${url.startsWith(RAW) ? `${sep}t=${Date.now()}` : ""}`, { signal: ctrl.signal, cache: "no-store" });
    if (r.status === 404) return null;
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return comoTexto ? r.text() : r.json();
  } finally {
    clearTimeout(t);
  }
}

async function carregarEstado() {
  const [swing, day, trava] = await Promise.allSettled([buscar(FONTES.swing), buscar(FONTES.day), buscar(FONTES.trava, true)]);
  if (swing.status === "fulfilled" && swing.value) estado.mesas.swing = swing.value;
  if (day.status === "fulfilled" && day.value) estado.mesas.day = day.value;
  if (trava.status === "fulfilled" && trava.value) {
    const [acao, em] = trava.value.trim().split(/\r?\n/);
    estado.trava = { acao: (acao || "").trim(), em: (em || "").trim() };
  }
  estado.erro = swing.status === "rejected" && day.status === "rejected" ? "sem conexão com a mesa" : null;
}

function simboloCoinbase(s) {
  return s.replace("/", "-");
}

async function carregarPrecos() {
  const cripto = traders().filter((t) => t.classe === "crypto").map((t) => t.ativo);
  await Promise.all(
    [...new Set(cripto)].map(async (ativo) => {
      const par = simboloCoinbase(ativo);
      try {
        const st = await buscar(`https://api.exchange.coinbase.com/products/${par}/stats`);
        estado.precos[ativo] = { preco: +st.last, abertura24h: +st.open, em: Date.now() };
      } catch {
        try {
          const sp = await buscar(`https://api.coinbase.com/v2/prices/${par}/spot`);
          const antes = estado.precos[ativo] || {};
          estado.precos[ativo] = { ...antes, preco: +sp.data.amount, em: Date.now() };
        } catch {
          /* sem preço ao vivo: mostra o último da mesa */
        }
      }
    }),
  );
}

async function carregarRodadas() {
  try {
    const r = await buscar(`${API}/actions/runs?per_page=20`);
    estado.rodadas = (r?.workflow_runs || []).map((w) => ({
      id: w.id,
      nome: w.name,
      status: w.status,
      resultado: w.conclusion,
      em: w.run_started_at || w.created_at,
      url: w.html_url,
    }));
  } catch {
    /* limite da API pública: tenta de novo na próxima */
  }
}

function traders() {
  return Object.values(estado.mesas).flatMap((m) => (m.traders || []).map((t) => ({ ...t, mesa: m.mesa })));
}

function travada() {
  if (estado.trava?.acao === "travar") return true;
  if (estado.trava?.acao === "liberar") return false;
  return Object.values(estado.mesas).some((m) => m.travada);
}

function posicaoAoVivo(t) {
  const p = t.posicao;
  if (!p) return null;
  const agora = estado.precos[t.ativo]?.preco ?? null;
  const sinal = p.lado === "venda" ? -1 : 1;
  const aberto = agora == null ? null : (agora - p.entrada) * p.qtd * sinal;
  const baixo = Math.min(p.stop, p.alvo);
  const alto = Math.max(p.stop, p.alvo);
  const pos = (v) => Math.min(100, Math.max(0, ((v - baixo) / (alto - baixo)) * 100));
  return { ...p, agora, aberto, posAgora: agora == null ? pos(p.entrada) : pos(agora), posEntrada: pos(p.entrada), invertido: sinal < 0 };
}

// ------------------------------------------------------------------ tela
function desenhar() {
  const lista = traders();
  const presos = travada();
  const mesas = Object.values(estado.mesas);

  // topo e barra
  const ultimaMesa = mesas.map((m) => m.gerado_em).sort().pop();
  const status = $("#status");
  const idade = ultimaMesa ? (Date.now() - new Date(ultimaMesa)) / 60000 : Infinity;
  const [cod, txt] = estado.erro && !mesas.length
    ? ["erro", "sem sinal"]
    : presos
      ? ["travada", "travada"]
      : idade < 10
        ? ["vivo", "ao vivo"]
        : ["atraso", ultimaMesa ? "atrasada" : "aguardando"];
  status.dataset.estado = cod;
  status.querySelector("span").textContent = txt;
  $("#modo").textContent = mesas.some((m) => m.modo === "real") ? "mesa REAL" : "mesa simulada";
  const barra = $("#barra-panico");
  barra.classList.toggle("travada", presos);
  $("#barra-texto").textContent = presos ? "MESA TRAVADA" : "OPERANDO";
  $("#btn-panico").textContent = presos ? "LIBERAR" : "PARAR TUDO";

  // resultado e kpis
  const realizado = lista.reduce((s, t) => s + (t.lucro || 0), 0);
  const aberto = lista.reduce((s, t) => s + (posicaoAoVivo(t)?.aberto || 0), 0);
  const total = realizado + aberto;
  const rt = $("#resultado-total");
  rt.textContent = fmtSinal(total);
  rt.className = `valor-grande ${classe(total)}`;
  $("#resultado-sub").textContent = aberto
    ? `${fmtSinal(realizado)} fechado · ${fmtSinal(aberto)} em aberto`
    : lista.length
      ? "desde o início da fase simulada"
      : "aguardando o primeiro estado da mesa";
  const capital = lista.reduce((s, t) => s + (t.capital || 0), 0) + aberto;
  const hoje = lista.reduce((s, t) => s + (t.hoje?.resultado || 0), 0);
  const resumo = mesas.reduce((a, m) => ({ ops: a.ops + (m.resumo?.operacoes || 0), v: a.v + (m.resumo?.vitorias || 0) }), { ops: 0, v: 0 });
  $("#k-capital").textContent = lista.length ? fmtUSD(Math.round(capital)).replace(/,00$/, "") : "–";
  const kh = $("#k-hoje");
  kh.textContent = lista.length ? fmtSinal(hoje) : "–";
  kh.className = classe(hoje);
  $("#k-ops").textContent = resumo.ops;
  $("#k-acerto").textContent = resumo.ops ? `${Math.round((resumo.v / resumo.ops) * 100)}%` : "–";

  desenharDias();
  desenharTraders(lista);
  desenharFeed(lista);
  desenharOperacoes();
  desenharElenco();
  $("#atualizado").textContent = ultimaMesa ? `mesa atualizada ${haQuanto(ultimaMesa)}` : "";
  avisar3D();
}

// resultado de cada dia: soma as duas mesas (day trade e swing) por data de São Paulo
function desenharDias() {
  const nomes = { day: "Day trade", swing: "Swing e cripto" };
  const hojeISO = new Date().toLocaleDateString("en-CA", { timeZone: FUSO });
  const porDia = new Map();
  const hojeMesa = [];
  for (const [chave, m] of Object.entries(estado.mesas)) {
    let hoje = 0;
    let opsHoje = 0;
    for (const d of m.dias || []) {
      const x = porDia.get(d.data) || { data: d.data, resultado: 0, operacoes: 0, vitorias: 0 };
      x.resultado += d.resultado || 0;
      x.operacoes += d.operacoes || 0;
      x.vitorias += d.vitorias || 0;
      porDia.set(d.data, x);
      if (d.data === hojeISO) { hoje = d.resultado || 0; opsHoje = d.operacoes || 0; }
    }
    hojeMesa.push({ chave, nome: nomes[chave] || chave, hoje, opsHoje });
  }
  hojeMesa.sort((a, b) => (a.chave === "day" ? -1 : b.chave === "day" ? 1 : 0));
  $("#hoje-mesas").innerHTML = hojeMesa.length
    ? hojeMesa
        .map(
          (h) => `<div class="hoje-mesa"><span>${esc(h.nome)} hoje</span><strong class="num ${classe(h.hoje)}">${fmtSinal(h.hoje)}</strong>` +
            `<em>${h.opsHoje ? `${h.opsHoje} operaç${h.opsHoje > 1 ? "ões" : "ão"}` : "sem operação fechada"}</em></div>`
        )
        .join("")
    : "";
  const dias = [...porDia.values()].sort((a, b) => (a.data < b.data ? -1 : 1)).slice(-20);
  const box = $("#dias");
  if (!dias.length) {
    box.innerHTML = `<p class="vazio">Ainda não há dia fechado. O primeiro aparece aqui assim que uma operação terminar.</p>`;
    $("#dias-resumo").textContent = "";
    return;
  }
  const maior = Math.max(...dias.map((d) => Math.abs(d.resultado)), 1);
  box.innerHTML = dias
    .map((d) => {
      const h = Math.max(4, Math.round((Math.abs(d.resultado) / maior) * 100));
      const [, mes, dia] = d.data.split("-");
      const tit = `${dia}/${mes}: ${fmtSinal(d.resultado)} em ${d.operacoes} operaç${d.operacoes > 1 ? "ões" : "ão"}`;
      return `<div class="dia ${classe(d.resultado)}${d.data === hojeISO ? " hoje" : ""}" title="${esc(tit)}">` +
        `<div class="dia-meio"><i style="height:${h / 2}%"></i></div><span>${dia}</span></div>`;
    })
    .join("");
  const verdes = dias.filter((d) => d.resultado > 0).length;
  const soma = dias.reduce((s, d) => s + d.resultado, 0);
  $("#dias-resumo").innerHTML =
    `<span><b class="pos">${verdes}</b> de ${dias.length} dias no verde</span>` +
    `<span>média por dia <b class="num ${classe(soma)}">${fmtSinal(soma / dias.length)}</b></span>`;
}

function desenharTraders(lista) {
  const box = $("#traders");
  box.replaceChildren();
  if (!lista.length) {
    box.append(el("div", "vazio", estado.erro ? "Sem conexão com a mesa agora. Tentando de novo." : "Carregando a mesa…"));
    return;
  }
  for (const t of lista) {
    const c = el("article", "trader");
    const preco = estado.precos[t.ativo];
    const var24 = preco?.abertura24h ? ((preco.preco - preco.abertura24h) / preco.abertura24h) * 100 : null;
    const p = posicaoAoVivo(t);
    c.innerHTML = `
      <div class="trader-topo">
        <div class="avatar">${esc(iniciais(t.nome))}</div>
        <div class="trader-nome"><strong>${esc(t.nome)}</strong><span>${esc(t.ativo)} · ${esc(t.tempo)} · ${esc(t.estrategia)}</span></div>
        <div class="preco">
          <strong class="num">${preco ? fmtPreco(preco.preco) : p ? fmtPreco(p.entrada) : "–"}</strong>
          <span class="${classe(var24)}">${var24 != null ? `${fmtPct(var24)} 24h` : preco ? "ao vivo" : t.classe === "crypto" ? "" : "pregão de NY"}</span>
        </div>
      </div>
      <div class="chips">
        <span class="chip humor-${esc(t.humor)}"><i></i>humor ${esc(t.humor)}</span>
        <span class="chip">${t.mesa === "day" ? "day trade" : "swing"}</span>
        ${t.ultimos?.length ? `<span class="chip">últimas: ${t.ultimos.slice(-5).map((x) => (x === "v" ? "✓" : "✗")).join(" ")}</span>` : ""}
      </div>`;
    if (p) {
      const ladoTxt = p.lado === "venda" ? "Vendido" : "Comprado";
      c.insertAdjacentHTML(
        "beforeend",
        `<div class="situacao"><b>${ladoTxt}</b> com ${p.qtd.toLocaleString("pt-BR", { maximumFractionDigits: 4 })} ${esc(t.ativo.split("/")[0])} desde ${diaHora(p.desde)}</div>
        <div class="regua">
          <div class="regua-linha" style="${p.invertido ? "transform:scaleX(-1)" : ""}">
            <span class="regua-entrada" style="left:${p.posEntrada}%"></span>
            <span class="regua-agora" style="left:${p.posAgora}%"></span>
          </div>
          <div class="regua-rotulos">
            <div><b>stop</b>${fmtPreco(p.stop)}</div>
            <div><b>entrada</b>${fmtPreco(p.entrada)}</div>
            <div><b>alvo</b>${fmtPreco(p.alvo)}</div>
          </div>
        </div>
        <div class="aberto"><span>Resultado em aberto${p.agora == null ? " (sem preço ao vivo)" : ""}</span><strong class="${classe(p.aberto)}">${fmtSinal(p.aberto)}</strong></div>`,
      );
    } else {
      const vigia = t.ultimo_candle
        ? `último candle de ${esc(t.tempo)} analisado às ${diaHora(t.ultimo_candle)}`
        : "esperando o primeiro candle";
      c.insertAdjacentHTML(
        "beforeend",
        `<div class="situacao">Sem posição. <b>De olho no ${esc(t.ativo.split("/")[0])}</b>, ${vigia}.</div>`,
      );
    }
    c.insertAdjacentHTML(
      "beforeend",
      `<div class="dia">
        <div><span>Hoje</span><strong class="${classe(t.hoje.resultado)}">${fmtSinal(t.hoje.resultado).replace("US$ ", "$")}</strong></div>
        <div><span>Vitórias</span><strong>${t.hoje.vitorias}/${t.hoje.meta_vitorias}</strong></div>
        <div><span>Derrotas</span><strong>${t.hoje.derrotas}/${t.hoje.max_derrotas}</strong></div>
      </div>`,
    );
    box.append(c);
  }
}

const NOMES = {};
function nomeDe(key) {
  if (!Object.keys(NOMES).length) for (const m of Object.values(estado.mesas)) for (const e of m.elenco || []) NOMES[e.key] = e.nome;
  return NOMES[key] || key;
}

function itemEvento(e) {
  const quem = nomeDe(e.trader).split(" ")[0];
  const mapa = {
    analista: ["📈", "info", `${quem} viu um sinal`],
    "cérebro": ["🧠", e.ok ? "ok" : "nao", e.ok ? `Cérebro de ${quem} liberou` : `Cérebro de ${quem} deixou passar`],
    "guardião": ["🛡️", e.ok ? "ok" : "nao", e.ok ? "Guardião montou o plano" : "Guardião recusou"],
    auditor: ["✅", e.ok ? "ok" : "nao", e.ok ? "Auditor aprovou a ordem" : "Auditor reprovou"],
    placar: [e.ok ? "🏆" : "🔻", e.ok ? "ok" : "nao", e.ok ? `Vitória de ${quem}` : `Derrota de ${quem}`],
    erro: ["⚠️", "nao", `Problema com ${quem}`],
  };
  const [ic, tipo, titulo] = mapa[e.etapa] || ["•", "info", `${quem}: ${e.etapa}`];
  return { id: `e:${e.ts}:${e.trader}:${e.etapa}`, em: e.ts, ic, tipo, titulo, det: `${e.ativo} · ${e.detalhe}` };
}

function itensOperacoes() {
  const out = [];
  for (const m of Object.values(estado.mesas))
    for (const o of m.operacoes || []) {
      const quem = nomeDe(o.trader).split(" ")[0];
      const verbo = o.lado === "venda" ? "vendeu" : "comprou";
      out.push({
        id: `oa:${o.aberta_em}:${o.trader}`,
        em: o.aberta_em,
        ic: "🟢",
        tipo: "ok",
        titulo: `${quem} ${verbo} ${o.ativo}`,
        det: `${o.qtd.toLocaleString("pt-BR", { maximumFractionDigits: 4 })} a ${fmtPreco(o.entrada)}`,
      });
      if (o.fechada_em)
        out.push({
          id: `of:${o.fechada_em}:${o.trader}`,
          em: o.fechada_em,
          ic: o.resultado > 0 ? "💰" : "🔻",
          tipo: o.resultado > 0 ? "ok" : "nao",
          titulo: `${quem} saiu: ${fmtSinal(o.resultado)}`,
          det: `${o.motivo || "saída"} a ${fmtPreco(o.saida)}`,
        });
    }
  return out;
}

const NOMES_ROBOS = {
  "Mesa simulada": "Turno da mesa",
  "Mesa day trade": "Pregão de day trade",
  "Botão de pânico": "Botão de pânico",
  "Escola de traders": "Escola",
  "Treino dos cérebros": "Treino dos cérebros",
  "Coleta de candles": "Coleta de candles",
};

function itensRodadas() {
  const vistos = new Set();
  return estado.rodadas
    .filter((r) => NOMES_ROBOS[r.nome] && !vistos.has(r.nome) && vistos.add(r.nome))
    .map((r) => {
      const rodando = r.status !== "completed";
      const ok = r.resultado === "success";
      return {
        id: `r:${r.id}:${r.status}`,
        em: r.em,
        ic: rodando ? "⏳" : ok ? "⚙️" : "⚠️",
        tipo: rodando ? "info" : ok ? "info" : "nao",
        titulo: `${NOMES_ROBOS[r.nome]} ${rodando ? "rodando agora" : ok ? "terminou" : "falhou"}`,
        det: rodando ? "acompanhe no GitHub" : ok ? "tudo certo" : "vou olhar o que houve",
        url: r.url,
      };
    });
}

function desenharFeed() {
  const ev = Object.values(estado.mesas).flatMap((m) => (m.eventos || []).map(itemEvento));
  const todos = [...ev, ...itensOperacoes(), ...itensRodadas()]
    .filter((i) => i.em)
    .sort((a, b) => new Date(b.em) - new Date(a.em))
    .slice(0, 25);
  const box = $("#feed");
  box.replaceChildren();
  if (!todos.length) {
    box.append(el("li", "", `<span class="ic info">🌙</span><span class="tx"><b>Mesa calma</b><small>Ainda sem sinais. Quando um trader agir, aparece aqui.</small></span><time></time>`));
    return;
  }
  for (const i of todos) {
    const li = el("li", !estado.primeiraCarga && !estado.vistos.has(i.id) ? "novo" : "");
    li.innerHTML = `<span class="ic ${i.tipo}">${i.ic}</span><span class="tx"><b>${esc(i.titulo)}</b><small>${esc(i.det)}</small></span><time>${diaHora(i.em)}</time>`;
    if (i.url) {
      li.style.cursor = "pointer";
      li.addEventListener("click", () => window.open(i.url, "_blank", "noopener"));
    }
    estado.vistos.add(i.id);
    box.append(li);
  }
  estado.primeiraCarga = false;
}

function desenharOperacoes() {
  const ops = Object.values(estado.mesas).flatMap((m) => m.operacoes || []).sort((a, b) => new Date(b.aberta_em) - new Date(a.aberta_em));
  const box = $("#operacoes");
  box.replaceChildren();
  $("#ops-dica").textContent = ops.length ? `${ops.length} mais recentes` : "";
  if (!ops.length) {
    box.append(el("div", "vazio", "Nenhuma operação ainda. O Rui só entra quando o XRP rompe o canal."));
    return;
  }
  for (const o of ops.slice(0, 15)) {
    const aberta = !o.fechada_em;
    box.append(
      el(
        "div",
        "op",
        `<div><b>${esc(nomeDe(o.trader).split(" ")[0])}</b> ${o.lado === "venda" ? "vendeu" : "comprou"} ${esc(o.ativo)}</div>
        <div class="r ${aberta ? "" : classe(o.resultado)}">${aberta ? "aberta" : fmtSinal(o.resultado)}</div>
        <small>${diaHora(o.aberta_em)} a ${fmtPreco(o.entrada)}${aberta ? "" : ` → ${fmtPreco(o.saida)}`}</small>
        <small style="text-align:right">${aberta ? "" : esc(o.motivo || "")}</small>`,
      ),
    );
  }
}

function desenharElenco() {
  const mapa = new Map();
  for (const m of Object.values(estado.mesas))
    for (const e of m.elenco || []) {
      const antes = mapa.get(e.key);
      if (!antes || e.situacao === "na mesa") mapa.set(e.key, e);
    }
  const box = $("#elenco");
  box.replaceChildren();
  const lista = [...mapa.values()].sort((a, b) => (a.situacao === b.situacao ? 0 : a.situacao === "na mesa" ? -1 : 1));
  for (const e of lista)
    box.append(
      el(
        "span",
        `membro ${e.situacao === "na mesa" ? "na-mesa" : ""}`,
        `<span class="mini">${esc(iniciais(e.nome))}</span>${esc(e.nome)} <small>${esc(e.ativo)} · ${esc(e.situacao)}</small>`,
      ),
    );
}

function proximaRodada() {
  // a mesa trabalha em turnos de ~55 min, olhando o mercado a cada minuto; um turno novo começa
  // logo depois dos 2 minutos de cada hora (o GitHub às vezes atrasa alguns minutos)
  const rodando = estado.rodadas.some((r) => r.nome === "Mesa simulada" && r.status !== "completed");
  if (rodando) {
    $("#proxima").textContent = "olhando o mercado a cada minuto";
    return;
  }
  const agora = new Date();
  const alvo = new Date(agora);
  alvo.setUTCSeconds(0, 0);
  if (agora.getUTCMinutes() >= 2) alvo.setUTCHours(alvo.getUTCHours() + 1);
  alvo.setUTCMinutes(2);
  const min = Math.max(1, Math.round((alvo - agora) / 60000));
  $("#proxima").textContent = `troca de turno, volta em ~${min} min`;
}

// ------------------------------------------------------------------ pânico
const CHAVE = "tc-chave-panico";
const lerChave = () => {
  try {
    return localStorage.getItem(CHAVE) || "";
  } catch {
    return "";
  }
};

function abrirFolha(id) {
  const f = $(id);
  f.hidden = false;
  f.onclick = (ev) => {
    if (ev.target === f || ev.target.hasAttribute("data-fechar")) f.hidden = true;
  };
}

function aviso(txt, ms = 5000) {
  const a = $("#aviso");
  a.textContent = txt;
  a.hidden = false;
  clearTimeout(aviso.t);
  aviso.t = setTimeout(() => (a.hidden = true), ms);
}

function prepararPanico() {
  $("#btn-panico").addEventListener("click", () => {
    const presos = travada();
    const chave = lerChave();
    $("#fp-titulo").textContent = presos ? "Liberar a mesa?" : "Parar a mesa inteira?";
    $("#fp-texto").textContent = presos
      ? "Os traders aprovados voltam a operar a partir da próxima rodada, com todas as travas de risco."
      : "Todas as posições abertas são zeradas e nenhum trader abre operação nova até você liberar.";
    const b = $("#fp-confirmar");
    b.textContent = presos ? "Sim, liberar" : "Sim, parar tudo";
    b.classList.toggle("liberar", presos);
    $("#fp-nota").textContent = chave
      ? "Dispara direto pelo app. A mesa swing para em 1 a 2 minutos."
      : "Vai abrir o GitHub: toque em Run workflow, escolha a ação e confirme. Em Ajustes dá para ligar o disparo direto.";
    b.onclick = () => acionar(presos ? "liberar" : "travar");
    abrirFolha("#folha-panico");
  });
}

async function acionar(acao) {
  $("#folha-panico").hidden = true;
  const chave = lerChave();
  if (!chave) {
    window.open(PAGINA_PANICO, "_blank", "noopener");
    return;
  }
  try {
    const r = await fetch(`${API}/actions/workflows/panico.yml/dispatches`, {
      method: "POST",
      headers: { Accept: "application/vnd.github+json", Authorization: `Bearer ${chave}`, "X-GitHub-Api-Version": "2022-11-28" },
      body: JSON.stringify({ ref: "main", inputs: { acao } }),
    });
    if (r.status !== 204) throw new Error(`GitHub respondeu ${r.status}`);
    estado.trava = { acao, em: new Date().toISOString() };
    desenhar();
    aviso(acao === "travar" ? "Pânico acionado. A mesa está sendo travada." : "Liberação enviada. A mesa volta na próxima rodada.", 7000);
    setTimeout(atualizarTudo, 20_000);
  } catch (e) {
    aviso(`Não consegui disparar (${e.message}). Abrindo o GitHub.`, 7000);
    window.open(PAGINA_PANICO, "_blank", "noopener");
  }
}

function prepararAjustes() {
  $("#abrir-ajustes").addEventListener("click", () => {
    $("#fa-chave").value = "";
    $("#fa-nota").textContent = lerChave() ? "Há uma chave salva neste celular." : "Nenhuma chave salva.";
    abrirFolha("#folha-ajustes");
  });
  $("#fa-salvar").addEventListener("click", () => {
    const v = $("#fa-chave").value.trim();
    if (!/^(github_pat_|ghp_)/.test(v)) {
      $("#fa-nota").textContent = "Essa chave não parece do GitHub (começa com github_pat_).";
      return;
    }
    try {
      localStorage.setItem(CHAVE, v);
      $("#folha-ajustes").hidden = true;
      aviso("Chave salva. O botão agora dispara direto.");
    } catch {
      $("#fa-nota").textContent = "Este navegador não deixou salvar.";
    }
  });
  $("#fa-apagar").addEventListener("click", () => {
    try {
      localStorage.removeItem(CHAVE);
    } catch {}
    $("#fa-nota").textContent = "Chave apagada.";
  });
}

// ------------------------------------------------------------------ escritório 3D
// O 3D mora em app/escritorio/escritorio.js e exporta montar(elemento, tradeCity).
// tradeCity.obter() devolve a foto atual da mesa; tradeCity.assinar(fn) avisa a cada atualização.
const tradeCity = {
  obter() {
    return {
      travada: travada(),
      traders: traders().map((t) => ({ ...t, aoVivo: posicaoAoVivo(t), preco: estado.precos[t.ativo]?.preco ?? null })),
      eventos: Object.values(estado.mesas).flatMap((m) => m.eventos || []),
      operacoes: Object.values(estado.mesas).flatMap((m) => m.operacoes || []),
      elenco: (() => {
        const mapa = new Map();
        for (const m of Object.values(estado.mesas)) for (const e of m.elenco || []) if (!mapa.has(e.key) || e.situacao === "na mesa") mapa.set(e.key, e);
        return [...mapa.values()];
      })(),
    };
  },
  assinar(fn) {
    ouvintes.add(fn);
    return () => ouvintes.delete(fn);
  },
};
window.TradeCity = tradeCity;
function avisar3D() {
  const foto = tradeCity.obter();
  for (const fn of ouvintes) {
    try {
      fn(foto);
    } catch (e) {
      console.warn("escritório:", e);
    }
  }
}
async function montarEscritorio() {
  try {
    const mod = await import("./escritorio/escritorio.js");
    const palco = $("#escritorio");
    await mod.montar(palco, tradeCity);
    palco.classList.add("com-3d");
  } catch {
    /* ainda sem 3D: fica a cidade à noite em CSS */
  }
}

// ------------------------------------------------------------------ ciclo
let ocupado = false;
async function atualizarTudo() {
  if (ocupado) return;
  ocupado = true;
  try {
    await carregarEstado();
    await Promise.all([carregarPrecos(), carregarRodadas()]);
  } finally {
    ocupado = false;
    desenhar();
    proximaRodada();
  }
}

function iniciar() {
  prepararPanico();
  prepararAjustes();
  desenhar();
  atualizarTudo();
  montarEscritorio();
  setInterval(() => document.visibilityState === "visible" && carregarEstado().then(desenhar), A_CADA.estado);
  setInterval(() => document.visibilityState === "visible" && carregarPrecos().then(desenhar), A_CADA.precos);
  setInterval(() => document.visibilityState === "visible" && carregarRodadas().then(() => (desenhar(), proximaRodada())), A_CADA.rodadas);
  setInterval(proximaRodada, 30_000);
  document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && atualizarTudo());
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  if (location.hash === "#panico") {
    history.replaceState(null, "", location.pathname);
    setTimeout(() => $("#btn-panico").click(), 600);
  }
}

iniciar();
