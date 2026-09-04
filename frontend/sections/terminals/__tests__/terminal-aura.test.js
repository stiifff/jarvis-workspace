// Tests de la lógica pura de TerminalAura (terminal-aura.js).
// Aura de notificación en cards: prende con los mismos eventos que suenan,
// no prende si la card es la activa, se apaga por acción explícita.
'use strict';
const assert = require('assert');
require('../terminal-aura.js');
const { nextSet, PRENDEN } = globalThis.TerminalAura._pure;

// prende con los mismos eventos que disparan sonido (+ mailbox_aviso: "tenés
// mensaje", aura sutil sin sonido — la enciende el WS mailbox_aviso del backend)
for (const ev of ['agente_termino', 'agente_espera', 'TASK_DONE', 'TASK_BLOCKED', 'TASK_ERROR', 'mailbox_aviso']) {
  const s = nextSet(new Set(), { tipo: 'evento', evento: ev, terminalId: 7, activaId: null });
  assert.ok(s.has(7), `prende con ${ev}`);
  assert.ok(PRENDEN.has(ev), `${ev} está en PRENDEN`);
}

// NO prende si la card es la activa (estás parado ahí)
assert.ok(!nextSet(new Set(), { tipo: 'evento', evento: 'agente_termino', terminalId: 7, activaId: 7 }).has(7),
  'card activa no prende');

// NO prende sin terminal_id ni con eventos desconocidos
assert.strictEqual(nextSet(new Set(), { tipo: 'evento', evento: 'agente_termino', terminalId: null, activaId: null }).size, 0,
  'sin terminal_id no prende');
assert.strictEqual(nextSet(new Set(), { tipo: 'evento', evento: 'TASK_PROGRESS', terminalId: 7, activaId: null }).size, 0,
  'evento desconocido no prende');

// apagar saca el id; apagar uno inexistente no rompe
assert.ok(!nextSet(new Set([7]), { tipo: 'apagar', terminalId: 7 }).has(7), 'apagar saca el id');
assert.strictEqual(nextSet(new Set([7]), { tipo: 'apagar', terminalId: 9 }).size, 1, 'apagar id ajeno no toca');

// varias terminales con aura a la vez
let s = new Set();
s = nextSet(s, { tipo: 'evento', evento: 'TASK_DONE', terminalId: 1, activaId: null });
s = nextSet(s, { tipo: 'evento', evento: 'agente_espera', terminalId: 2, activaId: null });
assert.strictEqual(s.size, 2, 'dos auras simultáneas');

// reset vacía (cambio de proyecto)
assert.strictEqual(nextSet(new Set([1, 2]), { tipo: 'reset' }).size, 0, 'reset vacía');

// inmutabilidad: el set de entrada no se muta
const orig = new Set([1]);
nextSet(orig, { tipo: 'evento', evento: 'TASK_DONE', terminalId: 2, activaId: null });
nextSet(orig, { tipo: 'apagar', terminalId: 1 });
assert.strictEqual(orig.size, 1, 'el set original no se muta');

console.log('terminal-aura: OK');
