'use strict';
// ═══════════════════════════════════════════════════════════════════════════
// JARVIS · Radio — Fuente V2: Spotify (Web Playback SDK)
// window.JarvisRadioSpotify
//
// Sesión: el token NO vive en el frontend — vive en el backend (cookie de
// sesión). El Web Playback SDK sí necesita el token EN el cliente, así que
// este módulo lo pide con  GET /api/radio/spotify/token  →  {access_token,
// expires_in} (401 = sin sesión). Flujo de login: GET /api/radio/spotify/login
// → {url} → window.open(url) → Spotify autoriza → callback redirige a
// /workspace?spotify=ok → acá se guarda localStorage['jarvis.spotify.autorizado']
// y se decora con toast "Spotify se conectó".
//
// CONTRATO del player (el radio lo recibe vía player: {...} de registrarFuente):
//   cargar(track)     → sdk play({ uri: track.id }) (id ya viene 'spotify:track:*')
//   play() / resume() → sdk resume()   ·   pause() → sdk pause()
//   seek(ms)          → sdk seek(ms)   ·   volumen(0-100) → sdk setVolume(v/100)
//   duracion()        → seg (0 = desconocida)
//   onEvento(cb)      → cb({tipo, ...}): 'duracion' {seg}, 'posicion' {seg},
//                       'play', 'pausa', 'fin', 'cargando' {track},
//                       'estado' {premium, dispositivo}, 'error' {motivo}
//
// Premium: el SDK NO reproduce en cuentas Free; account_error/initialization_error
// ⇒ estado 'sin-premium' y hint en el popover (clase .jr-src-hint): "Spotify
// full playback necesita cuenta Premium".
//
// NOTA: este módulo NO toca radio.js — se registra solo con
// JarvisRadio.registrarFuente() al cargar (con reitero por si el API llega
// tarde). Si el API aún no existe, silencioso.
// ═══════════════════════════════════════════════════════════════════════════
(function (root) {
  if (root.JarvisRadioSpotify) return;

  const ID = 'spotify';
  const KEY_AUTH = 'jarvis.spotify.autorizado';
  const END_TOKEN = '/api/radio/spotify/token';
  const END_LOGIN = '/api/radio/spotify/login';
  const END_BUSCAR = '/api/orchestrator/preview/buscar?modo=spotify&q=';
  const SDK_URL = 'https://sdk.scdn.co/spotify-player.js';

  const _ss = (s) => {
    const n = Math.max(0, Math.floor(Number(s) || 0));
    return Math.floor(n / 60) + ':' + String(n % 60).padStart(2, '0');
  };

  // ── estado observable ──
  const est = { autorizado: false, premium: null, dispositivo: null, track: null };
  let _listeners = [];
  function _notificar() { const s = _snap(); _listeners.forEach((cb) => { try { cb(s); } catch {} }); }
  function _snap() { return { autorizado: est.autorizado, premium: est.premium, dispositivo: est.dispositivo, track: est.track }; }

  // ── token (backend, con caché + invalidación por expires_in) ──
  let _token = null, _tokenHasta = 0, _tokenPend = null;
  async function _pedirToken() {
    if (_token && Date.now() < _tokenHasta) return _token;
    if (_tokenPend) return _tokenPend;
    _tokenPend = fetch(END_TOKEN, { credentials: 'same-origin', cache: 'no-store' })
      .then((r) => {
        if (r.status === 401) { const e = new Error('sesion'); e.noSesion = true; throw e; }
        if (!r.ok) throw new Error('http-' + r.status);
        return r.json();
      })
      .then((d) => {
        if (!d || !d.access_token) throw new Error('sin-token');
        _token = d.access_token;
        _tokenHasta = Date.now() + Math.max(60, Number(d.expires_in) || 3600) * 1000;
        _setAutorizado(true);
        return _token;
      })
      .catch((e) => {
        _token = null; _tokenHasta = 0;
        if (e && e.noSesion) _setAutorizado(false);
        throw e;
      })
      .finally(() => { _tokenPend = null; });
    return _tokenPend;
  }
  function _setAutorizado(ok) {
    if (est.autorizado === ok) return;
    est.autorizado = ok;
    try { localStorage.setItem(KEY_AUTH, ok ? '1' : '0'); } catch {}
    _emit('estado', _snap()); _notificar();
  }
  function _verificarSesion() { _pedirToken().catch(() => {}); }

  // ── eventos del adapter (el radio escucha por onEvento/enEvento) ──
  let _evCb = null;
  function _emit(tipo, extra) {
    if (typeof _evCb === 'function') { try { _evCb(Object.assign({ tipo }, extra || {})); } catch {} }
  }
  let _dur = 0, _pos = 0, _lastPaused = null, _finEmitido = false;

  // ── Web Playback SDK ──
  let _player = null, _sdkPend = null;
  function _sdk() {
    if (root.Spotify && root.Spotify.Player) return Promise.resolve();
    if (_sdkPend) return _sdkPend;
    _sdkPend = new Promise((res, rej) => {
      let done = false;
      const settle = (ok) => { if (done) return; done = true; ok ? res() : rej(new Error('sdk')); };
      const anterior = root.onSpotifyWebPlaybackSDKReady;
      root.onSpotifyWebPlaybackSDKReady = () => { try { if (anterior) anterior(); } catch {} settle(true); };
      const s = document.createElement('script');
      s.src = SDK_URL; s.async = true;
      s.onload = () => { if (!root.Spotify || !root.Spotify.Player) settle(false); };
      s.onerror = () => settle(false);
      document.head.appendChild(s);
      setTimeout(() => settle(false), 15000);
    });
    return _sdkPend;
  }
  function _onEstadoPlayer(state) {
    if (!state) return;
    const durMs = Number(state.duration_ms);
    const posMs = Number(state.position_ms);
    if (durMs > 0) { _dur = durMs / 1000; _emit('duracion', { seg: Math.floor(_dur) }); }
    _pos = posMs / 1000;
    _emit('posicion', { seg: Math.floor(_pos) });
    const tr = state.track;
    if (tr && tr.id) {
      est.track = { id: tr.id, titulo: tr.name || '', canal: (tr.artists && tr.artists[0] && tr.artists[0].name) || 'Spotify', thumb: (tr.album && tr.album.images && tr.album.images[0] && tr.album.images[0].url) || null };
      _notificar();
      if (_finEmitido && durMs > 0 && !state.paused) _finEmitido = false;
      if (_finEmitido) return;
    }
    const paused = !!state.paused;
    if (paused !== _lastPaused) {
      _lastPaused = paused;
      _emit(paused ? 'pausa' : 'play');
    }
    if (durMs > 0 && !paused && posMs > 0 && durMs - posMs <= 800 && !_finEmitido) {
      _finEmitido = true; _emit('fin');
    }
  }
  function _escuchar(p) {
    p.on('ready', (d) => {
      est.premium = true; est.dispositivo = (d && d.device_id) || null;
      _emit('estado', _snap()); _notificar(); _limpiarHint('spotify:premium');
    });
    p.on('not_ready', () => { est.dispositivo = null; _emit('estado', _snap()); _notificar(); });
    p.on('account_error', () => { _sinPremium(); });
    p.on('initialization_error', () => { _sinPremium(); });
    p.on('authentication_error', () => { _token = null; _tokenHasta = 0; _setAutorizado(false); _hint('Sesión de Spotify vencida', 'spotify:sesion'); });
    p.on('playback_error', () => _emit('error', { motivo: 'playback' }));
    p.on('player_state_changed', _onEstadoPlayer);
  }
  function _sinPremium() {
    est.premium = false; _emit('estado', _snap()); _notificar();
    _hint('La reproducción completa de Spotify necesita una cuenta Premium — iniciá sesión con una cuenta Premium', 'spotify:premium');
  }
  async function _asegurarPlayer() {
    await _pedirToken();   // si 401: sin sesión → cargar lo reporta
    await _sdk();          // si no cargó el SDK: error
    if (!_player) {
      _player = new root.Spotify.Player({
        name: 'Jarvis Radio',
        getOAuthToken: (cb) => { _pedirToken().then(cb).catch(() => cb('')); },
      });
      _escuchar(_player);
      _player.connect();
    }
    return _player;
  }

  // ── comandos (adapter) ──
  function cargar(track) {
    const uri = (track && (track.uri || track.url)) || (track && track.id) || '';
    return _asegurarPlayer()
      .then((p) => {
        let u = String(uri);
        if (!u) throw new Error('sin-uri');
        if (!/^spotify:/.test(u)) u = 'spotify:track:' + u;
        est.track = { id: u, titulo: (track && track.titulo) || '', canal: (track && track.canal) || 'Spotify', thumb: (track && track.thumb) || null };
        _lastPaused = false; _finEmitido = false; _dur = 0;
        _emit('cargando', { track: est.track });
        _notificar();
        return p.play({ uri: u });
      })
      .then(() => { _emit('play'); return true; })
      .catch((e) => {
        if (e && e.noSesion) { _emit('error', { motivo: 'sesion' }); _pedirLogin(); }
        else if (e && e.message === 'sdk') { _emit('error', { motivo: 'sdk' }); }
        else _emit('error', { motivo: 'play' });
        return false;
      });
  }
  function play() { if (_player) _player.resume().catch(() => {}); }
  function pause() { if (_player) _player.pause().catch(() => {}); }
  function seek(ms) { if (_player) _player.seek(Math.max(0, Math.round(Number(ms) || 0))).catch(() => {}); }
  function volumen(pct) { if (_player) _player.setVolume(Math.min(1, Math.max(0, (Number(pct) || 0) / 100))).catch(() => {}); }
  function duracion() { return _dur; }
  function posicion() { return _pos; }

  const _adapter = {
    cargar, play, resume: play, pause, seek, volumen, volume: volumen,
    duracion, posicion,
    onEvento: (cb) => { _evCb = cb; }, enEvento: (cb) => { _evCb = cb; },
  };

  // ── búsqueda (backend) ──
  function _pista(r) {
    if (!r || !r.id) return null;
    let dur = r.duracion != null ? r.duracion : r.dur;
    if (typeof dur === 'number' && isFinite(dur)) dur = _ss(dur);
    return {
      id: r.id, titulo: r.titulo || '', canal: r.canal || '', canalId: null,
      thumb: r.thumb || null, dur: dur || '', vistas: r.vistas || '',
      url: r.url || '', spotify: true, duracion_s: r.duracion || r.dur || null,
    };
  }
  async function buscar(q) {
    let data;
    try {
      const res = await fetch(END_BUSCAR + encodeURIComponent(String(q || '').trim()), { credentials: 'same-origin' });
      data = await res.json();
    } catch {
      _limpiarHint('spotify:sesion');
      return { resultados: [], token: null, error: 'no-red' , necesitaLogin: false };
    }
    if (data && data.error) {
      const err = String(data.error);
      if (/configurad|CLIENT_ID/i.test(err)) {
        _hint('Spotify no está configurado', 'spotify:config');
      } else if (/sesi[oó]n|login|token|401|autoriz|auth/i.test(err)) {
        // OJO: el backend dice "Sin sesión de Spotify…" (con ó acentuada):
        // /sesion/ plano NO matchea y el hint quedaba muerto.
        _hint('Sesión de Spotify no iniciada', 'spotify:sesion');
        _pedirLogin();
      }
      return { resultados: [], token: null, error: err, necesitaLogin: !/configurad|CLIENT_ID/i.test(err) };
    }
    const items = ((data && data.resultados) || []).map(_pista).filter(Boolean);
    return { resultados: items, token: (data && data.token) || null, error: null };
  }

  // ── hints: canal de radio.js si existe; si no, bloque .jr-src-hint propio ──
  const _hints = new Map();   // clave → texto
  function _hint(txt, clave) {
    _hints.set(clave || txt, txt);
    _renderHint();
  }
  function _limpiarHint(clave) {
    if (_hints.delete(clave || '')) _renderHint();
  }
  let _cssInyectado = false;
  function _css() {
    if (_cssInyectado) return; _cssInyectado = true;
    const st = document.createElement('style');
    st.id = 'jr-src-hint-css';
    st.textContent = `.jr-src-hints{padding:10px 14px 0;display:flex;flex-direction:column;gap:8px}
.jr-src-hint{display:flex;align-items:center;gap:10px;padding:9px 11px;border:1px solid var(--ob-accent-24);border-radius:var(--radius,8px);
  background:var(--ob-bg-2);color:var(--ob-fg-1);font:500 var(--text-xs,11px) var(--font-ui)}
.jr-src-hint b{color:var(--ob-fg-0);font-weight:600}
.jr-src-hint-btn{margin-left:auto;flex:0 0 auto;padding:5px 10px;border:1px solid var(--ob-accent-40);border-radius:var(--radius-btn,7px);
  background:var(--ob-accent-14);color:var(--ob-fg-0);font:600 var(--text-xs,11px) var(--font-ui);cursor:pointer}
.jr-src-hint-btn:hover{background:var(--ob-accent-24)}
.jr-sp-modal{position:fixed;inset:0;z-index:2300;display:grid;place-items:center;padding:18px;background:oklch(0% 0 0 / .5)}
.jr-sp-card{position:relative;width:min(340px, 92vw);padding:22px 20px 18px;border-radius:var(--radius-lg,14px);
  border:1px solid var(--ob-line-1);background:var(--ob-bg-2);box-shadow:var(--shadow-2);text-align:center;font-family:var(--font-ui)}
.jr-sp-mark{width:44px;height:44px;margin:0 auto 10px;border-radius:50%;display:grid;place-items:center;
  border:1px solid var(--ob-accent-40);background:var(--ob-accent-14);color:var(--ob-accent)}
.jr-sp-mark svg{width:22px;height:22px}
.jr-sp-t{display:block;font:600 var(--text-base,13px) var(--font-ui);color:var(--ob-fg-0)}
.jr-sp-d{display:block;margin-top:6px;font:400 var(--text-xs,11px) var(--font-ui);color:var(--ob-fg-3)}
.jr-sp-url{display:block;margin-top:10px;font:600 var(--text-xs,11px) var(--font-mono);color:var(--ob-accent);word-break:break-all}
.jr-sp-status{display:block;margin-top:10px;font:500 var(--text-xs,11px) var(--font-ui);color:var(--ob-info)}
.jr-sp-status[hidden],.jr-sp-url[hidden]{display:none}
.jr-sp-actions{display:flex;gap:8px;margin-top:16px;justify-content:center}
.jr-sp-actions button{padding:8px 14px;border-radius:var(--radius-btn,7px);font:600 var(--text-xs,11px) var(--font-ui);cursor:pointer}
.jr-sp-go{border:1px solid var(--ob-accent-40);background:var(--ob-accent);color:var(--ob-fg-0)}
.jr-sp-go:hover{filter:brightness(1.1)}
.jr-sp-close{border:1px solid var(--ob-line-1);background:transparent;color:var(--ob-fg-2)}
.jr-sp-close:hover{background:var(--ob-bg-3);color:var(--ob-fg-1)}
.jr-sp-x{position:absolute;top:8px;right:8px;width:28px;height:28px;border:0;border-radius:var(--radius-btn,7px);
  background:transparent;color:var(--ob-fg-3);display:grid;place-items:center;cursor:pointer}
.jr-sp-x:hover{background:var(--ob-bg-3);color:var(--ob-fg-1)}
.jr-sp-x svg{width:14px;height:14px}`;
    document.head.appendChild(st);
  }
  function _renderHint() {
    const J = root.JarvisRadio;
    if (J && typeof J.hintDeFuente === 'function') { try { J.hintDeFuente(ID, Array.from(_hints.values()).join('\n'), true); return; } catch {} }
    if (J && typeof J.fuenteHint === 'function') { try { J.fuenteHint(ID, Array.from(_hints.values()).join('\n'), true); return; } catch {} }
    _css();
    const pop = document.getElementById('jarvis-radio-pop');
    if (!pop) return;
    let cont = pop.querySelector('#jr-src-hints');
    if (!cont) {
      const pivot = pop.querySelector('#jr-browse') || pop.querySelector('.jr-seek') || pop.querySelector('.jr-card');
      if (!pivot) return;
      cont = document.createElement('div'); cont.id = 'jr-src-hints'; cont.className = 'jr-src-hints';
      pivot.parentNode.insertBefore(cont, pivot);
    }
    cont.innerHTML = '';
    _hints.forEach((txt) => {
      const b = document.createElement('div'); b.className = 'jr-src-hint';
      const span = document.createElement('span'); span.textContent = txt;
      b.appendChild(span);
      if (!txt.includes('Premium')) {
        const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'jr-src-hint-btn';
        btn.textContent = 'Conectá Spotify';
        btn.addEventListener('click', () => { try { abrirLogin(); } catch {} });
        b.appendChild(btn);
      }
      cont.appendChild(b);
    });
    if (root.JarvisI18n && typeof root.JarvisI18n.aplicar === 'function') {
      try { root.JarvisI18n.aplicar(cont); } catch {}
    }
  }

  // ── modal de login ──
  let _modal = null;
  const _SVG = {
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    n: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18V5l10-2v11"/><circle cx="6.5" cy="18" r="2.6"/><circle cx="16.5" cy="14" r="2.6"/></svg>',
  };
  function _montarModal() {
    if (_modal && _modal.isConnected) return;
    _css();
    const ov = document.createElement('div'); ov.className = 'jr-sp-modal'; ov.id = 'jr-sp-modal';
    ov.innerHTML =
      `<div class="jr-sp-card" role="dialog" aria-modal="true">
        <button class="jr-sp-x" type="button" aria-label="Cerrar">${_SVG.x}</button>
        <div class="jr-sp-mark">${_SVG.n}</div>
        <b class="jr-sp-t">Conectá Spotify</b>
        <span class="jr-sp-d">Autorizá el acceso y vas a volver conectado</span>
        <a class="jr-sp-url" hidden target="_blank" rel="noopener" href="#">Abrí la ventana de Spotify</a>
        <span class="jr-sp-status" hidden>Esperando autorización…</span>
        <div class="jr-sp-actions">
          <button class="jr-sp-go" type="button">Abrir Spotify</button>
          <button class="jr-sp-close" type="button">Ahora no</button>
        </div>
      </div>`;
    document.body.appendChild(ov);
    _modal = ov;
    ov.querySelector('.jr-sp-go').addEventListener('click', () => _irALogin());
    ov.querySelector('.jr-sp-close').addEventListener('click', _cerrarModal);
    ov.querySelector('.jr-sp-x').addEventListener('click', _cerrarModal);
    ov.addEventListener('click', (e) => { if (e.target === ov) _cerrarModal(); });
  }
  function _modalStatus(txt, url) {
    _montarModal();
    const st = _modal.querySelector('.jr-sp-status'); const a = _modal.querySelector('.jr-sp-url');
    st.hidden = !txt; st.textContent = txt || '';
    if (url) { a.hidden = false; a.href = url; } else a.hidden = true;
  }
  function _cerrarModal() { if (_modal) { _modal.remove(); _modal = null; _limpiarHint('spotify:sesion'); } }
  function _pedirLogin() { _montarModal(); }

  let _authWin = null, _authTimer = null;
  async function _irALogin() {
    let data = null;
    _modalStatus('Esperando autorización…');
    try {
      const res = await fetch(END_LOGIN, { credentials: 'same-origin' });
      data = await res.json();
    } catch {}
    if (data && data.url) {
      try {
        _authWin = window.open(data.url, 'jarvis-spotify-auth', 'width=560,height=740,popup=1');
      } catch {}
      if (!_authWin) { _modalStatus('', data.url); return; }
      _modalStatus('Esperando autorización…');
      _vigilarAuth();
    } else {
      _cerrarModal();
      const err = (data && data.error) || 'sin-url';
      if (/configurad|CLIENT_ID/i.test(String(err))) {
        _hint('Spotify no está configurado — poné SPOTIFY_CLIENT_ID en el .env', 'spotify:config');
        if (typeof root.toast === 'function') root.toast('Spotify no está configurado — poné SPOTIFY_CLIENT_ID en el .env', 'error', 5000);
      } else {
        _hint('Sesión de Spotify no iniciada', 'spotify:sesion');
      }
      _notificar();
    }
  }
  function _vigilarAuth() {
    clearInterval(_authTimer);
    let tries = 0;
    _authTimer = setInterval(async () => {
      tries++;
      let ok = false;
      try { ok = !!await _pedirToken(); } catch {}
      if (ok) {
        clearInterval(_authTimer);
        _cerrarModal();
        if (typeof root.toast === 'function') root.toast('Spotify se conectó', 'success', 3500);
        _notificar(); _emit('sesion', { autorizado: true });
        return;
      }
      const winClosed = _authWin ? _authWin.closed : false;
      if (tries >= 90 || (winClosed && tries >= 15)) {
        clearInterval(_authTimer);
        _cerrarModal(); _hint('Sesión de Spotify no iniciada', 'spotify:sesion');
      }
    }, 2000);
  }
  function abrirLogin() { _pedirLogin(); }

  // ── callback de la autorización: /workspace?spotify=ok ──
  function _leerCallbackUri() {
    try {
      const u = new URL(root.location.href);
      if (u.searchParams.get('spotify') !== 'ok') return;
      try { localStorage.setItem(KEY_AUTH, '1'); } catch {}
      const q = u.searchParams; q.delete('spotify');
      const qs = q.toString();
      try { root.history.replaceState(null, '', u.pathname + (qs ? '?' + qs : '')); } catch {}
      est.autorizado = true;
      if (typeof root.toast === 'function') root.toast('Spotify se conectó', 'success', 3000);
      _emit('sesion', { autorizado: true }); _notificar();
      setTimeout(() => { try { root.close(); } catch {} }, 900);
    } catch {}
  }

  // ── registro (radio.js: JarvisRadio.registrarFuente) ──
  let _registrado = false;
  function _payload() {
    return {
      id: ID, etiqueta_es: 'Spotify', etiqueta_en: 'Spotify',
      buscar, mas: null, relacionados: null,
      player: _adapter, login: abrirLogin,
    };
  }
  function registrar() {
    if (_registrado) return true;
    const J = root.JarvisRadio;
    if (!J || typeof J.registrarFuente !== 'function') return false;
    _registrado = true;
    try { J.registrarFuente(_payload()); } catch {}
    return true;
  }

  // ── i18n ──
  let _i18nDone = false;
  function _i18n() {
    if (_i18nDone || !(root.JarvisI18n && root.JarvisI18n.agregar)) return;
    _i18nDone = true;
    try {
      root.JarvisI18n.agregar({
        'Spotify': 'Spotify',
        'Sesión de Spotify no iniciada': 'Spotify session not started',
        'Sesión de Spotify vencida': 'Spotify session expired',
        'Conectá Spotify': 'Connect Spotify',
        'Abrir Spotify': 'Open Spotify',
        'Ahora no': 'Not now',
        'Spotify se conectó': 'Spotify connected',
        'Esperando autorización…': 'Waiting for authorization…',
        'Autorizá el acceso y vas a volver conectado': 'Authorize access and you\'ll come back connected',
        'Abrí la ventana de Spotify': 'Open the Spotify window',
        'Spotify no está configurado': 'Spotify is not configured',
        'Poné SPOTIFY_CLIENT_ID en el .env': 'Set SPOTIFY_CLIENT_ID in the .env',
        'La reproducción completa de Spotify necesita una cuenta Premium — iniciá sesión con una cuenta Premium': 'Spotify full playback needs a Premium account — sign in with a Premium account',
        'Iniciá sesión con una cuenta Premium': 'Sign in with a Premium account',
        'Dispositivo Spotify no disponible': 'Spotify device not available',
        'Conexión con Spotify perdida': 'Spotify connection lost',
        'Buscá y reproducí desde tu cuenta de Spotify': 'Search and play from your Spotify account',
      });
    } catch {}
  }

  // ── boot ──
  function _boot() {
    _i18n();
    _css();   // las clases .jr-src-hints las pinta el contenedor de radio.js
    _leerCallbackUri();
    _verificarSesion();
    if (registrar()) {
      let tries = 0;
      const iv = setInterval(() => { if (registrar() || ++tries > 8) clearInterval(iv); }, 400);
    }
  }
  if (typeof document !== 'undefined') {
    if (document.readyState !== 'loading') _boot();
    else window.addEventListener('load', _boot);
  }

  root.JarvisRadioSpotify = {
    registrar, abrirLogin, login: abrirLogin, conectar: abrirLogin,
    estado: _snap, onEstado: (cb) => { if (typeof cb === 'function') { _listeners.push(cb); } },
    _adapter, player: _adapter, _payload,
  };

})(typeof window !== 'undefined' ? window : globalThis);
