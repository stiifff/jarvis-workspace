'use strict';
// Tests de titulos-i18n.js: el título vivo de la card en el idioma de la UI.
// El pane title lo escribe la CLI en el idioma de la CONVERSACIÓN (español);
// con la UI en inglés se traduce vía /api/voice/translate (Google, gratis) con
// cache por texto normalizado — misma receta que las novedades del updater.
// En español no se toca nada (ni red ni texto).
const assert = require('node:assert');
const T = require('../titulos-i18n.js');
const { norm, capear, faltantes, mostrar } = T._pure;

// ── norm: clave de cache (espacios colapsados, trim) ─────────────────────────
assert.strictEqual(norm('  Arreglando   el  bug  '), 'Arreglando el bug');
assert.strictEqual(norm(null), '');
assert.strictEqual(norm(undefined), '');

// ── capear: corte en palabra a 60, SIN "…" (port del cap de _limpiar_titulo) ──
// El backend capea el ESPAÑOL a 60; la traducción inglesa puede volver a excederlo.
assert.strictEqual(T.TITULO_MAX, 60);
assert.strictEqual(capear('Fix the layout bug', 60), 'Fix the layout bug');
// 60 exactos: no se toca.
assert.strictEqual(capear('x'.repeat(60), 60), 'x'.repeat(60));
// Largo con espacios: corta en la última palabra que entra, sin espacio colgante.
const largo = 'Refactoring the terminal title translation cache so that every card shows English';
const cortado = capear(largo, 60);
assert.ok(cortado.length <= 60, `debe quedar en ≤60 (quedó ${cortado.length})`);
assert.ok(!/\s$/.test(cortado), 'sin espacio colgante');
assert.ok(!cortado.includes('…'), 'sin puntos suspensivos (pedido del usuario: corto y punto)');
assert.ok(largo.startsWith(cortado), 'debe ser un prefijo del original');
assert.ok(cortado.lastIndexOf(' ') > 0 && largo[cortado.length] === ' ',
  'el corte cae en un límite de palabra');
// Palabra única gigante (URL, hash): corte duro a 60.
assert.strictEqual(capear('a'.repeat(75), 60), 'a'.repeat(60));

// ── faltantes: lo ÚNICO que va a la red ───────────────────────────────────────
// Dedup + skip de vacíos, cacheados y en vuelo; devuelve claves normalizadas.
assert.deepStrictEqual(
  faltantes(['Arreglando el bug', ' Arreglando  el bug ', null, '', 'Corriendo tests'], {}, {}),
  ['Arreglando el bug', 'Corriendo tests'],
);
assert.deepStrictEqual(
  faltantes(['Arreglando el bug', 'Corriendo tests'], { 'Arreglando el bug': 'Fixing the bug' }, {}),
  ['Corriendo tests'],
);
assert.deepStrictEqual(
  faltantes(['Arreglando el bug'], {}, { 'Arreglando el bug': 1 }),
  [], 'lo que ya está en vuelo NO se re-pide (single-flight)',
);
assert.deepStrictEqual(faltantes([], {}, {}), []);
assert.deepStrictEqual(faltantes(null, {}, {}), []);

// ── mostrar: qué pinta la card ────────────────────────────────────────────────
const cache = { 'Arreglando el bug': 'Fixing the bug' };
// En español: SIEMPRE el original, con o sin cache.
assert.strictEqual(mostrar('Arreglando el bug', 'es', cache), 'Arreglando el bug');
// En inglés con cache hit: la traducción.
assert.strictEqual(mostrar('Arreglando el bug', 'en', cache), 'Fixing the bug');
// El lookup normaliza (el pane puede traer espacios dobles).
assert.strictEqual(mostrar(' Arreglando  el bug ', 'en', cache), 'Fixing the bug');
// Miss (todavía no llegó la traducción): el original — degradación elegante.
assert.strictEqual(mostrar('Corriendo tests', 'en', cache), 'Corriendo tests');
// Vacíos/null: se devuelven tal cual (el caller ya los filtra).
assert.strictEqual(mostrar(null, 'en', cache), null);
assert.strictEqual(mostrar('', 'en', cache), '');
// La traducción larga se capea a 60 AL MOSTRAR (la cache guarda el texto crudo).
const cacheLarga = { 'Título': 'Translating the living terminal title into the interface language every time' };
const visible = mostrar('Título', 'en', cacheLarga);
assert.ok(visible.length <= 60, `traducción capeada a 60 (quedó ${visible.length})`);
assert.ok(!visible.includes('…'));

// ── crear(): instancia con deps inyectadas (single-flight + cache + repintado) ─
(async () => {
  let resolver;
  const pedidos = [];
  const inst = T.crear({
    lang: () => 'en',
    fetch: (url, opts) => {
      pedidos.push({ url, body: JSON.parse(opts.body) });
      return new Promise((res) => { resolver = res; });
    },
  });

  // Antes de traducir: muestra el original.
  assert.strictEqual(inst.mostrar('Arreglando el bug'), 'Arreglando el bug');

  let repintados = 0;
  inst.pedir(['Arreglando el bug', 'Arreglando el bug', null], () => { repintados++; });
  assert.strictEqual(pedidos.length, 1, 'un solo POST por lote');
  assert.strictEqual(pedidos[0].url, '/api/voice/translate');
  assert.deepStrictEqual(pedidos[0].body.texts, ['Arreglando el bug'], 'dedup antes de la red');
  assert.strictEqual(pedidos[0].body.sl, 'auto', 'sl=auto: un título que YA está en inglés no se estropea');

  // Mientras el request está en vuelo, re-pedir NO duplica la red.
  inst.pedir(['Arreglando el bug'], () => {});
  assert.strictEqual(pedidos.length, 1, 'single-flight: sin request duplicado');

  // Llega la traducción → cache + onListo (repintado).
  resolver({ ok: true, json: async () => ({ texts: ['Fixing the bug'] }) });
  await new Promise((r) => setTimeout(r, 0));
  assert.strictEqual(repintados, 1, 'onListo se llama al llegar traducciones nuevas');
  assert.strictEqual(inst.mostrar('Arreglando el bug'), 'Fixing the bug');

  // Con la traducción ya cacheada: pedir de nuevo no toca la red.
  inst.pedir(['Arreglando el bug'], () => {});
  assert.strictEqual(pedidos.length, 1, 'cache hit: cero red');

  // ── En español: pedir es un no-op total (ni red ni estado) ──
  const esPedidos = [];
  const instEs = T.crear({ lang: () => 'es', fetch: () => { esPedidos.push(1); return Promise.reject(new Error('no debe llamarse')); } });
  instEs.pedir(['Arreglando el bug'], () => { throw new Error('no debe repintar'); });
  assert.strictEqual(esPedidos.length, 0, 'en español no se toca la red');

  // ── Falla de red: se limpia el vuelo y el próximo pedir REINTENTA ──
  let intentos = 0;
  const instFalla = T.crear({ lang: () => 'en', fetch: () => { intentos++; return Promise.reject(new Error('offline')); } });
  instFalla.pedir(['Corriendo tests'], () => { throw new Error('sin traducción no se repinta'); });
  await new Promise((r) => setTimeout(r, 0));
  assert.strictEqual(instFalla.mostrar('Corriendo tests'), 'Corriendo tests', 'degrada al español');
  instFalla.pedir(['Corriendo tests'], () => {});
  await new Promise((r) => setTimeout(r, 0));
  assert.strictEqual(intentos, 2, 'tras fallar, el próximo tick reintenta (no queda en vuelo para siempre)');

  // ── Respuesta idéntica al original (ya era inglés): se cachea igual ──
  // (evita re-pedir ese título en cada poll; sl=auto hace que sea el caso legítimo)
  const idPedidos = [];
  const instId = T.crear({
    lang: () => 'en',
    fetch: (url, opts) => { idPedidos.push(1); return Promise.resolve({ ok: true, json: async () => ({ texts: ['Fixing tests'] }) }); },
  });
  instId.pedir(['Fixing tests'], () => {});
  await new Promise((r) => setTimeout(r, 0));
  instId.pedir(['Fixing tests'], () => {});
  assert.strictEqual(idPedidos.length, 1, 'la identidad también se cachea: sin martilleo por poll');

  // ── Poda de cache: no crece sin límite ──
  const instPoda = T.crear({
    lang: () => 'en',
    fetch: (url, opts) => {
      const textos = JSON.parse(opts.body).texts;
      return Promise.resolve({ ok: true, json: async () => ({ texts: textos.map((t) => 'EN ' + t) }) });
    },
  });
  for (let i = 0; i < T.MAX_CACHE + 10; i++) {
    instPoda.pedir([`titulo ${i}`], () => {});
    await new Promise((r) => setTimeout(r, 0));
  }
  assert.strictEqual(instPoda.mostrar('titulo 0'), 'titulo 0', 'la entrada más vieja se podó (FIFO)');
  assert.strictEqual(instPoda.mostrar(`titulo ${T.MAX_CACHE + 9}`), `EN titulo ${T.MAX_CACHE + 9}`, 'la reciente sigue');

  console.log('titulos-i18n.test.js OK');
})().catch((e) => { console.error(e); process.exit(1); });
