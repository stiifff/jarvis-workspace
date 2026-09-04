/* ════════════════════════════════════════════════════════════════
   Jarvis — matemática del medidor de audio del waveform del PTT.

   El HUD de dictado por voz reacciona al MICRÓFONO REAL: workspace.js cuelga un
   AnalyserNode del stream de getUserMedia y, en un rAF, alimenta estas funciones
   con los datos crudos del analyser para mover las barras del ecualizador y la
   línea de nivel. Acá solo va la matemática pura (testeable en Node).
═══════════════════════════════════════════════════════════════ */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.JarvisAudioMeter = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  function _clamp01(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

  // Nivel global de voz (RMS) a partir del time-domain del analyser
  // (Uint8Array, silencio ≈ 128). Devuelve 0..1.
  function nivel(timeData) {
    var n = timeData ? timeData.length : 0;
    if (!n) return 0;
    var sum = 0;
    for (var i = 0; i < n; i++) {
      var d = (timeData[i] - 128) / 128;
      sum += d * d;
    }
    return _clamp01(Math.sqrt(sum / n));
  }

  // Alturas (0..1) de `nBarras` agrupando el espectro (getByteFrequencyData,
  // Uint8Array 0..255) en bandas contiguas y promediando cada una /255.
  function barras(freqData, nBarras) {
    var out = [];
    var n = freqData ? freqData.length : 0;
    if (!nBarras || nBarras < 1) return out;
    if (!n) { for (var k = 0; k < nBarras; k++) out.push(0); return out; }
    var ancho = n / nBarras;
    for (var b = 0; b < nBarras; b++) {
      var ini = Math.floor(b * ancho), fin = Math.floor((b + 1) * ancho);
      if (fin <= ini) fin = ini + 1;
      var s = 0, c = 0;
      for (var j = ini; j < fin && j < n; j++) { s += freqData[j]; c++; }
      out.push(c ? _clamp01((s / c) / 255) : 0);
    }
    return out;
  }

  // "Flow state" simétrico para el waveform de voz: en vez de bandas contiguas
  // (donde solo los graves —donde vive la voz— se mueven), reparte así para que
  // TODAS las barras bailen:
  //   - simetría centro→bordes (look de visualizador de voz tipo Siri),
  //   - centro = graves (voz), bordes = agudos por una curva log,
  //   - una envolvente por VOLUMEN global que levanta todas las barras al hablar,
  //   - una campana que realza el centro.
  // freqData = getByteFrequencyData (0..255). Devuelve nBarras alturas 0..1.
  function flujo(freqData, nBarras) {
    var out = [];
    var n = freqData ? freqData.length : 0;
    if (!nBarras || nBarras < 1) return out;
    if (!n) { for (var k = 0; k < nBarras; k++) out.push(0); return out; }
    // Energía global con boost (la voz rara vez satura el espectro a 255).
    var sum = 0;
    for (var i = 0; i < n; i++) sum += freqData[i];
    var energia = _clamp01((sum / n) / 255 * 3.4);
    var mitad = (nBarras - 1) / 2;
    for (var b = 0; b < nBarras; b++) {
      var d = mitad > 0 ? Math.abs(b - mitad) / mitad : 0;          // 0 centro .. 1 borde
      // Banda log: centro→graves, borde→agudos (recorta el tramo superior casi mudo).
      var idx = Math.min(n - 1, Math.floor(Math.pow(d, 1.6) * (n * 0.55)));
      var banda = freqData[idx] / 255;
      var ventana = 0.35 + 0.65 * Math.pow(Math.cos(d * Math.PI / 2), 1.3); // 1 centro .. .35 borde
      out.push(_clamp01((banda * 0.45 + energia * 0.85) * ventana));
    }
    return out;
  }

  // Suavizado asimétrico: ataque rápido (sube), release lento (baja) — da el
  // movimiento orgánico de un VU real (salta con la voz, cae despacio).
  function suavizar(prev, next, sube, baja) {
    if (sube == null) sube = 0.5;
    if (baja == null) baja = 0.18;
    var f = next > prev ? sube : baja;
    return prev + (next - prev) * f;
  }

  return { nivel: nivel, barras: barras, flujo: flujo, suavizar: suavizar };
}));
