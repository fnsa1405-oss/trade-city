// Trade City 3D — escritório com pessoas.
// Camadas: dados (estado.json; depois o placar real da mesa simulada) → cena 3D → interface.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { HorizontalTiltShiftShader } from 'three/addons/shaders/HorizontalTiltShiftShader.js';
import { VerticalTiltShiftShader } from 'three/addons/shaders/VerticalTiltShiftShader.js';
import { VignetteShader } from 'three/addons/shaders/VignetteShader.js';
import { criarCidade } from './cidade.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';
import { obterAoVivo, assinar, dentroDoApp } from './aovivo.js';

const $ = s => document.querySelector(s);
const MOBILE = matchMedia('(max-width: 700px)').matches || /Android|iPhone/i.test(navigator.userAgent);
const HQ = !MOBILE || new URLSearchParams(location.search).has('rec') || !!window.__REC;
let simT = 0;
const REC = new URLSearchParams(location.search).has('rec') || window.__REC;

/* ================= dados ================= */
export async function loadState() {
  // Hoje: arquivo de exemplo. No app real: o placar gerado pela mesa simulada (branch mesa-dados).
  // a montagem da sala (quem senta onde) vem do estado.json; os números vêm da mesa de verdade
  let s = window.__ESTADO;
  try { const r = await fetch('estado.json', { cache: 'no-store' }); if (r.ok) s = await r.json(); } catch (e) {}
  try { const vivo = await obterAoVivo(); if (vivo) { montarElenco(s, vivo); aplicarAoVivo(s, vivo, true); } } catch (e) { console.warn('mesa ao vivo:', e); }
  return s;
}

/* ================= mesa ao vivo ================= */
const CORES = ['#3fb6f2', '#7b6cff', '#d38cff', '#ff6fcf', '#ffd84d', '#3ddc97', '#ffb547', '#8f9bff', '#ff7a45'];
// quem senta na mesa e quem fica na escola segue a mesa de verdade (lido uma vez, ao abrir)
function montarElenco(s, vivo) {
  if (!vivo.elenco || !vivo.elenco.length) return;
  const base = {}; [...s.traders, ...s.escola].forEach(p => base[p.key] = p);
  const naMesa = (vivo.traders || []).map(t => t.key).filter((k, i, a) => a.indexOf(k) === i).slice(0, 12);
  const ficha = (e, i) => { const b = base[e.key] || {}; return { ...b, key: e.key, nome: e.nome, ativo: e.ativo, cor: b.cor || CORES[i % CORES.length], pf_escola: b.pf_escola || 0, humor: b.humor || 'normal', vitorias: 0, derrotas: 0, capital: b.capital || 10000, posicao: 'nenhuma', fala: b.fala || 'Foco no plano.', estrategia: b.estrategia || '' }; };
  const porKey = Object.fromEntries(vivo.elenco.map(e => [e.key, e]));
  s.traders = naMesa.map((k, i) => ficha(porKey[k] || { key: k, nome: k, ativo: '' }, i));
  s.escola = vivo.elenco.filter(e => !naMesa.includes(e.key)).slice(0, STUDENT_POS.length).map((e, i) => ({ ...ficha(e, i + 3), ativo: e.ativo.split('/')[0], status: 'estudando' }));
  arrumarMesa(s.traders.length);
}

const ETAPA_ATOR = { analista: null, 'cérebro': null, 'guardião': 'rocha', auditor: 'vera', placar: null };
const fmtP = v => v == null ? '–' : v.toLocaleString('pt-BR', { minimumFractionDigits: v < 10 ? 4 : 2, maximumFractionDigits: v < 10 ? 4 : 2 });
const fmtR = v => (v > 0 ? '+' : v < 0 ? '−' : '') + 'US$ ' + Math.abs(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
let vistoAte = '', opsVistas = new Set();
function aplicarAoVivo(s, vivo, primeira = false) {
  s.aoVivo = true; s.travada = !!vivo.travada;
  const porKey = Object.fromEntries((vivo.traders || []).map(t => [t.key, t]));
  s.hoje = 0;
  for (const tr of s.traders) {
    const t = porKey[tr.key];
    if (!t) { Object.assign(tr, { situacao: 'na escola', posicao: '—', fala: 'Voltei para a escola. Estudando para a próxima prova.' }); continue; }
    const p = t.posicao, ab = t.aoVivo;
    Object.assign(tr, {
      situacao: 'na mesa', preco: t.preco ?? null, humor: t.humor, vitorias: t.hoje.vitorias, derrotas: t.hoje.derrotas,
      capital: Math.round(t.capital + (ab?.aberto || 0)), estrategia: `${t.estrategia} · candles de ${t.tempo}`,
      posicao: p ? `${p.lado === 'venda' ? 'vendido' : 'comprado'} a ${fmtP(p.entrada)}` : 'nenhuma',
      fala: p ? (ab?.aberto != null ? `Posição ${ab.aberto >= 0 ? 'no lucro' : 'no prejuízo'}: ${fmtR(ab.aberto)}.` : `Stop em ${fmtP(p.stop)}, alvo em ${fmtP(p.alvo)}.`)
              : `De olho no ${t.ativo.split('/')[0]}. Sem posição por enquanto.`,
    });
    s.hoje += t.hoje.resultado + (ab?.aberto || 0);
  }
  const evs = (vivo.eventos || []).slice().sort((a, b) => a.ts < b.ts ? -1 : 1);
  const ops = vivo.operacoes || [];
  if (primeira) { vistoAte = evs.length ? evs[evs.length - 1].ts : ''; ops.forEach(o => opsVistas.add(o.aberta_em + o.trader)); return; }
  // novidades da mesa viram falas e a caminhada da ordem
  evs.filter(e => e.ts > vistoAte).forEach((e, i) => setTimeout(() => {
    const quem = actors[ETAPA_ATOR[e.etapa] || e.trader]; if (!quem) return;
    const txt = e.etapa === 'placar' ? (e.ok ? 'Vitória! ' : 'Stop. Faz parte. ') + e.detalhe.split(':').pop().trim()
      : e.etapa === 'guardião' ? (e.ok ? 'Plano montado: ' : 'Recusei: ') + e.detalhe
      : e.etapa === 'auditor' ? (e.ok ? 'Auditado. Liberado!' : 'Reprovado: ' + e.detalhe) : e.detalhe;
    say(quem, txt.length > 60 ? txt.slice(0, 58) + '…' : txt, 5);
    const nm = (STATE.traders.find(t => t.key === e.trader) || {}).nome; noticia((nm ? nm.split(' ')[0] + ': ' : '') + txt, new Date(e.ts));
  }, i * 2500));
  if (evs.length) vistoAte = evs[evs.length - 1].ts;
  ops.filter(o => !o.fechada_em && !opsVistas.has(o.aberta_em + o.trader)).forEach(o => {
    opsVistas.add(o.aberta_em + o.trader);
    const ativo = o.ativo.split('/')[0];
    startOrder({ rui: `${o.lado === 'venda' ? 'Vender' : 'Comprar'} ${ativo} a ${fmtP(o.entrada)}.`, rocha: 'Stop e alvo no lugar.', vera: 'Placar ok. Liberado!', cofre: 'Executado no simulado!' }, o.trader);
    noticia(`${(STATE.traders.find(t => t.key === o.trader) || {}).nome || o.trader} ${o.lado === 'venda' ? 'vende' : 'compra'} ${ativo} a ${fmtP(o.entrada)}`);
  });
  ops.forEach(o => opsVistas.add(o.aberta_em + o.trader));
}
function atualizarHud() {
  if (!STATE) return;
  const hb = document.querySelector('.hud b'); if (hb) { hb.textContent = STATE.travada ? 'MESA TRAVADA' : 'OPERANDO'; hb.style.color = STATE.travada ? 'var(--red)' : ''; }
  const na = STATE.traders.filter(t => t.situacao === 'na mesa').length;
  $('#hud-sub').textContent = STATE.aoVivo ? `${na} na mesa · ${STATE.traders.length - na + STATE.escola.length} na escola · ao vivo` : `${STATE.traders.length} traders · ${STATE.modo}`;
  $('#hud-cap').textContent = STATE.aoVivo ? fmtR(STATE.hoje) : 'US$ ' + STATE.traders.reduce((a, t) => a + t.capital, 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 });
  const pb = document.querySelector('.hud .panic'); if (pb) pb.textContent = STATE.travada ? '▶ LIBERAR' : '■ PARAR TUDO';
}

/* ================= utilidades ================= */
let seed = 11; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const easeIO = x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
const mat = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: .55, metalness: .05, ...o });
function rbox(w, h, d, r, m) { const g = new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2, h / 2, d / 2)); const me = new THREE.Mesh(g, m); me.castShadow = me.receiveShadow = true; return me; }
function canvasTex(w, h, draw) { const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d'); draw(g, w, h); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; t.userData = { c, g }; return t; }
const lerpAngle = (a, b, k) => { let d = ((b - a + Math.PI) % (Math.PI * 2)) - Math.PI; if (d < -Math.PI) d += Math.PI * 2; return a + d * k; };
// GLB guardado como base64 dentro de JSON (o host só serve .json); remonta e entrega ao GLTFLoader
const loader = new GLTFLoader(); loader.setMeshoptDecoder(MeshoptDecoder);
function b64ToBuf(b64) { const s = atob(b64); const u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u.buffer; }
function gltfJsonToGlb(j) {
  const b64 = j.buffers[0].uri.split(',')[1]; delete j.buffers[0].uri; const bin = new Uint8Array(b64ToBuf(b64));
  let js = new TextEncoder().encode(JSON.stringify(j)); const pad = (4 - js.length % 4) % 4; if (pad) { const t = new Uint8Array(js.length + pad); t.set(js); t.fill(32, js.length); js = t; }
  const bpad = (4 - bin.length % 4) % 4; const total = 28 + js.length + bin.length + bpad; const glb = new ArrayBuffer(total), dv = new DataView(glb), u8 = new Uint8Array(glb);
  dv.setUint32(0, 0x46546C67, true); dv.setUint32(4, 2, true); dv.setUint32(8, total, true); dv.setUint32(12, js.length, true); dv.setUint32(16, 0x4E4F534A, true); u8.set(js, 20);
  const o = 20 + js.length; dv.setUint32(o, bin.length + bpad, true); dv.setUint32(o + 4, 0x004E4942, true); u8.set(bin, o + 8); return glb;
}
async function loadPerson(name) { const j = await (await fetch(`assets/p2/${name}.json`)).json(); return loader.parseAsync(gltfJsonToGlb(j), ''); }

/* ================= cena ================= */
const app = $('#scene');
const renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: 'high-performance', preserveDrawingBuffer: !!REC });
renderer.setPixelRatio(REC ? (window.__RECPR || 1.5) : Math.min(devicePixelRatio, MOBILE ? 1.5 : 2));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.0;
app.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x161b36, 0.006);
// luz de ambiente realista (reflexos suaves em todos os materiais)
const pmrem = new THREE.PMREMGenerator(renderer); scene.environment = pmrem.fromScene(new RoomEnvironment(renderer), .04).texture;
const camera = new THREE.PerspectiveCamera(32, 1, .25, 400);
scene.background = canvasTex(4, 512, (g, w, h) => { const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, '#060a24'); gr.addColorStop(.55, '#1d2266'); gr.addColorStop(.8, '#4b3b86'); gr.addColorStop(1, '#8a5a8f'); g.fillStyle = gr; g.fillRect(0, 0, w, h); });
scene.add(new THREE.HemisphereLight(0xc8d2ff, 0x4a3d3a, .22));
const moon = new THREE.DirectionalLight(0xc4d0ff, 1.45);
moon.position.set(14, 22, 10); moon.castShadow = true;
moon.shadow.mapSize.set(HQ ? 4096 : 2048, HQ ? 4096 : 2048); moon.shadow.radius = 3;
Object.assign(moon.shadow.camera, { left: -16, right: 16, top: 14, bottom: -14, near: 1, far: 60 }); moon.shadow.bias = -0.0004; moon.shadow.normalBias = .02;
scene.add(moon);
const warm = (x, y, z, c = 0xffb870, i = 6, d = 9) => { const l = new THREE.PointLight(c, i, d, 1.6); l.position.set(x, y, z); scene.add(l); return l; };

/* ---------- prédio ---------- */
const W = 24, D = 18, H = 3.4;
const base = rbox(W + .6, .6, D + .6, .2, mat(0x353a73)); base.position.y = -.33; scene.add(base);
// piso de madeira clara (textura gerada)
const woodTex = canvasTex(512, 512, (g, w, h) => { g.fillStyle = '#c9a985'; g.fillRect(0, 0, w, h); for (let y = 0; y < h; y += 32) { const off = (y / 32 % 2) * 128; for (let x = -128; x < w; x += 256) { const v = 190 + Math.floor(rnd() * 30); g.fillStyle = `rgb(${v + 20},${v - 5},${v - 45})`; g.fillRect(x + off + 1, y + 1, 254, 30); g.fillStyle = 'rgba(90,60,30,.08)'; for (let k = 0; k < 6; k++) g.fillRect(x + off + rnd() * 250, y + 4 + rnd() * 24, 60 + rnd() * 80, 1); } } });
woodTex.wrapS = woodTex.wrapT = THREE.RepeatWrapping; woodTex.repeat.set(6, 4.5);
const floor = new THREE.Mesh(new THREE.PlaneGeometry(W, D, 48, 36), new THREE.MeshStandardMaterial({ map: woodTex, roughness: .62, envMapIntensity: .15 })); floor.rotation.x = -Math.PI / 2; floor.position.y = .005; floor.receiveShadow = true; scene.add(floor);
const blobTex = canvasTex(128, 128, (g, w, h) => { const gr = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2); gr.addColorStop(0, 'rgba(0,0,0,.55)'); gr.addColorStop(.55, 'rgba(0,0,0,.25)'); gr.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = gr; g.fillRect(0, 0, w, h); });
const blobMat = new THREE.MeshBasicMaterial({ map: blobTex, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 });
// sombra de contato: um degradê suave no chão, embaixo de móveis e pessoas
function blob(x, z, w, d, rot = 0, parent = scene) { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), blobMat); m.rotation.x = -Math.PI / 2; m.rotation.z = rot; m.position.set(x, .045, z); m.renderOrder = 1; parent.add(m); return m; }
function rug(x, z, w, d, c, rough = .95) { const m = rbox(w, .03, d, .015, mat(c, { roughness: rough })); m.position.set(x, .02, z); m.castShadow = false; m.userData.noAO = true; scene.add(m); return m; }
rug(-3.2, -4.1, 13.6, 3.6, 0x2b3040); rug(-4.5, 1.6, 10.5, 3.0, 0x353a4c);
// paredes de vidro (fundo e esquerda)
const glassM = new THREE.MeshPhysicalMaterial({ color: 0x9fc2ff, transparent: true, opacity: .1, roughness: .05, metalness: 0, side: THREE.DoubleSide, depthWrite: false, envMapIntensity: .12 });
const frameM = mat(0xdfe5ff, { roughness: .3, metalness: .4 });
const back = new THREE.Mesh(new THREE.PlaneGeometry(W, H), glassM); back.position.set(0, H / 2, -D / 2); scene.add(back);
const left = new THREE.Mesh(new THREE.PlaneGeometry(D, H), glassM); left.rotation.y = Math.PI / 2; left.position.set(-W / 2, H / 2, 0); scene.add(left);
for (let x = -W / 2; x <= W / 2 + .01; x += 3) { const p = rbox(.12, H, .12, .04, frameM); p.position.set(x, H / 2, -D / 2); scene.add(p); }
for (let z = -D / 2; z <= D / 2 + .01; z += 3) { const p = rbox(.12, H, .12, .04, frameM); p.position.set(-W / 2, H / 2, z); scene.add(p); }
const topB = rbox(W, .14, .16, .05, frameM); topB.position.set(0, H, -D / 2); scene.add(topB);
const topL = rbox(.16, .14, D, .05, frameM); topL.position.set(-W / 2, H, 0); scene.add(topL);
// guirlanda de luzinhas
const bulbs = []; const LC = [0xffd25e, 0xff5d6c, 0x6fd3ff, 0x3ddc97, 0xc9a2ff];
const bulbG = new THREE.SphereGeometry(.05, 10, 8);
function bulbAt(x, y, z, i, parent = scene) { const m = new THREE.MeshBasicMaterial({ color: LC[i % 5] }); const b = new THREE.Mesh(bulbG, m); b.position.set(x, y, z); b.userData.base = new THREE.Color(LC[i % 5]); parent.add(b); bulbs.push(b); }
let bi = 0; for (let x = -W / 2; x <= W / 2; x += .5) bulbAt(x, H - .18 - .12 * Math.abs(Math.sin(x * Math.PI / 3)), -D / 2 + .1, bi++);
for (let z = -D / 2 + .5; z <= D / 2; z += .5) bulbAt(-W / 2 + .1, H - .18 - .12 * Math.abs(Math.sin(z * Math.PI / 3)), z, bi++);

/* ---------- cidade lá fora ---------- */
const winTex = canvasTex(64, 128, (g, w, h) => { g.fillStyle = '#0d1236'; g.fillRect(0, 0, w, h); for (let y = 4; y < h; y += 8) for (let x = 3; x < w; x += 7) { const r = rnd(); if (r > .55) { g.fillStyle = r > .9 ? '#8fdcff' : '#ffc874'; g.fillRect(x, y, 4, 5); } } });
winTex.wrapS = winTex.wrapT = THREE.RepeatWrapping;
// a torre e a cidade lá embaixo (prédios, casas, ruas com gente, carros e motos)
const cidade = criarCidade(scene, { mobile: MOBILE });
// guarda-corpo nas bordas abertas do terraço (frente e direita)
{ const gm = new THREE.MeshPhysicalMaterial({ color: 0xbfe0ff, transparent: true, opacity: .06, roughness: .05, depthWrite: false, envMapIntensity: .12, side: THREE.DoubleSide }), rm = mat(0xcfd6e6, { roughness: .3, metalness: .7 });
  const fz = D / 2 + .22, fx = W / 2 + .22;
  const g1 = new THREE.Mesh(new THREE.PlaneGeometry(W + .44, 1.0), gm); g1.position.set(0, .5, fz); g1.userData.noAO = true; scene.add(g1);
  const g2 = new THREE.Mesh(new THREE.PlaneGeometry(D + .44, 1.0), gm); g2.rotation.y = Math.PI / 2; g2.position.set(fx, .5, 0); g2.userData.noAO = true; scene.add(g2);
  const h1 = new THREE.Mesh(new THREE.CylinderGeometry(.035, .035, W + .44, 8), rm); h1.rotation.z = Math.PI / 2; h1.position.set(0, 1.02, fz); scene.add(h1);
  const h2 = new THREE.Mesh(new THREE.CylinderGeometry(.035, .035, D + .44, 8), rm); h2.rotation.x = Math.PI / 2; h2.position.set(fx, 1.02, 0); scene.add(h2);
  for (let x = -W / 2; x <= W / 2 + .01; x += 2) { const p = new THREE.Mesh(new THREE.CylinderGeometry(.03, .03, 1.02, 6), rm); p.position.set(x, .51, fz); scene.add(p); }
  for (let z = -D / 2; z < D / 2 + .01; z += 2) { const p = new THREE.Mesh(new THREE.CylinderGeometry(.03, .03, 1.02, 6), rm); p.position.set(fx, .51, z); scene.add(p); } }
{ const n = 500, p = new Float32Array(n * 3); for (let i = 0; i < n; i++) { const a = rnd() * Math.PI * 2, e = .15 + rnd() * .8, r = 180; p[i * 3] = Math.cos(a) * Math.cos(e) * r; p[i * 3 + 1] = Math.sin(e) * r; p[i * 3 + 2] = Math.sin(a) * Math.cos(e) * r; }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p, 3)); scene.add(new THREE.Points(g, new THREE.PointsMaterial({ color: 0xffffff, size: .9, sizeAttenuation: true, fog: false }))); }
const glowTex = canvasTex(128, 128, (g) => { const r = g.createRadialGradient(64, 64, 0, 64, 64, 64); r.addColorStop(0, 'rgba(255,245,225,1)'); r.addColorStop(.25, 'rgba(255,235,200,.9)'); r.addColorStop(.3, 'rgba(255,225,180,.35)'); r.addColorStop(1, 'rgba(255,220,170,0)'); g.fillStyle = r; g.fillRect(0, 0, 128, 128); });
const moonS = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, fog: false, depthWrite: false })); moonS.scale.set(26, 26, 1); moonS.position.set(-30, 46, -120); scene.add(moonS);
const SN = MOBILE ? 900 : 1600; const snowP = new Float32Array(SN * 3), snowS = new Float32Array(SN);
for (let i = 0; i < SN; i++) { let x, z; do { x = (rnd() - .5) * 80; z = (rnd() - .5) * 70; } while (x > -13 && x < 13 && z > -10 && z < 10); snowP[i * 3] = x; snowP[i * 3 + 1] = rnd() * 30; snowP[i * 3 + 2] = z; snowS[i] = .6 + rnd(); }
const snowG = new THREE.BufferGeometry(); snowG.setAttribute('position', new THREE.BufferAttribute(snowP, 3));
const flake = canvasTex(32, 32, g => { const r = g.createRadialGradient(16, 16, 0, 16, 16, 16); r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = r; g.fillRect(0, 0, 32, 32); });
scene.add(new THREE.Points(snowG, new THREE.PointsMaterial({ map: flake, size: .35, transparent: true, depthWrite: false, opacity: .85 })));

/* ---------- telas animadas ---------- */
const screens = [];
function chartTex(col, seedN, off = false) { const t = canvasTex(256, 160, () => { }); t.userData.col = col; t.userData.seed = seedN; t.userData.off = off; drawChart(t, 0); screens.push(t); return t; }
function drawChart(t, time) {
  const { g, c } = t.userData; const W = c.width, H = c.height;
  g.fillStyle = t.userData.off ? '#1b2150' : '#04130e'; g.fillRect(0, 0, W, H);
  if (t.userData.off) { g.fillStyle = 'rgba(255,210,94,.75)'; g.font = '700 30px Inter, sans-serif'; g.textAlign = 'center'; g.fillText('VAGA', W / 2, H / 2 + 10); t.needsUpdate = true; return; }
  g.strokeStyle = 'rgba(61,255,154,.12)'; for (let y = 20; y < H; y += 28) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
  const s = t.userData.seed, n = 18, base = Math.floor(time * 1.5); let v = H * .55;
  for (let i = 0; i < n; i++) { const k = base + i; const r = Math.abs(Math.sin(k * 12.9898 + s * 78.233) * 43758.5453) % 1; const up = r > .42; const o = v, cl = v + (up ? -1 : 1) * (6 + r * 18); v = Math.min(H - 20, Math.max(20, cl));
    g.fillStyle = up ? t.userData.col : '#ff4d6d'; const x = 8 + i * (W - 16) / n; g.fillRect(x + 3, Math.min(o, v) - 6, 2, Math.abs(o - v) + 12); g.fillRect(x, Math.min(o, v), 8, Math.max(3, Math.abs(o - v))); }
  g.fillStyle = 'rgba(255,255,255,.85)'; g.font = '700 16px "JetBrains Mono", monospace'; g.textAlign = 'left'; g.fillText(t.userData.label || '', 8, 18);
  t.needsUpdate = true;
}
function newsTex() { return canvasTex(512, 288, () => { }); }
function drawNews(t, time) { const { g, c } = t.userData; const W = c.width, H = c.height; g.fillStyle = '#0a1a3a'; g.fillRect(0, 0, W, H);
  g.fillStyle = '#123b7a'; g.fillRect(0, 0, W, 54); g.fillStyle = '#fff'; g.font = '800 30px Inter, sans-serif'; g.textAlign = 'left'; g.fillText('MERCADOS AO VIVO', 18, 38);
  g.strokeStyle = '#3dff9a'; g.lineWidth = 4; g.beginPath(); for (let i = 0; i <= 40; i++) { const x = 20 + i * (W - 40) / 40, y = 170 - Math.sin(i * .35 + time * .5) * 40 - i * 1.2; i ? g.lineTo(x, y) : g.moveTo(x, y); } g.stroke();
  g.fillStyle = '#ff4d6d'; g.fillRect(0, H - 50, W, 50); g.fillStyle = '#fff'; g.font = '700 24px Inter, sans-serif'; const s = 'BTC +1,2%   ·   QQQ +0,4%   ·   SPY +0,2%   ·   XRP −0,3%   ·   ETH −0,6%   ·   '; const off = (time * 60) % 900; g.fillText(s + s, -off, H - 17); t.needsUpdate = true; }

/* ---------- móveis Kenney (CC0) ---------- */
let FURN = {}; const K = 2.0; // escala do kit (meia escala) para metros
// paleta e acabamento realistas para os móveis (madeira carvalho/nogueira, tecido grafite, metal escovado, vidro)
const FURN_PAL = { wood: [0xb48a5e, .55, 0], woodDark: [0x5e412d, .5, 0], carpet: [0x56627a, .92, 0], carpetDarker: [0x2c3140, .9, 0], carpetWhite: [0xe6e2da, .9, 0], carpetBlue: [0x3d5a86, .9, 0],
  metal: [0xbfc3cc, .32, .85], metalLight: [0xe2e5ea, .3, .8], metalMedium: [0x8e939d, .35, .85], metalDark: [0x3b3e46, .4, .7], plant: [0x3f8f55, .7, 0], lamp: [0xfff1d6, .4, 0] };
const furnCache = {};
function furnMat(m) { const k = m.name; if (furnCache[k]) return furnCache[k]; const p = FURN_PAL[k]; let n;
  if (k === 'glass') n = new THREE.MeshPhysicalMaterial({ color: 0xcfe6ff, roughness: .05, metalness: 0, transparent: true, opacity: .35, envMapIntensity: 1.2 });
  else if (p) { n = new THREE.MeshStandardMaterial({ color: p[0], roughness: p[1], metalness: p[2] }); if (k === 'lamp') { n.emissive = new THREE.Color(0xffd9a0); n.emissiveIntensity = 1.4; } }
  else { n = m.clone(); n.roughness = .6; }
  n.name = k; return furnCache[k] = n; }
async function loadFurniture() { const j = await (await fetch('assets/moveis.json')).json(); const out = {}; await Promise.all(Object.entries(j).map(async ([k, b64]) => { const g = await loader.parseAsync(b64ToBuf(b64), ''); g.scene.traverse(o => { if (o.isMesh) { o.castShadow = o.receiveShadow = true; o.material = furnMat(o.material); } }); out[k] = g.scene; })); return out; }
function put(name, x, z, rotY = 0, s = K, y = 0) { const src = FURN[name]; if (!src) return null; const o = src.clone(true); o.scale.setScalar(s); o.position.set(x, y, z); o.rotation.y = rotY; scene.add(o); return o; }
// put() posiciona pelo canto do modelo; putC centraliza pelo bounding box
function putC(name, x, z, rotY = 0, s = K, y = 0) { const o = put(name, 0, 0, rotY, s, y); if (!o) return null; const b = new THREE.Box3().setFromObject(o); const c = b.getCenter(new THREE.Vector3()); o.position.x += x - c.x; o.position.z += z - c.z;
  if (y < .1 && !/rug|book|lamp|keyboard|mouse|laptop|kitchenCoffee|kitchenMicro|toaster|plant/i.test(name)) { const sx = b.max.x - b.min.x, sz = b.max.z - b.min.z; if (sx < 4 && sz < 4) blob(x, z, sx * 1.35 + .2, sz * 1.35 + .2); } return o; }

/* ---------- móveis próprios ---------- */
const deskTop = mat(0x2a2f4d, { roughness: .4 }), deskLeg = mat(0x9aa3d6, { metalness: .6, roughness: .3 });
const neon = new THREE.MeshBasicMaterial({ color: 0x3dff9a }), neonV = new THREE.MeshBasicMaterial({ color: 0xc9a2ff });
const clickables = [];
function monitor(w, h, tex) { const g = new THREE.Group(); const frame = rbox(w + .05, h + .05, .04, .015, mat(0x0c0e1c, { roughness: .3 })); g.add(frame);
  const scr = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false, color: 0xbbbbbb })); scr.position.z = .022; g.add(scr);
  const st = rbox(.04, .2, .04, .015, deskLeg); st.position.set(0, -h / 2 - .08, -.025); g.add(st); return g; }
function desk(x, z, rotY, opts = {}) {
  const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = rotY;
  const top = rbox(1.8, .05, .85, .02, deskTop); top.position.y = .74; g.add(top);
  const strip = new THREE.Mesh(new THREE.BoxGeometry(1.76, .01, .01), opts.on === false ? neonV : neon); strip.position.set(0, .71, .425); g.add(strip);
  for (const sx of [-.86, .86]) { const l = rbox(.05, .72, .75, .02, deskLeg); l.position.set(sx, .36, 0); g.add(l); }
  const on = opts.on !== false; const tex = n => chartTex(opts.col || '#3dff9a', (opts.seed || 1) * 7 + n, !on);
  // monitores baixos para o rosto aparecer por cima
  if (on) { const m1 = monitor(.56, .32, tex(0)); m1.position.set(0, 1.0, -.27); g.add(m1); const m2 = monitor(.46, .27, tex(1)); m2.position.set(-.54, .98, -.18); m2.rotation.y = .45; g.add(m2); const m3 = monitor(.46, .27, tex(2)); m3.position.set(.54, .98, -.18); m3.rotation.y = -.45; g.add(m3); screens[screens.length - 3].userData.label = opts.label || ''; }
  else { const m1 = monitor(.5, .3, tex(0)); m1.position.set(0, .98, -.27); g.add(m1); }
  const kb = put('computerKeyboard', 0, 0, 0, K * .9); if (kb) { g.add(kb); const b = new THREE.Box3().setFromObject(kb); kb.position.set(-(b.min.x + b.max.x) / 2, .765, .3 - (b.min.z + b.max.z) / 2); }
  const ms = put('computerMouse', 0, 0, 0, K); if (ms) { g.add(ms); ms.position.set(.38, .765, .3); }
  const mug = new THREE.Mesh(new THREE.CylinderGeometry(.045, .04, .1, 16), mat(opts.mug || 0xf4f4f8)); mug.position.set(.66, .815, .16); mug.castShadow = true; g.add(mug);
  if (on) { const gl = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 1.4), new THREE.MeshBasicMaterial({ map: glowTex, color: 0x3dff9a, transparent: true, opacity: .14, depthWrite: false, blending: THREE.AdditiveBlending })); gl.rotation.x = -Math.PI / 2; gl.position.set(0, .03, .2); g.add(gl); }
  blob(0, 0, 2.3, 1.3, 0, g).position.y = .045;
  scene.add(g); return g;
}
function chairAt(x, z, rotY) { const c = putC('chairDesk', x, z, rotY); if (!c) return null; return c; }
function plantAt(x, z, kind = 'pottedPlant', s = K * 1.1) { return putC(kind, x, z, rnd() * 6, s); }
function label3d(text, sub, color, pos) { const el = document.createElement('div'); el.className = 'tag3d'; el.innerHTML = `<b style="color:${color}">${text}</b>${sub ? `<span>${sub}</span>` : ''}`; $('#labels').appendChild(el); return { el, pos }; }
const labels = [];
function sign(text, color, w, h) { const t = canvasTex(512, 128, (g, W, Hh) => { g.fillStyle = 'rgba(10,14,40,.88)'; g.beginPath(); g.roundRect(0, 0, W, Hh, 40); g.fill(); g.fillStyle = color; g.font = '800 54px Inter, sans-serif'; g.textAlign = 'center'; g.fillText(text, W / 2, 84); });
  return new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: t, transparent: true, toneMapped: false, depthWrite: false })); }

/* ---------- layout ---------- */
// SALA DE OPERAÇÕES (fundo à esquerda, paredes de vidro): traders em fileiras de frente para o telão.
// A sala se rearruma sozinha conforme a mesa cresce: 1 fileira até 6 lugares, 2 até 12, 3 depois disso.
const SALA = { x0: -W / 2, x1: 3.2, z0: -D / 2, z1: -.4, cx: -4.6, portaX: 1.9, portaZ: -2.0, entrada: [2.6, -1.0] };
const TRADER_POS = [], VAGA_POS = [];
function lugaresSala(n) { const rows = n <= 6 ? 1 : n <= 12 ? 2 : 3, cols = Math.ceil(n / rows), pitch = Math.min(2.3, 12.2 / cols);
  const zs = rows === 1 ? [-4.1] : rows === 2 ? [-5.1, -2.2] : [-6.1, -3.95, -1.8]; const out = [];
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols && out.length < n; c++) out.push([+(SALA.cx + (c - (cols - 1) / 2) * pitch).toFixed(2), zs[r]]);
  return out; }
function arrumarMesa(n) { const l = lugaresSala(n + 1); TRADER_POS.splice(0, TRADER_POS.length, ...l.slice(0, n)); VAGA_POS.splice(0, VAGA_POS.length, l[n]); }
arrumarMesa(3);
// onde alguém fica em pé para falar com um trader (atrás da cadeira, um pouco ao lado)
const atrasDe = ([x, z]) => [x + .55, z + .82];
const TEAM_POS = [[-8, 1.4], [-4.5, 1.4], [-1, 1.4]];
const STUDENT_POS = [[6.2, 4.2], [8.8, 4.2], [6.2, 6.6], [8.8, 6.6]];
const wallTex = canvasTex(MOBILE ? 1536 : 2048, MOBILE ? 440 : 587, () => { });
const news = [newsTex(), newsTex()];
let boardTex;
// ---- recreação: pingue-pongue, pebolim e fliperama ----
const ping = { bola: null, x0: 0, z: 0 };
function pingPong(x, z) { const g = new THREE.Group(); g.position.set(x, 0, z);
  const tt = canvasTex(512, 286, (c, w, h) => { c.fillStyle = '#1d4f8c'; c.fillRect(0, 0, w, h); c.strokeStyle = '#fff'; c.lineWidth = 6; c.strokeRect(3, 3, w - 6, h - 6); c.lineWidth = 3; c.beginPath(); c.moveTo(0, h / 2); c.lineTo(w, h / 2); c.stroke(); });
  const top = new THREE.Mesh(new THREE.BoxGeometry(2.74, .04, 1.525), [mat(0x163e6e), mat(0x163e6e), new THREE.MeshStandardMaterial({ map: tt, roughness: .45 }), mat(0x163e6e), mat(0x163e6e), mat(0x163e6e)]); top.position.y = .76; top.castShadow = top.receiveShadow = true; g.add(top);
  for (const [lx, lz] of [[-1.15, -.6], [1.15, -.6], [-1.15, .6], [1.15, .6]]) { const l = rbox(.06, .74, .06, .02, deskLeg); l.position.set(lx, .37, lz); g.add(l); }
  const net = new THREE.Mesh(new THREE.PlaneGeometry(1.6, .15), new THREE.MeshStandardMaterial({ color: 0xf4f4f4, transparent: true, opacity: .55, side: THREE.DoubleSide })); net.rotation.y = Math.PI / 2; net.position.y = .855; g.add(net);
  const bola = new THREE.Mesh(new THREE.SphereGeometry(.022, 10, 8), new THREE.MeshBasicMaterial({ color: 0xfff1d6 })); scene.add(bola); ping.bola = bola; ping.x0 = x; ping.z = z;
  blob(0, 0, 3.2, 2.0, 0, g).position.y = .045; scene.add(g); }
function pebolim(x, z) { const g = new THREE.Group(); g.position.set(x, 0, z);
  const caixa = rbox(.75, .2, 1.2, .03, mat(0x6b4426, { roughness: .5 })); caixa.position.y = .82; g.add(caixa);
  const campo = new THREE.Mesh(new THREE.PlaneGeometry(.66, 1.1), mat(0x2f8f45, { roughness: .8 })); campo.rotation.x = -Math.PI / 2; campo.position.y = .93; g.add(campo);
  for (const lz of [-.48, .48]) for (const lx of [-.3, .3]) { const l = rbox(.06, .72, .06, .02, mat(0x3a2414)); l.position.set(lx, .36, lz); g.add(l); }
  for (let i = 0; i < 6; i++) { const zz = -.45 + i * .18; const barra = new THREE.Mesh(new THREE.CylinderGeometry(.012, .012, 1.1, 6), mat(0xd0d4dc, { metalness: .8, roughness: .3 })); barra.rotation.z = Math.PI / 2; barra.position.set(0, .97, zz); g.add(barra);
    for (let k = 0; k < 3; k++) { const j = new THREE.Mesh(new THREE.BoxGeometry(.035, .1, .025), mat(i % 2 ? 0xd23a3a : 0x2f6fd8)); j.position.set(-.2 + k * .2, .95, zz); g.add(j); } }
  g.traverse(o => { if (o.isMesh) o.castShadow = true; }); blob(0, 0, 1.2, 1.6, 0, g).position.y = .045; scene.add(g); }
const arcadeTex = canvasTex(256, 200, () => { });
function fliperama(x, z) { const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = Math.PI / 2;
  const corpo = rbox(.7, 1.75, .7, .04, mat(0x26124a, { roughness: .4 })); corpo.position.y = .875; g.add(corpo);
  const tela = new THREE.Mesh(new THREE.PlaneGeometry(.52, .4), new THREE.MeshBasicMaterial({ map: arcadeTex, toneMapped: false })); tela.position.set(0, 1.32, .355); tela.rotation.x = -.15; g.add(tela);
  const painel = rbox(.66, .06, .3, .02, mat(0x111018)); painel.position.set(0, 1.0, .42); painel.rotation.x = .35; g.add(painel);
  for (const [bx, c] of [[-.15, 0xff4d6d], [.05, 0x3dff9a], [.17, 0xffd25e]]) { const b = new THREE.Mesh(new THREE.CylinderGeometry(.025, .025, .02, 10), new THREE.MeshBasicMaterial({ color: c })); b.position.set(bx, 1.04, .45); g.add(b); }
  const tt = sign('ARCADE', '#ff6fcf', .6, .15); tt.position.set(0, 1.66, .36); g.add(tt);
  g.traverse(o => { if (o.isMesh) o.castShadow = true; }); scene.add(g); }
function drawArcade(t) { const { g, c } = arcadeTex.userData; const W = c.width, H = c.height; g.fillStyle = '#05030f'; g.fillRect(0, 0, W, H);
  for (let i = 0; i < 18; i++) { g.fillStyle = i % 3 ? '#6fd3ff' : '#ff6fcf'; g.fillRect((i * 37 + t * 60 * (1 + i % 3)) % W, (i * 53) % H, 4, 4); }
  const px = W / 2 + Math.sin(t * 1.7) * 80; g.fillStyle = '#3dff9a'; g.beginPath(); g.moveTo(px, H - 30); g.lineTo(px - 16, H - 6); g.lineTo(px + 16, H - 6); g.fill();
  g.fillStyle = '#ffd25e'; g.font = '700 20px "JetBrains Mono", monospace'; g.fillText('SCORE ' + String(Math.floor(t * 37) % 99999).padStart(5, '0'), 12, 24); arcadeTex.needsUpdate = true; }
function buildOffice() {
  // SALA DE OPERAÇÕES: telão grande na parede do fundo, vidro na frente e à direita (porta no canto)
  { const tw = 9.6, th = 2.75, wall = new THREE.Group();
    const fr = rbox(tw + .3, th + .3, .16, .06, mat(0x0b0d1e, { roughness: .35, metalness: .3 })); wall.add(fr);
    const scr = new THREE.Mesh(new THREE.PlaneGeometry(tw, th), new THREE.MeshBasicMaterial({ map: wallTex, toneMapped: false })); scr.position.z = .09; wall.add(scr);
    wall.position.set(SALA.cx, 1.82, -D / 2 + .25); scene.add(wall);
    const glow = new THREE.Mesh(new THREE.PlaneGeometry(tw + 3, 3.2), new THREE.MeshBasicMaterial({ map: glowTex, color: 0x4fa8ff, transparent: true, opacity: .1, depthWrite: false, blending: THREE.AdditiveBlending })); glow.rotation.x = -Math.PI / 2; glow.position.set(SALA.cx, .03, -D / 2 + 1.4); scene.add(glow); }
  rug(SALA.cx, (SALA.z0 + SALA.z1) / 2 + .3, SALA.x1 - SALA.x0 - 1.2, SALA.z1 - SALA.z0 - 1.1, 0x252a3a);
  { const gm = new THREE.MeshPhysicalMaterial({ color: 0xbfe0ff, transparent: true, opacity: .07, roughness: .05, depthWrite: false, envMapIntensity: .12, side: THREE.DoubleSide }), rail = mat(0xdfe5ff, { metalness: .5, roughness: .3 });
    const fw = SALA.portaX - SALA.x0, sw = SALA.portaZ - SALA.z0;
    const f = new THREE.Mesh(new THREE.PlaneGeometry(fw, 2.6), gm); f.position.set(SALA.x0 + fw / 2, 1.3, SALA.z1); f.userData.noAO = true; scene.add(f);
    const r = new THREE.Mesh(new THREE.PlaneGeometry(sw, 2.6), gm); r.rotation.y = Math.PI / 2; r.position.set(SALA.x1, 1.3, SALA.z0 + sw / 2); r.userData.noAO = true; scene.add(r);
    const t1 = rbox(fw, .06, .06, .02, rail); t1.position.set(SALA.x0 + fw / 2, 2.6, SALA.z1); scene.add(t1); const t2 = rbox(.06, .06, sw, .02, rail); t2.position.set(SALA.x1, 2.6, SALA.z0 + sw / 2); scene.add(t2);
    for (let x = SALA.x0 + 3; x < SALA.portaX; x += 3) { const m = rbox(.05, 2.6, .05, .02, rail); m.position.set(x, 1.3, SALA.z1); scene.add(m); }
    const pf = rbox(.08, 2.6, .08, .03, rail); pf.position.set(SALA.portaX, 1.3, SALA.z1); scene.add(pf); const pr = rbox(.08, 2.6, .08, .03, rail); pr.position.set(SALA.x1, 1.3, SALA.portaZ); scene.add(pr);
    const sg = sign('SALA DE OPERAÇÕES', '#3dff9a', 2.6, .62); sg.position.set(SALA.cx, 2.95, SALA.z1 + .02); scene.add(sg);
    warm(SALA.cx - 3.6, 2.8, -4, 0xc8ffe6, 4.5, 10); warm(SALA.cx + 3.6, 2.8, -4, 0xc8ffe6, 4.5, 10); }

  // COPA (fundo à direita): balcão com pia, geladeira, cafeteira, micro-ondas, bebedouro, mesas altas
  rug(9.2, -6.6, 5.4, 4.4, 0xd8d2c4, .8);
  const kz = -8.55;
  putC('kitchenFridgeLarge', 11.25, kz + .05, 0); putC('kitchenCabinet', 10.1, kz, 0); putC('kitchenSink', 9.15, kz, 0); putC('kitchenCabinet', 8.2, kz, 0); putC('kitchenBar', 7.25, kz, 0);
  const coffee = putC('kitchenCoffeeMachine', 8.2, kz, 0); if (coffee) coffee.position.y = .9; const mw = putC('kitchenMicrowave', 10.1, kz, 0); if (mw) mw.position.y = .9;
  const toaster = putC('toaster', 7.3, kz, 0); if (toaster) toaster.position.y = .9;
  for (const ux of [8.2, 9.15, 10.1]) { const u = putC('kitchenCabinetUpper', ux, kz - .1, 0); if (u) u.position.y = 1.55; }
  // bebedouro (galão azul)
  { const g = new THREE.Group(); g.position.set(6.4, 0, -8.4); const body = rbox(.38, 1.0, .38, .05, mat(0xeef0f6, { roughness: .4 })); body.position.y = .5; g.add(body);
    const bottle = new THREE.Mesh(new THREE.CylinderGeometry(.15, .15, .42, 24), new THREE.MeshPhysicalMaterial({ color: 0x5fb6ff, transparent: true, opacity: .55, roughness: .05, transmission: .3 })); bottle.position.y = 1.23; g.add(bottle);
    const neck = new THREE.Mesh(new THREE.CylinderGeometry(.05, .05, .06, 12), mat(0x5fb6ff)); neck.position.y = 1.0; g.add(neck);
    for (const [cx, c] of [[-.07, 0x3a8cff], [.07, 0xff4d4d]]) { const tap = new THREE.Mesh(new THREE.BoxGeometry(.04, .04, .05), mat(c)); tap.position.set(cx, .78, .2); g.add(tap); }
    const tray = new THREE.Mesh(new THREE.BoxGeometry(.24, .02, .1), mat(0x9aa3d6)); tray.position.set(0, .62, .2); g.add(tray);
    g.traverse(o => { if (o.isMesh) o.castShadow = true; }); scene.add(g); }
  // mesas altas e banquetas
  [[8.2, -6.4], [10.4, -6.4]].forEach(([x, z]) => { putC('tableRound', x, z, 0); putC('chairModernCushion', x - .75, z, Math.PI / 2); putC('chairModernCushion', x + .75, z, -Math.PI / 2); });
  putC('trashcan', 5.9, -7.7, 0); plantAt(11.3, -5.2);
  const cs = sign('COPA', '#ffd25e', 1.4, .35); cs.position.set(9.2, 2.65, -D / 2 + .2); scene.add(cs);

  // CORRETORA (cofre) ao lado direito
  const vault = new THREE.Group(); vault.position.set(10.6, 0, -2.2);
  { const body = rbox(1.6, 1.8, 1.4, .18, mat(0xe0b03c, { metalness: .65, roughness: .28 })); body.position.y = .9; vault.add(body);
    const door = new THREE.Mesh(new THREE.CylinderGeometry(.5, .5, .1, 40), mat(0xa77d1c, { metalness: .8, roughness: .25 })); door.rotation.z = Math.PI / 2; door.position.set(-.82, .95, 0); vault.add(door);
    const dial = new THREE.Mesh(new THREE.TorusGeometry(.22, .04, 12, 32), mat(0xfff0b0, { metalness: .9, roughness: .2 })); dial.rotation.y = Math.PI / 2; dial.position.set(-.9, .95, 0); vault.add(dial); vault.userData.dial = dial;
    const sg = sign('CORRETORA SIMULADA', '#ffd25e', 2.2, .55); sg.position.set(-.4, 2.25, 0); sg.rotation.y = -Math.PI / 2; vault.add(sg); }
  scene.add(vault); warm(9.6, 2.6, -2.2, 0xffc45a, 7, 6); window.__vault = vault;

  // IMPRESSORA / estação de cópias
  { const g = new THREE.Group(); g.position.set(5.2, 0, -1.6); const cab = rbox(1.1, .7, .6, .04, mat(0xd9dbe6)); cab.position.y = .35; g.add(cab);
    const pr = rbox(.9, .45, .55, .05, mat(0xf3f4f8, { roughness: .35 })); pr.position.y = .93; g.add(pr); const tr = rbox(.6, .04, .35, .01, mat(0x2a2f4d)); tr.position.set(0, 1.17, .05); g.add(tr);
    const paper = new THREE.Mesh(new THREE.BoxGeometry(.3, .02, .4), mat(0xffffff)); paper.position.set(0, 1.2, .05); g.add(paper);
    const led = new THREE.Mesh(new THREE.SphereGeometry(.02, 8, 8), new THREE.MeshBasicMaterial({ color: 0x3dff9a })); led.position.set(.35, 1.0, .28); g.add(led);
    g.rotation.y = -Math.PI / 2; scene.add(g); putC('trashcan', 5.2, -.6, 0); }

  // LOUNGE (frente à esquerda): sofás, mesa de centro, TV, estante, luminárias, tapete redondo
  rug(-8.2, 6.2, 6.2, 4.6, 0x8c8073);
  putC('loungeSofaLong', -8.4, 8.3, Math.PI); putC('loungeSofa', -10.9, 6.1, Math.PI / 2); putC('loungeChairRelax', -5.7, 6.4, -Math.PI / 2 - .3);
  pingPong(-8.35, 6.0); pebolim(-10.9, 3.35); fliperama(-11.45, 4.75);
  putC('lampRoundFloor', -11.3, 8.4, 0); putC('lampSquareFloor', -6.0, 8.4, 0);

  { const tv = putC('televisionModern', -8.4, 4.25, Math.PI); }
  plantAt(-6.0, 4.3, 'plantSmall2', K * 1.4); plantAt(-11.4, 4.9, 'pottedPlant');
  const ls = sign('RECREAÇÃO', '#c9a2ff', 1.9, .48); ls.position.set(-8.4, 2.75, 3.42); scene.add(ls);
  { const gm = new THREE.MeshPhysicalMaterial({ color: 0xe6d2ff, transparent: true, opacity: .07, roughness: .05, depthWrite: false, envMapIntensity: .12, side: THREE.DoubleSide }), rail = mat(0xdfe5ff, { metalness: .5, roughness: .3 });
    const a = new THREE.Mesh(new THREE.PlaneGeometry(6.6, 2.6), gm); a.position.set(-W / 2 + 3.3, 1.3, 3.4); a.userData.noAO = true; scene.add(a);
    const b = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 2.6), gm); b.rotation.y = Math.PI / 2; b.position.set(-5.0, 1.3, 4.8 + 2.1); b.userData.noAO = true; scene.add(b);
    const t1 = rbox(6.6, .06, .06, .02, rail); t1.position.set(-W / 2 + 3.3, 2.6, 3.4); scene.add(t1); const t2 = rbox(.06, .06, 4.2, .02, rail); t2.position.set(-5.0, 2.6, 6.9); scene.add(t2); }

  // SALA DE REUNIÃO (vidro), centro-frente
  { const x0 = -3.6, x1 = 2.6, z0 = 4.4, z1 = 8.8; const gm = new THREE.MeshPhysicalMaterial({ color: 0xbfe0ff, transparent: true, opacity: .08, roughness: .05, depthWrite: false, envMapIntensity: .12, side: THREE.DoubleSide });
    const wA = new THREE.Mesh(new THREE.PlaneGeometry(x1 - x0, 2.4), gm); wA.position.set((x0 + x1) / 2, 1.2, z0); scene.add(wA);
    const wB = new THREE.Mesh(new THREE.PlaneGeometry(z1 - z0, 2.4), gm); wB.rotation.y = Math.PI / 2; wB.position.set(x0, 1.2, (z0 + z1) / 2); scene.add(wB);
    const wC = wB.clone(); wC.position.x = x1; scene.add(wC);
    const rail = mat(0xdfe5ff, { metalness: .5, roughness: .3 }); const r1 = rbox(x1 - x0, .05, .06, .02, rail); r1.position.set((x0 + x1) / 2, 2.4, z0); scene.add(r1);
    for (const xx of [x0, x1]) { const r = rbox(.06, .05, z1 - z0, .02, rail); r.position.set(xx, 2.4, (z0 + z1) / 2); scene.add(r); }
    const tbl = rbox(3.2, .06, 1.3, .25, mat(0x8a6a4e, { roughness: .45 })); tbl.position.set(-.5, .74, 6.6); scene.add(tbl);
    const leg = rbox(.12, .72, .9, .04, deskLeg); leg.position.set(-.5, .36, 6.6); scene.add(leg);
    for (const cx of [-1.6, -.5, .6]) { putC('chairModernFrameCushion', cx, 5.6, Math.PI) || putC('chairCushion', cx, 5.6, Math.PI); putC('chairModernFrameCushion', cx, 7.6, 0) || putC('chairCushion', cx, 7.6, 0); }
    const lap = putC('laptop', -1.1, 6.5, .4, K, .77);
    const scr = new THREE.Mesh(new THREE.PlaneGeometry(1.8, 1.0), new THREE.MeshBasicMaterial({ map: news[1], toneMapped: false })); scr.position.set(-.5, 1.5, 8.75); scr.rotation.y = Math.PI; scene.add(scr);
    plantAt(2.2, 8.4, 'plantSmall1', K * 1.4);
    const rs = sign('SALA DE REUNIÃO', '#8fe6ff', 2.0, .5); rs.position.set(-.5, 2.75, z0); scene.add(rs); }

  // ESCOLA (sala de treino) à direita, com quadro
  { const sg = new THREE.MeshPhysicalMaterial({ color: 0x8fe6ff, transparent: true, opacity: .08, roughness: .05, depthWrite: false, envMapIntensity: .12, side: THREE.DoubleSide });
    const w1 = new THREE.Mesh(new THREE.PlaneGeometry(7.8, 2.4), sg); w1.position.set(7.9, 1.2, 1.4); scene.add(w1);
    const w2 = new THREE.Mesh(new THREE.PlaneGeometry(7.4, 2.4), sg); w2.rotation.y = Math.PI / 2; w2.position.set(4.0, 1.2, 5.1); scene.add(w2);
    rug(7.9, 5.1, 7.4, 7.0, 0x3a5560);
    boardTex = canvasTex(1024, 512, () => { });
    const b = rbox(4.2, 1.9, .1, .05, mat(0x5a3d2a)); b.position.set(7.6, 1.45, 1.6); scene.add(b);
    const s = new THREE.Mesh(new THREE.PlaneGeometry(3.95, 1.7), new THREE.MeshStandardMaterial({ map: boardTex, roughness: .9, emissive: 0xffffff, emissiveMap: boardTex, emissiveIntensity: .25 })); s.position.set(7.6, 1.45, 1.66); scene.add(s);
    STUDENT_POS.forEach(([x, z]) => { const t = putC('desk', x, z - .55, Math.PI); if (t) STUDENT_DESK_Y = new THREE.Box3().setFromObject(t).max.y; });
    putC('bookcaseOpen', 11.6, 5.4, -Math.PI / 2); plantAt(11.3, 8.3); plantAt(4.5, 8.4, 'plantSmall3', K * 1.4);
    const es = sign('ESCOLA', '#8fe6ff', 1.4, .35); es.position.set(7.6, 2.75, 1.4); scene.add(es);
    warm(7.6, 2.6, 4.6, 0x8fe6ff, 5, 9); }

  // entrada: cabideiro, plantas, lixeiras
  putC('coatRack', 11.4, 1.0, 0); plantAt(-11.3, -8.3); plantAt(3.9, -8.3, 'plantSmall1', K * 1.4); plantAt(-5.9, -8.3, 'plantSmall2', K * 1.4); plantAt(-11.3, -1.2);
  putC('trashcan', -2.8, 3.1, 0);
  // árvore de natal na entrada do lounge
  { const tree = new THREE.Group(); tree.position.set(-4.8, 0, 8.3);
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(.08, .1, .4, 10), mat(0x7a4a2a)); trunk.position.y = .2; tree.add(trunk);
    [[.75, 1.0, .6], [.6, .85, 1.2], [.42, .7, 1.75]].forEach(([r, h, y]) => { const c = new THREE.Mesh(new THREE.ConeGeometry(r, h, 24), mat(0x1f9e64, { roughness: .7 })); c.position.y = y; c.castShadow = true; tree.add(c); });
    for (let i = 0; i < 24; i++) { const a = i * 2.4, y = .35 + i * .065, r = .72 - i * .026; bulbAt(Math.cos(a) * r, y, Math.sin(a) * r, i, tree); }
    const star = new THREE.Mesh(new THREE.OctahedronGeometry(.14), new THREE.MeshBasicMaterial({ color: 0xffd25e })); star.position.y = 2.2; tree.add(star); scene.add(tree); }
  // neon
  { const t = canvasTex(512, 256, (g, w) => { g.textAlign = 'center'; g.font = '800 120px "Bricolage Grotesque", sans-serif'; g.shadowColor = '#ff5fa2'; g.shadowBlur = 24; g.fillStyle = '#ffd1e6'; g.fillText('TRADE', w / 2, 110); g.shadowColor = '#ffb547'; g.fillStyle = '#ffe3b0'; g.fillText('CITY', w / 2, 230); });
    const n = new THREE.Mesh(new THREE.PlaneGeometry(3.0, 1.5), new THREE.MeshBasicMaterial({ map: t, transparent: true, toneMapped: false, depthWrite: false })); n.rotation.y = Math.PI / 2; n.position.set(-W / 2 + .15, 2.2, -4.5); scene.add(n); }
  warm(-4.5, 2.5, 1.6, 0xe2c8ff, 3.2, 8);
  warm(-8.4, 2.2, 6.4, 0xffc890, 5, 7); warm(-.5, 2.3, 6.6, 0xfff1dc, 4, 6); warm(9.2, 2.4, -6.8, 0xffe2b8, 5, 7);
}

/* ================= pessoas ================= */
// Corpos de proporção real (Quaternius Universal Base Characters, CC0) + 17 movimentos (Universal Animation Library, CC0).
// Roupa pintada por região do esqueleto: camisa no tronco e braços, calça no quadril e pernas, sapato nos pés.
const mixers = []; const actors = {}; const ANIMS = {}; const HAIR = {};
const AN = { Idle: 'Idle_Loop', Talk: 'Idle_Talking_Loop', Walk: 'Walk_Loop', WalkF: 'Walk_Formal_Loop', SitDown: 'Sitting_Enter', StandUp: 'Sitting_Exit', Sitting: 'Sitting_Idle_Loop', SitTalk: 'Sitting_Talking_Loop',
  Interact: 'Interact', PickUp: 'PickUp_Table', Dance: 'Dance_Loop', Walk_Carry: 'Walk_Carry_Loop', Drink: 'Consume', Arms: 'Idle_FoldArms_Loop', Phone: 'Idle_TalkingPhone_Loop', Yes: 'Yes', No: 'Idle_No_Loop' };
const SKIN = [0xf6d6bd, 0xe8b893, 0xd09a70, 0xa8714c, 0x86563a];
const BODY_AVG = new THREE.Color(169 / 255, 114 / 255, 80 / 255); // cor média da textura da pele (medida)
function clothAttr(mesh) {
  const g = mesh.geometry; if (g.attributes.cloth) return;
  const names = mesh.skeleton.bones.map(b => b.name); const si = g.attributes.skinIndex, sw = g.attributes.skinWeight, n = si.count; const arr = new Float32Array(n * 4);
  const cls = names.map(nm => /^spine|clavicle|upperarm/.test(nm) ? 0 : /lowerarm/.test(nm) ? 1 : /pelvis|thigh|calf/.test(nm) ? 2 : /foot|ball/.test(nm) ? 3 : -1);
  for (let i = 0; i < n; i++) for (let k = 0; k < 4; k++) { const c = cls[si.getComponent(i, k)]; if (c >= 0) arr[i * 4 + c] += sw.getComponent(i, k); }
  g.setAttribute('cloth', new THREE.BufferAttribute(arr, 4));
}
function bodyMaterial(base, o) {
  const m = base.clone(); m.roughness = .6; m.metalness = 0; m.envMapIntensity = .5;
  // tom de pele: divide pela cor média da textura (as duas em linear) e mantém os detalhes do rosto
  { const s = new THREE.Color().setHex(o.skin), a = BODY_AVG.clone(); s.convertSRGBToLinear(); a.convertSRGBToLinear(); m.color.setRGB(s.r / a.r, s.g / a.g, s.b / a.b, THREE.LinearSRGBColorSpace); }
  const U = { uShirt: { value: new THREE.Color(o.shirt) }, uPants: { value: new THREE.Color(o.pants || 0x2a2f45) }, uShoes: { value: new THREE.Color(o.shoes || 0x1b1b22) }, uLong: { value: o.long === false ? 0 : 1 }, uCollar: { value: new THREE.Color(o.collar || o.shirt) },
    uSuit: { value: o.inner !== undefined ? 1 : 0 }, uInner: { value: new THREE.Color(o.inner ?? 0xffffff) }, uTie: { value: new THREE.Vector4(...new THREE.Color(o.tie ?? 0).toArray(), o.tie !== undefined ? 1 : 0) },
    uVBot: { value: o.vbot ?? .42 }, uHem: { value: o.hem ?? -9 }, uBelt: { value: o.belt === false || o.hem !== undefined ? 0 : 1 }, uFem: { value: o.file === 'Regular_Female_FullBody' ? 1 : 0 } };
  m.userData.U = U;
  m.onBeforeCompile = sh => {
    Object.assign(sh.uniforms, U);
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nattribute vec4 cloth; varying vec4 vCloth; varying float vY; varying vec3 vP; uniform float uLong;').replace('#include <begin_vertex>', '#include <begin_vertex>\nvCloth = cloth; vY = position.y; vP = position.xyz; transformed += objectNormal * (clamp(cloth.x + cloth.y * uLong + cloth.z, 0., 1.) * .004 + cloth.w * .016);');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec4 vCloth; varying float vY; varying vec3 vP; uniform vec3 uShirt, uPants, uShoes, uCollar, uInner; uniform vec4 uTie; uniform float uLong, uSuit, uVBot, uHem, uBelt; float clothM;')
      .replace('#include <map_fragment>', `#include <map_fragment>
        float shr = vCloth.x + vCloth.y * uLong, par = vCloth.z, sor = vCloth.w;
        clothM = smoothstep(.4, .56, shr + par + sor);
        vec3 cc = mix(uPants, uShirt, smoothstep(-.08, .08, shr - par));
        cc = mix(cc, uShoes, smoothstep(-.08, .08, sor - max(par, shr)));
        float belt = smoothstep(.2, .06, abs(shr - par)) * step(.5, shr + par) * uBelt;
        cc = mix(cc, vec3(.03, .025, .02), belt * .9);
        // paletó/blazer: abertura em V mostra a camisa de dentro, com gravata no meio
        float shM = smoothstep(-.08, .08, shr - par) * step(.5, shr);
        if (uSuit > .5 && vP.z > .02) {
          float k = clamp((vP.y - uVBot) / (.67 - uVBot), 0., 1.);
          float halfW = .012 + k * .062;
          float inV = step(uVBot, vP.y) * step(vP.y, .72) * (1. - smoothstep(halfW - .006, halfW + .006, abs(vP.x)));
          cc = mix(cc, uInner, inV * shM);
          float halfT = .011 + (.66 - vP.y) * .03;
          float tie = step(uVBot - .03, vP.y) * step(vP.y, .66) * (1. - smoothstep(halfT - .004, halfT + .004, abs(vP.x))) * uTie.a;
          cc = mix(cc, uTie.rgb, tie * shM);
        }
        // vestido/saia: abaixo da barra a perna fica à mostra
        float bare = step(vP.y, uHem) * smoothstep(.3, .6, par) * (1. - smoothstep(.3, .6, sor));
        clothM *= 1. - bare;
        diffuseColor.rgb = mix(diffuseColor.rgb, cc, clothM);`)
      .replace('#include <roughnessmap_fragment>', '#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, .82, clothM);')
      .replace('#include <normal_fragment_maps>', '#include <normal_fragment_maps>\nnormal = normalize(mix(normal, nonPerturbedNormal, clothM));');
  };
  m.customProgramCacheKey = () => 'tc-body';
  return m;
}
function attachHair(r, skel, src, color) {
  const h = SkeletonUtils.clone(src.scene); let hm = null; h.traverse(o => { if (o.isSkinnedMesh) hm = o; }); if (!hm) return;
  const byName = {}; skel.bones.forEach(b => byName[b.name] = b);
  const bones = hm.skeleton.bones.map(b => byName[b.name] || b);
  hm.bind(new THREE.Skeleton(bones, hm.skeleton.boneInverses), hm.bindMatrix);
  hm.material = hm.material.clone(); hm.material.color = new THREE.Color(color); hm.material.roughness = .7; hm.material.envMapIntensity = .35; hm.material.side = THREE.DoubleSide;
  hm.castShadow = true; hm.frustumCulled = false; hm.removeFromParent(); r.add(hm);
}
// visual de cada pessoa da referência: cabelo longo/cacheado e óculos, presos ao osso da cabeça
function hairMat(c) { return new THREE.MeshStandardMaterial({ color: c, roughness: .5, metalness: 0, side: THREE.DoubleSide, envMapIntensity: .35 }); }
function strands(geo, amp, freq, curl = 0) { const ps = geo.attributes.position, v = new THREE.Vector3(); for (let i = 0; i < ps.count; i++) { v.fromBufferAttribute(ps, i); const a = Math.atan2(v.x, v.z);
    let k = 1 + amp * Math.sin(a * freq) + amp * .5 * Math.sin(a * freq * 2.3 + v.y * 40);
    if (curl) k += curl * (Math.sin(v.x * 90) * Math.sin(v.y * 85) * Math.sin(v.z * 95));
    v.x *= k; v.z *= k; ps.setXYZ(i, v.x, v.y, v.z); } geo.computeVertexNormals(); return geo; }
function buildHair(style, color, C, R) {
  const g = new THREE.Group(), m = hairMat(color);
  const gap = 1.7; // abertura do rosto
  if (style === 'cacheado') {
    const top = new THREE.Mesh(strands(new THREE.SphereGeometry(R * 1.42, 48, 32, 0, Math.PI * 2, 0, Math.PI * .34), .02, 9, .09), m); top.position.set(C.x, C.y + R * .02, C.z - R * .08); g.add(top);
    const back = new THREE.Mesh(strands(new THREE.SphereGeometry(R * 1.5, 48, 32, Math.PI / 2 + gap / 2, Math.PI * 2 - gap, Math.PI * .22, Math.PI * .5), .02, 9, .1), m); back.scale.set(1, 1.05, 1); back.position.set(C.x, C.y - R * .25, C.z - R * .18); g.add(back);
  } else {
    const top = new THREE.Mesh(strands(new THREE.SphereGeometry(R * 1.1, 48, 24, 0, Math.PI * 2, 0, Math.PI * .36), .012, 40), m); top.scale.set(1, 1.04, 1.06); top.position.set(C.x, C.y + R * .04, C.z - R * .04); g.add(top);
    const side = new THREE.Mesh(strands(new THREE.SphereGeometry(R * 1.12, 48, 24, Math.PI / 2 + gap / 2, Math.PI * 2 - gap, Math.PI * .2, Math.PI * .45), .012, 40), m); side.scale.set(1, 1.04, 1.06); side.position.set(C.x, C.y + R * .04, C.z - R * .04); g.add(side);
    const len = style === 'medio' ? R * 2.1 : R * 2.9;
    const cur = new THREE.Mesh(strands(new THREE.CylinderGeometry(R * 1.1, R * 1.32, len, 48, 10, true, 1.25, Math.PI * 2 - 2.5), .018, 46), m); cur.scale.set(1, 1, .82); cur.position.set(C.x, C.y - R * .25 - len / 2 + R * .3, C.z - R * .3); g.add(cur);
  }
  g.traverse(x => { if (x.isMesh) { x.castShadow = true; } }); return g;
}
function buildGlasses(eL, eR, color = 0x16161c) {
  const g = new THREE.Group(), m = new THREE.MeshStandardMaterial({ color, roughness: .3, metalness: .4 });
  const w = eL.distanceTo(eR), r = w * .25;
  for (const e of [eL, eR]) { const rim = new THREE.Mesh(new THREE.TorusGeometry(r, r * .09, 8, 28), m); rim.scale.set(1.15, .85, 1); rim.position.copy(e); g.add(rim);
    const lens = new THREE.Mesh(new THREE.CircleGeometry(r, 24), new THREE.MeshPhysicalMaterial({ color: 0xd8ecff, transparent: true, opacity: .05, roughness: .05, depthWrite: false })); lens.scale.set(1.15, .85, 1); lens.position.copy(e); g.add(lens); }
  const mid = eL.clone().add(eR).multiplyScalar(.5); const br = new THREE.Mesh(new THREE.BoxGeometry(w - r * 2.2, r * .14, r * .14), m); br.position.copy(mid); br.position.y += r * .25; g.add(br);
  for (const [e, sg] of [[eL, 1], [eR, -1]]) { const t = new THREE.Mesh(new THREE.BoxGeometry(r * .12, r * .12, w * 1.5), m); t.position.set(e.x + sg * r * 1.12, e.y + r * .2, e.z - w * .72); g.add(t); }
  return g;
}
function addLook(holder, r, bones, o) {
  if (!o.longHair && !o.glasses) return;
  holder.updateMatrixWorld(true); let eyes = null; r.traverse(m => { if (m.isSkinnedMesh) { m.skeleton.update(); if (/eye/i.test(m.material.name)) eyes = m; } });
  const head = bones.Head; const hp = head.getWorldPosition(new THREE.Vector3());
  let eb = eyes ? new THREE.Box3().setFromObject(eyes, true) : null; const ec = eb ? eb.getCenter(new THREE.Vector3()) : hp.clone().add(new THREE.Vector3(0, .1, .08));
  const R = (o.height || 1.74) * .058; // raio da cabeça
  const C = new THREE.Vector3(ec.x, ec.y + R * .42, ec.z - R * .92);
  if (o.longHair) { const h = buildHair(o.longHair, o.hair, C, R); head.attach(h); }
  if (o.glasses && eb) { const w = eb.max.x - eb.min.x; const z = eb.max.z + R * .12; const gl = buildGlasses(new THREE.Vector3(ec.x + w * .3, ec.y, z), new THREE.Vector3(ec.x - w * .3, ec.y, z)); head.attach(gl); }
}
// camadas de tecido: uma "casca" que cobre o corpo como roupa de verdade (preenche as reentrâncias,
// então paletó e calça caem retos em vez de marcar o corpo), presa ao mesmo esqueleto
const SHELL = {};
function shellGeo(g, kind, o) {
  const jacket = kind === 'top' && o.inner !== undefined, long = o.long !== false, hem = o.hem ?? -9;
  const key = g.uuid + kind + (long ? 'L' : 'S') + (jacket ? 'J' : '') + hem;
  if (SHELL[key] !== undefined) return SHELL[key];
  const pa = g.attributes.position, n = pa.count, P = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { P[i * 3] = pa.getX(i); P[i * 3 + 1] = pa.getY(i); P[i * 3 + 2] = pa.getZ(i); }
  const src = new THREE.BufferGeometry(); src.setAttribute('position', new THREE.BufferAttribute(P, 3));
  for (const a of ['skinIndex', 'skinWeight', 'cloth']) src.setAttribute(a, g.attributes[a].clone());
  src.setIndex(g.index ? g.index.clone() : null);
  const m = mergeVertices(src, 1e-4); const ix = m.index.array, Q = m.attributes.position, C = m.attributes.cloth;
  const mask = i => { const x = C.getX(i), y = C.getY(i), z = C.getZ(i), py = Q.getY(i);
    if (kind === 'top') return (x + (long ? y : 0)) + (jacket && z > .3 && py > -.24 ? 1 : 0);
    return py > hem - .12 ? z : 0; };
  const keep = []; for (let t = 0; t < ix.length; t += 3) { const s = mask(ix[t]) + mask(ix[t + 1]) + mask(ix[t + 2]); if (s > 1.5) keep.push(ix[t], ix[t + 1], ix[t + 2]); }
  if (!keep.length) return SHELL[key] = null;
  const map = new Map(), order = []; const idx = keep.map(v => { if (!map.has(v)) { map.set(v, order.length); order.push(v); } return map.get(v); });
  const out = new THREE.BufferGeometry(), N = order.length;
  for (const [nm, a] of Object.entries(m.attributes)) { const sz = a.itemSize, arr = new a.array.constructor(N * sz); order.forEach((v, j) => { for (let k = 0; k < sz; k++) arr[j * sz + k] = a.array[v * sz + k]; }); out.setAttribute(nm, new THREE.BufferAttribute(arr, sz, a.normalized)); }
  out.setIndex(idx); out.computeVertexNormals();
  const p0 = out.attributes.position.array.slice(), nr = out.attributes.normal.array, nb = Array.from({ length: N }, () => new Set());
  for (let t = 0; t < idx.length; t += 3) for (let k = 0; k < 3; k++) { nb[idx[t + k]].add(idx[t + (k + 1) % 3]); nb[idx[t + k]].add(idx[t + (k + 2) % 3]); }
  const NB = nb.map(s => [...s]); let h = new Float32Array(N);
  const pos = j => [p0[j * 3] + nr[j * 3] * h[j], p0[j * 3 + 1] + nr[j * 3 + 1] * h[j], p0[j * 3 + 2] + nr[j * 3 + 2] * h[j]];
  // relaxa a casca como uma membrana apoiada no corpo: só preenche o que é côncavo
  for (let it = 0; it < 60; it++) { const nh = new Float32Array(N);
    for (let j = 0; j < N; j++) { const L = NB[j]; if (!L.length) continue; let ax = 0, ay = 0, az = 0; for (const q of L) { const v = pos(q); ax += v[0]; ay += v[1]; az += v[2]; }
      ax = ax / L.length - p0[j * 3]; ay = ay / L.length - p0[j * 3 + 1]; az = az / L.length - p0[j * 3 + 2];
      nh[j] = Math.min(.05, Math.max(0, ax * nr[j * 3] + ay * nr[j * 3 + 1] + az * nr[j * 3 + 2])); }
    h = nh; }
  const off = kind === 'top' ? (jacket ? .016 : .009) : .008, pp = out.attributes.position.array;
  const bp = new Float32Array(p0);
  for (let j = 0; j < N; j++) { const y = p0[j * 3 + 1]; const flare = jacket && y < .12 ? (.12 - y) * .06 : 0; for (let k = 0; k < 3; k++) pp[j * 3 + k] = p0[j * 3 + k] + nr[j * 3 + k] * (h[j] + off + flare);
    // calça social: frente lisa entre as pernas
    if (kind === 'pants' && y > -.22 && y < .08 && pp[j * 3 + 2] > 0 && Math.abs(pp[j * 3]) < .1) pp[j * 3 + 2] = Math.min(pp[j * 3 + 2], .062 + Math.abs(pp[j * 3]) * .2); }
  out.setAttribute('bp', new THREE.BufferAttribute(bp, 3)); out.computeVertexNormals();
  return SHELL[key] = out;
}
function shellMat(col, kind, o) {
  const m = new THREE.MeshStandardMaterial({ color: col, roughness: .8, metalness: 0, envMapIntensity: .3, side: THREE.DoubleSide });
  const jacket = kind === 'top' && o.inner !== undefined;
  const U = { uVBot: { value: o.vbot ?? .42 }, uJ: { value: jacket ? 1 : 0 }, uBeltS: { value: kind === 'pants' && o.belt !== false && o.hem === undefined && !jacket ? 1 : 0 }, uK: { value: kind === 'top' ? 1 : 0 }, uHemS: { value: kind === 'pants' ? (o.hem ?? -9) : jacket ? -.16 : -9 } };
  m.onBeforeCompile = sh => { Object.assign(sh.uniforms, U);
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nattribute vec3 bp; attribute vec4 cloth; varying vec3 vB; varying vec4 vC;').replace('#include <begin_vertex>', '#include <begin_vertex>\nvB = bp; vC = cloth;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vB; varying vec4 vC; uniform float uVBot, uJ, uBeltS, uK, uHemS;')
      .replace('#include <map_fragment>', `#include <map_fragment>
        if (vB.y < uHemS) discard;
        if (uJ > .5 && vB.z > .0) {
          float cut = uVBot - .17 - vB.y; if (cut > 0. && abs(vB.x) < cut * .2) discard;
          float k = clamp((vB.y - uVBot) / (.67 - uVBot), 0., 1.), hw = .006 + k * .07;
          if (vB.y > uVBot && abs(vB.x) < hw) discard;
          // lapela: faixa ao lado do V um pouco mais clara, com costura escura na borda
          float d = abs(vB.x) - hw; float lap = step(uVBot + .02, vB.y) * (1. - smoothstep(.03, .036, d));
          diffuseColor.rgb *= 1. + lap * .12; diffuseColor.rgb *= 1. - (1. - smoothstep(.0, .004, d)) * step(uVBot, vB.y) * .45;
          // fecho do paletó e botões
          diffuseColor.rgb *= 1. - (1. - smoothstep(.0015, .003, abs(vB.x))) * step(vB.y, uVBot) * step(-.07, vB.y) * .5;
          float bt = 1. - smoothstep(.006, .009, length(vec2(vB.x - .006, vB.y - uVBot + .05)));
          bt = max(bt, 1. - smoothstep(.006, .009, length(vec2(vB.x - .006, vB.y - uVBot + .14))));
          diffuseColor.rgb = mix(diffuseColor.rgb, vec3(.04), bt * .85);
        }
        if (uK > .5 && uJ < .5) { float colr = smoothstep(.66, .7, vB.y); diffuseColor.rgb *= 1. + colr * .08; }
        if (uBeltS > .5) { float shr = vC.x + vC.y, par = vC.z; float belt = smoothstep(.26, .1, abs(shr - par)) * step(.5, shr + par); diffuseColor.rgb = mix(diffuseColor.rgb, vec3(.03, .025, .02), belt * .9); }`);
  };
  m.customProgramCacheKey = () => 'tc-shell'; return m;
}
function addShells(body, o) {
  const parts = [['top', o.shirt], ['pants', o.hem !== undefined ? o.shirt : (o.pants || 0x2a2f45)]];
  for (const [kind, col] of parts) { const g = shellGeo(body.geometry, kind, o); if (!g) continue;
    const s = new THREE.SkinnedMesh(g, shellMat(col, kind, o)); s.name = 'shell_' + kind; s.position.copy(body.position); s.quaternion.copy(body.quaternion); s.scale.copy(body.scale);
    body.parent.add(s); s.bind(body.skeleton, body.bindMatrix); s.castShadow = s.receiveShadow = true; s.frustumCulled = false; }
}
function makePerson(src, o) {
  const r = SkeletonUtils.clone(src.scene); let skel = null; const bodies = [];
  r.traverse(m => { if (!m.isMesh) return; m.castShadow = true; m.receiveShadow = true; m.frustumCulled = false;
    if (m.isSkinnedMesh && /Regular/i.test(m.material.name)) { skel = m.skeleton; clothAttr(m); m.material = bodyMaterial(m.material, o); bodies.push(m); }
    else if (/Hair/i.test(m.material.name)) { m.material = m.material.clone(); m.material.color = new THREE.Color(o.brow || o.hair); } });
  bodies.forEach(b => addShells(b, o));
  if (!skel) r.traverse(m => { if (m.isSkinnedMesh && !skel) skel = m.skeleton; });
  (o.hairs || []).forEach(hn => HAIR[hn] && attachHair(r, skel, HAIR[hn], o.hair));
  const holder = new THREE.Group(); holder.add(r); scene.add(holder); blob(0, 0, .85, .85, 0, holder);
  const mixer = new THREE.AnimationMixer(r); mixers.push(mixer);
  const acts = {}; for (const [k, n] of Object.entries(AN)) if (ANIMS[n]) acts[k] = mixer.clipAction(ANIMS[n]);
  // altura: medida pela cabeça na pose de pé
  const bones = {}; r.traverse(b => { if (b.isBone) bones[b.name] = b; });
  acts.Idle.play(); mixer.update(0); holder.updateMatrixWorld(true);
  const hy = bones.Head.getWorldPosition(new THREE.Vector3()).y; r.scale.multiplyScalar((o.height || 1.74) * .9 / hy); addLook(holder, r, bones, o); acts.Idle.stop();
  holder.userData = { mixer, acts, cur: null, curName: '', bones, model: r, yaw: 0, ...o };
  return holder;
}
function play(p, name, fade = .35, { once = false, hold = false, timeScale = 1, offset = 0 } = {}) {
  const u = p.userData; const a = u.acts[name]; if (!a) return; if (u.curName === name) { a.timeScale = timeScale; return; }
  a.reset(); a.enabled = true; a.setEffectiveWeight(1); a.timeScale = timeScale; a.setLoop(once || hold ? THREE.LoopOnce : THREE.LoopRepeat, once || hold ? 1 : Infinity); a.clampWhenFinished = once || hold;
  if (offset) a.time = offset % a.getClip().duration;
  if (u.cur) u.cur.crossFadeTo(a, fade, false); a.play(); u.cur = a; u.curName = name;
}
// pose sentada: laço sentado (respira, mexe as mãos), começando em ponto diferente para cada um
function sitPose(p, fade = 0) { play(p, p.userData.talky && !p.userData.kb ? 'SitTalk' : 'Sitting', fade, { offset: (p.userData.seed || 0) * .73 }); if (!fade) p.userData.mixer.update(0); }
// encaixa o quadril no assento da cadeira (centro do assento em x,z; altura seatY)
let SIT_HIP = null; // posição do quadril sentado relativa aos pés (medida 1x)
function seat(p, x, z, faceYaw, seatY = .5) {
  p.position.set(0, 0, 0); p.rotation.y = 0; p.userData.yaw = faceYaw; sitPose(p); p.updateMatrixWorld(true);
  const hp = p.userData.bones.pelvis.getWorldPosition(new THREE.Vector3());
  // o quadril fica um pouco à frente do centro do assento (as coxas apoiam no banco)
  const off = new THREE.Vector3(hp.x, 0, hp.z - .06).applyAxisAngle(new THREE.Vector3(0, 1, 0), faceYaw);
  p.rotation.y = faceYaw; p.position.set(x - off.x, seatY + .1 - hp.y, z - off.z);
  p.userData.seatPos = p.position.clone(); p.userData.home = { x, z, yaw: faceYaw };
}
let STUDENT_DESK_Y = .75;
// mãos no teclado: IK de dois ossos (CCD) por cima da pose sentada
function typeAt(p, x, y, z) { p.userData.kb = new THREE.Vector3(x, y, z); }
const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _c = new THREE.Vector3(), _q = new THREE.Quaternion(), _pq = new THREE.Quaternion();
function ikArm(B, side, target, w) {
  const up = B['upperarm_' + side], lo = B['lowerarm_' + side], hand = B['hand_' + side]; if (!up || !lo || !hand) return;
  for (let it = 0; it < 6; it++) for (const b of [lo, up]) {
    b.getWorldPosition(_a); hand.getWorldPosition(_b); _b.sub(_a).normalize(); _c.copy(target).sub(_a).normalize();
    _q.setFromUnitVectors(_b, _c); if (w < 1) _q.slerp(new THREE.Quaternion(), 1 - w);
    b.parent.getWorldQuaternion(_pq); const inv = _pq.clone().invert(); b.quaternion.premultiply(inv.multiply(_q).multiply(_pq)); b.updateMatrixWorld(true); }
  // mão paralela ao teclado (palma para baixo)
  hand.rotation.x *= .4; hand.updateMatrixWorld(true);
}
function typing(p, t, i) { const u = p.userData; if (!u.kb) return; const k = u.typeW = Math.min(1, (u.typeW || 0) + .05); u.model.updateMatrixWorld(true);
  const right = new THREE.Vector3(Math.cos(u.yaw), 0, -Math.sin(u.yaw));
  for (const [side, sg] of [['l', 1], ['r', -1]]) { const tg = u.kb.clone().addScaledVector(right, sg * .17); tg.y += .035 + Math.max(0, Math.sin(t * 11 + i * 1.7 + sg * 1.3)) * .018; ikArm(u.bones, side, tg, k); } }
let WALK_SPEED = 1.25, CARRY_SPEED = 1.1; // calculado a partir da passada do clipe
function measureWalkSpeed(p, name = 'Walk') {
  const u = p.userData; const a = u.acts[name]; if (!a) return WALK_SPEED; const mixer = u.mixer; a.reset().play(); const dur = a.getClip().duration;
  const foot = u.bones.foot_l; let mn = 1e9, mx = -1e9; const v = new THREE.Vector3(); p.position.set(0, 0, 0); p.rotation.y = 0;
  for (let i = 0; i <= 40; i++) { mixer.setTime(dur * i / 40); p.updateMatrixWorld(true); foot.getWorldPosition(v); mn = Math.min(mn, v.z); mx = Math.max(mx, v.z); }
  a.stop(); mixer.setTime(0); return Math.max(.5, Math.min(1.8, 2 * (mx - mn) / dur));
}
/* gata Bolota (procedural) */
const cat = new THREE.Group();
(function buildCat() {
  const fur = mat(0xe3a868, { roughness: .8 }), dark = mat(0xb9773d, { roughness: .8 });
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(.11, .26, 6, 14), fur); body.rotation.z = Math.PI / 2; body.position.y = .2; cat.add(body);
  const head = new THREE.Group(); head.position.set(.23, .3, 0); cat.add(head); cat.userData.head = head;
  head.add(new THREE.Mesh(new THREE.SphereGeometry(.1, 18, 14), fur));
  for (const sz of [-.05, .05]) { const e = new THREE.Mesh(new THREE.ConeGeometry(.04, .08, 4), fur); e.position.set(0, .09, sz); head.add(e); const eye = new THREE.Mesh(new THREE.SphereGeometry(.015, 8, 8), mat(0x1b1b2a)); eye.position.set(.085, .02, sz * .7); head.add(eye); }
  const tail = new THREE.Mesh(new THREE.CapsuleGeometry(.025, .24, 4, 8), dark); tail.position.set(-.27, .3, 0); tail.rotation.z = -.7; cat.add(tail); cat.userData.tail = tail;
  cat.userData.legs = []; for (const [lx, lz] of [[.13, .06], [.13, -.06], [-.13, .06], [-.13, -.06]]) { const l = new THREE.Mesh(new THREE.CapsuleGeometry(.025, .1, 4, 8), fur); l.position.set(lx, .08, lz); cat.add(l); cat.userData.legs.push(l); }
  cat.traverse(o => { if (o.isMesh) o.castShadow = true; }); scene.add(cat);
})();

/* ================= caminhos ================= */
const coin = new THREE.Mesh(new THREE.CylinderGeometry(.05, .05, .012, 24), new THREE.MeshBasicMaterial({ color: 0xffc845, toneMapped: false })); coin.rotation.x = Math.PI / 2; coin.visible = false; scene.add(coin);
const coinGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: 0xffb547, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending })); coinGlow.scale.set(.3, .3, 1); coin.add(coinGlow);
// curva suave por pontos (sem quinas): Catmull-Rom centrípeta
function curve(pts, closed = false) { const c = new THREE.CatmullRomCurve3(pts.map(([x, z]) => new THREE.Vector3(x, 0, z)), closed, 'centripetal', .5); c.arcLengthDivisions = 400; return c; }
// rota da ordem: Nico levanta → Rui → Rocha → Vera → corretora → volta
const ORDER_LEGS = [
  { pts: [[-8, .8], [-8.2, -.6], [-7.6, -2.4]], stop: 'rui', face: [-8, -4.2] },
  { pts: [[-7.6, -2.4], [-6.2, -.4], [-4.5, .55]], stop: 'rocha', face: [-4.5, 1.4] },
  { pts: [[-4.5, .55], [-2.7, .3], [-1, .55]], stop: 'vera', face: [-1, 1.4] },
  { pts: [[-1, .55], [2.5, -.6], [6.2, -1.6], [8.7, -2.2]], stop: 'cofre', face: [10.6, -2.2] },
  { pts: [[8.7, -2.2], [5.5, -.4], [0, .1], [-6, .1], [-8, .8]], stop: 'home', face: null },
].map(l => ({ ...l, c: curve(l.pts) , L: 0 })); ORDER_LEGS.forEach(l => l.L = l.c.getLength());
const CAT_C = curve([[-9.6, .3], [-3, .15], [3.6, .3], [3.6, 2.9], [-3, 3.0], [-9.6, 2.9]], true);

/* ================= pós ================= */
const rt = new THREE.WebGLRenderTarget(1, 1, { samples: HQ ? 4 : 2, type: THREE.HalfFloatType });
const composer = new EffectComposer(renderer, rt);
composer.addPass(new RenderPass(scene, camera));
// sombra de contato (oclusão de ambiente): cantos, pés de móveis e pessoas ganham peso
const gtao = new GTAOPass(scene, camera, 1, 1); gtao.output = GTAOPass.OUTPUT.Default; gtao.blendIntensity = 1.25;
gtao.updateGtaoMaterial({ radius: .45, distanceExponent: 1.5, thickness: .8, distanceFallOff: .8, scale: 1.1, samples: HQ ? 16 : 8 }); gtao.updatePdMaterial({ lumaPhi: 10, depthPhi: 2, normalPhi: 3, radius: 6, rings: 2, samples: HQ ? 16 : 8 });
// vidros, brilhos e partículas não entram no cálculo de oclusão (senão viram manchas escuras)
{ const orig = gtao.render.bind(gtao); const hid = []; gtao.render = (...args) => { hid.length = 0; scene.traverse(o => { if ((o.isMesh || o.isPoints || o.isSprite) && o.visible && (o.userData.noAO || (o.material && [].concat(o.material).some(m => m.transparent)))) { o.visible = false; hid.push(o); } }); orig(...args); hid.forEach(o => o.visible = true); }; }
// a oclusão em tela foi desligada: gerava manchas em alguns ângulos; no lugar dela, sombras de contato fixas
gtao.enabled = false;
const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), .35, .45, .9); composer.addPass(bloom);
const hTilt = new ShaderPass(HorizontalTiltShiftShader), vTilt = new ShaderPass(VerticalTiltShiftShader);
hTilt.uniforms.r.value = vTilt.uniforms.r.value = .5; // desfoque de borda removido: imagem nítida de ponta a ponta
const vig = new ShaderPass(VignetteShader); vig.uniforms.offset.value = 1.0; vig.uniforms.darkness.value = .6; // vinheta removida
composer.addPass(new OutputPass());
let tiltAmt = 1.1;
function resize() { const w = app.clientWidth, h = app.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.fov = w < h ? 42 : 30; camera.updateProjectionMatrix(); composer.setSize(w, h); // a oclusão copia a projeção no setSize: câmera primeiro
  hTilt.uniforms.h.value = tiltAmt / (w * renderer.getPixelRatio()); vTilt.uniforms.v.value = tiltAmt / (h * renderer.getPixelRatio()); bloom.resolution.set(w / 2, h / 2); }
addEventListener('resize', resize);

/* ================= câmera ================= */
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.dampingFactor = .07; controls.minDistance = 3; controls.maxDistance = 150;
controls.minPolarAngle = .35; controls.maxPolarAngle = 1.25; controls.target.set(0, .6, 0); controls.screenSpacePanning = false;
camera.position.set(17, 17, 19);
const SHOTS = {
  geral: { p: [17, 16, 19], t: [0, .3, 0] },
  torre: { p: [62, 18, 84], t: [0, -22, 0] },
  rua: { p: [16, -46, 62], t: [16, -63, 8] },
  mesa: { p: [-1.2, 3.3, -.9], t: [-5.2, 1.1, -6.2] },
  rui: { p: [-6.9, 2.0, -7.4], t: [-8, 1.05, -4.3] }, teo: { p: [-3.4, 2.0, -7.4], t: [-4.5, 1.05, -4.3] }, lena: { p: [.1, 2.0, -7.4], t: [-1, 1.05, -4.3] },
  ordem: { p: [4, 8, 9], t: [-3, .6, -1] },
  escola: { p: [12.5, 4.6, 11], t: [7.4, .9, 4.6] },
  copa: { p: [4.0, 3.6, -1.4], t: [8.0, 1, -7.6] },
  lounge: { p: [-3.6, 3.5, 2.6], t: [-7.9, .7, 7.6] },
  reuniao: { p: [3.8, 4.2, 11.6], t: [-.5, .8, 6.6] },
};
let fly = null;
function shotPos(s) { const t = new THREE.Vector3(...s.t), p = new THREE.Vector3(...s.p); if (camera.aspect < 1) p.sub(t).multiplyScalar(1 + (1 - camera.aspect) * .45).add(t); return p; }
function flyTo(name, dur = 1.8) { const s = SHOTS[name]; if (!s) return; fly = { from: camera.position.clone(), fromT: controls.target.clone(), to: shotPos(s), toT: new THREE.Vector3(...s.t), t0: performance.now() / 1000, dur }; }
function updateFly(now) { if (!fly) return; const k = easeIO(Math.min(1, (now - fly.t0) / fly.dur)); camera.position.lerpVectors(fly.from, fly.to, k); camera.position.y += Math.sin(k * Math.PI) * 1.0; controls.target.lerpVectors(fly.fromT, fly.toT, k); if (k >= 1) fly = null; }
controls.addEventListener('start', () => { fly = null; idleT = 0; });

/* ================= interface ================= */
let STATE = null;
// ---- telão da sala de operações: mercados, placar, notícias do dia e frase motivacional ----
var NEWS = [], HIST = {};
const FRASES = ['Proteja o capital primeiro. O lucro vem depois.', 'Siga o plano. Disciplina vence emoção.', 'Um stop pequeno é um bom negócio.', 'Paciência também é posição.',
  'Consistência vale mais que um grande acerto.', 'Não persiga o preço: espere o seu setup.', 'Perder faz parte. Quebrar não.', 'O mercado paga quem sabe esperar.'];
const hhmm = d => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: 'America/Sao_Paulo' });
function noticia(txt, quando = new Date()) { NEWS.unshift({ h: hhmm(quando), txt }); NEWS.length = Math.min(NEWS.length, 12); }
function noticiasIniciais() { const tr = STATE.traders.filter(t => t.situacao !== 'na escola');
  noticia(`Mesa abre com ${tr.length} traders: ${tr.map(t => t.nome.split(' ')[0]).join(', ')}`);
  noticia(`Meta do dia: ${STATE.regras.meta_vitorias} vitórias · trava em ${STATE.regras.trava_derrotas} derrotas`);
  const est = STATE.traders.filter(t => t.situacao === 'na escola').length + STATE.escola.length; if (est) noticia(`Escola: ${est} estratégias estudando para a prova`);
  noticia(STATE.aoVivo ? 'Placar ligado na mesa simulada ao vivo' : 'Mesa em modo de demonstração'); }
function serie(k, preco, t) { const h = HIST[k] || (HIST[k] = { v: [], sim: preco == null, base: preco || 100 + (k.charCodeAt(0) % 7) * 13 });
  if (preco != null) { h.sim = false; if (!h.v.length || h.v[h.v.length - 1] !== preco) h.v.push(preco); }
  else if (!h.v.length || Math.floor(t) !== h.lt) { h.lt = Math.floor(t); const last = h.v.length ? h.v[h.v.length - 1] : h.base; h.v.push(last * (1 + Math.sin(t * .7 + k.length) * .0015 + (rnd() - .5) * .003)); }
  if (h.v.length > 60) h.v.shift(); return h; }
function drawWall(t) {
  const { g, c } = wallTex.userData; const W = c.width, H = c.height, k = W / 2048; g.save(); g.scale(k, k); const w = 2048, h = H / k;
  g.fillStyle = '#050816'; g.fillRect(0, 0, w, h);
  const bg = g.createLinearGradient(0, 0, w, 0); bg.addColorStop(0, '#0a1a3a'); bg.addColorStop(1, '#101030'); g.fillStyle = bg; g.fillRect(0, 0, w, 64);
  g.textAlign = 'left'; g.fillStyle = '#3dff9a'; g.font = '800 36px Inter, sans-serif'; g.fillText('SALA DE OPERAÇÕES', 28, 45);
  g.fillStyle = 'rgba(255,255,255,.55)'; g.font = '600 24px Inter, sans-serif'; g.fillText(STATE.aoVivo ? `hoje ${fmtR(STATE.hoje)}` : `dia ${STATE.dia} de ${STATE.dias_total}`, 420, 43);
  g.textAlign = 'right'; g.fillStyle = '#fff'; g.font = '700 30px "JetBrains Mono", monospace'; g.fillText(hhmm(new Date()), w - 190, 45);
  const blink = Math.sin(t * 4) > 0; g.fillStyle = blink ? '#ff4d6d' : '#5a1a2a'; g.beginPath(); g.arc(w - 160, 34, 10, 0, 7); g.fill(); g.textAlign = 'left'; g.fillStyle = '#fff'; g.font = '700 24px Inter, sans-serif'; g.fillText('AO VIVO', w - 140, 43);
  const top = 82, bot = h - 74, panel = (x, wd, title, col) => { g.fillStyle = 'rgba(255,255,255,.035)'; g.beginPath(); g.roundRect(x, top, wd, bot - top, 16); g.fill(); g.fillStyle = col; g.font = '800 22px Inter, sans-serif'; g.fillText(title, x + 18, top + 32); };
  // mercados
  panel(20, 690, 'MERCADOS', '#6fd3ff');
  const ativos = [...new Map(STATE.traders.map(tr => [tr.ativo.split(' ')[0], tr])).values()].slice(0, 4);
  ativos.forEach((tr, i) => { const nm = tr.ativo.split(' ')[0], H2 = serie(nm, tr.preco ?? null, t), v = H2.v, x = 34 + (i % 2) * 336, y = top + 50 + Math.floor(i / 2) * 182, cw = 322, ch = 170;
    const ch0 = v[0], ch1 = v[v.length - 1], pct = (ch1 / ch0 - 1) * 100, up = pct >= 0, col = up ? '#3dff9a' : '#ff5d7a';
    g.fillStyle = 'rgba(255,255,255,.04)'; g.beginPath(); g.roundRect(x, y, cw, ch, 12); g.fill();
    g.fillStyle = '#fff'; g.font = '700 26px Inter, sans-serif'; g.fillText(nm, x + 14, y + 34); g.fillStyle = col; g.font = '700 22px "JetBrains Mono", monospace'; g.textAlign = 'right'; g.fillText(`${up ? '▲' : '▼'} ${Math.abs(pct).toFixed(2).replace('.', ',')}%`, x + cw - 14, y + 34);
    g.fillStyle = '#cfd4ff'; g.font = '600 22px "JetBrains Mono", monospace'; g.fillText(H2.sim ? 'simulado' : fmtP(ch1), x + cw - 14, y + 62); g.textAlign = 'left';
    const mn = Math.min(...v), mx = Math.max(...v), sx = (cw - 28) / Math.max(1, v.length - 1), yy = q => y + ch - 14 - (mx > mn ? (q - mn) / (mx - mn) : .5) * 80;
    const gr = g.createLinearGradient(0, y + 70, 0, y + ch); gr.addColorStop(0, up ? 'rgba(61,255,154,.35)' : 'rgba(255,93,122,.35)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
    g.beginPath(); v.forEach((q, j) => j ? g.lineTo(x + 14 + j * sx, yy(q)) : g.moveTo(x + 14, yy(q))); g.lineTo(x + 14 + (v.length - 1) * sx, y + ch - 10); g.lineTo(x + 14, y + ch - 10); g.closePath(); g.fillStyle = gr; g.fill();
    g.beginPath(); v.forEach((q, j) => j ? g.lineTo(x + 14 + j * sx, yy(q)) : g.moveTo(x + 14, yy(q))); g.strokeStyle = col; g.lineWidth = 3; g.stroke(); });
  // placar
  panel(726, 640, 'PLACAR DA MESA', '#3dff9a');
  const n = Math.max(1, STATE.traders.length), st = Math.min(56, (bot - top - 56) / n), fs = Math.round(Math.min(26, st * .5));
  STATE.traders.forEach((tr, i) => { const y = top + 52 + st * i; g.fillStyle = i % 2 ? 'rgba(255,255,255,.03)' : 'rgba(255,255,255,.06)'; g.fillRect(740, y, 612, st - 4);
    const yb = y + st * .62; g.fillStyle = tr.cor; g.beginPath(); g.arc(760, yb - fs * .32, Math.min(9, fs * .35), 0, 7); g.fill();
    g.fillStyle = '#fff'; g.font = `700 ${fs}px Inter, sans-serif`; g.fillText(tr.nome, 778, yb);
    g.fillStyle = '#a9b0e0'; g.font = `500 ${Math.round(fs * .85)}px "JetBrains Mono", monospace`; g.fillText(tr.ativo.split(' ')[0], 990, yb);
    g.fillStyle = tr.situacao === 'na escola' ? '#ffe08a' : { perigo: '#ff5d7a', alerta: '#ffb547', confiante: '#3dff9a' }[tr.humor] || '#6fd3ff'; g.fillText(tr.situacao === 'na escola' ? 'escola' : tr.humor, 1110, yb);
    g.fillStyle = '#cfd4ff'; g.fillText(`${tr.vitorias}V ${tr.derrotas}D`, 1240, yb); });
  // notícias
  panel(1382, 646, 'NOTÍCIAS DO DIA', '#ffd25e');
  NEWS.slice(0, 6).forEach((it, i) => { const y = top + 70 + i * 62; g.fillStyle = i === 0 ? 'rgba(255,210,94,.12)' : 'rgba(255,255,255,.03)'; g.beginPath(); g.roundRect(1396, y - 30, 618, 54, 10); g.fill();
    g.fillStyle = '#ffd25e'; g.font = '700 20px "JetBrains Mono", monospace'; g.fillText(it.h, 1410, y + 4);
    g.fillStyle = i === 0 ? '#fff' : '#cfd4ff'; g.font = `${i === 0 ? 700 : 500} 21px Inter, sans-serif`; let tx = it.txt; while (g.measureText(tx).width > 510 && tx.length > 4) tx = tx.slice(0, -2); g.fillText(tx === it.txt ? tx : tx + '…', 1490, y + 4); });
  // frase motivacional (troca a cada 14 s, com fade)
  const fi = Math.floor(t / 14) % FRASES.length, ph = (t % 14) / 14, al = Math.min(1, ph * 8, (1 - ph) * 8);
  const fb = g.createLinearGradient(0, h - 66, w, h); fb.addColorStop(0, '#2a1a05'); fb.addColorStop(.5, '#3a2508'); fb.addColorStop(1, '#2a1a05'); g.fillStyle = fb; g.fillRect(0, h - 66, w, 66);
  g.fillStyle = 'rgba(255,210,94,.6)'; g.font = '800 18px Inter, sans-serif'; g.fillText('FRASE DO DIA', 28, h - 27);
  g.globalAlpha = al; g.textAlign = 'center'; g.fillStyle = '#ffe3a6'; g.font = 'italic 700 34px Inter, sans-serif'; g.fillText(`“${FRASES[fi]}”`, w / 2, h - 22); g.globalAlpha = 1; g.textAlign = 'left';
  g.restore(); wallTex.needsUpdate = true;
}
function drawBoard() { const { g, c } = boardTex.userData; const W = c.width, H = c.height; g.fillStyle = '#1f5f4c'; g.fillRect(0, 0, W, H);
  g.fillStyle = '#f4f1e6'; g.font = '700 46px "Bricolage Grotesque", sans-serif'; g.textAlign = 'center'; g.fillText('PROVA: fator de lucro ≥ 1,3', W / 2, 80); g.font = '600 34px Inter, sans-serif'; g.textAlign = 'left';
  const naMesa = STATE.traders.filter(t => t.situacao !== 'na escola'), estudando = [...STATE.traders.filter(t => t.situacao === 'na escola').map(t => ({ nome: t.nome, ativo: t.ativo.split(' ')[0] })), ...STATE.escola];
  naMesa.forEach((t, i) => { g.fillStyle = '#9dffcf'; g.fillText(STATE.aoVivo ? `✓ ${t.nome}` : `✓ ${t.nome}  ${t.pf_escola.toFixed(2).replace('.', ',')}`, 70, 170 + i * Math.min(56, 320 / Math.max(1, naMesa.length))); });
  estudando.forEach((s, i) => { g.fillStyle = '#ffe08a'; g.fillText(`○ ${s.nome} (${s.ativo})`, 560, 170 + i * 46); });
  g.fillStyle = 'rgba(244,241,230,.7)'; g.font = '500 28px Inter, sans-serif'; g.fillText('aprovados', 70, 130); g.fillText('estudando', 560, 130); boardTex.needsUpdate = true; }
const bubbles = [];
function say(actor, text, dur = 3.2) { const el = document.createElement('div'); el.className = 'bubble'; el.textContent = text; $('#labels').appendChild(el); bubbles.push({ el, actor, until: performance.now() / 1000 + dur, untilT: simT + dur }); }
function showCard(html) { const c = $('#card'); c.innerHTML = html; c.classList.add('on'); }
function hideCard() { $('#card').classList.remove('on'); }
const MOODS = ['perigo', 'alerta', 'normal', 'confiante'];
const FOTOS = new Set(['teo', 'vera', 'rui', 'lena', 'nico', 'bia', 'rocha', 'sol', 'edu', 'dora', 'gui', 'ju', 'paulo', 'mari', 'caio', 'ana', 'leo']);
function avatar(key, cor, nome) { if (FOTOS.has(key)) return `<span class="av" style="background:${cor} url(assets/rostos/${key}.jpg) center 20%/cover;box-shadow:0 0 0 2px ${cor}"></span>`; return `<span class="av" style="background:${cor}">${(nome || '?').split(' ').map(x => x[0]).join('')}</span>`; }
function traderCard(tr) { return `<div class="ch">${avatar(tr.key, tr.cor, tr.nome)}<div><h3>${tr.nome}</h3><i>trader de ${tr.ativo}</i></div>${tr.situacao === 'na escola' ? '<span class="st">na escola</span>' : '<span class="ok">✓ na mesa</span>'}</div>
  <p>${tr.situacao === 'na escola' ? 'Saiu da mesa e voltou a estudar. Só volta quando passar de novo na prova.' : tr.estrategia}${STATE.aoVivo ? '' : `<br>Prova na escola: fator de lucro <b>${tr.pf_escola.toFixed(2).replace('.', ',')}</b>`}</p>
  <div class="mood">${MOODS.map(m => `<span class="${m === tr.humor ? 'on' : ''}">${m}</span>`).join('')}</div>
  <div class="kv"><div><small>hoje</small><b>${tr.vitorias}V · ${tr.derrotas}D</b></div><div><small>capital</small><b>$${tr.capital.toLocaleString('pt-BR')}</b></div><div><small>posição</small><b>${tr.posicao}</b></div></div>`; }
function teamCard(p) { return `<div class="ch">${avatar(p.key, p.cor, p.nome)}<div><h3>${p.nome}</h3><i>${p.papel}</i></div></div><p>${p.fala}</p>`; }
function studentCard(s) { return `<div class="ch">${avatar(s.key, s.cor, s.nome)}<div><h3>${s.nome}</h3><i>aluna(o) de ${s.ativo}</i></div><span class="st">na escola</span></div><p>Ainda não passou na prova. Precisa de fator de lucro 1,3 para ganhar uma mesa.</p>`; }
function tab(name) {
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.t === name)); idleT = 0;
  if (name === 'geral') { flyTo('geral'); hideCard(); }
  if (name === 'mesa') { flyTo('mesa'); showCard(`<h4>MESA SIMULADA NO AR</h4>${STATE.traders.map(t => `<div class="row"><span class="dot" style="background:${t.cor}"></span><b>${t.nome}</b><span class="m">${t.ativo.split(' ')[0]}</span><span class="pill">${t.humor}</span><span class="m">${t.vitorias}/10 V · ${t.derrotas}/5 D</span></div>`).join('')}<p class="foot">Dia ${STATE.dia} de ${STATE.dias_total}. Meta: ${STATE.regras.meta_vitorias} vitórias. Trava: ${STATE.regras.trava_derrotas} derrotas ou queda de ${STATE.regras.trava_queda_pct}%.</p>`); }
  if (name === 'ordem') { flyTo('ordem'); const fresh = !order; showCard(`<h4>CAMINHO DE UMA ORDEM${order && order.txt ? ' · AO VIVO' : ' · EXEMPLO'}</h4><ol class="steps">${['Rui propõe: COMPRA XRP', 'Nico confere a tendência', 'Rocha põe stop e alvo', 'Vera checa placar e trava', 'Corretora simulada executa'].map((s, i) => `<li id="st${i}">${s}</li>`).join('')}</ol>`); if (fresh) startOrder(); else { const n = order.leg + (order.phase === 'talk' ? 1 : 0); markStep(...[[0], [1, 2], [3], [4]].slice(0, n).flat()); } }
  if (name === 'escola') { flyTo('escola'); drawBoard(); showCard(STATE.aoVivo ? `<h4>BOLETIM DA ESCOLA</h4>${STATE.traders.map(t => `<div class="row"><b class="${t.situacao === 'na escola' ? '' : 'g'}">${t.situacao === 'na escola' ? '○' : '✓'} ${t.nome}</b><span class="m">${t.ativo.split(' ')[0]}</span><span class="pill">${t.situacao}</span></div>`).join('')}<p class="foot">Também estudando: ${STATE.escola.map(s => `${s.nome.split(' ')[0]} (${s.ativo})`).join(' · ')}</p>` : `<h4>BOLETIM DA ESCOLA</h4>${STATE.traders.map(t => `<div class="row"><b class="g">✓ ${t.nome}</b><span class="m">${t.ativo.split(' ')[0]}</span><span class="bar"><i style="width:${Math.min(100, t.pf_escola / 2 * 100)}%"></i></span><b>${t.pf_escola.toFixed(2).replace('.', ',')}</b></div>`).join('')}<p class="foot">Estudando: ${STATE.escola.map(s => `${s.nome.split(' ')[0]} (${s.ativo})`).join(' · ')}</p>`); }
  if (name === 'copa' || name === 'lounge' || name === 'reuniao') { flyTo(name); hideCard(); }
  if (name === 'torre' || name === 'rua') { flyTo(name, 3); hideCard(); }
}
window.tab = tab;
window.panico = () => {
  try { const b = window.parent !== window && window.parent.document.getElementById('btn-panico'); if (b) { b.click(); return; } } catch (e) {}
  location.href = '../#panico';
};

/* ================= ordem (Nico anda pela equipe) ================= */
let order = null, idleT = 0, autoTour = true;
function startOrder(txt, tk) { if (!actors.nico) return; if (order) return; { const sp = actors.nico.userData.seatPos, h = actors.nico.userData.home;
    // sai pela lateral da cadeira, entra na sala de operações pela porta e vai até o trader
    const i = Math.max(0, STATE.traders.findIndex(t => t.key === tk)); tk = STATE.traders[i] ? STATE.traders[i].key : 'rui';
    const tp = TRADER_POS[i] || TRADER_POS[0], [sx, sz] = atrasDe(tp), [ex, ez] = SALA.entrada, R1 = TEAM_POS[1];
    const L0 = ORDER_LEGS[0], L1 = ORDER_LEGS[1], LH = ORDER_LEGS[ORDER_LEGS.length - 1];
    L0.c = curve([[h.x, h.z], [h.x + .7, h.z - .35], [h.x + 1.3, .25], [.8, .25], [ex, ez], [ex, sz], [sx, sz]]); L0.L = L0.c.getLength(); L0.face = tp; L0.stop = tk;
    L1.c = curve([[sx, sz], [ex, sz], [ex, ez], [.8, .25], [R1[0], .55]]); L1.L = L1.c.getLength();
    LH.c = curve([[8.7, -2.2], [5.5, -.4], [0, .1], [-6, .1], [h.x + .75, h.z - .4], [h.x + .45, h.z]]); LH.L = LH.c.getLength(); } order = { phase: 'standup', leg: 0, d: 0, until: simT + 1.4, txt: txt || null }; play(actors.nico, 'StandUp', .25, { hold: true }); coin.visible = true; document.querySelectorAll('.steps li').forEach(l => l.classList.remove('done')); }
function markStep(...ks) { ks.forEach(k => document.getElementById('st' + k)?.classList.add('done')); }
function updateOrder(t, dt) {
  const nico = actors.nico; if (!order || !nico) return; const u = nico.userData;
  const spd = (window.__walkMul || 1) * WALK_SPEED;
  if (order.phase === 'standup') { if (t >= order.until) { order.phase = 'walk'; play(nico, 'Walk', .35, { timeScale: spd / WALK_SPEED }); nico.position.y = 0; } else { nico.position.y += (0 - nico.position.y) * Math.min(1, dt * 3); } return; }
  const leg = ORDER_LEGS[order.leg];
  if (order.phase === 'walk') {
    // desacelera no fim do trecho (sem deslizar: a animação acompanha a velocidade)
    const remain = leg.L - order.d; const k = Math.min(1, remain / .6, (order.d + .3) / .6); const v = spd * Math.max(.35, k);
    order.d += v * dt; u.acts.Walk.timeScale = v / WALK_SPEED;
    const f = Math.min(1, order.d / leg.L); const p = leg.c.getPointAt(f), tg = leg.c.getTangentAt(Math.min(.999, f));
    nico.position.set(p.x, 0, p.z); u.yaw = lerpAngle(u.yaw, Math.atan2(tg.x, tg.z), Math.min(1, dt * 6)); nico.rotation.y = u.yaw;
    if (order.d >= leg.L) {
      if (leg.stop === 'home') { order = null; coin.visible = false; u.settle = { from: nico.position.clone(), fromYaw: u.yaw, t0: t, dur: .9 }; play(nico, 'SitDown', .35, { hold: true }); u.sitting = t + 1.15; return; }
      order.phase = 'talk'; order.until = t + (window.__orderWait || 1.6); play(nico, 'Idle', .4);
      const who = leg.stop;
      if (who !== 'rocha' && who !== 'vera' && who !== 'cofre') { markStep(0); if (actors[who]) say(actors[who], order.txt?.rui || 'Quero comprar XRP.', 1.8); }
      if (who === 'rocha') { markStep(1, 2); say(actors.rocha, order.txt?.rocha || 'Stop 1,5 ATR. Alvo 3x.', 1.8); }
      if (who === 'vera') { markStep(3); say(actors.vera, order.txt?.vera || 'Placar ok. Liberado!', 1.8); }
      if (who === 'cofre') { markStep(4); say(nico, 'Executado no simulado!', 2); coin.visible = false; }
    }
  } else if (order.phase === 'talk') {
    if (leg.face) { const a = Math.atan2(leg.face[0] - nico.position.x, leg.face[1] - nico.position.z); u.yaw = lerpAngle(u.yaw, a, Math.min(1, dt * 4)); nico.rotation.y = u.yaw; }
    if (t >= order.until) { order.leg++; order.d = 0; order.phase = 'walk'; play(nico, 'Walk', .35); }
  }
  if (order && coin.visible) { u.bones.hand_r.getWorldPosition(coin.position); coin.position.y += .03; coin.rotation.z = t * 3; }
}

/* ================= montagem ================= */
const raycaster = new THREE.Raycaster(); const ptr = new THREE.Vector2();
const M = 'Regular_Male_FullBody', F = 'Regular_Female_FullBody';
// cada personagem segue uma pessoa da imagem de referência enviada pelo Alexandre (roupa, cabelo, pele, óculos)
const W_ = 0xdfe2e7, SH = 0x1a1410;
const CAST = {
  teo: { file: M, hairs: ['SlickBack', 'Beard'], shirt: 0x2b2e35, pants: 0x2b2e35, inner: W_, tie: 0x1f2d55, shoes: SH, hair: 0x2a1c14, skin: SKIN[1], height: 1.80, seed: 2 },
  vera: { file: F, hairs: [], longHair: 'longo', shirt: 0x1c1d22, pants: 0x1c1d22, inner: W_, vbot: .36, shoes: SH, hair: 0x2a1a12, brow: 0x2a1a12, skin: SKIN[1], height: 1.68, seed: 6 },
  rui: { file: M, hairs: ['SimpleParted', 'Beard'], glasses: true, shirt: 0x1f2e5a, pants: 0x1f2e5a, inner: 0xeef2fa, tie: 0x3d5f9a, shoes: SH, hair: 0x2a1c14, skin: SKIN[1], height: 1.76, seed: 1 },
  lena: { file: F, hairs: [], longHair: 'longo', glasses: true, shirt: 0xd9c7ae, pants: 0x18181b, inner: 0x141416, vbot: .36, shoes: SH, hair: 0xd8b884, brow: 0x9a7a52, skin: SKIN[0], height: 1.66, seed: 3, talky: true },
  nico: { file: M, hairs: ['Buzzed', 'Beard'], shirt: 0x18181b, pants: 0x1c1c20, shoes: 0xf2f2f2, hair: 0x111111, skin: 0x6e4630, height: 1.80, seed: 4 },
  rocha: { file: M, hairs: ['Buzzed', 'Beard'], shirt: 0x24262c, pants: 0x24262c, inner: W_, tie: 0x2b2b30, shoes: SH, hair: 0x1e1612, skin: SKIN[1], height: 1.82, seed: 5 },
  bia: { file: F, hairs: [], longHair: 'cacheado', shirt: 0xf4f2ee, pants: 0xcdb898, shoes: 0x2a1c14, hair: 0x2a1a12, brow: 0x2a1a12, skin: SKIN[2], height: 1.66, seed: 7, talky: true },
  edu: { file: M, hairs: ['SimpleParted'], shirt: 0xa9c4ec, pants: 0x1c1d22, shoes: SH, hair: 0x4a2e1c, skin: SKIN[0], height: 1.78, seed: 8 },
  sol: { file: F, hairs: [], longHair: 'longo', shirt: 0x141417, pants: 0x141417, long: false, hem: -.33, shoes: 0x0e0e10, hair: 0x16110d, brow: 0x16110d, skin: SKIN[1], height: 1.68, seed: 9 },
  dora: { file: F, hairs: [], longHair: 'longo', shirt: 0xf6f5f2, pants: 0x18181b, shoes: SH, hair: 0xe2c993, brow: 0xa08458, skin: SKIN[0], height: 1.66, seed: 10, talky: true },
  ana: { file: F, hairs: [], longHair: 'cacheado', shirt: 0xb3cbee, pants: 0x18181b, shoes: SH, hair: 0x1c120c, brow: 0x1c120c, skin: SKIN[2], height: 1.64, seed: 12 },
  mari: { file: F, hairs: [], longHair: 'longo', shirt: 0x1f2a52, pants: 0x1f2a52, long: false, hem: -.3, shoes: 0x0e0e10, hair: 0x2a1a12, brow: 0x2a1a12, skin: SKIN[1], height: 1.66, seed: 13, talky: true },
  leo: { file: M, hairs: ['SimpleParted', 'Beard'], shirt: 0x1f2a55, pants: 0xc8b48e, inner: 0xdbe6f5, shoes: 0x4a2e1c, hair: 0x2a1c14, skin: SKIN[1], height: 1.80, seed: 14 },
  gui: { file: M, hairs: ['SlickBack', 'Beard'], shirt: 0x2a2c33, pants: 0x2a2c33, inner: W_, tie: 0x1a1a1f, shoes: SH, hair: 0x1e1612, skin: SKIN[1], height: 1.80, seed: 15, talky: true },
  ju: { file: F, hairs: [], longHair: 'medio', glasses: true, shirt: 0x1c1d22, pants: 0x1c1d22, inner: W_, vbot: .36, shoes: SH, hair: 0x3a2418, brow: 0x3a2418, skin: SKIN[1], height: 1.67, seed: 16, talky: true },
  paulo: { file: M, hairs: ['SimpleParted'], shirt: 0x7b7f87, pants: 0x7b7f87, inner: W_, tie: 0x2c4a86, shoes: 0x3a2416, hair: 0x2a1c14, skin: SKIN[1], height: 1.76, seed: 17 },
  davi: { file: M, hairs: ['Balding', 'Moustache'], glasses: true, shirt: 0x2d3340, pants: 0x2d3340, inner: W_, tie: 0x6b1f2a, shoes: SH, hair: 0x8a8a8a, skin: SKIN[0], height: 1.77, seed: 18 },
  ivo: { file: M, hairs: ['Buzzed'], shirt: 0x3b4a6b, pants: 0x1c1d22, shoes: 0xf2f2f2, hair: 0x2a1c14, skin: SKIN[3], height: 1.74, seed: 19 },
  rita: { file: F, hairs: ['Ponytail'], shirt: 0xf1f1ef, pants: 0x18181b, inner: 0xf1f1ef, tie: 0x141416, shoes: SH, hair: 0x2a1a12, brow: 0x2a1a12, skin: SKIN[2], height: 1.64, seed: 21 },
  pedro: { file: M, hairs: ['Buzzed', 'Beard'], shirt: 0x3c6e9a, pants: 0x2a2f45, long: false, shoes: 0xe9e9ee, hair: 0x1a1410, skin: SKIN[2], height: 1.79, seed: 22 },
  bruna: { file: F, hairs: [], longHair: 'cacheado', shirt: 0xe2a33b, pants: 0x1d2a4a, long: false, shoes: 0xe9e9ee, hair: 0x2a1810, brow: 0x2a1810, skin: SKIN[3], height: 1.67, seed: 23 },
  cafe: { file: M, hairs: ['SlickBack'], shirt: 0x1c1d22, pants: 0x1c1d22, inner: W_, tie: 0x141416, shoes: SH, hair: 0x2a1c14, skin: SKIN[1], height: 1.78, seed: 11 },
};

async function main() {
  STATE = await loadState();
  atualizarHud();
  assinar(vivo => { if (!vivo || !STATE) return; aplicarAoVivo(STATE, vivo); atualizarHud(); });
  if (dentroDoApp()) document.body.classList.add('embed');
  const lbar = $('#lbar'); const prog = (k) => { if (lbar) lbar.style.width = (k * 100) + '%'; };
  FURN = await loadFurniture(); prog(.2);
  buildOffice(); noticiasIniciais(); drawWall(0); drawBoard(); news.forEach((n, i) => drawNews(n, i));
  // pessoas: 2 corpos, 8 cabelos e 2 pacotes de movimentos
  const SRC = {}; const list = [M, F, 'UAL1_Standard', 'UAL2_Standard', ...['SimpleParted', 'SlickBack', 'Buzzed', 'Balding', 'Beard', 'Ponytail', 'Moustache', 'Dreads'].map(h => 'Hair_' + h)]; let done = 0;
  await Promise.all(list.map(async f => { SRC[f] = await loadPerson(f); prog(.2 + .8 * (++done / list.length)); }));
  for (const f of ['UAL1_Standard', 'UAL2_Standard']) SRC[f].animations.forEach(a => ANIMS[a.name] = a);
  for (const f of list) if (f.startsWith('Hair_')) HAIR[f.slice(5)] = SRC[f];
  const mk = k => { const c = CAST[k] || { ...CAST.edu, seed: 40 + Object.keys(actors).length }; const p = makePerson(SRC[c.file], c); actors[k] = p; return p; };
  WALK_SPEED = measureWalkSpeed(mk('cafe')); CARRY_SPEED = measureWalkSpeed(actors.cafe, 'Walk_Carry');
  STATE.traders.forEach((tr, i) => { const [x, z] = TRADER_POS[i]; desk(x, z - 1.0, 0, { seed: i + 1, label: tr.ativo.split(' ')[0] }); chairAt(x, z - .28, Math.PI);
    const p = mk(tr.key); seat(p, x, z - .28, Math.PI); typeAt(p, x, .79, z - .7); p.userData.info = { kind: 'trader', d: tr }; clickables.push(p); labels.push(label3d(tr.nome, tr.ativo.split(' ')[0], tr.cor, new THREE.Vector3(x, 1.95, z))); });
  VAGA_POS.forEach(([x, z], i) => { desk(x, z - 1.0, 0, { on: false, seed: 20 + i }); chairAt(x, z + .05, Math.PI); });
  VAGA_POS.forEach(([x, z]) => labels.push(label3d('Vaga', 'para quem passar na escola', '#ffd25e', new THREE.Vector3(x, 1.7, z - 1))));
  STATE.equipe.forEach((m, i) => { const [x, z] = TEAM_POS[i]; desk(x, z + 1.0, Math.PI, { seed: 30 + i, col: '#c9a2ff', label: m.papel.split(' ')[0].toUpperCase() }); chairAt(x, z + .28, 0);
    const p = mk(m.key); seat(p, x, z + .28, 0); typeAt(p, x, .79, z + .7); p.userData.info = { kind: 'team', d: m }; clickables.push(p); labels.push(label3d(m.nome, m.papel, m.cor, new THREE.Vector3(x, 1.95, z))); });
  STATE.escola.forEach((s, i) => { const [x, z] = STUDENT_POS[i]; chairAt(x, z + .1, Math.PI);
    const p = mk(s.key); seat(p, x, z + .1, Math.PI); typeAt(p, x, STUDENT_DESK_Y + .02, z - .3); p.userData.info = { kind: 'student', d: s }; clickables.push(p); labels.push(label3d(s.nome.split(' ')[0], s.ativo, s.cor, new THREE.Vector3(x, 1.8, z))); });
  // gente pelo escritório: bebedouro, impressora, lounge e sala de reunião
  const npc = (k, nome, papel, fala) => { const p = mk(k); p.userData.info = { kind: 'npc', key: k, nome, papel, fala }; clickables.push(p); return p; };
  { const p = npc('ana', 'Ana', 'do financeiro', 'Água geladinha, melhor coisa.'); p.position.set(6.4, 0, -7.7); p.rotation.y = p.userData.yaw = Math.PI; p.userData.cycle = ['Idle', 4, 'Drink', 0, 'Talk', 3]; play(p, 'Idle', 0, { offset: 1 }); }
  { const p = npc('paulo', 'Paulo', 'do suporte', 'A impressora voltou a funcionar!'); p.position.set(5.2, 0, -.85); p.rotation.y = p.userData.yaw = Math.PI; p.userData.cycle = ['Interact', 0, 'Idle', 3, 'Phone', 6]; play(p, 'Idle', 0); }
  { const p = npc('mari', 'Mari', 'do marketing', 'Esse sofá é o melhor lugar da firma.'); seat(p, -7.3, 8.25, Math.PI, .4); sitPose(p); }
  { const p = npc('leo', 'Léo', 'do design', 'Pausa de cinco minutos e já volto.'); seat(p, -8.05, 8.25, Math.PI, .4); sitPose(p); }
  { const p = npc('gui', 'Gui', 'gerente de operações', 'Precisamos revisar o risco da semana.'); seat(p, -.5, 5.6, 0); sitPose(p); }
  { const p = npc('ju', 'Ju', 'compliance', 'Tudo registrado e auditado.'); seat(p, -.5, 7.6, Math.PI); sitPose(p); }
  labels.push(label3d('Escola', 'estratégias em prova', '#8fe6ff', new THREE.Vector3(7.6, 2.9, 1.6)));
  labels.push(label3d('Corretora', 'modo simulado', '#ffd25e', new THREE.Vector3(10.6, 2.9, -2.2)));
  // café servido na mesa: Caio e Rita pegam na copa, entram pela porta da sala e servem cada trader
  const bandeja = () => { const cup = new THREE.Group(); const tray = new THREE.Mesh(new RoundedBoxGeometry(.42, .025, .3, 2, .01), mat(0x6b4a2a)); cup.add(tray); [[-.1, -.06], [.1, -.06], [0, .07]].forEach(([cx, cz]) => { const k = new THREE.Mesh(new THREE.CylinderGeometry(.04, .033, .09, 14), mat(0xffffff)); k.position.set(cx, .055, cz); k.castShadow = true; cup.add(k); }); scene.add(cup); return cup; };
  [['cafe', [8.2, -7.3], 0, 0], ['rita', [9.15, -7.3], 1, 7]].forEach(([k, copa, par, espera]) => { const c = k === 'cafe' ? actors.cafe : mk('rita');
    c.position.set(copa[0], 0, copa[1]); c.rotation.y = c.userData.yaw = Math.PI; play(c, 'Idle', 0); c.userData.cup = bandeja();
    c.userData.garcom = { copa, par, fase: 'pegar', ate: espera + 2.5, alvo: par, c: null, d: 0, L: 1 }; garcons.push(c);
    c.userData.info = k === 'cafe' ? { kind: 'cafe' } : { kind: 'npc', key: 'rita', nome: 'Rita', papel: 'copeira, serve café na mesa', fala: 'Cafezinho saindo!' }; clickables.push(c); });
  // recreação: partida de pingue-pongue
  [['pedro', 'Pedro', 'da TI', -1], ['bruna', 'Bruna', 'do RH', 1]].forEach(([k, nome, papel, lado]) => { const p = npc(k, nome, papel, lado < 0 ? 'Valendo o cafezinho!' : 'Essa foi na quina!');
    p.position.set(ping.x0 + lado * 1.85, 0, ping.z); p.rotation.y = p.userData.yaw = -lado * Math.PI / 2; play(p, 'Interact', 0); p.userData.ping = lado;
    const rq = new THREE.Group(); const cab = new THREE.Mesh(new THREE.CylinderGeometry(.075, .075, .012, 18), mat(lado < 0 ? 0xc0282d : 0x1b1b1f)); cab.rotation.x = Math.PI / 2; cab.position.y = .1; rq.add(cab); const pega = rbox(.03, .1, .02, .008, mat(0x9a6b3a)); rq.add(pega); p.userData.bones.hand_r.add(rq); rq.scale.setScalar(1 / p.userData.model.scale.x); });
  cat.userData.info = { kind: 'cat' }; clickables.push(cat);

  renderer.domElement.addEventListener('pointerup', e => { if (e.pointerType === 'mouse' && e.button !== 0) return; const r = renderer.domElement.getBoundingClientRect(); ptr.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
    raycaster.setFromCamera(ptr, camera); const hit = raycaster.intersectObjects(clickables, true)[0]; if (!hit) return;
    let o = hit.object; while (o && !o.userData.info) o = o.parent; if (!o) return; const inf = o.userData.info; idleT = 0;
    if (inf.kind === 'trader') { showCard(traderCard(inf.d)); say(o, inf.d.fala); }
    if (inf.kind === 'team') { showCard(teamCard(inf.d)); say(o, inf.d.fala); }
    if (inf.kind === 'student') { showCard(studentCard(inf.d)); say(o, 'Na próxima prova eu passo!'); }
    if (inf.kind === 'cafe') { showCard(`<div class="ch">${avatar('caio', '#e8ecff', 'Caio')}<div><h3>Caio</h3><i>garçom da sala de operações</i></div></div><p>Pega o café na copa e serve cada trader na mesa, um por vez.</p>`); say(o, 'Café fresquinho!'); }
    if (inf.kind === 'npc') { showCard(`<div class="ch">${avatar(inf.key, '#cfd4ff', inf.nome)}<div><h3>${inf.nome}</h3><i>${inf.papel}</i></div></div><p>Faz parte da equipe que mantém a Trade City funcionando.</p>`); say(o, inf.fala); }
    if (inf.kind === 'cat') { showCard(`<div class="ch"><span class="av" style="background:#e3a868">B</span><div><h3>Bolota</h3><i>a gata da segurança</i></div></div><p>Faz a ronda do escritório e cochila no sofá do lounge.</p>`); say(o, 'Miau.'); } });
  // reflexo de ambiente discreto em tudo (o ambiente ilumina, mas sem lavar a cena)
  scene.traverse(o => { const ms = o.material ? [].concat(o.material) : []; ms.forEach(m => { if (m.envMapIntensity === 1 && m.name !== 'glass') m.envMapIntensity = .28; }); });
  resize(); document.body.classList.add('ready');
  if (!REC) { { const s = SHOTS.torre; camera.position.copy(shotPos(s)); controls.target.set(...s.t); flyTo('geral', 4.5); } requestAnimationFrame(loop); }
  window.__ready = true;
}

/* ================= laço ================= */
const clock = new THREE.Clock(); let scrIdx = 0; const tmpV = new THREE.Vector3(), tmpV2 = new THREE.Vector3();
const garcons = [];
function rotaGarcom(c, i) { const g = c.userData.garcom, tp = TRADER_POS[i] || TRADER_POS[0], [sx, sz] = atrasDe(tp), [ex, ez] = SALA.entrada;
  const pts = [g.copa, [7.0, -7.2], [6.75, -5.6], [4.3, -2.7], [3.7, -1.05], [ex, ez], [ex, sz], [sx - .05, sz]]; return { ida: curve(pts), volta: curve(pts.slice().reverse()), tp }; }
function atualizarGarcom(c, t, dt) { const g = c.userData.garcom, u = c.userData;
  if (g.fase === 'pegar' && t >= g.ate) { const n = Math.max(1, TRADER_POS.length); g.alvo = (g.alvo + 2) % n; if (n === 1) g.alvo = 0; g.rota = rotaGarcom(c, g.alvo); g.c = g.rota.ida; g.L = g.c.getLength(); g.d = 0; g.fase = 'ida'; play(c, 'Walk_Carry', .3, { timeScale: 1.4 }); }
  else if (g.fase === 'ida' || g.fase === 'volta') { g.d = Math.min(g.L, g.d + CARRY_SPEED * 1.4 * dt); const f = g.d / g.L, q = g.c.getPointAt(f), tg = g.c.getTangentAt(Math.min(.999, f));
    c.position.set(q.x, 0, q.z); u.yaw = lerpAngle(u.yaw, Math.atan2(tg.x, tg.z), Math.min(1, dt * 6)); c.rotation.y = u.yaw;
    if (g.d >= g.L) { if (g.fase === 'ida') { g.fase = 'servir'; g.ate = t + 2.6; g.falou = false; play(c, 'Interact', .3, { once: true }); } else { g.fase = 'pegar'; g.ate = t + 3 + (g.par ? 1.5 : 0); play(c, 'Interact', .3, { once: true }); } } }
  else if (g.fase === 'servir') { const [tx, tz] = g.rota.tp; u.yaw = lerpAngle(u.yaw, Math.atan2(tx - c.position.x, tz - c.position.z), Math.min(1, dt * 5)); c.rotation.y = u.yaw;
    if (!g.falou && t > g.ate - 1.4) { g.falou = true; const tr = STATE.traders[g.alvo]; if (tr && actors[tr.key]) say(actors[tr.key], ['Valeu!', 'Obrigado!', 'Salvou meu dia.', 'Bem forte, por favor.'][Math.floor(t) % 4], 1.6); }
    if (t >= g.ate) { g.fase = 'volta'; g.c = g.rota.volta; g.L = g.c.getLength(); g.d = 0; play(c, 'Walk_Carry', .3, { timeScale: 1.4 }); } }
  if (g.fase === 'pegar') { u.yaw = lerpAngle(u.yaw, Math.PI, Math.min(1, dt * 5)); c.rotation.y = u.yaw; }
  const B = u.bones; B.hand_l.getWorldPosition(tmpV); B.hand_r.getWorldPosition(tmpV2); u.cup.position.copy(tmpV).add(tmpV2).multiplyScalar(.5); u.cup.position.y += .02; u.cup.rotation.y = u.yaw; }
function simulate(t, dt) {
  cidade.atualizar(t, dt);
  mixers.forEach(m => m.update(dt));
  // vida de quem está sentado: cabeça olha devagar, mãos no teclado (ajuste pequeno e suave)
  Object.entries(actors).forEach(([k, p], i) => { const u = p.userData; if (u.sitting && t >= u.sitting) { sitPose(p, .2); u.sitting = 0; }
    if (u.cycle) { if (u.ci === undefined) { u.ci = 0; u.next = t + 2 + (u.seed % 3); }
      if (t >= u.next) { u.ci = (u.ci + 2) % u.cycle.length; const nm = u.cycle[u.ci], d = u.cycle[u.ci + 1]; const once = !d; play(p, nm, .4, { hold: once }); u.next = t + (once ? u.acts[nm].getClip().duration - .3 : d); } }
    if (u.curName !== 'Sitting' && u.curName !== 'SitTalk') { u.typeW = 0; return; } if (u.kb) typing(p, t, i); const head = u.bones.Head;
    if (head) { head.rotation.y += Math.sin(t * .3 + i * 2.1) * .12; head.rotation.x += Math.sin(t * .45 + i) * .04; }
  });
  bulbs.forEach((b, i) => { const k = .45 + .55 * Math.max(0, Math.sin(t * 2.6 + i * 1.3)); b.material.color.copy(b.userData.base).multiplyScalar(.4 + 1.6 * k); });
  const p = snowG.attributes.position.array; for (let i = 0; i < SN; i++) { p[i * 3 + 1] -= dt * snowS[i] * 1.2; p[i * 3] += Math.sin(t + i) * dt * .2; if (p[i * 3 + 1] < -2) p[i * 3 + 1] = 28; } snowG.attributes.position.needsUpdate = true;
  if (screens.length) { for (let k = 0; k < 2; k++) { const s = screens[scrIdx++ % screens.length]; if (!s.userData.off) drawChart(s, t + s.userData.seed); } }
  if (Math.floor(t * 2) !== Math.floor((t - dt) * 2)) { drawWall(t); }
  if (Math.floor(t * 10) !== Math.floor((t - dt) * 10)) news.forEach((n, i) => drawNews(n, t + i * 3));
  if (window.__vault) window.__vault.userData.dial.rotation.x = t * .6;
  // gata
  { const L = CAT_C.getLength(), f = ((t * .42) % L) / L, q = CAT_C.getPointAt(f), tg = CAT_C.getTangentAt(f); cat.position.set(q.x, 0, q.z); cat.rotation.y = Math.atan2(tg.x, tg.z) - Math.PI / 2;
    cat.userData.legs.forEach((l, i) => l.rotation.z = Math.sin(t * 9 + (i % 2) * Math.PI + (i > 1 ? Math.PI / 2 : 0)) * .45); cat.userData.tail.rotation.x = Math.sin(t * 3) * .4; cat.userData.head.rotation.y = Math.sin(t * .8) * .3; }
  garcons.forEach(c => atualizarGarcom(c, t, dt));
  // pingue-pongue: bola vai e volta, cada jogador "rebate" quando ela chega
  if (ping.bola) { const T = 1.7, u = (t % T) / T, ida = u < .5, sq = ida ? u * 2 : (u - .5) * 2, x = ping.x0 + (ida ? -1.5 + 3 * sq : 1.5 - 3 * sq);
    const y = sq < .72 ? .98 + (sq / .72) * (1 - sq / .72) * 1.1 - (sq / .72) * .19 : .79 + ((sq - .72) / .28) * (1 - (sq - .72) / .28) * .5 + ((sq - .72) / .28) * .19;
    ping.bola.position.set(x, y, ping.z + Math.sin(t * 2.3) * .35);
    for (const k of ['pedro', 'bruna']) { const p = actors[k]; if (!p) continue; const a = p.userData.acts.Interact; if (!a) continue; const dur = a.getClip().duration, hit = p.userData.ping < 0 ? 0 : .5; a.time = (((u - hit + 1.12) % 1)) * dur; } }
  if (Math.floor(t * 10) !== Math.floor((t - dt) * 10)) drawArcade(t);
  if (!order && !REC && !STATE.aoVivo && t > 8 && Math.floor(t) % 40 === 0) startOrder();
  { const n = actors.nico; const u = n && n.userData; if (u && u.settle) { const k = easeIO(Math.min(1, (t - u.settle.t0) / u.settle.dur)); n.position.lerpVectors(u.settle.from, u.seatPos, k); u.yaw = lerpAngle(u.settle.fromYaw, u.home.yaw, k); n.rotation.y = u.yaw; if (k >= 1) u.settle = null; } }
  updateOrder(t, dt);
}
function updateLabels() {
  const w = app.clientWidth, h = app.clientHeight; const show = camera.position.distanceTo(controls.target) < 30;
  labels.forEach(l => { tmpV2.copy(l.pos).applyMatrix4(camera.matrixWorldInverse); tmpV.copy(l.pos).project(camera); const vis = tmpV2.z < 0 && tmpV.z < 1 && show; l.el.style.opacity = vis ? 1 : 0; l.el.style.transform = `translate(-50%,-100%) translate(${(tmpV.x * .5 + .5) * w}px,${(-tmpV.y * .5 + .5) * h}px)`; });
  const now = performance.now() / 1000;
  for (let i = bubbles.length - 1; i >= 0; i--) { const b = bubbles[i]; if ((!REC && now > b.until) || (REC && simT > b.untilT)) { b.el.remove(); bubbles.splice(i, 1); continue; }
    tmpV.copy(b.actor.position); tmpV.y += 1.9; tmpV.project(camera); b.el.style.transform = `translate(-50%,-100%) translate(${(tmpV.x * .5 + .5) * w}px,${(-tmpV.y * .5 + .5) * h - 30}px)`; }
}
let perfT = 0, perfN = 0;
function loop() {
  const rawDt = clock.getDelta(); const dt = Math.min(rawDt, .05); simT += dt;
  // celular lento: desliga a oclusão e depois reduz a resolução, para manter a fluidez
  perfT += rawDt; perfN++; if (perfT > 3) { const avg = perfT / perfN; if (avg > .045 && gtao.enabled) gtao.enabled = false; else if (avg > .045 && renderer.getPixelRatio() > 1) { renderer.setPixelRatio(1); resize(); } perfT = 0; perfN = 0; } const now = performance.now() / 1000; idleT += dt;
  if (autoTour && idleT > 25 && !fly) { const keys = STATE && STATE.aoVivo ? ['mesa', 'copa', 'torre', 'escola', 'lounge', 'rua', 'reuniao', 'geral'] : ['mesa', 'copa', 'ordem', 'torre', 'escola', 'lounge', 'rua', 'reuniao', 'geral']; tab(keys[Math.floor(now / 25) % keys.length]); }
  updateFly(now); controls.update(); simulate(simT, dt); updateLabels(); composer.render(); requestAnimationFrame(loop);
}
window.__step = (t, dt, cam) => { simT = t; simulate(t, dt); if (cam) { camera.position.set(...cam.p); controls.target.set(...cam.t); camera.lookAt(controls.target); } updateLabels(); if (!window.__skip) composer.render(); };
window.__api = { gtao, scene, legs: ORDER_LEGS, camera, controls, play, THREE, tab, startOrder, say, actors, SHOTS, flyTo, showCard, hideCard, drawBoard, traderCard, teamCard, studentCard, get STATE() { return STATE; }, get order() { return order; }, set auto(v) { autoTour = v; }, get WALK() { return WALK_SPEED; } };
main().catch(e => { console.error(e); const l = $('#loading'); if (l) l.innerHTML = '<div style="font:600 16px Inter;padding:20px;text-align:center">Não foi possível carregar a cena.<br>' + e.message + '</div>'; });
