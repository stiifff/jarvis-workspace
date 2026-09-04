// JARVIS — Ciclo de vida del cierre del menú contextual de las terminales
// (copiar/pegar/seleccionar todo/limpiar). Lógica pura, testeada en Node;
// el armado del menú (DOM + acciones) vive en terminal.js.
//
// Por qué existe: la versión anterior armaba el cierre con listeners
// {once:true} sobre document → el PRIMER mousedown en cualquier lado los
// consumía aunque NO cerrara el menú (mousedown dentro del menú, en el
// padding, o apretar un ítem y soltar afuera) y el menú quedaba clavado
// para siempre. Acá los listeners son PERSISTENTES mientras el menú viva
// y se desarman explícitamente al cerrar.
(function (global) {
  'use strict';

  // Arma el cierre por mousedown-afuera y Escape sobre `doc`.
  // Capture-phase: un stopPropagation en burbuja (xterm en mouse-mode,
  // drag del layout) no puede dejarnos sin enterarnos del click.
  // Devuelve desarmar(); quien cierra el menú DEBE invocarla (en terminal.js
  // la llama _cerrarMenuContextual vía menu._desarmarCierre).
  function armarCierre(doc, menu, cerrar) {
    const onDown = ev => { if (!menu.contains(ev.target)) cerrar(); };
    const onKey  = ev => { if (ev.key === 'Escape') cerrar(); };
    doc.addEventListener('mousedown', onDown, true);
    doc.addEventListener('keydown',   onKey,  true);
    return function desarmar() {
      doc.removeEventListener('mousedown', onDown, true);
      doc.removeEventListener('keydown',   onKey,  true);
    };
  }

  const api = { armarCierre };
  global.TerminalCtxmenu = Object.assign(global.TerminalCtxmenu || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
