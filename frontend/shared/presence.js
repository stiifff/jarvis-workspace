// JARVIS — Reporter de sección para la Rich Presence de Discord ("Jugando Jarvis").
//
// El lanzador Jarvis.exe (scripts/jarvis-shell.cs, C#/WebView2 en Windows) es
// quien habla con el IPC de Discord poleteando GET /api/system/presence. Pero LA
// SECCIÓN en la que estás es estado del frontend (qué overlay/pestaña tenés a la
// vista), no del backend. Este módulo lo calcula y lo reporta con POST
// /api/system/presence/state: al cambiar algo, o como heartbeat mientras la
// página está VISIBLE — la vista que el usuario mira es la autoridad (las
// ocultas callan, así un cliente en otro idioma no pisa al que está en uso).
//
// La lógica con reglas — snapshot → sección (seccionDesde) y cuándo postear
// (debePostear) — se testea en Node (presence.test.js). El resto es plumbing.
(function (global) {
  'use strict';

  // Claves = las que entiende el backend (_PRESENCE_SECCIONES en system.py) y
  // las pestañas del dock (panel.js: preview·jarvis·editor·tasks·review·mobile).
  function seccionDesde(s) {
    s = s || {};
    if (!s.hayProyecto) return 'home';
    // Overlays full-screen: están POR ENCIMA del dock → ganan.
    if (s.settingsOpen) return 'settings';
    // Dock abierto con una pestaña activa → esa es la sección.
    if (s.dockOpen && s.dockTab) return s.dockTab;
    // Nada encima → el mosaico de terminales (la vista base del workspace).
    return 'terminals';
  }

  // El estado en el backend es global last-writer-wins: si hay DOS clientes con
  // el workspace abierto (browser + Jarvis app, cada uno con su localStorage
  // y por lo tanto su idioma), la tarjeta tiene que reflejar el que el usuario
  // está MIRANDO. Regla: página oculta = muda (no pisa al que se ve); visible =
  // postea si cambió la firma o si venció el heartbeat — la re-aserción
  // periódica le gana al estado viejo de otro cliente (o al default del server
  // recién booteado).
  function debePostear(s) {
    s = s || {};
    if (s.visible === false) return false;
    if (s.firma !== s.ultimaFirma) return true;
    if (s.ultimoPost == null) return true;
    return (s.ahora - s.ultimoPost) >= (s.heartbeatMs || 12000);
  }

  const pure = { seccionDesde, debePostear };
  global.JarvisPresence = Object.assign(global.JarvisPresence || {}, { _pure: pure, ...pure });

  // ── Runtime del navegador (no corre en Node) ───────────────────────────────
  if (typeof document !== 'undefined' && typeof window !== 'undefined') {
    function _snapshot() {
      let hayProyecto = false;
      try { hayProyecto = !!new URLSearchParams(location.search).get('id'); } catch (e) {}
      const D = window.JarvisDock, S = window.JarvisSettings;
      return {
        hayProyecto,
        settingsOpen:   !!(S && S.isOpen && S.isOpen()),
        dockOpen:       !!(D && D.isOpen && D.isOpen()),
        dockTab:        (D && D.activeTab && D.activeTab()) || null,
      };
    }

    function _localeActual() {
      try {
        return (window.JarvisI18n && window.JarvisI18n.lang && window.JarvisI18n.lang() === 'en')
          ? 'en' : 'es';
      } catch (e) { return 'es'; }
    }

    function _projectId() {
      try {
        const raw = new URLSearchParams(location.search).get('id');
        return (raw && /^\d+$/.test(raw)) ? parseInt(raw, 10) : null;
      } catch (e) { return null; }
    }

    function _proyectoNombre() {
      try {
        const el = document.getElementById('project-title');
        const txt = el && el.textContent ? el.textContent.trim() : '';
        // 'cargando' es el placeholder del breadcrumb antes de resolver el proyecto.
        return (txt && txt !== 'cargando') ? txt.slice(0, 64) : null;
      } catch (e) { return null; }
    }

    let _ultimo = null, _ultimoPost = null;
    function reportar(forzar) {
      const cuerpo = {
        seccion: seccionDesde(_snapshot()),
        locale: _localeActual(),
        project_id: _projectId(),
        proyecto: _proyectoNombre(),
      };
      const firma = JSON.stringify(cuerpo);
      const ok = debePostear({
        visible: document.visibilityState !== 'hidden',
        firma,
        ultimaFirma: forzar === true ? null : _ultimo,
        ahora: Date.now(),
        ultimoPost: _ultimoPost,
      });
      if (!ok) return;
      _ultimo = firma;
      _ultimoPost = Date.now();
      try {
        fetch('/api/system/presence/state', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: firma,
          keepalive: true,
        }).catch(function () {});
      } catch (e) {}
    }

    let _timer = null;
    function init() {
      if (_timer) return;
      reportar();                          // primer reporte inmediato
      _timer = setInterval(reportar, 4000); // postea si cambió o venció el heartbeat
      // Cambio de idioma en caliente → re-reportar ya (el shell muestra el nuevo
      // texto). forzar=true: el CustomEvent no debe caer en el `forzar === true`.
      window.addEventListener('jarvis:lang', function () { reportar(true); });
      // Al volver a estar visible, esta vista reclama la tarjeta YA (sin esperar
      // el heartbeat): es la que el usuario tiene delante.
      document.addEventListener('visibilitychange', function () {
        if (document.visibilityState !== 'hidden') reportar(true);
      });
      // Cambio de proyecto (nav sin recarga) → el pushState no dispara evento
      // propio; el poll de 4s lo agarra igual. init() es idempotente.
    }

    Object.assign(global.JarvisPresence, { init, reportar });
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = pure;
})(typeof window !== 'undefined' ? window : globalThis);
