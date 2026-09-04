'use strict';
const assert = require('node:assert');
const E = require('../escala.js');

// Rango y default: porcentajes enteros, paso de 5.
assert.strictEqual(E.MIN, 70);
assert.strictEqual(E.MAX, 150);
assert.strictEqual(E.PASO, 5);
assert.strictEqual(E.DEF, 100);
assert.strictEqual((E.MAX - E.MIN) % E.PASO, 0);   // el máximo es alcanzable con el paso

// ── normalizar: clampea, redondea al paso y aguanta basura ──
assert.strictEqual(E.normalizar(100), 100);
assert.strictEqual(E.normalizar(125), 125);
assert.strictEqual(E.normalizar('125'), 125);      // viene de localStorage (string)
assert.strictEqual(E.normalizar(70), 70);
assert.strictEqual(E.normalizar(150), 150);
assert.strictEqual(E.normalizar(10), 70);          // piso
assert.strictEqual(E.normalizar(999), 150);        // techo
assert.strictEqual(E.normalizar(-5), 70);
assert.strictEqual(E.normalizar(103), 105);        // snap al paso
assert.strictEqual(E.normalizar(102), 100);
assert.strictEqual(E.normalizar(147.4), 145);
assert.strictEqual(E.normalizar(null), 100);       // sin nada guardado
assert.strictEqual(E.normalizar(undefined), 100);
assert.strictEqual(E.normalizar(''), 100);
assert.strictEqual(E.normalizar('grande'), 100);
assert.strictEqual(E.normalizar(NaN), 100);
assert.strictEqual(E.normalizar(Infinity), 100);
assert.strictEqual(E.normalizar({}), 100);

// normalizar es idempotente en todo el rango y nunca sale de él.
for (let v = 60; v <= 160; v++) {
  const n = E.normalizar(v);
  assert.ok(n >= E.MIN && n <= E.MAX, `fuera de rango: ${v} → ${n}`);
  assert.strictEqual(n % E.PASO, 0, `no cae en el paso: ${v} → ${n}`);
  assert.strictEqual(E.normalizar(n), n, `no idempotente: ${n}`);
}

// ── esDefault: es lo que decide si se limpia el localStorage y el zoom inline ──
assert.strictEqual(E.esDefault(100), true);
assert.strictEqual(E.esDefault('100'), true);
assert.strictEqual(E.esDefault(null), true);       // sin preferencia = 100%
assert.strictEqual(E.esDefault(102), true);        // snapea a 100
assert.strictEqual(E.esDefault(105), false);
assert.strictEqual(E.esDefault(70), false);

// ── factor: lo que va a `zoom` y al calc de --jw-vh ──
assert.strictEqual(E.factor(100), 1);
assert.strictEqual(E.factor(125), 1.25);
assert.strictEqual(E.factor(70), 0.7);
assert.strictEqual(E.factor(150), 1.5);
assert.strictEqual(E.factor('bah'), 1);

// ── etiqueta: lo que se lee en el <output> del slider ──
assert.strictEqual(E.etiqueta(100), '100%');
assert.strictEqual(E.etiqueta(70), '70%');
assert.strictEqual(E.etiqueta(133), '135%');
assert.strictEqual(E.etiqueta(null), '100%');

console.log('escala.test.js OK');
