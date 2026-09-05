'use strict';
// ─── Web Preview ──────────────────────────────────────────────────────────────
// Browser embebido del Panel Único, ahora con PESTAÑAS: fila .wp-tabs + barra
// (‹ › url ⟳ ↗). Cada pestaña tiene su PROPIO iframe (oculto con [hidden] si no
// está activa: cambiar de pestaña NO recarga — scroll/SPA/video quedan vivos) y
// su historial. La lógica de pestañas es pura (preview-tabs.js, WebPreviewTabs);
// acá vive solo el render + efectos (detección de bloqueo XFO/CSP por pestaña).
// Persistencia por proyecto: localStorage jarvis.preview.tabs.<pid>.
// AUDIO PERSISTENTE: al cambiar de proyecto los iframes NO se destruyen — el
// pool {estado, vistas} se estaciona oculto (la música sigue) y se re-adopta
// al volver. Tras un reinicio/recarga, la música que sonaba se REANUDA sola
// desde el segundo guardado (tracking por postMessage de YouTube + urlMedia).
// Expone window.WebPreview = { init, setUrl, getUrl, openTab, detectar, refresh,
// openExternal, onProjectChanged, _pure }.
// Regla xterm: los iframes NUNCA animan width — se muestran/ocultan con [hidden].

(function (root) {

  // ── Lógica pura (testeable bajo Node, sin DOM) ──────────────────
  // 'localhost:3000' → 'http://localhost:3000'
  // '3000'           → 'http://localhost:3000'
  // 'http(s)://...'  → igual
  // 'host:puerto'    → 'http://host:puerto'
  // vacío / null     → null
  function _normalizarBase(input) {
    if (input == null) return null;
    const s = String(input).trim();
    if (!s) return null;
    // Ruta relativa/absoluta del FS o del sitio: 'http:///x' es malformada.
    if (s.startsWith('/')) return null;
    // ¿Trae esquema explícito? Un esquema es 'nombre://…' o 'nombre:resto'
    // donde 'resto' NO arranca con puerto. Si 'resto' empieza con dígitos
    // seguidos de '/' o fin de string ('3000', '3000/ruta?q=1'), eso es
    // 'host:puerto[/path]', NO un esquema (regresión: 'localhost:3000/x').
    const m = /^([a-z][a-z0-9+.-]*):(\/\/)?(.*)$/i.exec(s);
    if (m && (m[2] || !/^\d+(\/|$)/.test(m[3]))) {
      // Tiene esquema real: solo http/https con '//' son web embebible;
      // el resto (javascript:, data:, vbscript:, ftp:, file:, …) → null.
      const esquema = m[1].toLowerCase();
      if ((esquema === 'http' || esquema === 'https') && m[2]) return s;
      return null;
    }
    // Sin esquema. Puerto pelado ('3000') → localhost.
    if (/^\d+$/.test(s)) return `http://localhost:${s}`;
    // host, host:puerto, IP:puerto → asumimos http.
    return `http://${s}`;
  }

  // Twitch: el embed EXIGE parent = dominio embebedor. Jarvis corre en
  // localhost:3000 → parent=localhost (un parent mal deja el player deshabilitado).
  const TW_PARENT = 'parent=localhost';
  // Rutas de twitch.tv que NO son un canal (no reescribir a player).
  const TW_NO_CANAL = new Set(['videos', 'directory', 'settings', 'p', 'downloads',
    'jobs', 'turbo', 'subscriptions', 'wallet', 'inventory', 'drops', 'friends',
    'store', 'clips', 'search', 'following', 'popout']);

  function _embedTwitch(host, pathname) {
    if (host === 'clips.twitch.tv') {
      const c = /^\/([A-Za-z0-9_-]+)/.exec(pathname);
      return c ? `https://clips.twitch.tv/embed?clip=${c[1]}&${TW_PARENT}` : null;
    }
    const vod = /^\/videos\/(\d+)/.exec(pathname);
    if (vod) return `https://player.twitch.tv/?video=${vod[1]}&${TW_PARENT}`;
    const clip = /^\/[^/]+\/clip\/([A-Za-z0-9_-]+)/.exec(pathname);
    if (clip) return `https://clips.twitch.tv/embed?clip=${clip[1]}&${TW_PARENT}`;
    const canal = /^\/([A-Za-z0-9_]+)\/?$/.exec(pathname);
    if (canal && !TW_NO_CANAL.has(canal[1].toLowerCase())) {
      return `https://player.twitch.tv/?channel=${canal[1]}&${TW_PARENT}`;
    }
    return null;
  }

  // Reescribe URLs de plataformas a su REPRODUCTOR EMBEBIBLE (que la
  // plataforma sí deja meter en un iframe, a diferencia de la página normal
  // que manda XFO/CSP y no entra en un iframe):
  //   youtube.com/watch?v=X · youtu.be/X → youtube.com/embed/X
  //   twitch.tv/{canal|videos/id|.../clip/id} · clips.twitch.tv/{slug} → player/clip
  // Cualquier otra URL pasa intacta.
  function reescribirEmbed(url) {
    try {
      const u = new URL(url);
      const host = u.hostname.toLowerCase().replace(/^(www\.|m\.)/, '');
      if (host === 'youtube.com' && u.pathname === '/watch' && u.searchParams.get('v')) {
        return `https://www.youtube.com/embed/${u.searchParams.get('v')}`;
      }
      if (host === 'youtu.be' && u.pathname.length > 1) {
        return `https://www.youtube.com/embed/${u.pathname.slice(1).split('/')[0]}`;
      }
      if (host === 'twitch.tv' || host === 'clips.twitch.tv') {
        return _embedTwitch(host, u.pathname) || url;
      }
    } catch { /* URL rara: dejarla como estaba */ }
    return url;
  }

  // Los alias de loopback (127.0.0.1 / 0.0.0.0 / [::1]) apuntan al MISMO server
  // que localhost → los reescribimos a 'localhost' (igual que linkAlPreview y el
  // dev_detect del backend) para que una sola pestaña represente al server. Sin
  // esto, el mismo dev server aparecía DOS veces (una por alias) y el demo
  // servido por 127.0.0.1:3000 quedaba en otro origen que el workspace. Regex
  // sobre la AUTORIDAD (tras '//', hasta ':'/'/'/fin): no toca IPs en el path.
  function _canonLoopback(url) {
    return url
      .replace(/^(\w+:\/\/)127\.0\.0\.1(?=[:/]|$)/i, '$1localhost')
      .replace(/^(\w+:\/\/)0\.0\.0\.0(?=[:/]|$)/i, '$1localhost')
      .replace(/^(\w+:\/\/)\[::1\](?=[:/]|$)/i, '$1localhost');
  }

  // API pública: normaliza, canonicaliza loopback y aplica reescrituras de embebibilidad.
  function normalizarUrl(input) {
    const norm = _normalizarBase(input);
    return norm == null ? null : reescribirEmbed(_canonLoopback(norm));
  }

  // NOTA (2026-07-12, "menú-primero"): se eliminó la maquinaria de auto-abrir
  // (debeAutoAbrir/olvidarAutoAbierta) — un dev server/demo detectado YA NO abre
  // una pestaña sola. Viven en el menú #jw-localhosts-btn y los abre el usuario
  // (click en el menú, o maximizar/seleccionar la card del agente). Ver el
  // handler de dev_server_detectado en shell/workspace.js y refrescarSiExiste().

  // ¿El texto SIN espacios "parece" URL/host, y no una palabra suelta?
  // Esquema explícito, puerto pelado ('3000'), localhost, o un host con
  // punto / :puerto. 'gatos' NO parece URL (va a búsqueda, como un browser).
  function _pareceUrl(s) {
    if (/^https?:\/\//i.test(s)) return true;
    if (/^\d+$/.test(s)) return true;
    const host = s.split(/[/?#]/)[0];
    if (/^localhost(:\d+)?$/i.test(host)) return true;
    return host.includes('.') || /:\d+$/.test(host);
  }

  // Interpreta lo tipeado en la barra del preview:
  //   'yt lofi' / 'youtube lofi' → {tipo:'youtube', q:'lofi'}   (búsqueda YT)
  //   URL/host/puerto            → {tipo:'url', url:normalizada}
  //   cualquier otro texto       → {tipo:'busqueda', q:texto}   (búsqueda web)
  //   vacío                      → {tipo:'invalida'}
  // Los esquemas no navegables (javascript:, rutas) caen a búsqueda: jamás
  // se navegan, y buscarlos es lo que hace cualquier browser.
  function interpretarEntrada(input) {
    const s = String(input == null ? '' : input).trim();
    if (!s) return { tipo: 'invalida' };
    const yt = /^(?:yt|youtube)(?:\s+(.+))?$/i.exec(s);
    if (yt) return { tipo: 'youtube', q: (yt[1] || '').trim() };
    if (!/\s/.test(s)) {
      const norm = _normalizarBase(s);
      if (norm && _pareceUrl(s)) return { tipo: 'url', url: reescribirEmbed(norm) };
    }
    return { tipo: 'busqueda', q: s };
  }

  // Destino de una búsqueda de la barra: el SITIO REAL, no una página de
  // resultados propia. (Hasta 2026-07-26 esto abría serp.html, un SERP casero
  // que scrapeaba DuckDuckGo/YouTube server-side; se eliminó — con el Browse
  // nativo se entra a cualquier parte sin restricciones, así que buscar es
  // simplemente navegar al buscador de verdad.)
  //   tipo 'youtube' → youtube.com (con q: su página de resultados)
  //   cualquier otro → google.com  (con q: su página de resultados)
  // Sin q = la home del sitio: es lo que hacen los accesos directos del
  // estado vacío.
  function urlBusqueda(tipo, q) {
    const texto = String(q == null ? '' : q).trim();
    if (tipo === 'youtube') {
      return texto
        ? 'https://www.youtube.com/results?search_query=' + encodeURIComponent(texto)
        : 'https://www.youtube.com';
    }
    return texto
      ? 'https://www.google.com/search?q=' + encodeURIComponent(texto)
      : 'https://www.google.com';
  }

  // Política de referrer POR CARGA del iframe. Default 'no-referrer' (que
  // ninguna URL de Jarvis viaje afuera), PERO los embeds de YouTube exigen
  // saber qué origin los embebe: sin header Referer el player muere con
  // "Error 153 — Video player configuration error" (verificado 2026-07-02).
  // 'origin' manda SOLO http://localhost:3000/ — cero fuga de rutas/token.
  function politicaReferrer(url) {
    try {
      const u = new URL(url);
      const host = u.hostname.toLowerCase().replace(/^(www\.|m\.)/, '');
      if ((host === 'youtube.com' || host === 'youtube-nocookie.com')
          && u.pathname.startsWith('/embed/')) return 'origin';
      // Twitch valida por parent=, pero manda 'origin' igual no molesta.
      if (host === 'player.twitch.tv' || host === 'clips.twitch.tv') return 'origin';
    } catch { /* URL rara → default */ }
    return 'no-referrer';
  }

  // ¿Es un reproductor EMBEBIDO (YouTube/Twitch)? → se le saca
  // allow-popups al sandbox: sus links "abrir en la app / ver en el sitio"
  // usan window.open y, con popups, SALTAN a una pestaña externa (fuera de
  // Jarvis). Sin popups, el click no hace nada y el media se queda EN el
  // workspace. Espejo de reescribirEmbed (los hosts a los que reescribe).
  function esEmbed(url) {
    try {
      const u = new URL(url);
      const host = u.hostname.toLowerCase().replace(/^(www\.|m\.)/, '');
      if ((host === 'youtube.com' || host === 'youtube-nocookie.com')
          && u.pathname.startsWith('/embed/')) return true;
      if (host === 'player.twitch.tv' || host === 'clips.twitch.tv') return true;
    } catch { /* no-URL */ }
    return false;
  }

  // Parsea un embed de YouTube; null para cualquier otra URL. (SOLO YouTube:
  // lo usan urlMedia/politica-específicos que dependen de la API JS de YT.)
  function _embedYt(url) {
    try {
      const u = new URL(url);
      const host = u.hostname.toLowerCase().replace(/^(www\.|m\.)/, '');
      if ((host === 'youtube.com' || host === 'youtube-nocookie.com')
          && u.pathname.startsWith('/embed/')) return u;
    } catch { /* no-URL */ }
    return null;
  }

  // Prepara la URL que va al IFRAME (pestaña y barra muestran la limpia).
  // Embeds de YouTube: enablejsapi+origin SIEMPRE (habilita el tracking de
  // tiempo/estado por postMessage — la reanudación tras un reinicio depende
  // de esto) y, si viene `media` (restauración), start=segundo guardado +
  // autoplay si estaba sonando. Cualquier otra URL pasa intacta.
  function urlMedia(url, origin, media) {
    const u = _embedYt(url);
    if (!u) return url;
    u.searchParams.set('enablejsapi', '1');
    u.searchParams.set('origin', origin);
    u.searchParams.set('rel', '0');          // menos "videos relacionados" al final
    if (media && media.t > 3) u.searchParams.set('start', String(Math.floor(media.t)));
    if (media && media.play) u.searchParams.set('autoplay', '1');
    return u.toString();
  }

  // ¿Un link clickeado en la TERMINAL de un agente debe abrirse EN el Web
  // Preview (es un dev server local / demo estático de Jarvis) o en el
  // browser externo? Devuelve la URL lista para el preview — con los alias
  // 127.0.0.1 / 0.0.0.0 / [::1] reescritos a localhost, igual que dev_detect,
  // para que la pestaña se de-dupee con la del server autodetectado — o null
  // (→ que el llamador la mande afuera). El propio Jarvis (mismo puerto que
  // jarvisOrigin) solo entra si es un demo /static/… : embeber el workspace
  // entero dentro de sí mismo no tiene sentido.
  function linkAlPreview(uri, jarvisOrigin) {
    let u;
    try { u = new URL(String(uri)); } catch { return null; }
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
    const host = u.hostname.toLowerCase();
    if (!['localhost', '127.0.0.1', '0.0.0.0', '::1', '[::1]'].includes(host)) return null;
    u.hostname = 'localhost';
    const puerto = u.port || (u.protocol === 'https:' ? '443' : '80');
    try {
      const j = new URL(jarvisOrigin);
      const puertoJarvis = j.port || (j.protocol === 'https:' ? '443' : '80');
      if (puerto === puertoJarvis && !u.pathname.startsWith('/static/')) return null;
    } catch { /* origin raro: tratarlo como dev server normal */ }
    return u.toString();
  }

  // De DÓNDE sale el favicon de una pestaña (o null → ícono default/globo). Los
  // localhost NO resuelven en el servicio público de favicons (DuckDuckGo), que
  // para ellos devuelve un ícono genérico gris — por eso los localhost nunca
  // mostraban su ícono real. Ahora:
  //  1. `declarado`: el <link rel=icon> que leímos del documento al cargar (solo
  //     mismo-origen; los demos de Jarvis traen su ícono inline) — gana siempre.
  //  2. dev server LOCAL en OTRO puerto que el workspace → su propio /favicon.ico.
  //  3. demo del PROPIO Jarvis (mismo host:puerto que el workspace) sin declarado
  //     todavía → null (globo): su /favicon.ico sería el de Jarvis, no el del demo.
  //  4. sitio público → servicio de favicons (resuelve dominios reales).
  //  5. sin URL/host (pestaña vacía) → null.
  function faviconSrc(url, declarado, jarvisHost) {
    if (declarado) return declarado;
    let u;
    try { u = new URL(url); } catch { return null; }
    const host = u.hostname.toLowerCase();
    const esLocal = ['localhost', '127.0.0.1', '0.0.0.0', '::1', '[::1]'].includes(host);
    if (esLocal) {
      if (u.host === jarvisHost) return null;   // demo de Jarvis → esperar el declarado
      return u.origin + '/favicon.ico';         // dev server real → su favicon
    }
    return `https://icons.duckduckgo.com/ip3/${u.host}.ico`;
  }

  const _pure = { normalizarUrl, interpretarEntrada, urlBusqueda, politicaReferrer, urlMedia, esEmbed, linkAlPreview, faviconSrc };

  // ── Estado del módulo (solo en navegador) ───────────────────────
  // Accessor perezoso: preview-tabs.js carga antes en el HTML, pero en Node
  // (tests de _pure) no existe — por eso NUNCA se toca a nivel módulo.
  const T = () => root.WebPreviewTabs._pure;
  // Split / layouts (puro). DEFENSIVO: si preview-layout.js no está cargado
  // (p.ej. workspace.html todavía sin su <script>), cae a single-pane — el
  // preview funciona igual que siempre, nunca crashea.
  const _LY_SINGLE = {
    LAYOUTS: [], DEFAULT_LAYOUT: '1',
    normalizar: () => '1', panesDe: () => 1, template: () => '"a" 1fr / 1fr',
    asignar: (ids) => [Array.isArray(ids) && ids.length ? ids[0] : null],
  };
  const LY = () => (root.WebPreviewLayout && root.WebPreviewLayout._pure) || _LY_SINGLE;

  let _cont      = null;   // contenedor raíz (#jw-pane-preview)
  let _layout    = '1';    // disposición del split (id de WebPreviewLayout; '1' = single)
  let _montado   = false;
  let _estado    = null;   // estado puro de pestañas (WebPreviewTabs)
  let _vistas    = {};     // tabId → { iframe, gen, onLoad, loadTimer, esperando, vista, cargando, favicon }
  let _input     = null;
  let _btnBack   = null;
  let _btnFwd    = null;
  let _tabsEl    = null;   // fila .wp-tabs
  let _bodyEl    = null;   // .wp-body (acá viven los iframes por pestaña)
  let _detectada = null;   // último localhost autodetectado (solo informativo)
  let _pid       = null;   // proyecto actual (clave de persistencia)
  let _pools     = {};     // pid → { estado, vistas } estacionados (iframes VIVOS: el audio sigue)

  // ── SVG inline (el sprite ui.js no tiene chevron) ───────────────
  const SVG_BACK = '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 3.5L5.5 8l4.5 4.5"/></svg>';
  const SVG_FWD  = '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3.5L10.5 8 6 12.5"/></svg>';
  const SVG_RELOAD = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9M13.5 2v3h-3"/></svg>';
  const SVG_EXTERNAL = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 3h4v4M13 3l-6 6M11 9.5V13H3V5h3.5"/></svg>';
  const SVG_MOON = '<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13.5 9.2A5.5 5.5 0 1 1 6.8 2.5a4.3 4.3 0 0 0 6.7 6.7z"/></svg>';
  const SVG_GRID = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/></svg>';
  const SVG_MAX2 = '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 2h4v4M6 14H2v-4M14 2l-5 5M2 14l5-5"/></svg>';
  const SVG_PAUSE = '<svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="4" y="3" width="3" height="10" rx="1"/><rect x="9" y="3" width="3" height="10" rx="1"/></svg>';
  const SVG_CERRAR = '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg>';
  const SVG_PREV = '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="3" y="3" width="2" height="10" rx="1"/><path d="M13 3.5v9a.6.6 0 0 1-.9.5l-6-4.5a.6.6 0 0 1 0-1l6-4.5a.6.6 0 0 1 .9.5z"/></svg>';
  const SVG_NEXT = '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><rect x="11" y="3" width="2" height="10" rx="1"/><path d="M3 3.5v9a.6.6 0 0 0 .9.5l6-4.5a.6.6 0 0 0 0-1l-6-4.5a.6.6 0 0 0-.9.5z"/></svg>';
  const SVG_GLOBO = '<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 2.5 15.3 0 18M12 3c-2.5 2.7-2.5 15.3 0 18"/></svg>';
  const SVG_PLAY = '<svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M4.5 3.1a.8.8 0 0 1 1.2-.7l7 4.4a.8.8 0 0 1 0 1.4l-7 4.4a.8.8 0 0 1-1.2-.7z"/></svg>';
  const SVG_LUPA = '<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>';
  // Kebab "⋯": overflow de la barra cuando el dock está angosto (dock lateral).
  const SVG_MORE = '<svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><circle cx="3" cy="8" r="1.4"/><circle cx="8" cy="8" r="1.4"/><circle cx="13" cy="8" r="1.4"/></svg>';
  // Globo compacto para el favicon de una pestaña sin sitio (nueva/en blanco):
  // así TODA pestaña tiene un ícono visible, incluso comprimida a chip.
  const SVG_TAB_GLOBO = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" aria-hidden="true"><circle cx="8" cy="8" r="6"/><path d="M2 8h12M8 2c1.7 1.8 1.7 10.2 0 12M8 2c-1.7 1.8-1.7 10.2 0 12"/></svg>';

  const $ = (sel) => _cont ? _cont.querySelector(sel) : null;
  const _lsKey = (pid) => `jarvis.preview.tabs.${pid}`;

  function init(containerEl) {
    // Idempotente de verdad: si ya está montado NO reasignar _cont (el DOM
    // y los listeners viven en el contenedor original).
    if (_montado) return;
    _cont = containerEl || document.getElementById('jw-pane-preview');
    if (!_cont) { console.warn('[preview] sin contenedor'); return; }
    _montado = true;
    _estado = T().crearEstado();
    _montar();
    // Browse nativo : la URL real del webview hijo vuelve por acá.
    if (_nativoOk()) root.NativeBrowse.onEstado(_onEstadoNativo);
    // Si el proyecto ya se conoce (onProjectChanged corrió antes del primer
    // open del dock), restaurar sus pestañas persistidas.
    if (_pid != null) _restaurar(_pid);
  }

  function _montar() {
    // i18n de las etiquetas nuevas del chrome (tray ⋯ del dock angosto). Se
    // registran en runtime para no tocar shared/i18n-dict.js (lo bumpea otro
    // agente); el observer de i18n traduce el DOM al montarlo si el idioma es EN.
    if (window.JarvisI18n && window.JarvisI18n.agregar) {
      window.JarvisI18n.agregar({
        'Abrir en el navegador': 'Open in browser',
        'Fondo oscuro': 'Dark background',
        'Dividir en paneles': 'Split into panels',
        'Disposición de paneles': 'Panel layout',
        'Disposición de paneles (split)': 'Panel layout (split)',
        'Servidor local en vivo': 'Live local server',
      });
    }
    _cont.innerHTML = `
      <div class="wp-tabs" id="wp-tabs" role="tablist" aria-label="Pestañas del preview"></div>
      <div class="wp-bar">
        <button class="wp-nav" id="wp-back" title="Atrás" aria-label="Atrás" disabled>${SVG_BACK}</button>
        <button class="wp-nav" id="wp-fwd"  title="Adelante" aria-label="Adelante" disabled>${SVG_FWD}</button>
        <div class="wp-omni">
          <span class="wp-omni-lupa">${SVG_LUPA}</span>
          <!-- Chip LOCAL: visible cuando la pestaña activa es un servidor local
               (dev server del agente / demo de Jarvis) — punto vivo + etiqueta. -->
          <span class="wp-omni-local" id="wp-omni-local" hidden title="Servidor local en vivo"><i></i><b>LOCAL</b></span>
          <input class="wp-url" id="wp-url" type="text" spellcheck="false" autocomplete="off"
                 placeholder="Buscá en la web o pegá una URL…" aria-label="Búsqueda o URL del preview">
        </div>
        <button class="wp-nav" id="wp-reload" title="Recargar" aria-label="Recargar">${SVG_RELOAD}</button>
        <!-- Localhost activos: el menú vive ACÁ (salió de la barra del workspace,
             pedido del usuario). Lo puebla window.JarvisDevServers por su id; se
             oculta cuando no hay ningún localhost vivo. -->
        <button class="wp-nav wp-localhosts" id="jw-localhosts-btn" type="button" hidden
                title="Localhost activos" aria-label="Localhost activos" aria-haspopup="menu" aria-expanded="false"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01"/></svg><span class="jw-ds-count">0</span></button>
        <!-- Acciones secundarias: inline cuando hay ancho (display:contents), y
             colapsadas en el popover del kebab ⋯ cuando el dock está angosto. -->
        <div class="wp-more-tray" id="wp-more-tray" hidden role="menu" aria-label="Más opciones">
          <button class="wp-nav" id="wp-ext" role="menuitem" title="Abrir en pestaña del navegador" aria-label="Abrir en pestaña">${SVG_EXTERNAL}<span class="wp-nav-lbl">Abrir en el navegador</span></button>
          <button class="wp-nav" id="wp-dark" role="menuitem" title="Forzar fondo oscuro (modo iframe)" aria-label="Forzar fondo oscuro">${SVG_MOON}<span class="wp-nav-lbl">Fondo oscuro</span></button>
          <button class="wp-nav" id="wp-layout" role="menuitem" title="Disposición de paneles (split)" aria-label="Disposición de paneles">${SVG_GRID}<span class="wp-nav-lbl">Dividir en paneles</span></button>
        </div>
        <button class="wp-nav wp-more-btn" id="wp-more" title="Más opciones" aria-label="Más opciones" aria-haspopup="menu" aria-expanded="false">${SVG_MORE}</button>
        <div class="wp-lg" id="wp-lg" hidden role="menu" aria-label="Disposiciones"></div>
      </div>
      <div class="wp-body" id="wp-body">
        <div class="wp-empty" id="wp-empty">
          <div class="wp-empty-icon">${SVG_GLOBO}</div>
          <h2>Buscá en la web o abrí una URL</h2>
          <p>Escribí arriba una búsqueda o una URL. Con <code>yt&nbsp;…</code> buscás
             directo en YouTube; los <code>localhost</code> vivos que detecte
             Jarvis te esperan en el menú de la barra.</p>
          <div class="wp-empty-chips">
            <button class="wp-chip" type="button" data-chip="youtube">${SVG_PLAY} YouTube</button>
            <button class="wp-chip" type="button" data-chip="busqueda">${SVG_LUPA} Buscar en la web</button>
          </div>
        </div>
      </div>`;
    _montarGaleriaLayouts();

    _tabsEl  = $('#wp-tabs');
    _bodyEl  = $('#wp-body');
    _input   = $('#wp-url');
    _btnBack = $('#wp-back');
    _btnFwd  = $('#wp-fwd');

    _input.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      const r = interpretarEntrada(_input.value);
      if (r.tipo === 'invalida') {
        // Feedback visual con clase .error que anima un shake
        _input.classList.add('error');
        _input.addEventListener('animationend', function onEnd() {
          _input.removeEventListener('animationend', onEnd);
          _input.classList.remove('error');
        });
        // Fallback por si la animación no dispara (reduced-motion u otro motivo)
        setTimeout(() => _input.classList.remove('error'), 300);
        return;
      }
      // URL directa, o el buscador real (Google / YouTube) con la búsqueda.
      setUrl(r.tipo === 'url' ? r.url : urlBusqueda(r.tipo, r.q), true);
    });
    _btnBack.addEventListener('click', _atras);
    _btnFwd.addEventListener('click', _adelante);
    $('#wp-reload').addEventListener('click', refresh);
    $('#wp-ext').addEventListener('click', () => { _cerrarMore(); openExternal(); });
    $('#wp-layout').addEventListener('click', _toggleGaleria);
    $('#wp-more').addEventListener('click', _toggleMore);
    // Delegación de clicks dentro del body: heads de celda + CTAs del fallback
    // por-panel (activar/cerrar/maximizar/abrir-externo de ESA pestaña).
    _bodyEl.addEventListener('click', _onBodyClick);
    document.addEventListener('click', _cerrarGaleriaAfuera, true);
    document.addEventListener('click', _cerrarMoreAfuera, true);
    // Escape cierra los popovers del chrome (tray ⋯ / galería) antes de que el
    // Esc global del workspace des-maximice; solo frena el evento si cerró algo.
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      const tray = $('#wp-more-tray'), lg = $('#wp-lg');
      let cerro = false;
      if (tray && !tray.hasAttribute('hidden')) { _cerrarMore(); cerro = true; }
      if (lg && !lg.hasAttribute('hidden')) { _cerrarGaleria(); cerro = true; }
      if (cerro) { e.stopPropagation(); e.preventDefault(); }
    }, true);
    $('#wp-dark').addEventListener('click', () => { _cerrarMore(); _toggleDark(); });
    // Accesos directos del estado vacío: cada uno lleva a SU sitio (YouTube /
    // Google), no a una página de resultados nuestra.
    $('#wp-empty').addEventListener('click', (e) => {
      const chip = e.target.closest('[data-chip]');
      if (chip) setUrl(urlBusqueda(chip.dataset.chip, ''), true);
    });
    window.addEventListener('message', _onMensajeYoutube);

    _render();

    // Menú de "Localhost activos": su botón vive ahora en ESTA toolbar (salió de
    // la barra del workspace). Al montarse el preview lo enganchamos por id y
    // traemos el estado vivo del proyecto (el módulo guarda pid/servers aunque el
    // botón no existiera todavía; workspace.js sigue llamando refrescar por WS).
    root.JarvisDevServers?.init?.();
    if (_pid != null) root.JarvisDevServers?.cargar?.(_pid);
    else root.JarvisDevServers?.refrescar?.();
  }

  // ── Galería de disposiciones (snap zones) + split ────────────────
  const _layoutKey = (pid) => `jarvis.preview.layout.${pid}`;

  function _montarGaleriaLayouts() {
    const cont = $('#wp-lg');
    if (!cont) return;
    cont.innerHTML = LY().LAYOUTS.map((l) => {
      const celdas = Array.from({ length: l.panes }, () => '<i></i>').join('');
      return `<button class="wp-lg-cell" type="button" role="menuitemradio" data-layout="${l.id}" title="${l.label}">`
        + `<span class="wp-lg-mini wp-lg-${l.id}">${celdas}</span><span>${l.label}</span></button>`;
    }).join('');
    cont.addEventListener('click', (e) => {
      const b = e.target.closest('.wp-lg-cell');
      if (!b) return;
      _setLayout(b.dataset.layout);
      _cerrarGaleria();
    });
  }
  function _toggleGaleria(e) {
    if (e) e.stopPropagation();
    const cont = $('#wp-lg'), btn = $('#wp-layout');
    if (!cont) return;
    const abrir = cont.hasAttribute('hidden');
    if (abrir) _cerrarMore();   // dock angosto: la galería reemplaza al tray ⋯
    cont.toggleAttribute('hidden', !abrir);
    if (btn) btn.classList.toggle('activo', abrir);
    if (abrir) _marcarGaleria();
  }

  // ── Overflow ⋯ de la barra (solo visible en dock angosto vía @container) ──
  // Colapsa las acciones secundarias (ext/dark/layout) en un popover para no
  // aplastar la omnibar. Mismo patrón que la galería.
  function _toggleMore(e) {
    if (e) e.stopPropagation();
    const tray = $('#wp-more-tray'), btn = $('#wp-more');
    if (!tray) return;
    const abrir = tray.hasAttribute('hidden');
    tray.toggleAttribute('hidden', !abrir);
    if (btn) { btn.classList.toggle('activo', abrir); btn.setAttribute('aria-expanded', abrir ? 'true' : 'false'); }
  }
  function _cerrarMore() {
    const tray = $('#wp-more-tray'), btn = $('#wp-more');
    if (tray) tray.setAttribute('hidden', '');
    if (btn) { btn.classList.remove('activo'); btn.setAttribute('aria-expanded', 'false'); }
  }
  function _cerrarMoreAfuera(e) {
    const tray = $('#wp-more-tray');
    if (!tray || tray.hasAttribute('hidden')) return;
    if (tray.contains(e.target) || (e.target.closest && e.target.closest('#wp-more'))) return;
    _cerrarMore();
  }
  function _cerrarGaleria() {
    const cont = $('#wp-lg'), btn = $('#wp-layout');
    if (cont) cont.setAttribute('hidden', '');
    if (btn) btn.classList.remove('activo');
  }
  function _cerrarGaleriaAfuera(e) {
    const cont = $('#wp-lg');
    if (!cont || cont.hasAttribute('hidden')) return;
    if (cont.contains(e.target) || (e.target.closest && e.target.closest('#wp-layout'))) return;
    _cerrarGaleria();
  }
  function _marcarGaleria() {
    if (!_cont) return;
    for (const b of _cont.querySelectorAll('.wp-lg-cell')) {
      b.classList.toggle('activo', b.dataset.layout === _layout);
    }
  }
  function _setLayout(id) {
    const norm = LY().normalizar(id);
    if (norm === _layout) return;
    _layout = norm;
    try { if (_pid != null) localStorage.setItem(_layoutKey(_pid), _layout); } catch { /* quota/privado */ }
    _render();
  }

  // Clicks dentro del body (delegación): heads de celda del split y CTAs del
  // fallback por-panel. En modo single (1 panel) no hay heads → sin efecto.
  function _onBodyClick(e) {
    const cell = e.target.closest('.wp-cell');
    if (!cell) return;
    const id = Number(cell.dataset.tab);
    if (Number.isNaN(id)) return;
    if (e.target.closest('.wp-cell-cerrar')) { _cerrar(id); return; }
    if (e.target.closest('.wp-cell-max'))    { _setLayout('1'); _activar(id); return; }
    if (e.target.closest('.wp-cell-open'))   { openExternal(id); return; }
    if (e.target.closest('.wp-cell-head'))   { _activar(id); return; }
  }

  // ── Tracking de reproducción (postMessage API de YouTube) ────────
  // Con enablejsapi (urlMedia) el widget emite infoDelivery con currentTime
  // y playerState mientras suena — pero SOLO después de recibir "listening".
  // Lo guardado (url → {t, play}) viaja en el localStorage del proyecto
  // dueño (throttle 2.5s): un reinicio/recarga reanuda la música donde
  // estaba (_restaurar + urlMedia con start/autoplay).
  let _mediaPendiente = {};   // url → {t, play} leído del storage al restaurar
  let _mediaGuardadoTs = 0;

  function _onMensajeYoutube(e) {
    if (e.origin !== 'https://www.youtube.com' && e.origin !== 'https://www.youtube-nocookie.com') return;
    let d = e.data;
    if (typeof d === 'string') { try { d = JSON.parse(d); } catch { return; } }
    if (!d || d.event !== 'infoDelivery' || !d.info) return;
    const hit = _vistaPorVentana(e.source);
    if (!hit) return;
    if (typeof d.info.currentTime === 'number') hit.v.mediaT = d.info.currentTime;
    if (typeof d.info.playerState === 'number') hit.v.mediaPlay = d.info.playerState === 1;
    // Handoff a la Radio GLOBAL: cuando un video de YouTube EMPIEZA a sonar en una
    // pestaña, la música pasa a la Radio (que sigue con relacionados) y se pausa
    // acá para no duplicar el audio. Una vez por video (se rearma al navegar).
    if (d.info.playerState === 1 && !hit.v.handoff && window.JarvisRadio) {
      const tab = _estado.tabs.find((x) => x.id === hit.id);
      const pura = window.WebPreviewRadio && window.WebPreviewRadio._pure;
      const track = (tab && pura) ? pura.pistaDeUrl(tab.url, tab.titulo) : null;
      if (track) {
        hit.v.handoff = true;
        window.JarvisRadio.adopt(track);
        try { hit.v.iframe.contentWindow?.postMessage(JSON.stringify({ event: 'command', func: 'pauseVideo', args: [] }), e.origin); } catch {}
      }
    }
    const ahora = Date.now();
    if (ahora - _mediaGuardadoTs > 2500) { _mediaGuardadoTs = ahora; _guardarTodo(); }
  }

  // Busca la vista dueña de un contentWindow en el proyecto actual Y en los
  // pools estacionados (la música de otro proyecto sigue trackeándose).
  function _vistaPorVentana(win) {
    const en = (vistas) => {
      const k = Object.keys(vistas).find((k) => vistas[k].iframe.contentWindow === win);
      return k == null ? null : { v: vistas[k], id: Number(k) };
    };
    const aca = en(_vistas);
    if (aca) return aca;
    for (const pool of Object.values(_pools)) {
      const hit = en(pool.vistas);
      if (hit) return hit;
    }
    return null;
  }

  // El widget de YouTube no emite nada hasta recibir "listening": se lo
  // saludamos al load del iframe, con reintento (el bus del player tarda en
  // armarse). Siempre al load — el embed entra por una carga nuestra
  // (_cargar/refresh/_recargarTab). Hasta 2026-07-26 existía además un camino
  // "saludo inmediato" para el SERP, que se auto-navegaba al embed; con el
  // SERP eliminado, ese caso no existe más.
  function _engancharYoutube(v, url) {
    const u = _embedYt(url);
    if (!u) return;
    v.handoff = false;   // nuevo video → puede volver a hacer handoff a la Radio
    const saludo = () => {
      try {
        v.iframe.contentWindow?.postMessage(
          JSON.stringify({ event: 'listening', id: 'wp', channel: 'widget' }), u.origin);
      } catch { /* el iframe navegó a otra cosa */ }
    };
    v.iframe.addEventListener('load', () => { saludo(); setTimeout(saludo, 1200); }, { once: true });
  }

  // ── Render (estado puro → DOM) ───────────────────────────────────
  function _set(estado) {
    _estado = estado;
    _render();
    _guardar();
  }

  function _render() {
    _renderTabs();
    _renderVista();
    _sincronizarBarra();
    _syncTwitch();
  }

  // La Radio global se PARA solo mientras la pestaña ACTIVA es un Twitch (tiene su
  // propio audio); al salir de Twitch, la Radio vuelve sola. Idempotente por _twitchOn.
  let _twitchOn = false;
  function _syncTwitch() {
    if (!window.JarvisRadio) return;
    const activa = T().tabActiva(_estado);
    let host = '';
    try { host = activa && activa.url ? new URL(activa.url).hostname : ''; } catch {}
    const esTw = /(^|\.)twitch\.tv$/i.test(host);
    if (esTw === _twitchOn) return;
    _twitchOn = esTw;
    esTw ? window.JarvisRadio.pauseForTwitch() : window.JarvisRadio.resumeAfterTwitch();
  }

  // Pinta el favicon de UNA pestaña dentro de su span `.wp-tab-fav`. Fuente:
  // faviconSrc (declarado > /favicon.ico local > servicio público > null). Sin
  // src (pestaña vacía o demo de Jarvis sin ícono declarado aún) → globo default.
  // Con src: letra coloreada como placeholder mientras carga; al cargar, la
  // imagen; si falla (404) → globo para los locales (el "default" que el usuario
  // espera), la letra para los públicos.
  function _pintarFavicon(fav, t) {
    fav.className = fav.dataset.base || 'wp-tab-fav';
    fav.style.background = '';
    fav.replaceChildren();
    const host = _host(t.url);
    const declarado = _vistas[t.id] ? _vistas[t.id].favicon : null;
    const src = host ? faviconSrc(t.url, declarado, location.host) : null;
    if (!src) {
      fav.classList.add('wp-tab-fav-blank');
      fav.innerHTML = SVG_TAB_GLOBO;
      return;
    }
    fav.style.background = _colorHost(host);
    fav.textContent = host.replace(/^www\./, '')[0].toUpperCase();
    const img = document.createElement('img');
    img.alt = ''; img.loading = 'lazy';
    img.addEventListener('load', () => { fav.style.background = 'transparent'; fav.replaceChildren(img); });
    img.addEventListener('error', () => {
      img.remove();
      // Local sin favicon (404) → globo default; público → queda la letra.
      if (_esLocal(t.url)) {
        fav.style.background = ''; fav.textContent = '';
        fav.classList.add('wp-tab-fav-blank'); fav.innerHTML = SVG_TAB_GLOBO;
      }
    });
    img.src = src;
    fav.appendChild(img);
  }

  // Repinta SOLO el favicon de la pestaña `id` (sin rehacer toda la fila): lo
  // llama la resolución del <link rel=icon> al cargar el iframe.
  function _refrescarFaviconTab(id) {
    if (!_tabsEl || _drag) return;
    const el = _tabsEl.querySelector(`.wp-tab[data-tab-id="${id}"]`);
    const fav = el && el.querySelector('.wp-tab-fav');
    const t = _estado && _estado.tabs.find((x) => x.id === id);
    if (fav && t) _pintarFavicon(fav, t);
  }

  // Al cargar el iframe de una pestaña LOCAL mismo-origen (los demos de Jarvis),
  // leer el <link rel=icon> que declara la página y usarlo como favicon real —
  // así el demo muestra SU ícono (los demos lo traen inline) en vez del globo.
  // Cross-origin (dev server en otro puerto) tira SecurityError → se queda con
  // el /favicon.ico que ya intentó el render. Best-effort: cualquier fallo, nada.
  function _resolverFaviconLocal(id, v) {
    const t = _estado && _estado.tabs.find((x) => x.id === id);
    if (!t || !t.url || !_esLocal(t.url)) return;
    let doc = null;
    try { doc = v.iframe.contentDocument; } catch { doc = null; }
    if (!doc) return;
    const link = doc.querySelector('link[rel~="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"]');
    const href = link && link.getAttribute('href') ? link.href : null;
    if (href && v.favicon !== href) {
      v.favicon = href;
      _refrescarFaviconTab(id);
    }
  }

  function _renderTabs() {
    if (!_tabsEl) return;
    // Drag en curso: NO rehacer la fila (el innerHTML dejaría huérfano al
    // elemento arrastrado y el drag moriría en silencio — pasa de verdad: el
    // título/favicon real que llega al cargar re-renderiza seguido). Se marca
    // y _dragSoltar lo flushea al terminar.
    if (_drag) { _renderTabsDiferido = true; return; }
    _tabsEl.innerHTML = '';
    for (const t of _estado.tabs) {
      const activa = t.id === _estado.activaId;
      const el = document.createElement('div');
      el.className = 'wp-tab' + (activa ? ' activa' : '');
      el.dataset.tabId = t.id;        // para el refresco puntual del favicon al cargar
      el.setAttribute('role', 'tab');
      el.setAttribute('aria-selected', activa ? 'true' : 'false');
      el.title = t.url || 'Nueva pestaña';
      const fav = document.createElement('span');
      _pintarFavicon(fav, t);
      const titulo = document.createElement('span');
      titulo.className = 'wp-tab-titulo';
      titulo.textContent = t.titulo || _host(t.url) || 'Nueva pestaña';
      const cerrar = document.createElement('button');
      cerrar.className = 'wp-tab-cerrar';
      cerrar.type = 'button';
      cerrar.title = 'Cerrar pestaña';
      cerrar.setAttribute('aria-label', 'Cerrar pestaña');
      cerrar.textContent = '×';
      el.appendChild(fav);
      el.appendChild(titulo);
      el.appendChild(cerrar);
      el.addEventListener('click', (e) => {
        if (_dragFantasma) return;   // este click es el final de un drag, no un click
        if (e.target === cerrar) { _cerrar(t.id); return; }
        _activar(t.id);
      });
      el.addEventListener('pointerdown', (e) => _dragIniciar(e, el, t.id));
      _tabsEl.appendChild(el);
    }
    const mas = document.createElement('button');
    mas.className = 'wp-tab-new';
    mas.type = 'button';
    mas.title = 'Nueva pestaña';
    mas.setAttribute('aria-label', 'Nueva pestaña');
    mas.textContent = '+';
    mas.addEventListener('click', _nuevaTab);
    _tabsEl.appendChild(mas);
  }

  // ── Reorden de pestañas por arrastre (mantener y mover) ──────────
  // pointerdown arma el tracking; pasado el umbral la pestaña sigue al
  // puntero (transform, sin transición) y las demás se corren en vivo con
  // una transición corta. Al soltar: moverTab + persistencia (vía _set).
  // La medición (rects) se toma UNA vez al cruzar el umbral — el destino lo
  // calcula la pura destinoDrag contra esos centros originales. El capture
  // en la pestaña mantiene el drag vivo aunque el puntero pise un iframe.
  const DRAG_UMBRAL = 5;      // px: menos que esto es un click, no un drag
  let _drag = null;           // { id, el, x0, els, rects, idx, destino, gap }
  let _dragFantasma = false;  // suprime el click que dispara el mismo gesto
  let _renderTabsDiferido = false;  // hubo _renderTabs durante el drag → flush al soltar

  function _dragIniciar(e, el, id) {
    if (e.button !== 0 || e.target.closest('.wp-tab-cerrar')) return;
    if (_estado.tabs.length < 2 || _drag) return;
    const mover = (ev) => _dragMover(ev);
    const soltar = () => _dragSoltar();
    _drag = { id, el, x0: e.clientX, els: null, rects: null, idx: -1, destino: -1, gap: 0, mover, soltar };
    el.addEventListener('pointermove', mover);
    el.addEventListener('pointerup', soltar);
    el.addEventListener('pointercancel', soltar);
    try { el.setPointerCapture(e.pointerId); } catch { /* puntero ya muerto */ }
  }

  function _dragMover(e) {
    if (!_drag) return;
    const dx = e.clientX - _drag.x0;
    if (!_drag.rects) {
      if (Math.abs(dx) < DRAG_UMBRAL) return;
      _drag.els = [..._tabsEl.querySelectorAll('.wp-tab')];
      _drag.rects = _drag.els.map((t) => {
        const r = t.getBoundingClientRect();
        return { left: r.left, width: r.width };
      });
      _drag.idx = _drag.els.indexOf(_drag.el);
      _drag.gap = parseFloat(getComputedStyle(_tabsEl).columnGap) || 0;
      _tabsEl.classList.add('reordenando');
      _drag.el.classList.add('arrastrando');
    }
    // prev = destino anterior → histéresis (el jitter del mouse en el borde
    // no des-swapea); -1 = recién arranca, sin histéresis.
    _drag.destino = T().destinoDrag(_drag.rects, _drag.idx, dx,
      _drag.destino === -1 ? null : _drag.destino);
    _drag.el.style.transform = `translateX(${dx}px)`;
    const paso = _drag.rects[_drag.idx].width + _drag.gap;
    _drag.els.forEach((t, j) => {
      if (j === _drag.idx) return;
      let s = 0;
      if (_drag.idx < _drag.destino && j > _drag.idx && j <= _drag.destino) s = -paso;
      else if (_drag.idx > _drag.destino && j >= _drag.destino && j < _drag.idx) s = paso;
      t.style.transform = s ? `translateX(${s}px)` : '';
    });
  }

  function _dragSoltar() {
    const d = _drag;
    _drag = null;
    if (!d) return;
    d.el.removeEventListener('pointermove', d.mover);
    d.el.removeEventListener('pointerup', d.soltar);
    d.el.removeEventListener('pointercancel', d.soltar);
    // Renders de la fila diferidos durante el drag: flushear al salir (si el
    // drop reordena, el _set de abajo ya re-renderiza y esto queda en falso).
    const flush = () => {
      if (_renderTabsDiferido) { _renderTabsDiferido = false; _render(); }
    };
    if (!d.rects) { flush(); return; } // nunca cruzó el umbral: click normal
    _tabsEl.classList.remove('reordenando');
    d.el.classList.remove('arrastrando');
    d.els.forEach((t) => { t.style.transform = ''; });
    // El browser dispara un click al soltar: marcarlo como fantasma para que
    // no active/cierre la pestaña (el flag muere apenas drena la cola).
    _dragFantasma = true;
    setTimeout(() => { _dragFantasma = false; }, 0);
    if (d.destino !== -1 && d.destino !== d.idx) {
      _renderTabsDiferido = false;
      _set(T().moverTab(_estado, d.id, d.destino));
    } else {
      flush();
    }
  }

  // Render del split: ubica cada celda visible en su área (a/b/c/d), setea su
  // estado interno (iframe/nativo/fallback/loading) y el foco. Modo single
  // (1 panel) = grilla de 1 celda → comportamiento idéntico al de siempre.
  function _renderVista() {
    if (!_bodyEl) return;
    const panes = LY().panesDe(_layout);
    const split = panes > 1;
    const tabIds = _estado.tabs.map((t) => t.id);
    const activa = T().tabActiva(_estado);
    const visibles = LY().asignar(tabIds, panes, activa ? activa.id : null);
    const areas = ['a', 'b', 'c', 'd'];
    const posDe = {};
    visibles.forEach((tid, i) => { if (tid != null) posDe[tid] = i; });

    _bodyEl.style.gridTemplate = LY().template(_layout);
    _bodyEl.dataset.split = split ? '1' : '0';

    for (const [idStr, vista] of Object.entries(_vistas)) {
      const id = Number(idStr);
      const i = posDe[id];
      const visible = i != null;
      vista.cell.hidden = !visible;
      if (!visible) continue;
      vista.cell.style.gridArea = areas[i];
      vista.cell.classList.toggle('foco', !!(activa && activa.id === id));
      vista.iframe.hidden = !(vista.vista === 'iframe');
      if (vista.hueco) vista.hueco.hidden = !(vista.vista === 'nativo');
      const load = vista.stage.querySelector('.wp-loading');
      const fb   = vista.stage.querySelector('.wp-fallback');
      if (load) load.hidden = !vista.cargando;
      if (fb)   fb.hidden   = vista.vista !== 'fallback';
      const t = _estado.tabs.find((x) => x.id === id);
      const urlEl = vista.cell.querySelector('.wp-cell-url');
      const favEl = vista.cell.querySelector('.wp-cell-fav');
      if (favEl && t) _pintarFavicon(favEl, t);
      if (urlEl && t) {
        urlEl.textContent = '';
        const b = document.createElement('b');
        b.textContent = _host(t.url) || t.titulo || 'Nueva pestaña';
        urlEl.appendChild(b);
        const i = document.createElement('i');
        try {
          const u = new URL(t.url);
          i.textContent = (u.pathname && u.pathname !== '/') ? u.pathname : '';
        } catch { /* URL no parseable (pestaña vacía): sin ruta */ }
        urlEl.appendChild(i);
      }
    }

    const empty = $('#wp-empty');
    if (empty) {
      const activaSinUrl = !activa || !activa.url;
      const todoVacio = !_estado.tabs.some((t) => t.url);
      empty.hidden = split ? !todoVacio : !activaSinUrl;
    }
  }

  function _sincronizarBarra() {
    const t = T().tabActiva(_estado);
    if (_input)   _input.value      = (t && t.url) || '';
    if (_btnBack) _btnBack.disabled = !t || t.idx <= 0;
    if (_btnFwd)  _btnFwd.disabled  = !t || t.idx >= t.stack.length - 1;
    // Chip LOCAL de la omnibar: la pestaña activa es un servidor local vivo.
    const chipLocal = $('#wp-omni-local');
    if (chipLocal) chipLocal.hidden = !(t && t.url && _esLocal(t.url));
    // Modo nativo : el historial real vive en el webview hijo, así
    // que ‹ › van siempre habilitados y 🌙 no aplica (el webview ya renderiza
    // como un browser de verdad).
    const v = t ? _vistas[t.id] : null;
    const esNativo = !!(v && v.vista === 'nativo');
    if (esNativo) {
      if (_btnBack) _btnBack.disabled = false;
      if (_btnFwd)  _btnFwd.disabled  = false;
    }
    const btnDark = $('#wp-dark');
    if (btnDark) {
      btnDark.disabled = esNativo;
      btnDark.classList.toggle('activo', !!(v && v.dark) && !esNativo);
    }
  }

  // Color determinista por host (fallback del favicon: la inicial coloreada).
  function _colorHost(host) {
    let h = 0;
    for (let i = 0; i < host.length; i++) h = (h * 31 + host.charCodeAt(i)) % 360;
    return `oklch(58% 0.15 ${h})`;
  }

  function _host(url) {
    if (!url) return null;
    try {
      const u = new URL(url);
      return u.hostname + (u.port ? ':' + u.port : '');
    } catch { return url; }
  }

  // ── Vistas (iframe + efectos por pestaña) ────────────────────────
  // Cada pestaña vive en su propia CELDA (.wp-cell): un wrapper que NUNCA se
  // reparenta — solo cambia de grid-area y se muestra/oculta. Así el iframe no
  // recarga al entrar/salir del split (la música/video persiste). Adentro:
  // head del panel (visible solo en split) + stage (iframe/canvas/overlays).
  function _vistaDe(id) {
    let v = _vistas[id];
    if (v) return v;
    const cell = document.createElement('div');
    cell.className = 'wp-cell';
    cell.dataset.tab = String(id);
    cell.hidden = true;
    cell.innerHTML =
      `<div class="wp-cell-head">
         <span class="wp-cell-fav" data-base="wp-cell-fav"></span>
         <span class="wp-cell-url"></span>
         <button class="wp-cell-max" type="button" title="Ver solo este panel" aria-label="Maximizar panel">${SVG_MAX2}</button>
         <button class="wp-cell-cerrar" type="button" title="Cerrar pestaña" aria-label="Cerrar">×</button>
       </div>
       <div class="wp-cell-stage">
         <!-- Carga: barra de progreso fina arriba (estilo browser). -->
         <div class="wp-loading" hidden><i class="wp-loading-barra"></i><span class="ob-spinner lg"></span></div>
         <div class="wp-fallback" hidden>
           <div class="wp-fallback-icon">${icon('alert', 30)}</div>
           <h2>El sitio bloqueó el embebido</h2>
           <p>Este servidor manda <code>X-Frame-Options</code> o
              <code>CSP frame-ancestors</code> y no se deja mostrar dentro de Jarvis.</p>
           <button class="jw-btn primario wp-cta wp-cell-open" type="button">Abrir en pestaña ${SVG_EXTERNAL}</button>
         </div>
       </div>`;
    const stage = cell.querySelector('.wp-cell-stage');
    const f = document.createElement('iframe');
    f.className = 'wp-iframe';
    f.title = 'Web preview';
    f.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms allow-popups allow-modals');
    // autoplay delegado: sin esto, el embed de YouTube (cross-origin) no puede
    // arrancar con audio aunque el click venga de un gesto real del usuario.
    f.setAttribute('allow', 'autoplay; fullscreen; encrypted-media; picture-in-picture');
    f.setAttribute('referrerpolicy', 'no-referrer');
    stage.insertBefore(f, stage.firstChild);
    _bodyEl.appendChild(cell);
    v = { iframe: f, cell, stage, gen: 0, onLoad: null, loadTimer: null, esperando: false, vista: 'iframe', cargando: false, favicon: null };
    _vistas[id] = v;
    return v;
  }

  function _destruirVista(id, vistas = _vistas) {
    const v = vistas[id];
    if (!v) return;
    // claveNativa guarda el pid dueño: vale también para vistas estacionadas
    // de OTRO proyecto (no recalcular con _pid).
    if (v.claveNativa) { root.NativeBrowse.cerrar(v.claveNativa); v.claveNativa = null; }
    if (v.loadTimer) clearTimeout(v.loadTimer);
    if (v.onLoad) v.iframe.removeEventListener('load', v.onLoad);
    (v.cell || v.iframe).remove();
    delete vistas[id];
  }

  // ── Acciones sobre pestañas ──────────────────────────────────────
  function _nuevaTab() {
    const r = T().abrirTab(_estado, null);
    if (r.error === 'max') { _toastMax(); return; }
    _set(r.estado);
    if (_input) _input.focus();
  }

  function _activar(id) {
    _set(T().activarTab(_estado, id));
    // Lazy-load: pestaña restaurada de localStorage aún sin iframe → cargar.
    const t = T().tabActiva(_estado);
    if (t && t.url && !_vistas[t.id]) _cargar(t.id, t.url);
  }

  function _cerrar(id) {
    _destruirVista(id);
    _set(T().cerrarTab(_estado, id));
  }

  function _navegar(id, url, push) {
    _set(T().navegarTab(_estado, id, url, push));
    _cargar(id, url);
  }

  function _toastMax() {
    if (typeof toast === 'function') toast(`Máximo ${T().MAX_TABS} pestañas abiertas`);
  }

  // 🌙 dark forzado del iframe: filter invert (mejor esfuerzo — cross-origin
  // no deja inyectar CSS). hue-rotate conserva los matices; las imágenes
  // quedan invertidas, por eso es opt-in POR pestaña y no se persiste.
  function _toggleDark() {
    const t = T().tabActiva(_estado);
    if (!t) return;
    const v = _vistaDe(t.id);
    v.dark = !v.dark;
    v.iframe.classList.toggle('wp-dark-forzado', v.dark);
    _sincronizarBarra();
  }

  // ── API pública ──────────────────────────────────────────────────
  // Navega la pestaña ACTIVA (creándola si no hay ninguna). Compatibilidad
  // con los llamadores existentes (pill del badge, orquestador).
  function setUrl(url, push = true) {
    const norm = normalizarUrl(url);
    if (!norm) return;
    let activa = T().tabActiva(_estado);
    if (!activa) {
      const r = T().abrirTab(_estado, null);
      if (r.error === 'max') { _toastMax(); return; }
      _estado = r.estado; // _navegar hace el _set/render
      activa = T().tabActiva(_estado);
    }
    _navegar(activa.id, norm, push);
  }

  // Abre la URL en una pestaña NUEVA; si ya hay una pestaña con esa URL la
  // activa (dev servers detectados: no duplicar).
  function openTab(url) {
    const norm = normalizarUrl(url);
    if (!norm) return;
    const existente = T().encontrarPorUrl(_estado, norm);
    if (existente != null) { _activar(existente); return; }
    const r = T().abrirTab(_estado, null);
    if (r.error === 'max') { _toastMax(); return; }
    _estado = r.estado;
    _navegar(_estado.activaId, norm, true);
  }

  // Un dev server RE-detectado tras un reinicio (p.ej. el agente lo reinició
  // para un cambio de diseño) debe mostrar la versión fresca — PERO solo si el
  // usuario YA tiene abierta su pestaña. NUNCA crea una pestaña ni roba el foco
  // (regla "menú-primero", 2026-07-12: la detección no abre nada sola; el
  // usuario abre desde el menú #jw-localhosts-btn o maximizando la card del
  // agente). Recarga en su lugar por ORIGEN (misma URL base aunque el usuario
  // haya navegado adentro). Devuelve true si había una pestaña y la recargó.
  function refrescarSiExiste(url) {
    const norm = normalizarUrl(url);
    if (!norm || !_estado) return false;   // detección antes del primer init → no hay pestañas
    // Reuso por CARPETA para los demos de Jarvis (comparten origen :3000): así
    // no recargamos el demo de OTRO agente al re-detectar el de este.
    const id = T().encontrarPorReuso(_estado, norm, location.host);
    if (id == null) return false;
    _recargarTab(id);
    return true;
  }

  // Click de un link LOCAL en la terminal de un agente (ver linkAlPreview), salto
  // al localhost del agente (maximizar/seleccionar card) y fila del menú de
  // localhost: se comporta como un browser reusando la pestaña de esa "cosa" si
  // ya existe — un dev server real por ORIGEN, un demo de Jarvis por su CARPETA
  // (`encontrarPorReuso`: así el demo de un agente NO evicta el de otro, que
  // comparten origen :3000). La misma URL se RECARGA (el agente suele linkear
  // tras un rebuild: hay que ver lo fresco), otra ruta del mismo server/demo
  // NAVEGA esa pestaña; sin pestaña, se abre una nueva. Siempre queda activa.
  function abrirLink(url) {
    const norm = normalizarUrl(url);
    if (!norm) return;
    const id = T().encontrarPorReuso(_estado, norm, location.host);
    if (id == null) { openTab(norm); return; }
    const t = _estado.tabs.find((x) => x.id === id);
    // 'http://localhost:5173' y 'http://localhost:5173/' son la misma página
    // (URL.toString() agrega la barra; dev_detect no) — no apilar historial.
    const misma = t && (t.url === norm || t.url + '/' === norm || t.url === norm + '/');
    if (misma) _recargarTab(id);
    else _navegar(id, norm, true);
    _activar(id);
  }

  // Recarga el iframe de UNA pestaña por id (no necesariamente la activa),
  // con cache-bust: un restart/rebuild sirve contenido nuevo en la misma URL,
  // así que el reload real es la única forma de verlo. Espejo de refresh().
  function _recargarTab(id) {
    const t = _estado.tabs.find((x) => x.id === id);
    if (!t || !t.url) return;
    const v0 = _vistas[id];
    if (v0 && v0.vista === 'nativo') { root.NativeBrowse.recargar(v0.claveNativa); return; }
    const v = _vistaDe(id);
    v.vista = 'iframe';
    _iniciarDeteccion(id, v);
    v.iframe.referrerPolicy = politicaReferrer(t.url);
    _engancharYoutube(v, t.url);
    const base = urlMedia(t.url, location.origin, null);
    const sep = base.includes('?') ? '&' : '?';
    v.iframe.src = `${base}${sep}_wp=${Date.now()}`;
    _renderVista();
  }

  function getUrl() {
    const t = T().tabActiva(_estado);
    return t ? t.url : null;
  }

  function _atras() {
    const t = T().tabActiva(_estado);
    const vR = t ? _vistas[t.id] : null;
    if (vR && vR.vista === 'nativo') { root.NativeBrowse.atras(vR.claveNativa); return; }
    if (!t || t.idx <= 0) return;
    _set(T().atrasTab(_estado, t.id));
    const t2 = T().tabActiva(_estado);
    _cargar(t2.id, t2.url);
  }

  function _adelante() {
    const t = T().tabActiva(_estado);
    const vR = t ? _vistas[t.id] : null;
    if (vR && vR.vista === 'nativo') { root.NativeBrowse.adelante(vR.claveNativa); return; }
    if (!t || t.idx >= t.stack.length - 1) return;
    _set(T().adelanteTab(_estado, t.id));
    const t2 = T().tabActiva(_estado);
    _cargar(t2.id, t2.url);
  }

  // ── Browse NATIVO (solo en la app de escritorio) ───────────────────────
  // Los sitios EXTERNOS se abren en un webview hijo nativo del shell
  // (NativeBrowse, frontend/shell/native-browse.js): navegador real, fluido y
  // sin probe. Lo local (dev servers, demos de Jarvis) y los embeds de media
  // (YouTube/Twitch) SIGUEN en iframe: ya son nativos ahí
  // y toda la maquinaria de audio-persistente/pausa depende del iframe.
  function _nativoOk() { return !!(root.NativeBrowse && root.NativeBrowse.disponible); }
  function _esNativable(url) { return _nativoOk() && !_esLocal(url) && !esEmbed(url); }

  function _cargarNativo(id, url) {
    const v = _vistaDe(id);
    // Invalidar cualquier carga de iframe pendiente (onload/timeout viejos).
    v.gen += 1;
    v.esperando = false;
    if (v.loadTimer) { clearTimeout(v.loadTimer); v.loadTimer = null; }
    if (v.onLoad) { v.iframe.removeEventListener('load', v.onLoad); v.onLoad = null; }
    v.vista = 'nativo';
    v.cargando = false;   // el webview pinta su propia carga (browser real)
    // Soltar la página previa del iframe (si venía de un embed con audio, la
    // navegación lo reemplaza — igual que navegar en un browser).
    if (v.iframe.src && v.iframe.src !== 'about:blank') v.iframe.src = 'about:blank';
    if (!v.hueco) {
      v.hueco = document.createElement('div');
      v.hueco.className = 'wp-nativo';
      v.stage.appendChild(v.hueco);
    }
    v.claveNativa = `${_pid == null ? 's' : _pid}:${id}`;
    root.NativeBrowse.abrir(v.claveNativa, url, v.hueco);
    _renderVista();
  }

  // La pestaña vuelve de nativo a iframe (p. ej. navegó a un localhost).
  function _apagarNativo(v) {
    if (!v || v.vista !== 'nativo') return;
    if (v.claveNativa) root.NativeBrowse.cerrar(v.claveNativa);
    if (v.hueco) { v.hueco.remove(); v.hueco = null; }
    v.claveNativa = null;
  }

  // Estado de navegación del shell ({clave, url?, cargando?, titulo?, popup?}):
  // clicks DENTRO del sitio nativo → reflejar URL y TÍTULO real en la pestaña
  // sin tocar el stack (el historial vive en el webview; ‹ › delegan en él).
  // popup = el sitio pidió ventana nueva (target=_blank): pestaña nueva.
  function _onEstadoNativo(e) {
    const idStr = Object.keys(_vistas).find((k) => _vistas[k].claveNativa === e.clave);
    if (idStr == null) return;
    const id = Number(idStr);
    const v = _vistas[id];
    if (!v || v.vista !== 'nativo') return;
    if (e.popup) { openTab(e.popup); return; }
    const t = _estado.tabs.find((x) => x.id === id);
    if (!t) return;
    let est = _estado;
    if (e.url && t.url !== e.url) est = T().navegarTab(est, id, e.url, false);
    if (typeof e.titulo === 'string') est = T().tituloTab(est, id, e.titulo.slice(0, 80) || null);
    if (est !== _estado) _set(est);
  }

  // ── Carga real del iframe (con detección de bloqueo POR PESTAÑA) ─
  function _cargar(id, url) {
    if (_esNativable(url)) { _cargarNativo(id, url); return; }
    const v = _vistaDe(id);
    _apagarNativo(v);
    v.vista = 'iframe';
    _iniciarDeteccion(id, v);
    v.iframe.referrerPolicy = politicaReferrer(url);
    // Reanudación one-shot: si esta URL tenía música sonando antes del
    // reload, urlMedia le mete start=segundo guardado (+autoplay).
    const media = _mediaPendiente[url] || null;
    if (media) delete _mediaPendiente[url];
    _engancharYoutube(v, url);
    // Reproductores embebidos (YouTube/Twitch): sus links "ver en el
    // sitio / relacionados" abren con target=_blank y, con allow-popups,
    // SALTAN a una pestaña EXTERNA (fuera de Jarvis). Se los sacamos → el
    // media se queda EN el workspace.
    v.iframe.setAttribute('sandbox', esEmbed(url)
      ? 'allow-scripts allow-same-origin allow-forms allow-modals'
      : 'allow-scripts allow-same-origin allow-forms allow-popups allow-modals');
    v.iframe.src = urlMedia(url, location.origin, media);
    _renderVista();
    _probarEmbebibilidad(id, url);
  }

  // ⟳: recarga la pestaña activa con cache-bust en el query (no en la barra).
  function refresh() {
    const t = T().tabActiva(_estado);
    const v0 = t ? _vistas[t.id] : null;
    if (v0 && v0.vista === 'nativo') { root.NativeBrowse.recargar(v0.claveNativa); return; }
    if (!t || !t.url) return;
    const v = _vistaDe(t.id);
    v.vista = 'iframe';
    _iniciarDeteccion(t.id, v);
    v.iframe.referrerPolicy = politicaReferrer(t.url);
    _engancharYoutube(v, t.url);
    const base = urlMedia(t.url, location.origin, null);
    const sep = base.includes('?') ? '&' : '?';
    v.iframe.src = `${base}${sep}_wp=${Date.now()}`;
    _renderVista();
  }

  // ↗: abre la URL real en el navegador. Sin id → la pestaña activa; con id
  // (CTA del fallback de un panel del split) → la de ESE panel.
  function openExternal(id) {
    let url;
    if (id != null) { const t = _estado.tabs.find((x) => x.id === id); url = t && t.url; }
    else url = getUrl();
    if (url) window.open(url, '_blank', 'noopener');
  }

  // Sonda server-side de embebibilidad (spec §2.6 del Panel Único). El JS del
  // padre NO puede distinguir un iframe bloqueado por XFO/CSP de un
  // cross-origin válido, así que preguntamos al backend. Las URLs locales se
  // saltan el probe (el dev server propio siempre se deja embeber), y dentro
  // nativo los sitios externos tampoco pasan por acá: van derecho al
  // Browse nativo (_esNativable), que no tiene restricción de iframe.
  function _probarEmbebibilidad(id, norm) {
    if (_esLocal(norm)) return;
    const v = _vistaDe(id);
    const gen = v.gen; // capturada DESPUÉS de _iniciarDeteccion (que la bumpeó)
    fetch('/api/orchestrator/preview/probe?url=' + encodeURIComponent(norm))
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data || data.embebible !== false) return;
        if (gen !== v.gen) return;          // carga vieja: ignorar
        // Invalidar ESTA carga: un sitio bloqueado (ej. github) igual dispara
        // `onload` sobre su documento de error y pisaría el fallback. Bumpeamos
        // gen y soltamos el listener para que ese onload tardío quede huérfano.
        v.gen += 1;
        if (v.onLoad) { v.iframe.removeEventListener('load', v.onLoad); v.onLoad = null; }
        v.esperando = false;
        if (v.loadTimer) { clearTimeout(v.loadTimer); v.loadTimer = null; }
        // El sitio no se deja embeber (XFO/CSP) → pantalla de bloqueo con el
        // "Abrir en pestaña". (Hasta 2026-07-26 acá se levantaba solo un
        // Chromium server-side con screencast; ese modo remoto se eliminó:
        // en el browser no vale mantener un browser entero en el server.)
        v.cargando = false;
        v.vista = 'fallback';
        _renderVista();
      })
      .catch(() => { /* red caída: que decidan onload/timeout */ });
  }

  // localhost / 127.0.0.1 / [::1] → local (se saltan el probe).
  function _esLocal(url) {
    try {
      const host = new URL(url).hostname.toLowerCase();
      return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]';
    } catch { return false; }
  }

  // ── Detección de iframe bloqueado (por pestaña) ──────────────────
  // Señal primaria: el TIMEOUT. Una página bloqueada por XFO/CSP no dispara
  // onload (o lo hace sobre un documento de error). La generación v.gen
  // invalida onload/timeout de cargas viejas de ESA pestaña.
  const BLOQUEO_MS = 4000;

  function _iniciarDeteccion(id, v) {
    v.gen += 1;
    const gen = v.gen;
    v.esperando = true;
    v.cargando = true;
    // El favicon declarado era de la carga ANTERIOR: soltarlo para que esta
    // carga lo re-resuelva (navegar a otra página puede traer otro ícono).
    if (v.favicon) { v.favicon = null; _refrescarFaviconTab(id); }
    if (v.onLoad) v.iframe.removeEventListener('load', v.onLoad);
    v.onLoad = function onLoad() {
      v.iframe.removeEventListener('load', onLoad);
      if (v.onLoad === onLoad) v.onLoad = null;
      if (gen !== v.gen) return;      // onload de una carga vieja: ignorar
      v.esperando = false;
      v.cargando = false;
      if (v.loadTimer) { clearTimeout(v.loadTimer); v.loadTimer = null; }
      v.vista = 'iframe';
      _renderVista();
      _resolverFaviconLocal(id, v);   // leer el <link rel=icon> del sitio (mismo-origen)
    };
    v.iframe.addEventListener('load', v.onLoad);
    if (v.loadTimer) clearTimeout(v.loadTimer);
    v.loadTimer = setTimeout(() => {
      // No llegó onload en 4s → el server rechazó el embebido (XFO/CSP)
      // o no responde. Fallback con CTA "Abrir en pestaña".
      if (gen !== v.gen || !v.esperando) return;
      v.esperando = false;
      v.cargando = false;
      v.vista = 'fallback';
      _renderVista();
    }, BLOQUEO_MS);
  }

  // ── Autodetección de dev servers ────────────────────────────────
  // GET /api/orchestrator/preview/{id} → { url, urls } (dev servers/demos vivos).
  // "Menú-primero" (2026-07-12): detectar() YA NO abre pestañas — antes sembraba
  // una por cada localhost detectado y así se amontonaban puertos sin sentido
  // (http.server de backups, mockups, el mismo server por 127.0.0.1 y localhost).
  // Ahora los localhost viven en el menú #jw-localhosts-btn y los abre el usuario
  // (o el salto por card de agente); el refresco tras un reinicio lo hace el
  // evento WS dev_server_detectado (→ refrescarSiExiste). Acá solo recordamos la
  // más reciente (informativo) y, si no hay pestañas, mostramos el estado vacío.
  async function detectar(projectId) {
    if (projectId == null) return null;
    if (_pid == null) _pid = projectId;
    let urls = [];
    try {
      const res = await fetch(`/api/orchestrator/preview/${projectId}`);
      if (res.ok) {
        const data = await res.json();
        urls = Array.isArray(data && data.urls) ? data.urls
             : (data && data.url ? [data.url] : []);
      }
    } catch { urls = []; }
    urls = urls.map(normalizarUrl).filter(Boolean);
    _detectada = urls.length ? urls[urls.length - 1] : null;
    if (!(_estado && _estado.tabs.some((t) => t.url))) _render();  // sin pestañas → estado empty
    return _detectada;
  }

  // ── Persistencia por proyecto (localStorage) ─────────────────────
  function _guardar() {
    if (_pid == null || !_estado) return;
    _guardarProyecto(_pid, _estado, _vistas);
  }

  // Serializa pestañas + posiciones de reproducción (url → {t, play}) del
  // proyecto dueño. play refleja si SONABA: es lo que decide la reanudación.
  function _guardarProyecto(pid, estado, vistas) {
    const data = T().serializar(estado);
    const media = {};
    for (const t of estado.tabs) {
      const v = vistas[t.id];
      if (t.url && v && v.mediaT != null) media[t.url] = { t: Math.floor(v.mediaT), play: !!v.mediaPlay };
    }
    if (Object.keys(media).length) data.media = media;
    try { localStorage.setItem(_lsKey(pid), JSON.stringify(data)); } catch { /* quota/privado */ }
  }

  // Todos los proyectos vivos: el actual + los pools estacionados (su música
  // sigue sonando y su posición también debe sobrevivir un reinicio).
  function _guardarTodo() {
    _guardar();
    for (const [pid, pool] of Object.entries(_pools)) _guardarProyecto(pid, pool.estado, pool.vistas);
  }

  // Higiene de las pestañas persistidas antes de restaurarlas: canonicaliza
  // cada URL (los alias de loopback colapsan a localhost) y DE-DUPEA por URL —
  // así los duplicados que dejó el auto-abrir viejo (la misma página abierta
  // como 127.0.0.1 Y como localhost, o el mismo demo repetido) se funden en una
  // sola pestaña al reabrir, sin que el usuario tenga que limpiarlas a mano.
  // Descarta pestañas vacías (url null) persistidas. Remapea el índice activo y
  // las claves de `media` (posición de YouTube) a la URL canónica.
  function _limpiarPersistido(data) {
    if (!data || !Array.isArray(data.urls)) return data;
    const activaUrl = (Number.isInteger(data.activa) && data.activa >= 0 && data.activa < data.urls.length)
      ? data.urls[data.activa] : null;
    const vistos = new Set();
    const urls = [];
    for (const u of data.urls) {
      const n = typeof u === 'string' ? normalizarUrl(u) : null;
      if (!n || vistos.has(n)) continue;   // vacía o duplicada (incl. alias de loopback) → fuera
      vistos.add(n);
      urls.push(n);
    }
    const activaN = activaUrl ? normalizarUrl(activaUrl) : null;
    const activa = activaN && urls.includes(activaN) ? urls.indexOf(activaN)
                 : (urls.length ? urls.length - 1 : -1);
    let media = data.media;
    if (media && typeof media === 'object') {
      const m2 = {};
      for (const [k, v] of Object.entries(media)) { const nk = normalizarUrl(k); if (nk) m2[nk] = v; }
      media = m2;
    }
    return { ...data, urls, activa, media };
  }

  function _restaurar(pid) {
    let data = null;
    try { data = JSON.parse(localStorage.getItem(_lsKey(pid)) || 'null'); } catch { /* basura */ }
    data = _limpiarPersistido(data);
    _estado = T().deserializar(data);
    _mediaPendiente = (data && data.media) || {};
    try { _layout = LY().normalizar(localStorage.getItem(_layoutKey(pid))); } catch { _layout = '1'; }
    _render();
    // La ACTIVA carga ya. ADEMÁS carga toda pestaña que tenía música SONANDO
    // antes del reload (aunque quede en segundo plano: un iframe oculto
    // suena igual) — así la música vuelve sola y desde donde estaba. El
    // resto sigue lazy (carga al activarse).
    for (const t of _estado.tabs) {
      if (!t.url) continue;
      const m = _mediaPendiente[t.url];
      if (t.id === _estado.activaId || (m && m.play)) _cargar(t.id, t.url);
    }
  }

  // Cambio de proyecto: persistir es continuo (_set). El pool saliente
  // {estado, vistas} se ESTACIONA con sus iframes VIVOS pero ocultos — la
  // música/video que suena ahí SIGUE SONANDO entre proyectos (pedido del
  // usuario 2026-07-02) y al volver la pestaña está intacta, sin recargar.
  // Si el entrante no tenía pool, se restauran sus pestañas persistidas.
  // Los pools mueren solo al cerrar su pestaña o recargar la página (el
  // reload lo cubre la reanudación: _restaurar + urlMedia).
  function onProjectChanged(projectId) {
    if (projectId === _pid) return;
    const saliente = (_montado && _pid != null && _estado)
      ? { estado: _estado, vistas: _vistas } : null;
    if (saliente) {
      for (const v of Object.values(saliente.vistas)) {
        // La CELDA también se oculta (no solo su contenido): las celdas de
        // todos los proyectos conviven en la misma grilla .wp-body, y una
        // celda estacionada sin [hidden] sigue pintando su fondo — si quedó
        // DESPUÉS en el DOM que las del proyecto al que volvés, las tapa con
        // un panel negro que ni el ⟳ destapa (bug "preview negro al cambiar
        // de proyecto"). _renderVista la destapa al re-adoptar el pool.
        if (v.cell) v.cell.hidden = true;
        v.iframe.hidden = true;
        // Hueco oculto → el vigilante de NativeBrowse esconde el webview solo;
        // al volver al proyecto, _renderVista lo destapa y reaparece intacto.
        if (v.hueco) v.hueco.hidden = true;
      }
    }
    const r = T().cambiarProyecto(_pools, saliente ? _pid : null, saliente, projectId);
    _pools = r.pools;
    _pid = projectId;
    _detectada = null;
    if (!_montado) return;
    if (projectId == null) { _estado = T().crearEstado(); _vistas = {}; _layout = '1'; _render(); return; }
    if (r.pool) {
      _estado = r.pool.estado;
      _vistas = r.pool.vistas;
      try { _layout = LY().normalizar(localStorage.getItem(_layoutKey(projectId))); } catch { _layout = '1'; }
      _render();
    } else {
      _vistas = {};
      _restaurar(projectId);
    }
  }

  root.WebPreview = { init, setUrl, getUrl, openTab, abrirLink, refrescarSiExiste, detectar, refresh, openExternal, onProjectChanged, _pure };

  if (typeof module !== 'undefined' && module.exports) module.exports = root.WebPreview;

})(typeof window !== 'undefined' ? window : globalThis);
