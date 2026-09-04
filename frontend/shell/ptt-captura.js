'use strict';
// ─── Captura de bindings del PTT: las decisiones puras del mouse ─────────────
// Cuando el usuario aprieta "tocá para reasignar" (Configuración → Voz), el motor
// de workspace.js escucha el próximo apretón para guardarlo como binding. Acá
// vive el criterio de QUÉ apretón cuenta — sin DOM, testeable en Node.
//
// Regla: el binding se toma APRETANDO DONDE SEA, también encima del propio botón
// de reasignar (antes se ignoraba todo mousedown que cayera sobre él, así que
// para asignar Mouse·adelante había que salirse del botón — no era descubrible).
// La única excepción es el click IZQUIERDO sobre la UI de la captura (el botón de
// reasignar, el reset, el cerrar): ese click es la UI operándose a sí misma —
// notablemente el segundo click de un doble-click, que si no dejaba el
// push-to-talk en "click izquierdo" y con eso el workspace inusable.
// Patrón UMD _pure, espeja a ptt-fijado.js.

(function (root) {

  // Botones laterales del mouse (3=atrás, 4=adelante): el browser navega con
  // ellos, así que su acción default se cancela SIEMPRE mientras la app vive.
  function esBotonLateral(button) { return button === 3 || button === 4; }

  // ¿Este mousedown se guarda como binding?
  //   button      — e.button (0=izq, 1=medio, 2=der, 3=atrás, 4=adelante)
  //   enBotonBind — el apretón cayó sobre el botón que abre la captura
  //   enUiCaptura — cayó sobre el reset / cerrar (la UI que sigue viva mientras capturamos)
  // → 'bindear' | 'ignorar'
  function decisionMouse({ button, enBotonBind, enUiCaptura }) {
    if (button !== 0) return 'bindear';                    // medio/der/atrás/adelante: donde sea
    if (enBotonBind || enUiCaptura) return 'ignorar';      // el click izq es la UI, no un binding
    return 'bindear';
  }

  // ¿Hay que comerse este mouseup/auxclick/click?
  //   capturado — ya tomamos el mousedown de ESTE apretón: sus eventos de cierre
  //               todavía vienen en camino y le pegarían al botón de reasignar,
  //               reabriendo la captura recién cerrada.
  function debeTragar({ button, capturado }) {
    return !!capturado || esBotonLateral(button);
  }

  const api = { esBotonLateral, decisionMouse, debeTragar };
  api._pure = api;

  root.PttCaptura = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;

})(typeof window !== 'undefined' ? window : globalThis);
