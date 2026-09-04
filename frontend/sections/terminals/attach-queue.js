// JARVIS — Cola de attaches de terminales (anti-freeze del re-attach masivo).
//
// Tras un reload con 6-9 terminales (post-update, F5, cambio de proyecto) los
// WS se abrían TODOS a la vez: N seeds de hasta 2000 líneas con colores llegan
// juntos y xterm los parsea + N canvas se crean/redimensionan en el mismo
// instante en el main thread (y N capture-pane simultáneos del lado tmux en un
// server recién re-execado) → el workspace quedaba CONGELADO 3-5s apenas volvía
// (bug del update, 2026-07-11). Esta cola escalona la apertura: a lo sumo
// CONCURRENCIA attaches "en vuelo" (WS abierto esperando su seed); el resto
// espera su turno en FIFO. El slot se libera con el PRIMER dato del WS (el seed
// ya viajó), al cerrarse el WS, al cancelar (card eliminada) o por el failsafe
// de timeout — la cola NUNCA puede quedar trabada.
//
// Lógica pura (testeada en Node); el wiring vive en terminal.js:
//   _fitYAbrir → pedir(id, abrirWS) · onmessage 1º dato → listo(id)
//   onclose → listo(id) · desconectarTerminal → cancelar(id)
(function (global) {
  'use strict';

  // 2 en vuelo: paralelismo sin tormenta (en 4 cores, 2 capture-pane + 2 parses
  // de seed conviven bien). Con 1-2 terminales la cola es pass-through.
  const CONCURRENCIA = 2;
  // Failsafe por slot: si el seed nunca llega (WS colgado sin onclose todavía),
  // el slot se libera solo — el attach sigue su vida, la cola sigue fluyendo.
  const TIMEOUT_SLOT_MS = 6000;

  function crearCola(opts) {
    const conc = (opts && Number.isFinite(opts.concurrencia) && opts.concurrencia > 0)
      ? opts.concurrencia : CONCURRENCIA;
    const tmo = (opts && Number.isFinite(opts.timeoutMs) && opts.timeoutMs > 0)
      ? opts.timeoutMs : TIMEOUT_SLOT_MS;
    const espera = [];           // [{id, fn}] en FIFO
    const activos = new Map();   // id → timer del failsafe
    let usada = false;           // ¿alguna vez se pidió un attach? (overlay post-reload)
    let hechos = 0;              // attaches que YA soltaron su slot (progreso del overlay)

    function _despachar() {
      while (activos.size < conc && espera.length) {
        const { id, fn } = espera.shift();
        activos.set(id, setTimeout(() => listo(id), tmo));
        try { fn(); } catch (_) { listo(id); }   // un fn roto no retiene su slot
      }
    }

    // Pide turno para el attach de `id`. Un pedido nuevo del MISMO id (reconexión
    // con backoff) reemplaza al viejo: el fn anterior en espera se descarta y el
    // slot activo anterior se libera (ese WS ya murió o va a morir).
    function pedir(id, fn) {
      usada = true;
      cancelar(id);
      espera.push({ id, fn });
      _despachar();
    }

    // El attach de `id` ya no ocupa slot (llegó su seed / cerró su WS). Idempotente.
    function listo(id) {
      const t = activos.get(id);
      if (t === undefined) return;
      clearTimeout(t);
      activos.delete(id);
      hechos++;                  // corrió y soltó su slot → progreso del overlay
      _despachar();
    }

    // La card de `id` se fue (desconectarTerminal): sacarlo de la espera o
    // liberar su slot.
    function cancelar(id) {
      const i = espera.findIndex(e => e.id === id);
      if (i >= 0) espera.splice(i, 1);
      listo(id);
    }

    function estado() { return { pendientes: espera.length, activos: activos.size, usada, hechos }; }

    return { pedir, listo, cancelar, estado };
  }

  const api = { CONCURRENCIA, TIMEOUT_SLOT_MS, crearCola };
  // Instancia compartida del workspace (terminal.js y el overlay del updater la usan).
  const _cola = crearCola();
  api.pedir = (id, fn) => _cola.pedir(id, fn);
  api.listo = (id) => _cola.listo(id);
  api.cancelar = (id) => _cola.cancelar(id);
  api.estado = () => _cola.estado();

  global.TerminalAttach = Object.assign(global.TerminalAttach || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
