// JARVIS — Eco local predictivo de la terminal.
//
// Pinta la tecla del usuario al INSTANTE, local, sin esperar el round-trip
// (tecla → WS → PTY → tmux → eco → WS → xterm). Es el mismo mecanismo que hace
// que una terminal nativa se sienta a 0ms: el eco no viaja. Crítico cuando el
// round-trip tiene PICOS (p90 ~600ms en el cruce browser↔WSL): la tecla aparece
// ya y el pico se vuelve invisible.
//
// Reconciliación con el eco REAL del server, que llega ~12-600ms después:
//  - Eco lineal: el server devuelve el char tal cual → coincide con lo predicho
//    → se saltea (no se pinta dos veces).
//  - REDIBUJO: el shell (readline) NO siempre hace eco lineal. Al navegar el
//    historial (↑/↓), editar en el medio de la línea o envolver una línea larga,
//    REDIBUJA con movimientos RELATIVOS de cursor (\b, \x1b[C, \x1b[K…). Ese
//    output NO es el eco del char predicho. Como nuestra predicción se pintó al
//    buffer y AVANZÓ el cursor real, dejarla ahí desincroniza el cursor y cada
//    redibujo relativo queda 1 columna corrido → "come" una letra y acumula
//    garble (bug del historial cazado 2026-07-06). Por eso, ante un output que no
//    es el eco de lo pendiente, devolvemos `undo` = cuántos chars predichos SIN
//    confirmar hay que DESPINTAR antes de dejarlo pasar; el caller emite la
//    secuencia de borrado y así el redibujo cae sobre un cursor sincronizado.
//
// Contabilidad pura (testeada en Node); el wiring con xterm (write local del
// char predicho, saltear bytes ya pintados, secuencia de borrado del `undo` y
// `flush()` antes de las teclas no imprimibles) vive en terminal.js.
(function (global) {
  'use strict';

  function esCharImprimible(ch) {
    if (typeof ch !== 'string' || ch.length !== 1) return false;
    const code = ch.charCodeAt(0);
    // Imprimible de 1 code unit: ASCII + Latin-1 (á é í ó ú ñ ü ¿ ¡) + resto del BMP.
    // El eco real del shell devuelve el MISMO char → conciliar() lo saltea igual que
    // el ASCII. Se excluye: C0/DEL/C1 (control), mitades de surrogate (no son 1 char
    // válido) y combining marks (se predicen mal solas — los acentos del español son
    // precompuestos en Latin-1, no combinantes).
    if (code < 0x20) return false;
    if (code >= 0x7f && code <= 0x9f) return false;
    if (code >= 0xd800 && code <= 0xdfff) return false;
    if (code >= 0x0300 && code <= 0x036f) return false;
    return true;
  }

  function crearEcoLocal(opts) {
    const o = opts || {};
    const maxPendientes = Number.isFinite(o.maxPendientes) ? o.maxPendientes : 16;
    let pendientes = [];   // chars predichos (pintados local), sin confirmar

    // ¿predecir este char? Sólo un char imprimible simple y si hay lugar.
    function predecir(ch) {
      if (pendientes.length >= maxPendientes) return false;
      if (!esCharImprimible(ch)) return false;
      pendientes.push(ch);
      return true;
    }

    // Procesa output del server contra las predicciones pendientes.
    //   saltear: nº de bytes del PREFIJO de `data` ya pintados (el caller los
    //            descarta antes de escribir a xterm → evita el doble char).
    //   undo:    nº de chars predichos SIN confirmar que el caller debe DESPINTAR
    //            (borrado + retroceso de cursor) antes de escribir `data`, porque
    //            ese output no es su eco lineal (redibujo con cursor relativo). Si
    //            no se despintan, el cursor queda corrido y el redibujo garbla.
    function conciliar(data) {
      if (pendientes.length === 0) return { saltear: 0, undo: 0 };
      let i = 0;
      while (pendientes.length > 0 && i < data.length && data[i] === pendientes[0]) {
        i++; pendientes.shift();
      }
      let undo = 0;
      if (pendientes.length > 0 && i < data.length) {
        // El output ya no es el eco de lo que queda predicho (redibujo de readline
        // u output no relacionado): las predicciones aún pintadas hay que borrarlas
        // para que el output caiga sobre un buffer/cursor sincronizado.
        undo = pendientes.length;
        pendientes = [];
      }
      // Si i >= data.length con predicciones restantes: eco partido en chunks — las
      // dejamos pendientes (el próximo chunk las confirma), sin undo ni flicker.
      return { saltear: i, undo };
    }

    // Descarta TODA predicción pendiente y devuelve cuántas había. El caller lo usa
    // ANTES de mandar una tecla no imprimible (flechas/enter/backspace/ctrl/tab):
    // esas teclas gatillan un redibujo del shell, así que despintamos primero para
    // que el redibujo no arrastre un cursor corrido.
    function flush() {
      const n = pendientes.length;
      pendientes = [];
      return n;
    }

    return {
      predecir,
      conciliar,
      flush,
      pendientesN() { return pendientes.length; },
    };
  }

  const api = { crearEcoLocal, esCharImprimible };
  global.TerminalEcoLocal = Object.assign(global.TerminalEcoLocal || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
