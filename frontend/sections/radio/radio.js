'use strict';
// ═══════════════════════════════════════════════════════════════════════════
// JARVIS · Radio GLOBAL (window.JarvisRadio)
// Mini-player en el header (#jw-bar-right, a la izquierda de los íconos) que
// despliega un popover (Órbita) con lo que suena, buscador de YouTube,
// relacionados, cola, estaciones y ENTRAR A UN CANAL (ver todos sus videos).
//
// La música vive en un iframe de audio colgado de <body> → suena en TODO el
// workspace, sobrevive cambios de proyecto/pestaña y se REANUDA sola tras un
// reinicio, lo más rápido posible, desde el segundo donde quedó (boot temprano).
//
// El Web Preview YA NO tiene Radio: cuando reproducís un video de YouTube ahí,
// se HANDOFF a esta Radio global (adopta la pista + arma la cola de relacionados
// y sigue). La única vez que la Radio se para es mientras se ve Twitch.
//
// Motor puro reutilizado: window.WebPreviewRadio._pure (preview-radio.js).
// ═══════════════════════════════════════════════════════════════════════════
(function (root) {
  if (root.JarvisRadio) return;

  const KEY = 'jarvis.preview.radio';
  const YT_ORIGINS = ['https://www.youtube.com', 'https://www.youtube-nocookie.com'];
  const BUSCAR = '/api/orchestrator/preview/buscar?modo=yt&q=';
  const REL = '/api/orchestrator/preview/buscar?modo=ytrel&q=';   // relacionados REALES (q = id de video)
  const MAS = '/api/orchestrator/preview/buscar?modo=ytmas&token=';   // tanda SIGUIENTE de una búsqueda

  const RY = () => (root.WebPreviewRadio && root.WebPreviewRadio._pure) || null;

  // ── Íconos (inline) ──
  const I = {
    play:  '<path d="M7 4.5v15l13-7.5z" fill="currentColor" stroke="none"/>',
    pause: '<rect x="6.5" y="5" width="4" height="14" rx="1.2" fill="currentColor" stroke="none"/><rect x="13.5" y="5" width="4" height="14" rx="1.2" fill="currentColor" stroke="none"/>',
    prev:  '<path d="M18 5.5v13L9 12z" fill="currentColor" stroke="none"/><rect x="5" y="5.5" width="2.4" height="13" rx="1" fill="currentColor" stroke="none"/>',
    next:  '<path d="M6 5.5v13L15 12z" fill="currentColor" stroke="none"/><rect x="16.6" y="5.5" width="2.4" height="13" rx="1" fill="currentColor" stroke="none"/>',
    shuffle:'<path d="M16 4h4v4M20 4l-6.5 6.5M16 20h4v-4M20 20l-5-5M4 6l4 4M4 18l8.5-8.5"/>',
    repeat:'<path d="M17 2l3 3-3 3M20 5H8a4 4 0 0 0-4 4v1M7 22l-3-3 3-3M4 19h12a4 4 0 0 0 4-4v-1"/>',
    search:'<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    chevdown:'<path d="M6 9l6 6 6-6"/>', chevup:'<path d="M6 15l6-6 6 6"/>',
    radio: '<circle cx="5" cy="17" r="2.6"/><path d="M8 17V6l11-2.4V14"/><circle cx="17.5" cy="14.5" r="2.6"/>',
    eye:   '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="2.6"/>',
    heart: '<path d="M12 20s-7-4.4-9.3-8.2C1 8.6 2.6 5 6 5c2 0 3.2 1.2 4 2.3C10.8 6.2 12 5 14 5c3.4 0 5 3.6 3.3 6.8C19 15.6 12 20 12 20z"/>',
    clock: '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.5V12l3 2"/>',
    users: '<circle cx="9" cy="8" r="3.4"/><path d="M3.5 20a5.5 5.5 0 0 1 11 0M16 5.2a3.4 3.4 0 0 1 0 6.4M20.5 20a5.5 5.5 0 0 0-4-5.3"/>',
    back:  '<path d="M15 5l-7 7 7 7"/>', list: '<path d="M8 6h12M8 12h12M8 18h12M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    note:  '<path d="M9 18V5l10-2v11"/><circle cx="6.5" cy="18" r="2.6"/><circle cx="16.5" cy="14" r="2.6"/>',
    addq:  '<path d="M4 7h11M4 12h11M4 17h7M18 13v7M14.5 16.5h7"/>',
    volume:'<path d="M4 9h3l5-4v14l-5-4H4z" fill="currentColor" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/>',
    mute:  '<path d="M4 9h3l5-4v14l-5-4H4z" fill="currentColor" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M16 9.5l5 5M21 9.5l-5 5"/>',
  };
  const svg = (n, cls) => `<svg class="jr-ico ${cls || ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I[n]}</svg>`;
  const viz = (on) => `<span class="jr-viz${on ? ' on' : ''}"><i></i><i></i><i></i><i></i></span>`;

  const ST_META = { lofi: 'estudiar', synth: 'nocturno', focus: 'flow', jazz: 'café', chill: 'relax', piano: 'calma' };

  const _esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const $ = (sel, ctx) => (ctx || document).querySelector(sel);

  // ── Estado ──
  let _state = null;          // RY estado {track, sonando, t}. track lleva {id,titulo,canal,canalId,thumb,dur,vistas,url}
  let _audio = null, _booted = false, _msgOn = false, _intent = false, _gestoOn = false;
  let _saveTs = 0, _timer = null;
  // PLAYLIST: lo que se VE es lo que SIGUE. `_pl` = {items, idx} (motor puro
  // preview-radio.js): la lista que el usuario mira —búsqueda, canal, estación
  // o relacionados— ES la cola. Tocás una fila y siguen las de abajo, EN ORDEN;
  // nada la reordena por atrás. `_plFuente` sabe de dónde traer MÁS (token de
  // continuación de la búsqueda, o relacionados de la última pista).
  let _pl = { items: [], idx: -1 };
  let _plFuente = null;             // {tipo:'busqueda'|'canal'|'estacion'|'rel', q, token}
  const _played = new Set();        // ids de video ya reproducidos
  const _playedClaves = new Set();  // claves de CANCIÓN ya reproducidas (la misma canción
                                    // vuelve con OTRO id — official/en vivo — y re-sonaba a las 2-3 pistas)
  let _twitch = 0;            // >0 = pausada por Twitch (contador de fuentes)
  let _mounted = false, _open = false, _pane = 'rel', _inChannel = false, _buscando = false;
  let _vol = 80, _muted = false, _lastVol = 80;   // volumen (0-100) + mute, persistidos
  let _repeat = false;                            // repetir el track actual al terminar (persistido)
  let _cur = 0, _dur = 0, _seeking = false;       // progreso: segundo actual / duración / arrastrando
  let _lastPct = 0;                               // último % pintado del seek (detecta saltos hacia atrás)
  let _errSeguidos = 0;      // racha de tracks NO reproducibles (freno anti-tormenta de saltos)
  let _errEnEsteLoad = false; // ya se manejó UN error de esta carga (de-dupe del doble handshake)

  function _leer() { try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch { return null; } }
  function _guardar() { try { const r = RY(); if (r) localStorage.setItem(KEY, JSON.stringify(r.serializar(_state))); } catch {} }
  function _track(r) {
    if (!r || !r.id) return null;
    return { id: r.id, titulo: r.titulo || '', canal: r.canal || '', canalId: r.canalId || null,
      thumb: r.thumb || `https://i.ytimg.com/vi/${r.id}/hqdefault.jpg`, dur: r.duracion || r.dur || '',
      vistas: r.vistas || '', url: r.url || `https://www.youtube.com/watch?v=${r.id}` };
  }

  // ── Motor de audio (iframe persistente colgado de <body>) ──
  function _asegurarAudio() {
    if (_audio && _audio.isConnected) return _audio;
    const f = document.createElement('iframe');
    f.className = 'jr-audio'; f.id = 'jarvis-radio-audio'; f.title = 'Radio (audio)';
    f.setAttribute('allow', 'autoplay; encrypted-media'); f.setAttribute('referrerpolicy', 'origin');
    document.body.appendChild(f);
    f.addEventListener('load', () => { _errEnEsteLoad = false; _saludar(); setTimeout(_saludar, 1200); setTimeout(_volApply, 1000); });
    _audio = f; _asegurarListeners();
    return f;
  }
  // Handshake con el player embebido. Además de 'listening' (infoDelivery),
  // hay que SUSCRIBIRSE a onError explícitamente: sin eso YouTube no reenvía
  // los errores de "no reproducible" y un tema bloqueado dejaba la Radio muda.
  function _saludar() {
    try {
      _audio?.contentWindow?.postMessage(JSON.stringify({ event: 'listening', id: 'jarvis-radio', channel: 'widget' }), 'https://www.youtube.com');
      _cmd('addEventListener', ['onError']);
    } catch {}
  }
  function _cmd(func, args) { try { _audio?.contentWindow?.postMessage(JSON.stringify({ event: 'command', func, args: args || [] }), 'https://www.youtube.com'); } catch {} }
  function _asegurarListeners() { if (_msgOn) return; _msgOn = true; window.addEventListener('message', _onMensaje); }

  function _onMensaje(e) {
    if (!YT_ORIGINS.includes(e.origin)) return;
    if (!_audio || e.source !== _audio.contentWindow) return;
    let d = e.data; if (typeof d === 'string') { try { d = JSON.parse(d); } catch { return; } }
    if (!d) return;
    // Track NO reproducible: 101/150 = el dueño no permite reproducirlo fuera
    // de YouTube (VEVO/sellos), 100 = borrado/privado. SOLO esos códigos son
    // fatales (2/5 pueden ser transitorios y saltaban de más). El handshake se
    // manda DOS veces a propósito → el error puede llegar duplicado: _errEnEsteLoad
    // de-dupea a UN error por carga (el duplicado tardío saltaba temas BUENOS).
    if (d.event === 'onError') {
      const code = Number(d.info);
      if (![100, 101, 150].includes(code)) return;
      if (_errEnEsteLoad) return;
      _errEnEsteLoad = true;
      _errSeguidos += 1;
      const titulo = (_state && _state.track && _state.track.titulo) || 'Ese tema';
      if (typeof toast === 'function') {
        toast(_errSeguidos <= 5
          ? `«${titulo.slice(0, 44)}» no se deja reproducir fuera de YouTube — saltando ▸`
          : 'Varios temas seguidos no se dejan reproducir — elegí otro de la lista');
      }
      if (_state) { _state = { track: _state.track, sonando: false, t: 0 }; _renderNow(); _renderMini(); }
      if (_errSeguidos <= 5) _next();
      return;
    }
    if (d.event !== 'infoDelivery' || !d.info) return;
    const r = RY(); if (!r) return;
    const info = d.info;
    if (typeof info.duration === 'number' && info.duration > 0) _dur = info.duration;
    if (typeof info.currentTime === 'number' && info.currentTime > 0) {
      _state = r.conPosicion(_state, info.currentTime);
      if (!_seeking) { _cur = info.currentTime; _renderSeek(); }   // barra de progreso viva
    }
    const ps = info.playerState;
    if (ps === 0) {                              // FIN del track → repeat o auto-avance
      _intent = false;
      if (_repeat && _state && _state.track) { _cmd('seekTo', [0, true]); _cmd('playVideo'); return; }
      if (_next()) return;                       // arrancó el siguiente
      if (_state && (_state.sonando || _state.t)) { _state = { track: _state.track, sonando: false, t: 0 }; _renderNow(); _renderMini(); }
    } else if (ps === 1 || ps === 2) {
      const son = ps === 1;
      if (son) _errSeguidos = 0;   // algo sonó de verdad → racha de errores reseteada
      if (_state && son !== _state.sonando) { _state = { track: _state.track, sonando: son, t: _state.t || 0 }; _renderNow(); _renderMini(); }
    }
    const now = Date.now(); if (now - _saveTs > 3000) { _saveTs = now; _guardar(); }
  }

  function _armarGesto() {
    if (_gestoOn) return; _gestoOn = true;
    const g = () => {
      document.removeEventListener('pointerdown', g, true); document.removeEventListener('keydown', g, true); _gestoOn = false;
      if (!_intent || !_audio || !_state || !_state.track) return;
      _intent = false; _cmd('playVideo'); if (!_muted) { _cmd('unMute'); _cmd('setVolume', [_vol]); }
    };
    document.addEventListener('pointerdown', g, true); document.addEventListener('keydown', g, true);
  }
  function _guardadoPeriodico() {
    if (_timer) return;
    _timer = setInterval(() => { if (_state && _state.track) _guardar(); }, 5000);
    window.addEventListener('pagehide', () => { if (_state && _state.track) _guardar(); });
  }

  // ── Reproducción ──
  function _src(track, opts) { const r = RY(); return r ? r.urlEmbed(track.id, Object.assign({ origin: location.origin }, opts)) : ''; }

  // Arranca `track`. NO decide qué sigue: eso lo dice la playlist (`_pl`), que
  // arma quien reproduce (_reproducirDeLista / _reproducirSuelto). Lo único que
  // hace acá es RELLENAR por abajo si quedan pocas por delante, para que la
  // música nunca se corte al llegar al final de lo que se ve.
  function play(track, { auto = false } = {}) {
    const r = RY(); if (!r || !track || !track.id) return;
    _state = r.elegir(_state, track); _booted = true;
    _played.add(track.id);   // marcá como reproducida (para no volver a encolarla)
    const kc = _clave(track); if (kc) _playedClaves.add(kc);   // ...ni a la misma canción con otro id
    _cur = 0; _dur = _parseDur(track.dur); _seeking = false; _renderSeek();   // reset del progreso
    _asegurarAudio().src = _src(track, { autoplay: !_twitch, start: 0 });
    if (_twitch) _cmd('pauseVideo');
    _guardadoPeriodico(); _guardar(); _renderNow(); _renderMini(); _marcarActiva(!!auto);
    if (r.porDelante(_pl) < 4) _rellenarCola();
  }

  // Reproducir la fila `i` de una LISTA visible: esa lista pasa a ser la cola
  // (lo que sigue es lo que se ve, abajo, en orden).
  function _reproducirDeLista(items, i, fuente) {
    const r = RY(); if (!r) return;
    _pl = r.crearLista(items, i);
    _plFuente = fuente ? Object.assign({}, fuente) : { tipo: 'rel' };
    const t = r.pistaEn(_pl, _pl.idx); if (t) play(t);
  }
  // Reproducir algo SUELTO (handoff del preview, reanudación tras reinicio):
  // no hay lista todavía → la playlist nace con esa pista y se llena con sus
  // relacionados reales.
  function _reproducirSuelto(track) {
    const r = RY(); if (!r || !track) return;
    _pl = r.crearLista([track], 0);
    _plFuente = { tipo: 'rel' };
    play(track);
  }
  // Siembra la playlist con una pista que YA está sonando (reanudación tras un
  // reinicio, cued desde storage): sin tocar el player, la cola nace con ella y
  // se llena con sus relacionados.
  function _sembrarPlaylist(track) {
    const r = RY(); if (!r || !track || !track.id) return;
    _pl = r.crearLista([track], 0);
    _plFuente = { tipo: 'rel' };
    _rellenarCola();
  }
  // Salta a un índice de la playlist actual (avance, retroceso, click en la cola).
  function _irA(i, auto) {
    const r = RY(); if (!r) return false;
    const t = r.pistaEn(_pl, i); if (!t) return false;
    _pl = r.saltarA(_pl, i);
    play(t, { auto: !!auto });
    return true;
  }

  // Handoff desde el Web Preview: adopta lo que se puso a sonar ahí. NO abre el
  // popover (el usuario lo abre cuando quiere) — solo pasa a sonar en la Radio.
  function adopt(raw) { const t = _track(raw); if (t) { if (!_mounted) _montar(); _reproducirSuelto(t); } }

  function _alternar() {
    const r = RY(); if (!r || !_state || !_state.track) return;
    _intent = false; _state = r.alternar(_state);
    _cmd(_state.sonando ? 'playVideo' : 'pauseVideo');
    _guardadoPeriodico(); _guardar(); _renderNow(); _renderMini();
  }
  // Siguiente = la de ABAJO en la lista que se ve. Si se acabó, pide
  // continuaciones y arranca la primera que llegue (devuelve true: hay algo en
  // camino, no hay que dar la música por terminada).
  function _next() {
    const r = RY(); if (!r) return false;
    const i = r.siguienteIdx(_pl);
    if (i >= 0) return _irA(i, true);
    _rellenarCola().then(() => {
      const j = RY() && RY().siguienteIdx(_pl);
      if (j >= 0) _irA(j, true);
      else if (_state && (_state.sonando || _state.t)) {
        _state = { track: _state.track, sonando: false, t: 0 }; _renderNow(); _renderMini();
      }
    });
    return true;
  }
  // Anterior REAL: vuelve a la de arriba en la lista. Con el tema ya empezado
  // (>5s) el ⏮ rebobina primero, como cualquier reproductor.
  function _prev() {
    const r = RY(); if (!r || !_state || !_state.track) return;
    const i = r.anteriorIdx(_pl);
    if (_cur > 5 || i < 0) { _cmd('seekTo', [0, true]); _cmd('playVideo'); _cur = 0; _renderSeek(); return; }
    _irA(i, false);
  }

  // ── Twitch: la única cosa que para la Radio ──
  function pauseForTwitch() { _twitch++; if (_twitch === 1 && _state && _state.track && _state.sonando) { _cmd('pauseVideo'); const m = $('#jarvis-radio-mini'); if (m) m.classList.add('twitch'); } }
  function resumeAfterTwitch() { if (_twitch > 0) _twitch--; if (_twitch === 0) { const m = $('#jarvis-radio-mini'); if (m) m.classList.remove('twitch'); if (_state && _state.track && _state.sonando) _cmd('playVideo'); } }

  // ── Fetch al backend ──
  const _clave = (t) => { const r = RY(); return (r && r.claveCancion && t) ? r.claveCancion(t.titulo, t.canal) : ''; };

  // Una BÚSQUEDA (o el listado de un canal/estación) es una lista con fuente:
  // guarda la consulta y el `token` de continuación de YouTube para poder traer
  // la tanda siguiente cuando el usuario toca los dots (o cuando la música
  // llega al final de lo que se ve).
  async function _buscar(q, into) {
    q = (q || '').trim();
    const box = $(into); if (!box) return;
    if (!q) {   // input vacío → volver a mostrar la playlist que está sonando
      _buscando = false;
      if (_pl.items.length) _renderPlaylistEn(box);
      else { box.innerHTML = '<div class="jr-hint">Buscá música o elegí una estación.</div>'; box._items = []; box._fuente = null; }
      return;
    }
    _buscando = true;   // el pane muestra resultados de búsqueda (no la playlist)
    box.innerHTML = '<div class="jr-hint">Buscando…</div>';
    const q0 = q;
    try {
      const res = await fetch(BUSCAR + encodeURIComponent(q));
      const data = await res.json();
      const input = $('#jr-q'); if (input && input.value.trim() !== q0) return;   // el usuario siguió tipeando
      _renderFilas(box, (data.resultados || []).map(_track).filter(Boolean), data.error,
        { tipo: 'busqueda', q: q0, token: data.token || null });
    } catch { _renderFilas(box, [], 'No se pudo buscar'); }
  }

  // ── Continuaciones: de dónde salen las pistas que se suman por ABAJO ────────
  // Dos vías, según de dónde vino la lista:
  //   · búsqueda/canal/estación → la tanda SIGUIENTE de esa misma consulta
  //     (modo ytmas + token de continuación de YouTube). Más de lo que buscaste,
  //     sin repetir lo que ya se ve.
  //   · relacionados (o búsqueda agotada) → los relacionados REALES de la última
  //     pista de la lista (ytrel), con fallback a buscar por canal/título.
  // Devuelve pistas ya normalizadas; el dedupe fino lo hace `anexar` (por id y
  // por CANCIÓN) contra la lista destino.
  async function _traerMas(fuente, ultima) {
    const nuevas = [];
    if (fuente && fuente.token) {
      try {
        const data = await (await fetch(MAS + encodeURIComponent(fuente.token))).json();
        fuente.token = data.token || null;   // token de la tanda que sigue (o fin)
        for (const r of (data.resultados || [])) { const t = _track(r); if (t) nuevas.push(t); }
      } catch { fuente.token = null; }
      if (nuevas.length) return nuevas;
    }
    if (!ultima || !ultima.id) return nuevas;
    let data = null;
    try { data = await (await fetch(REL + encodeURIComponent(ultima.id))).json(); } catch { data = null; }
    for (const r of (data && data.resultados) || []) {
      const t = _track(r); if (!t || _played.has(t.id)) continue;
      const k = _clave(t); if (k && _playedClaves.has(k)) continue;
      nuevas.push(t);
    }
    if (nuevas.length) return nuevas;
    const q = (ultima.canal || ultima.titulo || '').trim(); if (!q) return nuevas;
    try {
      data = await (await fetch(BUSCAR + encodeURIComponent(q))).json();
      for (const r of (data.resultados || [])) {
        const t = _track(r); if (!t || _played.has(t.id)) continue;
        const k = _clave(t); if (k && _playedClaves.has(k)) continue;
        nuevas.push(t);
      }
    } catch {}
    return nuevas;
  }

  // Rellena la PLAYLIST por abajo (sin tocar el orden ni el índice). Devuelve
  // cuántas entraron. Una sola en vuelo: dos finales seguidos duplicaban filas.
  let _rellenando = null;
  function _rellenarCola() {
    if (_rellenando) return _rellenando;
    const r = RY(); if (!r || !_pl.items.length) return Promise.resolve(0);
    _rellenando = (async () => {
      const antes = _pl.items.length;
      try {
        if (!_plFuente) _plFuente = { tipo: 'rel' };
        const nuevas = await _traerMas(_plFuente, _pl.items[_pl.items.length - 1]);
        if (nuevas.length) {
          _pl = r.anexar(_pl, nuevas, r.claveCancion);
          _repintarPlaylist();
        }
      } catch {}
      const sumadas = _pl.items.length - antes;
      _rellenando = null;
      return sumadas;
    })();
    return _rellenando;
  }

  // Canal: sus videos vía búsqueda por el nombre del canal (mismo endpoint) —
  // esa lista también es una cola con continuación (token).
  async function _cargarCanal(track) {
    const list = $('#jr-cv-list'); if (!list) return;
    list.innerHTML = '<div class="jr-hint">Cargando el canal…</div>'; list._items = []; list._fuente = null;
    const q = (track.canal || track.titulo || '').trim();
    try {
      const res = await fetch(BUSCAR + encodeURIComponent(q));
      const data = await res.json();
      _renderFilas(list, (data.resultados || []).map(_track).filter(Boolean),
        data.error || 'No se pudieron traer los videos del canal',
        { tipo: 'canal', q, token: data.token || null });
    } catch { _renderFilas(list, [], 'No se pudo cargar el canal'); }
  }

  // ── Volumen: control por la API del iframe de YouTube (setVolume/mute), con
  // persistencia y reaplicación al reanudar (load del iframe + gesto de autoplay).
  const VOLKEY = 'jarvis.preview.radio.vol';
  function _volLoad() {
    try { const d = JSON.parse(localStorage.getItem(VOLKEY) || 'null');
      if (d) { _vol = Math.max(0, Math.min(100, +d.v || 0)); _muted = !!d.m; _lastVol = _vol || 60; _repeat = !!d.r; } } catch {}
  }
  function _volSave() { try { localStorage.setItem(VOLKEY, JSON.stringify({ v: _vol, m: _muted, r: _repeat })); } catch {} }
  function _volIcon() { return (_muted || _vol === 0) ? 'mute' : 'volume'; }
  function _volApply() { _cmd('setVolume', [_vol]); _muted ? _cmd('mute') : _cmd('unMute'); }
  function _volIconUpd() {
    const b = $('#jr-vol-btn'); if (b) { b.innerHTML = svg(_volIcon()); b.title = (_muted || _vol === 0) ? 'Activar sonido' : 'Silenciar'; }
  }
  function _volSliderUpd() {
    const v = _muted ? 0 : _vol;
    const fill = $('#jr-vol-fill'); if (fill) fill.style.width = v + '%';
    const el = $('#jr-vol-el'); if (el) el.setAttribute('aria-valuenow', String(v));
    const pct = $('#jr-vol-pct'); if (pct) pct.textContent = v;
  }
  function _volToggleMute() {
    if (_muted || _vol === 0) { _muted = false; if (_vol === 0) _vol = _lastVol || 60; }
    else { _muted = true; _lastVol = _vol; }
    _volApply(); _volSave(); _volIconUpd(); _volSliderUpd();
  }

  // ── Slider elástico (port vanilla de ElasticSlider/React Bits, sin libs) ──
  // Arrastrar más allá de un borde estira la pista como goma: el exceso pasa por
  // una sigmoide (rinde cada vez menos, tope VOL_OV px) y empuja el ícono/% de
  // ese lado; al soltar, un resorte subamortiguado (rAF) la devuelve con una
  // oscilación corta. Con prefers-reduced-motion la goma se apaga entera.
  const VOL_OV = 26;                 // estiramiento máximo en px (sigmoide)
  let _ov = 0, _ovSide = 0, _ovRaf = 0;   // overflow actual (px, con signo) / lado / rAF del resorte
  const _sinMotion = () => !!(root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches);
  function _ovDecay(v) { return (2 * (1 / (1 + Math.exp(-(v / VOL_OV))) - 0.5)) * VOL_OV; }   // sigmoide impar
  function _ovPaint() {
    const el = $('#jr-vol-el'), st = $('#jr-vol-stretch'); if (!el || !st) return;
    const btn = $('#jr-vol-btn'), pct = $('#jr-vol-pct');
    const a = Math.abs(_ov);
    if (a < 0.15) { st.style.transform = ''; if (btn) btn.style.transform = ''; if (pct) pct.style.transform = ''; return; }
    const w = el.clientWidth || 1;
    st.style.transformOrigin = _ovSide < 0 ? '100% 50%' : '0% 50%';
    st.style.transform = `scaleX(${(1 + a / w).toFixed(4)}) scaleY(${Math.max(0.78, 1 - (a / VOL_OV) * 0.2).toFixed(3)})`;
    if (btn) btn.style.transform = _ovSide < 0 ? `translateX(${(_ov * 0.6).toFixed(1)}px) scale(${(1 + (a / VOL_OV) * 0.12).toFixed(3)})` : '';
    if (pct) pct.style.transform = _ovSide > 0 ? `translateX(${(_ov * 0.6).toFixed(1)}px)` : '';
  }
  function _ovSpring() {
    cancelAnimationFrame(_ovRaf);
    if (_sinMotion() || Math.abs(_ov) < 0.15) { _ov = 0; _ovSide = 0; _ovPaint(); return; }
    let x = _ov, v = 0, last = performance.now();
    const paso = (now) => {
      const dt = Math.min(32, now - last) / 1000; last = now;
      v += (-320 * x - 17 * v) * dt; x += v * dt;   // resorte k=320 c=17 → ζ≈.48, 1-2 rebotes cortos
      if (Math.abs(x) < 0.15 && Math.abs(v) < 2) { _ov = 0; _ovSide = 0; _ovPaint(); return; }
      _ov = x; _ovPaint(); _ovRaf = requestAnimationFrame(paso);
    };
    _ovRaf = requestAnimationFrame(paso);
  }
  function _volSet(v) {
    _vol = Math.max(0, Math.min(100, Math.round(v))); if (_vol > 0) _muted = false;
    _volApply(); _volSave(); _volIconUpd(); _volSliderUpd();
  }
  function _volInitUI() {
    const el = $('#jr-vol-el'); if (!el) return;
    _volSliderUpd(); _volIconUpd();
    let drag = false;
    const mover = (e) => {
      const r = el.getBoundingClientRect(); if (!r.width) return;
      _volSet(((e.clientX - r.left) / r.width) * 100);
      let raw = 0;
      if (e.clientX < r.left) raw = e.clientX - r.left;
      else if (e.clientX > r.right) raw = e.clientX - r.right;
      _ovSide = raw < 0 ? -1 : (raw > 0 ? 1 : _ovSide);
      _ov = _sinMotion() ? 0 : _ovDecay(raw);
      _ovPaint();
    };
    el.addEventListener('pointerdown', (e) => {
      drag = true; el.classList.add('drag'); cancelAnimationFrame(_ovRaf);
      try { el.setPointerCapture(e.pointerId); } catch {}
      mover(e); e.preventDefault();
    });
    el.addEventListener('pointermove', (e) => { if (drag) mover(e); });
    const soltar = () => { if (!drag) return; drag = false; el.classList.remove('drag'); _ovSpring(); };
    el.addEventListener('pointerup', soltar);
    el.addEventListener('pointercancel', soltar);
    el.addEventListener('lostpointercapture', soltar);
    el.addEventListener('keydown', (e) => {
      let v = null;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') v = _vol - 5;
      else if (e.key === 'ArrowRight' || e.key === 'ArrowUp') v = _vol + 5;
      else if (e.key === 'Home') v = 0; else if (e.key === 'End') v = 100;
      if (v === null) return;
      e.preventDefault(); _volSet(v);
    });
    const b = $('#jr-vol-btn'); if (b) b.addEventListener('click', _volToggleMute);
  }

  // ── Barra de progreso (seek): tiempo transcurrido/total + adelantar en videos largos ──
  function _fmt(s) {
    s = Math.max(0, Math.floor(s || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
    const p = (n) => (n < 10 ? '0' + n : '' + n);
    return h > 0 ? h + ':' + p(m) + ':' + p(ss) : m + ':' + p(ss);
  }
  function _parseDur(str) {
    if (!str || /live|vivo/i.test(str)) return 0;
    const parts = String(str).split(':').map((x) => parseInt(x, 10));
    if (!parts.length || parts.some((n) => isNaN(n))) return 0;
    return parts.reduce((a, n) => a * 60 + n, 0);
  }
  function _renderSeek() {
    const fill = $('#jr-seek-fill'); if (!fill) return;
    const knob = $('#jr-seek-knob'), cur = $('#jr-seek-cur'), tot = $('#jr-seek-tot'), bar = $('#jr-seek-bar');
    const live = !(_dur > 0);                                   // live / duración desconocida
    const pct = live ? 100 : Math.max(0, Math.min(100, (_cur / _dur) * 100));
    // El fill se desliza (transition linear .5s) entre updates del player; un
    // salto hacia ATRÁS (track nuevo, seek) se pinta instantáneo con .snap para
    // que la barra no "rebobine" animada.
    if (bar && !_seeking && pct < _lastPct - 2) {
      bar.classList.add('snap');
      requestAnimationFrame(() => requestAnimationFrame(() => bar.classList.remove('snap')));
    }
    _lastPct = pct;
    fill.style.width = pct + '%';
    if (knob) knob.style.left = pct + '%';
    if (cur) cur.textContent = live ? 'EN VIVO' : _fmt(_cur);
    if (tot) tot.textContent = live ? '' : _fmt(_dur);
    if (bar) bar.classList.toggle('live', live);
  }
  function _seekAt(clientX) {
    const bar = $('#jr-seek-bar'); if (!bar || !(_dur > 0)) return null;
    const r = bar.getBoundingClientRect(); if (!r.width) return null;
    return Math.max(0, Math.min(1, (clientX - r.left) / r.width)) * _dur;
  }
  function _seekInitUI() {
    const bar = $('#jr-seek-bar'); if (!bar) return;
    const bub = $('#jr-seek-bub');
    const burbuja = (e) => {                       // burbuja de tiempo bajo el cursor (hover Y arrastre)
      if (!bub) return;
      const t = _seekAt(e.clientX); if (t == null) { bub.classList.remove('on'); return; }
      const r = bar.getBoundingClientRect();
      bub.style.left = (Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * 100) + '%';
      bub.textContent = _fmt(t); bub.classList.add('on');
    };
    const preview = (e) => { const t = _seekAt(e.clientX); if (t == null) return; _cur = t; _renderSeek(); };
    bar.addEventListener('pointerdown', (e) => {
      if (!(_dur > 0)) return;
      _seeking = true; bar.classList.add('seeking');
      try { bar.setPointerCapture(e.pointerId); } catch {} preview(e); burbuja(e); e.preventDefault();
    });
    bar.addEventListener('pointermove', (e) => { if (_seeking) preview(e); burbuja(e); });
    bar.addEventListener('pointerleave', () => { if (!_seeking && bub) bub.classList.remove('on'); });
    const soltar = (e) => {
      if (!_seeking) return; _seeking = false; bar.classList.remove('seeking');
      const t = _seekAt(e.clientX); if (t != null) { _cmd('seekTo', [Math.floor(t), true]); _cur = t; _renderSeek(); }
      if (bub && !bar.matches(':hover')) bub.classList.remove('on');
    };
    bar.addEventListener('pointerup', soltar);
    bar.addEventListener('pointercancel', () => {   // cancel NO commitea (clientX puede ser basura)
      _seeking = false; bar.classList.remove('seeking'); if (bub) bub.classList.remove('on');
    });
  }

  // ── i18n (ES⇆EN): registrá las frases ANTES de montar el UI para que el
  // observer de JarvisI18n las traduzca solo al re-render y al cambiar de idioma.
  let _i18nDone = false;
  function _i18n() {
    if (_i18nDone || !(root.JarvisI18n && root.JarvisI18n.agregar)) return;
    _i18nDone = true;
    root.JarvisI18n.agregar({
      'EN VIVO': 'LIVE',
      'Reproduciendo': 'Now playing',
      'Ver canal': 'View channel', 'Ver el canal': 'View channel',
      'Relacionados': 'Related', 'Cola': 'Queue', 'Estaciones': 'Stations',
      'Reproducir': 'Play', 'Reproducir / pausar': 'Play / pause',
      'Minimizar': 'Minimize', 'Cerrar': 'Close', 'Aleatorio': 'Shuffle', 'Mezclar la cola': 'Shuffle the queue',
      'Reiniciar': 'Restart', 'Siguiente': 'Next', 'Repetir': 'Repeat',
      'Volver': 'Back', 'Agregar a la cola': 'Add to queue',
      'Silenciar': 'Mute', 'Activar sonido': 'Unmute', 'Volumen': 'Volume', 'Progreso': 'Progress',
      'Buscá música o pegá un link de YouTube…': 'Search for music or paste a YouTube link…',
      'Buscá música o elegí una estación.': 'Search for music or pick a station.',
      'Nada sonando todavía.': 'Nothing playing yet.',
      'Poné algo a sonar y te muestro relacionados.': "Play something and I'll show you related tracks.",
      'Poné algo a sonar': 'Play something', 'en el workspace': 'in the workspace',
      'La cola está vacía. Se llena sola con los relacionados de lo que suena.': "The queue is empty — it fills up with what's related to what's playing.",
      'Buscando…': 'Searching…', 'Sin resultados': 'No results', 'No se pudo buscar': "Couldn't search",
      'Cargando el canal…': 'Loading channel…',
      'No se pudieron traer los videos del canal': "Couldn't load the channel's videos",
      'No se pudo cargar el canal': "Couldn't load the channel",
      'Sintonizando…': 'Tuning in…', 'No se pudo sintonizar': "Couldn't tune in",
      'Más música relacionada': 'More related music', 'Más del canal': 'More from this channel',
      'Más como': 'More like',
      'No hay más por ahora': 'Nothing more for now',
      'YouTube · videos del canal': 'YouTube · channel videos', 'Canal': 'Channel', 'vistas': 'views',
      'estudiar': 'study', 'nocturno': 'night', 'café': 'coffee', 'calma': 'calm',
    });
  }

  // ═══════════════ UI ═══════════════
  function _montar() {
    if (_mounted) return;
    const barRight = $('#jw-bar .jw-bar-right') || $('.jw-bar-right');
    if (!barRight) return;   // el header todavía no está; se reintenta
    _mounted = true;
    _i18n(); _volLoad();

    // Mini-player (a la IZQUIERDA de los íconos → primer hijo de .jw-bar-right)
    const mini = document.createElement('div');
    mini.className = 'jr-mini'; mini.id = 'jarvis-radio-mini'; mini.title = 'Radio';
    mini.setAttribute('role', 'button'); mini.tabIndex = 0;
    barRight.insertBefore(mini, barRight.firstChild);

    // Popover + catcher (colgados de <body>)
    const pop = document.createElement('div'); pop.className = 'jr-pop'; pop.id = 'jarvis-radio-pop';
    pop.innerHTML =
      `<div class="jr-card"><div class="jr-inner">
        <div class="jr-head"><span class="jr-mark">${svg('radio')}</span>
          <span class="jr-title">Radio <span class="jr-livewrap" id="jr-live" hidden><span class="jr-eq on"><i></i><i></i><i></i></span> EN VIVO</span></span>
          <button class="jr-ibtn" id="jr-min" title="Minimizar">${svg('chevup')}</button>
          <button class="jr-ibtn" id="jr-close" title="Cerrar">${svg('close')}</button></div>
        <label class="jr-search"><span>${svg('search')}</span><input id="jr-q" placeholder="Buscá música o pegá un link de YouTube…" spellcheck="false" autocomplete="off"></label>
        <div class="jr-now" id="jr-now"></div>
        <div class="jr-transport" id="jr-transport"></div>
        <div class="jr-seek" id="jr-seek">
          <span class="jr-seek-t" id="jr-seek-cur">0:00</span>
          <div class="jr-seek-bar" id="jr-seek-bar" role="slider" aria-label="Progreso" tabindex="0"><div class="jr-seek-fill" id="jr-seek-fill"></div><div class="jr-seek-knob" id="jr-seek-knob"></div><span class="jr-seek-bub" id="jr-seek-bub">0:00</span></div>
          <span class="jr-seek-t r" id="jr-seek-tot">0:00</span>
        </div>
        <div class="jr-vol" id="jr-vol">
          <span class="jr-vol-l"><button class="jr-vol-btn" id="jr-vol-btn" type="button" title="Silenciar" aria-label="Silenciar">${svg('volume')}</button></span>
          <div class="jr-vol-el" id="jr-vol-el" role="slider" aria-label="Volumen" aria-valuemin="0" aria-valuemax="100" aria-valuenow="80" tabindex="0">
            <div class="jr-vol-stretch" id="jr-vol-stretch"><div class="jr-vol-track"><div class="jr-vol-fill" id="jr-vol-fill"></div></div></div>
          </div>
          <span class="jr-vol-pct" id="jr-vol-pct">80</span>
        </div>
        <div id="jr-browse">
          <div class="jr-seg" id="jr-seg"><button class="on" data-p="rel">Relacionados</button><button data-p="q">Cola</button><button data-p="st">Estaciones</button></div>
          <div class="jr-scroll">
            <div class="jr-pane" id="jr-pane-rel"><div class="jr-hint">Poné algo a sonar y te muestro relacionados.</div></div>
            <div class="jr-pane" id="jr-pane-q" hidden></div>
            <div class="jr-pane jr-stations" id="jr-pane-st" hidden></div>
          </div>
        </div>
        <div class="jr-channel" id="jr-channel" hidden></div>
      </div></div>`;
    document.body.appendChild(pop);
    const catcher = document.createElement('div'); catcher.className = 'jr-catch'; catcher.id = 'jarvis-radio-catch';
    document.body.appendChild(catcher);

    // Listeners
    mini.addEventListener('click', (e) => { if (e.target.closest('#jr-mini-play')) return; _toggle(); });
    mini.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); _toggle(); } });
    $('#jr-min').addEventListener('click', () => _toggle(false));
    $('#jr-close').addEventListener('click', () => _toggle(false));
    catcher.addEventListener('click', () => _toggle(false));
    const q = $('#jr-q'); let deb = null;
    q.addEventListener('input', () => { clearTimeout(deb); deb = setTimeout(() => _buscar(q.value, '#jr-pane-rel'), 350); if (q.value.trim()) _setPane('rel'); });
    q.addEventListener('keydown', (e) => { if (e.key === 'Enter') { clearTimeout(deb); _buscar(q.value, '#jr-pane-rel'); _setPane('rel'); } });
    $('#jr-seg').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) _setPane(b.dataset.p); });
    $('#jr-pane-rel').addEventListener('click', (e) => {
      const rel = $('#jr-pane-rel'); _clicFila(e, () => (rel._items || []), rel);
    });
    $('#jr-pane-q').addEventListener('click', _clicQueue);
    $('#jr-pane-st').addEventListener('click', (e) => { const s = e.target.closest('.jr-station'); if (s) _estacion(s.dataset.q); });
    $('#jr-now').addEventListener('click', (e) => { if (e.target.closest('#jr-chanlink')) { if (_state && _state.track) _abrirCanal(_state.track); } });
    $('#jr-transport').addEventListener('click', (e) => {
      const b = e.target.closest('[data-a]'); if (!b) return;
      const a = b.dataset.a;
      if (a === 'play') _alternar(); else if (a === 'next') { if (!_next()) _prev0(); } else if (a === 'prev') _prev();
      else if (a === 'shuffle') _shuffle(b);
      else if (a === 'repeat') { _repeat = !_repeat; _volSave(); b.classList.toggle('on', _repeat); }
    });

    _volInitUI(); _seekInitUI();
    _renderEstaciones();
    _renderNow(); _renderMini(); _renderPaneChrome();

    // Estado inicial: si el boot no lo levantó, restaurar cued desde storage.
    if (!_state) {
      const r = RY(); _state = r ? r.deserializar(_leer()) : { track: null, sonando: false, t: 0 };
      if (_state.track) {
        _asegurarAudio().src = _src(_state.track, { autoplay: false, start: _state.t });
        _guardadoPeriodico();
        _sembrarPlaylist(_state.track);   // la cola arranca con lo que quedó cued
      }
      _renderNow(); _renderMini();
    }
  }
  function _prev0() { /* next sin cola: nada */ }

  function _toggle(force) {
    _open = typeof force === 'boolean' ? force : !_open;
    $('#jarvis-radio-pop').classList.toggle('on', _open);
    $('#jarvis-radio-catch').classList.toggle('on', _open);
    $('#jarvis-radio-mini').classList.toggle('abierto', _open);
    $('#jr-mini-chev') && ($('#jr-mini-chev').innerHTML = svg(_open ? 'chevup' : 'chevdown'));
    if (_open) {
      _alinear(); requestAnimationFrame(_segThumb);
      const rel = $('#jr-pane-rel');   // al abrir, Relacionados muestra lo que viene
      if (rel && _pane === 'rel' && !_buscando && !rel._esPl && _pl.items.length) _renderPlaylistEn(rel);
      const q = $('#jr-q'); if (q) setTimeout(() => q.focus(), 30);
    }
  }
  function open() { if (!_mounted) _montar(); _toggle(true); }
  function close() { _toggle(false); }
  function _alinear() {
    const m = $('#jarvis-radio-mini'), pop = $('#jarvis-radio-pop'); if (!m || !pop) return;
    const r = m.getBoundingClientRect(), vw = document.documentElement.clientWidth;
    const cardRight = Math.max(10, vw - r.right);
    pop.style.right = cardRight + 'px';
    const caret = Math.max(16, Math.min((vw - (r.left + r.width / 2)) - cardRight, 360));
    const card = pop.querySelector('.jr-card'); if (card) card.style.setProperty('--jr-caret', caret + 'px');
  }
  window.addEventListener('resize', () => { if (_open) _alinear(); });

  function _setPane(p) {
    _pane = p; _inChannel = false;
    $('#jr-channel').hidden = true; $('#jr-browse').hidden = false;
    for (const b of $('#jr-seg').querySelectorAll('button')) b.classList.toggle('on', b.dataset.p === p);
    _segThumb();
    $('#jr-pane-rel').hidden = p !== 'rel'; $('#jr-pane-q').hidden = p !== 'q'; $('#jr-pane-st').hidden = p !== 'st';
    if (p === 'q') _renderQueue();
    // Relacionados = la playlist que está sonando (salvo que el pane esté
    // mostrando una búsqueda: esa lista se respeta hasta que la vacíen).
    const rel = $('#jr-pane-rel');
    if (p === 'rel' && _pl.items.length && !_buscando && !(rel && rel._esPl)) _renderPlaylistEn(rel);
  }

  // Thumb deslizante del segmented: mide la pestaña activa y publica --segx/--segw.
  // Solo mide con el popover visible (cerrado, offsetWidth da 0 y el thumb se esconde).
  function _segThumb() {
    const seg = $('#jr-seg'); if (!seg) return;
    const b = seg.querySelector('button.on');
    if (!b || !b.offsetWidth) { seg.classList.remove('thumbed'); return; }
    seg.style.setProperty('--segx', b.offsetLeft + 'px');
    seg.style.setProperty('--segw', b.offsetWidth + 'px');
    seg.classList.add('thumbed');
  }

  // Ícono de música del mini-player (ondas de radio, como el mockup). Reemplaza
  // a la carátula: el mini muestra SIEMPRE el ícono; al sonar, las ondas hacen
  // el fade escalonado + el core "respira" (animación del mockup). La carátula
  // del track sigue viva en el popover grande (_renderNow).
  const _rdIco = () =>
    '<svg class="jr-rd" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" aria-hidden="true">'
    + '<circle class="jr-rd-core" cx="12" cy="12" r="2.1" fill="currentColor" stroke="none"/>'
    + '<path class="jr-rd-wv jr-rd-w1" d="M8.6 8.6a4.8 4.8 0 0 0 0 6.8M15.4 8.6a4.8 4.8 0 0 1 0 6.8"/>'
    + '<path class="jr-rd-wv jr-rd-w2" d="M6 6a8.5 8.5 0 0 0 0 12M18 6a8.5 8.5 0 0 1 0 12"/>'
    + '</svg>';

  // ── Render: mini ──
  // Solo un ÍCONO en la barra (como el mockup): las ondas de radio, que animan
  // al sonar. Sin cuadro/título/play inline. Click en el ícono → abre la radio
  // (el popover con todo: now-playing, transport, búsqueda, cola). El título del
  // track vive en el tooltip para el vistazo rápido.
  function _renderMini() {
    const m = $('#jarvis-radio-mini'); if (!m) return;
    const t = _state && _state.track, son = _state && _state.sonando;
    m.classList.toggle('playing', !!son);
    m.title = t ? `${t.titulo}${t.canal ? ' — ' + t.canal : ''}` : 'Radio';
    m.setAttribute('aria-label', t ? `Radio: ${t.titulo}` : 'Radio');
    m.innerHTML = _rdIco();
  }

  // ── Render: now-playing + transport ──
  function _renderNow() {
    const now = $('#jr-now'); if (!now) return;
    const t = _state && _state.track, son = _state && _state.sonando;
    const live = $('#jr-live'); if (live) live.hidden = !(t && son);
    if (!t) { now.classList.remove('playing'); now.innerHTML = '<div class="jr-hint" style="padding:14px 4px">Nada sonando todavía.</div>'; _renderTransport(); return; }
    now.innerHTML =
      `<span class="jr-art">${t.thumb ? `<img src="${_esc(t.thumb)}" alt="" onerror="this.remove()">` : ''}${viz(!!son)}</span>`
      + `<span class="jr-ninfo"><span class="jr-eyebrow">Reproduciendo</span>`
      + `<span class="jr-ntitle">${_esc(t.titulo)}</span>`
      + `<button class="jr-chanlink" id="jr-chanlink" title="Ver el canal"><span class="jr-av"></span><span>${_esc(t.canal || 'YouTube')}</span><span class="jr-vercanal">Ver canal</span></button>`
      + `<span class="jr-chips">`
      +   (t.vistas ? `<span class="jr-chip">${svg('eye')}<b>${_esc(t.vistas)}</b></span>` : `<span class="jr-chip">${svg('eye')}<b>YouTube</b></span>`)
      +   (t.dur ? `<span class="jr-chip">${svg('clock')}<b>${_esc(t.dur)}</b></span>` : '')
      + `</span></span>`;
    now.classList.toggle('playing', !!son);   // pulso del glow de la carátula al ritmo
    _renderTransport();
  }
  function chip(ic, val) { return `<span class="jr-chip">${svg(ic)}<b>${_esc(val)}</b></span>`; }

  // Waveform de música: 28 barras que "bailan" con fase orgánica (senoidal, sin
  // random → estable) mientras suena; en pausa se aquietan a una línea baja.
  // Simulada: el iframe de YouTube es cross-origin y no da acceso a Web Audio.
  function _waveHTML(on) {
    let bars = '';
    for (let i = 0; i < 28; i++) {
      const delay = -((i * 0.055) + (Math.sin(i * 0.65) * 0.14 + 0.16));
      const dur = 1.0 + (i % 6) * 0.14;
      bars += `<i style="animation-delay:${delay.toFixed(2)}s;animation-duration:${dur.toFixed(2)}s"></i>`;
    }
    return `<div class="jr-wave${on ? ' on' : ''}" aria-hidden="true">${bars}</div>`;
  }

  // Mezcla la cola (Fisher-Yates) — acción real del botón shuffle: el orden
  // nuevo se VE al instante en Relacionados/Cola, más un pop en el botón.
  function _shuffle(btn) {
    const r = RY();
    if (r && r.porDelante(_pl) > 1) {
      _pl = r.mezclarCola(_pl);
      // La lista visible ES la cola: re-pintarla entera para que se VEA el
      // orden nuevo (lo ya sonado y la pista actual se quedan donde están).
      for (const box of [$('#jr-pane-rel'), $('#jr-cv-list')]) if (box && box._esPl) _renderPlaylistEn(box);
      if (_pane === 'q') _renderQueue();
    }
    if (btn) { btn.classList.remove('pop'); void btn.offsetWidth; btn.classList.add('pop'); }
  }

  function _renderTransport() {
    const tp = $('#jr-transport'); if (!tp) return;
    const son = _state && _state.sonando;
    tp.innerHTML =
      _waveHTML(!!son)
      + `<div class="jr-tp"><button class="jr-tp-btn sm" data-a="shuffle" title="Mezclar la cola">${svg('shuffle')}</button>`
      + `<button class="jr-tp-btn" data-a="prev" title="Reiniciar">${svg('prev')}</button>`
      + `<button class="jr-tp-play" data-a="play" title="Reproducir / pausar">${svg(son ? 'pause' : 'play')}</button>`
      + `<button class="jr-tp-btn" data-a="next" title="Siguiente">${svg('next')}</button>`
      + `<button class="jr-tp-btn sm${_repeat ? ' on' : ''}" data-a="repeat" title="Repetir" aria-pressed="${_repeat ? 'true' : 'false'}">${svg('repeat')}</button></div>`;
  }
  function _renderPaneChrome() { /* placeholder para futuros badges de cola */ }

  // ── Render: filas / cola / estaciones ──
  function _filaHTML(t, i) {
    return `<button class="jr-row${_state && _state.track && _state.track.id === t.id ? ' activa' : ''}" data-i="${i}" data-vid="${_esc(t.id)}">`
      + `<span class="jr-thumb">${t.thumb ? `<img src="${_esc(t.thumb)}" alt="" onerror="this.remove()">` : ''}${t.dur ? `<span class="jr-dur${/live|vivo/i.test(t.dur) ? ' live' : ''}">${_esc(t.dur)}</span>` : ''}</span>`
      + `<span class="jr-rmeta"><b>${_esc(t.titulo)}</b><span class="s">${_esc(t.canal)}${t.vistas ? ' · ' + _esc(t.vistas) : ''}</span></span>`
      + `<span class="jr-add" title="Agregar a la cola" data-add="${i}">${svg('addq')}</span></button>`;
  }

  // DOTS DE CONTINUACIÓN: el pie de toda lista. Tres puntos que dicen "hay más
  // de esto" — click y se suman por abajo (la tanda siguiente de la búsqueda o
  // los relacionados de la última pista). Nunca reordena lo que ya se ve.
  // El texto va en DOS spans a propósito: la frase fija se traduce sola por el
  // i18n del workspace y la consulta del usuario queda aparte, sin tocar.
  function _dotsHTML(fuente) {
    const q = (fuente && fuente.q || '').trim();
    const busqueda = fuente && fuente.tipo === 'busqueda' && q;
    const txt = busqueda ? 'Más como' : (fuente && fuente.tipo === 'canal') ? 'Más del canal' : 'Más música relacionada';
    const corta = q.length > 24 ? q.slice(0, 24) + '…' : q;
    return `<button class="jr-more" type="button" data-mas="1" aria-label="${_esc(txt + (busqueda ? ' «' + corta + '»' : ''))}">`
      + `<span class="jr-dots" aria-hidden="true"><i></i><i></i><i></i></span>`
      + `<span class="jr-more-txt">${_esc(txt)}</span>`
      + (busqueda ? `<span class="jr-more-q">«${_esc(corta)}»</span>` : '') + `</button>`;
  }
  function _pintarDots(box) {
    if (!box) return;
    const viejo = box.querySelector(':scope > .jr-more'); if (viejo) viejo.remove();
    if (!(box._items && box._items.length)) return;
    box.insertAdjacentHTML('beforeend', _dotsHTML(box._fuente));
  }

  // Suma filas al final de una lista (arriba de los dots) con entrada suave —
  // sin re-render: el scroll y las filas de arriba no se mueven.
  function _insertarFilas(box, items, desde) {
    if (!box || !items || !items.length) return;
    const html = items.map((t, k) => _filaHTML(t, desde + k)).join('');
    const dots = box.querySelector(':scope > .jr-more');
    if (dots) dots.insertAdjacentHTML('beforebegin', html); else box.insertAdjacentHTML('beforeend', html);
    const filas = box.querySelectorAll('.jr-row');
    for (let i = desde; i < filas.length; i++) filas[i].classList.add('jr-nueva');
  }

  function _renderFilas(box, items, error, fuente) {
    if (!box) return;
    box._items = items || []; box._fuente = fuente || null; box._esPl = false;
    box.innerHTML = (items && items.length) ? items.map((t, i) => _filaHTML(t, i)).join('')
      : `<div class="jr-hint">${_esc(error || 'Sin resultados')}</div>`;
    _pintarDots(box);
  }
  // Pinta la PLAYLIST (lo que suena + lo que sigue) en un pane y lo marca como
  // "es la playlist": los dots de ahí rellenan la cola de verdad.
  function _renderPlaylistEn(box) {
    if (!box) return;
    _renderFilas(box, _pl.items, 'Poné algo a sonar y te muestro relacionados.', _plFuente);
    box._esPl = true;
    _marcarActiva(false);
  }
  // Re-pinta las listas después de sumar pistas por abajo, conservando el
  // scroll (se agregan filas nuevas, no se re-renderiza todo).
  function _repintarPlaylist() {
    const rel = $('#jr-pane-rel'), cv = $('#jr-cv-list');
    // Nadie está mostrando la playlist (handoff del preview, reanudación): que
    // Relacionados la muestre — es "lo que viene" y tiene que verse.
    if (!(rel && rel._esPl) && !(cv && cv._esPl)) {
      if (rel && !_buscando && !_inChannel && _pl.items.length) { _renderPlaylistEn(rel); }
      if (_pane === 'q') _renderQueue();
      return;
    }
    for (const box of [rel, cv]) {
      if (!box || !box._esPl) continue;
      const desde = box._items.length;
      const nuevas = _pl.items.slice(desde);
      if (!nuevas.length) continue;
      box._items = _pl.items;
      _insertarFilas(box, nuevas, desde);
      _pintarDots(box);
    }
    if (_pane === 'q') _renderQueue();
  }
  // La fila que suena se resalta en TODAS las listas visibles (la playlist
  // avanza a la vista, sin re-render). `traer` = acompañar el auto-avance
  // dejando la fila a la vista.
  function _marcarActiva(traer) {
    const vid = _state && _state.track && _state.track.id;
    for (const box of [$('#jr-pane-rel'), $('#jr-cv-list')]) {
      if (!box) continue;
      let activa = null;
      for (const row of box.querySelectorAll('.jr-row')) {
        const on = !!vid && row.dataset.vid === vid;
        row.classList.toggle('activa', on);
        if (on && !activa) activa = row;
      }
      if (traer && activa && box._esPl && !box.hidden) {
        try { activa.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch { activa.scrollIntoView(); }
      }
    }
    if (_pane === 'q') _renderQueue();
  }

  function _clicFila(e, getItems, box) {
    const items = getItems();
    if (e.target.closest('[data-mas]')) { _masEnLista(box || e.currentTarget); return; }
    const add = e.target.closest('[data-add]');
    if (add) {   // agregar a la cola = va al FINAL de lo que sigue
      const r = RY(), t = items[+add.dataset.add];
      if (r && t) { _pl = r.anexar(_pl, [t]); _repintarPlaylist(); if (_pane === 'q') _renderQueue(); }
      return;
    }
    const row = e.target.closest('.jr-row'); if (!row) return;
    const i = +row.dataset.i;
    if (!items[i]) return;
    // ESTA lista pasa a ser la cola: suena la elegida y siguen las de abajo.
    _reproducirDeLista(items, i, (box || e.currentTarget)._fuente);
    const b = box || e.currentTarget;
    b._items = _pl.items; b._esPl = true;
    for (const otro of [$('#jr-pane-rel'), $('#jr-cv-list')]) if (otro && otro !== b) otro._esPl = false;
    _marcarActiva(false);
  }

  // Los dots: traer MÁS para esta lista. Si la lista es la playlist, lo nuevo
  // entra en la cola real; si es una lista que solo se está mirando, se suma
  // ahí nomás (y seguirá siendo cola en cuanto toques una fila).
  const _masEnCurso = new WeakSet();
  async function _masEnLista(box) {
    if (!box || _masEnCurso.has(box)) return;
    const r = RY(); if (!r) return;
    const btn = box.querySelector(':scope > .jr-more');
    _masEnCurso.add(box);
    if (btn) btn.classList.add('cargando');
    try {
      if (box._esPl) {
        _plFuente = box._fuente || _plFuente;
        const n = await _rellenarCola();
        box._fuente = _plFuente;
        if (!n && btn) _dotsSinMas(box);
      } else {
        if (!box._fuente) box._fuente = { tipo: 'rel' };
        const nuevas = await _traerMas(box._fuente, box._items[box._items.length - 1]);
        const lista = r.anexar(r.crearLista(box._items, 0), nuevas, r.claveCancion);
        const suma = lista.items.slice(box._items.length);
        if (!suma.length) { _dotsSinMas(box); return; }
        const desde = box._items.length;
        box._items = lista.items;
        _insertarFilas(box, suma, desde);
        _pintarDots(box); _marcarActiva(false);
      }
    } catch {} finally {
      _masEnCurso.delete(box);
      const b2 = box.querySelector(':scope > .jr-more'); if (b2) b2.classList.remove('cargando');
    }
  }
  function _dotsSinMas(box) {
    const btn = box && box.querySelector(':scope > .jr-more'); if (!btn) return;
    btn.classList.remove('cargando'); btn.classList.add('fin'); btn.disabled = true;
    const q = btn.querySelector('.jr-more-q'); if (q) q.remove();
    const txt = btn.querySelector('.jr-more-txt'); if (txt) txt.textContent = 'No hay más por ahora';
  }

  function _renderQueue() {
    const box = $('#jr-pane-q'); if (!box) return;
    const r = RY(); const viene = r ? r.loQueViene(_pl) : [];
    if (!viene.length) { box.innerHTML = '<div class="jr-hint">La cola está vacía. Se llena sola con los relacionados de lo que suena.</div>'; return; }
    box.innerHTML = viene.map((t, i) =>
      `<div class="jr-qrow" data-i="${i}"><span class="jr-art jr-qart">${t.thumb ? `<img src="${_esc(t.thumb)}" alt="" onerror="this.remove()">` : ''}</span>`
      + `<span class="jr-rmeta"><b>${_esc(t.titulo)}</b><span class="s">${_esc(t.canal)}</span></span>`
      + `<span class="jr-qdur">${_esc(t.dur || '')}</span></div>`).join('');
  }
  // Click en la Cola: salta a esa pista de la playlist; lo de abajo sigue igual.
  function _clicQueue(e) {
    const row = e.target.closest('.jr-qrow'); if (!row) return;
    _irA(_pl.idx + 1 + (+row.dataset.i), false);
  }
  function _renderEstaciones() {
    const box = $('#jr-pane-st'); if (!box) return; const r = RY(); if (!r) return;
    box.innerHTML = r.ESTACIONES.map((e) =>
      `<button class="jr-station jr-st-${e.id}" data-q="${_esc(e.q)}"><span class="jr-st-name">${_esc(e.nombre)}</span><span class="jr-st-tag">${_esc(ST_META[e.id] || '')}</span></button>`).join('');
  }
  async function _estacion(q) {
    _setPane('rel');
    const box = $('#jr-pane-rel'); if (box) box.innerHTML = '<div class="jr-hint">Sintonizando…</div>';
    try {
      const res = await fetch(BUSCAR + encodeURIComponent(q));
      const data = await res.json();
      const items = (data.resultados || []).map(_track).filter(Boolean);
      const fuente = { tipo: 'estacion', q, token: data.token || null };
      _renderFilas(box, items, data.error, fuente);
      // La estación ES la cola: suena la primera y siguen las de abajo, en orden.
      if (items[0]) { _buscando = false; _reproducirDeLista(items, 0, fuente); if (box) { box._items = _pl.items; box._esPl = true; } _marcarActiva(false); }
    } catch { _renderFilas(box, [], 'No se pudo sintonizar'); }
  }

  // ── Vista de canal ──
  function _abrirCanal(track) {
    _inChannel = true; $('#jr-browse').hidden = true;
    const ch = $('#jr-channel'); ch.hidden = false;
    ch.innerHTML =
      `<div class="jr-cv-head"><button class="jr-cv-back" id="jr-cv-back" title="Volver">${svg('back')}</button>`
      + `<span class="jr-cv-av">${track.thumb ? '' : ''}</span>`
      + `<span class="jr-cv-meta"><b>${_esc(track.canal || 'Canal')}</b><span>${svg('users')} YouTube · videos del canal</span></span>`
      + `<button class="jr-cv-play" id="jr-cv-play" title="Reproducir">${svg('play')} Reproducir</button></div>`
      + `<div class="jr-scroll"><div class="jr-pane" id="jr-cv-list"></div></div>`;
    ch.querySelector('#jr-cv-back').addEventListener('click', () => { _inChannel = false; ch.hidden = true; $('#jr-browse').hidden = false; });
    ch.querySelector('#jr-cv-list').addEventListener('click', (e) => {
      const list = $('#jr-cv-list'); _clicFila(e, () => (list._items || []), list);
    });
    ch.querySelector('#jr-cv-play').addEventListener('click', () => {   // el canal entero como cola
      const list = $('#jr-cv-list'), items = (list && list._items) || [];
      if (!items.length) return;
      _reproducirDeLista(items, 0, list._fuente);
      list._items = _pl.items; list._esPl = true;
      const rel = $('#jr-pane-rel'); if (rel) rel._esPl = false;
      _marcarActiva(true);
    });
    _cargarCanal(track);
  }

  // ── Boot temprano: reanuda la música ASAP tras un reinicio ──
  function _boot() {
    if (_booted) return;
    const r = RY(); if (!r) return;
    const st = r.deserializar(_leer());
    if (!st || !st.track || !st.sonando) return;
    _booted = true; _state = st; _intent = true; _played.add(st.track.id);
    const kb = _clave(st.track); if (kb) _playedClaves.add(kb);
    _asegurarAudio().src = _src(st.track, { autoplay: true, start: st.t });
    _armarGesto(); _guardadoPeriodico();
    _sembrarPlaylist(st.track);
    _renderNow(); _renderMini();
  }

  // ── Init ──
  let _tries = 0;
  function init() {
    _montar();
    if (!_mounted && _tries < 40) { _tries++; setTimeout(init, 120); }   // el header puede tardar
  }

  // `play` público = poner algo a sonar desde afuera (mismo camino que el
  // handoff del preview: nace una playlist con esa pista y sigue por relacionados).
  root.JarvisRadio = { init, open, close, play: adopt, adopt, pauseForTwitch, resumeAfterTwitch, estado: () => _state };

  // Boot ASAP (resume) + montaje de UI cuando el DOM esté listo.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { _boot(); init(); }, { once: true });
  } else { _boot(); init(); }

})(typeof window !== 'undefined' ? window : globalThis);
