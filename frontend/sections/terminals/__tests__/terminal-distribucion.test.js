'use strict';
// Tests de la MEMORIA DE DISTRIBUCIÓN: cuando el usuario elige una disposición
// (columnas, cuadrícula, principal+N, filas…), el sistema recuerda esa FAMILIA y
// al agregar/quitar terminales re-acomoda SEGÚN esa distribución para el nuevo N.
//
// Modelo puro (en terminal-layout.js → `pure`):
//   distFromPreset(key, cells) → descriptor generalizable { k:'rows', r } | { k:'main' }
//   distCells(dist, n)          → cells para ese descriptor a un conteo N (orden lectura)
//   balancedRowsCells(n, R)     → n celdas en R filas balanceadas (top-heavy)
//   distinctYCount(cells)       → nº de filas distintas de un arreglo de celdas
//   applyDistribution(dist, orderedIds, n) → { id:{x,y,w,h} } (o null si dist auto)
//
// Corre con: node frontend/sections/terminals/__tests__/terminal-distribucion.test.js
const assert = require('assert');
const L = require('../terminal-layout.js');

const ids = n => Array.from({ length: n }, (_, i) => String(i + 1));
const approx = (a, b, tol = 1e-6) => Math.abs(a - b) <= tol;
const area = c => c.w * c.h;
const sum = arr => arr.reduce((s, x) => s + x, 0);
const EPS = 1e-9;
const solapan = (a, b) => a.x + a.w - b.x > EPS && b.x + b.w - a.x > EPS &&
                          a.y + a.h - b.y > EPS && b.y + b.h - a.y > EPS;
const filas = cells => { const s = new Set(); cells.forEach(c => s.add(Math.round(c.y * 1000))); return s.size; };
// Invariante de teselado: N celdas, dentro de [0,1], sin solapes, Σárea==1, orden lectura.
function teselaOk(cells, n, etiqueta) {
  assert.strictEqual(cells.length, n, `${etiqueta}: ${n} celdas`);
  for (const c of cells) {
    assert.ok(c.w > 0 && c.h > 0, `${etiqueta}: área positiva`);
    assert.ok(c.x >= -1e-9 && c.y >= -1e-9 && c.x + c.w <= 1 + 1e-9 && c.y + c.h <= 1 + 1e-9, `${etiqueta}: dentro del cuadrado`);
  }
  assert.ok(approx(sum(cells.map(area)), 1, 1e-6), `${etiqueta}: Σárea==1`);
  for (let i = 0; i < cells.length; i++)
    for (let j = i + 1; j < cells.length; j++)
      assert.ok(!solapan(cells[i], cells[j]), `${etiqueta}: celdas ${i},${j} sin solape`);
  const orden = cells.map((_, i) => i).sort((a, b) => (cells[a].y - cells[b].y) || (cells[a].x - cells[b].x));
  assert.deepStrictEqual(orden, cells.map((_, i) => i), `${etiqueta}: orden de lectura`);
}

// ── balancedRowsCells: reparto top-heavy en R filas, teselando ───────────────
{
  for (let n = 1; n <= 12; n++) {
    for (let R = 1; R <= n; R++) teselaOk(L.balancedRowsCells(n, R), n, `balRows(${n},${R})`);
  }
  // R=1 = columnas (una fila de n)
  assert.strictEqual(filas(L.balancedRowsCells(5, 1)), 1, 'R=1 → 1 fila');
  assert.strictEqual(L.balancedRowsCells(5, 1).length, 5, 'R=1, n=5 → 5 columnas');
  // R > n se clampa a n (no más filas que terminales)
  assert.strictEqual(filas(L.balancedRowsCells(3, 9)), 3, 'R>n se clampa a n filas');
  // top-heavy: el excedente va a las filas de ARRIBA (7 en 2 filas → [4,3])
  const c7 = L.balancedRowsCells(7, 2);
  assert.strictEqual(filas(c7), 2, '7 en 2 filas');
  const arriba = c7.filter(c => approx(c.y, 0)).length;
  const abajo = c7.filter(c => approx(c.y, 0.5)).length;
  assert.strictEqual(arriba, 4, 'top-heavy: 4 arriba');
  assert.strictEqual(abajo, 3, 'top-heavy: 3 abajo');
  // 8 en 3 filas → [3,3,2]
  const c8 = L.balancedRowsCells(8, 3);
  const cuenta = [0, 1, 2].map(r => c8.filter(c => approx(c.y, r / 3)).length);
  assert.deepStrictEqual(cuenta, [3, 3, 2], '8 en 3 filas → [3,3,2] top-heavy');
}
console.log('OK balancedRowsCells');

// ── distinctYCount: cuenta de filas ─────────────────────────────────────────
{
  assert.strictEqual(L.distinctYCount([{ x: 0, y: 0, w: 1, h: 1 }]), 1, '1 celda → 1 fila');
  assert.strictEqual(L.distinctYCount(L.snapPresets(4).find(p => p.key === 'grid').cells), 2, '2×2 → 2 filas');
  assert.strictEqual(L.distinctYCount(L.snapPresets(9).find(p => p.key === 'grid').cells), 3, '3×3 → 3 filas');
  assert.strictEqual(L.distinctYCount(L.snapPresets(6).find(p => p.key === 'cols').cells), 1, '6 columnas → 1 fila');
}
console.log('OK distinctYCount');

// ── distFromPreset: cada preset del catálogo mapea a una familia generalizable ─
{
  // main → familia 'main' (big-left)
  assert.deepStrictEqual(L.distFromPreset('main', L.snapPresets(4).find(p => p.key === 'main').cells), { k: 'main' });
  // cols / full → 1 fila
  assert.deepStrictEqual(L.distFromPreset('cols', L.snapPresets(3).find(p => p.key === 'cols').cells), { k: 'rows', r: 1 });
  assert.deepStrictEqual(L.distFromPreset('full', L.snapPresets(1)[0].cells), { k: 'rows', r: 1 });
  // grid 2×2 → 2 filas ; grid 3×3 → 3 filas
  assert.deepStrictEqual(L.distFromPreset('grid', L.snapPresets(4).find(p => p.key === 'grid').cells), { k: 'rows', r: 2 });
  assert.deepStrictEqual(L.distFromPreset('grid', L.snapPresets(9).find(p => p.key === 'grid').cells), { k: 'rows', r: 3 });
  // TODO preset del catálogo (1..12) produce un descriptor con familia válida
  for (let n = 1; n <= 12; n++) {
    for (const p of L.snapPresets(n)) {
      const d = L.distFromPreset(p.key, p.cells);
      assert.ok(d && (d.k === 'main' || (d.k === 'rows' && d.r >= 1)), `N=${n} "${p.key}" → familia válida`);
    }
  }
}
console.log('OK distFromPreset');

// ── distCells: la distribución GENERALIZA a cualquier N ──────────────────────
{
  // auto (null) → sin celdas fijas (lo resuelve el caller con la lógica vertical)
  assert.strictEqual(L.distCells(null, 5), null, 'dist auto → null');
  // 'columnas' (rows:1) siempre 1 fila, sea cual sea N
  for (const n of [2, 5, 9]) {
    const c = L.distCells({ k: 'rows', r: 1 }, n);
    teselaOk(c, n, `cols@${n}`);
    assert.strictEqual(filas(c), 1, `columnas@${n} → 1 fila`);
  }
  // 'cuadrícula 2 filas' (rows:2) mantiene 2 filas al crecer/achicar
  for (const n of [4, 6, 9]) {
    const c = L.distCells({ k: 'rows', r: 2 }, n);
    teselaOk(c, n, `rows2@${n}`);
    assert.strictEqual(filas(c), Math.min(2, n), `2 filas@${n}`);
  }
  // 3 filas se mantiene
  const g = L.distCells({ k: 'rows', r: 3 }, 12);
  teselaOk(g, 12, 'rows3@12');
  assert.strictEqual(filas(g), 3, '3 filas@12');
  // main: big-left para 2..5, degrada a 2 filas balanceadas para N≥6
  for (const n of [2, 3, 4, 5]) {
    const c = L.distCells({ k: 'main' }, n);
    teselaOk(c, n, `main@${n}`);
    assert.ok(approx(c[0].w, 0.5) && approx(c[0].h, 1), `main@${n}: principal = mitad izq completa`);
  }
  for (const n of [6, 8]) {
    const c = L.distCells({ k: 'main' }, n);
    teselaOk(c, n, `main@${n} (degradado)`);
    assert.ok(!(approx(c[0].w, 0.5) && approx(c[0].h, 1)), `main@${n}: sin principal gigante (degrada a grilla)`);
  }
}
console.log('OK distCells');

// ── applyDistribution: asigna ids a celdas en orden de lectura ───────────────
{
  // dist auto → null (el caller usa la lógica vertical existente)
  assert.strictEqual(L.applyDistribution(null, ids(4), 4), null, 'auto → null');
  // columnas: 4 ids → 4 columnas, id i → celda i
  const free = L.applyDistribution({ k: 'rows', r: 1 }, ids(4), 4);
  assert.strictEqual(Object.keys(free).length, 4, '4 ids colocados');
  const cells = L.distCells({ k: 'rows', r: 1 }, 4);
  ids(4).forEach((id, i) => assert.deepStrictEqual(free[id], cells[i], `id ${id} → celda ${i} en orden`));
  // menos celdas que ids: no explota (usa min)
  const free2 = L.applyDistribution({ k: 'rows', r: 2 }, ids(3), 3);
  assert.strictEqual(Object.keys(free2).length, 3, 'todos colocados con rows2');
}
console.log('OK applyDistribution');

// ── La propiedad que pidió el usuario: la distribución REACCIONA a través de N ─
{
  // Elijo COLUMNAS con 3 terminales → agrego una 4ª: sigue en columnas (1 fila).
  const distCols = L.distFromPreset('cols', L.snapPresets(3).find(p => p.key === 'cols').cells);
  const con4 = L.applyDistribution(distCols, ids(4), 4);
  assert.strictEqual(filas(Object.values(con4)), 1, 'elegí columnas → al agregar sigue en columnas');
  // Elijo CUADRÍCULA (2 filas) con 4 → agrego hasta 6: sigue en 2 filas.
  const distGrid = L.distFromPreset('grid', L.snapPresets(4).find(p => p.key === 'grid').cells);
  const con6 = L.applyDistribution(distGrid, ids(6), 6);
  assert.strictEqual(filas(Object.values(con6)), 2, 'elegí cuadrícula 2 filas → al agregar sigue en 2 filas');
  // Y al QUITAR (6→5) también respeta la familia (2 filas).
  const con5 = L.applyDistribution(distGrid, ids(5), 5);
  assert.strictEqual(filas(Object.values(con5)), 2, 'al quitar sigue en 2 filas');
}
console.log('OK reacción de la distribución a través de N');

// ── ORIENTACIÓN (heavy) — fix "no te podés salir del mismo diseño" (2026-07-08) ─
// Antes distFromPreset colapsaba 3·2 y 2·3 a la MISMA familia {rows,2} y la
// generalización era SIEMPRE top-heavy: elegir "2·3" aplicaba [3,2] (el diseño
// que ya tenías) y los dos tiles quedaban marcados activos a la vez. Ahora la
// familia captura la orientación: heavy:'bottom' cuando el peso va abajo.
{
  const counts = cells => L.rowCountsOf(cells);
  // rowCountsOf: columnas por fila, en orden
  assert.deepStrictEqual(counts(L.snapPresets(5).find(p => p.key === '3-2').cells), [3, 2], 'rowCountsOf 3·2');
  assert.deepStrictEqual(counts(L.snapPresets(5).find(p => p.key === '2-3').cells), [2, 3], 'rowCountsOf 2·3');
  assert.deepStrictEqual(counts(L.snapPresets(6).find(p => p.key === 'cols').cells), [6], 'rowCountsOf columnas');

  // balancedRowsCells con heavy explícito
  const abajo52 = L.balancedRowsCells(5, 2, 'bottom');
  teselaOk(abajo52, 5, 'balRows(5,2,bottom)');
  assert.deepStrictEqual(counts(abajo52), [2, 3], 'bottom-heavy: 5 en 2 filas → [2,3]');
  assert.deepStrictEqual(counts(L.balancedRowsCells(7, 2, 'bottom')), [3, 4], 'bottom-heavy: 7 → [3,4]');
  assert.deepStrictEqual(counts(L.balancedRowsCells(8, 3, 'bottom')), [2, 3, 3], 'bottom-heavy: 8 en 3 → [2,3,3]');
  assert.deepStrictEqual(counts(L.balancedRowsCells(7, 2)), [4, 3], 'default sigue top-heavy');

  // distFromPreset captura la orientación (top implícito para compat con lo persistido)
  assert.deepStrictEqual(L.distFromPreset('2-3', L.snapPresets(5).find(p => p.key === '2-3').cells),
    { k: 'rows', r: 2, heavy: 'bottom' }, '2·3 → familia bottom');
  assert.deepStrictEqual(L.distFromPreset('3-2', L.snapPresets(5).find(p => p.key === '3-2').cells),
    { k: 'rows', r: 2 }, '3·2 → familia top (sin campo heavy: compat v4)');
  assert.deepStrictEqual(L.distFromPreset('1-2', L.snapPresets(3).find(p => p.key === '1-2').cells),
    { k: 'rows', r: 2, heavy: 'bottom' }, '1·2 → bottom');

  // distCells respeta heavy al generalizar a otro N
  assert.deepStrictEqual(counts(L.distCells({ k: 'rows', r: 2, heavy: 'bottom' }, 7)), [3, 4], 'familia bottom @7 → [3,4]');
  assert.deepStrictEqual(counts(L.distCells({ k: 'rows', r: 2 }, 7)), [4, 3], 'familia top @7 → [4,3]');

  // La propiedad completa del pedido: elijo 2·3 con 5 → agrego la 6ª → [3,3];
  // quito una → VUELVE a [2,3] (antes volvía a [3,2] y "no podías salir").
  const dist = L.distFromPreset('2-3', L.snapPresets(5).find(p => p.key === '2-3').cells);
  const con6 = L.applyDistribution(dist, ids(6), 6);
  assert.deepStrictEqual(counts(Object.values(con6).sort((a, b) => (a.y - b.y) || (a.x - b.x))), [3, 3], '2·3 +1 → [3,3]');
  const con5 = L.applyDistribution(dist, ids(5), 5);
  assert.deepStrictEqual(counts(Object.values(con5).sort((a, b) => (a.y - b.y) || (a.x - b.x))), [2, 3], '2·3 al volver a 5 → [2,3], NO [3,2]');
}
console.log('OK orientación heavy (fix del diseño pegado)');

console.log('OK terminal-distribucion (todos)');
