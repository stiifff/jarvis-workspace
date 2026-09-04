'use strict';
// Tests de la lógica pura de metadatos de memorias (badges de estado,
// sublínea de la lista, resumen de salud del linter).
// Corre con: node frontend/sections/memory/__tests__/memory-meta.test.js
const assert = require('assert');
const M = require('../memory-meta.js');

// ── badges: estado + lección ──────────────────────────────────────
assert.deepStrictEqual(M.badges({ estado: 'vigente', tags: [] }), [],
  'vigente sin lección = sin badges');

let b = M.badges({ estado: 'lapida', tags: [] });
assert.strictEqual(b.length, 1);
assert.strictEqual(b[0].k, 'lapida');

b = M.badges({ estado: 'obsoleta', tags: ['x'] });
assert.strictEqual(b[0].k, 'obsoleta');

b = M.badges({ estado: 'vigente', tags: ['leccion', 'enjambre'] });
assert.strictEqual(b[0].k, 'leccion', 'tag leccion produce badge');

b = M.badges({ estado: 'lapida', tags: ['leccion'] });
assert.deepStrictEqual(b.map(x => x.k), ['lapida', 'leccion'], 'estado primero');

assert.deepStrictEqual(M.badges({}), [], 'memoria sin campos no rompe');

// ── subLinea: autor · fecha (actualizado gana) · links ───────────
assert.strictEqual(
  M.subLinea({ autor: 'Ana', creado: '2026-06-01', actualizado: '', links: [] }),
  'Ana · 2026-06-01');
assert.strictEqual(
  M.subLinea({ autor: 'Ana', creado: '2026-06-01', actualizado: '2026-07-09', links: ['a'] }),
  'Ana · act. 2026-07-09 · 1 link');
assert.strictEqual(
  M.subLinea({ autor: '', creado: '', links: ['a', 'b'] }),
  '— · 2 links');

// ── problemasSalud: solo los contadores > 0 ──────────────────────
assert.deepStrictEqual(M.problemasSalud(null), [], 'sin datos = sin problemas');
assert.deepStrictEqual(
  M.problemasSalud({ rotos: [], citas_muertas: [], huerfanas: [] }), []);
const p = M.problemasSalud({
  rotos: [{ slug: 'a', destino: 'x' }],
  citas_muertas: [{ slug: 'a', ruta: 'y' }, { slug: 'b', ruta: 'z' }],
  huerfanas: ['s'],
});
assert.deepStrictEqual(p, [
  { k: 'rotos', n: 1 },
  { k: 'citas', n: 2 },
  { k: 'huerfanas', n: 1 },
]);

// ── problemasSalud: chequeos nuevos (contrato, choques, cuarentena, guard) ──
const p2 = M.problemasSalud({
  contrato: [{ slug: 'a', faltas: ['sin-tags'] }],
  choques: [{ a: 'x', b: 'y' }],
  cuarentena: ['vieja1', 'vieja2'],
  candidatas_guard: [{ slug: 'l', veces: 4 }],
});
assert.deepStrictEqual(p2, [
  { k: 'contrato', n: 1 },
  { k: 'choques', n: 1 },
  { k: 'cuarentena', n: 2 },
  { k: 'guard', n: 1 },
], 'los 4 chequeos nuevos entran al strip');

// ── categoriasSalud: filas con problemas, ordenadas ──
const cs = M.categoriasSalud({
  por_categoria: {
    terminales: { nombre: 'Terminales & tmux', total: 31, rotos: 0, contrato: 0, huerfanas: 0, citas_muertas: 0 },
    voz: { nombre: 'Voz & Audio', total: 5, rotos: 1, contrato: 0, huerfanas: 2, citas_muertas: 0 },
  },
});
assert.strictEqual(cs.length, 1, 'solo categorías CON problemas');
assert.strictEqual(cs[0].nombre, 'Voz & Audio');
assert.strictEqual(cs[0].problemas, 3);   // 1 roto + 2 huérfanas

console.log('ok  memory-meta (badges, subLinea, problemasSalud, categoriasSalud)');

// ── problemasSalud: v3 (duplicados + candidatas a global) ──
const p3 = M.problemasSalud({
  duplicados: [{ a: 'x', b: 'y', similitud: 0.7 }],
  candidatas_global: [{ slug: 'gotcha-wsl', motivo: 'leccion-de-entorno' }],
});
assert.deepStrictEqual(p3, [
  { k: 'duplicados', n: 1 },
  { k: 'global', n: 1 },
], 'duplicados y candidatas a global entran al strip');

// ── estadoLecciones: línea compacta del loop de lecciones ──
const l1 = M.estadoLecciones({ lecciones: {
  activo: true, api_ok: true, senales_pendientes: 3, umbral: 6,
  lecciones_memoria: 12, archivo_destilado: false,
}});
assert.ok(l1.texto.includes('12'), 'cuenta las lecciones cargadas');
assert.ok(l1.texto.includes('3/6'), 'muestra señales pendientes vs umbral');
assert.strictEqual(l1.alerta, false);

const l2 = M.estadoLecciones({ lecciones: {
  activo: true, api_ok: false, senales_pendientes: 8, umbral: 6,
  lecciones_memoria: 0, archivo_destilado: false,
}});
assert.strictEqual(l2.alerta, true, 'señales sobre el umbral SIN api = alerta');
assert.ok(l2.texto.toLowerCase().includes('sin api'), 'dice por qué no destila');

assert.strictEqual(M.estadoLecciones({}), null, 'sin bloque lecciones → null');
assert.strictEqual(M.estadoLecciones({ lecciones: {} }), null, 'bloque vacío → null');

console.log('ok  memory-meta v3 (duplicados, global, estadoLecciones)');

// ── altimetro: ¿el recall rinde? (inyectadas vs leídas, 7 días) ──
const a1 = M.altimetro({ altimetro: {
  dias: 7, inyecciones: 12, lecturas: 8, lecturas_en_done: 5, tasa_lectura: 0.66,
}});
assert.ok(a1.texto.includes('12'), 'inyectadas');
assert.ok(a1.texto.includes('8'), 'leídas');
assert.ok(a1.texto.includes('66%'), 'tasa como porcentaje');
assert.ok(a1.texto.includes('5'), 'en pasos OK');

const a2 = M.altimetro({ altimetro: {
  dias: 7, inyecciones: 3, lecturas: 0, lecturas_en_done: 0, tasa_lectura: 0.0,
}});
assert.ok(a2.texto.includes('0%'), 'tasa 0 se muestra (no se oculta)');

assert.strictEqual(M.altimetro({}), null, 'sin bloque → null');
assert.strictEqual(M.altimetro({ altimetro: {} }), null, 'bloque vacío → null');
assert.strictEqual(
  M.altimetro({ altimetro: { dias: 7, inyecciones: 0, lecturas: 0, lecturas_en_done: 0, tasa_lectura: null } }),
  null, 'rodaje sin datos todavía → no mostrar nada');

console.log('ok  memory-meta altimetro');
