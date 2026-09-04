'use strict';
// Tests del ECO LOCAL predictivo: pinta la tecla del usuario al instante (0ms,
// local, como el kernel en una terminal nativa) y reconcilia con el eco real.
// Funciona en shells, donde el eco es el char tal cual → coincide con la
// predicción → se saltea (no se pinta dos veces).
//
// PERO el shell (readline) NO siempre hace "eco lineal": al navegar el historial
// (↑/↓), editar en el medio de la línea o envolver una línea larga, REDIBUJA con
// movimientos RELATIVOS de cursor (\b, \x1b[C…). Si dejáramos un char predicho
// pintado (con su avance de cursor) cuando llega uno de esos redibujos, el cursor
// queda 1 columna corrido y cada redibujo "come" una letra, acumulando garble
// (bug del historial, 2026-07-06). Por eso:
//   - conciliar() devuelve `undo` = cuántos chars predichos SIN confirmar hay que
//     despintar antes de dejar pasar un output que NO es su eco.
//   - flush() despinta TODO lo pendiente y devuelve el conteo (el caller lo usa
//     antes de mandar una tecla no imprimible: flechas/enter/backspace/ctrl…).
// El wiring con xterm (write local / saltear bytes / secuencia de borrado) vive
// en terminal.js.
const assert = require('node:assert');
const E = require('../terminal-eco-local.js');

// ─── predecir: char imprimible de 1 code unit (ASCII + BMP: acentos/ñ); nada de control ───
const e = E.crearEcoLocal({ maxPendientes: 8 });
assert.strictEqual(e.predecir('a'), true);
assert.strictEqual(e.predecir('Z'), true);
assert.strictEqual(e.pendientesN(), 2);
assert.strictEqual(e.predecir('\r'), false);       // enter
assert.strictEqual(e.predecir('\x7f'), false);     // backspace (DEL)
assert.strictEqual(e.predecir('\x1b'), false);     // escape (secuencias)
assert.strictEqual(e.predecir('\x9f'), false);     // C1 control
assert.strictEqual(e.predecir('́'), false);   // combining mark (no se predice sola)
assert.strictEqual(e.predecir('ñ'), true);         // acento español (Latin-1, 1 code unit) → SÍ
assert.strictEqual(e.predecir('á'), true);         // idem
assert.strictEqual(e.predecir('ab'), false);       // más de un char
assert.strictEqual(e.pendientesN(), 4);            // a, Z, ñ, á

// ─── SHELL: el eco coincide (incluidos acentos) → esos bytes ya están pintados ──
let r = e.conciliar('aZñá');
assert.deepStrictEqual(r, { saltear: 4, undo: 0 });
assert.strictEqual(e.pendientesN(), 0);

// ─── eco partido en dos chunks: cada parte consume su predicción (sin undo) ─────
e.predecir('h'); e.predecir('i');
r = e.conciliar('h');
assert.deepStrictEqual(r, { saltear: 1, undo: 0 });
assert.strictEqual(e.pendientesN(), 1);
r = e.conciliar('i');
assert.deepStrictEqual(r, { saltear: 1, undo: 0 });
assert.strictEqual(e.pendientesN(), 0);

// ─── sin pendientes (flood del agente) → no toca nada ─────────────────────────
assert.deepStrictEqual(e.conciliar('output del agente'), { saltear: 0, undo: 0 });

// ─── prefijo coincide y sigue más output relacionado: sólo se saltea lo predicho ─
e.predecir('x');
r = e.conciliar('xyz');                            // 'x' es el eco; 'yz' no había predicción
assert.deepStrictEqual(r, { saltear: 1, undo: 0 });
assert.strictEqual(e.pendientesN(), 0);

// ─── SHELL REDIBUJA (historial ↑/↓, wrap): el output NO es el eco simple del char
//     predicho → hay que BORRAR el char pintado (undo) para que el redibujo caiga
//     sobre un cursor sincronizado. saltear = lo que coincidió (0 acá). ──────────
e.predecir('q');
r = e.conciliar('\r\x1b[K> NO');                   // redibujo de la línea, no 'q'
assert.deepStrictEqual(r, { saltear: 0, undo: 1 });
assert.strictEqual(e.pendientesN(), 0);            // soltadas: el redibujo manda

// ─── desajuste tras coincidencia parcial: saltea lo confirmado, BORRA el resto ──
e.predecir('a'); e.predecir('b');
r = e.conciliar('aX');                             // 'a' coincide (confirmada), 'b' no
assert.deepStrictEqual(r, { saltear: 1, undo: 1 }); // saltear 'a', despintar 'b'
assert.strictEqual(e.pendientesN(), 0);

// ─── flush(): despinta TODO lo pendiente y devuelve el conteo (para el caller,
//     antes de mandar una tecla no imprimible: flechas/enter/backspace/ctrl…) ────
const f = E.crearEcoLocal({ maxPendientes: 8 });
f.predecir('t'); f.predecir('x');
assert.strictEqual(f.flush(), 2);
assert.strictEqual(f.pendientesN(), 0);
assert.strictEqual(f.flush(), 0);                  // idempotente sin pendientes

// ─── REGRESIÓN (el historial ↑/↓ "comía una letra del nombre"): sin predicciones
//     pendientes, un recall de TEXTO PLANO ('tput cols', como emite readline en
//     una línea vacía) NO pierde su primer byte. El fix real es que flush() corre
//     al presionar ↑ (terminal.js), así que acá pendientes ya está vacío. ────────
const g = E.crearEcoLocal({ maxPendientes: 8 });
assert.deepStrictEqual(g.conciliar('tput cols'), { saltear: 0, undo: 0 });

// ─── maxPendientes: no acumular sin confirmar más allá de la cota ─────────────
const c = E.crearEcoLocal({ maxPendientes: 3 });
assert.strictEqual(c.predecir('1'), true);
assert.strictEqual(c.predecir('2'), true);
assert.strictEqual(c.predecir('3'), true);
assert.strictEqual(c.predecir('4'), false);       // cota llena → no predice más
assert.strictEqual(c.pendientesN(), 3);

console.log('OK terminal-eco-local');
