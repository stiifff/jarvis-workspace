// Barra de título de la APP (Jarvis.exe, el shell de escritorio) — SOLO adentro.
//
// La ventana no tiene marco nativo (FormBorderStyle.None en scripts/jarvis-shell.cs):
// este módulo la reemplaza por controles integrados en el propio #jw-bar del
// workspace — arrastrar para mover, minimizar/maximizar/cerrar, doble-click para
// maximizar y zonas de resize en los bordes. En un browser normal NO hace nada
// (`window.__shell` no existe), así que el mismo frontend sirve a los dos.
//
// El puente lo publica el shell con AddScriptToExecuteOnDocumentCreated:
//   window.__shell.min() / .max() / .close() / .drag() / .resize(dir)
//   window.__shellMaximizado(bool)   ← lo llama el shell al cambiar de estado
//
// Autocontenido a propósito (inyecta su CSS y su HTML): workspace.html solo
// suma el <script>. Es el port a WebView2 del chrome que tenía la app vieja.
(function () {
  'use strict';
  var shell = window.__shell;
  if (!shell || !shell.drag) return;            // browser normal: no-op

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn, { once: true });
    } else { fn(); }
  }

  // Interactivo = no arrastra la ventana (mismo criterio que el chrome viejo).
  var INTERACTIVO = '.jw-icon-btn, button, input, select, textarea, a, [role="button"], #jw-winctl';

  // Dónde se monta el chrome, por página. La app arranca en el HOME (`/`), no
  // en el workspace: sin esta segunda entrada la ventana quedaba SIN botones y
  // sin poder moverse ni ir a pantalla completa hasta entrar a un proyecto.
  // `sangria` = padding lateral de esa barra, que se cancela con un margen
  // negativo para que la ✕ toque el borde real de la ventana.
  var SITIOS = [
    { barra: '#jw-bar', derecha: '.jw-bar-right', sangria: '6px' },   // workspace
    { barra: '.hc-top', derecha: '.hc-actions', sangria: '28px' }     // home
  ];

  ready(function () {
    var bar = null, right = null, sangria = '0px';
    for (var i = 0; i < SITIOS.length && !bar; i++) {
      var b = document.querySelector(SITIOS[i].barra);
      if (!b) continue;
      bar = b;
      right = document.querySelector(SITIOS[i].derecha) || b;
      sangria = SITIOS[i].sangria;
    }
    if (!bar) return;
    document.body.classList.add('app-chrome');

    inyectarCSS();
    var ctl = construirControles();
    ctl.style.marginRight = '-' + sangria;
    right.appendChild(ctl);
    montarResize();

    // Arrastrar la ventana desde la barra (salvo sobre algo interactivo).
    bar.addEventListener('mousedown', function (e) {
      if (e.button !== 0 || e.target.closest(INTERACTIVO)) return;
      if (document.body.classList.contains('app-fullscreen')) return;
      shell.drag();
    });

    // Doble-click en la zona draggable → igual que el botón maximizar.
    bar.addEventListener('dblclick', function (e) {
      if (e.target.closest(INTERACTIVO)) return;
      shell.max();
    });
  });

  // El shell avisa el estado real de la ventana (incluidos los cambios que hace
  // Windows solo: Win+Flechas, snap): alterna el ícono maximizar/restaurar y
  // apaga las zonas de resize. Ni maximizada ni en pantalla completa se
  // redimensiona — con los bordes vivos el drag la achicaba sola.
  window.__shellEstado = function (maximizada, fullscreen) {
    document.body.classList.toggle('app-maximized', !!maximizada);
    document.body.classList.toggle('app-fullscreen', !!fullscreen);
  };
  // Contrato viejo, por si algo todavía lo llama.
  window.__shellMaximizado = function (maximizada) {
    document.body.classList.toggle('app-maximized', !!maximizada);
  };

  // El shell avisa que la app se fue A LA BANDEJA (o volvió). Escondida no la
  // mira nadie, así que se apaga lo que gasta igual: la RADIO sobre todo — el
  // audio sigue sonando aunque la página esté oculta, el navegador no lo frena
  // solo. Las TERMINALES no se tocan: los agentes viven en tmux del lado del
  // server y tienen que seguir trabajando mientras la app no está.
  var _enBandeja = false;
  window.__shellOculto = function (oculto) {
    oculto = !!oculto;
    if (oculto === _enBandeja) return;      // idempotente: el par pausa/reanuda
    _enBandeja = oculto;                    // lleva contador y se desbalancea
    try {
      var r = window.JarvisRadio;
      if (!r) return;
      if (oculto) { r.pauseForTwitch && r.pauseForTwitch(); }
      else { r.resumeAfterTwitch && r.resumeAfterTwitch(); }
    } catch (e) { /* la radio puede no estar montada en esta página */ }
  };

  // El shell avisa que terminó de mover/redimensionar la ventana. Durante ese
  // gesto lo maneja Windows y la página NO recibe eventos de mouse, así que si
  // la ventana cambió de tamaño debajo del cursor el :hover queda PEGADO en el
  // botón que quedó ahí. Un pulso de pointer-events obliga al navegador a
  // recalcular qué está realmente bajo el cursor.
  window.__shellFinArrastre = function () {
    var ctl = document.getElementById('jw-winctl');
    if (!ctl) return;
    ctl.style.pointerEvents = 'none';
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { ctl.style.pointerEvents = ''; });
    });
  };

  // F11 = PANTALLA COMPLETA, como en la app vieja. Sin guard de INPUT/xterm a
  // propósito: tiene que responder siempre, incluso tipeando en una terminal.
  // En capture para ganarle a cualquier handler de la página. En un browser
  // normal este módulo ni corre, así que ahí F11 sigue siendo el de Chrome.
  //
  // Quién recuerda el estado previo (si venía maximizada, vuelve maximizada) es
  // el shell nativo, que es donde vive la verdad de la ventana.
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'F11' || !shell.fullscreen) return;
    e.preventDefault();
    shell.fullscreen();
  }, true);

  function construirControles() {
    var wrap = document.createElement('div');
    wrap.id = 'jw-winctl';
    wrap.setAttribute('aria-label', 'Controles de ventana');

    // Iconos del mockup: línea centrada, cuadrado REDONDEADO (rx grande) y ✕.
    // El maximizar conserva su variante "restaurar" cuando ya está maximizada.
    wrap.appendChild(boton('min', 'Minimizar',
      '<line x1="3" y1="8" x2="13" y2="8"/>', function () { shell.min(); }));

    wrap.appendChild(boton('max', 'Maximizar',
      '<rect class="ic-max" x="3.2" y="3.2" width="9.6" height="9.6" rx="2.1"/>' +
      '<path class="ic-restore" d="M5.6 5.6V4.4A1.4 1.4 0 0 1 7 3h4.6A1.4 1.4 0 0 1 13 4.4V9a1.4 1.4 0 0 1-1.4 1.4h-1.2"/>' +
      '<rect class="ic-restore" x="3" y="5.6" width="7.4" height="7.4" rx="1.8"/>',
      function () { shell.max(); }));

    wrap.appendChild(boton('close', 'Cerrar',
      '<path d="M3.3 3.3l9.4 9.4M12.7 3.3l-9.4 9.4"/>',
      function () { shell.close(); }));

    return wrap;
  }

  function boton(clase, titulo, svgInner, onClick) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'jw-winbtn jw-winbtn-' + clase;
    b.title = titulo;
    b.setAttribute('aria-label', titulo);
    b.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" ' +
      'stroke="currentColor" stroke-width="1.4" stroke-linecap="round" ' +
      'stroke-linejoin="round" aria-hidden="true">' + svgInner + '</svg>';
    // Soltar el foco tras el click: si queda enfocado, al apretar F11 Chrome le
    // pinta el anillo de foco encima (esos botones son chrome, nunca lo muestran).
    b.addEventListener('click', function (e) { onClick(e); b.blur(); });
    return b;
  }

  // 8 zonas invisibles de resize (bordes + esquinas): la ventana no tiene marco.
  function montarResize() {
    var dirs = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'];
    var host = document.createElement('div');
    host.id = 'jw-resize-host';
    dirs.forEach(function (d) {
      var z = document.createElement('div');
      z.className = 'jw-resize jw-resize-' + d;
      z.addEventListener('mousedown', function (e) {
        if (e.button !== 0) return;
        e.preventDefault();
        shell.resize(d);
      });
      host.appendChild(z);
    });
    document.body.appendChild(host);
  }

  function inyectarCSS() {
    var css = [
      /* Cluster de controles de ventana.
         La fila derecha de la barra se estira a propósito: es un flex item de
         #jw-bar, que centra, así que sin `align-self: stretch` su alto es el
         del CONTENIDO. El `height: 100%` de antes resolvía contra esa altura
         chica y por eso el hover pintaba un rectangulito en vez del botón
         entero. Ahora el cluster mide lo que mide la barra y los botones se
         estiran a ese alto. */
      '.app-chrome .jw-bar-right, .app-chrome .hc-actions { align-self: stretch; }',
      /* el margin-right (negativo, lo pone el JS según la barra) se come el
         padding lateral: la ✕ llega al borde real de la ventana, como en
         cualquier titlebar de Windows — la esquina es el destino más fácil de
         acertar con el mouse */
      '#jw-winctl { display: inline-flex; align-items: stretch;',
      '  align-self: stretch; margin-left: 6px; }',
      /* 46px de ancho × alto completo de la barra: la medida de los botones de
         título de Windows. El área sensible es TODA la celda, no el ícono. */
      '.jw-winbtn { width: 46px; align-self: stretch; border: 0;',
      '  background: transparent;',
      '  color: var(--ob-fg-3, #a9a3c4); display: grid; place-items: center;',
      '  cursor: default; padding: 0;',
      '  transition: background .14s ease, color .14s ease; }',
      /* chrome de ventana: nunca el anillo de foco del navegador */
      '.jw-winbtn:focus, .jw-winbtn:focus-visible { outline: none; box-shadow: none; }',
      '.jw-winbtn:hover { background: oklch(100% 0 0 / .07); color: var(--ob-fg-0, #eae7f6); }',
      '.jw-winbtn:active { background: oklch(100% 0 0 / .12); }',
      '.jw-winbtn-close:hover { background: #e04848; color: #fff; }',
      '.jw-winbtn-close:active { background: #c53838; }',
      /* alternar ícono maximizar/restaurar según el estado */
      '.jw-winbtn-max .ic-restore { display: none; }',
      '.app-maximized .jw-winbtn-max .ic-max { display: none; }',
      '.app-maximized .jw-winbtn-max .ic-restore { display: inline; }',
      /* Pantalla completa: los controles de ventana NO se muestran — es la
         convención (y lo pidió el usuario). Se sale con F11, igual que se
         entró. */
      '.app-fullscreen #jw-winctl { display: none; }',
      /* la barra es zona de arrastre: sin selección de texto al mover */
      '.app-chrome #jw-bar, .app-chrome .hc-top {',
      '  user-select: none; -webkit-user-select: none; }',

      /* Zonas de resize (invisibles) — sobre los bordes de la ventana */
      '#jw-resize-host { position: fixed; inset: 0; z-index: 2147483000; pointer-events: none; }',
      '.jw-resize { position: absolute; pointer-events: auto; }',
      '.jw-resize-n { top: 0; left: 6px; right: 6px; height: 5px; cursor: ns-resize; }',
      '.jw-resize-s { bottom: 0; left: 6px; right: 6px; height: 5px; cursor: ns-resize; }',
      '.jw-resize-e { top: 6px; bottom: 6px; right: 0; width: 5px; cursor: ew-resize; }',
      '.jw-resize-w { top: 6px; bottom: 6px; left: 0; width: 5px; cursor: ew-resize; }',
      '.jw-resize-ne { top: 0; right: 0; width: 9px; height: 9px; cursor: nesw-resize; }',
      '.jw-resize-nw { top: 0; left: 0; width: 9px; height: 9px; cursor: nwse-resize; }',
      '.jw-resize-se { bottom: 0; right: 0; width: 9px; height: 9px; cursor: nwse-resize; }',
      '.jw-resize-sw { bottom: 0; left: 0; width: 9px; height: 9px; cursor: nesw-resize; }',
      /* maximizada o pantalla completa: no hay resize */
      '.app-maximized #jw-resize-host, .app-fullscreen #jw-resize-host { display: none; }'
    ].join('\n');
    var s = document.createElement('style');
    s.id = 'jw-winchrome-css';
    s.textContent = css;
    document.head.appendChild(s);
  }
})();
