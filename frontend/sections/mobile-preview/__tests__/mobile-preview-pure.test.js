// Tests de la lógica pura del Mobile Preview (geometría del marco). Corre con:
//   node frontend/sections/mobile-preview/__tests__/mobile-preview-pure.test.js
'use strict';
const assert = require('assert');
const {
  dimsOrientadas, escalaFrame, transformFrame, debeAutoAbrir, debeAutoAgregarTelefono,
  lienzoMuestraVacio, viewportListo,
  clampZoom, fitAll, zoomAt, transformBoard, webNueva, normalizarUrlWeb, webSaneada,
  urlSamplerVuelta, notaNueva, notaSaneada, tituloNota,
} = require('../mobile-preview-pure.js');

// ── dimsOrientadas: landscape intercambia w/h ──
assert.deepStrictEqual(dimsOrientadas(393, 852, 'portrait'), { w: 393, h: 852 });
assert.deepStrictEqual(dimsOrientadas(393, 852, 'landscape'), { w: 852, h: 393 });
assert.deepStrictEqual(dimsOrientadas(393, 852, undefined), { w: 393, h: 852 });

// ── escalaFrame: encaja en el contenedor, nunca agranda salvo zoom ──
// Contenedor grande: cabe entero, escala tope 1 (sin zoom).
assert.strictEqual(escalaFrame(2000, 2000, 393, 852, 100, 24), 1);
// Contenedor chico: escala < 1 por alto.
let s = escalaFrame(400, 426, 393, 852, 100, 24);
assert.ok(s > 0 && s < 1, 'contenedor chico → escala fraccional');
assert.strictEqual(s, (426 - 24) / 852);
// Zoom 200% duplica la escala base.
assert.strictEqual(escalaFrame(2000, 2000, 393, 852, 200, 24), 2);
// Zoom 50% la reduce a la mitad.
assert.strictEqual(escalaFrame(2000, 2000, 393, 852, 50, 24), 0.5);
// Contenedor degenerado (más chico que el margen) → nunca negativo.
assert.ok(escalaFrame(10, 10, 393, 852, 100, 24) >= 0, 'escala nunca negativa');

// ── transformFrame: translate (pan) ANTES de scale, en px de pantalla ──
// Sin pan, centrado: solo la escala.
assert.strictEqual(transformFrame(0, 0, 1), 'translate(0px, 0px) scale(1)');
// Con pan: el translate va primero (px de pantalla, 1:1 con el cursor).
assert.strictEqual(transformFrame(40, -25, 0.8), 'translate(40px, -25px) scale(0.8)');
// El orden importa: 'translate' debe preceder a 'scale' en el string.
const t = transformFrame(10, 10, 2);
assert.ok(t.indexOf('translate') < t.indexOf('scale'), 'translate antes que scale');

// (chromeFrame se eliminó del módulo: la geometría real del hardware vive en
// device-catalog.js — ver __tests__/device-catalog.test.js.)

// ── parseCssColor / luminancia / esFondoClaro: status bar adaptativa ──
const { parseCssColor, luminancia, esFondoClaro } = require('../mobile-preview-pure.js');
// Formatos que reporta getComputedStyle (y tolerancias extra)
assert.deepStrictEqual(parseCssColor('rgb(255, 255, 255)'), { r: 255, g: 255, b: 255, a: 1 });
assert.deepStrictEqual(parseCssColor('rgba(10, 20, 30, 0.5)'), { r: 10, g: 20, b: 30, a: 0.5 });
assert.deepStrictEqual(parseCssColor('#fff'), { r: 255, g: 255, b: 255, a: 1 });
assert.deepStrictEqual(parseCssColor('#102030'), { r: 16, g: 32, b: 48, a: 1 });
assert.deepStrictEqual(parseCssColor('color(srgb 1 0 0)'), { r: 255, g: 0, b: 0, a: 1 });
assert.strictEqual(parseCssColor('cualquier-cosa'), null);
assert.strictEqual(parseCssColor(null), null);
// Luminancia WCAG: extremos y punto medio perceptual
assert.strictEqual(luminancia({ r: 0, g: 0, b: 0 }), 0);
assert.strictEqual(luminancia({ r: 255, g: 255, b: 255 }), 1);
assert.ok(Math.abs(luminancia({ r: 118, g: 118, b: 118 }) - 0.184) < 0.01, 'gris medio ~0.18');
// esFondoClaro: blanco→true (íconos negros), negro→false (íconos blancos)
assert.strictEqual(esFondoClaro('rgb(255, 255, 255)'), true);
assert.strictEqual(esFondoClaro('rgb(0, 0, 0)'), false);
assert.strictEqual(esFondoClaro('rgb(245, 245, 245)'), true, 'casi blanco = claro');
assert.strictEqual(esFondoClaro('rgb(30, 30, 40)'), false, 'tema oscuro típico = oscuro');
// indeterminados → null (el caller mantiene el default)
assert.strictEqual(esFondoClaro('rgba(0, 0, 0, 0)'), null, 'transparente: no decide');
assert.strictEqual(esFondoClaro('basura'), null);
// colorMayoria: el fondo real gana aunque un toast tape UN punto
const { colorMayoria } = require('../mobile-preview-pure.js');
assert.strictEqual(colorMayoria(['rgb(243, 83, 105)', 'rgb(10, 20, 40)', 'rgb(10, 20, 40)']), 'rgb(10, 20, 40)', 'mayoría le gana al toast');
assert.strictEqual(colorMayoria(['basura', 'rgb(1, 2, 3)']), 'rgb(1, 2, 3)', 'ignora imparseables');
assert.strictEqual(colorMayoria(['x', null]), null, 'nada válido → null');
assert.strictEqual(colorMayoria(['#fff', '#000', '#fff']), '#fff');
// esGradienteSeguro: solo gradientes CSS puros (se inyectan como estilo)
const { esGradienteSeguro } = require('../mobile-preview-pure.js');
assert.strictEqual(esGradienteSeguro('linear-gradient(rgb(29, 40, 71), rgb(67, 94, 168))'), true);
assert.strictEqual(esGradienteSeguro('radial-gradient(circle, #fff, #000)'), true);
assert.strictEqual(esGradienteSeguro('repeating-linear-gradient(45deg, #000 0 4px, #111 4px 8px)'), true);
assert.strictEqual(esGradienteSeguro('url(http://evil.com/x.png)'), false, 'nada de url()');
assert.strictEqual(esGradienteSeguro('linear-gradient(#000, #111), url(/x.png)'), false, 'mezcla con url() tampoco');
assert.strictEqual(esGradienteSeguro('none'), false);
assert.strictEqual(esGradienteSeguro(''), false);
assert.strictEqual(esGradienteSeguro(null), false);
assert.strictEqual(esGradienteSeguro('x'.repeat(3000)), false, 'largo acotado');
console.log('colores (sampler): OK');

// ── debeAutoAbrir: auto-abrir el Móvil UNA sola vez por proyecto ──
// (autoAbrir, autoMostrar, enMobile, yaVisto) → { abrir, visto }
// Primera vez en el proyecto (toggle ON, no estaba a la vista): abre y marca visto.
assert.deepStrictEqual(debeAutoAbrir(true, true, false, false), { abrir: true, visto: true });
// Ya visto antes: NO se vuelve a abrir solo (aunque ahora esté cerrado).
assert.deepStrictEqual(debeAutoAbrir(true, true, false, true), { abrir: false, visto: true });
// Lo dejaste activo (enMobile): no forzar, pero queda marcado visto.
assert.deepStrictEqual(debeAutoAbrir(true, true, true, false), { abrir: false, visto: true });
// No es entrada de proyecto (autoAbrir=false): nunca abre ni quema la "primera vez".
assert.deepStrictEqual(debeAutoAbrir(false, true, false, false), { abrir: false, visto: false });
// Toggle global apagado: no abre y preserva yaVisto sin tocarlo (false sigue false).
assert.deepStrictEqual(debeAutoAbrir(true, false, false, false), { abrir: false, visto: false });
// Toggle apagado pero ya visto: preserva el visto en true.
assert.deepStrictEqual(debeAutoAbrir(true, false, false, true), { abrir: false, visto: true });
console.log('debeAutoAbrir: OK');

// ── debeAutoAgregarTelefono: la detección de Metro NO repone un teléfono quitado ──
// (numTelefonos, sinTelefono) → ¿auto-agregar el iPhone default al detectar la app?
// Lienzo virgen (0 teléfonos, sin quita deliberada): sí, aparece el default.
assert.strictEqual(debeAutoAgregarTelefono(0, false), true);
// El usuario quitó el último teléfono a propósito: NO reaparece solo.
assert.strictEqual(debeAutoAgregarTelefono(0, true), false);
// Ya hay teléfonos en el board: nunca se suma otro solo.
assert.strictEqual(debeAutoAgregarTelefono(1, false), false);
assert.strictEqual(debeAutoAgregarTelefono(3, true), false);
console.log('debeAutoAgregarTelefono: OK');

// ── lienzoMuestraVacio: el empty NO tapa teléfonos agregados sin Metro ──
assert.strictEqual(lienzoMuestraVacio(0, 0, 0, false), true, 'lienzo virgen sin app → empty');
assert.strictEqual(lienzoMuestraVacio(1, 0, 0, false), false, 'un teléfono a mano, sin Metro → se ve el teléfono');
assert.strictEqual(lienzoMuestraVacio(4, 0, 0, false), false, '4 teléfonos fantasma no: ya están en el board');
assert.strictEqual(lienzoMuestraVacio(0, 1, 0, false), false, 'una card web ocupa el lienzo');
assert.strictEqual(lienzoMuestraVacio(0, 0, 1, false), false, 'una nota ocupa el lienzo');
assert.strictEqual(lienzoMuestraVacio(0, 0, 0, true), false, 'app detectada, 0 teléfonos → empty off (lienzo vivo)');
console.log('lienzoMuestraVacio: OK');

// ── viewportListo: no encuadrar con el stage en 0×0 (dock hidden / max) ──
assert.strictEqual(viewportListo(0, 0), false);
assert.strictEqual(viewportListo(1, 800), false, 'ancho degenerado');
assert.strictEqual(viewportListo(800, 0), false);
assert.strictEqual(viewportListo(320, 240), true);
console.log('viewportListo: OK');

// ── clampZoom: rango [min,max], nunca ≤0 ──
assert.strictEqual(clampZoom(1), 1);
assert.strictEqual(clampZoom(5, 0.2, 3), 3);       // tope
assert.strictEqual(clampZoom(0.01, 0.2, 3), 0.2);  // piso
assert.strictEqual(clampZoom(-3, 0.2, 3), 0.2);    // negativo → piso
console.log('clampZoom: OK');

// ── fitAll: encuadra el bbox de todos los teléfonos y centra ──
// Un teléfono 400×800 en (0,0), viewport 1000×1000, margen 100:
//   zoom por alto = (1000-200)/800 = 1 (tope maxZoom=1), centrado.
let f = fitAll([{ x: 0, y: 0, w: 400, h: 800 }], 1000, 1000, 100, 1);
assert.strictEqual(f.zoom, 1);
// centro del bbox (200,400) va al centro del viewport (500,500):
assert.strictEqual(f.panX, 500 - 200 * 1);  // 300
assert.strictEqual(f.panY, 500 - 400 * 1);  // 100
// Dos teléfonos lado a lado: bbox más ancho → zoom<1 para que entren.
let f2 = fitAll([{ x: 0, y: 0, w: 400, h: 800 }, { x: 500, y: 0, w: 400, h: 800 }], 1000, 600, 50, 1);
assert.ok(f2.zoom > 0 && f2.zoom < 1, 'dos teléfonos → zoom fraccional');
// bbox = 0..900 ancho, 0..800 alto; zoom = min((1000-100)/900,(600-100)/800) = min(1,0.625)=0.625
assert.ok(Math.abs(f2.zoom - 0.625) < 1e-9, 'zoom por el alto');
// Sin teléfonos o viewport degenerado → identidad.
assert.deepStrictEqual(fitAll([], 1000, 1000, 50, 1), { zoom: 1, panX: 0, panY: 0 });
assert.deepStrictEqual(fitAll([{ x: 0, y: 0, w: 400, h: 800 }], 0, 0, 50, 1), { zoom: 1, panX: 0, panY: 0 });
console.log('fitAll: OK');

// ── zoomAt: el punto de pantalla bajo el cursor queda fijo ──
// Zoom desde 1 a 2 con cursor en (300,300), pan inicial (0,0):
//   el punto del board bajo el cursor era (300,300); tras zoom debe seguir en (300,300).
let z = zoomAt(1, 0, 0, 2, 300, 300, 0.2, 3);
assert.strictEqual(z.zoom, 2);
// board point = (cx-pan)/zoom = 300; pantalla nueva = panX' + 300*2 debe = 300 → panX' = -300
assert.strictEqual(z.panX, -300);
assert.strictEqual(z.panY, -300);
// verificación de invariante: el punto del board se re-proyecta al mismo lugar
let bx = (300 - 0) / 1;
assert.strictEqual(z.panX + bx * z.zoom, 300);
// respeta el tope de zoom (no pasa de max)
let zt = zoomAt(2.9, 0, 0, 2, 100, 100, 0.2, 3);
assert.strictEqual(zt.zoom, 3);
console.log('zoomAt: OK');

// ── transformBoard: pan (px de pantalla) luego scale ──
assert.strictEqual(transformBoard(0, 0, 1), 'translate(0px, 0px) scale(1)');
assert.strictEqual(transformBoard(120, -40, 0.5), 'translate(120px, -40px) scale(0.5)');
console.log('transformBoard: OK');

// ── webNueva: geometría default, a la derecha del elemento más a la derecha ──
let wn = webNueva(7, []);
assert.strictEqual(wn.id, 7);
assert.strictEqual(wn.x, 0);
assert.strictEqual(wn.url, '');
assert.ok(wn.w > 300 && wn.h > 200);
wn = webNueva(8, [{ x: 100, y: 40, w: 400, h: 800 }, { x: 900, y: 60, w: 300, h: 500 }]);
assert.strictEqual(wn.x, 900 + 300 + 70);   // a la derecha del que más lejos llega
assert.strictEqual(wn.y, 60);               // alineada con ese
console.log('webNueva: OK');

// ── normalizarUrlWeb: https:// implícito, solo http/https ──
assert.strictEqual(normalizarUrlWeb('claude.ai/design'), 'https://claude.ai/design');
assert.strictEqual(normalizarUrlWeb('  github.com  '), 'https://github.com');
assert.strictEqual(normalizarUrlWeb('http://localhost:5173'), 'http://localhost:5173');
assert.strictEqual(normalizarUrlWeb('https://x.com'), 'https://x.com');
assert.strictEqual(normalizarUrlWeb('file:///etc/passwd'), '');
assert.strictEqual(normalizarUrlWeb('javascript:alert(1)'), '');
assert.strictEqual(normalizarUrlWeb('hola'), '');          // sin pinta de dominio
assert.strictEqual(normalizarUrlWeb(''), '');
assert.strictEqual(normalizarUrlWeb(null), '');
console.log('normalizarUrlWeb: OK');

// ── webSaneada: basura vieja de localStorage no rompe el board ──
assert.deepStrictEqual(webSaneada({ id: 3, url: 'https://x.com', x: 10, y: 20, w: 900, h: 600 }),
  { id: 3, url: 'https://x.com', x: 10, y: 20, w: 900, h: 600 });
assert.strictEqual(webSaneada(null), null);
assert.strictEqual(webSaneada({ id: 'no' }), null);
let ws = webSaneada({ id: 1, url: 42, x: 'z', y: 1e9, w: 5, h: 99999 });
assert.strictEqual(ws.url, '');
assert.strictEqual(ws.x, 0);          // x inválida → default
assert.strictEqual(ws.y, 50000);      // clampeada
assert.strictEqual(ws.w, 320);        // mínimo usable
assert.strictEqual(ws.h, 4000);       // techo
console.log('webSaneada: OK');

// ── urlSamplerVuelta: URL para VOLVER al espejo instrumentado tras un escape ──
// (un full reload dentro del sampler recarga la URL reescrita = una página de
// Jarvis; el workspace re-apunta el iframe con esta URL, preservando la ruta)
const DS = '/api/mobile-preview/3/sampler?url=http%3A%2F%2Flocalhost%3A8081&ruta=%2F';
// Ruta reportada por la app → reemplaza el param ruta, conserva url= intacto.
let uv = urlSamplerVuelta(DS, '/perfil');
assert.strictEqual(uv, '/api/mobile-preview/3/sampler?url=http%3A%2F%2Flocalhost%3A8081&ruta=%2Fperfil');
// Ruta con query propia de la app: viaja entera dentro del param ruta.
uv = urlSamplerVuelta(DS, '/perfil?tab=2');
assert.ok(uv.indexOf('ruta=%2Fperfil%3Ftab%3D2') !== -1, 'query de la app dentro de ruta=');
// Ruta inválida (vacía, sin barra, protocolo-relativa) → el src previo tal cual.
assert.strictEqual(urlSamplerVuelta(DS, ''), DS);
assert.strictEqual(urlSamplerVuelta(DS, 'perfil'), DS);
assert.strictEqual(urlSamplerVuelta(DS, '//evil.com'), DS);
assert.strictEqual(urlSamplerVuelta(DS, null), DS);
// Sin src previo no hay adónde volver.
assert.strictEqual(urlSamplerVuelta('', '/x'), null);
assert.strictEqual(urlSamplerVuelta(null, '/x'), null);
// src previo impronunciable → se devuelve tal cual (mejor recargar eso que nada).
assert.strictEqual(urlSamplerVuelta('::no-url::', '/x'), '::no-url::');
console.log('urlSamplerVuelta: OK');

// ── notaNueva: el papel nace a la DERECHA de todo lo que ya hay en el board ──
let nn = notaNueva([]);
assert.deepStrictEqual({ x: nn.x, y: nn.y, w: nn.w, h: nn.h }, { x: 0, y: 0, w: 320, h: 300 });
assert.strictEqual(nn.titulo, '');
assert.strictEqual(nn.cuerpo, '');
assert.strictEqual(nn.secreta, 0);
assert.strictEqual(nn.color, 'papel');
// Con un teléfono y una card web: se ubica pasando al más DERECHO, a su altura.
nn = notaNueva([{ x: 0, y: 0, w: 393, h: 852 }, { x: 463, y: 120, w: 960, h: 640 }]);
assert.strictEqual(nn.x, 463 + 960 + 70);
assert.strictEqual(nn.y, 120);
console.log('notaNueva: OK');

// ── notaSaneada: una fila corrupta del server no rompe el board ──
assert.strictEqual(notaSaneada(null), null);
assert.strictEqual(notaSaneada({ id: 0 }), null);          // sin id usable
assert.strictEqual(notaSaneada({ id: 'x' }), null);
let ns = notaSaneada({ id: '7', titulo: 'Expo', cuerpo: 'user/pass', secreta: true, color: 'ambar', x: 10, y: 20, w: 400, h: 500 });
assert.deepStrictEqual(ns, { id: 7, titulo: 'Expo', cuerpo: 'user/pass', secreta: 1, color: 'ambar', x: 10, y: 20, w: 400, h: 500 });
ns = notaSaneada({ id: 2, titulo: 99, cuerpo: null, color: 'fucsia', x: 'ñ', y: 99999, w: 10, h: 99999 });
assert.strictEqual(ns.titulo, '');        // no-string → vacío
assert.strictEqual(ns.cuerpo, '');
assert.strictEqual(ns.secreta, 0);
assert.strictEqual(ns.color, 'papel');    // color desconocido → papel
assert.strictEqual(ns.x, 0);              // x inválida → default
assert.strictEqual(ns.y, 50000);          // clampeada
assert.strictEqual(ns.w, 220);            // mínimo usable
assert.strictEqual(ns.h, 4000);           // techo
console.log('notaSaneada: OK');

// ── tituloNota: fallback legible para aria-labels y toasts ──
assert.strictEqual(tituloNota({ titulo: '  Cuenta EAS ' }), 'Cuenta EAS');
assert.strictEqual(tituloNota({ titulo: '   ' }), 'Nota sin título');
assert.strictEqual(tituloNota(null), 'Nota sin título');
console.log('tituloNota: OK');

console.log('mobile-preview-pure: OK');
