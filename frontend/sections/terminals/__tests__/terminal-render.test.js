'use strict';
// Tests del fix de "terminal NEGRA hasta scrollear" (ver [[negro-al-maximizar-raf-starvation]]).
// Causa raíz (medida en banco de pruebas 2026-07-04): term.resize() borra el canvas
// (CanvasAddon reasigna canvas.width) y el repintado queda atado al ÚNICO rAF del
// RenderDebouncer de xterm — que se STARVA bajo carga (terminales ocultas parseando
// su WS) hasta 5s. term.refresh() NO cura: solo fusiona en ese rAF pendiente.
// Fix: (1) pintarYa = render SINCRÓNICO saltando el debouncer, en la misma task que
// el resize (el compositor jamás ve el canvas borrado); (2) blindarRenderStarvation =
// fallback por setTimeout en el debouncer (los timers compiten como task normal con
// los onmessage del WS; el rAF depende del frame scheduling, que es lo que se starva).
//
// Los fakes replican la SEMÁNTICA EXACTA del RenderDebouncer/RenderService minificados
// del vendor (frontend/vendor/xterm/xterm.js, módulos 6193 y RenderService): si xterm
// se actualiza y cambia el contrato, estos tests siguen verdes pero pintarYa degrada
// solo a term.refresh (fallback) — por eso el módulo NUNCA debe tirar.

const assert = require('node:assert');
const Render = require('../terminal-render.js');

// ── Fakes fieles al vendor ────────────────────────────────────────────────────

function ventanaFake() {
  let rafId = 0; const rafs = new Map();
  let tId = 0; const timers = new Map();
  return {
    requestAnimationFrame(cb) { rafs.set(++rafId, cb); return rafId; },
    cancelAnimationFrame(id) { rafs.delete(id); },
    setTimeout(cb, ms) { timers.set(++tId, { cb, ms }); return tId; },
    clearTimeout(id) { timers.delete(id); },
    // El browser POR FIN sirve un frame (lo que bajo starvation tarda segundos):
    servirRaf() { const l = [...rafs.values()]; rafs.clear(); l.forEach(cb => cb()); },
    // Los timers SÍ corren entre las tasks del WS (task queue normal):
    dispararTimers() { const l = [...timers.values()]; timers.clear(); l.forEach(t => t.cb()); },
    rafsPendientes() { return rafs.size; },
    timersPendientes() { return timers.size; },
  };
}

// Réplica del RenderDebouncer vendoreado (xterm 5.3, módulo 6193) — misma lógica.
class DebouncerFake {
  constructor(win, renderCallback) {
    this._parentWindow = win;
    this._renderCallback = renderCallback;
    this._refreshCallbacks = [];
  }
  dispose() {
    if (this._animationFrame) {
      this._parentWindow.cancelAnimationFrame(this._animationFrame);
      this._animationFrame = undefined;
    }
  }
  refresh(e, t, i) {
    this._rowCount = i;
    e = e !== undefined ? e : 0;
    t = t !== undefined ? t : this._rowCount - 1;
    this._rowStart = this._rowStart !== undefined ? Math.min(this._rowStart, e) : e;
    this._rowEnd = this._rowEnd !== undefined ? Math.max(this._rowEnd, t) : t;
    if (!this._animationFrame) {
      this._animationFrame = this._parentWindow.requestAnimationFrame(() => this._innerRefresh());
    }
  }
  _innerRefresh() {
    this._animationFrame = undefined;
    if (this._rowStart === undefined || this._rowEnd === undefined || this._rowCount === undefined) {
      this._runRefreshCallbacks(); return;
    }
    const e = Math.max(this._rowStart, 0);
    const t = Math.min(this._rowEnd, this._rowCount - 1);
    this._rowStart = undefined; this._rowEnd = undefined;
    this._renderCallback(e, t);
    this._runRefreshCallbacks();
  }
  _runRefreshCallbacks() {
    for (const cb of this._refreshCallbacks) cb(0);
    this._refreshCallbacks = [];
  }
}

// Réplica del gate de RenderService.refreshRows (pausa por IntersectionObserver).
class SvcFake {
  constructor(win, pintados) {
    this._isPaused = false;
    this._needsFullRefresh = false;
    this._rowCount = 24;
    this._renderDebouncer = new DebouncerFake(win, (a, b) => pintados.push([a, b]));
  }
  refreshRows(e, t) {
    if (this._isPaused) { this._needsFullRefresh = true; return; }
    this._renderDebouncer.refresh(e, t, this._rowCount);
  }
}

function termFake(win) {
  const pintados = [];          // llamadas REALES al renderer (lo que pinta el canvas)
  const fallbacks = [];         // llamadas a term.refresh (el camino viejo, rAF-gated)
  const svc = new SvcFake(win, pintados);
  return {
    term: {
      rows: 24, cols: 80,
      _core: { _renderService: svc },
      refresh(a, b) { fallbacks.push([a, b]); },
    },
    svc, pintados, fallbacks,
  };
}

// ── 1 · La mecánica del bug (documentada): refresh NO pinta hasta que el rAF corre ──
{
  const win = ventanaFake();
  const { svc, pintados } = termFake(win);
  svc.refreshRows(0, 23);
  assert.strictEqual(pintados.length, 0, 'el debouncer NO pinta en la misma task (por eso el negro)');
  assert.strictEqual(win.rafsPendientes(), 1, 'queda 1 rAF pendiente — bajo starvation tarda segundos');
  win.servirRaf();
  assert.deepStrictEqual(pintados, [[0, 23]], 'recién pinta cuando el browser sirve el frame');
}

// ── 2 · pintarYa: pinta SINCRÓNICO en la misma task, sin depender de ningún rAF ──
{
  const win = ventanaFake();
  const { term, pintados } = termFake(win);
  const modo = Render.pintarYa(term);
  assert.strictEqual(modo, 'sync', 'con internals sanos debe pintar por la vía sincrónica');
  assert.deepStrictEqual(pintados, [[0, 23]], 'el viewport completo quedó pintado YA');
  assert.strictEqual(win.rafsPendientes(), 0, 'no deja rAF pendiente (lo cancela: cero doble-paint)');
  win.servirRaf();
  assert.strictEqual(pintados.length, 1, 'servir frames después no re-pinta nada');
}

// ── 3 · pintarYa con un rAF YA pendiente (refresh previo en vuelo): lo absorbe ──
{
  const win = ventanaFake();
  const { term, svc, pintados } = termFake(win);
  svc.refreshRows(3, 7);                    // alguien ya agendó un repintado parcial
  const modo = Render.pintarYa(term);
  assert.strictEqual(modo, 'sync');
  assert.deepStrictEqual(pintados, [[0, 23]], 'fusiona el rango pendiente y pinta todo una sola vez');
  win.servirRaf();
  assert.strictEqual(pintados.length, 1, 'el rAF viejo quedó cancelado — sin doble paint');
}

// ── 4 · pintarYa con render PAUSADO (card fuera de viewport): fallback inofensivo ──
{
  const win = ventanaFake();
  const { term, svc, pintados, fallbacks } = termFake(win);
  svc._isPaused = true;
  const modo = Render.pintarYa(term);
  assert.strictEqual(modo, 'fallback', 'pausado: no tiene sentido pintar un canvas invisible');
  assert.strictEqual(pintados.length, 0);
  assert.deepStrictEqual(fallbacks, [[0, 23]], 'degrada a term.refresh (xterm marca needsFullRefresh y pinta al volver)');
}

// ── 4b · pintarYa FORZADO (aunPausado): pinta aunque xterm se crea pausado ──
// Caso real (banco 2026-07-18): el wipe del RO del CanvasAddon cae cuando la card
// YA está visible pero el unpause del IntersectionObserver de xterm todavía no se
// entregó (frames atrasados bajo carga). svc.refreshRows tragaría el pedido (gate
// de pausa) → se puentea con el refresh directo del debouncer de la instancia.
{
  const win = ventanaFake();
  const { term, svc, pintados, fallbacks } = termFake(win);
  svc._isPaused = true;
  const modo = Render.pintarYa(term, true);
  assert.strictEqual(modo, 'sync', 'forzado: pinta aunque el service se crea pausado');
  assert.deepStrictEqual(pintados, [[0, 23]], 'viewport completo pintado YA');
  assert.strictEqual(fallbacks.length, 0, 'sin fallback: el paint fue real');
  assert.strictEqual(win.rafsPendientes(), 0, 'sin rAF pendiente (cancelado)');
  win.servirRaf(); win.dispararTimers();
  assert.strictEqual(pintados.length, 1, 'sin doble paint');
}

// ── 5 · pintarYa con internals rotos/futuros (upgrade de xterm): degrada, JAMÁS tira ──
{
  const fallbacks = [];
  const sinCore = { rows: 24, refresh(a, b) { fallbacks.push([a, b]); } };
  assert.strictEqual(Render.pintarYa(sinCore), 'fallback');
  assert.deepStrictEqual(fallbacks, [[0, 23]]);
  assert.strictEqual(Render.pintarYa(null), 'noop', 'sin term: no-op silencioso');
  const refreshRoto = { rows: 24, refresh() { throw new Error('x'); } };
  assert.doesNotThrow(() => Render.pintarYa(refreshRoto), 'ni siquiera un refresh roto debe propagar');
}

// ── 6 · blindarRenderStarvation: el rAF se starva → el timer pinta igual ──
{
  const win = ventanaFake();
  const { term, svc, pintados } = termFake(win);
  assert.strictEqual(Render.blindarRenderStarvation(term, 50), true);
  svc.refreshRows(0, 23);
  assert.strictEqual(win.rafsPendientes(), 1);
  assert.strictEqual(win.timersPendientes(), 1, 'cada frame agendado arma su fallback por timer');
  // El browser NUNCA sirve el rAF (starvation)… pero el timer corre como task normal:
  win.dispararTimers();
  assert.deepStrictEqual(pintados, [[0, 23]], 'el timer pintó — negro acotado a ~50ms, no 5s');
  assert.strictEqual(win.rafsPendientes(), 0, 'el rAF starved quedó cancelado');
  win.servirRaf();
  assert.strictEqual(pintados.length, 1, 'sin doble paint si el frame llega después');
}

// ── 7 · blindar: camino feliz (el rAF corre normal) → el timer se desarma, cero overhead ──
{
  const win = ventanaFake();
  const { term, svc, pintados } = termFake(win);
  Render.blindarRenderStarvation(term, 50);
  svc.refreshRows(2, 5);
  svc.refreshRows(1, 3);   // coalescing intacto: 2 refresh = 1 rAF = 1 timer
  assert.strictEqual(win.rafsPendientes(), 1);
  assert.strictEqual(win.timersPendientes(), 1);
  win.servirRaf();
  assert.deepStrictEqual(pintados, [[1, 5]], 'el wrapper no rompe el coalescing de rangos del debouncer');
  assert.strictEqual(win.timersPendientes(), 0, 'el paint por rAF desarma el timer');
  win.dispararTimers();
  assert.strictEqual(pintados.length, 1, 'timer ya desarmado: no re-pinta');
}

// ── 8 · blindar es idempotente + convive con pintarYa + respeta dispose ──
{
  const win = ventanaFake();
  const { term, svc, pintados } = termFake(win);
  Render.blindarRenderStarvation(term, 50);
  Render.blindarRenderStarvation(term, 50);   // doble aplicación NO apila wrappers
  svc.refreshRows(0, 23);
  assert.strictEqual(win.timersPendientes(), 1, 'un solo timer aunque se blinde dos veces');
  Render.pintarYa(term);                       // pinta sync → debe desarmar el timer también
  assert.deepStrictEqual(pintados, [[0, 23]]);
  assert.strictEqual(win.timersPendientes(), 0, 'pintarYa pasa por _innerRefresh → timer desarmado');
  win.dispararTimers(); win.servirRaf();
  assert.strictEqual(pintados.length, 1);

  // dispose del debouncer (cierre de terminal): el timer huérfano no pinta post-mortem.
  svc.refreshRows(0, 23);
  svc._renderDebouncer.dispose();
  win.dispararTimers();
  assert.strictEqual(pintados.length, 1, 'tras dispose el timer es no-op');
}

// ── 9 · blindar con internals rotos: devuelve false y no rompe nada ──
{
  assert.strictEqual(Render.blindarRenderStarvation({}, 50), false);
  assert.strictEqual(Render.blindarRenderStarvation(null, 50), false);
}

// ── 10 · debeRepintarAlMostrar: SOLO la transición oculta→visible ──
// Tercera capa del "negro hasta scrollear" (2026-07-11): el bitmap de un canvas
// OCULTO (display:none al maximizar otra card / app tapada) puede no sobrevivir
// (hibernación de canvas de Chromium/WebView2, presión de GPU en iGPU). xterm no
// se entera y al volver a verse NO repinta si nada marcó filas sucias → letras
// desaparecidas hasta que un scroll fuerza el refresh. Cura: repintar en la
// transición a visible. antes=null (primera observación) NO repinta (evita el
// doble paint del arranque).
{
  const D = Render.debeRepintarAlMostrar;
  assert.strictEqual(D(false, true), true);    // oculta → visible: repintar
  assert.strictEqual(D(true, true), false);    // sigue visible: nada
  assert.strictEqual(D(true, false), false);   // se ocultó: nada (repinta al volver)
  assert.strictEqual(D(false, false), false);  // sigue oculta
  assert.strictEqual(D(null, true), false);    // primera observación: nada
  assert.strictEqual(D(null, false), false);
}

// ── 11 · repintarAlMostrar sin IntersectionObserver (Node/browser viejo): null ──
{
  assert.strictEqual(Render.repintarAlMostrar(null, null), null);
  assert.strictEqual(Render.repintarAlMostrar({}, {}), null);   // sin IO en Node
}

// ── 12 · blindarContextoCanvas: contextrestored → repintado completo ──
// Chromium ≥99 emite contextlost/contextrestored en canvas 2D (GPU reset /
// descarte del backing store). Al restaurar, el bitmap está VACÍO y xterm no lo
// sabe → repintar. Con internals de xterm ausentes, pintarYa degrada a
// term.refresh — acá se espía ese fallback.
{
  const escuchas = [];
  const canvasFake = { addEventListener: (ev, cb) => escuchas.push({ ev, cb }) };
  const elemento = { querySelectorAll: () => [canvasFake, canvasFake] };
  const refrescos = [];
  const termFakeMin = { rows: 24, refresh: (a, b) => refrescos.push([a, b]) };
  const n = Render.blindarContextoCanvas(termFakeMin, elemento);
  assert.strictEqual(n, 2, 'blinda cada capa canvas');
  const restored = escuchas.filter(e => e.ev === 'contextrestored');
  assert.strictEqual(restored.length, 2);
  restored[0].cb();
  assert.deepStrictEqual(refrescos, [[0, 23]], 'contextrestored repinta el viewport completo');
  // Elemento sin canvases / nulo: 0, sin romper.
  assert.strictEqual(Render.blindarContextoCanvas(termFakeMin, { querySelectorAll: () => [] }), 0);
  assert.strictEqual(Render.blindarContextoCanvas(termFakeMin, null), 0);
}

// ── 13-18 · blindarWipeCanvas: CUARTA capa — el wipe async del propio CanvasAddon ──
// Causa raíz (banco 2026-07-18, stacks capturados): el CanvasAddon tiene SU PROPIO
// ResizeObserver (observeDevicePixelDimensions → _setCanvasDevicePixelDimensions →
// layer.resize) que llega 1-2 frames DESPUÉS del refit+pintarYa y reasigna
// canvas.width cuando el tamaño en device-pixels difiere por REDONDEO SUB-PIXEL
// (depende de la geometría exacta del tile → por eso "algunas veces"; con DPR
// fraccional de Windows, mucho más seguido). Ese re-set BORRA el bitmap; su pedido
// de redraw se pierde si el service está pausado (unpause del IO todavía en vuelo
// tras display:none→visible) o si otro wipe cae después del último refresh. El
// state-cache queda limpio → xterm cree que está todo pintado → letras invisibles
// PERMANENTES hasta que un scroll/output ensucia filas. Gatillos reales: eliminar
// terminal / maximizar-restaurar (cambian la geometría de los tiles).
// Cura: MutationObserver sobre width/height de cada canvas de capa — el microtask
// corre ANTES de que el compositor muestre el frame → repintado inmediato; pausado
// degrada a term.refresh (nfr → el unpause pinta). Cubre TODOS los wipers (el RO
// del addon, handleResize, y cualquier futuro).

// MutationObserver fake: captura targets/opts y permite disparar la entrega batcheada.
class MOFake {
  constructor(cb) { this.cb = cb; this.targets = []; MOFake.instancias.push(this); }
  observe(t, opts) { this.targets.push({ t, opts }); }
  disconnect() { this.desconectado = true; }
  entregar(records) { this.cb(records || [{}], this); }
}
MOFake.instancias = [];

// ── 13 · sin MutationObserver (Node pelado / browser prehistórico): null, sin romper ──
{
  const { term } = termFake(ventanaFake());
  const antes = global.MutationObserver;
  delete global.MutationObserver;
  assert.strictEqual(Render.blindarWipeCanvas(term, { querySelectorAll: () => [{}] }), null);
  if (antes !== undefined) global.MutationObserver = antes;
}

// ── 14 · observa cada capa canvas con attributeFilter width/height ──
{
  global.MutationObserver = MOFake;
  MOFake.instancias = [];
  const win = ventanaFake();
  const { term, pintados } = termFake(win);
  const c1 = {}, c2 = {}, c3 = {}, c4 = {};
  const elemento = { querySelectorAll: sel => (sel === 'canvas' ? [c1, c2, c3, c4] : []) };
  const obs = Render.blindarWipeCanvas(term, elemento);
  assert.ok(obs instanceof MOFake, 'devuelve el observer (disposer)');
  assert.strictEqual(MOFake.instancias.length, 1, 'UN observer por terminal (no uno por capa)');
  assert.strictEqual(obs.targets.length, 4, 'observa las 4 capas');
  for (const { opts } of obs.targets) {
    assert.strictEqual(opts.attributes, true);
    assert.deepStrictEqual(opts.attributeFilter, ['width', 'height'],
      'solo width/height: reasignarlos es EXACTAMENTE lo que borra el bitmap');
  }
  assert.strictEqual(pintados.length, 0, 'instalar no pinta nada');
  delete global.MutationObserver;
}

// ── 15 · wipe (batch de mutaciones de varias capas) → UN repintado sincrónico ──
{
  global.MutationObserver = MOFake;
  MOFake.instancias = [];
  const win = ventanaFake();
  const { term, pintados } = termFake(win);
  const obs = Render.blindarWipeCanvas(term, { querySelectorAll: () => [{}, {}] });
  // El addon re-setea width y height de sus 4 capas en la misma task → el observer
  // entrega TODOS los records juntos en un solo callback (semántica real de MO).
  obs.entregar([{}, {}, {}, {}, {}, {}, {}, {}]);
  assert.deepStrictEqual(pintados, [[0, 23]], 'un solo repintado completo por entrega, sincrónico');
  assert.strictEqual(win.rafsPendientes(), 0, 'sin rAF pendiente: el compositor no llega a mostrar el canvas vacío');
  delete global.MutationObserver;
}

// ── 16 · wipe con xterm "pausado": si la card está VISIBLE pinta igual; oculta → fallback ──
// La pausa de xterm puede estar RANCIA: tras display:none→visible (restaurar,
// eliminar) el unpause del IO viaja 1-N frames. El wipe del RO solo llega con la
// card con caja (visible) — pintar es correcto y evita el flash hasta el unpause.
// offsetParent es el discriminador que ya usa _repintarAlVolver (terminal.js).
{
  global.MutationObserver = MOFake;
  MOFake.instancias = [];
  const win = ventanaFake();
  const { term, svc, pintados, fallbacks } = termFake(win);
  const visible = { querySelectorAll: () => [{}], offsetParent: {} };
  const obs = Render.blindarWipeCanvas(term, visible);
  svc._isPaused = true;
  obs.entregar();
  assert.deepStrictEqual(pintados, [[0, 23]], 'visible + pausa rancia: pinta YA (no espera el unpause)');
  assert.strictEqual(fallbacks.length, 0);
}
{
  global.MutationObserver = MOFake;
  MOFake.instancias = [];
  const win = ventanaFake();
  const { term, svc, pintados, fallbacks } = termFake(win);
  const oculta = { querySelectorAll: () => [{}], offsetParent: null };
  const obs = Render.blindarWipeCanvas(term, oculta);
  svc._isPaused = true;
  obs.entregar();
  assert.strictEqual(pintados.length, 0, 'genuinamente oculta: no pinta un canvas invisible');
  assert.deepStrictEqual(fallbacks, [[0, 23]], 'degrada a term.refresh → needsFullRefresh → el unpause pinta');
  delete global.MutationObserver;
}

// ── 17 · sin canvases / elemento nulo / observe que tira: null o inofensivo ──
{
  global.MutationObserver = MOFake;
  MOFake.instancias = [];
  const { term } = termFake(ventanaFake());
  assert.strictEqual(Render.blindarWipeCanvas(term, { querySelectorAll: () => [] }), null,
    'sin capas canvas no hay nada que vigilar');
  assert.strictEqual(Render.blindarWipeCanvas(term, null), null);
  assert.strictEqual(Render.blindarWipeCanvas(null, { querySelectorAll: () => [{}] }), null);
  class MORoto { constructor() {} observe() { throw new Error('x'); } disconnect() {} }
  global.MutationObserver = MORoto;
  assert.doesNotThrow(() => Render.blindarWipeCanvas(term, { querySelectorAll: () => [{}] }));
  delete global.MutationObserver;
}

// ── 18 · el disposer corta la vigilancia (cierre de terminal, sin repintados post-mortem) ──
{
  global.MutationObserver = MOFake;
  MOFake.instancias = [];
  const { term } = termFake(ventanaFake());
  const obs = Render.blindarWipeCanvas(term, { querySelectorAll: () => [{}] });
  assert.strictEqual(typeof obs.disconnect, 'function');
  obs.disconnect();
  assert.strictEqual(obs.desconectado, true);
  delete global.MutationObserver;
}

console.log('terminal-render.test.js OK');
