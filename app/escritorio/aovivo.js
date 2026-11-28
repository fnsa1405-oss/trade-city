// Liga o escritório 3D aos dados reais da mesa.
// Dentro do app (iframe), usa o window.TradeCity da página principal, que já busca tudo.
// Aberto sozinho (tela cheia), busca os mesmos arquivos direto do GitHub.
const RAW = "https://raw.githubusercontent.com/fnsa1405-oss/trade-city";

function pai() {
  try {
    return window.parent !== window && window.parent.TradeCity ? window.parent.TradeCity : null;
  } catch {
    return null; // outra origem
  }
}

async function buscar(url) {
  try {
    const r = await fetch(`${url}?t=${Date.now()}`, { cache: "no-store" });
    return r.ok ? r : null;
  } catch {
    return null;
  }
}

export async function obterAoVivo() {
  const tc = pai();
  if (tc) return tc.obter();
  const [a, b, c] = await Promise.all([
    buscar(`${RAW}/mesa-dados/estado.json`),
    buscar(`${RAW}/mesa-daytrade/estado.json`),
    buscar(`${RAW}/controle/trava.txt`),
  ]);
  const mesas = (await Promise.all([a, b].map((r) => (r ? r.json().catch(() => null) : null)))).filter(Boolean);
  if (!mesas.length) return null;
  const trava = c ? (await c.text()).trim().split(/\s+/)[0] : "";
  return {
    travada: trava === "travar" || (trava !== "liberar" && mesas.some((m) => m.travada)),
    traders: mesas.flatMap((m) => (m.traders || []).map((t) => ({ ...t, mesa: m.mesa, aoVivo: null, preco: null }))),
    eventos: mesas.flatMap((m) => m.eventos || []),
    operacoes: mesas.flatMap((m) => m.operacoes || []),
  };
}

export function assinar(fn) {
  const tc = pai();
  if (tc) return tc.assinar(fn);
  const id = setInterval(async () => {
    const f = await obterAoVivo();
    if (f) fn(f);
  }, 60_000);
  return () => clearInterval(id);
}

export const dentroDoApp = () => !!pai();
