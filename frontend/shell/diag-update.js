'use strict';
// JARVIS — Diagnóstico del freeze post-update (instrumentación temporal del
// deep work 2026-07-11: "el scroll anda ~1s, se congela ~5.5s y vuelve solo").
//
// Se activa SOLO tras un reload post-update (updater.js llama arrancar() al
// ver la marca de sessionStorage) y muestrea ~30s cuatro señales que separan
// las hipótesis:
//   raf   — gap máximo entre frames en la ventana (main thread del browser
//           trabado = jank local; el scroll visual muere acá).
//   ping  — latencia de /api/health (event loop del server ahogado; la rueda
//           en alt-screen viaja por esa misma cola).
//   rx    — bytes recibidos por los WS de las terminales en la ventana
//           (terminal.js suma en window._jarvisDiagRx). Si el usuario rueda
//           (wheel>0) y rx=0 con ping sano, el stall está en tmux/la app.
//   wheel — eventos de rueda del usuario en la ventana (¿estaba scrolleando?).
// + longtasks (PerformanceObserver) con su duración, para nombrar al culpable
// del jank si es local.
//
// Al terminar POSTea todo a /api/system/diag-update (el server lo appendea a
// data/diag_update.jsonl) y loguea el resumen en consola. Costo en régimen:
// CERO (sin la marca no se instala nada más que el contador rx de terminal.js).

(function (root) {

  // ── Lógica pura (testeable en Node) ─────────────────────────────
  // Ventanas "congeladas" dentro de las muestras: tramos contiguos donde el
  // main thread está trabado (raf ≥ umbralRaf) O el usuario rueda sin recibir
  // nada (wheel > 0 && rx === 0). Devuelve [{desde, hasta, ms, motivo}] con
  // tramos de al menos minMs (los micro-hipos no cuentan).
  function ventanasCongeladas(muestras, opts = {}) {
    const umbralRaf = opts.umbralRaf ?? 300;
    const minMs = opts.minMs ?? 800;
    const out = [];
    let abierta = null;
    const cerrar = (hasta) => {
      if (abierta && (hasta - abierta.desde) >= minMs) {
        out.push({ desde: abierta.desde, hasta, ms: hasta - abierta.desde, motivo: abierta.motivo });
      }
      abierta = null;
    };
    for (const m of (muestras || [])) {
      const jankLocal = (m.raf || 0) >= umbralRaf;
      const mudo = (m.wheel || 0) > 0 && (m.rx || 0) === 0;
      if (jankLocal || mudo) {
        const motivo = jankLocal ? 'main-thread' : 'sin-output';
        if (!abierta) abierta = { desde: m.t, motivo };
        else if (abierta.motivo !== motivo) abierta.motivo = 'mixto';
      } else {
        cerrar(m.t);
      }
    }
    if (abierta && muestras.length) cerrar(muestras[muestras.length - 1].t);
    return out;
  }

  const _pure = { ventanasCongeladas };

  // ── Sampler (solo browser) ──────────────────────────────────────
  const _esBrowser = typeof document !== 'undefined';
  let _corriendo = false;

  function arrancar(motivo) {
    if (!_esBrowser || _corriendo) return;
    _corriendo = true;
    root._jarvisDiagRx = root._jarvisDiagRx || 0;   // terminal.js suma acá

    const DURACION = 30000, PASO = 200, PING_CADA = 400;
    const t0 = performance.now();
    const t0Epoch = Date.now();
    const muestras = [];
    const longtasks = [];

    // Frames: el gap máximo entre rAF dentro de cada ventana de muestreo.
    let _ultimoFrame = t0, _rafGapMax = 0, _rafVivo = true;
    const _frame = (ts) => {
      _rafGapMax = Math.max(_rafGapMax, ts - _ultimoFrame);
      _ultimoFrame = ts;
      if (_rafVivo) requestAnimationFrame(_frame);
    };
    requestAnimationFrame(_frame);

    // Long tasks con atribución (si el browser las da).
    let obs = null;
    try {
      obs = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) {
          longtasks.push({ t: Math.round(e.startTime - t0), dur: Math.round(e.duration) });
        }
      });
      obs.observe({ entryTypes: ['longtask'] });
    } catch (_) { /* sin soporte */ }

    // Rueda del usuario (passive, no toca el scroll).
    let _wheelN = 0;
    const _onWheel = () => { _wheelN++; };
    document.addEventListener('wheel', _onWheel, { capture: true, passive: true });

    // Ping serializado a /api/health.
    let _pingMs = null, _pingVivo = true;
    const _ping = async () => {
      if (!_pingVivo) return;
      const ini = performance.now();
      try {
        const r = await fetch('/api/health', { cache: 'no-store' });
        _pingMs = r.ok ? Math.round(performance.now() - ini) : -1;
      } catch (_) { _pingMs = -1; }
      if (_pingVivo) setTimeout(_ping, PING_CADA);
    };
    _ping();

    let _rxPrev = root._jarvisDiagRx;
    const _tick = () => {
      const ahora = performance.now();
      const rx = root._jarvisDiagRx;
      muestras.push({
        t: Math.round(ahora - t0),
        raf: Math.round(_rafGapMax),
        ping: _pingMs,
        rx: rx - _rxPrev,
        wheel: _wheelN,
        overlay: !!document.querySelector('.jw-up-overlay'),
      });
      _rxPrev = rx; _rafGapMax = 0; _wheelN = 0;
      if (ahora - t0 < DURACION) { setTimeout(_tick, PASO); return; }
      // Cierre: parar todo y reportar.
      _rafVivo = false; _pingVivo = false;
      try { obs && obs.disconnect(); } catch (_) {}
      document.removeEventListener('wheel', _onWheel, { capture: true });
      const ventanas = ventanasCongeladas(muestras);
      const informe = { motivo: motivo || 'post-update', t0Epoch, muestras, longtasks, ventanas };
      try { console.log('[diag-update] ventanas congeladas:', JSON.stringify(ventanas), '· longtasks:', longtasks.length); } catch (_) {}
      try {
        fetch('/api/system/diag-update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(informe),
        }).catch(() => {});
      } catch (_) { /* best-effort */ }
      _corriendo = false;
    };
    setTimeout(_tick, PASO);
  }

  root.JarvisDiagUpdate = { arrancar, _pure };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.JarvisDiagUpdate;

})(typeof window !== 'undefined' ? window : globalThis);
