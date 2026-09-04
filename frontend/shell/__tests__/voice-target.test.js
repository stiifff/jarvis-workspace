'use strict';
// Tests de la resolución PURA del destino de la voz (a quién le va el dictado).
// Corre con: node frontend/shell/__tests__/voice-target.test.js
const assert = require('assert');
const { resolverDestinoVoz, HOVER_DWELL_MS } = require('../voice-target.js')._pure;

const base = {
  proyectoAbierto: true,
  jarvisVisible:   false,
  fijado:          { type: 'jarvis' },
  hover:           null,
  terminales:      [1, 2, 3],
  activaId:        null,
  focoJarvis:      false,
};
const r = (over) => resolverDestinoVoz({ ...base, ...over });

// ── Sin workspace abierto no hay destino ──────────────────────────
assert.strictEqual(r({ proyectoAbierto: false }), null);
assert.strictEqual(r({ proyectoAbierto: false, hover: { type: 'terminal', id: 2 } }), null);

// ── HOVER manda: la terminal bajo el cursor se queda con la voz ───
// (el pedido: no hace falta clickearla, alcanza con tener el mouse encima)
assert.deepStrictEqual(r({ hover: { type: 'terminal', id: 2 } }), { type: 'terminal', id: 2 });
// Gana incluso si el "fijado" (último click/dwell) apuntaba a OTRA terminal.
assert.deepStrictEqual(r({ hover: { type: 'terminal', id: 3 }, fijado: { type: 'terminal', id: 1 } }),
                       { type: 'terminal', id: 3 });
// Y gana con Jarvis a la vista: el cursor sobre la terminal es intención explícita.
assert.deepStrictEqual(r({ hover: { type: 'terminal', id: 1 }, jarvisVisible: true }),
                       { type: 'terminal', id: 1 });
// Hover sobre una terminal que ya no existe → se ignora (no inventa destino muerto).
assert.deepStrictEqual(r({ hover: { type: 'terminal', id: 99 }, jarvisVisible: true }), { type: 'jarvis' });
// Cursor sobre el panel de Jarvis → Jarvis, aunque el fijado sea una terminal.
assert.deepStrictEqual(r({ hover: { type: 'jarvis' }, fijado: { type: 'terminal', id: 1 } }), { type: 'jarvis' });

// ── Escribiendo en el chat de Jarvis ──────────────────────────────
// Con el cursor FUERA de toda terminal, el foco en el composer manda: el
// dictado anexa a lo que estás tipeando ahí.
assert.deepStrictEqual(r({ focoJarvis: true, fijado: { type: 'terminal', id: 1 } }), { type: 'jarvis' });
// Pero el cursor sobre una terminal gana igual: el foco es un estado pegajoso
// (clickeaste el chat hace rato), el mouse encima de la card es intención de
// ahora — y es lo que el usuario pidió explícitamente.
assert.deepStrictEqual(r({ focoJarvis: true, hover: { type: 'terminal', id: 2 } }), { type: 'terminal', id: 2 });

// ── Sticky: sin cursor sobre nada, vale el último apuntado ────────
assert.deepStrictEqual(r({ fijado: { type: 'terminal', id: 2 } }), { type: 'terminal', id: 2 });
// Terminal fijada que murió → NO se manda al vacío; cae a los fallbacks.
assert.deepStrictEqual(r({ fijado: { type: 'terminal', id: 9 }, jarvisVisible: true }), { type: 'jarvis' });
assert.deepStrictEqual(r({ fijado: { type: 'terminal', id: 9 }, activaId: 3 }), { type: 'terminal', id: 3 });

// ── Fijado en Jarvis ──────────────────────────────────────────────
// Con el chat a la vista, la voz es suya.
assert.deepStrictEqual(r({ jarvisVisible: true }), { type: 'jarvis' });
// Jarvis OCULTO: la terminal activa (última clickeada) se queda con la voz.
assert.deepStrictEqual(r({ activaId: 2 }), { type: 'terminal', id: 2 });
// Activa que ya no existe → no la usa.
assert.deepStrictEqual(r({ activaId: 77, terminales: [1] }), { type: 'terminal', id: 1 });

// ── Fallbacks cuando nadie apuntó nada ────────────────────────────
// Proyecto en pantalla de arranque (sin terminales) → Jarvis manos libres.
assert.deepStrictEqual(r({ terminales: [] }), { type: 'jarvis', manosLibres: true });
// UNA sola terminal: no hay ambigüedad posible, va ahí (antes: "seleccioná una").
assert.deepStrictEqual(r({ terminales: [7] }), { type: 'terminal', id: 7 });
// Varias terminales y ninguna referencia (ni hover, ni click, ni activa) → sin destino.
assert.strictEqual(r({}), null);

// ── Dwell del hover ───────────────────────────────────────────────
// Existe y es corto: pasar de largo no debe dejar el destino pegado, pero
// apuntar y hablar tiene que sentirse inmediato.
assert.ok(HOVER_DWELL_MS >= 100 && HOVER_DWELL_MS <= 400, 'dwell fuera de rango razonable');

console.log('✓ voice-target: destino de la voz por hover/click/foco OK');
