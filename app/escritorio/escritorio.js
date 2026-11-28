// Monta o escritório 3D (escritorio/index.html) dentro do palco do app.
// O 3D roda num iframe da mesma origem e lê os dados ao vivo do window.TradeCity desta página.
export async function montar(palco) {
  const f = document.createElement("iframe");
  f.className = "cena3d";
  f.src = "escritorio/index.html";
  f.title = "Escritório 3D da Trade City, ao vivo";
  f.setAttribute("loading", "eager");
  f.setAttribute("allow", "fullscreen");
  palco.prepend(f);
  const cheia = document.createElement("a");
  cheia.className = "palco-cheia";
  cheia.href = "escritorio/index.html";
  cheia.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>Tela cheia';
  palco.append(cheia);
}
