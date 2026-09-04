// JARVIS — Strands: cintas de luz WebGL2 (port vanilla del <Strands/> de React Bits).
// Sin ogl ni React: un triángulo fullscreen + fragment shader. Los colores se
// resuelven desde CSS (var(--ob-*)) para que el efecto siga SIEMPRE al tema
// activo — nunca hex hardcodeado. Lógica pura testeable en Node vía _pure.
//
// Uso:  const h = JarvisStrands.montar(container, { coloresCss: ['var(--ob-accent)', ...], speed: 0.3 });
//       h.refrescarColores()  → re-lee los var() (llamar en 'theme-changed')
//       h.destroy()
//
// Respeta prefers-reduced-motion (frame estático), pausa con pestaña oculta o
// contenedor fuera de viewport, DPR capado a 1.5 y contexto low-power.
(function (global) {
  'use strict';

  const MAX_HEBRAS = 12;
  const MAX_COLORES = 8;

  // Defaults del componente original; los overrides finos van por opts.
  const DEFAULTS = {
    count: 3, speed: 0.5, amplitude: 1, waviness: 1, thickness: 0.7,
    glow: 2.6, taper: 3, spread: 1, hueShift: 0, intensity: 0.6,
    saturation: 1.5, opacity: 1, scale: 1.5,
  };

  function clampHebras(n) {
    const v = Math.round(Number(n));
    if (!Number.isFinite(v)) return DEFAULTS.count;
    return Math.min(Math.max(v, 1), MAX_HEBRAS);
  }

  // Mezcla opts sobre DEFAULTS coercionando a número; lo no-numérico cae al default.
  function resolverOpciones(opts) {
    const out = {};
    for (const k of Object.keys(DEFAULTS)) {
      const v = Number(opts && opts[k]);
      out[k] = Number.isFinite(v) ? v : DEFAULTS[k];
    }
    out.count = clampHebras(out.count);
    return out;
  }

  // rgbs: array de [r,g,b] en 0..1 → paleta plana de 8 vec3 (repite el último).
  // n === 0 ⇒ el shader usa su espectro arcoíris interno (uColorCount 0).
  function armarPaleta(rgbs) {
    const lista = Array.isArray(rgbs) ? rgbs.filter(c => Array.isArray(c) && c.length === 3) : [];
    const n = Math.min(lista.length, MAX_COLORES);
    const plano = new Float32Array(MAX_COLORES * 3);
    for (let i = 0; i < MAX_COLORES; i++) {
      const c = n ? lista[Math.min(i, n - 1)] : [1, 1, 1];
      plano[i * 3] = c[0]; plano[i * 3 + 1] = c[1]; plano[i * 3 + 2] = c[2];
    }
    return { plano, n };
  }

  const pure = { MAX_HEBRAS, MAX_COLORES, DEFAULTS, clampHebras, resolverOpciones, armarPaleta };
  global.JarvisStrands = Object.assign(global.JarvisStrands || {}, { _pure: pure });
  if (typeof module !== 'undefined' && module.exports) module.exports = pure;
  if (typeof document === 'undefined') return;

  // ═══ Parte DOM/WebGL ═══════════════════════════════════════════

  const VERT = `#version 300 es
in vec2 position;
void main() { gl_Position = vec4(position, 0.0, 1.0); }
`;

  const FRAG = `#version 300 es
precision highp float;

uniform float uTime;
uniform vec2 uResolution;
uniform vec3 uColors[${MAX_COLORES}];
uniform int uColorCount;
uniform int uStrandCount;
uniform float uSpeed;
uniform float uAmplitude;
uniform float uWaviness;
uniform float uThickness;
uniform float uGlow;
uniform float uTaper;
uniform float uSpread;
uniform float uHueShift;
uniform float uIntensity;
uniform float uOpacity;
uniform float uScale;
uniform float uSaturation;

out vec4 fragColor;

const float PI = 3.14159265;

vec3 spectrum(float t) {
  return 0.5 + 0.5 * cos(2.0 * PI * (t + vec3(0.00, 0.33, 0.67)));
}

vec3 samplePalette(float t) {
  t = fract(t);
  float scaled = t * float(uColorCount);
  int idx = int(floor(scaled));
  float blend = fract(scaled);
  int nextIdx = idx + 1;
  if (nextIdx >= uColorCount) nextIdx = 0;
  return mix(uColors[idx], uColors[nextIdx], blend);
}

vec3 strandColor(float t) {
  if (uColorCount > 0) return samplePalette(t);
  return spectrum(t);
}

void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5 * uResolution) / uResolution.y;
  uv /= max(uScale, 0.0001);

  float e = 0.06 + uIntensity * 0.94;
  // Desvío del port: el taper original (cos sobre x normalizado por ALTO) es
  // periódico y en canvas anchos (aspect > ~3) repite lóbulos brillantes en los
  // bordes. Acá el envelope se normaliza por ANCHO: un solo lóbulo centrado que
  // muere exactamente en ambos bordes, sea cual sea el aspect.
  float xn = gl_FragCoord.x / uResolution.x - 0.5;
  float env = pow(max(cos(xn * PI), 0.0), uTaper);

  vec3 col = vec3(0.0);

  for (int i = 0; i < ${MAX_HEBRAS}; i++) {
    if (i >= uStrandCount) break;

    float fi = float(i);
    float ph = fi * 1.7 * uSpread;
    float freq = (2.0 + fi * 0.35) * uWaviness;
    float spd = 1.4 + fi * 1.2;

    float tt = uTime * uSpeed;
    float w = sin(uv.x * freq + tt * spd + ph) * 0.60
            + sin(uv.x * freq * 1.1 - tt * spd * 0.7 + ph * 1.7) * 0.40;

    float amp = (0.1 + 0.02 * e) * env * uAmplitude;
    float y = w * amp;

    float d = abs(uv.y - y);
    float thick = (0.001 + 0.05 * e) * (0.35 + env) * uThickness;
    float g = thick / (d + thick * 0.45);
    g = g * g;

    float h = fi / float(uStrandCount) + uv.x * 0.30 + uTime * 0.04 + uHueShift;
    col += strandColor(h) * g * env;
  }

  col *= 0.45 + 0.7 * e;
  col = 1.0 - exp(-col * uGlow);

  float gray = dot(col, vec3(0.2126, 0.7152, 0.0722));
  col = max(mix(vec3(gray), col, uSaturation), 0.0);

  float lum = max(max(col.r, col.g), col.b);
  float alpha = clamp(lum, 0.0, 1.0) * uOpacity;

  fragColor = vec4(col * uOpacity, alpha);
}
`;

  // Resuelve CUALQUIER color CSS (var(), oklch, color-mix…) a [r,g,b] 0..1:
  // probe en el DOM (getComputedStyle resuelve los var) → canvas 2D → bytes sRGB.
  let _cv2d = null;
  function resolverColorCss(css) {
    try {
      const probe = document.createElement('span');
      probe.style.display = 'none';
      probe.style.color = css;
      document.body.appendChild(probe);
      const computado = getComputedStyle(probe).color;
      probe.remove();
      if (!computado) return null;
      if (!_cv2d) {
        const cv = document.createElement('canvas');
        cv.width = cv.height = 1;
        _cv2d = cv.getContext('2d', { willReadFrequently: true });
      }
      _cv2d.clearRect(0, 0, 1, 1);
      _cv2d.fillStyle = '#000';
      _cv2d.fillStyle = computado;
      _cv2d.fillRect(0, 0, 1, 1);
      const px = _cv2d.getImageData(0, 0, 1, 1).data;
      if (px[3] === 0) return null;  // no parseó
      return [px[0] / 255, px[1] / 255, px[2] / 255];
    } catch (_) { return null; }
  }

  function _compilar(gl, tipo, src) {
    const sh = gl.createShader(tipo);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      console.warn('[strands] shader:', gl.getShaderInfoLog(sh));
      gl.deleteShader(sh);
      return null;
    }
    return sh;
  }

  // Monta el efecto dentro de `cont`. Devuelve handle {destroy, refrescarColores, set}
  // o null si no hay WebGL2 / colores (el fondo estático de CSS queda como fallback).
  function montar(cont, opts) {
    if (!cont) return null;
    const coloresCss = (opts && opts.coloresCss) || [];
    let rgbs = coloresCss.map(resolverColorCss).filter(Boolean);
    if (coloresCss.length && !rgbs.length) return null;  // tema ilegible: no montar

    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2', {
      alpha: true, premultipliedAlpha: true, antialias: false,
      powerPreference: 'low-power', depth: false, stencil: false,
    });
    if (!gl) return null;

    let opciones = resolverOpciones(opts);
    let prog = null, locs = null, vao = null, buf = null;

    function initGL() {
      const vs = _compilar(gl, gl.VERTEX_SHADER, VERT);
      const fs = _compilar(gl, gl.FRAGMENT_SHADER, FRAG);
      if (!vs || !fs) return false;
      prog = gl.createProgram();
      gl.attachShader(prog, vs);
      gl.attachShader(prog, fs);
      gl.linkProgram(prog);
      gl.deleteShader(vs); gl.deleteShader(fs);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
        console.warn('[strands] link:', gl.getProgramInfoLog(prog));
        return false;
      }
      vao = gl.createVertexArray();
      gl.bindVertexArray(vao);
      buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      const aPos = gl.getAttribLocation(prog, 'position');
      gl.enableVertexAttribArray(aPos);
      gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);
      gl.useProgram(prog);
      gl.disable(gl.BLEND);          // fragColor ya sale premultiplicado
      gl.disable(gl.DEPTH_TEST);
      const U = n => gl.getUniformLocation(prog, n);
      locs = {
        uTime: U('uTime'), uResolution: U('uResolution'), uColors: U('uColors[0]'),
        uColorCount: U('uColorCount'), uStrandCount: U('uStrandCount'), uSpeed: U('uSpeed'),
        uAmplitude: U('uAmplitude'), uWaviness: U('uWaviness'), uThickness: U('uThickness'),
        uGlow: U('uGlow'), uTaper: U('uTaper'), uSpread: U('uSpread'), uHueShift: U('uHueShift'),
        uIntensity: U('uIntensity'), uOpacity: U('uOpacity'), uScale: U('uScale'),
        uSaturation: U('uSaturation'),
      };
      aplicarEstaticos();
      aplicarPaleta();
      aplicarTamano();
      return true;
    }

    function aplicarEstaticos() {
      if (!locs) return;
      const o = opciones;
      gl.uniform1i(locs.uStrandCount, o.count);
      gl.uniform1f(locs.uSpeed, o.speed);
      gl.uniform1f(locs.uAmplitude, o.amplitude);
      gl.uniform1f(locs.uWaviness, o.waviness);
      gl.uniform1f(locs.uThickness, o.thickness);
      gl.uniform1f(locs.uGlow, o.glow);
      gl.uniform1f(locs.uTaper, o.taper);
      gl.uniform1f(locs.uSpread, o.spread);
      gl.uniform1f(locs.uHueShift, o.hueShift);
      gl.uniform1f(locs.uIntensity, o.intensity);
      gl.uniform1f(locs.uOpacity, o.opacity);
      gl.uniform1f(locs.uScale, o.scale);
      gl.uniform1f(locs.uSaturation, o.saturation);
    }

    function aplicarPaleta() {
      if (!locs) return;
      const { plano, n } = armarPaleta(rgbs);
      gl.uniform3fv(locs.uColors, plano);
      gl.uniform1i(locs.uColorCount, n);
    }

    function aplicarTamano() {
      const dpr = Math.min(global.devicePixelRatio || 1, 1.5);
      const w = Math.max(1, Math.round(cont.clientWidth * dpr));
      const h = Math.max(1, Math.round(cont.clientHeight * dpr));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w; canvas.height = h;
      }
      gl.viewport(0, 0, w, h);
      if (locs) gl.uniform2f(locs.uResolution, w, h);
    }

    // ── Loop: pausable sin salto de tiempo (tAcum retiene lo ya animado) ──
    const mediaQuieto = global.matchMedia ? global.matchMedia('(prefers-reduced-motion: reduce)') : null;
    let rafId = 0, t0 = 0, tAcum = 0, ultimoSeg = 0;
    let visible = true, oculto = document.hidden, muerto = false, perdido = false;

    function dibujar(seg) {
      ultimoSeg = seg;
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform1f(locs.uTime, seg);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    function frame(t) {
      rafId = requestAnimationFrame(frame);
      if (!t0) t0 = t;
      dibujar(tAcum + (t - t0) * 0.001);
    }
    function pausar() {
      if (rafId) { cancelAnimationFrame(rafId); rafId = 0; tAcum = ultimoSeg; }
    }
    function corresponderEstado() {
      const quieto = mediaQuieto && mediaQuieto.matches;
      const activo = !muerto && !perdido && visible && !oculto && !quieto;
      if (activo && !rafId) { t0 = 0; rafId = requestAnimationFrame(frame); }
      else if (!activo) pausar();
      if (quieto && !muerto && !perdido && locs) dibujar(12.0);  // composición estática linda
    }

    function onVisibilidad() { oculto = document.hidden; corresponderEstado(); }
    document.addEventListener('visibilitychange', onVisibilidad);

    const io = ('IntersectionObserver' in global)
      ? new IntersectionObserver(entradas => {
          visible = entradas[0] ? entradas[0].isIntersecting : true;
          corresponderEstado();
        })
      : null;
    if (io) io.observe(cont);

    const ro = ('ResizeObserver' in global) ? new ResizeObserver(aplicarTamano) : null;
    if (ro) ro.observe(cont);

    function onQuieto() { corresponderEstado(); }
    if (mediaQuieto && mediaQuieto.addEventListener) mediaQuieto.addEventListener('change', onQuieto);

    function onLost(e) { e.preventDefault(); perdido = true; corresponderEstado(); }
    function onRestored() { perdido = !initGL(); corresponderEstado(); }
    canvas.addEventListener('webglcontextlost', onLost);
    canvas.addEventListener('webglcontextrestored', onRestored);

    if (!initGL()) return null;
    canvas.className = 'strands-canvas';
    cont.appendChild(canvas);
    corresponderEstado();
    // primer frame pintado → fade-in vía CSS (.on)
    requestAnimationFrame(() => cont.classList.add('on'));

    return {
      // re-lee los var(--ob-*) del tema activo (llamar en 'theme-changed')
      refrescarColores() {
        const nuevos = coloresCss.map(resolverColorCss).filter(Boolean);
        if (nuevos.length) { rgbs = nuevos; gl.useProgram(prog); aplicarPaleta(); }
      },
      set(cambios) {
        opciones = resolverOpciones(Object.assign({}, opciones, cambios));
        gl.useProgram(prog);
        aplicarEstaticos();
      },
      destroy() {
        muerto = true;
        pausar();
        document.removeEventListener('visibilitychange', onVisibilidad);
        if (mediaQuieto && mediaQuieto.removeEventListener) mediaQuieto.removeEventListener('change', onQuieto);
        if (io) io.disconnect();
        if (ro) ro.disconnect();
        canvas.removeEventListener('webglcontextlost', onLost);
        canvas.removeEventListener('webglcontextrestored', onRestored);
        if (canvas.parentNode === cont) cont.removeChild(canvas);
        const ext = gl.getExtension('WEBGL_lose_context');
        if (ext) ext.loseContext();
      },
    };
  }

  Object.assign(global.JarvisStrands, { montar, resolverColorCss });
})(typeof window !== 'undefined' ? window : globalThis);
