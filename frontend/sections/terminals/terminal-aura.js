// JARVIS — Aura de notificación en cards de terminal (spec 2026-06-07).
// Prende cuando el agente terminó / espera respuesta y NO estás en esa card;
// se apaga con click sobre la card o cuando el agente retoma (agente_trabajando).
(function (global) {
  'use strict';

  // Mismos momentos en que suena un sonido de esa terminal, más 'mailbox_aviso'
  // ("tenés un mensaje de otro agente"): aura sutil, sin sonido — la enciende el
  // WS mailbox_aviso que el backend emite por destinatario concreto.
  const PRENDEN = new Set(['agente_termino', 'agente_espera',
                           'TASK_DONE', 'TASK_BLOCKED', 'TASK_ERROR',
                           'mailbox_aviso']);

  // Lógica pura: (set de ids con aura, acción) → set nuevo. No muta la entrada.
  function nextSet(set, accion) {
    const s = new Set(set || []);
    if (accion.tipo === 'evento') {
      if (PRENDEN.has(accion.evento) && accion.terminalId != null
          && accion.terminalId !== accion.activaId) s.add(accion.terminalId);
      return s;
    }
    if (accion.tipo === 'apagar') { s.delete(accion.terminalId); return s; }
    if (accion.tipo === 'reset')  return new Set();
    return s;
  }

  const pure = { PRENDEN, nextSet };
  global.TerminalAura = Object.assign(global.TerminalAura || {}, { _pure: pure });

  if (typeof document === 'undefined') return;  // tests Node: solo _pure

  let _set = new Set();

  function _dispatch(accion) {
    const antes = _set;
    _set = nextSet(_set, accion);
    for (const id of _set) if (!antes.has(id))
      document.getElementById(`terminal-card-${id}`)?.classList.add('con-aura');
    for (const id of antes) if (!_set.has(id))
      document.getElementById(`terminal-card-${id}`)?.classList.remove('con-aura');
  }

  // Evento WS de notificación → prender (salvo que la card sea la activa:
  // el aura es para terminales donde NO estás).
  global.TerminalAura.notificar = (evento, terminalId) => {
    const activa = document.querySelector('.terminal-card.activa');
    const activaId = activa ? parseInt(activa.id.replace('terminal-card-', ''), 10) : null;
    _dispatch({ tipo: 'evento', evento, terminalId, activaId });
  };
  global.TerminalAura.apagar = (terminalId) => _dispatch({ tipo: 'apagar', terminalId });
  global.TerminalAura.reset  = () => _dispatch({ tipo: 'reset' });
})(typeof window !== 'undefined' ? window : globalThis);
