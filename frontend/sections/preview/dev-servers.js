'use strict';
// ─── Menú de "Localhost activos" ──────────────────────────────────────────────
// Botón en la TOOLBAR del Web Preview (#jw-localhosts-btn — se movió acá desde la
// barra del workspace a pedido del usuario 2026-07-09; preview.js lo renderiza y
// llama init() al montar) con el CONTADOR de localhost vivos del proyecto: SOLO
// dev servers locales detectados en los previews de las terminales
// (NO lista terminales/agentes trabajando — pedido del usuario 2026-06-20). Solo
// APARECE cuando hay al menos un localhost (con 0 el botón se oculta).
// Al click abre un popover con la lista de localhost:
//   host:puerto + qué agente lo levantó, con ✕ para cerrar cada uno (mata el
//   proceso del puerto) y "Cerrar localhost". Click en una fila → Web Preview.
//
// Fuente de datos: GET /api/orchestrator/preview/{id}/servers → {servers}.
// Se refresca por los WS dev_server_detectado/dev_server_caido (workspace.js
// llama refrescar()), y mientras el popover está abierto se pollea solo.
// Lógica pura en _pure (testeable en Node).
//
// Expone window.JarvisDevServers = { init, cargar, refrescar, open, close,
//   toggle, _pure }.

(function (root) {

  // ── Lógica pura (sin DOM, testeable en Node) ────────────────────
  // 'http://localhost:5173/app' → 'localhost:5173'
  function hostPuerto(url) {
    try { return new URL(url).host || url; } catch { return url; }
  }
  // Cantidad de localhost activos. El botón se oculta cuando es 0.
  function total(servers) {
    return Array.isArray(servers) ? servers.length : 0;
  }
  // Etiqueta de la fila: dev server → 'localhost:5173'; demo servido por el
  // propio Jarvis → su ruta bajo /static ('wb-redesigns'), sin /index.html
  // ni query (mostrar 'localhost:3000' para todos los demos no diría nada).
  function etiqueta(s) {
    if (!s || s.tipo !== 'demo') return hostPuerto(s && s.url);
    try {
      const path = new URL(s.url).pathname
        .replace(/^\/static\//, '')
        .replace(/\/?(index\.html?)?$/i, '');
      return path || hostPuerto(s.url);
    } catch { return hostPuerto(s && s.url); }
  }

  // (El salto del preview al maximizar/seleccionar la card de un agente ya no
  //  resuelve el server acá: usa GET /preview/{pid}/terminal/{tid}/localhost,
  //  que además escanea el scrollback del pane si el snapshot quedó vacío.)
  const _pure = { hostPuerto, total, etiqueta };

  const _t = (s) => (root.JarvisI18n && root.JarvisI18n.t) ? root.JarvisI18n.t(s) : s;

  // ── A partir de acá, solo navegador ─────────────────────────────
  const _esBrowser = typeof document !== 'undefined';

  let _btn     = null;   // #jw-localhosts-btn
  let _countEl = null;   // contador dentro del botón
  let _pop     = null;   // popover (en <body>)
  let _abierto = false;
  let _montado = false;
  let _pid     = null;   // proyecto actual
  let _servers = [];     // último fetch (localhost)
  let _pollId  = null;   // interval mientras el popover está abierto

  function _svgServer() {
    return '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01"/></svg>';
  }

  function init() {
    if (!_esBrowser || _montado) return;
    _btn = document.getElementById('jw-localhosts-btn');
    if (!_btn) return;
    _montado = true;

    _btn.innerHTML = `${_svgServer()}<span class="jw-ds-count">0</span>`;
    _countEl = _btn.querySelector('.jw-ds-count');

    _pop = document.createElement('div');
    _pop.className = 'jw-ds-pop';
    _pop.setAttribute('role', 'menu');
    _pop.setAttribute('aria-label', 'Localhost activos');
    _pop.hidden = true;
    document.body.appendChild(_pop);

    _btn.addEventListener('click', (e) => { e.stopPropagation(); toggle(); });
    document.addEventListener('click', (e) => {
      if (!_abierto) return;
      if (_pop.contains(e.target) || _btn.contains(e.target)) return;
      close();
    });
    document.addEventListener('keydown', (e) => {
      if (_abierto && e.key === 'Escape') { e.stopPropagation(); close(); }
    });
    window.addEventListener('resize', () => { if (_abierto) _posicionar(); });

    _pintarBadge();
  }

  // Carga inicial / cambio de proyecto: fija el pid y trae los servers.
  function cargar(projectId) {
    _pid = projectId;
    return refrescar();
  }

  // Re-fetch de los localhost vivos del proyecto actual.
  async function refrescar() {
    if (!_montado || _pid == null) return;
    try {
      const r = await fetch(`/api/orchestrator/preview/${_pid}/servers`);
      if (r.ok) {
        const data = await r.json();
        _servers = Array.isArray(data && data.servers) ? data.servers : [];
      }
    } catch { /* server reiniciando: el próximo evento reintenta */ }
    _pintarBadge();
    if (_abierto) _render();
  }

  function _pintarBadge() {
    const n = _pure.total(_servers);
    if (_countEl) _countEl.textContent = String(n);
    // Solo aparece cuando hay un localhost activo (pedido del usuario): 0 → oculto.
    _btn.hidden = (n === 0);
    _btn.classList.toggle('jw-ds-vacio', n === 0);
    _btn.setAttribute('title', n
      ? (n === 1 ? _t('1 localhost activo') : _t('{n} localhost activos').replace('{n}', n))
      : 'Ningún localhost activo');
  }

  function _posicionar() {
    const r = _btn.getBoundingClientRect();
    _pop.style.top   = Math.round(r.bottom + 6) + 'px';
    _pop.style.right = Math.round(window.innerWidth - r.right) + 'px';
    _pop.style.left  = 'auto';
  }

  function _render() {
    if (!_pop) return;
    const n = _servers.length;

    const head = document.createElement('div');
    head.className = 'jw-ds-head';
    head.innerHTML = `
      <span class="jw-ds-title">Localhost</span>
      <span class="jw-ds-n">${n}</span>`;
    // "Cerrar localhost" cierra todos los dev servers de la lista.
    if (n) {
      const cerrarTodos = document.createElement('button');
      cerrarTodos.type = 'button';
      cerrarTodos.className = 'jw-ds-closeall';
      cerrarTodos.textContent = 'Cerrar localhost';
      cerrarTodos.addEventListener('click', _cerrarTodos);
      head.appendChild(cerrarTodos);
    }

    const list = document.createElement('div');
    list.className = 'jw-ds-list';

    if (!n) {
      const vacio = document.createElement('div');
      vacio.className = 'jw-ds-vacio-msg';
      vacio.textContent = 'Ningún localhost activo. Cuando un agente levante un dev server aparece acá.';
      list.appendChild(vacio);
    } else {
      for (const s of _servers) list.appendChild(_filaServer(s));
    }

    _pop.innerHTML = '';
    _pop.appendChild(head);
    _pop.appendChild(list);
  }

  function _filaServer(s) {
    const esDemo = s.tipo === 'demo';
    const row = document.createElement('div');
    row.className = 'jw-ds-row';
    row.setAttribute('role', 'menuitem');
    row.tabIndex = 0;
    row.title = esDemo
      ? _t('Abrir el demo {url} en el preview').replace('{url}', s.url)
      : _t('Abrir {url} en el preview').replace('{url}', s.url);

    const dot = document.createElement('span');
    dot.className = 'jw-ds-dot' + (esDemo ? ' demo' : '');

    const main = document.createElement('span');
    main.className = 'jw-ds-main';
    const host = document.createElement('span');
    host.className = 'jw-ds-host';
    host.textContent = _pure.etiqueta(s);
    if (esDemo) {
      const chip = document.createElement('span');
      chip.className = 'jw-ds-chip-demo';
      chip.textContent = 'demo';
      host.appendChild(chip);
    }
    const quien = document.createElement('span');
    quien.className = 'jw-ds-quien';
    quien.textContent = s.propio ? 'Jarvis' : (s.terminal_nombre || 'un agente');
    main.appendChild(host);
    main.appendChild(quien);

    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'jw-ds-x';
    // Demo = página servida por el PROPIO Jarvis: el ✕ solo la saca del menú,
    // no hay ningún proceso que matar (el 3000 es el workspace).
    x.title = esDemo ? 'Ocultar este demo (no cierra ningún proceso)'
                     : 'Cerrar este server (mata el proceso del puerto)';
    x.setAttribute('aria-label', esDemo
      ? _t('Ocultar {etiqueta}').replace('{etiqueta}', _pure.etiqueta(s))
      : _t('Cerrar {host}').replace('{host}', _pure.hostPuerto(s.url)));
    x.innerHTML = (typeof icon === 'function') ? icon('x', 13) : '×';
    x.addEventListener('click', (e) => { e.stopPropagation(); _cerrarUno(s); });

    row.appendChild(dot);
    row.appendChild(main);
    row.appendChild(x);
    row.addEventListener('click', () => _abrirEnPreview(s.url));
    row.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); _abrirEnPreview(s.url); }
    });
    return row;
  }

  function _abrirEnPreview(url) {
    root.JarvisDock?.open?.('preview');
    const pane = document.getElementById('jw-pane-preview');
    root.WebPreview?.init?.(pane);
    // abrirLink reusa la pestaña del mismo ORIGEN (misma URL → recarga fresca,
    // otra ruta → la navega) — mismo comportamiento que el click de un link
    // localhost en la terminal. openTab queda de fallback.
    (root.WebPreview?.abrirLink || root.WebPreview?.openTab || (() => {}))(url);
    close();
  }

  async function _stop(url) {
    try {
      const r = await fetch(`/api/orchestrator/preview/${_pid}/stop`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      return r.ok ? (await r.json().catch(() => ({}))) : null;
    } catch { return null; }
  }

  async function _cerrarUno(s) {
    // Ocultar un demo es inofensivo (no toca procesos) → sin confirmación.
    if (s.tipo !== 'demo') {
      const ok = (typeof confirmar === 'function')
        ? await confirmar(_t('¿Cerrar el server de {host}? Se va a terminar el proceso.').replace('{host}', _pure.hostPuerto(s.url)),
                          { titulo: 'Cerrar server', peligro: true, confirmText: 'Cerrar server' })
        : true;
      if (!ok) return;
    }
    const res = await _stop(s.url);
    if (typeof toast === 'function') {
      toast(res && res.mensaje ? res.mensaje
        : (s.tipo === 'demo' ? 'Demo oculto' : 'Server cerrado'), 'success');
    }
    await refrescar();
  }

  async function _cerrarTodos() {
    const n = _servers.length;
    if (!n) return;
    // Solo los servers con proceso ameritan confirmación; los demos se ocultan.
    const conProceso = _servers.filter((s) => s.tipo !== 'demo').length;
    if (conProceso) {
      const ok = (typeof confirmar === 'function')
        ? await confirmar(conProceso === 1
            ? _t('¿Cerrar el localhost activo? Se va a terminar el proceso. Los demos solo se ocultan.')
            : _t('¿Cerrar los {n} localhost activos? Se van a terminar los procesos. Los demos solo se ocultan.').replace('{n}', conProceso),
                          { titulo: 'Cerrar localhost', peligro: true, confirmText: 'Cerrar todos' })
        : true;
      if (!ok) return;
    }
    for (const s of _servers.slice()) await _stop(s.url);
    if (typeof toast === 'function') toast('Localhost cerrados', 'success');
    await refrescar();
  }

  function open() {
    if (!_montado || _abierto) return;
    _render();
    _pop.hidden = false;
    _posicionar();
    _abierto = true;
    _btn.classList.add('activo');
    _btn.setAttribute('aria-expanded', 'true');
    refrescar();   // datos frescos al abrir
    // Mientras está abierto, los títulos de los agentes cambian sin WS → pollear.
    clearInterval(_pollId);
    _pollId = setInterval(refrescar, 2500);
  }

  function close() {
    if (!_abierto) return;
    _pop.hidden = true;
    _abierto = false;
    _btn.classList.remove('activo');
    _btn.setAttribute('aria-expanded', 'false');
    clearInterval(_pollId);
    _pollId = null;
  }

  function toggle() { _abierto ? close() : open(); }

  root.JarvisDevServers = { init, cargar, refrescar, open, close, toggle, _pure };

  if (typeof module !== 'undefined' && module.exports) module.exports = root.JarvisDevServers;

})(typeof window !== 'undefined' ? window : globalThis);
