'use strict';
// Regresión del bug "el historial se traga letras" (2026-07-17): bash/tmux/glibc
// miden los emoji como 2 columnas, pero las tablas default de xterm.js 5.3
// (Unicode 6) los miden 1. Con una entrada de historial que contiene un emoji
// (p.ej. `echo utf8-está─✅`), cada redibujo RELATIVO de readline (↑/↓) aterriza
// 1 columna corrido a la izquierda y se come el prompt, una letra por pasada
// (reproducido byte a byte contra el pane real en el diagnóstico). El fix es el
// addon oficial Unicode11 vendoreado + activado en terminal.js: el grid local
// mide EXACTAMENTE igual que tmux. Este test guarda (a) que el addon vendoreado
// exista y mida bien, y (b) que el wiring de carga siga presente.
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const RAIZ = path.join(__dirname, '..', '..', '..');

// (a) El addon vendoreado existe y sus tablas miden como bash/tmux/glibc.
const Addon = require(path.join(RAIZ, 'vendor', 'xterm', 'xterm-addon-unicode11.js'));
const addon = new Addon.Unicode11Addon();
let provider = null;
addon.activate({ unicode: { register(p) { provider = p; } } });
assert.ok(provider, 'el addon debe registrar su provider de anchos');
assert.strictEqual(provider.version, '11');
assert.strictEqual(provider.wcwidth(0x2705), 2, '✅ debe medir 2 columnas (glibc/tmux miden 2)');
assert.strictEqual(provider.wcwidth(0x1f600), 2, '😀 debe medir 2 columnas');
assert.strictEqual(provider.wcwidth(0x2500), 1, '─ (box drawing) sigue midiendo 1');
assert.strictEqual(provider.wcwidth(0xe1), 1, 'á sigue midiendo 1');
assert.strictEqual(provider.wcwidth(0x41), 1, 'ASCII sigue midiendo 1');
assert.strictEqual(provider.wcwidth(0x4e00), 2, 'CJK sigue midiendo 2');

// (b) El wiring sigue: workspace.html carga el addon y terminal.js lo activa.
const html = fs.readFileSync(path.join(RAIZ, 'shell', 'workspace.html'), 'utf8');
assert.ok(html.includes('xterm-addon-unicode11.js'), 'workspace.html debe cargar el addon');
const tjs = fs.readFileSync(path.join(RAIZ, 'sections', 'terminals', 'terminal.js'), 'utf8');
assert.ok(tjs.includes("activeVersion = '11'"), 'terminal.js debe activar la versión 11');
assert.ok(tjs.includes('Unicode11Addon'), 'terminal.js debe cargar el Unicode11Addon');

console.log('unicode11-addon.test.js OK');
