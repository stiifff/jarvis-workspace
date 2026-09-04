'use strict';
// Tests del diagnóstico de GARBLE: compara el grid que tmux DIBUJA (la verdad)
// contra lo que xterm muestra en pantalla. Si difieren con tmux limpio, el daño
// está 100% en el render del browser (lo que el historial del proyecto ya
// confirmó) — y acá quedan las líneas EXACTAS que se rompieron, para cazar la
// causa en la GPU real del usuario en vez de adivinar.
const assert = require('node:assert');
const D = require('../terminal-diagnostico.js');

// ─── grids idénticos → sin garble ─────────────────────────────────────────────
let r = D.compararGrid(['hola', 'mundo'], ['hola', 'mundo']);
assert.strictEqual(r.iguales, true);
assert.deepStrictEqual(r.diferencias, []);

// ─── trailing spaces se ignoran (tmux rellena la fila con espacios) ───────────
r = D.compararGrid(['hola   ', 'mundo'], ['hola', 'mundo  ']);
assert.strictEqual(r.iguales, true);
assert.deepStrictEqual(r.diferencias, []);

// ─── una fila difiere → la marca con índice y ambos textos ────────────────────
r = D.compararGrid(['hola', 'XXrto'], ['hola', 'mundo']);
assert.strictEqual(r.iguales, false);
assert.strictEqual(r.diferencias.length, 1);
assert.deepStrictEqual(r.diferencias[0], { i: 1, x: 'XXrto', t: 'mundo' });

// ─── distinta cantidad de filas → compara hasta el máximo, la faltante como '' ─
r = D.compararGrid(['a'], ['a', 'b']);
assert.strictEqual(r.iguales, false);
assert.deepStrictEqual(r.diferencias[0], { i: 1, x: '', t: 'b' });

// ─── varias filas rotas → todas listadas ──────────────────────────────────────
r = D.compararGrid(['a', 'b', 'c'], ['a', 'X', 'Y']);
assert.strictEqual(r.diferencias.length, 2);
assert.deepStrictEqual(r.diferencias.map(d => d.i), [1, 2]);

// ─── entradas raras no rompen (defensivo) ─────────────────────────────────────
r = D.compararGrid(null, null);
assert.strictEqual(r.iguales, true);
r = D.compararGrid(['x'], null);
assert.strictEqual(r.iguales, false);

console.log('OK terminal-diagnostico');
