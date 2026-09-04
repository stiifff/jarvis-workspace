// Tests de JarvisSTT (stt-jerga.js): post-corrección determinista de jerga del
// workspace en el texto dictado + diagnóstico de captura del mic.
// (La decisión de fuente / re-rank / presupuesto del SR se removió 2026-07-17:
// el dictado es 100% server —Groq con fallback local— sin SpeechRecognition.)
'use strict';
const assert = require('assert');
require('../stt-jerga.js');
const { corregirJerga, diagnosticoMic } = globalThis.JarvisSTT._pure;

// ── corregirJerga: los errores REALES observados (benchmark 2026-07-09) ──
assert.strictEqual(
  corregirJerga('Jarvis, hace que mid del frontend'),
  'Jarvis, hace commit del frontend',
  '"que mid" (error medido en TODOS los modelos) → commit');
assert.strictEqual(corregirJerga('hacé comité del backend'), 'hacé commit del backend',
  '"comité" gateado por forma de hacer → commit');
assert.strictEqual(corregirJerga('el comité de vecinos se reúne'), 'el comité de vecinos se reúne',
  '"comité" SIN verbo hacer delante es español legítimo — no tocar');
assert.strictEqual(corregirJerga('hacele un comit a eso'), 'hacele un commit a eso');

// ── nombres de CLIs / herramientas ──
assert.strictEqual(corregirJerga('abrí una terminal con yarvis'), 'abrí una terminal con Jarvis');
assert.strictEqual(corregirJerga('preguntale a jarbis'), 'preguntale a Jarvis');
assert.strictEqual(corregirJerga('lanzá cloud code y códex'), 'lanzá Claude Code y Codex');
assert.strictEqual(corregirJerga('usá clod code para eso'), 'usá Claude Code para eso');
assert.strictEqual(corregirJerga('probá con quen y con open code'), 'probá con qwen y con opencode');
assert.strictEqual(corregirJerga('sumá géminis al workflow'), 'sumá Gemini al workflow');
assert.strictEqual(corregirJerga('mirá la sesión de temux'), 'mirá la sesión de tmux');
assert.strictEqual(corregirJerga('en el te mux quedó colgado'), 'en el tmux quedó colgado');
assert.strictEqual(corregirJerga('abrí anti gravity'), 'abrí antigravity');

// ── términos de dev partidos o fonetizados ──
assert.strictEqual(corregirJerga('tocá el front end y el back end'), 'tocá el frontend y el backend');
assert.strictEqual(corregirJerga('mostrame el dash board'), 'mostrame el dashboard');
assert.strictEqual(corregirJerga('fijate el work flow'), 'fijate el workflow');
assert.strictEqual(corregirJerga('levantá el local host'), 'levantá el localhost');
assert.strictEqual(corregirJerga('hacé puch y deploi'), 'hacé push y deploy');
assert.strictEqual(corregirJerga('hacé merch de la rama'), 'hacé merge de la rama');
assert.strictEqual(corregirJerga('agregá la sección de merch a la landing'),
  'agregá la sección de merch a la landing',
  '"merch" sin verbo hacer = merchandising legítimo — no tocar');
assert.strictEqual(corregirJerga('tablero canban'), 'tablero kanban');

// ── errores reales de data/dictados.log (2026-07-10) ──
assert.strictEqual(corregirJerga('la animación que hace el header del mokap'),
  'la animación que hace el header del mockup', 'mokap → mockup');
assert.strictEqual(corregirJerga('sale un escrol bar sin sentido'),
  'sale un scrollbar sin sentido', 'escrol bar → scrollbar');
assert.strictEqual(corregirJerga('quitá el scroll bar de la terminal'),
  'quitá el scrollbar de la terminal');
assert.strictEqual(corregirJerga('no voy a poner ahí el webbuilder'),
  'no voy a poner ahí el Web Builder', 'webbuilder → Web Builder');
assert.strictEqual(corregirJerga('el diseño del header y el saldívar de workspaces'),
  'el diseño del header y el sidebar de workspaces', 'saldívar gateado por artículo → sidebar');
assert.strictEqual(corregirJerga('la señora Saldívar vino ayer'),
  'la señora Saldívar vino ayer', 'apellido sin artículo pegado: no tocar');
assert.strictEqual(corregirJerga('probá el said bar nuevo'),
  'probá el sidebar nuevo', 'said bar → sidebar');
assert.strictEqual(corregirJerga('O k perfecto bueno'), 'ok perfecto bueno',
  '"O k" → ok (la k suelta no es español)');

// ── no romper español normal (falsos positivos) ──
for (const frase of [
  'quiero que la cuenta quede al día',          // "cuen" adentro de palabra
  '¿quién hizo esto?',                          // quién ≠ quen
  'el codo me duele',                           // codo ≠ code
  'la nube es cloud pero acá no hay code',      // cloud/code sueltos: no tocar
  'preví ese problema ayer',                    // preví ≠ preview
]) {
  assert.strictEqual(corregirJerga(frase), frase, `no tocar: "${frase}"`);
}

// ── idempotencia: corregir dos veces = corregir una ──
const unaVez = corregirJerga('hacé comité del front end con yarvis y temux');
assert.strictEqual(corregirJerga(unaVez), unaVez, 'idempotente');

// ── entradas degeneradas ──
assert.strictEqual(corregirJerga(''), '');
assert.strictEqual(corregirJerga(null), '');
assert.strictEqual(corregirJerga(undefined), '');

// ── diagnosticoMic: avisos de captura mala ──
assert.strictEqual(diagnosticoMic({ picoDb: -8, clips: 0, etiqueta: 'Micrófono (USB)' }), null,
  'niveles sanos: sin aviso');
assert.strictEqual(diagnosticoMic({ picoDb: -30, clips: 0, etiqueta: '' }), 'bajo',
  'picos < -24dBFS: mic muy bajo');
assert.strictEqual(diagnosticoMic({ picoDb: -2, clips: 12, etiqueta: '' }), 'saturado',
  'clipping: saturado');
assert.strictEqual(diagnosticoMic({ picoDb: -10, clips: 0, etiqueta: 'Headset (WH-1000 Hands-Free AG Audio)' }),
  'bluetooth', 'auricular BT en perfil HFP (telefonía): avisar');
assert.strictEqual(diagnosticoMic({ picoDb: -30, clips: 5, etiqueta: 'X Hands-Free' }), 'bluetooth',
  'prioridad: bluetooth > saturado > bajo');
assert.strictEqual(diagnosticoMic({ picoDb: null, clips: 0, etiqueta: '' }), null,
  'sin métricas (waveform apagado): sin aviso');
assert.strictEqual(diagnosticoMic({}), null, 'objeto vacío: sin aviso');

// ── API depurada (2026-07-17): el aparato del SR ya NO se expone ──
// Con el dictado 100% server (Groq + fallback local) murieron la elección de
// fuente, el re-rank de alternativas, la unión de fragmentos, el bias on-device
// y el presupuesto SR-vs-server. Si reaparecen, alguien está reintroduciendo
// el camino de Google — ver memoria stt-groq-motor.
for (const muerta of ['decidirFuenteDictado', 'elegirAlternativa', 'unirFragmento',
                      'frasesParaBias', 'elegirTextoDictado', 'presupuestoServidor']) {
  assert.ok(!(muerta in globalThis.JarvisSTT), `API muerta expuesta: ${muerta}`);
  assert.ok(!(muerta in globalThis.JarvisSTT._pure), `API muerta en _pure: ${muerta}`);
}

console.log('stt-jerga: OK');
