/* ════════════════════════════════════════════════════════════════
   Mobile Preview — lógica pura (testeable en Node).

   Geometría del marco del teléfono: orientación + escala con zoom + chrome
   (status bar / safe areas). El panel ya NO arranca Metro: solo detecta el Expo
   que corre en una terminal, así que la decisión de auto-arranque se eliminó.
═══════════════════════════════════════════════════════════════ */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.MobilePreviewPure = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // Viewport del device según orientación (landscape intercambia ancho/alto).
  function dimsOrientadas(w, h, orientacion) {
    return orientacion === 'landscape' ? { w: h, h: w } : { w: w, h: h };
  }

  // Escala del marco para entrar en el contenedor manteniendo el viewport real.
  // base = encajar (tope 1, sin agrandar de más); luego se multiplica por el
  // zoom manual (50–200% → 0.5–2.0). Nunca negativa (contenedor degenerado).
  function escalaFrame(bw, bh, w, h, zoom, margen) {
    if (zoom == null) zoom = 100;
    if (margen == null) margen = 24;
    if (!(w > 0) || !(h > 0)) return 0;
    var base = Math.min((bw - margen) / w, (bh - margen) / h, 1);
    if (!(base > 0)) base = 0;
    return base * (zoom / 100);
  }

  // Transform del marco: el pan (arrastre libre) va como translate ANTES del
  // scale, así sus px son px de pantalla (arrastre 1:1 con el cursor, sin que la
  // escala los distorsione). transform-origin: center en CSS.
  function transformFrame(panX, panY, escala) {
    return 'translate(' + (panX || 0) + 'px, ' + (panY || 0) + 'px) scale(' + escala + ')';
  }

  // Decide si AUTO-ABRIR la pestaña Móvil al entrar a un proyecto Expo.
  // Regla anti-molestia (pedido del usuario): el Móvil se auto-abre UNA sola
  // vez por proyecto (la primera). Si después lo cerrás con la ✕, NO se te
  // vuelve a abrir solo cuando re-entrás a ese proyecto — su estado lo gobierna
  // el dock (persistido por proyecto). Para traerlo de vuelta, abrís la pestaña
  // Móvil a mano desde el panel.
  //   autoAbrir   — true SOLO al entrar al proyecto (no en re-sincronizaciones).
  //   autoMostrar — toggle global jarvis.autoMobilePreview (ON por default).
  //   enMobile    — el dock ya está abierto en la pestaña Móvil (estado restaurado).
  //   yaVisto     — ya se auto-mostró el Móvil de ESTE proyecto antes.
  // Devuelve { abrir, visto }: abrir = ¿abrirlo ahora?; visto = flag a persistir.
  function debeAutoAbrir(autoAbrir, autoMostrar, enMobile, yaVisto) {
    // Sin entrada de proyecto o con el auto-preview global apagado: no tocamos
    // nada y NO quemamos la "primera vez" (si luego prendés el toggle, se verá).
    if (!autoAbrir || !autoMostrar) return { abrir: false, visto: !!yaVisto };
    // Ya está a la vista (lo dejaste activo) o ya se mostró antes: no forzar,
    // pero dejarlo marcado como visto para no re-aparecer tras un cierre futuro.
    if (enMobile || yaVisto) return { abrir: false, visto: true };
    // Primera vez en este proyecto: abrir y marcar visto.
    return { abrir: true, visto: true };
  }

  // Decide si la detección de Metro AUTO-AGREGA el teléfono default al lienzo.
  // Regla anti-molestia (hermana de debeAutoAbrir): si el usuario QUITÓ el
  // último teléfono a propósito (sinTelefono, persistido por proyecto), la app
  // detectada NO lo repone — vuelve solo cuando él lo agrega a mano.
  function debeAutoAgregarTelefono(numTelefonos, sinTelefono) {
    return numTelefonos === 0 && !sinTelefono;
  }

  // (chromeFrame se ELIMINÓ: encogía el iframe al "área segura", que es lo
  // CONTRARIO al device real — las apps son edge-to-edge y el hardware las
  // tapa por encima. La geometría real vive en device-catalog.js y el panel
  // la dibuja como OVERLAYS sobre el iframe a viewport completo.)

  // ── Status bar adaptativa: análisis del color muestreado ────────────────────
  // El sampler reporta colores COMPUTADOS del browser: casi siempre rgb()/rgba(),
  // pero se toleran #hex y el color(srgb …) de Chrome moderno.
  function parseCssColor(s) {
    if (typeof s !== 'string') return null;
    s = s.trim();
    var m = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/i.exec(s);
    if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] == null ? 1 : +m[4] };
    m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(s);
    if (m) {
      var h = m[1];
      if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
      return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16), b: parseInt(h.slice(4, 6), 16), a: 1 };
    }
    m = /^color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+))?\)$/i.exec(s);
    if (m) return { r: 255 * +m[1], g: 255 * +m[2], b: 255 * +m[3], a: m[4] == null ? 1 : +m[4] };
    return null;
  }

  // Luminancia relativa WCAG (0 = negro, 1 = blanco), sRGB linealizado.
  function luminancia(c) {
    var lin = function (v) { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  }

  // ¿Un background-image reportado por el sampler es un gradiente CSS puro y
  // seguro para inyectar como estilo? (sin url() — nada de cargar recursos —
  // y con pinta de gradiente de verdad; largo acotado por sanidad).
  function esGradienteSeguro(s) {
    if (typeof s !== 'string' || !s || s.length > 2400) return false;
    if (/url\s*\(/i.test(s)) return false;
    return /^(repeating-)?(linear|radial|conic)-gradient\(/i.test(s.trim());
  }

  // Color MÁS VOTADO entre varios puntos muestreados (ignora imparseables).
  // Un toast/overlay tapa UN punto; la mayoría sigue siendo el fondo real.
  function colorMayoria(lista) {
    var cuenta = {}, mejor = null, n = 0;
    (lista || []).forEach(function (c) {
      if (!parseCssColor(c)) return;
      cuenta[c] = (cuenta[c] || 0) + 1;
      if (cuenta[c] > n) { n = cuenta[c]; mejor = c; }
    });
    return mejor;
  }

  // ¿Fondo CLARO (→ íconos oscuros, como el status bar real de iOS/Android)?
  // null = indeterminado (color raro o casi transparente): el caller conserva
  // el default de íconos blancos. Umbral 0.4: gris medio ya pide íconos negros
  // (mismo criterio perceptual que usa iOS con fondos intermedios).
  function esFondoClaro(colorStr, umbral) {
    if (umbral == null) umbral = 0.4;
    var c = parseCssColor(colorStr);
    if (!c || c.a < 0.5) return null;
    return luminancia(c) > umbral;
  }

  // ── Lienzo del Studio (pan/zoom sobre el board de teléfonos) ──────────────
  // El board se transforma con translate(pan) scale(zoom), transform-origin 0 0:
  // un punto del board (bx,by) cae en pantalla en (panX+bx*zoom, panY+by*zoom).

  function clampZoom(z, min, max) {
    if (min == null) min = 0.2;
    if (max == null) max = 3;
    if (!(z > 0)) z = min;
    return Math.max(min, Math.min(max, z));
  }

  // Encuadra TODOS los teléfonos en el viewport: calcula el bounding box (cada
  // phone = {x,y,w,h} en unidades del board, w/h ya con su escala propia) y
  // devuelve {zoom,panX,panY} para centrarlo con margen. maxZoom evita agrandar
  // de más cuando hay un solo teléfono chico.
  function fitAll(phones, vw, vh, margen, maxZoom) {
    if (margen == null) margen = 56;
    if (maxZoom == null) maxZoom = 1;
    if (!phones || !phones.length || !(vw > 0) || !(vh > 0)) {
      return { zoom: 1, panX: 0, panY: 0 };
    }
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (var i = 0; i < phones.length; i++) {
      var p = phones[i];
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x + p.w > maxX) maxX = p.x + p.w;
      if (p.y + p.h > maxY) maxY = p.y + p.h;
    }
    var bw = maxX - minX, bh = maxY - minY;
    if (!(bw > 0) || !(bh > 0)) return { zoom: 1, panX: 0, panY: 0 };
    var zoom = Math.min((vw - 2 * margen) / bw, (vh - 2 * margen) / bh, maxZoom);
    zoom = clampZoom(zoom);
    var cx = minX + bw / 2, cy = minY + bh / 2;
    return { zoom: zoom, panX: vw / 2 - cx * zoom, panY: vh / 2 - cy * zoom };
  }

  // Zoom manteniendo fijo el punto de pantalla (cx,cy) — zoom hacia el cursor.
  function zoomAt(zoom, panX, panY, factor, cx, cy, min, max) {
    var nz = clampZoom(zoom * factor, min, max);
    var k = nz / zoom;
    return { zoom: nz, panX: cx - (cx - panX) * k, panY: cy - (cy - panY) * k };
  }

  // Transform del BOARD del lienzo (origin 0 0): pan primero, luego scale.
  function transformBoard(panX, panY, zoom) {
    return 'translate(' + (panX || 0) + 'px, ' + (panY || 0) + 'px) scale(' + (zoom || 1) + ')';
  }

  // ── Cards de NAVEGADOR en el lienzo (browse nativo) ────────────
  // Una card web = { id, url, x, y, w, h } en unidades del board, conviviendo
  // con los teléfonos. Geometría default: tamaño desktop cómodo, ubicada a la
  // derecha del elemento existente más a la derecha (phones y webs por igual).

  var WEB_W = 960, WEB_H = 640, WEB_SEP = 70;

  function webNueva(id, existentes) {
    var x = 0, y = 0, maxDer = -Infinity;
    for (var i = 0; i < (existentes || []).length; i++) {
      var e = existentes[i];
      var der = (e.x || 0) + (e.w || 0);
      if (der > maxDer) { maxDer = der; y = e.y || 0; }
    }
    if (maxDer > -Infinity) x = maxDer + WEB_SEP;
    return { id: id, url: '', x: x, y: y, w: WEB_W, h: WEB_H };
  }

  // Normaliza lo tipeado en la barra de una card: agrega https:// si no trae
  // esquema; solo http/https valen. Devuelve '' si no es usable como URL.
  function normalizarUrlWeb(input) {
    var s = String(input == null ? '' : input).trim();
    if (!s) return '';
    if (/^https?:\/\//i.test(s)) return s;
    if (/^[a-z][a-z0-9+.-]*:/i.test(s)) return '';   // otro esquema (file:, etc.)
    if (!/^[^\s]+\.[^\s]{2,}/.test(s)) return '';    // sin pinta de dominio
    return 'https://' + s;
  }

  // Saneo al restaurar de localStorage (basura vieja no rompe el board).
  function webSaneada(w) {
    if (!w || typeof w !== 'object') return null;
    var id = Number(w.id);
    if (!Number.isFinite(id) || id <= 0) return null;
    var num = function (v, def, min, max) {
      v = Number(v);
      if (!Number.isFinite(v)) return def;
      return Math.max(min, Math.min(max, v));
    };
    return {
      id: id,
      url: typeof w.url === 'string' ? w.url : '',
      x: num(w.x, 0, -50000, 50000),
      y: num(w.y, 0, -50000, 50000),
      w: num(w.w, WEB_W, 320, 4000),
      h: num(w.h, WEB_H, 220, 4000),
    };
  }

  // ── Notas del lienzo (papeles del proyecto) ───────────────────────────────
  // Una nota = { id, titulo, cuerpo, secreta, color, x, y, w, h } persistida en
  // la DB local (nunca en el repo). Geometría: papel angosto y alto, ubicado a
  // la derecha de todo lo que ya está en el board (misma regla que las cards web).

  var NOTA_W = 320, NOTA_H = 300, NOTA_SEP = 70;
  var NOTA_COLORES = ['papel', 'ambar', 'violeta', 'verde', 'cian', 'rosa'];

  function notaNueva(existentes) {
    var x = 0, y = 0, maxDer = -Infinity;
    for (var i = 0; i < (existentes || []).length; i++) {
      var e = existentes[i];
      var der = (e.x || 0) + (e.w || 0);
      if (der > maxDer) { maxDer = der; y = e.y || 0; }
    }
    if (maxDer > -Infinity) x = maxDer + NOTA_SEP;
    return { titulo: '', cuerpo: '', secreta: 0, color: 'papel', x: x, y: y, w: NOTA_W, h: NOTA_H };
  }

  // Saneo de lo que devuelve el server (una fila corrupta no rompe el board).
  function notaSaneada(n) {
    if (!n || typeof n !== 'object') return null;
    var id = Number(n.id);
    if (!Number.isFinite(id) || id <= 0) return null;
    var num = function (v, def, min, max) {
      v = Number(v);
      if (!Number.isFinite(v)) return def;
      return Math.max(min, Math.min(max, v));
    };
    return {
      id: id,
      titulo: typeof n.titulo === 'string' ? n.titulo : '',
      cuerpo: typeof n.cuerpo === 'string' ? n.cuerpo : '',
      secreta: n.secreta ? 1 : 0,
      color: NOTA_COLORES.indexOf(n.color) >= 0 ? n.color : 'papel',
      x: num(n.x, 0, -50000, 50000),
      y: num(n.y, 0, -50000, 50000),
      w: num(n.w, NOTA_W, 220, 4000),
      h: num(n.h, NOTA_H, 160, 4000),
    };
  }

  // Título que se muestra cuando la nota todavía no tiene uno (el placeholder
  // real vive en el input; esto es para el aria-label y los toasts).
  function tituloNota(n) {
    var t = (n && typeof n.titulo === 'string' ? n.titulo : '').trim();
    return t || 'Nota sin título';
  }

  // URL para VOLVER al espejo instrumentado tras un escape de navegación.
  // El sampler reescribe su URL a la ruta de la app (expo-router lee
  // location.pathname), así que un full reload adentro (HMR de Metro, `r` en
  // la terminal, location.reload()) recarga ESA ruta contra el origen de
  // Jarvis = el dashboard adentro del teléfono. El workspace deshace el escape
  // re-apuntando el iframe con esta URL. dsSrc = último src bueno del iframe
  // (relativo a Jarvis); rutaApp = ruta que la app tenía al descargarse.
  // Ruta inválida o src que no es un sampler → el src previo tal cual.
  function urlSamplerVuelta(dsSrc, rutaApp) {
    if (!dsSrc) return null;
    var rutaOk = typeof rutaApp === 'string' && rutaApp.charAt(0) === '/' && rutaApp.charAt(1) !== '/';
    if (!rutaOk) return dsSrc;
    try {
      var u = new URL(dsSrc, 'http://jarvis.invalid');
      if (u.pathname.slice(-8) !== '/sampler') return dsSrc;
      u.searchParams.set('ruta', rutaApp);
      return u.pathname + u.search;
    } catch (e) { return dsSrc; }
  }

  return {
    dimsOrientadas: dimsOrientadas,
    escalaFrame: escalaFrame,
    transformFrame: transformFrame,
    parseCssColor: parseCssColor,
    luminancia: luminancia,
    colorMayoria: colorMayoria,
    esFondoClaro: esFondoClaro,
    esGradienteSeguro: esGradienteSeguro,
    debeAutoAbrir: debeAutoAbrir,
    debeAutoAgregarTelefono: debeAutoAgregarTelefono,
    clampZoom: clampZoom,
    fitAll: fitAll,
    zoomAt: zoomAt,
    transformBoard: transformBoard,
    webNueva: webNueva,
    normalizarUrlWeb: normalizarUrlWeb,
    webSaneada: webSaneada,
    notaNueva: notaNueva,
    notaSaneada: notaSaneada,
    tituloNota: tituloNota,
    NOTA_COLORES: NOTA_COLORES,
    urlSamplerVuelta: urlSamplerVuelta,
  };
}));
