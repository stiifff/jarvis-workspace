/* ════════════════════════════════════════════════════════════════
   Device Catalog — dispositivos REALES para el Mobile Studio (puro, Node-testeable).

   Cada entrada describe un teléfono con sus medidas VERDADERAS en puntos CSS
   (pt lógicos = px CSS del viewport): viewport, safe areas, status bar, recorte
   (Dynamic Island / notch / punch-hole), radio de pantalla y home indicator.
   La regla de fidelidad: el iframe del preview mide EXACTAMENTE vw×vh del
   device y los overlays (isla, status bar, home bar) se dibujan con la
   geometría real 1:1 — así lo que tapa la isla acá es lo que tapa en la mano.

   DATOS INVESTIGADOS 2026-07-11 con fuentes cruzadas (no editar sin fuente):
   · iPhone: useyourloaf.com (viewports/safe areas/status bar, medidos en
     simulador por generación) + iosref.com (px/escala) + kylebshr/ScreenCorners
     (radios reales via _displayCornerRadius) + DynamicIslandUtilities y
     flutter device_frame (geometría de la isla: 126×37.33 @y11 vs 125×36.67
     @y11.33 — adoptamos 126×37.33 @y11; difieren <1pt).
   · Samsung: blisk/yesviz/viewport-tester + XDA (density de fábrica: Ultras
     rinden FHD+ a 450dpi → 384dp @2.8125, NO el 3.75 "de ficha"). El alto del
     S24/S25 base es 780 (el 800 viejo era del S20). Punch/radios/status ≈
     estimados (~3.2mm visibles → dp por panel; One UI no publica device tree).
   · Pixel: device trees de AOSP (config_mainBuiltInDisplayCutout verbatim:
     Pixel 8 punch ⌀27.6dp centro y=25 / Pixel 9 ⌀32 y=33; radio 96px=36.6dp).
     Status bar actual de Android 15+: P8 50dp / P9 66dp (más gruesa, real).
   · Android se modela con NAVEGACIÓN POR GESTOS (pill 108×4, inset 24dp):
     es el uso moderno real y coincide con apps edge-to-edge tipo Expo.
   Detalle y fuentes: [[mobile-studio-fidelidad]].
═══════════════════════════════════════════════════════════════ */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.DeviceCatalog = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ── Catálogo ───────────────────────────────────────────────────────────────
  // Esquema por device:
  //   nombre, marca ('apple'|'samsung'|'google'|'tablet')
  //   vw, vh    → viewport lógico portrait (pt CSS)
  //   dpr       → devicePixelRatio real (informativo: un iframe NO puede emularlo)
  //   statusBar → alto de la status bar del SO (pt); statusBarLand opcional
  //   safe      → insets reales: { top, bottom, landIzq, landDer, landBottom }
  //   cutout    → { tipo:'island'|'notch'|'punch'|'none', w, h, y } (pt, centrado)
  //   radio     → radio de esquina de la PANTALLA (pt); radioMarco opcional
  //               (default: radio + bezel — cierto en aparatos edge-to-edge)
  //   homebar   → { w, h, b } indicador de home (b = separación del borde) | null
  //   bezel     → grosor del marco físico dibujado (pt, estético)
  var HB_IOS = { w: 134, h: 5, b: 8 };      // home indicator iPhone (X-class, medido UIKit)
  var HB_AND = { w: 108, h: 4, b: 8 };      // pill de gestos stock Android
  var ISLA = { tipo: 'island', w: 126, h: 37.33, y: 11 };
  var DEVICES = {
    // ── iPhone ──
    ipse:   { nombre: 'iPhone SE', marca: 'apple', vw: 375, vh: 667, dpr: 2, statusBar: 20,
              safe: { top: 20, bottom: 0, landIzq: 0, landDer: 0, landBottom: 0 },
              cutout: { tipo: 'none' }, radio: 0, radioMarco: 34, homebar: null, bezel: 12 },
    ip13m:  { nombre: 'iPhone 13 mini', marca: 'apple', vw: 375, vh: 812, dpr: 3, statusBar: 50,
              safe: { top: 50, bottom: 34, landIzq: 50, landDer: 50, landBottom: 21 },
              cutout: { tipo: 'notch', w: 161, h: 32, y: 0 }, radio: 44, homebar: HB_IOS, bezel: 12 },
    ip13:   { nombre: 'iPhone 13 / 14', marca: 'apple', vw: 390, vh: 844, dpr: 3, statusBar: 47,
              safe: { top: 47, bottom: 34, landIzq: 47, landDer: 47, landBottom: 21 },
              cutout: { tipo: 'notch', w: 161, h: 32, y: 0 }, radio: 47.33, homebar: HB_IOS, bezel: 12 },
    ip14pl: { nombre: 'iPhone 14 Plus', marca: 'apple', vw: 428, vh: 926, dpr: 3, statusBar: 47,
              safe: { top: 47, bottom: 34, landIzq: 47, landDer: 47, landBottom: 21 },
              cutout: { tipo: 'notch', w: 160, h: 32, y: 0 }, radio: 53.33, homebar: HB_IOS, bezel: 12 },
    ip15p:  { nombre: 'iPhone 15 / 15 Pro', marca: 'apple', vw: 393, vh: 852, dpr: 3, statusBar: 54,
              safe: { top: 59, bottom: 34, landIzq: 59, landDer: 59, landBottom: 21 },
              cutout: ISLA, radio: 55, homebar: HB_IOS, bezel: 13 },
    ip15pm: { nombre: 'iPhone 15 Pro Max', marca: 'apple', vw: 430, vh: 932, dpr: 3, statusBar: 54,
              safe: { top: 59, bottom: 34, landIzq: 59, landDer: 59, landBottom: 21 },
              cutout: ISLA, radio: 55, homebar: HB_IOS, bezel: 13 },
    ip16p:  { nombre: 'iPhone 16 Pro / 17', marca: 'apple', vw: 402, vh: 874, dpr: 3, statusBar: 54,
              safe: { top: 62, bottom: 34, landIzq: 62, landDer: 62, landBottom: 21 },
              cutout: { tipo: 'island', w: 126, h: 37.33, y: 14 }, radio: 62, homebar: HB_IOS, bezel: 12 },
    ip16pm: { nombre: 'iPhone 16 Pro Max', marca: 'apple', vw: 440, vh: 956, dpr: 3, statusBar: 54,
              safe: { top: 62, bottom: 34, landIzq: 62, landDer: 62, landBottom: 21 },
              cutout: { tipo: 'island', w: 126, h: 37.33, y: 14 }, radio: 62, homebar: HB_IOS, bezel: 12 },
    ipair:  { nombre: 'iPhone Air', marca: 'apple', vw: 420, vh: 912, dpr: 3, statusBar: 54,
              safe: { top: 68, bottom: 34, landIzq: 68, landDer: 68, landBottom: 29 },
              cutout: { tipo: 'island', w: 126, h: 37.33, y: 20 }, radio: 62, homebar: HB_IOS, bezel: 11 },
    // ── Samsung (viewport de FÁBRICA; los Ultra rinden FHD+ → 384dp @2.8125) ──
    s21:    { nombre: 'Galaxy S21', marca: 'samsung', vw: 360, vh: 800, dpr: 3, statusBar: 28, statusBarLand: 24,
              safe: { top: 28, bottom: 24, landIzq: 25, landDer: 0, landBottom: 24 },
              cutout: { tipo: 'punch', w: 17, h: 17, y: 7.5 }, radio: 19, homebar: HB_AND, bezel: 11 },
    s24:    { nombre: 'Galaxy S23 / S24 / S25', marca: 'samsung', vw: 360, vh: 780, dpr: 3, statusBar: 28, statusBarLand: 24,
              safe: { top: 28, bottom: 24, landIzq: 25, landDer: 0, landBottom: 24 },
              cutout: { tipo: 'punch', w: 17, h: 17, y: 7.5 }, radio: 16, homebar: HB_AND, bezel: 10 },
    s23u:   { nombre: 'Galaxy S22/S23 Ultra', marca: 'samsung', vw: 384, vh: 824, dpr: 2.8125, statusBar: 28, statusBarLand: 24,
              safe: { top: 28, bottom: 24, landIzq: 25, landDer: 0, landBottom: 24 },
              cutout: { tipo: 'punch', w: 17, h: 17, y: 7.5 }, radio: 11, homebar: HB_AND, bezel: 10 },
    s24u:   { nombre: 'Galaxy S24/S25 Ultra', marca: 'samsung', vw: 384, vh: 832, dpr: 2.8125, statusBar: 28, statusBarLand: 24,
              safe: { top: 28, bottom: 24, landIzq: 25, landDer: 0, landBottom: 24 },
              cutout: { tipo: 'punch', w: 17, h: 17, y: 7.5 }, radio: 16, homebar: HB_AND, bezel: 11 },
    a55:    { nombre: 'Galaxy A54 / A55', marca: 'samsung', vw: 412, vh: 892, dpr: 2.625, statusBar: 28, statusBarLand: 24,
              safe: { top: 28, bottom: 24, landIzq: 27, landDer: 0, landBottom: 24 },
              cutout: { tipo: 'punch', w: 19, h: 19, y: 7.5 }, radio: 15, homebar: HB_AND, bezel: 13 },
    // ── Google (punch/radio verbatim de los device trees de AOSP) ──
    px8:    { nombre: 'Pixel 8', marca: 'google', vw: 412, vh: 915, dpr: 2.625, statusBar: 50, statusBarLand: 24,
              safe: { top: 50, bottom: 24, landIzq: 39, landDer: 0, landBottom: 24 },
              cutout: { tipo: 'punch', w: 27.6, h: 27.6, y: 11.2 }, radio: 37, homebar: HB_AND, bezel: 12 },
    px9:    { nombre: 'Pixel 9', marca: 'google', vw: 412, vh: 923, dpr: 2.625, statusBar: 66, statusBarLand: 24,
              safe: { top: 66, bottom: 24, landIzq: 49, landDer: 0, landBottom: 24 },
              cutout: { tipo: 'punch', w: 32, h: 32, y: 17 }, radio: 38, homebar: HB_AND, bezel: 12 },
    // ── Tablet ──
    ipad:   { nombre: 'iPad Pro 11″', marca: 'tablet', vw: 834, vh: 1194, dpr: 2, statusBar: 24,
              safe: { top: 24, bottom: 20, landIzq: 0, landDer: 0, landBottom: 20 },
              cutout: { tipo: 'none' }, radio: 18, homebar: { w: 315, h: 5, b: 8 }, bezel: 18 },
  };
  var ORDEN = [
    'ipse', 'ip13m', 'ip13', 'ip14pl', 'ip15p', 'ip15pm', 'ip16p', 'ip16pm', 'ipair',
    's21', 's24', 's23u', 's24u', 'a55',
    'px8', 'px9',
    'ipad',
  ];

  function device(key) { return DEVICES[key] || DEVICES.ip15p; }

  // Radio del marco exterior (chasis): radio de pantalla + bezel, salvo
  // aparatos de pantalla cuadrada con cuerpo redondeado (SE) que lo declaran.
  function frameRadius(key) {
    var d = device(key);
    return d.radioMarco != null ? d.radioMarco : d.radio + d.bezel;
  }

  // DPR legible para la UI ("3", "2.63", "2.81").
  function dprLabel(key) {
    var x = device(key).dpr;
    return x % 1 ? x.toFixed(2) : String(x);
  }

  // ── Viewport orientado ─────────────────────────────────────────────────────
  function dims(key, landscape) {
    var d = device(key);
    return landscape ? { w: d.vh, h: d.vw } : { w: d.vw, h: d.vh };
  }

  // Insets REALES del sistema: lo que SafeAreaView recibiría en el aparato.
  // Un iframe web ve env(safe-area-inset-*)=0, así que el preview ENCAJA la
  // app en esta área de contenido (misma geometría que en la mano) y pinta
  // las franjas con el color muestreado — ver [[mobile-studio-fidelidad]].
  function insets(key, landscape) {
    var d = device(key), s = d.safe || {};
    if (!landscape) return { top: s.top || 0, right: 0, bottom: s.bottom || 0, left: 0 };
    var top = d.marca === 'apple' ? 0
      : ((d.statusBarLand != null ? d.statusBarLand : d.statusBar) || 0);
    return { top: top, right: s.landDer || 0, bottom: s.landBottom || 0, left: s.landIzq || 0 };
  }

  // ── Geometría de overlays (cajas {x,y,w,h} en coordenadas del viewport) ────
  // En landscape el recorte queda en el borde IZQUIERDO (rotación natural del
  // aparato: la isla/punch gira con el vidrio), centrado vertical; la status
  // bar desaparece en iPhone (iOS la oculta en landscape) y el home indicator
  // sigue abajo, centrado.
  function cutoutBox(key, landscape) {
    var d = device(key), c = d.cutout;
    if (!c || c.tipo === 'none') return null;
    var v = dims(key, landscape);
    if (!landscape) return { x: (v.w - c.w) / 2, y: c.y, w: c.w, h: c.h, tipo: c.tipo };
    return { x: c.y, y: (v.h - c.w) / 2, w: c.h, h: c.w, tipo: c.tipo };
  }

  function statusBarBox(key, landscape) {
    var d = device(key);
    if (landscape && d.marca === 'apple') return null;   // iOS: sin status bar apaisado
    if (!d.statusBar) return null;
    var v = dims(key, landscape);
    var h = (landscape && d.statusBarLand != null) ? d.statusBarLand : d.statusBar;
    return { x: 0, y: 0, w: v.w, h: h };
  }

  function homebarBox(key, landscape) {
    var d = device(key);
    if (!d.homebar) return null;
    var v = dims(key, landscape);
    // Apaisado real: el indicador se estira (~exacto en iOS: mismo alto, ancho mayor).
    var w = landscape ? Math.round(d.homebar.w * 1.55) : d.homebar.w;
    return { x: (v.w - w) / 2, y: v.h - d.homebar.b - d.homebar.h, w: w, h: d.homebar.h };
  }

  // Zonas seguras como cajas sombreables (guías): lo que en el device real queda
  // tapado o reservado por el sistema. Devuelve lista (top/bottom o izq/der/bottom).
  function safeZones(key, landscape) {
    var d = device(key), v = dims(key, landscape), s = d.safe || {}, out = [];
    if (!landscape) {
      if (s.top) out.push({ lado: 'top', x: 0, y: 0, w: v.w, h: s.top });
      if (s.bottom) out.push({ lado: 'bottom', x: 0, y: v.h - s.bottom, w: v.w, h: s.bottom });
    } else {
      if (s.landIzq) out.push({ lado: 'izq', x: 0, y: 0, w: s.landIzq, h: v.h });
      if (s.landDer) out.push({ lado: 'der', x: v.w - s.landDer, y: 0, w: s.landDer, h: v.h });
      if (s.landBottom) out.push({ lado: 'bottom', x: 0, y: v.h - s.landBottom, w: v.w, h: s.landBottom });
    }
    return out;
  }

  return {
    DEVICES: DEVICES, ORDEN: ORDEN,
    device: device, dims: dims, insets: insets, frameRadius: frameRadius, dprLabel: dprLabel,
    cutoutBox: cutoutBox, statusBarBox: statusBarBox, homebarBox: homebarBox, safeZones: safeZones,
  };
}));
