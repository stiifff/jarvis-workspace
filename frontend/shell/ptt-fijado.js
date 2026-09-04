'use strict';
// ─── Dictado FIJADO: lógica pura del doble-tap del PTT ───────────────────────
// Doble-tap de la tecla de voz = grabar SIN sostener la tecla (mouse y teclado
// libres para moverse por el workspace mientras se dicta; el destino ya quedó
// congelado en _activeVoiceSession al arrancar el hold). Acá viven las
// decisiones puras (SIN DOM): detectar el doble-tap y qué hacer ante blur /
// pestaña oculta con un dictado fijado en curso. El cableado a los eventos
// reales vive en workspace.js (motor PTT). Patrón UMD _pure, testeable en Node.

(function (root) {

  // Ventana máxima entre los DOS keyup para que cuente como doble-tap.
  const DOBLE_TAP_MS = 450;

  // ¿El tap actual (keyup en `ahoraMs`) forma doble-tap con el anterior?
  // `ultimoTapMs` = 0 significa "nunca hubo tap": jamás es doble-tap (sin este
  // guard, un primer tap con performance.now() chico al arrancar la página
  // caería dentro de la ventana por accidente).
  function esDobleTap(ahoraMs, ultimoTapMs) {
    if (!ultimoTapMs || ultimoTapMs <= 0) return false;
    const dt = ahoraMs - ultimoTapMs;
    return dt > 0 && dt <= DOBLE_TAP_MS;
  }

  // window.blur con un hold de mic activo. Fijado + foco en un IFRAME de esta
  // misma página (Web Preview / browser remoto) = el usuario está paseando por
  // el workspace → 'mantener' la grabación. Cualquier otro blur (otra app u
  // hold normal, donde el keyup se perdería en el iframe) → 'soltar' (corta y
  // envía): jamás mic caliente fuera de la página.
  function alBlur({ fijado, tagActivo }) {
    return (fijado && tagActivo === 'IFRAME') ? 'mantener' : 'soltar';
  }

  // visibilitychange → hidden. Con dictado fijado activo hay que commitear
  // ('enviar') ANTES de soltar el stream del mic: matar el stream primero
  // abortaría el recorder sin procesar lo ya dictado.
  function alOcultarPestana({ fijado, activo }) {
    return (fijado && activo) ? 'enviar' : 'nada';
  }

  // mouseup de un hold de MOUSE del mic (binding mouse3/mouse4). `durMs` = cuánto
  // estuvo apretado el botón. Un click más corto que el umbral es un TAP (no un
  // dictado): 'fijar' si encadena doble-tap con el click anterior, sino 'tap'
  // (descartar la captura y mostrar la píldora — espejo del tap de tecla). Un
  // hold real (≥ umbral) → 'soltar' (release normal: commitea y envía). El click
  // que CORTA un dictado fijado no pasa por acá: su mousedown fue tragado (hold
  // ya activo) y el caller salta directo al release.
  function alMouseUp({ durMs, ahoraMs, ultimoTapMs, umbralTapMs }) {
    if (durMs >= (umbralTapMs ?? 220)) return 'soltar';
    return esDobleTap(ahoraMs, ultimoTapMs) ? 'fijar' : 'tap';
  }

  // Texto del hint de la píldora durante un dictado fijado. `t` = traductor
  // opcional (JarvisI18n.t); el template entero pasa por t() y recién después
  // se interpola la tecla, así el diccionario tiene UNA entrada.
  function hintFijado(labelTecla, t) {
    const tr = t || ((s) => s);
    return '📌 ' + tr('fijado · {k} envía · Esc cancela').replace('{k}', labelTecla);
  }

  // ─── Supervivencia de captura mid-hold ─────────────────────────────
  // El track del mic puede morir SOLO con la tecla apretada (flapping del
  // dispositivo de audio en Windows, BT cambiando de perfil, etc.). Un stop
  // espontáneo NO es un release: tratarlo como tal enviaba el mensaje a mitad
  // del dictado (bug 2026-07-17, delatado por ms de horas en dictados.log =
  // commit sin release). Esta decisión dice qué hacer cuando el recorder se
  // detiene. (La gemela del SpeechRecognition —alTerminarSR— murió 2026-07-17
  // con la remoción del SR: dictado 100% server, ver memoria stt-groq-motor.)

  // onstop del MediaRecorder. `soltado` = _micSoltado (el release/discard ya
  // corrió). 'commitear' = flujo normal · 'revivir' = murió solo con la tecla
  // apretada (re-armar captura, NO enviar) · 'nada' = generación vieja.
  function alPararRecorder({ genRecorder, genVigente, soltado }) {
    if (genRecorder !== genVigente) return 'nada';
    return soltado ? 'commitear' : 'revivir';
  }

  const api = { DOBLE_TAP_MS, esDobleTap, alBlur, alOcultarPestana,
                alMouseUp, hintFijado, alPararRecorder };
  api._pure = api;

  root.PttFijado = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;

})(typeof window !== 'undefined' ? window : globalThis);
