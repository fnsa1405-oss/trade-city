// Guarda a casca do app para abrir rápido e funcionar sem sinal.
// Os dados da mesa sempre vêm da rede (com a última cópia como reserva).
const VERSAO = "tc-__VERSAO__";
const CASCA = ["./", "index.html", "estilo.css?v=__VERSAO__", "app.js?v=__VERSAO__", "manifest.webmanifest", "icones/icone.svg", "icones/icone-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSAO).then((c) => c.addAll(CASCA)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSAO).map((k) => caches.delete(k)))).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === self.location.origin) {
    // casca: rede primeiro (pega versão nova), cache se estiver sem sinal
    e.respondWith(
      fetch(req)
        .then((r) => {
          const copia = r.clone();
          caches.open(VERSAO).then((c) => c.put(req, copia));
          return r;
        })
        .catch(() => caches.match(req).then((r) => r || caches.match("index.html"))),
    );
    return;
  }
  if (url.hostname === "raw.githubusercontent.com") {
    // estado da mesa: rede, e a última cópia se cair o sinal
    const chave = url.origin + url.pathname;
    e.respondWith(
      fetch(req)
        .then((r) => {
          if (r.ok) {
            const copia = r.clone();
            caches.open(VERSAO).then((c) => c.put(chave, copia));
          }
          return r;
        })
        .catch(() => caches.match(chave).then((r) => r || Response.error())),
    );
  }
});
