'use strict';
// Tests de la lógica pura del campo de escucha (mapeo mic → intensidad visual).
// Corre con: node frontend/shell/__tests__/voice-field.test.js
const assert = require('assert');
const { mapear, suavizar, vale, espectro, PISO, TECHO, BASE } =
  require('../voice-field.js')._pure;

// ── mapear ────────────────────────────────────────────────────────
// Silencio total → presencia MÍNIMA, nunca cero: "te escucho" no puede apagarse
// entre palabra y palabra.
assert.strictEqual(mapear(0), BASE);
assert.strictEqual(mapear(PISO), BASE);
assert.strictEqual(mapear(PISO - 0.01), BASE);   // bajo el piso, igual
// Techo del rango real del mic → intensidad plena.
assert.strictEqual(mapear(TECHO), 1);
assert.strictEqual(mapear(1), 1);                // clamp: nunca pasa de 1
assert.strictEqual(mapear(50), 1);
// Monótona creciente dentro del rango.
let prev = -1;
for (let n = 0; n <= 0.6; n += 0.02) {
  const v = mapear(n);
  assert.ok(v >= prev, `mapear debe crecer (n=${n})`);
  assert.ok(v >= BASE && v <= 1, `mapear fuera de rango (n=${n} → ${v})`);
  prev = v;
}
// La gamma < 1 expande la zona BAJA: hablar bajito ya tiene que verse. A mitad
// del rango real la intensidad supera holgadamente el punto medio lineal.
const medio = (PISO + TECHO) / 2;
assert.ok(mapear(medio) > 0.5 + BASE / 2, 'la voz baja tiene que levantar el campo');
// Basura (mic sin publicar nivel todavía) → mínimo, sin NaN.
for (const basura of [undefined, null, NaN, Infinity, -Infinity, 'x', {}]) {
  assert.strictEqual(mapear(basura), BASE, `basura ${String(basura)} → BASE`);
}

// ── suavizar ──────────────────────────────────────────────────────
// Sube rápido (ataque) y baja despacio (caída): sin parpadeo entre sílabas.
const sube = suavizar(0.2, 1);
const baja = suavizar(1, 0.2);
assert.ok(sube > 0.2 && sube < 1, 'el ataque avanza sin saltar al objetivo');
assert.ok(1 - baja < sube - 0.2, 'la caída tiene que ser más lenta que el ataque');
// Nunca se pasa del objetivo (sin overshoot ni rebote).
assert.ok(sube <= 1 && baja >= 0.2);
// Converge: repetir suavizar acerca al objetivo indefinidamente.
let v = 0;
for (let i = 0; i < 200; i++) v = suavizar(v, 0.8);
assert.ok(Math.abs(v - 0.8) < 1e-6, 'debe converger al objetivo');
// Estable en el punto fijo.
assert.strictEqual(suavizar(0.5, 0.5), 0.5);
// Basura → tratada como 0, sin NaN.
assert.strictEqual(suavizar(NaN, 0), 0);
assert.ok(Number.isFinite(suavizar(undefined, undefined)));

// ── vale (¿escribir al DOM?) ──────────────────────────────────────
// Escribir una custom property invalida el estilo del subárbol: un cambio
// invisible no se paga.
assert.strictEqual(vale(0.5, 0.5), false);
assert.strictEqual(vale(0.5, 0.502), false);
assert.strictEqual(vale(0.5, 0.6), true);
assert.strictEqual(vale(0.6, 0.5), true);   // simétrico: también al bajar
// El primer frame (escrito = -1) siempre escribe.
assert.strictEqual(vale(-1, BASE), true);

// ── espectro ──────────────────────────────────────────────────────
// Sin bins todavía (el waveform no publicó nada): línea de base, nunca vacío.
for (const nada of [undefined, null, []]) {
  const e = espectro(nada, 9);
  assert.strictEqual(e.length, 9);
  assert.ok(e.every(v => v === 0.02), 'sin señal → línea de base');
}
// Simétrico: la barra i y su espejo tienen la MISMA altura (una barra que salta
// sola de un lado se lee como error, no como voz).
const bins = Array.from({ length: 64 }, (_, i) => (64 - i) / 64);   // graves fuertes
const e33 = espectro(bins, 33);
assert.strictEqual(e33.length, 33);
for (let i = 0; i < 16; i++) {
  assert.strictEqual(e33[i], e33[32 - i], `barra ${i} debe espejar a ${32 - i}`);
}
// Graves al CENTRO: con un espectro que decae, el centro es el pico.
assert.ok(e33[16] > e33[0], 'los graves van al centro');
assert.ok(e33[16] >= Math.max(...e33), 'el centro es el máximo');
// Siempre dentro de rango, incluso con basura adentro del array.
const sucio = espectro([NaN, 2, -1, 'x', undefined, 0.5], 7);
assert.ok(sucio.every(v => v >= 0.02 && v <= 1), `fuera de rango: ${sucio}`);
// n inválido no rompe.
assert.strictEqual(espectro(bins, 0).length, 1);

console.log('✓ voice-field: todos los tests pasaron');
