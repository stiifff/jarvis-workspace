'use strict';
// Tests de la lógica pura de la pestaña Live (memoria).
// Corre con: node frontend/sections/memory/__tests__/live-state.test.js
const assert = require('assert');
const L = require('../live-state.js');

const snapA = {
  agentes: [
    { terminal_id: 10, nombre: 'Backend', tipo_ia: 'claude', estado: 'idle',
      archivos: [{ path: 'a.py', reads: 0, writes: 1, hace_s: 5, dueno: true }] },
    { terminal_id: 20, nombre: 'Frontend', tipo_ia: 'codex', estado: 'trabajando',
      archivos: [] },
  ],
  permisos: [],
  actividad: [],
};

// ── aplicarSnapshot: primera vez no flashea (es la foto inicial) ──
let st = L.aplicarSnapshot(L.crearEstado(), snapA, 1000);
assert.strictEqual(st.agentes.length, 2);
assert.deepStrictEqual(L.flashesVigentes(st, 1000), [], 'snapshot inicial sin flashes');

// ── write nuevo → flash de ese path ───────────────────────────────
const snapB = JSON.parse(JSON.stringify(snapA));
snapB.agentes[0].archivos[0].writes = 2;
st = L.aplicarSnapshot(st, snapB, 2000);
assert.deepStrictEqual(L.flashesVigentes(st, 2000), ['a.py'], 'write nuevo flashea');

// ── archivo nuevo → flash ─────────────────────────────────────────
const snapC = JSON.parse(JSON.stringify(snapB));
snapC.agentes[1].archivos.push({ path: 'b.js', reads: 0, writes: 1, hace_s: 0, dueno: true });
st = L.aplicarSnapshot(st, snapC, 3000);
assert.ok(L.flashesVigentes(st, 3000).includes('b.js'), 'archivo nuevo flashea');

// ── flashes expiran a los FLASH_MS ────────────────────────────────
assert.deepStrictEqual(L.flashesVigentes(st, 3000 + L.FLASH_MS + 1), [], 'flash expira');

// ── snapshot igual → sin flashes nuevos ───────────────────────────
st = L.aplicarSnapshot(st, snapC, 9000);
assert.deepStrictEqual(L.flashesVigentes(st, 9000), [], 'sin cambios, sin flash');

// ── ordenarAgentes: trabajando primero, después por nombre ───────
const orden = L.ordenarAgentes(snapA.agentes).map(a => a.nombre);
assert.deepStrictEqual(orden, ['Frontend', 'Backend'], 'trabajando primero');

// ── hace(): formato humano ────────────────────────────────────────
assert.strictEqual(L.hace(40), '40s');
assert.strictEqual(L.hace(130), '2m');
assert.strictEqual(L.hace(7300), '2h');

// ── los flashes vencidos se podan del estado al aplicar otro snapshot ──
st = L.aplicarSnapshot(st, snapC, 99999);
assert.deepStrictEqual(Object.keys(st.flashes), [], 'flashes vencidos podados');

console.log('live-state.test.js OK');
