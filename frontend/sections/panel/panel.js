// JARVIS — JarvisDock: el Panel Único dockeado a la derecha del mosaico.
// Header de pestañas (solo iconos) + splitter contra las terminales + maximizar.
// Espeja el patrón window.JarvisEditor / window.TerminalLayout: lógica pura
// (sin DOM, testeable en Node) + motor DOM (solo navegador). Los contenidos de
// cada pestaña NO se reescriben: sus contenedores ya viven en workspace.html y
// se alternan con el atributo `hidden` (display:none) — NUNCA animar width.
(function (global) {
  'use strict';

  // ── Constantes ────────────────────────────────────────────────────
  const DEFAULT_W = 320, MIN_W = 300, MAX_FRAC = 0.70;   // 340→320: +20px para terminales por defecto (la persistencia del usuario manda)
  const DEFAULT_TAB = 'preview';
  // Pestañas donde ⤢ (maximizar) tiene sentido (contrato §2.4).
  // 'jarvis' incluido: el orquestador se despliega a pantalla completa (su
  // layout es editorial-responsive por container-query) además de vivir
  // angosto en el dock como panel lateral.
  const MAXIMIZABLE = new Set(['preview', 'jarvis']);   // 'editor' retirado del dock (→ editor deslizante)

  // ── Lógica pura (sin DOM) ──────────────────────────────────────────
  // clampWidth: el dock vive entre MIN_W y MAX_FRAC del ancho del contenido.
  // El tope nunca baja de MIN_W (contenedor angosto → gana el mínimo usable).
  function clampWidth(px, contentW) {
    const max = Math.max(MIN_W, Math.round((contentW || 0) * MAX_FRAC));
    return Math.min(max, Math.max(MIN_W, Math.round(px)));
  }

  // resolveAgentWidth: al maximizar una card de terminal (un agente a pantalla
  // completa), ¿qué ancho toma el dock? Si el usuario YA ensanchó el panel dentro
  // de la pantalla completa de ESE agente, hay un `saved` → se usa. Si NUNCA lo
  // tocó ahí (saved null/NaN), se deja el ancho base — "como estaba". Clampea
  // contra el contenido. Esta es la regla que pidió el usuario: recordar el ancho
  // por-agente sólo si realmente usó el panel para agrandarlo.
  function resolveAgentWidth(saved, baseWidth, contentW) {
    const w = (saved == null || Number.isNaN(saved)) ? baseWidth : saved;
    return clampWidth(w, contentW);
  }

  // resolveAgentTab: al maximizar una card, ¿qué pestaña muestra el dock? Si hay
  // una pestaña recordada para ESE agente (la última que dejó en su pantalla
  // completa) Y sigue siendo visible ahora → esa. Si nunca cambió de pestaña ahí
  // (saved vacío) o quedó oculta (ej. 'mobile' en un proyecto que ya no es Expo)
  // → la pestaña base, la "normal" donde están los demás. Mismo criterio que el
  // ancho: sólo se respeta el recuerdo si el usuario realmente lo generó.
  function resolveAgentTab(saved, baseTab, visible) {
    if (saved && (!visible || visible[saved] !== false)) return saved;
    return baseTab;
  }

  // resolveAgentOpen: al maximizar una card, ¿el dock abierto o cerrado? Si hay
  // estado recordado para ESE agente ('1'/'0', porque el usuario lo abrió/cerró
  // en su pantalla completa) → ese. Si no → como estaba (la base). Mismo criterio
  // que ancho/pestaña: sólo se respeta el recuerdo si el usuario lo generó.
  function resolveAgentOpen(saved, baseOpen) {
    if (saved === '1') return true;
    if (saved === '0') return false;
    return baseOpen;
  }

  // badgeTotal: suma de todos los badges de pestaña (alimenta el badge del ▣).
  function badgeTotal(badges) {
    let t = 0;
    for (const k in badges) t += (badges[k] | 0);
    return t;
  }

  // ¿La pestaña está realmente "vista" ahora mismo? (dock abierto y activa).
  function _activaVisible(s, tab) { return s.open && s.tab === tab; }

  // restoreTab: decide la pestaña activa al restaurar + si queda una "pendiente".
  // La pestaña deseada (persistida) puede estar OCULTA en este instante porque
  // su visibilidad real se resuelve async DESPUÉS del restore (ej. 'mobile' se
  // habilita recién cuando se detecta que el proyecto es Expo). En vez de
  // degradarla a DEFAULT y PERDER el deseo del usuario, la marcamos como
  // `pending`: cuando esa pestaña se vuelva visible la re-activamos (ver el
  // método setTabVisible del motor DOM). Si nunca lo hace (proyecto no-Expo, u
  // 'web' que es overlay y jamás recibe setTabVisible(true)), queda en DEFAULT.
  function restoreTab(persistedTab, visible) {
    const tab = persistedTab || DEFAULT_TAB;
    if (visible && visible[tab] === false) return { tab: DEFAULT_TAB, pending: tab };
    return { tab, pending: null };
  }

  // resolveMobileVisible: visibilidad de la pestaña Móvil al RESTAURAR, decidida
  // SINCRÓNICAMENTE (sin esperar la detección async de Expo). Sin esto el restore
  // caía a 'preview' y recién la detección la cambiaba a Móvil → el usuario veía
  // "primero Web preview y después salta a Móvil" (flash). Prioridad:
  //   1. cache por-proyecto ('1'/'0') = última Expo-ness conocida (escrita por
  //      _persist cuando la detección corrió la última vez) → restaura DIRECTO.
  //   2. sin cache (1ra visita post-update): inferir del tab persistido — si
  //      dejaste 'mobile' como activa, el proyecto ERA Expo (no podés activar una
  //      pestaña oculta), así que la mostramos directo igual.
  //   3. sin señal: oculta. NUNCA arrastramos el valor del proyecto ANTERIOR
  //      (mostraría Móvil en un no-Expo al venir de uno Expo); la detección async
  //      la prende si corresponde. Si la Expo-ness cambió (raro), también corrige.
  function resolveMobileVisible(cached, persistedTab) {
    if (cached === '1') return true;
    if (cached === '0') return false;
    return persistedTab === 'mobile';
  }

  // nextState: reductor PURO. Devuelve un estado NUEVO (no muta la entrada).
  function nextState(state, action) {
    const s = {
      open: state.open, tab: state.tab, width: state.width,
      maximized: state.maximized,
      badges: Object.assign({}, state.badges),
      visible: Object.assign({}, state.visible),
    };
    switch (action.type) {
      case 'open': {
        s.open = true;
        // No abrir en una pestaña explícitamente oculta (ej: 'mobile' en un
        // proyecto no-Expo): se respeta la tab actual/default en su lugar.
        if (action.tab && s.visible[action.tab] !== false) s.tab = action.tab;
        // abrir limpia el badge de la pestaña que queda activa
        s.badges[s.tab] = 0;
        if (!MAXIMIZABLE.has(s.tab)) s.maximized = false;
        return s;
      }
      case 'close':
        s.open = false; s.maximized = false; return s;
      case 'toggle':
        return nextState(s, { type: s.open ? 'close' : 'open' });
      case 'setTab': {
        // No activar una pestaña explícitamente oculta (ej. 'mobile' persistida
        // de un proyecto Expo, restaurada en uno que no lo es).
        if (s.visible[action.tab] === false) return s;
        s.open = true;
        s.tab = action.tab;
        s.badges[action.tab] = 0;              // verla la marca como leída
        if (!MAXIMIZABLE.has(s.tab)) s.maximized = false;
        return s;
      }
      case 'notify': {
        const n = (action.n == null) ? 1 : action.n;
        if (_activaVisible(s, action.tab)) return s;   // ya la está mirando
        s.badges[action.tab] = (s.badges[action.tab] | 0) + n;
        return s;
      }
      case 'setMax':
        if (!MAXIMIZABLE.has(s.tab)) { s.maximized = false; return s; }
        s.maximized = !!action.value; return s;
      case 'setWidth':
        s.width = clampWidth(action.px, action.contentW); return s;
      case 'resetWidth':
        s.width = DEFAULT_W; return s;
      case 'setTabVisible': {
        s.visible[action.tab] = !!action.value;
        // si oculto la pestaña activa, caigo a la default (cualquier falsy oculta)
        if (!action.value && s.tab === action.tab) {
          s.tab = DEFAULT_TAB;
          if (!MAXIMIZABLE.has(s.tab)) s.maximized = false;
        }
        return s;
      }
      default:
        return s;
    }
  }

  const pure = { nextState, badgeTotal, clampWidth, resolveAgentWidth, resolveAgentTab, resolveAgentOpen, restoreTab, resolveMobileVisible, DEFAULT_W, MIN_W, MAX_FRAC, DEFAULT_TAB, MAXIMIZABLE };

  // Superficie pública mínima (el motor DOM la completa en Task 21).
  global.JarvisDock = Object.assign(global.JarvisDock || {}, { _pure: pure });

  // ── Motor DOM (solo navegador) ─────────────────────────────────────
  if (typeof document !== 'undefined') {
    let _projectId = null;
    let _cb = {};                         // { onTabShown, onResized }
    // Pestaña deseada al restaurar pero OCULTA en ese instante (su visibilidad
    // se resuelve async; ej. 'mobile' espera la detección de Expo). La re-activa
    // setTabVisible(...,true) cuando aparece. La limpia cualquier selección
    // explícita del usuario (no queremos arrastrarlo de vuelta si ya navegó).
    let _pendingTab = null;
    // Contexto "agente a pantalla completa": cuando una card de terminal está
    // maximizada, el ancho del dock puede diferir del normal y se recuerda POR
    // AGENTE. _maxAgentId = id de la terminal maximizada (o null si ninguna).
    // _baseWidth = ancho normal a restaurar al salir de la pantalla completa
    // (espeja el K_WIDTH global). _baseTab = pestaña "normal" (la de los demás) a
    // restaurar al salir. Ver enterAgentFullscreen/exitAgentFullscreen.
    let _maxAgentId = null;
    let _baseWidth = DEFAULT_W;
    let _baseTab = DEFAULT_TAB;
    let _baseOpen = false;   // abierto/cerrado "normal" a restaurar al salir de la pantalla completa
    let _state = {
      open: false, tab: DEFAULT_TAB, width: DEFAULT_W, maximized: false,
      // web: false — el builder salió del dock (overlay #jw-webbuilder).
      // NO quitar la clave: 'visible salvo false explícito' — con false,
      // un jarvis.dock.tab persistido en 'web' degrada a DEFAULT_TAB.
      // editor: false — el editor Monaco salió del dock; lo reemplaza el editor
      // deslizante (#jw-editor / window.JarvisSlideEditor). Con false, un
      // jarvis.dock.tab persistido en 'editor' degrada a DEFAULT_TAB.
      badges: {}, visible: { mobile: false, preview: true, jarvis: true,
        editor: false, tasks: true, review: true, web: false },
    };
    let _wired = false;

    const $ = (id) => document.getElementById(id);
    const _dock = () => $('jw-dock');
    const _content = () => $('jw-content');
    const _contentW = () => (_content() ? _content().clientWidth : 0);

    // ── localStorage (claves del contrato) ──────────────────────────
    const _kOpen  = () => `jarvis.dock.open.${_projectId}`;
    const _kTab   = () => `jarvis.dock.tab.${_projectId}`;
    // Cache por-proyecto de la visibilidad de la pestaña Móvil (= Expo-ness). Se
    // lee en _restore para mostrar Móvil DIRECTO, sin esperar la detección async
    // (que causaba el flash preview→mobile). La escribe _persist con el último
    // valor conocido (lo fija setTabVisible desde consultarMobilePreview).
    const _kMVis  = () => `jarvis.dock.mvis.${_projectId}`;
    const K_WIDTH = 'jarvis.dock.width';   // legado: fallback para proyectos sin ancho propio
    // Ancho POR PROYECTO (pedido 2026-07-07): ensanchar el panel en un proyecto
    // no debe ensancharlo en los demás. El K_WIDTH global queda como default
    // heredado (solo lectura) para proyectos que aún no tienen ancho propio.
    const _kWidth = () => `jarvis.dock.width.${_projectId}`;
    // Ancho del dock recordado POR AGENTE (terminal) para su pantalla completa.
    // Clave por id de terminal (los ids son únicos globalmente). Sólo existe si el
    // usuario ensanchó el panel dentro de la pantalla completa de ESE agente.
    const _kAgentW = (id) => `jarvis.dock.agentw.${id}`;
    // Pestaña del dock recordada POR AGENTE para su pantalla completa (idéntico
    // criterio que _kAgentW). Sólo existe si el usuario cambió de pestaña ahí.
    const _kAgentTab = (id) => `jarvis.dock.agenttab.${id}`;
    // Abierto/cerrado del dock recordado POR AGENTE para su pantalla completa
    // ('1'/'0'). Sólo existe si el usuario abrió/cerró el panel estando ahí.
    const _kAgentOpen = (id) => `jarvis.dock.agentopen.${id}`;
    // (La franja usa 'jarvis.strip.hidden' pero la maneja la Fase 1; el dock no.)

    function _persist() {
      try {
        // open/tab son por-proyecto: no escribir basura bajo '.null' antes de setProject.
        if (_projectId != null) {
          // El abierto/cerrado BASE (el "normal") y la pestaña BASE sólo se escriben
          // FUERA del contexto de agente maximizado. En contexto, ambos viven
          // por-agente y los persiste _dispatch ante un cambio REAL — así no pisamos
          // la base ni creamos un override que el usuario no generó.
          if (_maxAgentId == null) {
            localStorage.setItem(_kOpen(), _state.open ? '1' : '0');
            localStorage.setItem(_kTab(), _state.tab);
          }
          localStorage.setItem(_kMVis(), _state.visible.mobile === false ? '0' : '1');
        }
        // El ancho (POR PROYECTO) sólo se escribe fuera del contexto de agente
        // maximizado. Dentro de ese contexto el ancho vive por-agente y lo
        // persiste, sólo en acciones REALES de resize del usuario,
        // _commitWidthPersist() — así no pisamos la base ni creamos un override
        // que el usuario no pidió.
        if (_maxAgentId == null && _projectId != null) {
          localStorage.setItem(_kWidth(), String(_state.width));
        }
      } catch (_) {}
    }

    // Persiste el ancho actual en el destino correcto: por-agente si hay una card
    // maximizada, global si no. Lo llaman SÓLO los gestos de resize del usuario
    // (soltar el splitter, doble-click de reset) — no el _persist() general.
    function _commitWidthPersist() {
      try {
        if (_maxAgentId != null) {
          localStorage.setItem(_kAgentW(_maxAgentId), String(_state.width));
        } else {
          // Resize real del usuario: al ancho de ESTE proyecto (no al global).
          if (_projectId != null) localStorage.setItem(_kWidth(), String(_state.width));
          _baseWidth = _state.width;   // el ancho normal cambió → nueva base
        }
      } catch (_) {}
    }

    // Carga el estado open/tab/ancho del proyecto actual (todo por-proyecto;
    // el ancho cae al K_WIDTH global heredado si el proyecto no tiene el suyo).
    function _restore() {
      let width = DEFAULT_W;
      try {
        let w = _projectId != null ? parseInt(localStorage.getItem(_kWidth()), 10) : NaN;
        if (Number.isNaN(w)) w = parseInt(localStorage.getItem(K_WIDTH), 10);
        // Con el DOM sin medir (_contentW()=0) NO clampear contra el 70%:
        // colapsaría cualquier ancho guardado a MIN_W. Se re-clampea al render.
        if (!Number.isNaN(w)) {
          const cw = _contentW();
          width = cw ? clampWidth(w, cw) : Math.max(MIN_W, Math.round(w));
        }
      } catch (_) {}
      let open = false, persisted = DEFAULT_TAB, mvisCache = null;
      // Las claves open/tab son por-proyecto: sin _projectId (init antes de
      // setProject) NO leer 'jarvis.dock.*.null' — el width sí es global y ya cargó.
      if (_projectId != null) try {
        open = localStorage.getItem(_kOpen()) === '1';
        const t = localStorage.getItem(_kTab());
        if (t) persisted = t;
        mvisCache = localStorage.getItem(_kMVis());
      } catch (_) {}
      // Resolver la visibilidad de Móvil SINCRÓNICAMENTE (cache por-proyecto +
      // inferencia del tab persistido) para restaurar DIRECTO a Móvil sin el flash
      // preview→mobile. La detección async después confirma (o corrige si la
      // Expo-ness cambió). maximized arranca siempre en false.
      const visible = Object.assign({}, _state.visible,
        { mobile: resolveMobileVisible(mvisCache, persisted) });
      // restoreTab: si aun así la tab deseada quedó oculta (ej. 'web' overlay),
      // cae a DEFAULT pero la recuerda como PENDIENTE; setTabVisible(...,true) la
      // re-activa si alguna vez aparece (red de seguridad de la carrera async).
      const r = restoreTab(persisted, visible);
      _pendingTab = r.pending;
      _state = { open, tab: r.tab, width, maximized: false,
        badges: {}, visible };
      // Restaurar (init o cambio de proyecto) sale de cualquier contexto de agente
      // maximizado: ancho/pestaña/abierto vuelven a ser los globales y son la base.
      _maxAgentId = null;
      _baseWidth = width;
      _baseTab = r.tab;
      _baseOpen = open;
    }

    // ── Dispatch: aplica una acción pura y re-renderiza ─────────────
    function _dispatch(action) {
      const prev = _state;
      _state = nextState(_state, action);
      _render(prev);
      _persist();
      // En la pantalla completa de un agente, un cambio REAL de pestaña o de
      // abierto/cerrado se recuerda por-agente (no toca la base, que la restaura
      // _exitAgentContext al salir). Sólo se crea el override de lo que cambió.
      if (_maxAgentId != null) {
        try {
          if (prev.tab !== _state.tab) localStorage.setItem(_kAgentTab(_maxAgentId), _state.tab);
          if (prev.open !== _state.open) localStorage.setItem(_kAgentOpen(_maxAgentId), _state.open ? '1' : '0');
        } catch (_) {}
      }
    }

    // ── Render: vuelca el estado al DOM del contrato ────────────────
    function _render(prev) {
      const dock = _dock();
      if (!dock) return;

      // Visibilidad del dock + splitter
      dock.hidden = !_state.open;
      const splitter = $('jw-dock-splitter');
      if (splitter) splitter.hidden = !_state.open || _state.maximized;

      // Ancho (px inline; NUNCA transición de width — regla xterm).
      // Maximizado: sin width inline para que mande el CSS de .jw-dock--max.
      dock.style.width = _state.maximized ? '' : (_state.width + 'px');

      // Maximizado: clase que lo lleva a position:fixed inset:0 (CSS)
      dock.classList.toggle('jw-dock--max', _state.maximized);

      // Pestañas: visibilidad (hidden), activa, badge por pestaña
      document.querySelectorAll('.jw-tab').forEach((btn) => {
        const tab = btn.dataset.tab;
        const vis = _state.visible[tab] !== false;
        btn.hidden = !vis;
        btn.classList.toggle('activa', _state.open && _state.tab === tab);
        btn.setAttribute('aria-selected', (_state.open && _state.tab === tab) ? 'true' : 'false');
        const b = btn.querySelector('.jw-badge');
        if (b) {
          const n = _state.badges[tab] | 0;
          b.textContent = n > 99 ? '99+' : String(n);
          b.hidden = n === 0;
        }
      });

      // Panes: solo el activo visible (display:none vía hidden)
      document.querySelectorAll('.jw-pane').forEach((p) => {
        p.hidden = !(_state.open && p.dataset.pane === _state.tab);
      });

      // ⤢ visible solo en editor|preview; ✕ siempre
      const max = $('jw-dock-max');
      if (max) {
        max.hidden = !MAXIMIZABLE.has(_state.tab);
        max.classList.toggle('activo', _state.maximized);
        max.setAttribute('aria-pressed', _state.maximized ? 'true' : 'false');
      }

      // ↗ "Abrir en pestaña de navegador": solo con el editor a la vista
      const ext = $('jw-dock-external');
      if (ext) ext.hidden = !(_state.open && _state.tab === 'editor');

      // Toggle ▣ del bar: estado on/off + badge suma
      const toggle = $('jw-dock-toggle');
      if (toggle) {
        toggle.classList.toggle('activo', _state.open);
        toggle.setAttribute('aria-pressed', _state.open ? 'true' : 'false');
      }
      const tbadge = $('jw-dock-badge');
      if (tbadge) {
        const total = badgeTotal(_state.badges);
        tbadge.textContent = total > 99 ? '99+' : String(total);
        tbadge.hidden = total === 0;
      }

      // Callbacks de relayout/refit: se disparan cuando cambia algo que
      // afecta el espacio del mosaico o el contenido de un pane.
      const abrioOcerro = !prev || prev.open !== _state.open || prev.maximized !== _state.maximized
        || prev.width !== _state.width;
      // "Pane recién visible": cambia la tab O el dock se abre — en ambos
      // casos el contenido necesita su refit (Monaco/iframe), a propósito.
      const cambioTab = !prev || prev.tab !== _state.tab || prev.open !== _state.open;

      if (abrioOcerro) {
        // El mosaico se re-adapta solo (ResizeObserver), pero forzamos refit.
        global.TerminalLayout?.relayoutAll?.();
        _cb.onResized?.();
      }
      if (cambioTab && _state.open) {
        _cb.onTabShown?.(_state.tab);
      }

      // Maximizar/restaurar: refit del contenido del pane activo (Task 29).
      // onResized (arriba) ya dispara un relayout síncrono, pero al pasar a
      // position:fixed el layout se asienta recién tras el reflow del fixed;
      // dos pasadas diferidas evitan franjas muertas en entornos más lentos.
      const cambioMax = !prev || prev.maximized !== _state.maximized;
      if (cambioMax && _state.open) {
        if (_state.tab === 'editor') {
          requestAnimationFrame(() => global.JarvisEditor?.relayout?.());
          setTimeout(() => global.JarvisEditor?.relayout?.(), 240);
        }
        // preview (iframe): no requiere refit (spec §4.1).
      }
    }

    // _El toggle de la franja es de la Fase 1 — JarvisDock no lo toca._
    // (La franja, su botón #jw-strip-hide, el atajo Ctrl+B, la persistencia
    //  'jarvis.strip.hidden' y la clase body.jw-strip-off los implementa
    //  workspace.js en la Fase 1 Task 3. Acá NO se redefine nada de eso.)

    // ── Splitter (drag horizontal) — patrón terminal-layout.js:284-340 ─
    let _rz = null;
    function _onSplitterDown(e) {
      if (_state.maximized) return;
      e.preventDefault(); e.stopPropagation();
      e.currentTarget.setPointerCapture?.(e.pointerId);
      // Marcar la interacción en TerminalLayout: durante el drag SOLO se
      // re-renderiza el mosaico (las cards siguen al mouse); ningún fit ni
      // resize viaja a tmux hasta soltar. Sin esto, relayoutAll() refiteaba
      // por frame → resize+SIGWINCH por frame → el TUI (Claude Code) redibuja
      // su banner en cada uno y tritura el scrollback. Mismo patrón que los
      // divisores internos del grid (terminal-layout.js _onDividerDown).
      global.TerminalLayout?.setInteracting?.(true);
      _rz = { startX: e.clientX, baseW: _state.width, raf: 0 };
      document.addEventListener('pointermove', _onSplitterMove);
      document.addEventListener('pointerup', _onSplitterUp, { once: true });
      // pointercancel: gesto interrumpido (touch/menú contextual) — sin esto
      // quedaría colgado el pointermove en document y la clase jw-resizing.
      document.addEventListener('pointercancel', _onSplitterUp, { once: true });
      document.body.classList.add('jw-resizing');
    }
    function _onSplitterMove(e) {
      if (!_rz) return;
      // El dock está a la DERECHA: arrastrar a la izquierda lo agranda. El delta
      // llega en píxeles de PANTALLA y el ancho se escribe en píxeles CSS: con la
      // Escala puesta hay que traducirlo o el borde se escapa del cursor (a 125%
      // el dock crecía 125px por cada 100 de arrastre).
      const dx = global.JarvisEscala?.aCss?.(_rz.startX - e.clientX) ?? (_rz.startX - e.clientX);
      const px = clampWidth(_rz.baseW + dx, _contentW());
      _state = Object.assign({}, _state, { width: px });
      const dock = _dock();
      if (dock) dock.style.width = px + 'px';   // px directos, sin transición
      // Re-render del mosaico throttleado por rAF mientras se arrastra
      // (con setInteracting(true), relayoutAll() solo renderiza — no refitea).
      if (_rz.raf) cancelAnimationFrame(_rz.raf);
      _rz.raf = requestAnimationFrame(() => {
        _rz.raf = 0;
        global.TerminalLayout?.relayoutAll?.();
      });
    }
    function _onSplitterUp() {
      if (!_rz) return;
      if (_rz.raf) cancelAnimationFrame(_rz.raf);
      _rz = null;
      document.removeEventListener('pointermove', _onSplitterMove);
      document.removeEventListener('pointerup', _onSplitterUp);
      document.removeEventListener('pointercancel', _onSplitterUp);
      document.body.classList.remove('jw-resizing');
      // Resize real del usuario: persiste el ancho al destino correcto (por-agente
      // si hay una card maximizada, global si no).
      _commitWidthPersist();
      // Liberar la interacción ANTES del relayout: este es el refit ÚNICO
      // del drag (un solo resize a tmux, un solo redraw del TUI).
      global.TerminalLayout?.setInteracting?.(false);
      // Refit forzado al soltar (mosaico + contenido del pane activo).
      global.TerminalLayout?.relayoutAll?.();
      _cb.onResized?.();
      if (_state.tab === 'editor') global.JarvisEditor?.relayout?.();
    }

    // ── Wire único de todos los controles del dock/strip ────────────
    function _wire() {
      if (_wired) return;
      _wired = true;

      // Pestañas
      document.querySelectorAll('.jw-tab').forEach((btn) => {
        btn.addEventListener('click', () => {
          _pendingTab = null;   // elección explícita: cancela cualquier restore pendiente
          _dispatch({ type: 'setTab', tab: btn.dataset.tab });
        });
      });
      // Acciones del header del dock
      $('jw-dock-close')?.addEventListener('click', () => _dispatch({ type: 'close' }));
      $('jw-dock-max')?.addEventListener('click', () => _dispatch({ type: 'setMax', value: !_state.maximized }));
      $('jw-dock-external')?.addEventListener('click', () => {
        if (_projectId) global.open(`/editor?project=${encodeURIComponent(_projectId)}`, '_blank');
      });
      // Toggle ▣ del bar
      $('jw-dock-toggle')?.addEventListener('click', () => _dispatch({ type: 'toggle' }));
      // (La franja —#jw-strip-hide / #jw-strip-home y Ctrl+B— la maneja la Fase 1;
      //  JarvisDock no cablea esos controles.)
      // Splitter
      const sp = $('jw-dock-splitter');
      if (sp) {
        sp.addEventListener('pointerdown', _onSplitterDown);
        sp.addEventListener('dblclick', () => { _dispatch({ type: 'resetWidth' }); _commitWidthPersist(); });
      }
    }

    // ── Contexto de agente a pantalla completa ──────────────────────
    // Cuando se maximiza una card de terminal, el dock toma el ANCHO y la PESTAÑA
    // recordados para ESE agente (si el usuario los cambió ahí antes); si no, deja
    // los base — el ancho y la pestaña "normales", donde están los demás. Al
    // restaurar la card, el dock vuelve a esa base. El override por-agente se crea
    // SÓLO con una acción real del usuario dentro del contexto: arrastrar el
    // splitter (ancho → _commitWidthPersist) o cambiar de pestaña (→ _dispatch).
    // Si no tocó nada, no hay override y el agente re-maximiza con lo normal.
    function _applyDockShape(width, tab, open) {
      if (width === _state.width && tab === _state.tab && open === _state.open) return;
      const prev = _state;
      const badges = Object.assign({}, _state.badges);
      // Ver la pestaña la marca leída: cambio de pestaña con el dock abierto, o
      // el dock ABRIÉNDOSE sobre ella (espeja el 'open' del reductor nextState).
      if (open && (tab !== _state.tab || !_state.open)) badges[tab] = 0;
      _state = Object.assign({}, _state, { width, tab, open, badges });
      _render(prev);  // relayout del mosaico (ancho) + abrir/cerrar + paneles/onTabShown (pestaña), en una pasada
    }

    function _enterAgentContext(id) {
      if (id == null) return;
      id = String(id);
      if (_maxAgentId === id) return;
      // La base se captura al entrar DESDE el modo normal. En un cambio directo
      // entre cards maximizadas (A→B) la base ya está fijada: no re-capturar el
      // ancho/pestaña/abierto de A (podrían ser sus overrides) como base.
      if (_maxAgentId == null) { _baseWidth = _state.width; _baseTab = _state.tab; _baseOpen = _state.open; }
      _maxAgentId = id;
      let savedW = null;
      try { const v = parseInt(localStorage.getItem(_kAgentW(id)), 10); if (!Number.isNaN(v)) savedW = v; } catch (_) {}
      let savedTab = null, savedOpen = null;
      try { savedTab = localStorage.getItem(_kAgentTab(id)); savedOpen = localStorage.getItem(_kAgentOpen(id)); } catch (_) {}
      _applyDockShape(
        resolveAgentWidth(savedW, _baseWidth, _contentW()),
        resolveAgentTab(savedTab, _baseTab, _state.visible),
        resolveAgentOpen(savedOpen, _baseOpen),
      );
    }

    function _exitAgentContext() {
      if (_maxAgentId == null) return;
      _maxAgentId = null;
      // Volver a la base. Guard: si la pestaña base quedó oculta (Expo-ness cambió
      // durante la pantalla completa, muy raro), caer a la default.
      const tab = (_baseTab && _state.visible[_baseTab] === false) ? DEFAULT_TAB : _baseTab;
      _applyDockShape(clampWidth(_baseWidth, _contentW()), tab, _baseOpen);
    }

    // ── Superficie pública (contrato) ───────────────────────────────
    Object.assign(global.JarvisDock = global.JarvisDock || {}, {
      _pure: pure,
      init(cb) {
        _cb = cb || {};
        _wire();
        _restore();
        _render(null);
      },
      open(tab)  { if (tab) _pendingTab = null; _dispatch({ type: 'open', tab }); },
      close()    { _dispatch({ type: 'close' }); },
      toggle()   { _dispatch({ type: 'toggle' }); },
      setTab(t)  { _pendingTab = null; _dispatch({ type: 'setTab', tab: t }); },
      notify(t, n = 1) { _dispatch({ type: 'notify', tab: t, n }); },
      setTabVisible(t, v) {
        _dispatch({ type: 'setTabVisible', tab: t, value: v });
        // Resolver el restore pendiente: si esta pestaña RECIÉN se vuelve visible
        // y era la que el usuario tenía activa al salir (guardada en _pendingTab),
        // re-activarla. Esto cierra la carrera entre el restore síncrono y la
        // detección async de visibilidad (la pestaña Móvil aparece al detectar
        // Expo). Con el dock abierto la mostramos; cerrado, solo fijamos la
        // pestaña (sin abrir) para que el próximo open caiga ahí.
        if (v && _state.visible[t] !== false && _pendingTab === t) {
          _pendingTab = null;
          if (_state.open) { _dispatch({ type: 'setTab', tab: t }); }
          else {
            // Dock cerrado: solo fijamos la pestaña deseada (sin relayout: no cambia
            // nada visible). Pasamos el prev real para que _render no fuerce un
            // relayout del mosaico cuando ni open/width/max cambiaron.
            const prev = _state;
            _state = Object.assign({}, _state, { tab: t });
            _render(prev); _persist();
          }
        }
      },
      setMaximized(v) { _dispatch({ type: 'setMax', value: v }); },
      // Pantalla completa de un AGENTE (card de terminal maximizada). No confundir
      // con setMaximized (que maximiza el propio dock). Ver _enterAgentContext.
      enterAgentFullscreen(id) { _enterAgentContext(id); },
      exitAgentFullscreen()    { _exitAgentContext(); },
      // Salto PROGRAMÁTICO a una pestaña (ej: el localhost del agente al
      // maximizar su card): abre el dock y la activa SIN persistir la base ni
      // crear override por-agente — esos recuerdos se reservan a acciones
      // reales del usuario (contrato de _enterAgentContext). Al restaurar la
      // card, _exitAgentContext vuelve a la base como si esto no hubiera pasado.
      revealTab(tab) {
        if (!tab || _state.visible[tab] === false) return;
        _applyDockShape(_state.width, tab, true);
      },
      forgetAgentFullscreen(id) {
        // La terminal se eliminó: si estaba maximizada, salir del contexto; y
        // borrar su ancho/pestaña recordados para no acumular claves muertas.
        if (id != null && _maxAgentId === String(id)) _exitAgentContext();
        try { if (id != null) { localStorage.removeItem(_kAgentW(id)); localStorage.removeItem(_kAgentTab(id)); localStorage.removeItem(_kAgentOpen(id)); } } catch (_) {}
      },
      isOpen()   { return _state.open; },
      activeTab(){ return _state.open ? _state.tab : null; },
      isMaximized() { return _state.maximized; },
      // Al cambiar de proyecto: re-apuntar y restaurar open/tab del nuevo.
      onProjectChanged(projectId) {
        _projectId = String(projectId);
        _restore();
        _render(null);
        if (_state.open) _cb.onTabShown?.(_state.tab);
      },
      // Primer init de proyecto (lo llama workspace.js tras conocer projectId).
      setProject(projectId) { _projectId = String(projectId); _restore(); _render(null); },
    });
  }

  // ── Export para Node (tests) ───────────────────────────────────────
  if (typeof module !== 'undefined' && module.exports) module.exports = pure;
})(typeof window !== 'undefined' ? window : globalThis);
