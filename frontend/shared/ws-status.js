// JARVIS — Indicador de estado del WebSocket de eventos (Sprint 3).
// El WS ya reconectaba (3s fijo); esto le da backoff exponencial + un dot
// visible en la barra que aparece SOLO cuando NO está conectado (regla
// idle-pip: cero ruido cuando todo está sano).
(function (global) {
  'use strict';

  // Backoff exponencial: 1.5s, 3s, 6s, 12s, 24s, cap 30s. El 1er intento bajó de
  // 3s→1.5s: un blip del server (reinicio rápido) reconecta el doble de rápido. Puro/testeable.
  function proximoDelay(intentos) {
    const n = Math.max(0, intentos | 0);
    return Math.min(1500 * Math.pow(2, n), 30000);
  }

  const pure = { proximoDelay };
  global.WsStatus = Object.assign(global.WsStatus || {}, { _pure: pure });
  if (typeof document === 'undefined') return;  // tests Node: solo _pure

  function _dot() { return document.getElementById('jw-ws-dot'); }

  // estado ∈ 'conectado' | 'reconectando' | 'caido'
  global.WsStatus.set = (estado) => {
    const el = _dot();
    if (!el) return;
    el.dataset.estado = estado;
    if (estado === 'conectado') { el.hidden = true; el.removeAttribute('title'); return; }
    el.hidden = false;
    el.title = estado === 'reconectando' ? 'Reconectando…' : 'Sin conexión con el server';
  };
})(typeof window !== 'undefined' ? window : globalThis);
