'use strict';
// Tests de la lógica pura del dictado FIJADO (doble-tap del PTT).
// Corre con: node frontend/shell/__tests__/ptt-fijado.test.js
const assert = require('assert');
const { esDobleTap, alBlur, alOcultarPestana, alMouseUp, hintFijado, DOBLE_TAP_MS,
        alPararRecorder } =
  require('../ptt-fijado.js')._pure;

// ── esDobleTap ────────────────────────────────────────────────────
// Dos taps dentro de la ventana → doble-tap.
assert.strictEqual(esDobleTap(1000, 800), true);
assert.strictEqual(esDobleTap(1000, 1000 - DOBLE_TAP_MS), true);   // justo en el borde
// Fuera de la ventana → no.
assert.strictEqual(esDobleTap(1000, 1000 - DOBLE_TAP_MS - 1), false);
assert.strictEqual(esDobleTap(5000, 800), false);
// Sin tap previo (0 = nunca) NUNCA es doble-tap, aunque performance.now() sea
// chico al arrancar la página (dt caería dentro de la ventana por accidente).
assert.strictEqual(esDobleTap(300, 0), false);
// dt no positivo (relojes raros / mismo evento) → no.
assert.strictEqual(esDobleTap(800, 800), false);
assert.strictEqual(esDobleTap(700, 800), false);

// ── alBlur ────────────────────────────────────────────────────────
// Fijado + foco en un iframe de ESTA página (Web Preview) → seguir grabando.
assert.strictEqual(alBlur({ fijado: true, tagActivo: 'IFRAME' }), 'mantener');
// Fijado pero blur real (otra app/ventana: activeElement no es iframe) → soltar.
assert.strictEqual(alBlur({ fijado: true, tagActivo: 'BODY' }), 'soltar');
assert.strictEqual(alBlur({ fijado: true, tagActivo: undefined }), 'soltar');
// Hold normal (tecla sostenida): el keyup se pierde en el iframe → soltar siempre.
assert.strictEqual(alBlur({ fijado: false, tagActivo: 'IFRAME' }), 'soltar');
assert.strictEqual(alBlur({ fijado: false, tagActivo: 'BODY' }), 'soltar');

// ── alOcultarPestana ──────────────────────────────────────────────
// Pestaña oculta con dictado fijado activo → commitear ANTES de soltar el stream.
assert.strictEqual(alOcultarPestana({ fijado: true, activo: true }), 'enviar');
// Sin hold activo (carrera: ya se estaba cerrando) o sin fijar → nada especial.
assert.strictEqual(alOcultarPestana({ fijado: true, activo: false }), 'nada');
assert.strictEqual(alOcultarPestana({ fijado: false, activo: true }), 'nada');
assert.strictEqual(alOcultarPestana({ fijado: false, activo: false }), 'nada');

// ── alMouseUp (binding de botón de mouse: mouse3/mouse4) ─────────
// Hold real (apretado ≥ umbral) → release normal (commitea y envía).
assert.strictEqual(alMouseUp({ durMs: 500, ahoraMs: 1000, ultimoTapMs: 900, umbralTapMs: 220 }), 'soltar');
assert.strictEqual(alMouseUp({ durMs: 220, ahoraMs: 1000, ultimoTapMs: 0, umbralTapMs: 220 }), 'soltar');
// Click corto sin tap previo → 'tap' (descarta la captura, muestra la píldora).
assert.strictEqual(alMouseUp({ durMs: 100, ahoraMs: 1000, ultimoTapMs: 0, umbralTapMs: 220 }), 'tap');
// Click corto FUERA de la ventana de doble-tap → 'tap'.
assert.strictEqual(alMouseUp({ durMs: 100, ahoraMs: 5000, ultimoTapMs: 1000, umbralTapMs: 220 }), 'tap');
// Doble-click (dos clicks cortos dentro de la ventana) → 'fijar'.
assert.strictEqual(alMouseUp({ durMs: 100, ahoraMs: 1300, ultimoTapMs: 1000, umbralTapMs: 220 }), 'fijar');
assert.strictEqual(alMouseUp({ durMs: 100, ahoraMs: 1000 + DOBLE_TAP_MS, ultimoTapMs: 1000, umbralTapMs: 220 }), 'fijar');
// Umbral default (220) si no se pasa.
assert.strictEqual(alMouseUp({ durMs: 100, ahoraMs: 1300, ultimoTapMs: 1000 }), 'fijar');
assert.strictEqual(alMouseUp({ durMs: 300, ahoraMs: 1300, ultimoTapMs: 1000 }), 'soltar');

// ── hintFijado ────────────────────────────────────────────────────
// Sin traductor: texto ES con la tecla y el Esc visibles.
{
  const h = hintFijado('Alt');
  assert.ok(h.includes('Alt'), h);
  assert.ok(h.includes('Esc'), h);
  assert.ok(h.includes('fijado'), h);
}
// Con traductor: pasa el template completo por t() y recién ahí mete la tecla.
{
  const t = (s) => s === 'fijado · {k} envía · Esc cancela' ? 'pinned · {k} sends · Esc cancels' : s;
  const h = hintFijado('Alt', t);
  assert.strictEqual(h, '📌 pinned · Alt sends · Esc cancels');
}

// ── alPararRecorder (onstop del MediaRecorder) ───────────────────
// El bug de "se envió solo sin soltar la tecla" (2026-07-17): el track del mic
// moría mid-hold, el onstop veía la generación vigente y COMMITEABA + enviaba
// como si fuera un release. Un stop espontáneo con la tecla aún apretada NO es
// un release: hay que revivir la captura, jamás enviar.
// Generación vieja (lo pisó un hold nuevo): morir en silencio.
assert.strictEqual(alPararRecorder({ genRecorder: 3, genVigente: 4, soltado: false }), 'nada');
assert.strictEqual(alPararRecorder({ genRecorder: 3, genVigente: 4, soltado: true }), 'nada');
// Stop DESPUÉS del release (cola/discard lo frenó): flujo normal de commit.
assert.strictEqual(alPararRecorder({ genRecorder: 4, genVigente: 4, soltado: true }), 'commitear');
// Stop espontáneo con la tecla AÚN apretada (track del mic murió) → revivir, NO enviar.
assert.strictEqual(alPararRecorder({ genRecorder: 4, genVigente: 4, soltado: false }), 'revivir');

// ── API depurada (2026-07-17): el SpeechRecognition se removió del dictado ──
// (100% server: Groq + fallback local). alTerminarSR y su tope de revividas
// murieron con él; alPararRecorder (revive del RECORDER ante mic caído) sigue.
const api = require('../ptt-fijado.js')._pure;
assert.ok(!('alTerminarSR' in api), 'API muerta expuesta: alTerminarSR');
assert.ok(!('MAX_REVIVIDAS_SR' in api), 'API muerta expuesta: MAX_REVIVIDAS_SR');

console.log('ptt-fijado.test.js OK');
