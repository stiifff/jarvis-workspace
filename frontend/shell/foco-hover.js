'use strict';
// ─── Foco de teclado por hover: el Enter va a la terminal que estás mirando ──
// Hermano de voice-target.js: si el MOUSE apunta el destino de la voz, apunta
// también el del teclado. Caso real (pedido 2026-07-23): dictás/pegás un mensaje
// en una terminal, queda escrito en el prompt del agente, y para mandarlo tenías
// que clickear la card antes de apretar Enter.
// Lógica PURA (sin DOM); el cableado vive en workspace.js. Patrón UMD _pure.

(function (root) {

  // Mudar el foco es más invasivo que apuntar la voz: si estás tipeando en una
  // terminal, rozar el mouse contra la card de al lado NO se lleva las teclas
  // hasta que pares. Ventana desde la última tecla, y cada tecla la renueva:
  // 800 ms es 3-4× el hueco entre teclas de un tipeo corrido (queda protegido
  // de punta a punta) y no se hace notar cuando movés el mouse a propósito para
  // seguir escribiendo en otra terminal.
  const GRACIA_TIPEO_MS = 800;

  // Entradas (ya resueltas por el caller):
  //   hoverTermId        — terminal bajo el cursor (ya pasó el dwell) o null
  //   foco               — dónde está el teclado: 'terminal' | 'editable' | 'libre'
  //                        ('editable' = composer de Jarvis, editor, inputs, iframes)
  //   focoTermId         — si foco==='terminal', cuál
  //   desdeUltimaTeclaMs — ms desde la última tecla tipeada en una terminal
  // Devuelve el id a enfocar, o null = no tocar el foco.
  function decidirFocoPorHover({ hoverTermId, foco, focoTermId, desdeUltimaTeclaMs }) {
    // Cursor fuera de toda terminal: el foco se queda donde está (no lo
    // devolvemos al vacío — si salís de la card y seguís tipeando, le seguís
    // hablando a la misma terminal, igual que el destino de la voz).
    if (hoverTermId == null) return null;
    // Un campo de texto en uso es intocable: lo que estás escribiendo ahí no se
    // puede ir a un PTY por apoyar el mouse en otro lado.
    if (foco === 'editable') return null;
    // Ya está enfocada.
    if (foco === 'terminal' && focoTermId === hoverTermId) return null;
    // Tipeando en otra terminal: esperá a que pare.
    if (foco === 'terminal' && (desdeUltimaTeclaMs ?? Infinity) < GRACIA_TIPEO_MS) return null;
    return hoverTermId;
  }

  const api = { decidirFocoPorHover, GRACIA_TIPEO_MS };
  api._pure = api;

  root.FocoHover = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;

})(typeof window !== 'undefined' ? window : globalThis);
