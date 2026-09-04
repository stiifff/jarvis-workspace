// JARVIS — Post-corrección determinista del dictado (STT) + diagnóstico de mic.
//
// El modo de fallo REAL del dictado es la jerga técnica en inglés dentro del
// español ("hacé commit" → "hace que mid"): lo cometen TODOS los modelos de
// STT probados (benchmark 2026-07-09, ver memoria stt-faster-whisper-migracion).
// La palanca es corregir el TEXTO acá: 0ms, 0 RAM, sin tokens de API.
// (El aparato del SpeechRecognition —decisión de fuente, re-rank de
// alternativas, unión de fragmentos, presupuesto SR-vs-server— se removió
// 2026-07-17: el dictado es 100% server, Groq + fallback local. Ver memoria
// stt-groq-motor.)
//
// Para sumar una corrección nueva: agregá su regla a REGLAS (los errores se
// cazan de dictados reales mal transcritos). Regla de diseño: CONSERVADOR —
// solo secuencias que no son español válido, o gateadas por contexto (p.ej.
// "comité"/"merch" solo tras una forma de "hacer": "el comité de vecinos" y
// "la sección de merch" son español legítimo y no se tocan).
(function (global) {
  'use strict';

  // Límite de palabra consciente del español: \b de JS es ASCII y cree que hay
  // borde entre "t" y "é" (p.ej. cazaría el "comit" DENTRO de "comité").
  const L = 'a-záéíóúüñ';
  function regla(patron, reemplazo) {
    return [new RegExp(`(?<![${L}])(?:${patron})(?![${L}])`, 'gi'), reemplazo];
  }

  // Formas de "hacer" (hacé, hace, hacer, hacele, haga, hagan…) para las reglas
  // gateadas por contexto. Grupo con captura: el reemplazo preserva el verbo.
  const HACER = `(hac[${L}]*|hag[${L}]*)`;

  const REGLAS = [
    // commit — el error medido en todos los modelos ("que mid") + fonetizaciones
    regla('que\\s+mid', 'commit'),
    regla(`${HACER}(\\s+(?:un|una|el)\\s+|\\s+)comité(s?)`, '$1$2commit$3'),
    regla('comits?', 'commit'),

    // nombres de CLIs / herramientas
    regla('yarvis|yarbis|jarbis|harvis|iarvis|jarvis', 'Jarvis'),
    regla('[ck]l[ao]u?de?\\s+cou?de?', 'Claude Code'),
    regla('claude', 'Claude'),
    regla('[ck][óo]dex', 'Codex'),
    regla('g[ée]minis?|yemini|llemini', 'Gemini'),
    regla('kwen|quen|cu[ée]n', 'qwen'),
    regla('open\\s?code', 'opencode'),
    regla('anti\\s?gravit[iy]', 'antigravity'),
    regla('t[ei]\\s?mux|t\\s?mux', 'tmux'),

    // términos de dev partidos o fonetizados
    regla('front[\\s-]?end', 'frontend'),
    regla('back[\\s-]?end', 'backend'),
    regla('dash\\s?boa?rd?', 'dashboard'),
    regla('work[\\s-]?flo[uw]?w?', 'workflow'),
    regla('local\\s?host', 'localhost'),
    regla('puch', 'push'),
    regla('deploi|diploi', 'deploy'),
    regla(`${HACER}(\\s+(?:un|una|el)\\s+|\\s+)merch`, '$1$2merge'),
    regla('canban|camban|kanb[áa]n', 'kanban'),
    regla('previu|prebiu|pre\\s?viu', 'preview'),

    // errores REALES de data/dictados.log (2026-07-10): el SR fonetiza la
    // jerga de UI al español más cercano
    regla('mokap|mok\\s?ap|mock\\s?up', 'mockup'),
    regla('scroll\\s?bar|escrol\\s?bar', 'scrollbar'),
    regla('web\\s?builder', 'Web Builder'),
    // "sidebar" → "saldívar" (apellido real: gateado por artículo/determinante,
    // igual que comité/merch) + fonetizaciones directas sin ambigüedad
    regla(`(el|la|del|al|este|ese)\\s+sald[íi]var`, '$1 sidebar'),
    regla('s[áa]id\\s?bar|said\\s?bar', 'sidebar'),
    regla('o\\s+k', 'ok'),   // "O k perfecto" — la "k" suelta no es español
  ];

  // Aplica todas las reglas al texto dictado. Pura e idempotente (las salidas
  // canónicas no re-matchean ninguna regla).
  function corregirJerga(texto) {
    let t = (texto == null) ? '' : String(texto);
    for (const [re, rep] of REGLAS) t = t.replace(re, rep);
    return t;
  }

  // ── Diagnóstico de captura ─────────────────────────────────────────────────
  // Con métricas del AnalyserNode del PTT (pico en dBFS + muestras clipeadas) y
  // la etiqueta del dispositivo, detecta las 3 causas típicas de dictado malo
  // que NINGÚN modelo arregla. Umbrales de la literatura: sano = picos −12…−6;
  // muy bajo = picos < −24; clipping = |x| ≥ 0.99. "Hands-Free" en la etiqueta
  // = auricular Bluetooth en perfil HFP (audio telefónico de 8-16 kHz).
  function diagnosticoMic({ picoDb, clips, etiqueta } = {}) {
    if (/hands-?free/i.test(etiqueta || '')) return 'bluetooth';
    if (typeof picoDb !== 'number') return null;
    if ((clips || 0) >= 3) return 'saturado';
    if (picoDb < -24) return 'bajo';
    return null;
  }

  const pure = { corregirJerga, diagnosticoMic, REGLAS };
  global.JarvisSTT = Object.assign(global.JarvisSTT || {}, {
    corregirJerga, diagnosticoMic,
    _pure: pure,
  });
})(typeof window !== 'undefined' ? window : globalThis);
