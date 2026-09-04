// JARVIS — Diagnóstico de GARBLE ("letras rotas") en la terminal.
//
// El garble del proyecto es 100% render-side: tmux dibuja bien la pantalla pero
// xterm muestra basura (lo cura tipear/F5). Nunca se reprodujo fuera de la GPU
// real del usuario, así que se debugeó a ciegas. Esto compara el grid que tmux
// DIBUJA contra lo que xterm muestra y deja las filas EXACTAS que difieren —
// para cazar la causa con evidencia en la máquina del usuario.
//
// Contabilidad pura (testeada en Node); el wiring (leer el buffer de xterm,
// pedir el snapshot de tmux, juntar renderer/cols/rows y descargar) vive en
// terminal.js, detrás de un atajo de captura.
(function (global) {
  'use strict';

  // tmux rellena cada fila con espacios hasta el ancho del pane; xterm no.
  // Comparar sin el relleno de la derecha evita falsos positivos.
  function rstrip(s) {
    return (typeof s === 'string' ? s : '').replace(/\s+$/, '');
  }

  // Compara dos grids de pantalla (arrays de filas) fila por fila.
  //   { iguales, diferencias: [{ i, x, t }] }
  //   i = índice de fila, x = lo que muestra xterm, t = lo que dibuja tmux.
  function compararGrid(xterm, tmux) {
    const xs = Array.isArray(xterm) ? xterm : [];
    const ts = Array.isArray(tmux) ? tmux : [];
    const n = Math.max(xs.length, ts.length);
    const diferencias = [];
    for (let i = 0; i < n; i++) {
      const x = rstrip(xs[i]);
      const t = rstrip(ts[i]);
      if (x !== t) diferencias.push({ i, x, t });
    }
    return { iguales: diferencias.length === 0, diferencias };
  }

  const api = { compararGrid, rstrip };
  global.TerminalDiagnostico = Object.assign(global.TerminalDiagnostico || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
