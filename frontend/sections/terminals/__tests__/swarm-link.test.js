// Tests de la lógica pura de SwarmLink (swarm-link.js).
// El ícono de vínculo en la card: cuándo aparece, de qué color, y qué dice.
//
// Regla que se está defendiendo acá: compartir archivo NO es una alerta (está
// medido que dos ediciones en zonas distintas conviven perfecto). La alerta es
// la colisión. Si el ícono grita cada vez que dos tocan el mismo archivo, en
// dos días se ignora y no sirve para nada.
'use strict';
const assert = require('assert');
require('../swarm-link.js');
const { grupoDe, estadoDeCard, companeros, tituloVinculo, diffEstados } =
  globalThis.SwarmLink._pure;

const G_CONV = {
  id: 'g1-2', estado: 'convergencia', archivos: ['builder.js'], simbolos: [],
  miembros: [{ tid: 1, nombre: 'Claude Code #1' }, { tid: 2, nombre: 'Claude Code #2' }],
};
const G_COL = { ...G_CONV, id: 'g3-4', estado: 'colision',
  miembros: [{ tid: 3, nombre: 'A' }, { tid: 4, nombre: 'B' }] };

// ─── grupoDe / estadoDeCard ───────────────────────────────────────────────────

assert.strictEqual(grupoDe([G_CONV], 1), G_CONV, 'encuentra su grupo');
assert.strictEqual(grupoDe([G_CONV], 9), null, 'ajeno al grupo → null');
assert.strictEqual(grupoDe([], 1), null, 'sin grupos → null');
assert.strictEqual(grupoDe(null, 1), null, 'null no rompe');

assert.strictEqual(estadoDeCard([G_CONV], 1), 'convergencia');
assert.strictEqual(estadoDeCard([G_COL], 3), 'colision');
assert.strictEqual(estadoDeCard([G_CONV], 9), null, 'sin vínculo → sin ícono');

// un grupo sin `estado` explícito NO se trata como alerta
assert.strictEqual(estadoDeCard([{ ...G_CONV, estado: undefined }], 1), 'convergencia',
  'ante la duda, informativo — nunca alarma');

// ─── companeros ───────────────────────────────────────────────────────────────

assert.deepStrictEqual(companeros(G_CONV, 1), ['Claude Code #2'], 'los otros, no vos');
assert.deepStrictEqual(companeros(null, 1), [], 'sin grupo → []');

const G3 = { ...G_CONV, miembros: [{ tid: 1, nombre: 'A' }, { tid: 2, nombre: 'B' },
                                    { tid: 3, nombre: 'C' }] };
assert.deepStrictEqual(companeros(G3, 2), ['A', 'C'], 'grupo de tres');

// ─── tituloVinculo: tiene que decir QUIÉN y DÓNDE ────────────────────────────

const t1 = tituloVinculo(G_CONV, 1);
assert.ok(t1.includes('Claude Code #2'), 'nombra al otro agente');
assert.ok(t1.includes('builder.js'), 'dice dónde se cruzan');
assert.ok(!t1.includes('Claude Code #1'), 'no se nombra a sí mismo');

assert.ok(tituloVinculo(G_COL, 3).toLowerCase().includes('colisión'),
  'la colisión se nombra distinto que la convergencia');

// tres agentes: los enumera con "y" antes del último
assert.ok(tituloVinculo(G3, 2).includes('A') && tituloVinculo(G3, 2).includes('C'),
  'enumera a los dos compañeros');

// sin archivo compartido cae al símbolo (el caso de archivos distintos)
const G_SIMB = { ...G_CONV, archivos: [], simbolos: ['bw-cfg-uso-top'] };
assert.ok(tituloVinculo(G_SIMB, 1).includes('bw-cfg-uso-top'),
  'sin archivo común, muestra el símbolo compartido');

// sin superficie legible no inventa texto roto
const G_PELADO = { ...G_CONV, archivos: [], simbolos: [] };
assert.ok(!tituloVinculo(G_PELADO, 1).includes('—'), 'sin superficie, sin guión colgando');
assert.strictEqual(tituloVinculo(null, 1), '', 'sin grupo, sin título');

// traduce si le pasan traductor
assert.ok(tituloVinculo(G_CONV, 1, (s) => s === 'Trabajando con' ? 'Working with' : s)
  .startsWith('Working with'), 'usa el traductor');

// ─── diffEstados: repintar solo lo que cambió ────────────────────────────────

let d = diffEstados(new Map(), [G_CONV], [1, 2, 9]);
assert.strictEqual(d.estados.size, 2, 'solo los del grupo tienen estado');
assert.strictEqual(d.cambios.length, 2, 'los dos son cambios nuevos');
assert.ok(!d.estados.has(9), 'el que no está en ningún grupo no entra');

// mismo estado dos veces → sin cambios (no repinta)
const d2 = diffEstados(d.estados, [G_CONV], [1, 2]);
assert.strictEqual(d2.cambios.length, 0, 'estado estable no repinta');

// pasar de convergencia a colisión SÍ es un cambio
const d3 = diffEstados(d.estados, [{ ...G_CONV, estado: 'colision' }], [1, 2]);
assert.deepStrictEqual(d3.cambios.map(c => c[1]), ['colision', 'colision'],
  'la escalada a colisión repinta');

// deshacerse el grupo apaga el ícono (cambio a null)
const d4 = diffEstados(d.estados, [], [1, 2]);
assert.strictEqual(d4.estados.size, 0);
assert.deepStrictEqual(d4.cambios.map(c => c[1]), [null, null], 'apaga los dos');

// una terminal que se fue de pantalla también se apaga
const d5 = diffEstados(d.estados, [G_CONV], [1]);
assert.ok(d5.cambios.some(c => c[0] === 2 && c[1] === null),
  'terminal que ya no está en pantalla se limpia');

// ─── Aviso a la VÍCTIMA de una colisión (2b) ─────────────────────────────────
// Cuando A borra un símbolo que B usa, B se entera por la animación del Swarm.
// La lógica pura decide a QUIÉN avisar (víctimas en pantalla) y QUÉ decirle.
const { victimasDeColision, mensajeColisionVictima } = globalThis.SwarmLink._pure;

const EV_COL = {
  terminal_id: 3, terminal_nombre: 'Backend',
  colisiones: [
    { simbolo: 'aplicarIdioma', tid: 4, nombre: 'Frontend', path: 'app.js' },
    { simbolo: 'bw-cfg-uso-top', tid: 4, nombre: 'Frontend', path: 'app.js' },
    { simbolo: 'otra', tid: 5, nombre: 'Docs', path: 'docs.js' },
  ],
};

// una entrada por víctima, con sus símbolos juntos
let vs = victimasDeColision(EV_COL, [4, 5]);
assert.strictEqual(vs.length, 2, 'una entrada por víctima, no por símbolo');
const v4 = vs.find(x => x.tid === 4);
assert.deepStrictEqual(v4.simbolos, ['aplicarIdioma', 'bw-cfg-uso-top'], 'junta los símbolos de esa víctima');
assert.strictEqual(v4.path, 'app.js', 'dónde ESA víctima lo usa');

// solo las víctimas que están en pantalla (no se puede pulsar una card ausente)
assert.deepStrictEqual(victimasDeColision(EV_COL, [4]).map(x => x.tid), [4], 'filtra las que no se ven');

// el actor nunca es su propia víctima
const EV_SELF = { terminal_id: 3, colisiones: [{ simbolo: 'x', tid: 3, nombre: 'B', path: 'a.js' }] };
assert.deepStrictEqual(victimasDeColision(EV_SELF, [3]), [], 'el actor no se avisa a sí mismo');

// robustez: evento vacío / null no rompe
assert.deepStrictEqual(victimasDeColision({}, [1]), [], 'evento vacío → []');
assert.deepStrictEqual(victimasDeColision(null, [1]), [], 'null → []');

// mensaje DESDE el lado de la víctima: quién, qué símbolos, y dónde los usa
const m = mensajeColisionVictima('Backend', ['aplicarIdioma', 'bw-cfg-uso-top'], 'app.js');
assert.ok(m.includes('Backend'), 'nombra a quien lo rompió');
assert.ok(m.includes('aplicarIdioma') && m.includes('bw-cfg-uso-top'), 'lista los símbolos rotos');
assert.ok(m.includes('app.js'), 'dice dónde los usás');
assert.ok(mensajeColisionVictima('', ['x'], '').length > 0, 'sin actor conocido igual dice algo');
assert.ok(mensajeColisionVictima('B', ['x'], '', s => s === 'borró' ? 'deleted' : s).includes('deleted'),
  'usa el traductor');

console.log('swarm-link colisión-víctima: OK');

console.log('swarm-link: OK');
