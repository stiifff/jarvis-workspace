'use strict';
// Test puro del mini-renderer de Markdown del chat del Builder agéntico.
const assert = require('node:assert');
const M = require('../md-mini.js');
const r = M.render;

// escapa HTML ANTES de transformar (seguridad + el <!doctype> se ve literal)
assert.ok(r('el `<!doctype html>` va literal').includes('&lt;!doctype html&gt;'));
assert.ok(!r('<script>alert(1)</script>').includes('<script>'), 'no debe inyectar script');

// negrita / itálica / código inline
assert.ok(r('esto es **Barro**').includes('<strong>Barro</strong>'));
assert.ok(r('un *toque* de itálica').includes('<em>toque</em>'));
assert.ok(r('un `VibeMark` acá').includes('<code>VibeMark</code>'));

// REGRESIÓN: código con números adentro NO se corrompe (el centinela ≠ dígitos)
const cn = r('leí `5 files` y `2 searches`');
assert.ok(cn.includes('<code>5 files</code>'), cn);
assert.ok(cn.includes('<code>2 searches</code>'), cn);
// y un número suelto en el texto NO se envuelve en <code>
assert.ok(!r('tengo 5 cosas').includes('<code>'), 'un número suelto no es código');

// listas
assert.ok(r('- uno\n- dos').includes('<ul><li>uno</li><li>dos</li></ul>'));
assert.ok(r('1. a\n2. b').includes('<ol><li>a</li><li>b</li></ol>'));

// headings (# → h3, ## → h4)
assert.ok(r('## Current Logo Analysis').includes('<h4>Current Logo Analysis</h4>'));
assert.ok(r('# Título').includes('<h3>Título</h3>'));

// párrafo multilínea → <br>; bloques separados por línea en blanco
assert.ok(r('línea uno\nlínea dos').includes('línea uno<br>línea dos'));
assert.ok(r('p1\n\np2') === '<p>p1</p><p>p2</p>', r('p1\n\np2'));

// link http se vuelve <a> con seguridad; javascript: NO
assert.ok(r('mirá [acá](https://x.com)').includes('<a href="https://x.com"'));
assert.ok(!r('[x](javascript:alert(1))').includes('<a '), 'no linkea javascript:');

// borde: vacío / null
assert.strictEqual(r(''), '');
assert.strictEqual(r(null), '');

console.log('md-mini OK — todos los asserts pasaron');
