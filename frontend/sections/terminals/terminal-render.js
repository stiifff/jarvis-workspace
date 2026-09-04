'use strict';
// Cura del bug "terminal NEGRA hasta scrollear" — ver [[negro-al-maximizar-raf-starvation]].
//
// Causa raíz (medida en banco de pruebas, 2026-07-04): term.resize() reasigna
// canvas.width en el CanvasAddon → el canvas queda BORRADO (se ve el fondo oscuro),
// y el repintado vive en el ÚNICO rAF del RenderDebouncer de xterm. Bajo carga del
// hilo principal (terminales ocultas siguen PARSEANDO su WS aunque no rendericen)
// ese rAF se starva por SEGUNDOS: el frame scheduling del browser es lo que se muere
// de hambre, mientras las tasks normales (onmessage, timers) sí siguen corriendo.
// term.refresh() NO cura nada: solo fusiona filas en el rAF ya pendiente.
// Un scroll/tecla "curaba" porque el input real fuerza al event loop a servir frames.
//
// Dos armas, ambas apoyadas en internals ESTABLES de xterm 5.3 (vendoreado, no
// cambia solo) y con degradación a term.refresh si un upgrade los mueve:
//  · pintarYa(term): repinta el viewport SINCRÓNICO, en la MISMA task que el resize
//    que borró el canvas → el compositor jamás llega a mostrar el canvas vacío.
//  · blindarRenderStarvation(term): fallback por setTimeout en el debouncer — si el
//    rAF no corrió en STARVE_MS, pinta el timer (task normal que compite justo con
//    los onmessage). Acota TODO negro residual (unpause tras overlays, seeds, etc.).
(function (global) {

  // Cota del negro bajo starvation. El banco midió: sin input el rAF tarda mediana
  // 222ms / máx 5004ms; con input real ~250-330ms. 50ms de timer deja el hueco
  // por debajo del umbral perceptible sin agregar presión (1 timer por frame, se
  // desarma en el camino feliz donde el rAF corre a ~16ms).
  const STARVE_MS = 50;

  function _svc(term) {
    try { return (term && term._core && term._core._renderService) || null; } catch (_) { return null; }
  }

  function _fallbackRefresh(term) {
    try { term.refresh(0, (term.rows || 1) - 1); } catch (_) {}
  }

  /**
   * Repinta el viewport COMPLETO ahora mismo, saltando el rAF del RenderDebouncer.
   * Llamar SIEMPRE inmediatamente después de un term.resize()/fit (es lo que borra
   * el canvas). Si el render está pausado (card fuera de viewport) degrada a
   * term.refresh: xterm marca _needsFullRefresh y pinta solo al volver a ser visible.
   * `aunPausado` puentea ese gate para el caso "pausa RANCIA": la card ya está
   * visible pero el unpause del IntersectionObserver de xterm todavía no se entregó
   * (frames atrasados bajo carga) — svc.refreshRows tragaría el pedido, así que se
   * va directo al debouncer de la instancia. Solo usarlo sabiendo que la card tiene
   * caja real (ver blindarWipeCanvas). Devuelve 'sync' | 'fallback' | 'noop'.
   */
  function pintarYa(term, aunPausado) {
    if (!term) return 'noop';
    const svc = _svc(term);
    const deb = svc && svc._renderDebouncer;
    if (!svc || !deb || typeof deb._innerRefresh !== 'function' ||
        typeof deb.refresh !== 'function' || typeof svc.refreshRows !== 'function' ||
        (svc._isPaused === true && !aunPausado)) {
      _fallbackRefresh(term);
      return 'fallback';
    }
    try {
      if (svc._isPaused === true) {
        deb.refresh(0, (term.rows || 1) - 1, term.rows || 1);   // directo: sin el gate de pausa
      } else {
        svc.refreshRows(0, (term.rows || 1) - 1);   // marca todo el viewport (y agenda un rAF)
      }
      // Cancelar el rAF recién agendado ANTES de pintar: _innerRefresh limpia
      // _animationFrame pero NO cancela el frame en sí → quedaría un paint doble.
      const win = deb._parentWindow;
      if (deb._animationFrame !== undefined && win && typeof win.cancelAnimationFrame === 'function') {
        win.cancelAnimationFrame(deb._animationFrame);
        deb._animationFrame = undefined;
      }
      deb._innerRefresh();                         // pinta YA, en esta misma task
      return 'sync';
    } catch (_) {
      _fallbackRefresh(term);
      return 'fallback';
    }
  }

  /**
   * Blinda el RenderDebouncer de UNA terminal contra la starvation del rAF:
   * cada vez que se agenda un frame, arma un setTimeout de respaldo — si el rAF
   * no corrió en `ms`, pinta el timer y cancela el rAF. En el camino feliz el
   * rAF corre a ~16ms y desarma el timer (cero repintados extra).
   * Cubre los negros que NO nacen de un resize nuestro: el full-refresh al
   * des-pausar (volver de un overlay / cambio de proyecto), seeds del WS, etc.
   * Idempotente. Devuelve true si pudo blindar (false = internals desconocidos,
   * p.ej. un upgrade de xterm: el comportamiento queda como el actual).
   */
  function blindarRenderStarvation(term, ms) {
    const espera = ms || STARVE_MS;
    const svc = _svc(term);
    const deb = svc && svc._renderDebouncer;
    const win = deb && deb._parentWindow;
    if (!deb || !win || typeof win.setTimeout !== 'function' ||
        typeof deb.refresh !== 'function' || typeof deb._innerRefresh !== 'function') return false;
    if (deb._jrvBlindado) return true;
    deb._jrvBlindado = true;

    const refreshOrig = deb.refresh.bind(deb);
    const innerOrig = deb._innerRefresh.bind(deb);

    const desarmar = () => {
      if (deb._jrvTimer !== undefined) { win.clearTimeout(deb._jrvTimer); deb._jrvTimer = undefined; }
    };

    // Cualquier paint (rAF, timer o pintarYa) pasa por _innerRefresh → desarma el timer.
    deb._innerRefresh = function () { desarmar(); innerOrig(); };

    deb.refresh = function (a, b, c) {
      refreshOrig(a, b, c);
      if (deb._animationFrame !== undefined && deb._jrvTimer === undefined) {
        deb._jrvTimer = win.setTimeout(() => {
          deb._jrvTimer = undefined;
          if (deb._animationFrame === undefined) return;   // el rAF ya pintó (o dispose)
          try { win.cancelAnimationFrame(deb._animationFrame); } catch (_) {}
          deb._animationFrame = undefined;
          deb._innerRefresh();
        }, espera);
      }
    };
    return true;
  }

  // ── Tercera capa (2026-07-11): "letras desaparecidas hasta scrollear" ──
  // Las dos armas de arriba cubren el canvas borrado por RESIZE (pintarYa) y el
  // rAF starved (blindar). Quedaba la familia "el BITMAP del canvas murió sin
  // que xterm se entere": Chromium/WebView2 hiberna o descarta el backing store
  // de un canvas oculto (display:none al maximizar otra card) o tapado (app en
  // segundo plano), y en GPU reset pierde el contexto 2D. xterm no repinta si
  // ninguna fila quedó sucia → letras en negro; un scroll "curaba" porque fuerza
  // refreshRows. Tres ganchos one-shot (cero costo estable):
  //  · repintarAlMostrar: transición oculta→visible del container → repintado.
  //  · blindarContextoCanvas: contextrestored (Chromium ≥99) → repintado.
  //  · (en terminal.js) focus/visibilitychange de la página → repintado de las visibles.

  // PURA: repintar SOLO en la transición oculta→visible. antes=null (primera
  // observación del IO) no repinta: evita el doble paint del arranque.
  function debeRepintarAlMostrar(antes, ahora) {
    return antes === false && ahora === true;
  }

  /**
   * Observa el container de una terminal y repinta al volver a ser visible.
   * El refresh inmediato marca TODO el viewport sucio (si xterm sigue "paused"
   * queda _needsFullRefresh armado y su propio unpause repinta); el pintarYa en
   * rAF cubre el caso en que xterm ya des-pausó (paint síncrono sin esperar su
   * debouncer). Devuelve el IntersectionObserver (disposer) o null si no hay IO.
   */
  function repintarAlMostrar(term, elemento) {
    if (!term || !elemento || typeof IntersectionObserver === 'undefined' ||
        typeof requestAnimationFrame === 'undefined') return null;
    let visible = null;
    const io = new IntersectionObserver(entries => {
      const e = entries[entries.length - 1];
      const ahora = !!(e && e.isIntersecting);
      const antes = visible;
      visible = ahora;
      if (!debeRepintarAlMostrar(antes, ahora)) return;
      _fallbackRefresh(term);
      requestAnimationFrame(() => pintarYa(term));
    }, { threshold: 0 });
    try { io.observe(elemento); } catch (_) { return null; }
    return io;
  }

  /**
   * contextlost/contextrestored del canvas 2D (Chromium ≥99: GPU reset o
   * descarte del backing store): al restaurar, el bitmap está VACÍO y xterm no
   * lo sabe → repintado completo. Listeners pasivos sobre cada capa canvas del
   * container (texto/selección/cursor/link — y el del WebGL, inofensivo: ese
   * addon ya maneja su propio webglcontextlost). Devuelve cuántas capas blindó.
   */
  function blindarContextoCanvas(term, elemento) {
    if (!term || !elemento || typeof elemento.querySelectorAll !== 'function') return 0;
    let n = 0;
    try {
      elemento.querySelectorAll('canvas').forEach(c => {
        c.addEventListener('contextrestored', () => pintarYa(term));
        n++;
      });
    } catch (_) { /* DOM raro: sin blindaje, comportamiento actual */ }
    return n;
  }

  // ── Cuarta capa (2026-07-18): el WIPE ASYNC del propio CanvasAddon ──
  // Causa raíz del "letras invisibles al eliminar/maximizar" que sobrevivía a las
  // tres capas (banco con stacks capturados): el CanvasAddon trae SU PROPIO
  // ResizeObserver (observeDevicePixelDimensions → _setCanvasDevicePixelDimensions
  // → layer.resize) que llega 1-2 frames DESPUÉS de nuestro refit+pintarYa y
  // reasigna canvas.width/height cuando el tamaño en device-pixels difiere del que
  // calculó handleResize por REDONDEO SUB-PIXEL (depende de la geometría exacta del
  // tile → "algunas veces"; con DPR fraccional de Windows pasa mucho más). Ese
  // re-set BORRA el bitmap; su pedido de redraw se pierde si el service está
  // pausado (el unpause del IntersectionObserver viaja todavía, típico tras
  // display:none→visible de maximizar/restaurar/eliminar) o si otro wipe cae
  // después del último refresh. El state-cache de la capa queda limpio → xterm
  // cree que está todo pintado → NADA repinta hasta que un scroll/output ensucia
  // filas. Cura en el punto exacto de la invalidación: MutationObserver sobre
  // width/height de cada capa — el microtask corre ANTES de que el compositor
  // muestre el frame → pintarYa inmediato (pausado degrada a term.refresh → el
  // unpause pinta). Cubre TODOS los wipers: el RO del addon, handleResize y
  // cualquier futuro. Costo estable cero (solo dispara en re-sets reales).

  /**
   * Vigila los atributos width/height de cada capa canvas del container y repinta
   * ante cualquier reasignación (= bitmap borrado). Devuelve el MutationObserver
   * (disposer: .disconnect() al cerrar la terminal) o null si no hay
   * MutationObserver / no hay capas. Un solo observer por terminal.
   */
  function blindarWipeCanvas(term, elemento) {
    if (!term || !elemento || typeof MutationObserver === 'undefined' ||
        typeof elemento.querySelectorAll !== 'function') return null;
    let capas;
    try { capas = elemento.querySelectorAll('canvas'); } catch (_) { return null; }
    if (!capas || !capas.length) return null;
    const mo = new MutationObserver(() => {
      // Pausa RANCIA: si la card tiene caja (visible de verdad), pintar aunque
      // xterm se crea pausado — el unpause de su IO puede tardar frames bajo
      // carga y ese hueco era el flash en blanco. Genuinamente oculta
      // (offsetParent null, mismo discriminador que _repintarAlVolver):
      // fallback a term.refresh → needsFullRefresh → el unpause pinta.
      let visible = true;
      try { visible = elemento.offsetParent !== null; } catch (_) {}
      pintarYa(term, visible);
    });
    try {
      capas.forEach(c => mo.observe(c, { attributes: true, attributeFilter: ['width', 'height'] }));
    } catch (_) { /* DOM raro: lo observado hasta acá queda vigilado igual */ }
    return mo;
  }

  const api = { STARVE_MS, pintarYa, blindarRenderStarvation,
                debeRepintarAlMostrar, repintarAlMostrar, blindarContextoCanvas,
                blindarWipeCanvas };
  global.TerminalRender = Object.assign(global.TerminalRender || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
