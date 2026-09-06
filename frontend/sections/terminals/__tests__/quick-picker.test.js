'use strict';
const assert = require('node:assert');
const Q = require('../quick-picker.js');

assert.strictEqual(Q.OPCIONES.length, 9);
assert.deepStrictEqual(Q.OPCIONES.map(o => o.tipo),
  ['claude', 'codex', 'opencode', 'qwen', 'antigravity', 'grok', 'cursor', 'pi', 'manual']);
assert.strictEqual(Q.opcionPorTecla('1').tipo, 'claude');
assert.strictEqual(Q.opcionPorTecla('5').tipo, 'antigravity');
assert.strictEqual(Q.opcionPorTecla('6').tipo, 'grok');
assert.strictEqual(Q.opcionPorTecla('7').tipo, 'cursor');
assert.strictEqual(Q.opcionPorTecla('8').tipo, 'pi');
assert.strictEqual(Q.opcionPorTecla('9').tipo, 'manual');
assert.strictEqual(Q.opcionPorTecla('10'), null);
assert.strictEqual(Q.opcionPorTecla('x'), null);
// indicePorDigito: 'DigitN' → índice en OPCIONES; el resto → null
assert.strictEqual(Q.indicePorDigito('Digit7'), 6);
assert.strictEqual(Q.indicePorDigito('Digit9'), 8);
assert.strictEqual(Q.indicePorDigito('Digit0'), -1);   // fuera de rango: el keydown corta
assert.strictEqual(Q.indicePorDigito('KeyA'), null);
assert.strictEqual(Q.indicePorDigito(''), null);
assert.strictEqual(Q.indicePorDigito(null), null);
// navegación circular con flechas
assert.strictEqual(Q.moverSeleccion(0, 1, 5), 1);
assert.strictEqual(Q.moverSeleccion(4, 1, 5), 0);
assert.strictEqual(Q.moverSeleccion(0, -1, 5), 4);
// focoBloqueaAtajo: ¿el elemento enfocado debe bloquear el atajo Ctrl+\?
const clsList = (...cs) => ({ contains: (c) => cs.includes(c) });
assert.strictEqual(Q.focoBloqueaAtajo(null), false);
assert.strictEqual(Q.focoBloqueaAtajo(undefined), false);
assert.strictEqual(Q.focoBloqueaAtajo({ tagName: 'BODY', classList: clsList() }), false);
assert.strictEqual(Q.focoBloqueaAtajo({ tagName: 'INPUT', classList: clsList() }), true);
assert.strictEqual(Q.focoBloqueaAtajo({ tagName: 'TEXTAREA', classList: clsList() }), true);
// el textarea oculto de xterm NO bloquea: el atajo debe correr con foco en una terminal
assert.strictEqual(Q.focoBloqueaAtajo({ tagName: 'TEXTAREA', classList: clsList('xterm-helper-textarea') }), false);
assert.strictEqual(Q.focoBloqueaAtajo({ tagName: 'DIV', classList: clsList(), isContentEditable: true }), true);
// elemento sin classList (defensivo) sigue funcionando
assert.strictEqual(Q.focoBloqueaAtajo({ tagName: 'INPUT' }), true);

// ─── cantidad (stepper global del picker) ───────────────────────────────────
// clampCantidad: acota entre 1 y el cupo libre (mínimo 1 aunque no haya cupo:
// el guard de "ya estás lleno" vive ANTES de abrir el picker, en workspace.js)
assert.strictEqual(Q.clampCantidad(3, 8), 3);
assert.strictEqual(Q.clampCantidad(0, 8), 1);
assert.strictEqual(Q.clampCantidad(-2, 8), 1);
assert.strictEqual(Q.clampCantidad(99, 4), 4);
assert.strictEqual(Q.clampCantidad(2, 0), 1);
assert.strictEqual(Q.clampCantidad(2, undefined), 1);
assert.strictEqual(Q.clampCantidad(NaN, 8), 1);
// deltaCantidadPorTecla: ←/− bajan, →/+ suben, el resto no toca
assert.strictEqual(Q.deltaCantidadPorTecla('ArrowRight'), 1);
assert.strictEqual(Q.deltaCantidadPorTecla('+'), 1);
assert.strictEqual(Q.deltaCantidadPorTecla('ArrowLeft'), -1);
assert.strictEqual(Q.deltaCantidadPorTecla('-'), -1);
assert.strictEqual(Q.deltaCantidadPorTecla('ArrowDown'), 0);
assert.strictEqual(Q.deltaCantidadPorTecla('Enter'), 0);
assert.strictEqual(Q.deltaCantidadPorTecla('5'), 0);
console.log('quick-picker.test.js OK');

// ─── Tanda (contadores por CLI) + disposición (picker "Nueva terminal") ─────
// totalCounts: suma defensiva
assert.strictEqual(Q.totalCounts({}), 0);
assert.strictEqual(Q.totalCounts({ claude: 2, manual: 1 }), 3);
assert.strictEqual(Q.totalCounts(null), 0);
assert.strictEqual(Q.totalCounts({ claude: -3 }), 0);
// sumarCount: inmutable, respeta cupo, resta a 0 saca la clave
{
  const base = { claude: 1 };
  const mas = Q.sumarCount(base, 'codex', 1, 12);
  assert.deepStrictEqual(mas, { claude: 1, codex: 1 });
  assert.deepStrictEqual(base, { claude: 1 });                     // inmutable
  assert.deepStrictEqual(Q.sumarCount({ claude: 1 }, 'claude', -1, 12), {});
  assert.deepStrictEqual(Q.sumarCount({ claude: 2 }, 'codex', 1, 2), { claude: 2 });  // cupo lleno: no suma
  assert.deepStrictEqual(Q.sumarCount({ claude: 2 }, 'claude', -1, 2), { claude: 1 }); // restar siempre se puede
  assert.deepStrictEqual(Q.sumarCount({}, 'qwen', -1, 5), {});     // restar de 0 = no-op
}
// autoCells: canónico vertical (≤6 una fila; 7..12 dos filas, abajo capada en 3, top-fill)
{
  const a1 = Q.autoCells(1);
  assert.strictEqual(a1.length, 1);
  assert.strictEqual(a1[0].w, 1);
  const a4 = Q.autoCells(4);
  assert.strictEqual(a4.length, 4);
  assert.ok(a4.every(c => c.h === 1));                              // una sola fila
  const a7 = Q.autoCells(7);                                        // 7 → [6,1]
  assert.strictEqual(a7.filter(c => c.y === 0).length, 6);
  assert.strictEqual(a7.filter(c => c.y === 0.5).length, 1);
  const a9 = Q.autoCells(9);                                        // 9 → [6,3]
  assert.strictEqual(a9.filter(c => c.y === 0).length, 6);
  assert.strictEqual(a9.filter(c => c.y === 0.5).length, 3);
  const a10 = Q.autoCells(10);                                      // 10 → [7,3]
  assert.strictEqual(a10.filter(c => c.y === 0).length, 7);
  assert.deepStrictEqual(Q.autoDesc(5), { filas: [5] });
  assert.deepStrictEqual(Q.autoDesc(8), { filas: [6, 2] });
}
// cellsEq: igualdad con epsilon
assert.ok(Q.cellsEq([{ x: 0, y: 0, w: 1, h: 1 }], [{ x: 0.005, y: 0, w: 0.996, h: 1 }]));
assert.ok(!Q.cellsEq([{ x: 0, y: 0, w: 1, h: 1 }], [{ x: 0.5, y: 0, w: 0.5, h: 1 }]));
assert.ok(!Q.cellsEq([], [{ x: 0, y: 0, w: 1, h: 1 }]));
// tilesFor con el catálogo REAL de terminal-layout (mismo _pure que usa el browser):
// Auto primero, sin duplicados del Auto (para n≤6 el preset "cols" es idéntico → afuera),
// y "Principal + N" presente solo en 3..5.
{
  const TL = require('../terminal-layout.js');
  const t1 = Q.tilesFor(1, TL.snapPresets);
  assert.strictEqual(t1[0].key, 'auto');
  assert.ok(!t1.some(t => t.key === 'full'), '1: "Pantalla completa" duplica al Auto');
  const t4 = Q.tilesFor(4, TL.snapPresets);
  assert.ok(!t4.some(t => t.key === 'cols'), '4: "4 columnas" duplica al Auto');
  assert.ok(t4.some(t => t.key === 'main'), '4: falta Principal + 3');
  const t6 = Q.tilesFor(6, TL.snapPresets);
  assert.ok(!t6.some(t => t.key === 'main'), '6: Principal + N no existe con N>=6');
  const t9 = Q.tilesFor(9, TL.snapPresets);
  assert.ok(t9.length >= 4, '9: auto + catálogo');
  t9.forEach(t => assert.strictEqual(t.cells.length, 9, `9: preset ${t.key} no tesela 9`));
  // sin snapPresets (TerminalLayout ausente) el picker degrada a solo-Auto
  assert.deepStrictEqual(Q.tilesFor(3, undefined).map(t => t.key), ['auto']);
}
console.log('quick-picker.test.js (tanda+disposición) OK');
