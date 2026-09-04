// JARVIS — Escala de la app (zoom global de la interfaz). Lógica pura testeable
// en Node + aplicación DOM, mismo patrón que themes.js.
//
// El usuario elige cuán grande se ve TODO el workspace —franja, barra, cards,
// dock, overlays y el texto de las terminales— sin tocar el zoom del navegador
// (que en la app de escritorio ni siquiera tiene atajo).
//
// MOTOR: `zoom` en <html>. NO es `transform: scale()`: zoom entra en el LAYOUT,
// así que xterm re-mide su celda y redibuja el canvas a la escala nueva —
// texto NÍTIDO, no una foto agrandada (verificado en browser a 70/80/130/150%).
//
// GOTCHA (la razón de --jw-vh / --jw-vw): las unidades de viewport NO se ajustan
// por zoom. Con `zoom: 1.25`, un `height: 100vh` sigue midiendo la ventana entera
// y el shell termina 25% más alto que la pantalla (scroll, dock cortado, diálogos
// que se van abajo, breadcrumb pisando la marca). Por eso el workspace mide el
// viewport con `var(--jw-vh, 100vh)` / `var(--jw-vw, 100vw)` (declaradas en
// tokens.css) y este módulo las mantiene en `calc(100vh / factor)`. Si agregás
// una medida relativa a la pantalla, usá esas variables — nunca vh/vw pelados.
(function (global) {
  'use strict';

  // Porcentajes enteros. El rango es el usable de verdad: abajo de 70% la
  // tipografía de 11px se vuelve ilegible; arriba de 150% no entra un mosaico
  // de terminales en una pantalla común.
  const MIN = 70, MAX = 150, PASO = 5, DEF = 100;

  function normalizar(v) {
    // null/''/undefined = "nunca eligió nada" → 100%, NO el piso del rango
    // (Number(null) es 0, que clampearía a MIN y arrancaría la app al 70%).
    if (v === null || v === undefined || v === '') return DEF;
    const n = Number(v);
    if (!Number.isFinite(n)) return DEF;
    const snap = Math.round(n / PASO) * PASO;
    return Math.min(MAX, Math.max(MIN, snap));
  }
  function esDefault(v) { return normalizar(v) === DEF; }
  function factor(v) { return normalizar(v) / 100; }
  function etiqueta(v) { return `${normalizar(v)}%`; }

  const pure = { MIN, MAX, PASO, DEF, normalizar, esDefault, factor, etiqueta };
  // px CSS = px de PANTALLA / zoom. Los eventos del mouse (clientX/clientY, y las
  // distancias que salen de restarlos) vienen en píxeles de pantalla, pero todo lo
  // que se escribe en un style —left/top de un menú, el ancho de un panel— se
  // interpreta en píxeles CSS, que el zoom vuelve a multiplicar. Sin esta división
  // el menú contextual aparece corrido y los arrastres se van del cursor.
  pure.aCss = function aCss(px, zoomActual) {
    const z = (Number.isFinite(zoomActual) && zoomActual > 0) ? zoomActual : 1;
    const n = Number(px);
    return Number.isFinite(n) ? n / z : 0;
  };
  global.JarvisEscala = Object.assign(global.JarvisEscala || {}, { _pure: pure, ...pure });

  if (typeof document !== 'undefined') {
    const KEY = 'jarvis.escala';
    let _tAcomodar = 0, _tAcomodar2 = 0;

    function actual() {
      try { return normalizar(localStorage.getItem(KEY)); } catch { return DEF; }
    }

    function _pintar(n) {
      const el = document.documentElement;
      if (n === DEF) {
        el.style.removeProperty('zoom');
        el.style.removeProperty('--jw-vh');
        el.style.removeProperty('--jw-vw');
        return;
      }
      const f = factor(n);
      el.style.setProperty('zoom', String(f));
      el.style.setProperty('--jw-vh', `calc(100vh / ${f})`);
      el.style.setProperty('--jw-vw', `calc(100vw / ${f})`);
    }

    // Cambiar la escala cambia el tamaño en píxeles CSS de cada card: xterm y
    // Monaco tienen que re-medirse. Debounce: el arrastre del slider dispara
    // esto muchas veces y un fit() por frame es carísimo (regla xterm).
    //
    // El refit de cada terminal va FORZADO (force=true) a propósito: el camino
    // normal se saltea el fit si el contenedor "ya midió eso" (dedupe por
    // clientWidth/Height) o si el motor cree que hay un arrastre en curso, y con
    // el zoom esas dos condiciones mienten — al volver de 70% a 100% el canvas se
    // quedaba con la grilla del 70% (290×54) desbordando la card 385px.
    //
    // Y va DOS VECES: xterm re-mide la celda recién cuando redibuja con el zoom
    // nuevo, así que la primera pasada puede calcular con la celda vieja. La
    // segunda ya ve la definitiva y deja la grilla exacta (sin esto, a 125% el
    // composer del agente quedaba tapado abajo).
    function _refitTerminales() {
      try { global.TerminalLayout?.relayoutAll?.(); } catch (_) {}
      try {
        const vivas = global.terminalesXterm;
        if (vivas && global.refitTerminal) {
          for (const id of vivas.keys()) { try { global.refitTerminal(id, true); } catch (_) {} }
        }
      } catch (_) {}
      try { global.JarvisEditor?.relayout?.(); } catch (_) {}
    }

    function _acomodar(n) {
      clearTimeout(_tAcomodar);
      clearTimeout(_tAcomodar2);
      _tAcomodar = setTimeout(() => {
        _refitTerminales();
        try { global.dispatchEvent(new CustomEvent('escala-changed', { detail: n })); } catch (_) {}
        _tAcomodar2 = setTimeout(_refitTerminales, 280);
      }, 140);
    }

    // silencioso=true: para el arrastre vivo del slider (pinta ya, sin avisarle
    // a nadie); al soltar, un aplicar() normal acomoda terminales y editor.
    function aplicar(valor, opts) {
      const n = normalizar(valor);
      try {
        if (n === DEF) localStorage.removeItem(KEY);
        else localStorage.setItem(KEY, String(n));
      } catch (_) {}
      _pintar(n);
      if (!(opts && opts.silencioso)) _acomodar(n);
      return n;
    }

    // Zoom REALMENTE aplicado en <html> (no el guardado): es lo que hay que usar
    // para traducir coordenadas del mouse mientras la app está pintada.
    function zoom() {
      try {
        const z = parseFloat(document.documentElement.style.zoom);
        return (Number.isFinite(z) && z > 0) ? z : 1;
      } catch (_) { return 1; }
    }

    Object.assign(global.JarvisEscala, {
      actual, aplicar, zoom,
      // px de pantalla → px CSS, con el zoom vivo. La usan los puntos de la UI que
      // posicionan algo o miden un arrastre a partir de clientX/clientY.
      aCss: (px) => pure.aCss(px, zoom()),
      init() { _pintar(actual()); },
    });
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = pure;
})(typeof window !== 'undefined' ? window : globalThis);
