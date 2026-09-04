'use strict';
// Tests de la lógica pura del browser embebido (normalización de URL +
// decisión de auto-abrir ante dev server detectado).
// Corre con: node frontend/sections/preview/__tests__/preview-url.test.js
const assert = require('assert');
const { normalizarUrl, urlMedia, esEmbed, politicaReferrer, linkAlPreview, faviconSrc } = require('../preview.js')._pure;

// ── host:puerto → http:// ─────────────────────────────────────────
assert.strictEqual(normalizarUrl('localhost:3000'), 'http://localhost:3000', 'localhost:puerto');
assert.strictEqual(normalizarUrl('192.168.0.5:8080'), 'http://192.168.0.5:8080', 'IP:puerto');

// ── host:puerto CON path/query → http:// (regresión: 'localhost' tomado
//    como esquema porque el resto no era solo dígitos) ────────────────
assert.strictEqual(normalizarUrl('localhost:3000/ruta?q=1'), 'http://localhost:3000/ruta?q=1', 'localhost:puerto/path?query');
assert.strictEqual(normalizarUrl('localhost:3000/static/index.html'), 'http://localhost:3000/static/index.html', 'localhost:puerto/path');
assert.strictEqual(normalizarUrl('192.168.0.5:8080/x'), 'http://192.168.0.5:8080/x', 'IP:puerto/path');
// ...sin reabrir el agujero de esquemas peligrosos:
assert.strictEqual(normalizarUrl('mailto:foo'), null, 'mailto: sigue siendo null');

// ── puerto pelado → http://localhost:puerto ───────────────────────
assert.strictEqual(normalizarUrl('3000'), 'http://localhost:3000', 'puerto pelado');

// ── URLs completas pasan igual ────────────────────────────────────
assert.strictEqual(normalizarUrl('http://x'), 'http://x', 'http pasa');
assert.strictEqual(normalizarUrl('https://x'), 'https://x', 'https pasa');
assert.strictEqual(normalizarUrl('https://docs.expo.dev/guides'), 'https://docs.expo.dev/guides', 'https con path pasa');

// ── trim de espacios ──────────────────────────────────────────────
assert.strictEqual(normalizarUrl('  localhost:3000  '), 'http://localhost:3000', 'trim + normaliza');
assert.strictEqual(normalizarUrl('  http://x  '), 'http://x', 'trim de URL completa');

// ── vacío / nulo → null ───────────────────────────────────────────
assert.strictEqual(normalizarUrl(''), null, 'vacío → null');
assert.strictEqual(normalizarUrl('   '), null, 'solo espacios → null');
assert.strictEqual(normalizarUrl(null), null, 'null → null');
assert.strictEqual(normalizarUrl(undefined), null, 'undefined → null');

// ── esquemas peligrosos / no-web → null ───────────────────────────
// Sin '//': hoy quedaban como 'http://javascript:...' (XSS embebido).
assert.strictEqual(normalizarUrl('javascript:alert(1)'), null, 'javascript: sin // → null');
assert.strictEqual(normalizarUrl('data:text/html,<h1>x</h1>'), null, 'data: sin // → null');
assert.strictEqual(normalizarUrl('vbscript:msgbox(1)'), null, 'vbscript: sin // → null');
// Con '//': hoy pasaban tal cual por el regex de esquema explícito.
assert.strictEqual(normalizarUrl('javascript://alert(1)'), null, 'javascript:// → null');
assert.strictEqual(normalizarUrl('data://x'), null, 'data:// → null');
assert.strictEqual(normalizarUrl('vbscript://x'), null, 'vbscript:// → null');

// ── otros esquemas con :// no-web → null (solo http/https) ─────────
assert.strictEqual(normalizarUrl('ftp://host/file'), null, 'ftp:// → null');
assert.strictEqual(normalizarUrl('file:///etc/passwd'), null, 'file:// → null');

// ── ruta relativa (arranca con '/') → null ────────────────────────
// Antes producía 'http:///etc/passwd' (URL malformada).
assert.strictEqual(normalizarUrl('/etc/passwd'), null, 'ruta absoluta-relativa → null');
assert.strictEqual(normalizarUrl('/foo/bar'), null, 'ruta relativa → null');

// ── documental: 'localhost' sin puerto → http://localhost ─────────
assert.strictEqual(normalizarUrl('localhost'), 'http://localhost', 'localhost sin puerto');

// ── alias de loopback → localhost (el MISMO server = una sola pestaña) ──
// Sin esto el mismo dev server aparecía dos veces (una por alias) y el demo
// por 127.0.0.1:3000 quedaba en distinto origen que el workspace (→ error).
assert.strictEqual(normalizarUrl('http://127.0.0.1:5541'), 'http://localhost:5541', '127.0.0.1 → localhost');
assert.strictEqual(normalizarUrl('http://127.0.0.1:3000/static/x/y.html'),
  'http://localhost:3000/static/x/y.html', '127.0.0.1 con path → localhost');
assert.strictEqual(normalizarUrl('127.0.0.1:8000'), 'http://localhost:8000', '127.0.0.1:puerto pelado → localhost');
assert.strictEqual(normalizarUrl('http://0.0.0.0:4321/'), 'http://localhost:4321/', '0.0.0.0 → localhost');
assert.strictEqual(normalizarUrl('http://[::1]:5173/app'), 'http://localhost:5173/app', '[::1] → localhost');
// NO tocar una IP de LAN ni una IP que aparezca en el PATH:
assert.strictEqual(normalizarUrl('http://192.168.0.5:8080'), 'http://192.168.0.5:8080', 'IP de LAN intacta');
assert.strictEqual(normalizarUrl('http://localhost:3000/x/127.0.0.1'),
  'http://localhost:3000/x/127.0.0.1', 'IP en el path intacta');

// ── YouTube → /embed/ (embebible en iframe, CON audio) ─────────────
assert.strictEqual(normalizarUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ'),
  'https://www.youtube.com/embed/dQw4w9WgXcQ', 'watch?v= → embed');
assert.strictEqual(normalizarUrl('https://m.youtube.com/watch?v=abc'),
  'https://www.youtube.com/embed/abc', 'm.youtube también');
assert.strictEqual(normalizarUrl('https://youtu.be/dQw4w9WgXcQ'),
  'https://www.youtube.com/embed/dQw4w9WgXcQ', 'youtu.be corto → embed');
assert.strictEqual(normalizarUrl('youtube.com/watch?v=abc&t=42'),
  'https://www.youtube.com/embed/abc', 'sin esquema + params extra → embed');
// embed ya armado y resto de youtube pasan intactos:
assert.strictEqual(normalizarUrl('https://www.youtube.com/embed/abc'),
  'https://www.youtube.com/embed/abc', 'embed pasa igual');
assert.strictEqual(normalizarUrl('https://www.youtube.com/results?search_query=x'),
  'https://www.youtube.com/results?search_query=x', 'búsqueda de youtube pasa igual');
// no-youtube no se toca:
assert.strictEqual(normalizarUrl('https://example.com/watch?v=abc'),
  'https://example.com/watch?v=abc', 'watch?v= de otro host pasa igual');

// ── Twitch → player/clip embed (EXIGE parent = dominio embebedor) ──
assert.strictEqual(normalizarUrl('https://www.twitch.tv/shroud'),
  'https://player.twitch.tv/?channel=shroud&parent=localhost', 'twitch canal → player');
assert.strictEqual(normalizarUrl('https://twitch.tv/videos/123456789'),
  'https://player.twitch.tv/?video=123456789&parent=localhost', 'twitch VOD → player');
assert.strictEqual(normalizarUrl('https://clips.twitch.tv/SomeClipSlug'),
  'https://clips.twitch.tv/embed?clip=SomeClipSlug&parent=localhost', 'clips.twitch → embed');
assert.strictEqual(normalizarUrl('https://www.twitch.tv/somechannel/clip/AbcClip123'),
  'https://clips.twitch.tv/embed?clip=AbcClip123&parent=localhost', 'twitch clip largo → embed');
assert.strictEqual(normalizarUrl('https://www.twitch.tv/directory'),
  'https://www.twitch.tv/directory', 'twitch/directory NO es canal → intacto (no se reescribe a player)');

console.log('OK normalizarUrl');

// ═══ esEmbed: ¿sacar allow-popups del sandbox? (evita escape a Windows) ═══
assert.strictEqual(esEmbed('https://www.youtube.com/embed/abc'), true, 'yt embed');
assert.strictEqual(esEmbed('https://player.twitch.tv/?channel=x&parent=localhost'), true, 'twitch player');
assert.strictEqual(esEmbed('https://clips.twitch.tv/embed?clip=x'), true, 'twitch clip embed');
assert.strictEqual(esEmbed('https://www.youtube.com/watch?v=abc'), false, 'yt watch NO es embed');
assert.strictEqual(esEmbed('https://example.com/page'), false, 'sitio normal NO es embed');
console.log('OK esEmbed');

// ═══ politicaReferrer: Twitch necesita 'origin' (como YouTube) ═══════
assert.strictEqual(politicaReferrer('https://player.twitch.tv/?channel=x'), 'origin', 'twitch → origin');
assert.strictEqual(politicaReferrer('https://www.youtube.com/embed/abc'), 'origin', 'yt embed → origin');
assert.strictEqual(politicaReferrer('https://example.com/'), 'no-referrer', 'otro → no-referrer');
console.log('OK politicaReferrer');

// (La maquinaria de auto-abrir el preview —debeAutoAbrir/olvidarAutoAbierta— se
//  eliminó el 2026-07-12: "menú-primero", la detección de un dev server ya no
//  abre pestañas solas. Ver el handler dev_server_detectado en shell/workspace.js.)

// ═══ urlMedia: URL que va al iframe (tracking + reanudación) ══════════

// ── yt embed SIEMPRE con enablejsapi+origin (habilita el tracking) ──
{
  const u = new URL(urlMedia('https://www.youtube.com/embed/abc', 'http://localhost:3000', null));
  assert.strictEqual(u.searchParams.get('enablejsapi'), '1', 'enablejsapi');
  assert.strictEqual(u.searchParams.get('origin'), 'http://localhost:3000', 'origin del workspace');
  assert.strictEqual(u.searchParams.get('start'), null, 'sin media → sin start');
  assert.strictEqual(u.searchParams.get('autoplay'), null, 'sin media → sin autoplay');
}

// ── con media {t, play}: reanuda desde el segundo guardado, sonando ─
{
  const u = new URL(urlMedia('https://www.youtube.com/embed/abc?listType=x', 'http://localhost:3000', { t: 92, play: true }));
  assert.strictEqual(u.searchParams.get('start'), '92', 'start del guardado');
  assert.strictEqual(u.searchParams.get('autoplay'), '1', 'sonaba → autoplay');
  assert.strictEqual(u.searchParams.get('listType'), 'x', 'params previos intactos');
}

// ── pausado: restaura la posición pero NO arranca solo ──────────────
{
  const u = new URL(urlMedia('https://www.youtube.com/embed/abc', 'http://localhost:3000', { t: 92, play: false }));
  assert.strictEqual(u.searchParams.get('start'), '92', 'posición restaurada');
  assert.strictEqual(u.searchParams.get('autoplay'), null, 'pausado → sin autoplay');
}

// ── recién arrancado (<3s): desde cero (un start=1 queda raro) ──────
{
  const u = new URL(urlMedia('https://www.youtube.com/embed/abc', 'http://localhost:3000', { t: 2, play: true }));
  assert.strictEqual(u.searchParams.get('start'), null, 'sin start');
  assert.strictEqual(u.searchParams.get('autoplay'), '1', 'pero sí autoplay');
}

// ── cualquier otra URL pasa INTACTA (sin params de yt) ──────────────
assert.strictEqual(urlMedia('http://localhost:5173/app', 'http://localhost:3000', { t: 50, play: true }),
  'http://localhost:5173/app', 'no-yt intacta');
assert.strictEqual(urlMedia('no-es-url', 'http://localhost:3000', null), 'no-es-url', 'basura intacta');

console.log('OK urlMedia');

// ═══ linkAlPreview: click de un link en la terminal → ¿al Web Preview? ═══
const JARVIS = 'http://localhost:3000';

// ── dev servers locales → al preview (con la URL lista) ─────────────
assert.strictEqual(linkAlPreview('http://localhost:5173', JARVIS),
  'http://localhost:5173/', 'localhost:puerto → preview');
assert.strictEqual(linkAlPreview('http://localhost:5173/admin?x=1', JARVIS),
  'http://localhost:5173/admin?x=1', 'ruta interna del dev server → preview');
assert.strictEqual(linkAlPreview('https://localhost:8443/', JARVIS),
  'https://localhost:8443/', 'https local también');

// ── alias de loopback → se reescriben a localhost (de-dupe con la
//    pestaña del server autodetectado, que dev_detect normaliza igual) ──
assert.strictEqual(linkAlPreview('http://127.0.0.1:5173/', JARVIS),
  'http://localhost:5173/', '127.0.0.1 → localhost');
assert.strictEqual(linkAlPreview('http://0.0.0.0:8000/docs', JARVIS),
  'http://localhost:8000/docs', '0.0.0.0 → localhost');
assert.strictEqual(linkAlPreview('http://[::1]:5173/', JARVIS),
  'http://localhost:5173/', '[::1] → localhost');

// ── el propio Jarvis: demos /static sí, el workspace no ─────────────
assert.strictEqual(linkAlPreview('http://localhost:3000/static/mi-demo/index.html', JARVIS),
  'http://localhost:3000/static/mi-demo/index.html', 'demo /static de Jarvis → preview');
assert.strictEqual(linkAlPreview('http://127.0.0.1:3000/static/mi-demo/', JARVIS),
  'http://localhost:3000/static/mi-demo/', 'demo por 127.0.0.1 → normalizada');
assert.strictEqual(linkAlPreview('http://localhost:3000/', JARVIS), null,
  'el workspace entero NO se embebe en sí mismo');
assert.strictEqual(linkAlPreview('http://localhost:3000/login', JARVIS), null,
  'rutas de la app de Jarvis → browser externo');

// ── lo NO local va al browser externo (null) ────────────────────────
assert.strictEqual(linkAlPreview('https://github.com/x/y', JARVIS), null, 'sitio externo → null');
assert.strictEqual(linkAlPreview('http://192.168.0.5:8080/', JARVIS), null, 'IP de LAN → null (no es loopback)');
assert.strictEqual(linkAlPreview('ftp://localhost/archivo', JARVIS), null, 'esquema no-web → null');
assert.strictEqual(linkAlPreview('no-es-url', JARVIS), null, 'basura → null');
assert.strictEqual(linkAlPreview(null, JARVIS), null, 'null → null');

// ── origin de Jarvis raro/ausente → el link local igual va al preview ─
assert.strictEqual(linkAlPreview('http://localhost:5173/', 'basura'),
  'http://localhost:5173/', 'origin no parseable → dev server igual entra');

console.log('OK linkAlPreview');

// ═══ faviconSrc: de dónde sale el ícono de una pestaña ═══════════════
const JH = 'localhost:3000';   // host del workspace
// el favicon DECLARADO por la página (leído del <link rel=icon>) gana siempre
assert.strictEqual(faviconSrc('http://localhost:3000/static/a/index.html', 'data:image/svg+xml,<svg/>', JH),
  'data:image/svg+xml,<svg/>', 'declarado gana');
// demo del PROPIO Jarvis (mismo host:puerto) sin declarado → null (globo default)
assert.strictEqual(faviconSrc('http://localhost:3000/static/a/index.html', null, JH), null,
  'demo de Jarvis sin ícono → default');
// dev server LOCAL en otro puerto → su propio /favicon.ico
assert.strictEqual(faviconSrc('http://localhost:5173/app', null, JH), 'http://localhost:5173/favicon.ico',
  'dev server real → su /favicon.ico');
assert.strictEqual(faviconSrc('http://127.0.0.1:8000/', null, JH), 'http://127.0.0.1:8000/favicon.ico',
  '127.0.0.1 dev server → su /favicon.ico');
// sitio público → servicio de favicons (resuelve dominios reales)
assert.strictEqual(faviconSrc('https://github.com/x/y', null, JH), 'https://icons.duckduckgo.com/ip3/github.com.ico',
  'público → servicio de favicons');
// sin URL / no-URL → null (pestaña vacía)
assert.strictEqual(faviconSrc('', null, JH), null, 'vacío → null');
assert.strictEqual(faviconSrc('basura', null, JH), null, 'no-URL → null');
// workspace servido por 127.0.0.1 → el demo por ese mismo host tampoco adivina /favicon.ico
assert.strictEqual(faviconSrc('http://127.0.0.1:3000/static/a/', null, '127.0.0.1:3000'), null,
  'demo mismo host que el workspace → default');
console.log('OK faviconSrc');

console.log('OK ALL');
