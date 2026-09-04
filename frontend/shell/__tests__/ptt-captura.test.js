'use strict';
// Test de la lógica pura de captura de bindings del PTT (frontend/shell/ptt-captura.js).
// Bug que motivó el módulo: apretar un botón del mouse ENCIMA del botón
// "tocá para reasignar" no bindeaba nada (el motor ignoraba todo mousedown que
// cayera sobre el propio botón), así que el usuario tenía que salirse del botón
// para asignar Mouse·adelante.

const assert = require('assert');
const PttCaptura = require('../ptt-captura.js');

const decision = (o) => PttCaptura.decisionMouse(o);

// ── 1. El caso del bug: botón no-primario ENCIMA del botón de reasignar ──
for (const button of [1, 2, 3, 4]) {
  assert.strictEqual(
    decision({ button, enBotonBind: true, enUiCaptura: false }), 'bindear',
    `botón ${button} sobre el propio botón de reasignar tiene que bindear`);
  assert.strictEqual(
    decision({ button, enBotonBind: false, enUiCaptura: false }), 'bindear',
    `botón ${button} fuera del botón sigue bindeando (no había regresión acá)`);
}

// ── 2. Ni el reset ni el cerrar se comen el binding de un botón lateral ──
assert.strictEqual(decision({ button: 4, enBotonBind: false, enUiCaptura: true }), 'bindear',
  'Mouse·adelante sobre el botón de reset igual se bindea');

// ── 3. El click IZQUIERDO sigue manejando la UI durante la captura ──
assert.strictEqual(decision({ button: 0, enBotonBind: false, enUiCaptura: true }), 'ignorar',
  'click izq sobre reset/cerrar: es la UI, no un binding');
assert.strictEqual(decision({ button: 0, enBotonBind: true, enUiCaptura: false }), 'ignorar',
  'click izq sobre el propio botón: es el click que abre/reabre la captura, no "bindeá click izq" ' +
  '(sin esto, un doble-click en "tocá para reasignar" dejaba el PTT en click izquierdo)');

// ── 4. Click izquierdo en cualquier otro lado SÍ se bindea (no cambió) ──
assert.strictEqual(decision({ button: 0, enBotonBind: false, enUiCaptura: false }), 'bindear',
  'click izq lejos de la UI de captura sigue siendo un binding válido');

// ── 5. Defaults tolerantes: sin flags de DOM, decide por el botón ──
assert.strictEqual(decision({ button: 4 }), 'bindear');
assert.strictEqual(decision({ button: 0 }), 'bindear');

// ── 6. Tragar los eventos que siguen al mousedown capturado ──
// Sin esto, el click que cierra el mousedown que acabamos de capturar le pega
// de nuevo al botón de reasignar y REABRE la captura.
assert.strictEqual(PttCaptura.debeTragar({ button: 0, capturado: true }), true,
  'ya capturamos: el mouseup/click de ESE mismo apretón se traga');
assert.strictEqual(PttCaptura.debeTragar({ button: 0, capturado: false }), false,
  'sin captura, el click izquierdo tiene que llegar a la UI');
assert.strictEqual(PttCaptura.debeTragar({ button: 3, capturado: false }), true,
  'los laterales se tragan siempre: sino el browser navega back/forward');
assert.strictEqual(PttCaptura.debeTragar({ button: 4, capturado: false }), true);
assert.strictEqual(PttCaptura.debeTragar({ button: 1, capturado: false }), false);

console.log('✓ ptt-captura: decisiones de captura de binding del mouse');
