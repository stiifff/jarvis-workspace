// JARVIS — Lógica pura del overlay de drag & drop de archivos sobre terminales.
//
// Al arrastrar un archivo sobre una card de terminal aparece un overlay CENTRAL
// que anuncia qué se va a soltar (imagen / video / archivo). Ese cartel se
// decide MIRANDO SOLO los tipos MIME que el browser expone durante `dragover`:
// `DataTransferItem.kind` y `.type` SÍ están disponibles antes del drop (los
// bytes y el file.name recién aparecen en el `drop`). Por eso podemos distinguir
// una imagen de un mp4 mientras el archivo todavía flota sobre la card.
//
// Acá vive la parte decisoria (testeada en Node); el wiring con el DOM (crear el
// overlay, mostrarlo/ocultarlo, subir el archivo) está en terminal.js.
(function (global) {
  'use strict';

  // Clasifica el arrastre en la CLASE que decide el mensaje del overlay:
  //   'imagen'  → hay un archivo image/*
  //   'video'   → hay un archivo video/*  (mp4, mov, webm…)
  //   'archivo' → hay archivos, pero de otro tipo (o de tipo desconocido)
  //   null      → NO hay archivos (arrastre de texto/selección/URL) → sin overlay
  // Gana el PRIMER archivo del dataTransfer (un arrastre normal es de un archivo;
  // Windows suele anteponer un item 'string' text/plain que ignoramos).
  function clasificarArrastre(dataTransfer) {
    if (!dataTransfer) return null;
    const items = dataTransfer.items;
    let hayArchivo = false;
    if (items && items.length) {
      for (let i = 0; i < items.length; i++) {
        const it = items[i];
        if (!it || it.kind !== 'file') continue;
        hayArchivo = true;
        const t = (it.type || '').toLowerCase();
        if (t.indexOf('image/') === 0) return 'imagen';
        if (t.indexOf('video/') === 0) return 'video';
      }
      if (hayArchivo) return 'archivo';   // hay archivo(s) pero de otro tipo
    }
    // Fallback: algunos browsers no pueblan items[] en dragover, sólo types[].
    const types = dataTransfer.types ? Array.prototype.slice.call(dataTransfer.types) : [];
    if (types.indexOf('Files') !== -1) return 'archivo';
    return null;
  }

  // Mensaje del overlay para cada clase. Fuente en ESPAÑOL (rioplatense); lo
  // traduce frontend/shared/i18n.js contra su diccionario. `titulo` = línea
  // grande; `hint` = la línea chica de abajo.
  const _MENSAJES = {
    imagen:  { titulo: 'Soltá la imagen acá', hint: 'para adjuntarla a la terminal' },
    video:   { titulo: 'Soltá el video acá',  hint: 'para adjuntarlo a la terminal' },
    archivo: { titulo: 'Soltá el archivo acá', hint: 'para adjuntarlo a la terminal' },
  };
  function mensajeDrop(clase) {
    return _MENSAJES[clase] || null;
  }

  // En el DROP: ¿este MIME se sube al backend (imagen/video) y se pega su ruta
  // absoluta, o se manda sólo el nombre del archivo? Sólo imagen y video son
  // materializables útiles para las CLIs (Claude lee la imagen; la ruta del
  // video sirve para ffmpeg y demás).
  function esSubible(mime) {
    const t = (mime || '').toLowerCase();
    return t.indexOf('image/') === 0 || t.indexOf('video/') === 0;
  }

  const api = { clasificarArrastre, mensajeDrop, esSubible };
  global.TerminalDrop = Object.assign(global.TerminalDrop || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
