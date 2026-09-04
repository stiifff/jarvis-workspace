// JARVIS — Lógica pura del paste (Ctrl+V) en terminales.
//
// Por qué existe: pegar una imagen mandando \x16 a la CLI (su paste nativo)
// la obligaba a leer el clipboard de Windows vía interop WSL→powershell.exe:
// 3.5s+ medidos SOLO el arranque de .NET, más la conversión/transferencia de
// la imagen → el "Pasting..." eterno de Claude Code. El browser YA tiene los
// bytes de la imagen en el evento paste, así que el camino rápido es subirla
// a POST /api/terminals/{id}/upload-image (milisegundos) y pegar la ruta con
// bracketed paste. El \x16 queda como FALLBACK si la subida falla.
//
// Acá vive la parte decisoria (testeada en Node); el wiring con el DOM/WS
// está en terminal.js (handler 'paste' del container).
(function (global) {
  'use strict';

  // Decide qué hacer con el contenido de un evento paste.
  //   texto  → pegar el texto (bracketed paste)
  //   imagen → subir el item `indice` y pegar la ruta
  //   nada   → ignorar el evento
  // TEXTO SIEMPRE GANA sobre imagen: Windows pega image/*+text/plain a la vez
  // al copiar desde Slack/Excel/web (lo común al programar); si ganara la
  // imagen se perdería el texto copiado.
  function planDePaste({ texto, items } = {}) {
    if (texto) return { accion: 'texto' };
    const lista = items || [];
    for (let i = 0; i < lista.length; i++) {
      const it = lista[i];
      if (it && it.kind === 'file' && typeof it.type === 'string' && it.type.startsWith('image/')) {
        return { accion: 'imagen', indice: i };
      }
    }
    return { accion: 'nada' };
  }

  // Nombre de archivo para la imagen pegada: los screenshots del clipboard
  // vienen sin file.name → clipboard-<ts>.<ext del mime> (default png).
  function nombreImagenPegada({ nombre, mime, ts } = {}) {
    if (nombre) return nombre;
    const ext = ((mime || '').split('/')[1] || 'png').toLowerCase();
    return `clipboard-${ts}.${ext}`;
  }

  // Qué mandar al PTY si la subida de la imagen falla. En terminales de
  // agente, \x16 dispara el paste nativo de la CLI (lee el clipboard del OS
  // vía interop — lento, pero la imagen sigue ahí: red de seguridad). En bash
  // (`manual`) no hay quién lea el clipboard → null (mostrar error).
  function fallbackImagenPaste(tipoIa) {
    return tipoIa === 'manual' ? null : '\x16';
  }

  const api = { planDePaste, nombreImagenPegada, fallbackImagenPaste };
  global.TerminalPaste = Object.assign(global.TerminalPaste || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
