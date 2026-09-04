'use strict';
// Tests de interpretarEntrada + urlBusqueda: qué hace la barra del preview con
// lo tipeado — URL directa, búsqueda web o búsqueda de YouTube (prefijo
// yt/youtube) — y a qué SITIO REAL manda cada búsqueda.
// Corre con: node frontend/sections/preview/__tests__/preview-entrada.test.js
const assert = require('assert');
const { interpretarEntrada, urlBusqueda, politicaReferrer } = require('../preview.js')._pure;

// ── URLs reconocibles → tipo 'url' (normalizada) ──────────────────
assert.deepStrictEqual(interpretarEntrada('http://localhost:5173'),
  { tipo: 'url', url: 'http://localhost:5173' }, 'URL con esquema');
assert.deepStrictEqual(interpretarEntrada('github.com/anthropics'),
  { tipo: 'url', url: 'http://github.com/anthropics' }, 'host con punto');
assert.deepStrictEqual(interpretarEntrada('localhost:3000/ruta?q=1'),
  { tipo: 'url', url: 'http://localhost:3000/ruta?q=1' }, 'localhost con path');
assert.deepStrictEqual(interpretarEntrada('3000'),
  { tipo: 'url', url: 'http://localhost:3000' }, 'puerto pelado');
assert.deepStrictEqual(interpretarEntrada('localhost'),
  { tipo: 'url', url: 'http://localhost' }, 'localhost pelado');
assert.deepStrictEqual(interpretarEntrada('192.168.0.5:8080'),
  { tipo: 'url', url: 'http://192.168.0.5:8080' }, 'IP:puerto');

// ── la reescritura de YouTube a embed sigue viva en el camino url ──
assert.deepStrictEqual(interpretarEntrada('https://youtu.be/dQw4w9WgXcQ'),
  { tipo: 'url', url: 'https://www.youtube.com/embed/dQw4w9WgXcQ' }, 'youtu.be → embed');

// ── prefijo yt / youtube → búsqueda de YouTube ────────────────────
assert.deepStrictEqual(interpretarEntrada('yt lofi hip hop'),
  { tipo: 'youtube', q: 'lofi hip hop' }, 'yt + término');
assert.deepStrictEqual(interpretarEntrada('YouTube  música para programar'),
  { tipo: 'youtube', q: 'música para programar' }, 'youtube case-insensitive + espacios');
assert.deepStrictEqual(interpretarEntrada('yt'),
  { tipo: 'youtube', q: '' }, 'yt solo → YouTube sin término');
assert.deepStrictEqual(interpretarEntrada('youtube'),
  { tipo: 'youtube', q: '' }, 'youtube solo');
// …pero youtube.com sigue siendo URL, no búsqueda:
assert.deepStrictEqual(interpretarEntrada('youtube.com').tipo, 'url', 'youtube.com es URL');

// ── texto suelto → búsqueda web ───────────────────────────────────
assert.deepStrictEqual(interpretarEntrada('mejores cafés de asunción'),
  { tipo: 'busqueda', q: 'mejores cafés de asunción' }, 'frase con espacios');
assert.deepStrictEqual(interpretarEntrada('gatos'),
  { tipo: 'busqueda', q: 'gatos' }, 'palabra sola sin punto → búsqueda');
assert.deepStrictEqual(interpretarEntrada('cómo usar css grid?'),
  { tipo: 'busqueda', q: 'cómo usar css grid?' }, 'pregunta');

// ── entradas no navegables caen a búsqueda (como un browser) ──────
assert.deepStrictEqual(interpretarEntrada('javascript:alert(1)').tipo, 'busqueda',
  'esquema peligroso NUNCA navega: se busca como texto');
assert.deepStrictEqual(interpretarEntrada('/etc/passwd').tipo, 'busqueda', 'ruta → búsqueda');

// ── vacío → invalida ──────────────────────────────────────────────
assert.deepStrictEqual(interpretarEntrada(''), { tipo: 'invalida' }, 'vacío');
assert.deepStrictEqual(interpretarEntrada('   '), { tipo: 'invalida' }, 'espacios');
assert.deepStrictEqual(interpretarEntrada(null), { tipo: 'invalida' }, 'null');

console.log('OK interpretarEntrada');

// ═══ urlBusqueda: buscar = navegar al buscador REAL ════════════════
// Hasta 2026-07-26 esto devolvía la URL same-origin de serp.html (un SERP
// casero que scrapeaba DDG/YouTube). Ahora manda al sitio de verdad.
assert.strictEqual(
  urlBusqueda('busqueda', 'lofi hip hop'),
  'https://www.google.com/search?q=lofi%20hip%20hop',
  'búsqueda web → Google');
assert.strictEqual(
  urlBusqueda('youtube', 'música'),
  'https://www.youtube.com/results?search_query=m%C3%BAsica',
  'búsqueda de YouTube → su página de resultados, con encoding');

// Sin término = la HOME del sitio: es lo que hacen los accesos directos del
// estado vacío (chips YouTube / Buscar en la web).
assert.strictEqual(urlBusqueda('youtube', ''), 'https://www.youtube.com', 'chip YouTube');
assert.strictEqual(urlBusqueda('busqueda', ''), 'https://www.google.com', 'chip Buscar en la web');
assert.strictEqual(urlBusqueda('youtube', '   '), 'https://www.youtube.com', 'espacios = sin término');
assert.strictEqual(urlBusqueda('busqueda', null), 'https://www.google.com', 'null = sin término');

// Un tipo desconocido cae a la web (nunca devuelve null: la barra siempre navega).
assert.strictEqual(urlBusqueda('cualquiera', 'gatos'),
  'https://www.google.com/search?q=gatos', 'tipo desconocido → Google');

console.log('OK urlBusqueda');

// ═══ politicaReferrer: los embeds de YouTube exigen Referer (Error 153) ═══
assert.strictEqual(politicaReferrer('https://www.youtube.com/embed/abc?autoplay=1'),
  'origin', 'embed de youtube → origin');
assert.strictEqual(politicaReferrer('https://youtube.com/embed/abc'),
  'origin', 'sin www también');
assert.strictEqual(politicaReferrer('https://www.youtube-nocookie.com/embed/abc'),
  'origin', 'variante nocookie');
// Todo lo demás conserva la privacidad por default:
assert.strictEqual(politicaReferrer('https://www.youtube.com/watch?v=abc'),
  'no-referrer', 'watch NO es embed');
assert.strictEqual(politicaReferrer('https://github.com/x'),
  'no-referrer', 'sitio cualquiera');
assert.strictEqual(politicaReferrer('http://localhost:5173'),
  'no-referrer', 'dev server local');
assert.strictEqual(politicaReferrer('basura no url'),
  'no-referrer', 'URL rara → default');

console.log('OK politicaReferrer');
console.log('OK ALL');
