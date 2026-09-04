// Bienvenida: qué agentes tenés y cuáles se pueden instalar.
//
// Las dos reglas que estos tests protegen:
//  1. La pantalla aparece SOLO en un primer arranque de verdad. Una bienvenida
//     que sale siempre es una que se aprende a cerrar sin leer.
//  2. Nunca se ofrece un botón que no pueda cumplir: Antigravity no sale de
//     npm, y sin Node no hay con qué instalar nada.
const assert = require('assert');
global.window = globalThis;
require('../bienvenida.js');
const { debeMostrarse, accionDe } = globalThis.Bienvenida._pure;

// ── cuándo aparece ────────────────────────────────────────────────────────
assert.strictEqual(
  debeMostrarse({ clis: [{ instalado: false }, { instalado: false }] }), true,
  'sin ningún agente, la app tiene algo que decir');
assert.strictEqual(
  debeMostrarse({ clis: [{ instalado: true }, { instalado: false }] }), false,
  'con uno instalado ya se puede trabajar: no molestar');
assert.strictEqual(debeMostrarse({ clis: [] }), false, 'sin datos, no se muestra');
assert.strictEqual(debeMostrarse(null), false);
assert.strictEqual(debeMostrarse({}), false);

// ── qué se ofrece de cada uno ─────────────────────────────────────────────
assert.strictEqual(accionDe({ instalado: true, instalable: true }, true), 'listo');
assert.strictEqual(accionDe({ instalado: false, instalable: true }, true), 'instalar');
// Antigravity: app de escritorio de Google, no un paquete. Un botón que no
// puede cumplir es peor que una línea que lo explique.
assert.strictEqual(accionDe({ instalado: false, instalable: false }, true), 'aparte');
// Sin Node no hay npm: el botón sería una promesa vacía.
assert.strictEqual(accionDe({ instalado: false, instalable: true }, false), 'sin-node');
// Y lo ya instalado se muestra listo aunque no haya Node: no depende de npm.
assert.strictEqual(accionDe({ instalado: true, instalable: true }, false), 'listo');
assert.strictEqual(accionDe(null, true), 'nada');

console.log('bienvenida.test.js OK');
