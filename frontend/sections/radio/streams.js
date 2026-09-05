'use strict';
// ═══════════════════════════════════════════════════════════════════════════
// JARVIS · Radio — Fuente V3: Streams (radio en vivo)
// window.JarvisRadioStreams
//
// Catálogo LOCAL de radios ICEcast públicas (SomaFM, HTTPS): no hay backend,
// no hay cuenta, no hay sesión — el "buscador" es un filtro local del catálogo
// y el player es un <audio> colgado de <body> con el contrato del radio.
//
// CONTRATO del player (el radio lo recibe vía player: {...} de registrarFuente):
//   cargar(track)      → audio.src = track.url + play()
//   play() / resume()  → reanudar
//   pause()            → pausar (lo usa pauseForTwitch del radio)
//   seek(ms)           → no-op (vivo: no se puede rebobinar)
//   volumen(0-100)     → reaplica el volumen del radio al <audio>
//   onEvento(cb)       → cb({tipo, ...}): 'duracion' {seg} (0 = en vivo),
//                        'posicion' {seg}, 'play', 'pausa',
//                        'error' {motivo}, 'blocked' (autoplay sin gesto)
//
// MIXED CONTENT: si algún stream futuro fuera http:// y el workspace se sirve
// por https://, el navegador BLOQUEA el audio (mixed content). El catálogo
// actual es 100% https(somafm) y solo requiere conexión a internet; si el
// audio muere por red, el radio debe saltar al siguiente stream.
// ═══════════════════════════════════════════════════════════════════════════
(function (root) {
  if (root.JarvisRadioStreams) return;

  const ID = 'streams';

  // ── Catálogo (SomaFM público, verificado 2026-09-05: ice1 responde 200) ──
  // OJO: la estación se llama `indiepop` ("Indie Pop Rocks!") — `indipop`
  // NO existe en SomaFM (404). Colores = tono de categoría (verde ≠ rojo…).
  const _ESTREAMS = [
    { id: 'soma:groovesalad',   url: 'https://ice1.somafm.com/groovesalad-128-mp3',   titulo: 'Groove Salad',        color: '#7d6cf0' },
    { id: 'soma:dronezone',     url: 'https://ice1.somafm.com/dronezone-128-mp3',     titulo: 'Drone Zone',          color: '#5a9bff' },
    { id: 'soma:spacestation',  url: 'https://ice1.somafm.com/spacestation-128-mp3',  titulo: 'Space Station Soma',  color: '#8f7cff' },
    { id: 'soma:defcon',        url: 'https://ice1.somafm.com/defcon-128-mp3',        titulo: 'DEF CON Radio',       color: '#ff7a6b' },
    { id: 'soma:sonicuniverse', url: 'https://ice1.somafm.com/sonicuniverse-128-mp3', titulo: 'Sonic Universe',     color: '#22c9b8' },
    { id: 'soma:indiepop',      url: 'https://ice1.somafm.com/indiepop-128-mp3',      titulo: 'Indie Pop Rocks!',    color: '#ff9d5c' },
    { id: 'soma:secretagent',   url: 'https://ice1.somafm.com/secretagent-128-mp3',   titulo: 'Secret Agent',        color: '#c77cf0' },
    { id: 'soma:fluid',         url: 'https://ice1.somafm.com/fluid-128-mp3',         titulo: 'Fluid',               color: '#4fd2ff' },
    { id: 'soma:deepspaceone',  url: 'https://ice1.somafm.com/deepspaceone-128-mp3',  titulo: 'Deep Space One',      color: '#9aa8ff' },
  ];
  const DESCS = {
    'soma:groovesalad':   ['Chillout y downtempo para estudiar',   'Chillout & downtempo for studying'],
    'soma:dronezone':     ['Ambient y drones profundos',           'Deep ambient drones'],
    'soma:spacestation':  ['Dreamy trip-hop y space rock',         'Dreamy trip-hop & space rock'],
    'soma:defcon':        ['Techno y podcasts del Hacker News',    'Techno & Hacker News podcasts'],
    'soma:sonicuniverse': ['Jazz underground de NYC',              'Underground jazz from NYC'],
    'soma:indiepop':      ['Indie pop y rock de hoy',              'Today\'s indie pop & rock'],
    'soma:secretagent':   ['Lounge, downtempo y chill exótico',    'Lounge, downtempo & exotic chill'],
    'soma:fluid':         ['Ambient instrumental de la NASA',      'Instrumental from the NASA archives'],
    'soma:deepspaceone':  ['Clásica y ambient para el espacio',    'Classical & ambient for space'],
  };

  // Thumb generado: chip de color de categoría + monograma mono (data-URI así
  // se renderiza en cualquier <img> sin ficheros ni backend).
  function _thumb(t) {
    let ini = 'XX';
    if (t.titulo) {
      const w = t.titulo.replace(/[^A-Za-zÁÉÍÓÚÑáéíóúñ ]/g, '').trim();
      ini = (w.split(' ').length > 1 ? w.split(' ')[0][0] + w.split(' ')[1][0] : w.slice(0, 2)).toUpperCase();
    }
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="74" height="42"><rect width="74" height="42" rx="8" fill="${t.color}"/><circle cx="10" cy="32" r="3" fill="rgba(255,255,255,.85)"/><text x="37" y="27" font-family="JetBrains Mono,monospace" font-size="14" font-weight="700" fill="rgba(10,8,24,.85)" text-anchor="middle">${ini}</text></svg>`;
    return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
  }

  function _pista(t) {
    return {
      id: t.id, titulo: t.titulo, canal: 'SomaFM', canalId: null,
      thumb: _thumb(t), dur: '∞', vistas: '', url: t.url,
      color: t.color, descripcion: (DESCS[t.id] || [t.descripcion || ''])[0], enVivo: true,
    };
  }

  const ESTREAMS = _ESTREAMS.map(_pista);

  function buscarLocal(q) {
    const s = String(q || '').trim().toLowerCase();
    const r = s ? ESTREAMS.filter((t) => (t.titulo + ' ' + t.descripcion).toLowerCase().includes(s)) : ESTREAMS.slice();
    return Promise.resolve({ resultados: r, token: null, error: null });
  }

  // ── Player: <audio> persistente colgado de <body> ──
  let _audio = null, _evCb = null, _actual = null;
  let _dur = 0, _vol = 0.8;

  function _asegurarAudio() {
    if (_audio && _audio.isConnected) return _audio;
    _audio = document.createElement('audio');
    _audio.className = 'jr-audio-stream';
    _audio.id = 'jr-audio-stream';
    _audio.preload = 'none';
    _audio.setAttribute('data-fuente', ID);
    _audio.addEventListener('timeupdate', () => { _emit('posicion', { seg: Math.floor(_audio.currentTime || 0) }); });
    _audio.addEventListener('durationchange', () => {
      const d = Number.isFinite(_audio.duration) ? Math.floor(_audio.duration) : 0;
      _dur = d; _emit('duracion', { seg: d });
    });
    _audio.addEventListener('play', () => _emit('play'));
    _audio.addEventListener('pause', () => _emit('pausa'));
    _audio.addEventListener('ended', () => _emit('fin'));
    _audio.addEventListener('error', () => {
      if (!_actual) return;   // error de una carga vieja ya descartada
      if (_audio.getAttribute('src') !== _actual.url && !_audio.readyState) return;
      _emit('error', { motivo: 'stream' });
    });
    _audio.addEventListener('stalled', () => _emit('buffering'));
    document.body.appendChild(_audio);
    return _audio;
  }

  function _emit(tipo, extra) {
    if (typeof _evCb === 'function') { try { _evCb(Object.assign({ tipo }, extra || {})); } catch {} }
  }

  function cargar(track) {
    const a = _asegurarAudio();
    const url = (track && (track.url || track.stream)) || '';
    if (!url) { _emit('error', { motivo: 'sin-url' }); return Promise.resolve(false); }
    _actual = track || { url };
    return new Promise((res) => {
      const done = () => { a.removeEventListener('playing', done); res(true); };
      const fail = (e) => {
        a.removeEventListener('error', fail); a.removeEventListener('playing', done);
        const blocked = e && (e.name === 'NotAllowedError');
        _emit(blocked ? 'blocked' : 'error', { motivo: blocked ? 'autoplay' : 'stream' });
        res(false);
      };
      a.addEventListener('playing', done, { once: true });
      a.addEventListener('error', fail, { once: true });
      a.src = url;
      a.load();
      a.volume = _vol;
      const p = a.play();
      if (p && typeof p.catch === 'function') p.catch(fail);
    });
  }
  function play() { const a = _asegurarAudio(); if (_actual) { const p = a.play(); if (p && p.catch) p.catch(() => _emit('blocked')); } }
  function pause() { _asegurarAudio().pause(); }
  function seek() { /* en vivo no se rebobina */ }
  function volumen(pct) {
    _vol = Math.min(1, Math.max(0, (Number(pct) || 0) / 100));
    if (_audio) _audio.volume = _vol;
  }
  function duracion() { return _dur; }
  function posicion() { return _audio ? Math.floor(_audio.currentTime || 0) : 0; }

  const _adapter = {
    cargar, play, resume: play, pause, seek, volumen, volume: volumen,
    duracion, posicion,
    onEvento: (cb) => { _evCb = cb; }, enEvento: (cb) => { _evCb = cb; },
  };
  function _estado() { return { sonando: !!(_audio && _actual && !_audio.paused), track: _actual, url: (_actual && _actual.url) || null }; }

  // ── Registro (radio.js: JarvisRadio.registrarFuente) ──
  let _registrado = false;
  function registrar() {
    if (_registrado) return true;
    const J = root.JarvisRadio;
    if (!J || typeof J.registrarFuente !== 'function') return false;
    _registrado = true;
    J.registrarFuente({
      id: ID, etiqueta_es: 'Streams', etiqueta_en: 'Streams',
      buscar: buscarLocal, mas: null, relacionados: null,
      player: _adapter, catalogo: ESTREAMS,
    });
    return true;
  }

  // ── i18n ──
  let _i18nDone = false;
  function _i18n() {
    if (_i18nDone || !(root.JarvisI18n && root.JarvisI18n.agregar)) return;
    _i18nDone = true;
    const d = {
      'Streams': 'Streams',
      'Stream de radio en vivo': 'Live radio stream',
      'Elegí un stream en vivo': 'Pick a live stream',
      'Radio en vivo · sin cuenta': 'Live radio · no account needed',
      'Conexión perdida con el stream': 'Stream connection lost',
      'Chillout y downtempo para estudiar': 'Chillout & downtempo for studying',
      'Ambient y drones profundos': 'Deep ambient drones',
      'Dreamy trip-hop y space rock': 'Dreamy trip-hop & space rock',
      'Techno y podcasts del Hacker News': 'Techno & Hacker News podcasts',
      'Jazz underground de NYC': 'Underground jazz from NYC',
      'Indie pop y rock de hoy': "Today's indie pop & rock",
      'Lounge, downtempo y chill exótico': 'Lounge, downtempo & exotic chill',
      'Ambient instrumental de la NASA': 'Instrumental from the NASA archives',
      'Clásica y ambient para el espacio': 'Classical & ambient for space',
    };
    try { root.JarvisI18n.agregar(d); } catch {}
  }

  // ── Boot ──
  function _boot() {
    _i18n();
    if (registrar()) return;
    let tries = 0;   // rechequeo corto por si radio.js llega un tiempito después
    const iv = setInterval(() => { if (registrar() || ++tries > 8) clearInterval(iv); }, 400);
  }
  if (typeof document !== 'undefined') {
    if (document.readyState !== 'loading') _boot();
    else window.addEventListener('load', _boot);
  }

  root.JarvisRadioStreams = {
    registrar, buscarLocal, estado: _estado,
    ESTREAMS, catalogo: ESTREAMS, _adapter, player: _adapter,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.JarvisRadioStreams;

})(typeof window !== 'undefined' ? window : globalThis);
