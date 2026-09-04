// JARVIS — Temas de color + tonalidad global. Lógica pura testeable en Node + aplicación DOM.
// El tema vive en html[data-theme] (mismo elemento que :root), para que las derivadas
// color-mix y los aliases legacy trackeen el acento; 'violeta' es el default (sin atributo).
// La tonalidad (Apariencia → Tonalidad) ajusta los tokens OKLCH del tema activo con
// overrides inline en <html> — nunca toca tokens.css y se re-aplica al cambiar de tema.
(function (global) {
  'use strict';

  // 24 temas, cada uno con su bloque html[data-theme] en tokens.css. La colección
  // 2026-07-10 reemplazó indigo/cian/ambar/bordo (casi duplicados) por 6 ejes nuevos;
  // el mismo día entraron bosque/petroleo (parejas bg/acento de tonos distintos) y
  // papel/alba (los primeros temas CLAROS: invierten fondos, texto, vidrio y señales).
  // El orden de ESTA lista es canónico (tests); el picker de Apariencia los muestra
  // ordenados por rueda de color, no por este array.
  const TEMAS = [
    'violeta', 'azul', 'verde', 'rosa', 'rojo',
    'oceano', 'esmeralda', 'lima', 'naranja', 'oro',
    'orquidea', 'grafito', 'hielo', 'medianoche',
    'sakura', 'salvia', 'neon', 'crepusculo', 'aurora', 'tinta',
    'bosque', 'petroleo', 'papel', 'alba',
  ];
  const DEFAULT_TEMA = 'violeta';
  function normalizarTema(t) { return TEMAS.includes(t) ? t : DEFAULT_TEMA; }

  // Temas CLAROS (fondo alto + texto oscuro; invierten fg/vidrio/señales en
  // tokens.css). Fuente canónica de la clasificación — el filtro del picker
  // de Apariencia lee esto; todo tema claro futuro se suma acá.
  const TEMAS_CLAROS = ['papel', 'alba'];
  function esTemaClaro(t) { return TEMAS_CLAROS.includes(t); }

  // ── Tonalidad ──
  // matiz: giro de rueda en grados (−40…40) · saturacion: % del croma (50…150) ·
  // profundidad: puntos de luminosidad de fondos/líneas (−3…3, negativo = más hondo).
  const TINTE_DEFAULT = { matiz: 0, saturacion: 100, profundidad: 0 };

  function normalizarTinte(t) {
    const src = (t && typeof t === 'object') ? t : {};
    const num = (v, min, max, def) => {
      const n = Number(v);
      return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : def;
    };
    return {
      matiz:       num(src.matiz, -40, 40, 0),
      saturacion:  num(src.saturacion, 50, 150, 100),
      profundidad: num(src.profundidad, -3, 3, 0),
    };
  }
  function esTinteNeutro(t) {
    return t.matiz === 0 && t.saturacion === 100 && t.profundidad === 0;
  }

  // 'oklch(61% 0.22 293)' → {l, c, h}. Solo el formato de tokens.css (sin alpha).
  const OKLCH_RE = /^oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s*\)$/;
  function parseOklch(str) {
    const m = OKLCH_RE.exec(String(str || '').trim());
    return m ? { l: +m[1], c: +m[2], h: +m[3] } : null;
  }

  // Ajusta un color de token según el tinte. La profundidad solo mueve fondos/líneas
  // (conProfundidad=true); el acento conserva su luminosidad para no perder contraste.
  function ajustarOklch(str, tinte, conProfundidad) {
    const col = parseOklch(str);
    if (!col) return null;
    const r3 = (x) => Math.round(x * 1000) / 1000;
    const l = Math.min(97, Math.max(3, col.l + (conProfundidad ? tinte.profundidad : 0)));
    const c = Math.min(0.27, Math.max(0, col.c * (tinte.saturacion / 100)));
    const h = ((col.h + tinte.matiz) % 360 + 360) % 360;
    return `oklch(${r3(l)}% ${r3(c)} ${r3(h)})`;
  }

  const pure = {
    TEMAS, DEFAULT_TEMA, normalizarTema, TEMAS_CLAROS, esTemaClaro,
    TINTE_DEFAULT, normalizarTinte, esTinteNeutro, parseOklch, ajustarOklch,
  };
  global.JarvisThemes = Object.assign(global.JarvisThemes || {}, { _pure: pure, ...pure });

  if (typeof document !== 'undefined') {
    const KEY = 'jarvis.theme';
    const KEY_TINTE = 'jarvis.tinte';

    // Tokens que la tonalidad reescribe. Las derivadas (--ob-accent-14, aliases
    // legacy, color-mix de secciones) trackean solas porque referencian a estos.
    const VARS_FONDO = [
      '--ob-bg-void', '--ob-bg-terminal', '--ob-bg-0', '--ob-bg-1', '--ob-bg-2',
      '--ob-bg-3', '--ob-bg-4', '--ob-line-1', '--ob-line-2', '--ob-line-3',
    ];
    const VARS_ACENTO = ['--ob-accent', '--ob-accent-fg', '--ob-accent-dim'];

    function actual() {
      try { return normalizarTema(localStorage.getItem(KEY)); } catch { return DEFAULT_TEMA; }
    }
    function tinte() {
      try { return normalizarTinte(JSON.parse(localStorage.getItem(KEY_TINTE) || 'null')); }
      catch { return normalizarTinte(null); }
    }

    // Limpia SIEMPRE los overrides primero (los computed deben ser los del tema
    // base) y recién ahí escribe los ajustados — así el switch de tema no arrastra
    // los valores tintados del tema anterior.
    function _pintarTinte(t) {
      const el = document.documentElement;
      for (const v of VARS_FONDO) el.style.removeProperty(v);
      for (const v of VARS_ACENTO) el.style.removeProperty(v);
      if (esTinteNeutro(t)) return;
      const cs = getComputedStyle(el);
      for (const v of VARS_FONDO) {
        const adj = ajustarOklch(cs.getPropertyValue(v), t, true);
        if (adj) el.style.setProperty(v, adj);
      }
      for (const v of VARS_ACENTO) {
        const adj = ajustarOklch(cs.getPropertyValue(v), t, false);
        if (adj) el.style.setProperty(v, adj);
      }
    }

    // El fondo NATIVO de la ventana, cuando corremos dentro del shell.
    //
    function _avisar(tema) {
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('theme-changed', { detail: tema }));
      }
    }

    function aplicar(tema) {
      const t = normalizarTema(tema);
      if (t === DEFAULT_TEMA) document.documentElement.removeAttribute('data-theme');
      else document.documentElement.dataset.theme = t;
      try { localStorage.setItem(KEY, t); } catch {}
      _pintarTinte(tinte());
      _avisar(t);
      return t;
    }

    // silencioso=true: para el arrastre vivo de los sliders (sin re-tematizar
    // xterm/strands en cada frame); al soltar, un setTinte normal emite el evento.
    function setTinte(valor, opts) {
      const t = normalizarTinte(valor);
      try {
        if (esTinteNeutro(t)) localStorage.removeItem(KEY_TINTE);
        else localStorage.setItem(KEY_TINTE, JSON.stringify(t));
      } catch {}
      _pintarTinte(t);
      if (!(opts && opts.silencioso)) _avisar(actual());
      return t;
    }

    Object.assign(global.JarvisThemes, {
      actual, aplicar, tinte, setTinte,
      init() { aplicar(actual()); },
    });
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = pure;
})(typeof window !== 'undefined' ? window : globalThis);
