'use strict';
// Test puro de la lógica que decide "en qué sección estoy" para la Rich Presence
// de Discord. El runtime (fetch/setInterval) NO se testea acá — solo el mapeo
// snapshot → clave de sección, que es la única parte con reglas.
const assert = require('node:assert');
const P = require('../presence.js');

const s = (o) => P.seccionDesde(o);

// Sin proyecto cargado (o snapshot vacío) → home.
assert.strictEqual(s({ hayProyecto: false }), 'home');
assert.strictEqual(s({}), 'home');
assert.strictEqual(s(null), 'home');

// Overlays full-screen ganan sobre el dock (están por ENCIMA en pantalla).
assert.strictEqual(s({ hayProyecto: true, settingsOpen: true }), 'settings');
// Una clave de un overlay que ya no existe no puede resucitar una sección
// (el Web Builder se eliminó el 2026-07-25): se ignora y manda el dock.
assert.strictEqual(s({ hayProyecto: true, webBuilderOpen: true }), 'terminals');

// Dock abierto → la pestaña activa es la sección.
assert.strictEqual(s({ hayProyecto: true, dockOpen: true, dockTab: 'preview' }), 'preview');
assert.strictEqual(s({ hayProyecto: true, dockOpen: true, dockTab: 'editor' }), 'editor');
assert.strictEqual(s({ hayProyecto: true, dockOpen: true, dockTab: 'jarvis' }), 'jarvis');

// Dock cerrado (o abierto sin pestaña) → el mosaico de terminales.
assert.strictEqual(s({ hayProyecto: true }), 'terminals');
assert.strictEqual(s({ hayProyecto: true, dockOpen: false, dockTab: 'preview' }), 'terminals');
assert.strictEqual(s({ hayProyecto: true, dockOpen: true, dockTab: null }), 'terminals');

// Los overlays ganan incluso con el dock abierto detrás.
assert.strictEqual(s({ hayProyecto: true, settingsOpen: true, dockOpen: true, dockTab: 'tasks' }), 'settings');

// ── debePostear: la vista VISIBLE es la autoridad de la tarjeta ──────────────
// El estado del presence es global last-writer-wins; con 2 clientes (browser +
// Jarvis app) con idiomas distintos, tiene que ganar el que el usuario está
// MIRANDO. Regla: oculto = mudo; visible = postea si cambió algo o si venció
// el heartbeat (re-aserción que pisa el estado viejo de otro cliente).
const d = (o) => P.debePostear(o);

// Página oculta → NUNCA postea (ni aunque haya cambios: no es lo que se mira).
assert.strictEqual(d({ visible: false, firma: 'a', ultimaFirma: 'b', ahora: 0, ultimoPost: 0 }), false);
assert.strictEqual(d({ visible: false, firma: 'a', ultimaFirma: null, ahora: 99999, ultimoPost: 0 }), false);

// Visible + cambió la firma → postea ya.
assert.strictEqual(d({ visible: true, firma: 'a', ultimaFirma: 'b', ahora: 0, ultimoPost: 0 }), true);
// Primer reporte (nunca posteó) → postea.
assert.strictEqual(d({ visible: true, firma: 'a', ultimaFirma: null, ahora: 0, ultimoPost: null }), true);

// Visible sin cambios: heartbeat. Antes del umbral no, después sí.
assert.strictEqual(d({ visible: true, firma: 'a', ultimaFirma: 'a', ahora: 4000, ultimoPost: 0 }), false);
assert.strictEqual(d({ visible: true, firma: 'a', ultimaFirma: 'a', ahora: 12000, ultimoPost: 0 }), true);
assert.strictEqual(d({ visible: true, firma: 'a', ultimaFirma: 'a', ahora: 20000, ultimoPost: 12000, heartbeatMs: 5000 }), true);
assert.strictEqual(d({ visible: true, firma: 'a', ultimaFirma: 'a', ahora: 14000, ultimoPost: 12000, heartbeatMs: 5000 }), false);

// `visible` ausente (entorno raro sin document) → se asume visible: nunca
// dejar de reportar en silencio.
assert.strictEqual(d({ firma: 'a', ultimaFirma: 'b', ahora: 0, ultimoPost: 0 }), true);

console.log('presence.test.js OK');
