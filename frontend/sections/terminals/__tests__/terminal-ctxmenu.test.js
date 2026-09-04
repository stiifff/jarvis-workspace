'use strict';
// Tests del ciclo de vida del cierre del menú contextual de terminales.
// Bug histórico (regresión cubierta acá): los listeners de cierre sobre
// document usaban {once:true}, así que el PRIMER mousedown en cualquier lado
// los consumía aunque NO cerrara el menú (p.ej. mousedown dentro del menú,
// en el padding, o apretar un ítem y soltar afuera) → el menú quedaba clavado
// para siempre. El contrato nuevo: listeners PERSISTENTES mientras el menú
// viva, desarmados explícitamente al cerrar.
// Corre con: node frontend/sections/terminals/__tests__/terminal-ctxmenu.test.js
const assert = require('assert');
const M = require('../terminal-ctxmenu.js');

// ── Stubs mínimos de DOM ──────────────────────────────────────────
function docStub() {
  const listeners = { mousedown: [], keydown: [] };
  return {
    listeners,
    addEventListener(tipo, fn, opts) { listeners[tipo].push({ fn, opts }); },
    removeEventListener(tipo, fn) {
      listeners[tipo] = listeners[tipo].filter(l => l.fn !== fn);
    },
    // Copia defensiva: un listener puede desarmarse a sí mismo durante el dispatch.
    dispatch(tipo, ev) { for (const l of [...listeners[tipo]]) l.fn(ev); },
  };
}
const DENTRO = { soy: 'boton del menu' };
const AFUERA = { soy: 'otro lado' };
const menuStub = () => ({ contains: t => t === DENTRO });

// Glue como en terminal.js: cerrar() desarma y marca cerrado.
function armar() {
  const doc = docStub();
  let cerrado = 0;
  const desarmar = M.armarCierre(doc, menuStub(), () => { cerrado++; desarmar(); });
  return { doc, desarmar, cerrados: () => cerrado };
}

// ── mousedown DENTRO del menú NO cierra y el listener SIGUE vivo ──
{
  const { doc, cerrados } = armar();
  doc.dispatch('mousedown', { target: DENTRO });
  assert.strictEqual(cerrados(), 0, 'mousedown dentro no cierra');
  assert.strictEqual(doc.listeners.mousedown.length, 1, 'listener sobrevive (regresión {once:true})');
  // …y un mousedown afuera DESPUÉS sigue cerrando
  doc.dispatch('mousedown', { target: AFUERA });
  assert.strictEqual(cerrados(), 1, 'mousedown afuera posterior cierra');
}
console.log('OK mousedown dentro no consume el cierre');

// ── tecla no-Escape NO cierra y Escape DESPUÉS sigue cerrando ─────
{
  const { doc, cerrados } = armar();
  doc.dispatch('keydown', { key: 'a' });
  doc.dispatch('keydown', { key: 'ArrowDown' });
  assert.strictEqual(cerrados(), 0, 'teclas comunes no cierran');
  assert.strictEqual(doc.listeners.keydown.length, 1, 'listener de teclado sobrevive');
  doc.dispatch('keydown', { key: 'Escape' });
  assert.strictEqual(cerrados(), 1, 'Escape posterior cierra');
}
console.log('OK teclas comunes no consumen el Escape');

// ── mousedown afuera cierra directo ───────────────────────────────
{
  const { doc, cerrados } = armar();
  doc.dispatch('mousedown', { target: AFUERA });
  assert.strictEqual(cerrados(), 1, 'mousedown afuera cierra');
}
console.log('OK mousedown afuera cierra');

// ── al cerrar se desarman AMBOS listeners (sin leaks ni doble cierre) ──
{
  const { doc, cerrados } = armar();
  doc.dispatch('mousedown', { target: AFUERA });
  assert.strictEqual(doc.listeners.mousedown.length, 0, 'mousedown desarmado tras cerrar');
  assert.strictEqual(doc.listeners.keydown.length, 0, 'keydown desarmado tras cerrar');
  doc.dispatch('mousedown', { target: AFUERA });
  doc.dispatch('keydown', { key: 'Escape' });
  assert.strictEqual(cerrados(), 1, 'cerrar no se dispara de nuevo tras desarmar');
}
console.log('OK desarmar limpia ambos listeners');

// ── desarmar() manual (menú cerrado por otra vía, p.ej. click en ítem) ──
{
  const { doc, desarmar, cerrados } = armar();
  desarmar();
  assert.strictEqual(doc.listeners.mousedown.length, 0, 'sin listener mousedown tras desarmar');
  assert.strictEqual(doc.listeners.keydown.length, 0, 'sin listener keydown tras desarmar');
  doc.dispatch('mousedown', { target: AFUERA });
  assert.strictEqual(cerrados(), 0, 'listeners desarmados no cierran nada');
}
console.log('OK desarmar manual');

// ── capture-phase: que un stopPropagation en burbuja no nos deje ciegos ──
{
  const { doc } = armar();
  for (const tipo of ['mousedown', 'keydown']) {
    const opts = doc.listeners[tipo][0].opts;
    assert.ok(opts === true || (opts && opts.capture === true), `${tipo} en capture`);
  }
}
console.log('OK listeners en capture-phase');

console.log('terminal-ctxmenu: todos los tests OK');
