'use strict';
// ─── Campo de escucha: "la ventana te escucha" ───────────────────────────────
// Respuesta visual AMBIENTAL mientras dictás con el PTT. No es decoración: dice
// un estado que antes solo vivía en la píldora (y que con el dock cerrado no se
// veía en ningún lado) — Jarvis está capturando tu voz AHORA, y reacciona al
// volumen real del micrófono.
//
// Dos piezas, una idea:
//   · borde de luz (4 tiras finas, siempre): se ve con 12 terminales abiertas y
//     no tapa contenido. Late con tu voz.
//   · aliento radial (solo con el mosaico VACÍO): la respiración grande del
//     empty state, donde hay lugar para que se note.
//
// Reglas del sistema que esto respeta a rajatabla (ver .agents/context/DESIGN.md):
//   · cero hex: todo sale de var(--ob-info)/var(--ob-accent).
//   · JAMÁS backdrop-filter ni capas full-screen sobre el canvas de xterm: las
//     tiras del borde son chicas y solo cambian opacity/transform (compositor,
//     sin repaint del gradiente).
//   · prefers-reduced-motion: presencia fija, sin latido ni rAF.
// Decisiones puras (sin DOM) abajo en `_pure`, testeadas en __tests__.

(function (root) {

  // ── Parte PURA ────────────────────────────────────────────────────
  // Mapa nivel-de-mic → intensidad visual. `window._orchVoiceLevel` (el que
  // publica el waveform del PTT) vive casi siempre entre 0.02 (silencio de sala)
  // y ~0.55 (voz normal cerca del mic); mapear 0..1 lineal dejaba el campo
  // planchado. Piso/techo recortan ese rango real y la gamma < 1 expande la
  // zona baja, así hablar bajito también se ve.
  const PISO  = 0.02;
  const TECHO = 0.55;
  const GAMMA = 0.72;
  // Presencia mínima: aunque estés callado el campo queda encendido — "te
  // escucho" no puede apagarse entre palabra y palabra, y el apretón del PTT
  // tiene que verse ANTES de la primera sílaba (calibrado en browser).
  const BASE  = 0.22;

  function mapear(nivel) {
    const n = typeof nivel === 'number' && isFinite(nivel) ? nivel : 0;
    const t = (Math.min(TECHO, Math.max(PISO, n)) - PISO) / (TECHO - PISO);
    return BASE + Math.pow(t, GAMMA) * (1 - BASE);
  }

  // Suavizado ASIMÉTRICO: sube casi al toque (la sílaba tiene que verse) y baja
  // despacio (sin parpadeo entre palabras — el parpadeo es lo que hace que un
  // efecto reactivo se sienta barato).
  const ATAQUE = 0.42;
  const CAIDA  = 0.10;

  function suavizar(prev, objetivo) {
    const p = typeof prev === 'number' && isFinite(prev) ? prev : 0;
    const o = typeof objetivo === 'number' && isFinite(objetivo) ? objetivo : 0;
    return p + (o - p) * (o > p ? ATAQUE : CAIDA);
  }

  // ¿Vale la pena escribir el nuevo valor al DOM? Escribir una custom property
  // invalida el estilo del subárbol: si el cambio no se ve, no se paga.
  function vale(anterior, nuevo) {
    return Math.abs(nuevo - anterior) > 0.004;
  }

  // Espectro simétrico: `bins` es el análisis de frecuencia que publica el
  // waveform del PTT (window._orchVoiceBins, 64 valores 0..1, escala
  // perceptual). Devuelve `n` alturas 0..1 con los GRAVES al centro y los
  // agudos hacia los extremos — el eco visual de una consola de audio, y
  // simétrico porque una barra que salta sola de un lado se lee como error.
  // Piso 0.02: la línea nunca desaparece del todo (es el "hay señal").
  function espectro(bins, n) {
    const N = Math.max(1, n | 0);
    const out = new Array(N);
    const len = bins && bins.length ? bins.length : 0;
    if (!len) { out.fill(0.02); return out; }
    const centro = (N - 1) / 2;
    for (let i = 0; i < N; i++) {
      // distancia al centro 0..1 → índice del bin (curva: más resolución en graves)
      const d = centro === 0 ? 0 : Math.abs(i - centro) / centro;
      const idx = Math.min(len - 1, Math.floor(Math.pow(d, 1.25) * (len - 1)));
      const v = bins[idx];
      out[i] = Math.max(0.02, Math.min(1, typeof v === 'number' && isFinite(v) ? v : 0));
    }
    return out;
  }

  const puro = { mapear, suavizar, vale, espectro, PISO, TECHO, BASE };

  // ── Parte DOM ─────────────────────────────────────────────────────
  const api = Object.assign({}, puro, { _pure: puro });

  if (typeof document !== 'undefined') {
    const BARRAS = 33;     // impar: hay una barra JUSTO en el centro

    let el = null;         // #jw-voice-field
    let barras = [];       // las <i> del espectro
    let suaves = [];       // altura suavizada de cada barra
    let raf = 0;
    let nivelSuave = 0;
    let escrito = -1;
    let modo = null;       // 'rec' | 'proc' | null

    const reduce = () => !!window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;

    function montar() {
      if (el && el.isConnected) return el;
      el = document.createElement('div');
      el.id = 'jw-voice-field';
      el.className = 'vfield';
      el.setAttribute('aria-hidden', 'true');
      el.innerHTML = '<i class="vf-e vf-t"></i><i class="vf-e vf-b"></i>' +
                     '<i class="vf-e vf-l"></i><i class="vf-e vf-r"></i>' +
                     '<i class="vf-breath"></i>' +
                     '<div class="vf-spec">' + '<i></i>'.repeat(BARRAS) + '</div>';
      document.body.appendChild(el);
      barras = Array.from(el.querySelectorAll('.vf-spec i'));
      suaves = barras.map(() => 0.02);
      return el;
    }

    // El campo VIVE en la pantalla de arranque y en ningún otro lado: si el
    // mosaico tiene terminales, el usuario está leyendo código y la ventana no
    // se le enciende (pedido 2026-07-22). Sin este elemento a la vista,
    // `escuchar()` es un no-op.
    function espacioLibre() {
      const empty = document.getElementById('terminals-empty');
      if (empty && !empty.classList.contains('oculto')) return empty;
      const wel = document.getElementById('jw-welcome');
      if (wel && !wel.classList.contains('oculto')) return wel;
      return null;
    }

    let host = null;   // empty state que también recibe --vf-i (logo reactivo)

    function escribir(v) {
      if (!vale(escrito, v)) return;
      escrito = v;
      const s = v.toFixed(3);
      el.style.setProperty('--vf-i', s);
      if (host) host.style.setProperty('--vf-i', s);
    }

    function tick() {
      if (modo !== 'rec') { raf = 0; return; }
      // Si aparecieron terminales a mitad del dictado, la pantalla de arranque
      // se fue y el campo con ella: nunca queda encendido sobre el mosaico.
      if (!host || host.classList.contains('oculto')) { raf = 0; api.apagar(); return; }
      nivelSuave = suavizar(nivelSuave, mapear(window._orchVoiceLevel || 0));
      escribir(nivelSuave);
      // Espectro: son 33 transforms por frame — un costo que se paga acá, donde
      // no hay xterm peleando por la CPU, y que convierte el fondo en el
      // instrumento que muestra TU voz en vez de un adorno.
      if (barras.length) {
        const h = espectro(window._orchVoiceBins, barras.length);
        for (let i = 0; i < barras.length; i++) {
          suaves[i] = suavizar(suaves[i], h[i]);
          barras[i].style.transform = `scaleY(${suaves[i].toFixed(3)})`;
        }
      }
      raf = requestAnimationFrame(tick);
    }

    // Deja caer las barras a la línea de base (no se congelan a media altura:
    // una barra clavada miente, dice que hay señal cuando ya no hay).
    function bajarBarras() {
      for (let i = 0; i < barras.length; i++) {
        suaves[i] = 0.02;
        barras[i].style.transform = 'scaleY(0.02)';
      }
    }

    // Arranca el campo en modo escucha (dictado con destino ya resuelto).
    // Fuera de la pantalla de arranque no hace NADA: ni monta el elemento.
    api.escuchar = function escuchar() {
      host = espacioLibre();
      if (!host) return;
      montar();
      modo = 'rec';
      el.dataset.mode = 'rec';
      el.classList.add('on');
      if (reduce()) { escribir(0.55); return; }   // presencia fija, sin rAF
      nivelSuave = BASE;
      escrito = -1;
      escribir(BASE);
      bajarBarras();                              // el espectro arranca en la línea de base
      if (!raf) raf = requestAnimationFrame(tick);
    };

    // Soltaste: ya no hay voz que seguir. El campo se queda encendido en un
    // valor fijo mientras se transcribe (el trabajo sigue) y cambia de color.
    api.procesando = function procesando() {
      if (!el || !modo) return;
      modo = 'proc';
      el.dataset.mode = 'proc';
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      escrito = -1;
      escribir(0.42);
      bajarBarras();
    };

    // Apagar (fin del dictado, descarte o cancelación). El CSS hace el fade.
    api.apagar = function apagar() {
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      modo = null;
      if (!el) return;
      el.classList.remove('on');
      delete el.dataset.mode;
      if (host) { host.style.removeProperty('--vf-i'); host = null; }
      escrito = -1;
    };

    api.activo = () => modo;
  }

  root.JarvisVoiceField = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;

})(typeof window !== 'undefined' ? window : globalThis);
