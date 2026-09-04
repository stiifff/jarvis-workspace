// Tests de la lógica pura de AgentSemaphore (agent-semaphore.js): conteo por estado.
'use strict';
const assert = require('assert');
require('../agent-semaphore.js');
const { resumir } = globalThis.AgentSemaphore._pure;

// thinking→trabajando, watching→esperando, error→error, idle/otros no cuentan
assert.deepStrictEqual(
  resumir({ 1: 'thinking', 2: 'thinking', 3: 'watching', 4: 'error', 5: 'idle' }),
  { trabajando: 2, esperando: 1, error: 1 },
);

// vacío
assert.deepStrictEqual(resumir({}), { trabajando: 0, esperando: 0, error: 0 });
assert.deepStrictEqual(resumir(null), { trabajando: 0, esperando: 0, error: 0 });

// idle no cuenta
assert.deepStrictEqual(resumir({ 1: 'idle', 2: 'idle' }), { trabajando: 0, esperando: 0, error: 0 });

// acepta Map además de objeto
const m = new Map([[1, 'thinking'], [2, 'error']]);
assert.deepStrictEqual(resumir(m), { trabajando: 1, esperando: 0, error: 1 });

// estados desconocidos no cuentan
assert.deepStrictEqual(resumir({ 1: 'banana' }), { trabajando: 0, esperando: 0, error: 0 });

console.log('agent-semaphore: OK');
