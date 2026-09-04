'use strict';
// Tests de la lógica pura de layouts / split del Web Preview (preview-layout.js).
// Node puro (assert nativo), patrón UMD _pure.
const assert = require('assert');
const L = require('../preview-layout.js')._pure;

let n = 0;
const test = (nombre, fn) => { fn(); n++; };

// ── Catálogo ──────────────────────────────────────────────────────
test('LAYOUTS tiene 9 disposiciones con ids únicos y panes 1..4', () => {
  assert.strictEqual(L.LAYOUTS.length, 9);
  const ids = L.LAYOUTS.map((x) => x.id);
  assert.strictEqual(new Set(ids).size, 9, 'ids duplicados');
  for (const lay of L.LAYOUTS) {
    assert.ok(lay.panes >= 1 && lay.panes <= 4, `panes fuera de rango en ${lay.id}`);
    assert.ok(typeof lay.label === 'string' && lay.label.length, `sin label en ${lay.id}`);
    assert.ok(typeof lay.template === 'string' && lay.template.includes('/'), `template inválido en ${lay.id}`);
  }
});

// ── normalizar ────────────────────────────────────────────────────
test('normalizar acepta ids válidos y cae a "1" con basura', () => {
  assert.strictEqual(L.normalizar('3c'), '3c');
  assert.strictEqual(L.normalizar('4'), '4');
  assert.strictEqual(L.normalizar('zz'), '1');
  assert.strictEqual(L.normalizar(undefined), '1');
  assert.strictEqual(L.normalizar(null), '1');
});

// ── panesDe ───────────────────────────────────────────────────────
test('panesDe devuelve la cantidad correcta (default 1)', () => {
  assert.strictEqual(L.panesDe('1'), 1);
  assert.strictEqual(L.panesDe('2c'), 2);
  assert.strictEqual(L.panesDe('2r'), 2);
  assert.strictEqual(L.panesDe('3c'), 3);
  assert.strictEqual(L.panesDe('3L'), 3);
  assert.strictEqual(L.panesDe('3T'), 3);
  assert.strictEqual(L.panesDe('4'), 4);
  assert.strictEqual(L.panesDe('4c'), 4);
  assert.strictEqual(L.panesDe('4L'), 4);
  assert.strictEqual(L.panesDe('basura'), 1);
});

// ── template ──────────────────────────────────────────────────────
test('template refleja la disposición y cae al único con basura', () => {
  assert.ok(L.template('3c').includes('a b c'));
  assert.ok(L.template('2r').includes('"a" 1fr "b" 1fr'));
  assert.strictEqual(L.template('nope'), L.template('1'));
});

// ── asignar (qué pestañas se ven en el split) ─────────────────────
test('asignar toma las primeras N pestañas', () => {
  assert.deepStrictEqual(L.asignar([10, 20, 30, 40], 2), [10, 20]);
  assert.deepStrictEqual(L.asignar([10, 20, 30, 40, 50], 3), [10, 20, 30]);
});

test('asignar rellena con null si faltan pestañas', () => {
  assert.deepStrictEqual(L.asignar([10], 4), [10, null, null, null]);
  assert.deepStrictEqual(L.asignar([], 1), [null]);
  assert.deepStrictEqual(L.asignar([], 2), [null, null]);
});

test('asignar garantiza que la pestaña activa quede visible', () => {
  // activa 50 no entra en las primeras 2 → reemplaza el último visible
  assert.deepStrictEqual(L.asignar([10, 20, 30, 40, 50], 2, 50), [10, 50]);
  // activa ya visible → sin cambios
  assert.deepStrictEqual(L.asignar([10, 20, 30], 2, 10), [10, 20]);
  // activa null → primeras N
  assert.deepStrictEqual(L.asignar([10, 20, 30], 2, null), [10, 20]);
});

test('asignar es defensivo con panes inválido', () => {
  assert.deepStrictEqual(L.asignar([10, 20], 0), [10]);
  assert.deepStrictEqual(L.asignar([10, 20], NaN), [10]);
});

console.log(`preview-layout.test.js — ${n} tests OK`);
