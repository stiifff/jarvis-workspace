// Tests del catálogo de dispositivos del Mobile Studio. Corre con:
//   node frontend/sections/mobile-preview/__tests__/device-catalog.test.js
'use strict';
const assert = require('assert');
const DC = require('../device-catalog.js');
const { DEVICES, ORDEN, device, dims, cutoutBox, statusBarBox, homebarBox, safeZones } = DC;

// ── Integridad del catálogo: todo device tiene los campos y rangos sanos ──
for (const key of Object.keys(DEVICES)) {
  const d = DEVICES[key];
  assert.ok(d.nombre && typeof d.nombre === 'string', `${key}: nombre`);
  assert.ok(['apple', 'samsung', 'google', 'tablet'].includes(d.marca), `${key}: marca`);
  assert.ok(d.vw >= 320 && d.vw <= 1400, `${key}: vw sano (${d.vw})`);
  assert.ok(d.vh >= 480 && d.vh <= 1400, `${key}: vh sano (${d.vh})`);
  assert.ok(d.vh > d.vw, `${key}: portrait (vh > vw)`);
  assert.ok(d.dpr >= 1 && d.dpr <= 4, `${key}: dpr sano`);
  assert.ok(d.statusBar >= 0 && d.statusBar <= 70, `${key}: statusBar sano`);
  assert.ok(d.safe && d.safe.top >= d.statusBar - 1, `${key}: safe.top >= statusBar`);
  assert.ok(d.cutout && typeof d.cutout.tipo === 'string', `${key}: cutout.tipo`);
  if (d.cutout.tipo !== 'none') {
    assert.ok(d.cutout.w > 0 && d.cutout.h > 0 && d.cutout.y >= 0, `${key}: cutout geometría`);
    assert.ok(d.cutout.y + d.cutout.h <= d.safe.top + 1, `${key}: el recorte vive dentro del safe.top`);
    assert.ok(d.cutout.w < d.vw / 2, `${key}: recorte más angosto que medio viewport`);
  }
  assert.ok(d.radio >= 0 && d.radio <= 80, `${key}: radio sano`);
  if (d.homebar) {
    assert.ok(d.homebar.w > 0 && d.homebar.h > 0 && d.homebar.b >= 0, `${key}: homebar`);
    assert.ok(d.safe.bottom > 0, `${key}: homebar implica safe.bottom`);
  }
  assert.ok(d.bezel > 0 && d.bezel <= 30, `${key}: bezel sano`);
}

// ── ORDEN apunta solo a devices existentes y no repite ──
assert.ok(ORDEN.length >= 5, 'ORDEN con al menos los 5 históricos');
assert.strictEqual(new Set(ORDEN).size, ORDEN.length, 'ORDEN sin repetidos');
for (const k of ORDEN) assert.ok(DEVICES[k], `ORDEN: ${k} existe`);

// ── Claves históricas del Mobile Studio siguen vivas (pools/estado viejo) ──
for (const k of ['ip15p', 'ipse', 'px8', 's24', 'ipad']) assert.ok(DEVICES[k], `legacy: ${k}`);

// ── device(): fallback al default con clave desconocida ──
assert.strictEqual(device('no-existe'), DEVICES.ip15p);

// ── Valores EXACTOS investigados (fuentes cruzadas 2026-07-11) — si esto
//    falla, alguien tocó el catálogo sin fuente. Ver [[mobile-studio-fidelidad]].
{
  // iPhone 15/15 Pro: 393×852 @3x, safe 59/34, status bar 54, isla 126×37.33 @y11
  const d = DEVICES.ip15p;
  assert.deepStrictEqual([d.vw, d.vh, d.dpr, d.statusBar], [393, 852, 3, 54]);
  assert.deepStrictEqual([d.safe.top, d.safe.bottom], [59, 34]);
  assert.deepStrictEqual([d.cutout.w, d.cutout.h, d.cutout.y], [126, 37.33, 11]);
  assert.strictEqual(d.radio, 55);
  // iPhone 16 Pro: 402×874, safe top 62 (NO 59 — cambió en esta gen), isla baja a y=14
  assert.deepStrictEqual([DEVICES.ip16p.vw, DEVICES.ip16p.vh, DEVICES.ip16p.safe.top, DEVICES.ip16p.cutout.y], [402, 874, 62, 14]);
  assert.strictEqual(DEVICES.ip16pm.vw, 440);
  assert.strictEqual(DEVICES.ip16pm.vh, 956);
  // iPhone 13/14: 390×844, notch 161×32, safe 47
  assert.deepStrictEqual([DEVICES.ip13.vw, DEVICES.ip13.vh, DEVICES.ip13.safe.top, DEVICES.ip13.cutout.w], [390, 844, 47, 161]);
  // Galaxy S23/S24/S25: 360×780 (la corrección clave — el catálogo viejo decía 800)
  assert.deepStrictEqual([DEVICES.s24.vw, DEVICES.s24.vh, DEVICES.s24.dpr], [360, 780, 3]);
  // Ultras: 384dp de fábrica (FHD+ a 450dpi), DPR 2.8125 out-of-box
  assert.deepStrictEqual([DEVICES.s24u.vw, DEVICES.s24u.vh, DEVICES.s24u.dpr], [384, 832, 2.8125]);
  // Pixel (verbatim AOSP): P8 punch ⌀27.6 centro y=25 → y 11.2; P9 923 de alto (2424/2.625)
  assert.deepStrictEqual([DEVICES.px8.cutout.w, DEVICES.px8.cutout.y], [27.6, 11.2]);
  assert.deepStrictEqual([DEVICES.px9.vw, DEVICES.px9.vh], [412, 923]);
  // Home indicator iOS: 134×5 a 8pt del borde
  assert.deepStrictEqual(DEVICES.ip15p.homebar, { w: 134, h: 5, b: 8 });
}

// ── insets(): el área de contenido REAL que el sistema le da a la app ──
{
  const { insets } = DC;
  // iPhone 15 Pro portrait: 59 arriba (isla+status), 34 abajo (home)
  assert.deepStrictEqual(insets('ip15p', false), { top: 59, right: 0, bottom: 34, left: 0 });
  // landscape iOS: SIN top (status bar oculta), isla a los costados, 21 abajo
  assert.deepStrictEqual(insets('ip15p', true), { top: 0, right: 59, bottom: 21, left: 59 });
  // Android landscape: la status bar sigue (statusBarLand), punch a la izquierda
  assert.deepStrictEqual(insets('s24', true), { top: 24, right: 0, bottom: 24, left: 25 });
  // SE: solo status bar clásica, sin home indicator
  assert.deepStrictEqual(insets('ipse', false), { top: 20, right: 0, bottom: 0, left: 0 });
  // el área de contenido nunca es degenerada
  for (const key of Object.keys(DEVICES)) {
    for (const land of [false, true]) {
      const v = dims(key, land), i = insets(key, land);
      assert.ok(v.w - i.left - i.right > 200, `${key}: ancho útil sano`);
      assert.ok(v.h - i.top - i.bottom > 200, `${key}: alto útil sano`);
    }
  }
}

// ── frameRadius(): radio+bezel por default; override para pantallas cuadradas ──
assert.strictEqual(DC.frameRadius('ip15p'), 55 + 13);
assert.strictEqual(DC.frameRadius('ipse'), 34, 'SE: cuerpo redondeado con pantalla cuadrada');

// ── dprLabel(): legible, sin colas binarias ──
assert.strictEqual(DC.dprLabel('ip15p'), '3');
assert.strictEqual(DC.dprLabel('px8'), '2.63');
assert.strictEqual(DC.dprLabel('s24u'), '2.81');

// ── dims(): landscape intercambia ──
assert.deepStrictEqual(dims('ip15p', false), { w: DEVICES.ip15p.vw, h: DEVICES.ip15p.vh });
assert.deepStrictEqual(dims('ip15p', true), { w: DEVICES.ip15p.vh, h: DEVICES.ip15p.vw });

// ── cutoutBox(): centrado portrait, rotado a la IZQUIERDA en landscape ──
{
  const c = DEVICES.ip15p.cutout, v = dims('ip15p', false);
  const box = cutoutBox('ip15p', false);
  assert.ok(Math.abs((box.x + box.w / 2) - v.w / 2) < 0.01, 'isla centrada en X');
  assert.strictEqual(box.y, c.y);
  assert.strictEqual(box.w, c.w);
  assert.strictEqual(box.h, c.h);
  const lv = dims('ip15p', true);
  const lbox = cutoutBox('ip15p', true);
  assert.strictEqual(lbox.x, c.y, 'landscape: pegada al borde izquierdo a la distancia y');
  assert.ok(Math.abs((lbox.y + lbox.h / 2) - lv.h / 2) < 0.01, 'landscape: centrada en Y');
  assert.strictEqual(lbox.w, c.h, 'landscape: rota (w=h)');
  assert.strictEqual(lbox.h, c.w, 'landscape: rota (h=w)');
  assert.strictEqual(cutoutBox('ipse', false), null, 'SE sin recorte');
}

// ── statusBarBox(): iPhone la pierde en landscape; Android la conserva ──
{
  const sb = statusBarBox('ip15p', false);
  assert.deepStrictEqual(sb, { x: 0, y: 0, w: DEVICES.ip15p.vw, h: DEVICES.ip15p.statusBar });
  assert.strictEqual(statusBarBox('ip15p', true), null, 'iOS apaisado: sin status bar');
  const sba = statusBarBox('s24', true);
  assert.ok(sba && sba.w === DEVICES.s24.vh, 'Android apaisado: status bar a lo ancho');
  // La status bar gruesa de Pixel es de portrait: apaisado cae a statusBarLand
  assert.strictEqual(statusBarBox('px9', false).h, 66);
  assert.strictEqual(statusBarBox('px9', true).h, 24);
}

// ── homebarBox(): centrado, pegado abajo; más ancho apaisado; null sin barra ──
{
  const hb = homebarBox('ip15p', false), d = DEVICES.ip15p, v = dims('ip15p', false);
  assert.ok(Math.abs((hb.x + hb.w / 2) - v.w / 2) < 0.51, 'homebar centrada');
  assert.strictEqual(hb.y, v.h - d.homebar.b - d.homebar.h);
  const hbl = homebarBox('ip15p', true);
  assert.ok(hbl.w > hb.w, 'apaisado: más ancha');
  assert.strictEqual(homebarBox('ipse', false), null, 'SE sin homebar');
}

// ── safeZones(): portrait top+bottom; landscape laterales+bottom; dentro del viewport ──
{
  const zp = safeZones('ip15p', false);
  assert.deepStrictEqual(zp.map((z) => z.lado), ['top', 'bottom']);
  const zl = safeZones('ip15p', true);
  assert.deepStrictEqual(zl.map((z) => z.lado), ['izq', 'der', 'bottom']);
  for (const key of Object.keys(DEVICES)) {
    for (const land of [false, true]) {
      const v = dims(key, land);
      for (const z of safeZones(key, land)) {
        assert.ok(z.x >= 0 && z.y >= 0 && z.x + z.w <= v.w + 0.01 && z.y + z.h <= v.h + 0.01,
          `${key} ${land ? 'land' : 'port'}: zona ${z.lado} dentro del viewport`);
      }
    }
  }
  const zse = safeZones('ipse', false);
  assert.deepStrictEqual(zse.map((z) => z.lado), ['top'], 'SE: solo status bar arriba');
}

console.log('device-catalog.test.js OK');
