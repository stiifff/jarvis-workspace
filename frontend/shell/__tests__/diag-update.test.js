'use strict';
// Tests de la lógica pura del diagnóstico post-update (ventanasCongeladas).
// Corre con: node frontend/shell/__tests__/diag-update.test.js
const assert = require('assert');
const { ventanasCongeladas } = require('../diag-update.js')._pure;

const M = (t, raf, rx, wheel) => ({ t, raf, rx, wheel });

// Sin problemas → sin ventanas
assert.deepStrictEqual(ventanasCongeladas([M(0, 16, 100, 2), M(200, 17, 80, 1)]), []);

// Main thread trabado ≥800ms → una ventana 'main-thread'
{
  const ms = [M(0, 16, 10, 0), M(200, 900, 0, 0), M(400, 900, 0, 0),
              M(600, 900, 0, 0), M(800, 900, 0, 0), M(1000, 900, 0, 0),
              M(1200, 16, 10, 0)];
  const v = ventanasCongeladas(ms);
  assert.strictEqual(v.length, 1);
  assert.strictEqual(v[0].motivo, 'main-thread');
  assert.ok(v[0].ms >= 800, `ventana de ${v[0].ms}ms`);
}

// Rueda sin output (rx=0 con wheel>0) → 'sin-output'
{
  const ms = [M(0, 16, 10, 1), M(200, 16, 0, 3), M(400, 16, 0, 4),
              M(600, 16, 0, 2), M(800, 16, 0, 3), M(1000, 16, 0, 1),
              M(1200, 16, 50, 2)];
  const v = ventanasCongeladas(ms);
  assert.strictEqual(v.length, 1);
  assert.strictEqual(v[0].motivo, 'sin-output');
}

// Micro-hipo (<800ms) NO cuenta
{
  const ms = [M(0, 16, 10, 0), M(200, 900, 10, 0), M(400, 16, 10, 0)];
  assert.deepStrictEqual(ventanasCongeladas(ms), []);
}

// Rueda sin output PERO con rx llegando → no es freeze (el flood del agente cuenta como vida)
{
  const ms = [M(0, 16, 500, 5), M(200, 16, 500, 5), M(400, 16, 500, 5)];
  assert.deepStrictEqual(ventanasCongeladas(ms), []);
}

// Mixto: jank local + mudo en el mismo tramo → 'mixto'
{
  const ms = [M(0, 900, 0, 0), M(200, 16, 0, 3), M(400, 900, 0, 0),
              M(600, 900, 0, 0), M(800, 900, 0, 0), M(1000, 16, 10, 0)];
  const v = ventanasCongeladas(ms);
  assert.strictEqual(v.length, 1);
  assert.strictEqual(v[0].motivo, 'mixto');
}

// Tolera basura
assert.deepStrictEqual(ventanasCongeladas(undefined), []);
assert.deepStrictEqual(ventanasCongeladas([]), []);

console.log('OK ventanasCongeladas');
console.log('OK ALL');
