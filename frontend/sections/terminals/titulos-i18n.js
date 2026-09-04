'use strict';
// Títulos vivos en el idioma de la UI (es ⇆ en).
//
// El pane title lo escribe la CLI en el idioma de la CONVERSACIÓN (español,
// porque el usuario les habla en español) — el i18n de diccionario no puede
// cubrirlo (texto libre). Con la UI en inglés se traduce vía
// POST /api/voice/translate (Google translate_a/single: gratis, sin tokens de
// API), con la misma receta que las novedades del updater: cache por texto
// normalizado + single-flight + degradación al original si la red falla.
// Con la UI en español este módulo es un no-op total (ni red ni cambios).
//
// sl='auto': un título que YA viene en inglés (Codex u otra CLI) no se
// estropea "traduciéndolo desde español" — Google detecta el origen.
(function (global) {
  const TITULO_MAX = 60;   // mismo cap visual que _limpiar_titulo (backend)
  const MAX_CACHE = 200;   // títulos ES distintos recordados por sesión (poda FIFO)

  function norm(s) { return (s == null ? '' : String(s)).replace(/\s+/g, ' ').trim(); }

  // Corte en palabra a `max`, SIN "…" — port del cap de _limpiar_titulo: el
  // backend capea el ESPAÑOL a 60, pero la traducción inglesa puede excederlo.
  function capear(texto, max) {
    texto = norm(texto);
    if (texto.length <= max) return texto;
    const corte = texto.lastIndexOf(' ', max);
    return (corte > 0 ? texto.slice(0, corte) : texto.slice(0, max)).replace(/\s+$/, '');
  }

  // PURA: de los títulos crudos del poll, los ÚNICOS que hay que mandar a la
  // red (ni cacheados ni en vuelo), como claves normalizadas y sin duplicados.
  function faltantes(titulos, cache, enVuelo) {
    const out = [], visto = {};
    (titulos || []).forEach((t) => {
      const k = norm(t);
      if (!k || (cache && k in cache) || (enVuelo && k in enVuelo) || visto[k]) return;
      visto[k] = 1; out.push(k);
    });
    return out;
  }

  // PURA: el texto que pinta la card. En 'en' la traducción cacheada (capeada
  // al mostrar; la cache guarda el texto crudo); si todavía no llegó, o el
  // idioma es español, el original — degradación elegante, nunca vacío.
  function mostrar(titulo, lang, cache) {
    if (lang !== 'en' || !cache) return titulo;
    const tr = cache[norm(titulo)];
    return tr ? capear(tr, TITULO_MAX) : titulo;
  }

  // Instancia con estado (cache + vuelo). `deps` inyectables para los tests;
  // en el browser los defaults leen JarvisI18n y fetch reales EN CADA LLAMADA
  // (lazy: el orden de carga de los <script> no importa).
  function crear(deps) {
    deps = deps || {};
    const _lang = deps.lang || (() => {
      try { return global.JarvisI18n ? global.JarvisI18n.lang() : 'es'; } catch (e) { return 'es'; }
    });
    const _fetch = deps.fetch || ((url, opts) => global.fetch(url, opts));
    const cache = {};       // titulo ES normalizado → traducción EN cruda
    const orden = [];       // claves en orden de llegada (poda FIFO)
    const enVuelo = {};     // claves con POST en curso (single-flight)

    function guardar(k, v) {
      if (!(k in cache)) {
        orden.push(k);
        if (orden.length > MAX_CACHE) delete cache[orden.shift()];
      }
      cache[k] = v;
    }

    // Dispara la traducción de lo que falte, en background. `onListo` se llama
    // SOLO si llegaron traducciones nuevas (para repintar). Un request fallido
    // libera el vuelo: el próximo poll reintenta solo.
    function pedir(titulos, onListo) {
      if (_lang() !== 'en') return;
      const falta = faltantes(titulos, cache, enVuelo);
      if (!falta.length) return;
      falta.forEach((k) => { enVuelo[k] = 1; });
      let p;
      try {
        p = _fetch('/api/voice/translate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ texts: falta, sl: 'auto' }),
        });
      } catch (e) { falta.forEach((k) => { delete enVuelo[k]; }); return; }
      Promise.resolve(p)
        .then((r) => (r && r.ok ? r.json() : null))
        .then((data) => {
          falta.forEach((k) => { delete enVuelo[k]; });
          if (!data || !Array.isArray(data.texts)) return;
          let hubo = false;
          falta.forEach((k, i) => {
            const tr = norm(data.texts[i]);
            // La identidad también se cachea: con sl=auto es el caso legítimo
            // "ya estaba en inglés" — sin cachearla se re-pediría en cada poll.
            if (tr) { guardar(k, tr); hubo = true; }
          });
          if (hubo && typeof onListo === 'function') onListo();
        })
        .catch(() => { falta.forEach((k) => { delete enVuelo[k]; }); });
    }

    return {
      mostrar: (titulo) => mostrar(titulo, _lang(), cache),
      pedir,
    };
  }

  const singleton = crear();
  const api = {
    TITULO_MAX, MAX_CACHE, crear,
    _pure: { norm, capear, faltantes, mostrar },
    mostrar: singleton.mostrar,
    pedir: singleton.pedir,
  };
  global.JarvisTitulosI18n = Object.assign(global.JarvisTitulosI18n || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
