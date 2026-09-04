// Tests de la lógica pura de WsStatus (ws-status.js): backoff exponencial.
'use strict';
const assert = require('assert');
require('../ws-status.js');
const { proximoDelay } = globalThis.WsStatus._pure;

assert.strictEqual(proximoDelay(0), 1500,  '1er intento: 1.5s');
assert.strictEqual(proximoDelay(1), 3000,  '2do: 3s');
assert.strictEqual(proximoDelay(2), 6000,  '3ro: 6s');
assert.strictEqual(proximoDelay(3), 12000, '4to: 12s');
assert.strictEqual(proximoDelay(4), 24000, '5to: 24s');
assert.strictEqual(proximoDelay(5), 30000, '6to: cap a 30s');
assert.strictEqual(proximoDelay(10), 30000, 'sigue capeado a 30s');
assert.strictEqual(proximoDelay(-5), 1500, 'negativo → mínimo 1.5s');

console.log('ws-status: OK');
