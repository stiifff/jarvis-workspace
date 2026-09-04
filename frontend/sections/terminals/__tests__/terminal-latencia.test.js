'use strict';
// Tests del medidor de latencia de ECO de la terminal: mide cuántos ms tarda en
// aparecer lo que el usuario tipea (round-trip real: tecla → WS → PTY → tmux →
// eco → WS → xterm). Es la herramienta de verificación EN LA MÁQUINA DEL USUARIO
// — muestra el número real en su browser, no una suposición de headless.
// Lógica pura (acá), wiring con el WS/UI en terminal.js.
const assert = require('node:assert');
const M = require('../terminal-latencia.js');

// ─── Un output sin input previo NO es eco de nada → null ──────────────────────
const m = M.crearMedidor({ ventana: 5 });
assert.strictEqual(m.marcarOutput(1000), null);
assert.deepStrictEqual(m.stats(), { n: 0, ultima: null, p50: null, p90: null });

// ─── input → primer output = round-trip en ms ─────────────────────────────────
m.marcarInput(1000);
assert.strictEqual(m.marcarOutput(1042), 42);

// ─── el SEGUNDO output sin nuevo input no cuenta (es flood del agente, no eco) ─
assert.strictEqual(m.marcarOutput(1050), null);

// ─── input mientras hay uno pendiente: se queda con el PRIMERO de la ráfaga ────
// (si tipeás 3 teclas rápidas, el eco que vuelve es el de la primera).
m.marcarInput(2000);
m.marcarInput(2005);   // ráfaga: no pisa al pendiente
m.marcarInput(2010);
assert.strictEqual(m.marcarOutput(2030), 30);   // 2030 - 2000

// ─── ms negativo (reloj raro: output antes que input) → defensivo, null ───────
m.marcarInput(3000);
assert.strictEqual(m.marcarOutput(2999), null);
// y el pendiente quedó limpio: el siguiente output no arrastra nada
assert.strictEqual(m.marcarOutput(3100), null);

// ─── marcarInput con ts no-finito se ignora (no traba el pendiente) ───────────
m.marcarInput(NaN);
assert.strictEqual(m.marcarOutput(4000), null);   // no había pendiente válido

// ─── stats: percentiles nearest-rank sobre una muestra conocida ───────────────
const g = M.crearMedidor({ ventana: 50 });
for (let i = 1; i <= 10; i++) { g.marcarInput(i * 1000); g.marcarOutput(i * 1000 + i * 10); }
// muestras = [10,20,30,40,50,60,70,80,90,100]
const s = g.stats();
assert.strictEqual(s.n, 10);
assert.strictEqual(s.ultima, 100);
assert.strictEqual(s.p50, 50);   // ceil(0.5*10)=5 → idx 4
assert.strictEqual(s.p90, 90);   // ceil(0.9*10)=9 → idx 8

// ─── ventana acota a las últimas N muestras ───────────────────────────────────
const w = M.crearMedidor({ ventana: 3 });
for (let i = 1; i <= 6; i++) { w.marcarInput(i * 100); w.marcarOutput(i * 100 + i); }
// agregadas [1,2,3,4,5,6] pero ventana=3 → solo [4,5,6]
const sw = w.stats();
assert.strictEqual(sw.n, 3);
assert.strictEqual(sw.ultima, 6);

console.log('OK terminal-latencia');
