'use strict';
// Tests de la decisión PURA del foco de teclado por hover (el Enter va a la
// terminal que estás mirando, sin clickearla).
// Corre con: node frontend/shell/__tests__/foco-hover.test.js
const assert = require('assert');
const { decidirFocoPorHover, GRACIA_TIPEO_MS } = require('../foco-hover.js')._pure;

const base = {
  hoverTermId:        7,
  foco:               'libre',
  focoTermId:         null,
  desdeUltimaTeclaMs: 99999,
};
const d = (over) => decidirFocoPorHover({ ...base, ...over });

// ── El caso del pedido: dejaste texto en una terminal, ponés el mouse encima
//    y apretás Enter. Sin click, el foco tiene que estar ahí.
assert.strictEqual(d({}), 7);
// Viniendo de otra terminal (sin tipeo reciente) también se muda.
assert.strictEqual(d({ foco: 'terminal', focoTermId: 3 }), 7);

// ── Sin cursor sobre ninguna terminal: no se toca el foco ─────────
// (el foco NO vuelve al vacío al salir: seguís tipeándole a la última)
assert.strictEqual(d({ hoverTermId: null }), null);
assert.strictEqual(d({ hoverTermId: null, foco: 'terminal', focoTermId: 3 }), null);

// ── Nunca robarle el foco a un campo de texto ─────────────────────
// Composer de Jarvis, editor Monaco, inputs, iframes: aunque el mouse
// descanse sobre una terminal, lo que tipeás sigue yendo donde estabas.
assert.strictEqual(d({ foco: 'editable' }), null);

// ── Tipeando en OTRA terminal: gracia antes de mudar el foco ──────
// Movés el mouse mientras escribís un comando → las teclas siguientes NO se
// van a la terminal de al lado.
assert.strictEqual(d({ foco: 'terminal', focoTermId: 3, desdeUltimaTeclaMs: 0 }), null);
assert.strictEqual(d({ foco: 'terminal', focoTermId: 3, desdeUltimaTeclaMs: GRACIA_TIPEO_MS - 1 }), null);
// Pasada la gracia (dejaste de tipear), el mouse manda de nuevo.
assert.strictEqual(d({ foco: 'terminal', focoTermId: 3, desdeUltimaTeclaMs: GRACIA_TIPEO_MS }), 7);
// Tipeo reciente en la MISMA terminal que el cursor: ya está enfocada, no-op.
assert.strictEqual(d({ foco: 'terminal', focoTermId: 7, desdeUltimaTeclaMs: 0 }), null);

// ── Gracia razonable: filtra el tipeo en curso sin volverse pegajosa ──
assert.ok(GRACIA_TIPEO_MS >= 500 && GRACIA_TIPEO_MS <= 1500, 'gracia fuera de rango razonable');

console.log('✓ foco-hover: el teclado sigue al mouse (con guardas) OK');
