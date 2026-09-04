'use strict';
// Tests de la máquina de estados pura de pestañas del Web Preview.
// Corre con: node frontend/sections/preview/__tests__/preview-tabs.test.js
const assert = require('assert');
const T = require('../preview-tabs.js')._pure;

// ── estado inicial ─────────────────────────────────────────────────
{
  const e = T.crearEstado();
  assert.deepStrictEqual(e.tabs, [], 'arranca sin pestañas');
  assert.strictEqual(e.activaId, null, 'sin activa');
  assert.strictEqual(T.tabActiva(e), null, 'tabActiva null');
}

// ── abrirTab: con URL, queda activa, historial arrancado ───────────
{
  const r = T.abrirTab(T.crearEstado(), 'http://localhost:5173');
  assert.strictEqual(r.error, null, 'sin error');
  assert.strictEqual(r.estado.tabs.length, 1, 'una pestaña');
  const t = T.tabActiva(r.estado);
  assert.strictEqual(t.url, 'http://localhost:5173', 'url seteada');
  assert.deepStrictEqual(t.stack, ['http://localhost:5173'], 'historial con la url');
  assert.strictEqual(t.idx, 0, 'idx al inicio');
}

// ── abrirTab: vacía (url null) — pestaña "nueva" sin historial ─────
{
  const r = T.abrirTab(T.crearEstado(), null);
  const t = T.tabActiva(r.estado);
  assert.strictEqual(t.url, null, 'sin url');
  assert.deepStrictEqual(t.stack, [], 'historial vacío');
  assert.strictEqual(t.idx, -1, 'idx -1');
}

// ── abrirTab: ids únicos y crecientes ──────────────────────────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  e = T.abrirTab(e, 'http://b').estado;
  assert.notStrictEqual(e.tabs[0].id, e.tabs[1].id, 'ids distintos');
  assert.strictEqual(e.activaId, e.tabs[1].id, 'la última abierta queda activa');
}

// ── abrirTab: tope MAX_TABS ────────────────────────────────────────
{
  let e = T.crearEstado();
  for (let i = 0; i < T.MAX_TABS; i++) e = T.abrirTab(e, `http://t${i}`).estado;
  const r = T.abrirTab(e, 'http://overflow');
  assert.strictEqual(r.error, 'max', 'devuelve error max');
  assert.strictEqual(r.estado.tabs.length, T.MAX_TABS, 'no agrega de más');
}

// ── activarTab ─────────────────────────────────────────────────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  const idA = e.activaId;
  e = T.abrirTab(e, 'http://b').estado;
  e = T.activarTab(e, idA);
  assert.strictEqual(T.tabActiva(e).url, 'http://a', 'activa la pedida');
  assert.strictEqual(T.activarTab(e, 9999), e, 'id inexistente → estado igual');
}

// ── cerrarTab: cierra la activa → activa la vecina derecha ─────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  e = T.abrirTab(e, 'http://b').estado;
  e = T.abrirTab(e, 'http://c').estado;
  const idB = e.tabs[1].id;
  e = T.activarTab(e, idB);
  e = T.cerrarTab(e, idB);
  assert.strictEqual(e.tabs.length, 2, 'quedan dos');
  assert.strictEqual(T.tabActiva(e).url, 'http://c', 'activa la de la derecha');
}

// ── cerrarTab: era la última de la derecha → activa la izquierda ───
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  e = T.abrirTab(e, 'http://b').estado;
  e = T.cerrarTab(e, e.activaId);
  assert.strictEqual(T.tabActiva(e).url, 'http://a', 'activa la izquierda');
}

// ── cerrarTab: cerrar una NO activa no cambia la activa ────────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  const idA = e.activaId;
  e = T.abrirTab(e, 'http://b').estado;
  e = T.cerrarTab(e, idA);
  assert.strictEqual(T.tabActiva(e).url, 'http://b', 'activa intacta');
}

// ── cerrarTab: la única → queda vacío ──────────────────────────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  e = T.cerrarTab(e, e.activaId);
  assert.deepStrictEqual(e.tabs, [], 'sin pestañas');
  assert.strictEqual(e.activaId, null, 'sin activa');
}

// ── navegarTab: push trunca los forwards ───────────────────────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  const id = e.activaId;
  e = T.navegarTab(e, id, 'http://b');
  e = T.navegarTab(e, id, 'http://c');
  e = T.atrasTab(e, id);                       // ← en b
  e = T.navegarTab(e, id, 'http://d');         // pisa el forward c
  const t = T.tabActiva(e);
  assert.deepStrictEqual(t.stack, ['http://a', 'http://b', 'http://d'], 'trunca forwards');
  assert.strictEqual(t.idx, 2, 'idx al final');
  assert.strictEqual(t.url, 'http://d', 'url actual');
}

// ── navegarTab: misma url no duplica en el stack ───────────────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  e = T.navegarTab(e, e.activaId, 'http://a');
  assert.deepStrictEqual(T.tabActiva(e).stack, ['http://a'], 'sin duplicado');
}

// ── navegarTab con push=false (back/forward externo) no apila ──────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  e = T.navegarTab(e, e.activaId, 'http://b', false);
  const t = T.tabActiva(e);
  assert.strictEqual(t.url, 'http://b', 'url cambia');
  assert.deepStrictEqual(t.stack, ['http://a'], 'stack intacto');
}

// ── atras/adelante en los bordes: no-op ────────────────────────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  const id = e.activaId;
  assert.strictEqual(T.atrasTab(e, id), e, 'atrás en el inicio → no-op');
  assert.strictEqual(T.adelanteTab(e, id), e, 'adelante en el final → no-op');
}

// ── atras/adelante mueven url e idx ────────────────────────────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  const id = e.activaId;
  e = T.navegarTab(e, id, 'http://b');
  e = T.atrasTab(e, id);
  assert.strictEqual(T.tabActiva(e).url, 'http://a', 'atrás vuelve a a');
  e = T.adelanteTab(e, id);
  assert.strictEqual(T.tabActiva(e).url, 'http://b', 'adelante vuelve a b');
}

// ── tituloTab ──────────────────────────────────────────────────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  e = T.tituloTab(e, e.activaId, 'Mi App');
  assert.strictEqual(T.tabActiva(e).titulo, 'Mi App', 'título seteado');
}

// ── encontrarPorUrl ────────────────────────────────────────────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  const idA = e.activaId;
  e = T.abrirTab(e, 'http://b').estado;
  assert.strictEqual(T.encontrarPorUrl(e, 'http://a'), idA, 'encuentra por url');
  assert.strictEqual(T.encontrarPorUrl(e, 'http://zzz'), null, 'no está → null');
}

// ── encontrarPorOrigen: mismo host:puerto aunque el path difiera ───
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://localhost:5173/about').estado;
  const id5173 = e.activaId;
  e = T.abrirTab(e, 'http://localhost:8000').estado;
  // un restart detecta la URL base; la pestaña ya navegó a /about → mismo origen
  assert.strictEqual(T.encontrarPorOrigen(e, 'http://localhost:5173/'), id5173, 'match por origen ignorando path');
  assert.strictEqual(T.encontrarPorOrigen(e, 'localhost:5173'), null, 'sin esquema no parsea como URL → null');
  assert.strictEqual(T.encontrarPorOrigen(e, 'http://localhost:9999'), null, 'otro puerto → null');
  assert.strictEqual(T.encontrarPorOrigen(e, 'basura'), null, 'no-URL → null');
  // pestaña "nueva" (url null) no matchea ningún origen
  e = T.abrirTab(e, null).estado;
  assert.strictEqual(T.encontrarPorOrigen(e, 'http://localhost:5173'), id5173, 'la pestaña vacía no interfiere');
}

// ── claveReuso / encontrarPorReuso: demos de Jarvis por CARPETA ─────
// (fix "una pestaña le quita la del otro" con varios agentes, 2026-07-12)
{
  const JH = 'localhost:3000';   // host del propio workspace
  // dev server real → clave = origen (host:puerto), ignora el path
  assert.strictEqual(T.claveReuso('http://localhost:5173/about', JH), 'http://localhost:5173', 'server real → origen');
  // demo de Jarvis → clave = carpeta del demo, NO el origen compartido :3000
  assert.strictEqual(T.claveReuso('http://localhost:3000/static/demo-a/index.html', JH),
    'http://localhost:3000/static/demo-a', 'demo → carpeta');
  assert.strictEqual(T.claveReuso('http://localhost:3000/static/demo-a/sub/x.html', JH),
    'http://localhost:3000/static/demo-a', 'subpágina del MISMO demo → misma carpeta');
  // dos demos distintos = claves distintas (no colapsan)
  assert.notStrictEqual(
    T.claveReuso('http://localhost:3000/static/demo-a/', JH),
    T.claveReuso('http://localhost:3000/static/demo-b/', JH), 'demos distintos → claves distintas');
  // sin jarvisHost → todo por origen (comportamiento previo)
  assert.strictEqual(T.claveReuso('http://localhost:3000/static/demo-a/', ''), 'http://localhost:3000', 'sin host → origen');
  assert.strictEqual(T.claveReuso('basura', JH), null, 'no-URL → null');

  // encontrarPorReuso: el demo de un agente NO matchea el de otro (mismo :3000)
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://localhost:3000/static/demo-a/index.html').estado;
  const idA = e.activaId;
  e = T.abrirTab(e, 'http://localhost:3000/static/demo-b/index.html').estado;
  const idB = e.activaId;
  assert.strictEqual(T.encontrarPorReuso(e, 'http://localhost:3000/static/demo-a/otra.html', JH), idA,
    'demo-a reusa SU pestaña');
  assert.strictEqual(T.encontrarPorReuso(e, 'http://localhost:3000/static/demo-b/', JH), idB,
    'demo-b reusa la SUYA (no la de a)');
  assert.strictEqual(T.encontrarPorReuso(e, 'http://localhost:3000/static/demo-c/', JH), null,
    'demo nuevo → sin pestaña (se abrirá una)');
  // CONTRASTE: por origen (viejo) demo-b habría matcheado la pestaña de demo-a (el bug)
  assert.strictEqual(T.encontrarPorOrigen(e, 'http://localhost:3000/static/demo-b/'), idA,
    'por ORIGEN colapsan → era el bug');

  // dev server real: encontrarPorReuso sigue reusando por origen (restart/navegar)
  let e2 = T.crearEstado();
  e2 = T.abrirTab(e2, 'http://localhost:5173/about').estado;
  const id5173b = e2.activaId;
  assert.strictEqual(T.encontrarPorReuso(e2, 'http://localhost:5173/', JH), id5173b, 'server real reusa por origen');
}

// ── serializar / deserializar (round-trip de persistencia) ─────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  const idA = e.activaId;
  e = T.abrirTab(e, 'http://b').estado;
  e = T.activarTab(e, idA);
  const data = T.serializar(e);
  assert.deepStrictEqual(data, { urls: ['http://a', 'http://b'], activa: 0 }, 'serializa urls + activa');
  const e2 = T.deserializar(data);
  assert.strictEqual(e2.tabs.length, 2, 'restaura las dos');
  assert.strictEqual(T.tabActiva(e2).url, 'http://a', 'restaura la activa');
}

// ── deserializar: basura → estado limpio ───────────────────────────
{
  assert.deepStrictEqual(T.deserializar(null).tabs, [], 'null → vacío');
  assert.deepStrictEqual(T.deserializar({}).tabs, [], 'sin urls → vacío');
  assert.deepStrictEqual(T.deserializar({ urls: 'x' }).tabs, [], 'urls no-array → vacío');
  const e = T.deserializar({ urls: ['http://a'], activa: 99 });
  assert.strictEqual(T.tabActiva(e).url, 'http://a', 'activa fuera de rango → última válida');
}

// ── inmutabilidad: las operaciones no mutan la entrada ─────────────
{
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  const congelado = JSON.stringify(e);
  T.abrirTab(e, 'http://b');
  T.cerrarTab(e, e.activaId);
  T.navegarTab(e, e.activaId, 'http://c');
  T.atrasTab(e, e.activaId);
  T.tituloTab(e, e.activaId, 'x');
  T.activarTab(e, e.activaId);
  assert.strictEqual(JSON.stringify(e), congelado, 'entrada intacta');
}

console.log('OK preview-tabs');

// ═══ cambiarProyecto: estacionar/adoptar pools de iframes vivos ═══════
// El pool ({estado, vistas}) es OPACO acá: la función solo decide qué se
// estaciona y qué se adopta; los efectos (ocultar iframes) viven en preview.js.

// ── primer cambio: parkea el saliente, el entrante no tenía pool ────
{
  const poolA = { estado: 'eA', vistas: {} };
  const r = T.cambiarProyecto({}, 1, poolA, 2);
  assert.strictEqual(r.pool, null, 'entrante sin pool → null (restaurar de localStorage)');
  assert.strictEqual(r.pools[1], poolA, 'el saliente queda estacionado');
}

// ── vuelta atrás: adopta el pool estacionado y lo saca del estacionamiento ──
{
  const poolB = { estado: 'eB' };
  const r = T.cambiarProyecto({ 2: poolB }, 1, { estado: 'eA' }, 2);
  assert.strictEqual(r.pool, poolB, 'devuelve el pool del entrante');
  assert.strictEqual(r.pools[2], undefined, 'ya no está estacionado');
  assert.ok(r.pools[1], 'el saliente quedó estacionado');
}

// ── primer proyecto de la sesión: sin saliente, nada que parkear ────
{
  const r = T.cambiarProyecto({}, null, null, 5);
  assert.deepStrictEqual(r.pools, {}, 'sin pools');
  assert.strictEqual(r.pool, null, 'sin pool para adoptar');
}

// ── salir a "sin proyecto" (null): solo parkea ──────────────────────
{
  const r = T.cambiarProyecto({}, 3, { estado: 'e3' }, null);
  assert.ok(r.pools[3], 'parkea el saliente');
  assert.strictEqual(r.pool, null, 'nada que adoptar');
}

// ── saliente null con pid: no estaciona basura ──────────────────────
{
  const r = T.cambiarProyecto({}, 4, null, 5);
  assert.deepStrictEqual(r.pools, {}, 'sin pool saliente no se estaciona nada');
}

// ── no muta la entrada ──────────────────────────────────────────────
{
  const pools = { 7: { estado: 'e7' } };
  T.cambiarProyecto(pools, 1, { estado: 'e1' }, 7);
  assert.deepStrictEqual(Object.keys(pools), ['7'], 'pools de entrada intacto');
}

console.log('OK cambiarProyecto');

// ═══ moverTab: reordenar pestañas (drag & drop de la fila) ════════════
function estadoABC() {
  let e = T.crearEstado();
  e = T.abrirTab(e, 'http://a').estado;
  e = T.abrirTab(e, 'http://b').estado;
  e = T.abrirTab(e, 'http://c').estado;
  return e;
}
const urls = (e) => e.tabs.map((t) => t.url);

// ── mover hacia adelante y hacia atrás ──────────────────────────────
{
  const e = estadoABC();
  assert.deepStrictEqual(urls(T.moverTab(e, e.tabs[0].id, 2)),
    ['http://b', 'http://c', 'http://a'], 'primera al final');
  assert.deepStrictEqual(urls(T.moverTab(e, e.tabs[2].id, 0)),
    ['http://c', 'http://a', 'http://b'], 'última al principio');
  assert.deepStrictEqual(urls(T.moverTab(e, e.tabs[1].id, 2)),
    ['http://a', 'http://c', 'http://b'], 'del medio al final');
}

// ── destino clampeado; misma posición / id inexistente → estado intacto ──
{
  const e = estadoABC();
  assert.deepStrictEqual(urls(T.moverTab(e, e.tabs[0].id, 99)),
    ['http://b', 'http://c', 'http://a'], 'destino grande clampea al final');
  assert.deepStrictEqual(urls(T.moverTab(e, e.tabs[2].id, -5)),
    ['http://c', 'http://a', 'http://b'], 'destino negativo clampea a 0');
  assert.strictEqual(T.moverTab(e, e.tabs[1].id, 1), e, 'misma posición → mismo estado');
  assert.strictEqual(T.moverTab(e, 999, 0), e, 'id inexistente → mismo estado');
}

// ── la activa sigue siendo la misma pestaña (por id) y no muta ──────
{
  const e = estadoABC();               // activa = la última abierta (c)
  const congelado = JSON.stringify(e);
  const r = T.moverTab(e, e.tabs[2].id, 0);
  assert.strictEqual(r.activaId, e.activaId, 'activaId no cambia al mover');
  assert.strictEqual(JSON.stringify(e), congelado, 'entrada intacta');
}

// ── el orden movido sobrevive serializar/deserializar ───────────────
{
  const e = T.moverTab(estadoABC(), estadoABC().tabs[0].id, 2);
  const r = T.deserializar(T.serializar(e));
  assert.deepStrictEqual(urls(r), ['http://b', 'http://c', 'http://a'], 'persistencia respeta el orden');
}

console.log('OK moverTab');

// ═══ destinoDrag: a qué índice cae la pestaña arrastrada ══════════════
// rects = medición al ARRANCAR el drag ({left, width} por pestaña, en orden);
// dx = desplazamiento del puntero. EAGER: la arrastrada toma el lugar del
// vecino apenas su borde delantero invade DRAG_FRACCION de ese vecino (no
// hace falta cruzarlo entero). `prev` (destino anterior) activa la
// histéresis: des-cruzar un límite ya cruzado pide unos px extra.
{
  const rects = [{ left: 0, width: 100 }, { left: 102, width: 100 }, { left: 204, width: 100 }];
  assert.strictEqual(T.destinoDrag(rects, 0, 0), 0, 'sin mover → se queda');
  assert.strictEqual(T.destinoDrag(rects, 0, 110), 1, 'bien pasado el vecino → índice 1');
  assert.strictEqual(T.destinoDrag(rects, 0, 210), 2, 'pasa todas → al final');
  assert.strictEqual(T.destinoDrag(rects, 2, -110), 1, 'arrastre a la izquierda');
  assert.strictEqual(T.destinoDrag(rects, 2, -210), 0, 'hasta el principio');
  assert.strictEqual(T.destinoDrag(rects, 1, -5000), 0, 'clamp: nunca negativo');
  assert.strictEqual(T.destinoDrag(rects, 1, 5000), 2, 'clamp: nunca pasa el final');
}

// ── EAGER: con acercarse alcanza (borde invade ⅓ del vecino) ────────
{
  const rects = [{ left: 0, width: 100 }, { left: 102, width: 100 }, { left: 204, width: 100 }];
  // der de la 1ª = 100+dx; límite del vecino = 102 + 35 = 137 → dx=38 ya swapea
  assert.strictEqual(T.destinoDrag(rects, 0, 38), 1, 'invadió ⅓ del vecino → swap YA');
  assert.strictEqual(T.destinoDrag(rects, 0, 30), 0, 'todavía no invadió lo suficiente');
  // hacia la izquierda, simétrico: izq de la 3ª = 204+dx; límite = 102+65 = 167 → dx=-38
  assert.strictEqual(T.destinoDrag(rects, 2, -38), 1, 'invadió ⅓ del vecino izquierdo → swap');
  assert.strictEqual(T.destinoDrag(rects, 2, -30), 2, 'todavía no');
  // no salta DOS lugares por invadir apenas el primero
  assert.strictEqual(T.destinoDrag(rects, 0, 45), 1, 'un solo lugar por vez');
}

// ── HISTÉRESIS: volver atrás pide unos px extra (anti-flicker) ──────
{
  const rects = [{ left: 0, width: 100 }, { left: 102, width: 100 }, { left: 204, width: 100 }];
  // ya swapeado (prev=1): en dx=35 (der=135 < 137) SIN prev volvería a 0,
  // pero con histéresis el límite baja a 129 → sigue en 1.
  assert.strictEqual(T.destinoDrag(rects, 0, 35, 1), 1, 'jitter chico no des-swapea');
  assert.strictEqual(T.destinoDrag(rects, 0, 25, 1), 0, 'retroceso franco sí vuelve');
  // simétrico a la izquierda
  assert.strictEqual(T.destinoDrag(rects, 2, -35, 1), 1, 'jitter chico mantiene (izq)');
  assert.strictEqual(T.destinoDrag(rects, 2, -25, 1), 2, 'retroceso franco vuelve (izq)');
  // sin prev (arranque del drag): comportamiento sin histéresis
  assert.strictEqual(T.destinoDrag(rects, 0, 35), 0, 'sin prev no hay histéresis');
}

console.log('OK destinoDrag');
console.log('OK ALL');
