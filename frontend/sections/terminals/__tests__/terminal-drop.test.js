'use strict';
// Tests de la lógica pura del overlay de drag&drop de archivos sobre terminales.
// Contexto: al arrastrar un archivo sobre una card de terminal aparece un
// overlay CENTRAL que anuncia qué soltar (imagen / video / archivo). El tipo se
// decide MIRANDO SOLO los tipos MIME que el browser expone durante dragover
// (item.kind/type SÍ están antes del drop; los bytes y el nombre recién en el
// drop). El mensaje es fuente en español y lo traduce i18n.js.
const assert = require('node:assert');
const D = require('../terminal-drop.js');

// ─── clasificarArrastre: qué clase de overlay mostrar ────────────────────────
// Imagen → 'imagen'
assert.strictEqual(
  D.clasificarArrastre({ items: [{ kind: 'file', type: 'image/png' }] }),
  'imagen',
);
// Video mp4 → 'video'
assert.strictEqual(
  D.clasificarArrastre({ items: [{ kind: 'file', type: 'video/mp4' }] }),
  'video',
);
// Otros contenedores de video (mov/webm) también caen en 'video'
assert.strictEqual(D.clasificarArrastre({ items: [{ kind: 'file', type: 'video/quicktime' }] }), 'video');
assert.strictEqual(D.clasificarArrastre({ items: [{ kind: 'file', type: 'video/webm' }] }), 'video');
// Archivo de otro tipo (pdf, zip…) → 'archivo'
assert.strictEqual(
  D.clasificarArrastre({ items: [{ kind: 'file', type: 'application/pdf' }] }),
  'archivo',
);
// Archivo con type desconocido pero kind 'file' → 'archivo' (hay un archivo)
assert.strictEqual(D.clasificarArrastre({ items: [{ kind: 'file', type: '' }] }), 'archivo');
// Arrastre de texto/selección/URL (item 'string', sin files) → null (sin overlay central)
assert.strictEqual(
  D.clasificarArrastre({ items: [{ kind: 'string', type: 'text/plain' }] }),
  null,
);
// Sin items pero types incluye 'Files' (fallback de algunos browsers) → 'archivo'
assert.strictEqual(D.clasificarArrastre({ items: [], types: ['Files'] }), 'archivo');
// Sin items y types sólo texto → null
assert.strictEqual(D.clasificarArrastre({ items: [], types: ['text/plain'] }), null);
// dataTransfer nulo/indefinido → null (nunca tira)
assert.strictEqual(D.clasificarArrastre(null), null);
assert.strictEqual(D.clasificarArrastre(undefined), null);
// La imagen gana aunque venga un item 'string' antes (Windows agrega text/plain
// junto al archivo al arrastrar desde el explorador).
assert.strictEqual(
  D.clasificarArrastre({ items: [{ kind: 'string', type: 'text/plain' }, { kind: 'file', type: 'image/jpeg' }] }),
  'imagen',
);
// El primer archivo manda: video antes que un pdf posterior → 'video'
assert.strictEqual(
  D.clasificarArrastre({ items: [{ kind: 'file', type: 'video/mp4' }, { kind: 'file', type: 'application/pdf' }] }),
  'video',
);

// ─── mensajeDrop: título + hint por clase (español; i18n traduce) ────────────
assert.deepStrictEqual(D.mensajeDrop('imagen'),  { titulo: 'Soltá la imagen acá', hint: 'para adjuntarla a la terminal' });
assert.deepStrictEqual(D.mensajeDrop('video'),   { titulo: 'Soltá el video acá',  hint: 'para adjuntarlo a la terminal' });
assert.deepStrictEqual(D.mensajeDrop('archivo'), { titulo: 'Soltá el archivo acá', hint: 'para adjuntarlo a la terminal' });
assert.strictEqual(D.mensajeDrop('inexistente'), null);
assert.strictEqual(D.mensajeDrop(null), null);

// ─── esSubible: en el DROP decide si el archivo se sube al backend y se pega la
// ruta (imagen/video) o se manda sólo el nombre (otros). ─────────────────────
assert.strictEqual(D.esSubible('image/png'), true);
assert.strictEqual(D.esSubible('image/jpeg'), true);
assert.strictEqual(D.esSubible('video/mp4'), true);
assert.strictEqual(D.esSubible('video/webm'), true);
assert.strictEqual(D.esSubible('application/pdf'), false);
assert.strictEqual(D.esSubible('text/plain'), false);
assert.strictEqual(D.esSubible(''), false);
assert.strictEqual(D.esSubible(null), false);
assert.strictEqual(D.esSubible(undefined), false);

console.log('terminal-drop.test.js OK');
