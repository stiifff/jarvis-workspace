// Tests de la lógica pura del motor i18n. Corre con:
//   node frontend/shared/__tests__/i18n.test.js
'use strict';
const assert = require('assert');
const { _pure } = require('../i18n.js');
const { traducir, normalizar, partes } = _pure;

const DICT = { 'Nuevo proyecto': 'New project', 'Buscar…': 'Search…', 'Guardar': 'Save' };

// ── normalizar: colapsa espacios y recorta ──
assert.strictEqual(normalizar('  Nuevo   proyecto \n'), 'Nuevo proyecto');
assert.strictEqual(normalizar(''), '');
assert.strictEqual(normalizar(null), '');

// ── traducir: solo en inglés, contra el dict ──
assert.strictEqual(traducir('Nuevo proyecto', 'en', DICT), 'New project');
assert.strictEqual(traducir('  Nuevo   proyecto  ', 'en', DICT), 'New project', 'normaliza antes de buscar');
assert.strictEqual(traducir('Nuevo proyecto', 'es', DICT), null, 'en español no traduce');
assert.strictEqual(traducir('Inexistente', 'en', DICT), null, 'sin entrada → null');
assert.strictEqual(traducir('', 'en', DICT), null);
assert.strictEqual(traducir('Buscar…', 'en', DICT), 'Search…');
// Traducción igual al original → null (no hace falta tocar el DOM)
assert.strictEqual(traducir('Guardar', 'en', { 'Guardar': 'Guardar' }), null);

// ── partes: separa whitespace para conservar el que rodea al núcleo ──
let p = partes('\n  Crear cuenta  ');
assert.strictEqual(p.pre, '\n  ');
assert.strictEqual(p.core, 'Crear cuenta');
assert.strictEqual(p.post, '  ');
// Sin espacios alrededor
p = partes('Hola');
assert.strictEqual(p.pre, ''); assert.strictEqual(p.core, 'Hola'); assert.strictEqual(p.post, '');
// Reconstrucción exacta
['  x  ', 'y', '\t z\n', ''].forEach(v => {
  const q = partes(v);
  assert.strictEqual(q.pre + q.core + q.post, v, 'pre+core+post reconstruye el original');
});

console.log('i18n: OK');
