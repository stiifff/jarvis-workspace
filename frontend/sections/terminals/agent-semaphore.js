// JARVIS — Semáforo de agentes en la barra (Sprint 3).
// Pill compacto que muestra cuántos agentes están trabajando / esperando /
// en error, reusando los colores de pip de las cards. Oculto si todos idle.
(function (global) {
  'use strict';

  // Estados de setTerminalStatus (workspace.js): idle | thinking | watching | error.
  // thinking = trabajando (verde) · watching = esperando (ámbar) · error (rojo).
  // idle no cuenta. Puro y testeable: map terminalId→estado → conteos.
  function resumir(mapEstados) {
    const r = { trabajando: 0, esperando: 0, error: 0 };
    const vals = mapEstados instanceof Map ? mapEstados.values()
                                           : Object.values(mapEstados || {});
    for (const estado of vals) {
      if (estado === 'thinking') r.trabajando++;
      else if (estado === 'watching') r.esperando++;
      else if (estado === 'error') r.error++;
    }
    return r;
  }

  const pure = { resumir };
  global.AgentSemaphore = Object.assign(global.AgentSemaphore || {}, { _pure: pure });
  if (typeof document === 'undefined') return;  // tests Node: solo _pure

  const _estados = new Map();   // terminalId → estado

  function _render() {
    const el = document.getElementById('jw-semaphore');
    if (!el) return;
    const r = resumir(_estados);
    const total = r.trabajando + r.esperando + r.error;
    if (total === 0) { el.hidden = true; el.innerHTML = ''; return; }
    const partes = [];
    if (r.trabajando) partes.push(`<span class="jw-sem-it jw-sem-work">● ${r.trabajando}</span>`);
    if (r.esperando)  partes.push(`<span class="jw-sem-it jw-sem-wait">◐ ${r.esperando}</span>`);
    if (r.error)      partes.push(`<span class="jw-sem-it jw-sem-err">✕ ${r.error}</span>`);
    el.innerHTML = partes.join('');
    el.title = `${r.trabajando} trabajando · ${r.esperando} esperando · ${r.error} en error`;
    el.hidden = false;
  }

  global.AgentSemaphore.set = (terminalId, estado) => {
    if (terminalId == null) return;
    if (!estado || estado === 'idle') _estados.delete(terminalId);
    else _estados.set(terminalId, estado);
    _render();
  };
  global.AgentSemaphore.quitar = (terminalId) => { _estados.delete(terminalId); _render(); };
  global.AgentSemaphore.reset  = () => { _estados.clear(); _render(); };
})(typeof window !== 'undefined' ? window : globalThis);
