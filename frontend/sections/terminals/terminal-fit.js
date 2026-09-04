'use strict';
// Cálculo REAL de filas/columnas para fitear xterm a una card de terminal.
//
// Por qué existe (NO usar fitAddon.fit() crudo): `.terminal-body` es
// box-sizing:border-box y reserva la píldora flotante con `padding: 39px 4px 4px`.
// El FitAddon de xterm 5.3 toma como alto disponible getComputedStyle(parent).height
// — que en border-box DEVUELVE la altura CON el padding incluido (850px en vez de
// 807px) — y le resta el padding del elemento `.xterm` (que es 0, el padding está
// en el PADRE). Resultado: cuenta ~1 fila de más; esa fila sobresale por debajo del
// área visible y la clipea el `overflow:hidden` del body → "no se ve el contenido
// de la parte de abajo" (composer/estado del agente cortado). Acá restamos el
// padding REAL del contenedor antes de dividir por la celda. Ver
// [[tmux-size-clamping]] (esto es CLIPPING del fondo, distinto del garble).
(function (global) {
  // Piso COMUNICABLE (2026-07-02, auditoría "cortada a media card"): el gate de
  // envío a tmux (onResize / refitTerminal en terminal.js) filtra cols<20 ||
  // rows<5 como degenerado. Si xterm se aplicara un tamaño por debajo de eso,
  // tmux NUNCA se enteraría → divergencia silenciosa xterm≠tmux (pasaba con la
  // celda mínima del mosaico, 160×90px). Regla: xterm jamás queda en un tamaño
  // que no se le puede comunicar a tmux; una card minúscula recorta el
  // contenido con overflow:hidden (preferible a desincronizar).
  const MIN_COLS = 20;
  const MIN_ROWS = 5;

  // clientW/clientH: lo que devuelve el DOM (content + padding, sin border ni
  // scrollbar). padW/padH: padding total horizontal/vertical del contenedor.
  // cellW/cellH: tamaño CSS de una celda (term._core._renderService.dimensions.css.cell).
  // Devuelve {cols, rows} clampeados al piso comunicable; nunca NaN/Infinity.
  function dimsReales(clientW, clientH, padW, padH, cellW, cellH) {
    const availW = clientW - padW;
    const availH = clientH - padH;
    const cols = (cellW > 0 && availW > 0) ? Math.max(MIN_COLS, Math.floor(availW / cellW)) : MIN_COLS;
    const rows = (cellH > 0 && availH > 0) ? Math.max(MIN_ROWS, Math.floor(availH / cellH)) : MIN_ROWS;
    return { cols, rows };
  }

  // Igual que dimsReales pero en PÍXELES DE DISPOSITIVO, que es la unidad del
  // buffer del canvas — lo único que se dibuja de verdad.
  //
  // factor = px de dispositivo por px CSS = zoom de la Escala × devicePixelRatio.
  // cellDevW/cellDevH: dimensions.device.cell (misma unidad que el buffer).
  // Cuando el factor NO es entero (toda escala que no sea 100% en pantalla común)
  // el navegador redondea el buffer y el cálculo puede pasarse por UN píxel; ese
  // píxel es una fila entera que no se dibuja nunca —justo la del composer del
  // agente—, así que ahí se reserva 1px. Con factor entero no se reserva nada y
  // el resultado es idéntico al de dimsReales.
  function dimsDispositivo(clientW, clientH, padW, padH, cellDevW, cellDevH, factor) {
    const f = (Number.isFinite(factor) && factor > 0) ? factor : 1;
    const margen = Number.isInteger(f) ? 0 : 1;
    return dimsReales((clientW - padW) * f - margen, (clientH - padH) * f - margen,
                      0, 0, cellDevW, cellDevH);
  }

  const api = { MIN_COLS, MIN_ROWS, dimsReales, dimsDispositivo };
  global.TerminalFit = Object.assign(global.TerminalFit || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
