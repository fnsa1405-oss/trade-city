// Cidade lá embaixo: o escritório fica no último andar de uma torre.
// Prédios, casas, parques, postes e ruas com gente, carros e motos andando.
// Tudo é mesclado ou instanciado (poucas chamadas de desenho) para rodar leve no celular.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

export const CHAO = -64;          // altura da rua (o escritório fica em y = 0)
const P = 32, BLOCO = 26, RUA = 6; // quadra + rua
let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const pick = a => a[Math.floor(rnd() * a.length)];

function tex(w, h, draw) { const c = document.createElement('canvas'); c.width = w; c.height = h; const g = c.getContext('2d'); draw(g, w, h); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; t.wrapS = t.wrapT = THREE.RepeatWrapping; return t; }

// fachada: 8 andares x 6 janelas por quadro (12 m x 28 m)
function fachadaTex(tipo) {
  return tex(192, 256, (g, w, h) => {
    const fy = h / 8, fx = w / 6;
    g.fillStyle = tipo === 'vidro' ? '#0b1430' : '#151418'; g.fillRect(0, 0, w, h);
    for (let a = 0; a < 8; a++) { const aceso = rnd(); // andares inteiros acesos ou apagados, como escritório à noite
      for (let j = 0; j < 6; j++) { const r = rnd(); const on = aceso > .45 ? r > .25 : r > .82;
        const x = j * fx + (tipo === 'vidro' ? 1 : 5), y = a * fy + (tipo === 'vidro' ? 2 : 6), ww = fx - (tipo === 'vidro' ? 2 : 10), hh = fy - (tipo === 'vidro' ? 6 : 13);
        if (on) { const quente = tipo === 'vidro' ? r > .7 : r > .2; const gr = g.createLinearGradient(0, y, 0, y + hh);
          gr.addColorStop(0, quente ? '#ffd9a0' : '#cfe8ff'); gr.addColorStop(1, quente ? '#c9893e' : '#6ea6d8'); g.fillStyle = gr; }
        else g.fillStyle = tipo === 'vidro' ? '#16244a' : '#1d2230';
        g.fillRect(x, y, ww, hh); }
      g.fillStyle = tipo === 'vidro' ? '#05070f' : '#0c0c10'; g.fillRect(0, a * fy + fy - 3, w, 3); }
  });
}
function lojaTex() {
  return tex(256, 32, (g, w, h) => { g.fillStyle = '#121216'; g.fillRect(0, 0, w, h);
    const cores = ['#ffcf7a', '#ff9a6a', '#9fe0ff', '#fff2d6', '#ff7ab8', '#a7ffb0'];
    for (let x = 0; x < w; x += 32) { g.fillStyle = pick(cores); g.globalAlpha = .9; g.fillRect(x + 3, 9, 26, 21); g.globalAlpha = 1; g.fillStyle = pick(cores); g.fillRect(x + 3, 3, 26, 4); } });
}
function casaTex() {
  return tex(64, 32, (g, w, h) => { g.fillStyle = '#fff'; g.fillRect(0, 0, w, h);
    for (const x of [10, 38]) { const on = rnd() > .3; g.fillStyle = on ? '#ffc46e' : '#2a3040'; g.fillRect(x, 10, 14, 12); g.fillStyle = '#ddd'; g.fillRect(x + 6, 10, 2, 12); } });
}

// paredes de um prisma retangular (4 lados), com UV em metros (quadro de 12 x 28 m)
function lados(w, h, d, x, y, z, uw = 9, uh = 24, cor = null) {
  const pos = [], uv = [], idx = []; const ox = rnd(), oy = Math.floor(rnd() * 8) / 8;
  const faces = [[[-w / 2, d / 2], [w / 2, d / 2], w], [[w / 2, d / 2], [w / 2, -d / 2], d], [[w / 2, -d / 2], [-w / 2, -d / 2], w], [[-w / 2, -d / 2], [-w / 2, d / 2], d]];
  let u0 = ox;
  for (const [[ax, az], [bx, bz], L] of faces) { const n = pos.length / 3;
    pos.push(x + ax, y, z + az, x + bx, y, z + bz, x + bx, y + h, z + bz, x + ax, y + h, z + az);
    uv.push(u0, oy, u0 + L / uw, oy, u0 + L / uw, oy + h / uh, u0, oy + h / uh); u0 += L / uw;
    idx.push(n, n + 1, n + 2, n, n + 2, n + 3); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2)); g.setIndex(idx); g.computeVertexNormals();
  if (cor) pinta(g, cor);
  return g;
}
function pinta(g, cor) { const c = new THREE.Color(cor), n = g.attributes.position.count, a = new Float32Array(n * 3); for (let i = 0; i < n; i++) c.toArray(a, i * 3); g.setAttribute('color', new THREE.BufferAttribute(a, 3)); return g; }
function caixa(w, h, d, x, y, z, cor) { const g = new THREE.BoxGeometry(w, h, d).toNonIndexed(); g.translate(x, y + h / 2, z); g.deleteAttribute('uv'); return pinta(g, cor); }
// telhado de duas águas
function telhado(w, d, hR, x, y, z, cor) {
  const e = .35, W2 = w / 2 + e, D2 = d / 2 + e;
  const v = [[-W2, 0, -D2], [W2, 0, -D2], [W2, 0, D2], [-W2, 0, D2], [-W2, hR, 0], [W2, hR, 0]];
  const t = [[0, 4, 5], [0, 5, 1], [3, 2, 5], [3, 5, 4], [0, 3, 4], [1, 5, 2]];
  const pos = []; t.forEach(tr => tr.forEach(i => pos.push(v[i][0] + x, v[i][1] + y, v[i][2] + z)));
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); g.computeVertexNormals(); return pinta(g, cor);
}

export function criarCidade(scene, { mobile = false, renderer } = {}) {
  seed = 7;
  const R = mobile ? 230 : 300, N = Math.ceil(R / P);
  const grupo = new THREE.Group(); grupo.name = 'cidade'; scene.add(grupo);
  const sem = o => { o.castShadow = false; o.receiveShadow = false; o.userData.noAO = true; o.matrixAutoUpdate = false; o.updateMatrix(); return o; };

  /* ---- chão: ruas, faixas, calçadas ---- */
  const ruaT = tex(512, 512, (g, w) => { const k = w / P; // 16 px por metro
    g.fillStyle = '#25272d'; g.fillRect(0, 0, w, w);
    const b0 = (P - BLOCO) / 2 * k, b1 = (P + BLOCO) / 2 * k;
    g.fillStyle = '#5d5f66'; g.fillRect(b0, b0, b1 - b0, b1 - b0);                 // calçada
    g.fillStyle = '#3d4048'; g.fillRect(b0 + 2.2 * k, b0 + 2.2 * k, b1 - b0 - 4.4 * k, b1 - b0 - 4.4 * k); // miolo da quadra
    g.fillStyle = '#4a4c53'; for (let i = b0; i < b1; i += k * 1.2) { g.fillRect(i, b0, 1, 2.2 * k); g.fillRect(i, b1 - 2.2 * k, 1, 2.2 * k); g.fillRect(b0, i, 2.2 * k, 1); g.fillRect(b1 - 2.2 * k, i, 2.2 * k, 1); }
    g.fillStyle = 'rgba(255,210,90,.55)'; for (let i = b0 + k; i < b1 - k; i += k * 3) { g.fillRect(i, 0, k * 1.6, 2); g.fillRect(i, w - 2, k * 1.6, 2); g.fillRect(0, i, 2, k * 1.6); g.fillRect(w - 2, i, 2, k * 1.6); }
    g.fillStyle = 'rgba(235,235,235,.6)'; // faixa de pedestre
    for (let s = 0; s < 6; s++) { const o = b0 + .6 * k + s * .9 * k; for (const e of [0, b1]) { g.fillRect(o, e === 0 ? 0 : b1, k * .5, b0); g.fillRect(o + (b1 - b0) - 6.2 * k, e === 0 ? 0 : b1, k * .5, b0); g.fillRect(e === 0 ? 0 : b1, o, b0, k * .5); g.fillRect(e === 0 ? 0 : b1, o + (b1 - b0) - 6.2 * k, b0, k * .5); } }
  });
  const S = 2 * N * P + P; ruaT.repeat.set(S / P, S / P); ruaT.offset.set(0, 0); // S é múltiplo ímpar de P: o centro do quadro já cai no centro da quadra
  const chao = new THREE.Mesh(new THREE.PlaneGeometry(S, S), new THREE.MeshStandardMaterial({ map: ruaT, roughness: .85, envMapIntensity: .1 }));
  chao.rotation.x = -Math.PI / 2; chao.position.y = CHAO; grupo.add(sem(chao));

  /* ---- prédios ---- */
  const vidroT = [fachadaTex('vidro'), fachadaTex('vidro')], concT = [fachadaTex('conc'), fachadaTex('conc')];
  const gVidro = [[], []], gConc = [[], []], gLoja = [], gTopo = [], gCasa = [], gTelha = [], gGrama = [];
  const arvores = [], postes = [], luzesAviao = [];
  const quadras = [];
  for (let i = -N; i <= N; i++) for (let j = -N; j <= N; j++) { const cx = i * P, cz = j * P, r = Math.hypot(cx, cz); if (r > R) continue; quadras.push([i, j, cx, cz, r]); }
  const PARQUES = new Set(['1,-1', '-2,1', '3,2', '-1,-3', '4,-3', '-4,-2']);
  for (const [i, j, cx, cz, r] of quadras) {
    if (i === 0 && j === 0) continue; // a nossa torre
    const k = i + ',' + j;
    if (PARQUES.has(k) || (r > 120 && rnd() < .06)) { // parque
      gGrama.push(caixa(BLOCO - 4.4, .12, BLOCO - 4.4, cx, CHAO, cz, 0x2f5a2c));
      for (let n = 0; n < 16; n++) arvores.push([cx + (rnd() - .5) * 19, cz + (rnd() - .5) * 19, .8 + rnd() * .7]);
      continue;
    }
    if (r < 150) { // centro e bairro de prédios: lotes 2x2 ou um prédio grande
      const centro = r < 120;
      const lotes = rnd() < .3 ? [[0, 0, 21]] : [[-5.5, -5.5, 9.6], [5.5, -5.5, 9.6], [-5.5, 5.5, 9.6], [5.5, 5.5, 9.6]];
      for (const [lx, lz, tam] of lotes) {
        let h = r < 75 ? 10 + rnd() * 22 : r < 120 ? 12 + rnd() * 30 : 8 + rnd() * 22; if (r > 140 && rnd() < .1) h = 55 + rnd() * 60;
        const vidro = centro ? rnd() < .55 : rnd() < .2;
        let w = tam * (.75 + rnd() * .25), d = tam * (.75 + rnd() * .25), y = CHAO, x = cx + lx, z = cz + lz;
        gLoja.push(lados(w + .3, 4, d + .3, x, y, z, 8, 4)); // térreo com lojas acesas
        y += 4; h -= 4; const fat = h > 40 ? 3 : h > 22 ? 2 : 1;
        for (let s = 0; s < fat; s++) { const hs = s === fat - 1 ? h : h * (.5 + rnd() * .2); const ti = Math.floor(rnd() * 2);
          (vidro ? gVidro : gConc)[ti].push(lados(w, hs, d, x, y, z)); gTopo.push(caixa(w + .4, .5, d + .4, x, y + hs - .5, z, vidro ? 0x262c3a : 0x34343a)); y += hs; h -= hs; w *= .78; d *= .78; if (h < 3) break; }
        if (rnd() < .5) gTopo.push(caixa(w * .3, 1.6, d * .3, x + w * .15, y, z - d * .1, 0x40424a)); // casa de máquinas
        if (y - CHAO > 55) luzesAviao.push(x, y + .8, z);
      }
      if (centro) for (const [ax, az] of [[-11.5, 0], [11.5, 0], [0, -11.5], [0, 11.5]]) if (rnd() < .5) arvores.push([cx + ax + (rnd() - .5) * 8 * (ax === 0), cz + az + (rnd() - .5) * 8 * (az === 0), .6]);
    } else { // bairro de casas: 3x3 lotes com jardim
      gGrama.push(caixa(BLOCO - 4.4, .1, BLOCO - 4.4, cx, CHAO, cz, 0x2a4a28));
      for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) { if (a === 0 && b === 0) { arvores.push([cx, cz, 1.1]); continue; }
        const x = cx + a * 7.2, z = cz + b * 7.2, w = 4.2 + rnd() * 1.4, d = 4.6 + rnd() * 1.4, h = 2.8 + (rnd() < .35 ? 2.8 : 0);
        const parede = pick([0xe9e1d0, 0xf2efe6, 0xd9c2a0, 0xc98b6b, 0xb7c4c9, 0xe2cfa8]);
        gCasa.push(lados(w, h, d, x, CHAO + .1, z, 4.4, h > 3 ? 5.6 : 2.8, parede));
        const tg = telhado(w, d, 1.3 + rnd() * .6, x, CHAO + .1 + h, z, pick([0x7a3426, 0x5b2a22, 0x3b3f46, 0x8a4a2e]));
        if (rnd() < .5) tg.rotateY(0), tg.translate(0, 0, 0);
        gTelha.push(tg); if (rnd() < .6) arvores.push([x + 2.8, z + 2.8, .7 + rnd() * .4]); }
    }
    // postes nas esquinas
    if (r < R - 20) postes.push([cx + 13.6, cz + 13.6], [cx - 13.6, cz + 13.6]);
  }

  const mat = (tx, cor, vidro) => new THREE.MeshStandardMaterial({ color: cor, map: null, emissive: 0xffffff, emissiveMap: tx, emissiveIntensity: vidro ? 1.05 : .95, roughness: vidro ? .25 : .85, metalness: vidro ? .5 : 0, envMapIntensity: vidro ? .6 : .1 });
  const junta = (arr, m) => { if (!arr.length) return; const me = new THREE.Mesh(mergeGeometries(arr), m); grupo.add(sem(me)); return me; };
  gVidro.forEach((a, i) => junta(a, mat(vidroT[i], 0x1a2742, true)));
  gConc.forEach((a, i) => junta(a, mat(concT[i], 0x2b2a2e, false)));
  const lojaM = new THREE.MeshStandardMaterial({ color: 0x18181c, emissive: 0xffffff, emissiveMap: lojaTex(), emissiveIntensity: 1.1, roughness: .7 }); junta(gLoja, lojaM);
  junta(gTopo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .8 }));
  junta(gGrama, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1 }));
  const casaM = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .9, emissive: 0xffffff, emissiveMap: casaTex(), emissiveIntensity: .0 });
  casaM.onBeforeCompile = sh => { sh.fragmentShader = sh.fragmentShader.replace('#include <emissivemap_fragment>', `vec4 em = texture2D(emissiveMap, vEmissiveMapUv); float jan = step(.5, em.r) * step(em.b, .6); totalEmissiveRadiance = vec3(1., .72, .38) * jan * 1.1; diffuseColor.rgb *= mix(1., .2, step(em.r, .5));`); };
  junta(gCasa, casaM); junta(gTelha, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .8 }));

  /* ---- a nossa torre ---- */
  { const tw = 24.6, td = 18.6, topo = -.63, h = topo - CHAO;
    const t = fachadaTex('vidro'); const m = mat(t, 0x1c2a48, true); m.emissiveIntensity = .8;
    const torre = new THREE.Mesh(lados(tw, h - 6, td, 0, CHAO + 6, 0), m); grupo.add(sem(torre));
    const lobby = new THREE.Mesh(lados(tw - 1, 6, td - 1, 0, CHAO, 0, 8, 6), new THREE.MeshStandardMaterial({ color: 0x111, emissive: 0xffe2b0, emissiveIntensity: .55, roughness: .3 })); grupo.add(sem(lobby));
    // frisos verticais e a faixa de luz embaixo do último andar
    const fr = []; for (let x = -tw / 2; x <= tw / 2 + .01; x += tw / 6) fr.push(caixa(.35, h, .35, x, CHAO, td / 2, 0x0d1220), caixa(.35, h, .35, x, CHAO, -td / 2, 0x0d1220));
    for (let z = -td / 2; z <= td / 2 + .01; z += td / 4) fr.push(caixa(.35, h, .35, tw / 2, CHAO, z, 0x0d1220), caixa(.35, h, .35, -tw / 2, CHAO, z, 0x0d1220));
    junta(fr, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .4, metalness: .6 }));
    const faixa = new THREE.Mesh(new THREE.BoxGeometry(tw + .3, .18, td + .3), new THREE.MeshBasicMaterial({ color: 0x8fd8ff })); faixa.position.y = -1.0; grupo.add(sem(faixa));
    // letreiro na fachada da frente
    const lt = tex(1024, 128, (g, w, h) => { g.clearRect(0, 0, w, h); g.font = '800 92px Inter, Arial, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle'; g.shadowColor = '#ffcf6a'; g.shadowBlur = 18; g.fillStyle = '#ffe3a6'; g.fillText('TRADE CITY', w / 2, h / 2 + 4); });
    lt.wrapS = lt.wrapT = THREE.ClampToEdgeWrapping;
    const placa = new THREE.Mesh(new THREE.PlaneGeometry(14, 1.75), new THREE.MeshBasicMaterial({ map: lt, transparent: true, depthWrite: false, toneMapped: false }));
    placa.position.set(0, -3.4, td / 2 + .25); grupo.add(sem(placa));
    const placa2 = placa.clone(); placa2.rotation.y = Math.PI / 2; placa2.position.set(tw / 2 + .25, -3.4, 0); placa2.scale.setScalar(.9); grupo.add(sem(placa2));
  }

  /* ---- árvores (instanciadas) ---- */
  { const copa = new THREE.IcosahedronGeometry(1.7, 1); copa.translate(0, 3.6, 0); pinta(copa, 0x2e5a2a);
    const pos = copa.attributes.position; for (let i = 0; i < pos.count; i++) { const n = 1 + (Math.sin(i * 12.9898) * 43758.5 % 1) * .12; pos.setXYZ(i, pos.getX(i) * n, pos.getY(i), pos.getZ(i) * n); } copa.computeVertexNormals();
    const tronco = new THREE.CylinderGeometry(.16, .22, 2.4, 6).toNonIndexed(); tronco.translate(0, 1.2, 0); tronco.deleteAttribute('uv'); pinta(tronco, 0x4a3524);
    const cg = copa.toNonIndexed(); cg.deleteAttribute('uv');
    const geo = mergeGeometries([cg, tronco]);
    const im = new THREE.InstancedMesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .9 }), arvores.length);
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), c = new THREE.Color();
    arvores.forEach(([x, z, s], i) => { q.setFromAxisAngle(new THREE.Vector3(0, 1, 0), rnd() * 6); m4.compose(new THREE.Vector3(x, CHAO, z), q, new THREE.Vector3(s, s * (.9 + rnd() * .3), s)); im.setMatrixAt(i, m4); im.setColorAt(i, c.setHSL(.25 + rnd() * .08, .35 + rnd() * .2, .35 + rnd() * .25)); });
    grupo.add(sem(im)); }

  /* ---- postes com poça de luz no chão ---- */
  { const haste = new THREE.CylinderGeometry(.08, .1, 6, 5).toNonIndexed(); haste.translate(0, 3, 0); haste.deleteAttribute('uv'); pinta(haste, 0x2a2c33);
    const im = new THREE.InstancedMesh(haste, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .5 }), postes.length);
    const lamp = new THREE.InstancedMesh(new THREE.SphereGeometry(.28, 8, 6), new THREE.MeshBasicMaterial({ color: 0xffe0a0 }), postes.length);
    const poca = tex(64, 64, (g) => { const r = g.createRadialGradient(32, 32, 0, 32, 32, 32); r.addColorStop(0, 'rgba(255,200,120,.55)'); r.addColorStop(1, 'rgba(255,190,110,0)'); g.fillStyle = r; g.fillRect(0, 0, 64, 64); });
    const pg = new THREE.PlaneGeometry(12, 12); pg.rotateX(-Math.PI / 2);
    const pocas = new THREE.InstancedMesh(pg, new THREE.MeshBasicMaterial({ map: poca, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }), postes.length);
    const m4 = new THREE.Matrix4();
    postes.forEach(([x, z], i) => { im.setMatrixAt(i, m4.makeTranslation(x, CHAO, z)); lamp.setMatrixAt(i, m4.makeTranslation(x, CHAO + 6, z)); pocas.setMatrixAt(i, m4.makeTranslation(x, CHAO + .15, z)); });
    [im, lamp, pocas].forEach(o => grupo.add(sem(o))); }

  /* ---- luzes de aviação no alto dos prédios altos ---- */
  let aviao = null;
  if (luzesAviao.length) { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(luzesAviao, 3));
    aviao = new THREE.Points(g, new THREE.PointsMaterial({ color: 0xff3030, size: 1.6, transparent: true, depthWrite: false })); grupo.add(sem(aviao)); }

  /* ---- trânsito: carros, motos e pessoas ---- */
  const faixas = []; // pistas: eixo, linha, sentido
  const LIM = Math.min(R - 10, 180);
  for (let k = -N; k < N; k++) { const L = k * P + P / 2; if (Math.abs(L) > LIM - 8) continue; for (const ax of ['x', 'z']) for (const s of [1, -1]) faixas.push({ ax, L: L + s * 1.5, s, vel: 8 + rnd() * 5, fase: rnd() * 2 * LIM, n: 0 }); }
  const carros = [], motos = [], gente = [];
  const NC = mobile ? 110 : 220, NM = mobile ? 30 : 60, NP = mobile ? 260 : 520;
  const tot = NC + NM, cada = [];
  const perto = faixas.filter(f => Math.abs(f.L) < 115), ordem = perto.concat(faixas, perto);
  for (let n = 0; n < tot; n++) { const f = ordem[n % ordem.length]; cada.push(f); f.n++; }
  const usados = new Map();
  cada.forEach((f, n) => { const i = usados.get(f) || 0; usados.set(f, i + 1); // espaçados por igual na pista, mesma velocidade: ninguém atravessa ninguém
    const v = { f, p: -LIM + (f.fase + i * 2 * LIM / f.n) % (2 * LIM), vel: f.vel }; (n % 4 === 3 && motos.length < NM ? motos : carros.length < NC ? carros : motos).push(v); });
  const calcadas = []; for (let k = -N; k < N; k++) { const L = k * P + P / 2; if (Math.abs(L) > 110) continue; for (const ax of ['x', 'z']) for (const o of [-4.2, 4.2]) calcadas.push({ ax, L: L + o }); }
  for (let n = 0; n < NP; n++) { const c = calcadas[Math.floor(rnd() * calcadas.length)]; const lim = 125; gente.push({ c, lim, p: (rnd() * 2 - 1) * lim, s: rnd() < .5 ? 1 : -1, vel: .9 + rnd() * .7, fase: rnd() * 6, para: rnd() < .12 }); }

  // carro: carroceria (cor da instância) + cabine escura; luzes num segundo mesh com as mesmas matrizes
  const corpo = caixa(1.8, .7, 4.3, 0, .28, 0, 0xffffff), cabine = caixa(1.6, .6, 2.2, 0, .98, -.2, 0x262a33);
  const rodas = []; for (const [x, z] of [[-.85, 1.35], [.85, 1.35], [-.85, -1.35], [.85, -1.35]]) rodas.push(caixa(.3, .62, .62, x, 0, z, 0x111114));
  const carroG = mergeGeometries([corpo, cabine, ...rodas]);
  const luzC = mergeGeometries([caixa(.4, .16, .05, -.62, .62, 2.16, 0xfff4d0), caixa(.4, .16, .05, .62, .62, 2.16, 0xfff4d0), caixa(.4, .14, .05, -.62, .66, -2.16, 0xff2a2a), caixa(.4, .14, .05, .62, .66, -2.16, 0xff2a2a)]);
  const motoG = mergeGeometries([caixa(.35, .5, 1.9, 0, .3, 0, 0xffffff), caixa(.12, .62, .62, 0, 0, .7, 0x111114), caixa(.12, .62, .62, 0, 0, -.7, 0x111114), caixa(.42, .7, .32, 0, 1.0, -.1, 0x2b2f3a), caixa(.3, .3, .3, 0, 1.55, -.05, 0x1b1b1f)]);
  const luzM = mergeGeometries([caixa(.18, .14, .05, 0, .72, .98, 0xfff4d0), caixa(.16, .1, .05, 0, .62, -.98, 0xff2a2a)]);
  // pessoa: pernas e cabeça fixas, camisa com cor da instância
  const pernas = mergeGeometries([caixa(.16, .82, .2, -.1, 0, 0, 0x22242b), caixa(.16, .82, .2, .1, 0, 0, 0x22242b), (() => { const h = new THREE.SphereGeometry(.13, 8, 6).toNonIndexed(); h.translate(0, 1.6, 0); h.deleteAttribute('uv'); return pinta(h, 0xc89a78); })()]);
  const camisa = caixa(.44, .66, .26, 0, .82, 0, 0xffffff);
  const vMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .35, metalness: .35, envMapIntensity: .8 });
  const unl = new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: false });
  const iC = new THREE.InstancedMesh(carroG, vMat, carros.length), iCL = new THREE.InstancedMesh(luzC, unl, carros.length);
  const iM = new THREE.InstancedMesh(motoG, vMat, motos.length), iML = new THREE.InstancedMesh(luzM, unl, motos.length);
  const iP = new THREE.InstancedMesh(pernas, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .8 }), gente.length), iPC = new THREE.InstancedMesh(camisa, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .8 }), gente.length);
  const corC = [0xf2f2f2, 0x15161a, 0x9aa0a8, 0xb3121e, 0x1d3f8a, 0x5a5f66, 0xe8e2d4, 0x0f5132, 0xf0c419, 0x7a1f2b], cc = new THREE.Color();
  carros.forEach((v, i) => iC.setColorAt(i, cc.setHex(pick(corC))));
  motos.forEach((v, i) => iM.setColorAt(i, cc.setHex(pick([0xb3121e, 0x15161a, 0xf2f2f2, 0x1d3f8a, 0xf08a19]))));
  gente.forEach((v, i) => iPC.setColorAt(i, cc.setHex(pick([0xf2f2f2, 0x1b2a4a, 0x8a1f2b, 0x3c6e4a, 0xd9c7ae, 0x2b2b30, 0x6a8fc7, 0xe2a33b, 0x7a4a8f]))));
  [iC, iCL, iM, iML, iP, iPC].forEach(o => { o.instanceMatrix.setUsage(THREE.DynamicDrawUsage); o.frustumCulled = false; grupo.add(sem(o)); });

  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), up = new THREE.Vector3(0, 1, 0), vp = new THREE.Vector3(), um = new THREE.Vector3(1, 1, 1);
  const pose = (ax, L, p, s, y) => { if (ax === 'x') { vp.set(p, y, L); q.setFromAxisAngle(up, s > 0 ? Math.PI / 2 : -Math.PI / 2); } else { vp.set(L, y, p); q.setFromAxisAngle(up, s > 0 ? 0 : Math.PI); } return m4.compose(vp, q, um); };
  const wrap = (p, lim) => p > lim ? p - 2 * lim : p < -lim ? p + 2 * lim : p;

  function atualizar(t, dt) {
    dt = Math.min(dt, .1);
    carros.forEach((v, i) => { v.p = wrap(v.p + v.vel * dt * v.f.s, LIM); pose(v.f.ax, v.f.L, v.p, v.f.s, CHAO + .03); iC.setMatrixAt(i, m4); iCL.setMatrixAt(i, m4); });
    motos.forEach((v, i) => { v.p = wrap(v.p + v.vel * dt * v.f.s, LIM); const lado = Math.sin(t * .4 + i) * .5; pose(v.f.ax, v.f.L + lado * v.f.s, v.p, v.f.s, CHAO + .03); iM.setMatrixAt(i, m4); iML.setMatrixAt(i, m4); });
    gente.forEach((g, i) => { if (!g.para) g.p = wrap(g.p + g.vel * dt * g.s, g.lim); const bob = g.para ? 0 : Math.abs(Math.sin(t * 7 * g.vel + g.fase)) * .05; pose(g.c.ax, g.c.L, g.p, g.s, CHAO + .03 + bob); iP.setMatrixAt(i, m4); iPC.setMatrixAt(i, m4); });
    [iC, iCL, iM, iML, iP, iPC].forEach(o => o.instanceMatrix.needsUpdate = true);
    if (aviao) aviao.material.opacity = Math.sin(t * 3) > .3 ? 1 : .15;
  }
  atualizar(0, 0);
  return { grupo, atualizar };
}
