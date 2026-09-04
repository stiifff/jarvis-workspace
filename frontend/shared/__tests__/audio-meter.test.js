// Tests de la matemática pura del medidor de audio del waveform del PTT.
//   node frontend/shared/__tests__/audio-meter.test.js
'use strict';
const assert = require('assert');
const { nivel, barras, flujo, suavizar } = require('../audio-meter.js');

// ── nivel: RMS del time-domain (Uint8 centrado en 128) → 0..1 ──
assert.ok(nivel(new Uint8Array(64).fill(128)) < 0.02, 'silencio ≈ 0');
const fuerte = Uint8Array.from({ length: 64 }, (_, i) => (i % 2 ? 255 : 0));
assert.ok(nivel(fuerte) > 0.5, 'señal fuerte → alto');
assert.ok(nivel(fuerte) <= 1, 'clampea a 1');
assert.strictEqual(nivel(new Uint8Array(0)), 0, 'vacío → 0');

// ── barras: n bandas, cada una 0..1 ──
const f = new Uint8Array(32).fill(128);
const b = barras(f, 7);
assert.strictEqual(b.length, 7, 'devuelve n barras');
assert.ok(b.every(x => x >= 0 && x <= 1), 'todas en 0..1');
assert.ok(Math.abs(b[0] - 0.5) < 0.02, '128/255 ≈ 0.5');
assert.ok(barras(new Uint8Array(32).fill(0), 5).every(x => x === 0), 'freq 0 → barras 0');
assert.ok(barras(new Uint8Array(32).fill(255), 5).every(x => Math.abs(x - 1) < 0.001), 'freq 255 → 1');

// ── flujo: visualizador simétrico, reactivo al volumen, todas las barras vivas ──
assert.strictEqual(flujo(new Uint8Array(64).fill(0), 15).length, 15, 'devuelve n barras');
assert.ok(flujo(new Uint8Array(64).fill(0), 15).every(x => x === 0), 'silencio → todo 0');
const ff = flujo(new Uint8Array(64).fill(128), 15);
assert.ok(ff.every(x => x >= 0 && x <= 1), 'todas en 0..1');
// Simetría centro→bordes
for (let i = 0; i < 7; i++) assert.ok(Math.abs(ff[i] - ff[14 - i]) < 1e-9, 'simétrico');
// Con señal, TODAS las barras se mueven (ninguna queda en 0) — el fix del "solo una barra"
assert.ok(ff.every(x => x > 0), 'con señal todas las barras > 0 (todas bailan)');
// El centro pesa más que los bordes (campana)
assert.ok(ff[7] >= ff[0] && ff[7] >= ff[14], 'centro >= bordes');
// Más volumen → barras más altas (reactivo al volumen)
const bajo  = flujo(new Uint8Array(64).fill(40), 15);
const alto  = flujo(new Uint8Array(64).fill(200), 15);
assert.ok(alto[7] > bajo[7], 'más volumen → centro más alto');
assert.strictEqual(flujo(new Uint8Array(0), 15).length, 15, 'vacío → n ceros');
assert.deepStrictEqual(flujo(null, 0), [], 'sin barras → []');

// ── suavizar: ataque rápido (sube), release lento (baja) ──
assert.ok(Math.abs(suavizar(0, 1) - 0.5) < 1e-9, 'attack default 0.5');
assert.ok(Math.abs(suavizar(1, 0) - 0.82) < 1e-9, 'release default 0.18 → cae poco');
assert.ok(Math.abs(suavizar(0.5, 0.5) - 0.5) < 1e-9, 'sin cambio si igual');
assert.ok(suavizar(0, 1) < 1 && suavizar(1, 0) > 0.5, 'attack no salta a 1, release no cae a 0');

console.log('audio-meter: OK');
