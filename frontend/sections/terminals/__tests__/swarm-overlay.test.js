// Tests de la lógica pura de SwarmOverlay (swarm-overlay.js).
//
// El overlay no es un gráfico de telemetría: es un ESCENARIO. Los agentes son
// nodos, entre los que comparten superficie hay un enlace que respira, y cuando
// uno le manda un mensaje a otro un pulso recorre ese enlace del que habla al
// que escucha. Acá se testea la geometría que hace posible esa animación.
'use strict';
const assert = require('assert');
require('../swarm-overlay.js');
const { posicionarNodos, enlacesDe, enlaceEntre, pulsosDeMensajes, pulsoDeNodo,
        hace, resumenSuperficie, lineaEvento, pidDe, GEO } = globalThis.SwarmOverlay._pure;

const MIEMBROS = [{ tid: 1, nombre: 'Claude Code #1' },
                  { tid: 2, nombre: 'Claude Code #2' }];
const TRES = [...MIEMBROS, { tid: 3, nombre: 'Claude Code #3' }];
const T = 1_000_000;

// ─── Nodos en el escenario ────────────────────────────────────────────────────

let n = posicionarNodos(MIEMBROS, {});
assert.strictEqual(n.length, 2, 'un nodo por agente');
assert.ok(n[0].x < n[1].x, 'dos agentes quedan ENFRENTADOS, izquierda y derecha');
assert.ok(Math.abs(n[0].y - n[1].y) < 0.001, 'y a la misma altura');
assert.ok(Math.abs((n[0].x + n[1].x) / 2 - GEO.ancho / 2) < 0.001, 'centrados');

const n3 = posicionarNodos(TRES, {});
assert.strictEqual(n3.length, 3);
// tres → círculo: ninguno comparte posición y el primero queda ARRIBA
const ys = n3.map(p => p.y);
assert.ok(ys[0] < ys[1] && ys[0] < ys[2], 'el primero queda arriba del todo');
// El escenario es ANCHO (920×380), así que el reparto es sobre una elipse, no
// sobre un círculo: aprovecha el largo en vez de amontonarse en el medio. Lo
// que importa no es que sea equilátero sino que ninguno se pise con otro y que
// el conjunto quede centrado.
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
for (let i = 0; i < 3; i++) {
  for (let j = i + 1; j < 3; j++) {
    assert.ok(dist(n3[i], n3[j]) > GEO.nodo * 2.4,
      `nodos ${i} y ${j} bien separados (no se superponen)`);
  }
}
assert.ok(Math.abs(n3.reduce((s, p) => s + p.x, 0) / 3 - GEO.ancho / 2) < 1,
  'el grupo queda centrado horizontalmente');

// La etiqueta va del lado LIBRE: si el nombre del nodo de arriba fuera abajo,
// caería justo encima de sus dos enlaces.
assert.strictEqual(n3[0].etiquetaArriba, true, 'el nodo de arriba rotula arriba');
assert.ok(n3.slice(1).every(p => p.etiquetaArriba === false),
  'los de abajo rotulan abajo');

assert.deepStrictEqual(posicionarNodos([], {}), [], 'sin miembros no rompe');
assert.deepStrictEqual(posicionarNodos(null, {}), []);
const uno = posicionarNodos([{ tid: 1, nombre: 'A' }], {});
assert.strictEqual(uno[0].x, GEO.ancho / 2, 'uno solo va al centro');
// miembros basura no generan nodos fantasma
assert.strictEqual(posicionarNodos([{ nombre: 'sin tid' }], {}).length, 0);

// los nodos caben dentro del escenario (si no, se cortan contra el borde)
for (const p of [...n, ...n3]) {
  assert.ok(p.x > GEO.nodo && p.x < GEO.ancho - GEO.nodo, `x dentro: ${p.x}`);
  assert.ok(p.y > GEO.nodo && p.y < GEO.alto - GEO.nodo, `y dentro: ${p.y}`);
}

// ─── Enlaces ──────────────────────────────────────────────────────────────────

let e = enlacesDe(n, {});
assert.strictEqual(e.length, 1, 'dos agentes, un enlace');
// El enlace TOCA el anillo, no atraviesa el disco: arranca recortado desde el
// borde del nodo, no desde su centro.
const borde = GEO.nodo * 0.62;
assert.ok(e[0].x1 > n[0].x + borde * 0.9 && e[0].x1 < n[0].x + borde * 2,
  'la punta arranca en el borde del nodo, no en su centro');
assert.ok(e[0].x2 < n[1].x - borde * 0.9, 'y termina antes del otro nodo');
assert.ok(e[0].x1 < e[0].x2, 'sigue yendo de izquierda a derecha');

const e3 = enlacesDe(n3, {});
assert.strictEqual(e3.length, 3, 'tres agentes, tres enlaces (todos con todos)');
// con tres, los enlaces se COMBAN hacia afuera para no superponerse
for (const x of e3) {
  const mx = (x.x1 + x.x2) / 2, my = (x.y1 + x.y2) / 2;
  assert.ok(Math.hypot(x.cx - mx, x.cy - my) > 1,
    'el enlace se separa de la recta: con tres, si no, se pisan');
}
// con dos NO se comba (una recta limpia entre los dos)
assert.ok(Math.hypot(e[0].cx - (e[0].x1 + e[0].x2) / 2,
                     e[0].cy - (e[0].y1 + e[0].y2) / 2) < 0.001,
  'dos agentes: enlace recto');

assert.deepStrictEqual(enlacesDe([], {}), []);
assert.deepStrictEqual(enlacesDe(null, {}), []);

// enlaceEntre encuentra el par en cualquier orden
assert.ok(enlaceEntre(e3, 1, 2), 'encuentra 1-2');
assert.ok(enlaceEntre(e3, 2, 1), 'y también 2-1');
assert.strictEqual(enlaceEntre(e3, 1, 9), null, 'par inexistente → null');
assert.strictEqual(enlaceEntre(null, 1, 2), null);

// ─── Pulsos: el mensaje viajando ─────────────────────────────────────────────

let p = pulsosDeMensajes(
  [{ tipo: 'mensaje', ts: T, de: 'Claude Code #1', para: 'Claude Code #2', texto: 'hola' }],
  n, e, 6);
assert.strictEqual(p.length, 1, 'un mensaje, un pulso');
assert.strictEqual(p[0].de, 1);
assert.strictEqual(p[0].para, 2);
assert.ok(p[0].enlace, 'el pulso sabe por qué enlace viajar');
assert.strictEqual(p[0].invertido, false, 'de 1 a 2 recorre el enlace de ida');

// la RESPUESTA recorre el mismo enlace al revés (o el pulso viajaría al revés)
p = pulsosDeMensajes(
  [{ tipo: 'mensaje', ts: T, de: 'Claude Code #2', para: 'Claude Code #1' }], n, e, 6);
assert.strictEqual(p[0].invertido, true, 'de 2 a 1 recorre invertido');

// tolera mayúsculas y espacios en los nombres (así llegan de la DB)
p = pulsosDeMensajes(
  [{ tipo: 'mensaje', ts: T, de: '  claude code #1 ', para: 'CLAUDE CODE #2' }], n, e, 6);
assert.strictEqual(p.length, 1, 'normaliza los nombres');

// alguien de afuera del grupo no genera pulso
p = pulsosDeMensajes(
  [{ tipo: 'mensaje', ts: T, de: 'Claude Code #1', para: 'Alguien Más' }], n, e, 6);
assert.strictEqual(p.length, 0);

// las ediciones no son pulsos
p = pulsosDeMensajes([{ tipo: 'edicion', ts: T, tid: 1 }], n, e, 6);
assert.strictEqual(p.length, 0);

// se acotan: treinta pulsos a la vez no son información, son ruido
const muchos = Array.from({ length: 30 }, (_, i) => ({
  tipo: 'mensaje', ts: T + i, de: 'Claude Code #1', para: 'Claude Code #2',
  texto: `m${i}` }));
p = pulsosDeMensajes(muchos, n, e, 6);
assert.strictEqual(p.length, 6, 'tope respetado');
assert.strictEqual(p[p.length - 1].texto, 'm29', 'se queda con los MÁS RECIENTES');

// ─── Pulso del nodo (halo de actividad) ──────────────────────────────────────

let pn = pulsoDeNodo([{ tipo: 'edicion', ts: T, tid: 1 },
                      { tipo: 'edicion', ts: T + 10, tid: 1 },
                      { tipo: 'edicion', ts: T, tid: 2 }], 1, T + 20);
assert.strictEqual(pn.escrituras, 2, 'cuenta solo las suyas');
assert.strictEqual(pn.activo, true, 'escribió recién → halo encendido');

pn = pulsoDeNodo([{ tipo: 'edicion', ts: T, tid: 1 }], 1, T + 5000);
assert.strictEqual(pn.activo, false, 'hace rato que no escribe → halo apagado');

pn = pulsoDeNodo([{ tipo: 'mensaje', ts: T, de: 'A', para: 'B' }], 1, T + 1);
assert.strictEqual(pn.escrituras, 0, 'un mensaje no es una escritura');
assert.strictEqual(pulsoDeNodo([], 1, T).activo, false, 'sin actividad, sin halo');

// ─── hace() ───────────────────────────────────────────────────────────────────

assert.strictEqual(hace(1000, 1030), '30s');
assert.strictEqual(hace(1000, 1000 + 180), '3m');
assert.strictEqual(hace(1000, 1000 + 7200), '2h');
assert.strictEqual(hace(1000, 900), '0s', 'un ts futuro no da negativo');

// ─── resumenSuperficie: el "por qué están enredados" ─────────────────────────

// Los nombres son el dato útil: contar ("3 símbolos en común") esconde justo lo
// que el usuario necesita para decidir si le importa.
assert.strictEqual(resumenSuperficie({ archivos: ['builder.js'], simbolos: [] }),
  'builder.js', 'un solo archivo se nombra');
const dos = resumenSuperficie({ archivos: ['a.js', 'b.js'], simbolos: [] });
assert.ok(dos.includes('a.js') && dos.includes('b.js'), 'dos archivos: los dos');
const tres = resumenSuperficie({ archivos: ['a.js', 'b.js', 'c.js'], simbolos: [] });
assert.ok(tres.includes('a.js') && tres.includes('+2'), 'el primero + cuántos más');
assert.ok(resumenSuperficie({ archivos: [], simbolos: ['bw-cfg-uso-top'] })
  .includes('bw-cfg-uso-top'), 'sin archivo común, muestra el símbolo');
const mm = resumenSuperficie({ archivos: [], simbolos: ['a1', 'b2', 'c3', 'd4', 'e5'] });
assert.ok(mm.includes('a1') && mm.includes('c3') && mm.includes('+2'));
assert.ok(!mm.includes('d4'), 'no vomita la lista entera en el encabezado');
assert.strictEqual(resumenSuperficie({ archivos: [], simbolos: [] }), '');
assert.strictEqual(resumenSuperficie(null), '', 'null no rompe');

// ─── lineaEvento: la lectura cronológica ─────────────────────────────────────

let l = lineaEvento({ tipo: 'mensaje', de: 'A', para: 'B', texto: 'hola' });
assert.strictEqual(l.icono, 'mensaje');
assert.strictEqual(l.quien, 'A');
assert.ok(l.extra.includes('B'), 'se ve a quién le habla');

l = lineaEvento({ tipo: 'colision', nombre: 'B', simbolo: 'aplicarIdioma',
                  contra_nombre: 'A', contra_path: 'builder.js' });
assert.strictEqual(l.icono, 'colision');
assert.ok(l.texto.includes('aplicarIdioma') && l.texto.includes('A'),
  'dice qué rompió y a quién');

l = lineaEvento({ tipo: 'edicion', nombre: 'A', path: 'x.js', simbolos: ['uno', 'dos'] });
assert.strictEqual(l.icono, 'edicion');
assert.strictEqual(l.texto, 'x.js');

l = lineaEvento({ tipo: 'edicion', nombre: 'A', path: 'x.js', sobrescritura: true });
assert.strictEqual(l.icono, 'sobrescritura', 'la sobrescritura se marca distinto');

// ─── pidDe: de qué proyecto es este grupo ────────────────────────────────────
// El bug que arreglás no lo ves: el overlay pedía el detalle a un proyecto que
// resolvía por una variable global que NUNCA existió, así que la URL salía nula,
// el fetch no se hacía y el panel se cerraba solo en el mismo frame en que se
// abría. Desde afuera: "le doy click y no pasa nada".

assert.strictEqual(pidDe(7, '?id=9'), '7', 'manda el que abre el overlay');
assert.strictEqual(pidDe(null, '?id=9&qa=1'), '9', 'sin dato explícito, la URL');
assert.strictEqual(pidDe(undefined, '?id=12'), '12', 'undefined también cae a la URL');
assert.strictEqual(pidDe('', '?id=3'), '3', 'vacío no es un proyecto');
assert.strictEqual(pidDe(null, '?qa=1'), null, 'sin proyecto en ningún lado, null');
assert.strictEqual(pidDe(null, ''), null, 'sin querystring no explota');
assert.strictEqual(pidDe(0, '?id=5'), '5', 'no hay proyecto 0: cae a la URL');

console.log('swarm-overlay: OK');
