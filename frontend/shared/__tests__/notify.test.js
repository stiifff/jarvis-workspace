// Tests de la lógica pura de JarvisNotify (notify.js): título flash + gating.
'use strict';
const assert = require('assert');
require('../notify.js');
const { tituloFlash, debeAvisar, debeOsNotif } = globalThis.JarvisNotify._pure;

// ── tituloFlash ──
assert.strictEqual(tituloFlash('Jarvis', 0, true), 'Jarvis', 'sin pendientes: título base');
assert.strictEqual(tituloFlash('Jarvis', 2, false), 'Jarvis', 'fase no-alterna: título base');
assert.strictEqual(tituloFlash('Jarvis', 2, true), '🔔 (2) Jarvis', 'pendientes + alterno: con badge');
assert.strictEqual(tituloFlash('Jarvis', -1, true), 'Jarvis', 'n negativo: base');

// ── debeAvisar: solo si oculta y sonido no silenciado ──
assert.strictEqual(debeAvisar({ hidden: true, sonidoOn: true }), true);
assert.strictEqual(debeAvisar({ hidden: true, sonidoOn: undefined }), true, 'default no silenciado');
assert.strictEqual(debeAvisar({ hidden: false, sonidoOn: true }), false, 'pestaña visible: no');
assert.strictEqual(debeAvisar({ hidden: true, sonidoOn: false }), false, 'silenciado: no');

// ── debeOsNotif: permiso concedido + opt-in ──
assert.strictEqual(debeOsNotif({ permiso: 'granted', osOptIn: true }), true);
assert.strictEqual(debeOsNotif({ permiso: 'granted', osOptIn: false }), false, 'sin opt-in: no');
assert.strictEqual(debeOsNotif({ permiso: 'default', osOptIn: true }), false, 'sin permiso: no');
assert.strictEqual(debeOsNotif({ permiso: 'denied', osOptIn: true }), false);

console.log('notify: OK');
