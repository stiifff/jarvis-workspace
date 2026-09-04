'use strict';
// Tests de la lógica pura del toggle de la franja de proyectos.
// Corre con: node frontend/sections/panel/__tests__/strip.test.js
const assert = require('assert');
const S = require('../strip.js');

// toggle invierte
assert.strictEqual(S.nextStripHidden(false, 'toggle'), true,  'visible -> oculto');
assert.strictEqual(S.nextStripHidden(true,  'toggle'), false, 'oculto -> visible');
// show/hide fuerzan sin importar el estado actual
assert.strictEqual(S.nextStripHidden(true,  'show'), false, 'show fuerza visible');
assert.strictEqual(S.nextStripHidden(false, 'show'), false, 'show idempotente');
assert.strictEqual(S.nextStripHidden(false, 'hide'), true,  'hide fuerza oculto');
assert.strictEqual(S.nextStripHidden(true,  'hide'), true,  'hide idempotente');
// acción desconocida no cambia el estado
assert.strictEqual(S.nextStripHidden(false, 'wat'), false, 'acción rara no toca visible');
assert.strictEqual(S.nextStripHidden(true,  'wat'), true,  'acción rara no toca oculto');
console.log('OK nextStripHidden');

console.log('OK ALL');
