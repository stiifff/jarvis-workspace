// JARVIS — Medidor de latencia de ECO de la terminal.
//
// Mide el round-trip REAL de lo que el usuario tipea: tecla → WS → PTY → tmux →
// eco → WS → xterm. Es la herramienta que rompe el ciclo de "lo arreglaron y no":
// muestra los ms REALES en el browser del usuario (incluido el cruce
// browser↔WSL, que no se puede medir desde headless), no una suposición.
//
// Contabilidad pura (testeada en Node); el wiring con el WS y el display vive en
// terminal.js: marcarInput() en term.onData, marcarOutput() en ws.onmessage.
(function (global) {
  'use strict';

  // Mantener un input "pendiente" (esperando su eco) y, al llegar el primer
  // output, registrar el round-trip. Sólo el PRIMER output tras un input cuenta:
  // así el flood del agente (output sin tecla previa) no contamina la medición.
  function crearMedidor(opts) {
    const ventana = (opts && Number.isFinite(opts.ventana) && opts.ventana > 0)
      ? opts.ventana : 50;
    let pendiente = null;   // ts del primer input de la ráfaga, esperando eco
    const muestras = [];    // ms de round-trip, acotado a `ventana`

    function marcarInput(ts) {
      if (!Number.isFinite(ts)) return;
      // Guardar el PRIMERO de una ráfaga: si tipeás varias teclas seguidas, el
      // primer eco que vuelve es el de la primera tecla.
      if (pendiente === null) pendiente = ts;
    }

    function marcarOutput(ts) {
      if (pendiente === null || !Number.isFinite(ts)) return null;
      const ms = ts - pendiente;
      pendiente = null;                          // consumido (o descartado)
      if (!Number.isFinite(ms) || ms < 0) return null;   // reloj raro: no medir
      muestras.push(ms);
      if (muestras.length > ventana) muestras.shift();
      return ms;
    }

    // nearest-rank: ceil(p·n) en índice 1-based.
    function percentil(ordenado, p) {
      const rank = Math.ceil(p * ordenado.length);
      return ordenado[Math.max(0, rank - 1)];
    }

    function stats() {
      const n = muestras.length;
      if (n === 0) return { n: 0, ultima: null, p50: null, p90: null };
      const ordenado = muestras.slice().sort((a, b) => a - b);
      return {
        n,
        ultima: muestras[n - 1],
        p50: percentil(ordenado, 0.5),
        p90: percentil(ordenado, 0.9),
      };
    }

    return { marcarInput, marcarOutput, stats };
  }

  const api = { crearMedidor };
  global.TerminalLatencia = Object.assign(global.TerminalLatencia || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
