'use strict';
// Tests de la lógica pura del SELECTOR DE DISPOSICIÓN ("snap", estilo Windows-11)
// que aparece al arrastrar una terminal. Modelo: cada preset trae `cells` en
// FRACCIONES (0-1), en orden de lectura, con cells.length === N.
//   snapPresets(n) → [{ key, label, cells:[{x,y,w,h}] }]
//   applyPreset(cells, orderedIds, draggedId, zoneIndex) → { id:{x,y,w,h} }
//   hitZone(cells, fx, fy) → índice de la celda bajo (fx,fy)
// Corre con: node frontend/sections/terminals/__tests__/terminal-snap.test.js
const assert = require('assert');
const L = require('../terminal-layout.js');

const ids = n => Array.from({ length: n }, (_, i) => String(i + 1));
const approx = (a, b, tol = 1e-6) => Math.abs(a - b) <= tol;
const area = c => c.w * c.h;
const sum = arr => arr.reduce((s, x) => s + x, 0);
// Solape con epsilon: los bordes de celdas adyacentes coinciden salvo error de
// float (0.4+0.2 !== 0.6 en doubles); en px se redondea y desaparece. Un solape
// REAL supera EPS holgadamente.
const EPS = 1e-9;
const solapan = (a, b) => a.x + a.w - b.x > EPS && b.x + b.w - a.x > EPS &&
                          a.y + a.h - b.y > EPS && b.y + b.h - a.y > EPS;

// ── snapPresets: para cada N los presets teselan el cuadrado unidad ──────────
{
  for (let n = 1; n <= 12; n++) {
    const presets = L.snapPresets(n);
    assert.ok(Array.isArray(presets) && presets.length >= 1, `N=${n} devuelve presets`);
    const keys = new Set();
    for (const p of presets) {
      assert.ok(p.key && typeof p.label === 'string' && p.label, `N=${n} preset con key+label`);
      assert.ok(!keys.has(p.key), `N=${n} keys únicas (${p.key})`);
      keys.add(p.key);
      // cardinalidad exacta: una celda por terminal
      assert.strictEqual(p.cells.length, n, `N=${n} preset "${p.key}" tiene ${n} celdas`);
      // dentro de [0,1]
      for (const c of p.cells) {
        assert.ok(c.x >= -1e-9 && c.y >= -1e-9 && c.x + c.w <= 1 + 1e-9 && c.y + c.h <= 1 + 1e-9,
          `N=${n} "${p.key}" celda dentro del cuadrado`);
        assert.ok(c.w > 0 && c.h > 0, `N=${n} "${p.key}" celda con área positiva`);
      }
      // cobertura total (Σ áreas ≈ 1) — teselado sin huecos
      assert.ok(approx(sum(p.cells.map(area)), 1, 1e-6), `N=${n} "${p.key}" Σárea==1`);
      // sin solapes (bordes que se tocan NO cuentan)
      for (let i = 0; i < p.cells.length; i++)
        for (let j = i + 1; j < p.cells.length; j++)
          assert.ok(!solapan(p.cells[i], p.cells[j]), `N=${n} "${p.key}" celdas ${i},${j} sin solape`);
      // orden de lectura: ordenar por (y,x) no cambia la secuencia
      const orden = p.cells.map((c, i) => i)
        .sort((a, b) => (p.cells[a].y - p.cells[b].y) || (p.cells[a].x - p.cells[b].x));
      assert.deepStrictEqual(orden, p.cells.map((_, i) => i), `N=${n} "${p.key}" celdas en orden de lectura`);
    }
  }
}
console.log('OK snapPresets');

// ── snapPresets: catálogo esperado por conteo (varía con N, como pidió el user) ──
{
  // 4 terminales → sale el set de 4; 6 → el set de 6. Verificamos algunas claves.
  assert.ok(L.snapPresets(1).length === 1, 'N=1 un solo preset');
  assert.deepStrictEqual(L.snapPresets(2).map(p => p.key), ['cols', 'rows'], 'N=2');
  assert.ok(L.snapPresets(4).some(p => p.key === 'grid'), 'N=4 incluye 2×2');
  assert.ok(L.snapPresets(4).some(p => p.key === 'main'), 'N=4 incluye principal+resto');
  assert.ok(L.snapPresets(6).some(p => p.key === 'grid'), 'N=6 incluye 3×2');
  // el preset "main" (_bigLeft) SOLO existe de +2 a +4, o sea N=3,4,5: con N≥6 la
  // grande ocupa media pantalla y el resto queda ilegible (pedido del usuario).
  for (const n of [3, 4, 5]) {
    const m = L.snapPresets(n).find(p => p.key === 'main');
    assert.ok(m, `N=${n} SÍ tiene main (Principal + ${n - 1})`);
    assert.ok(approx(m.cells[0].w, 0.5) && approx(m.cells[0].h, 1), `N=${n} main: celda 0 = mitad izq completa`);
  }
  for (let n = 6; n <= 12; n++) {
    assert.ok(!L.snapPresets(n).some(p => p.key === 'main'), `N=${n} NO tiene main (terminales ilegibles)`);
  }
}
console.log('OK snapPresets catálogo');

// ── applyPreset: la arrastrada cae en la zona elegida; el resto rellena en orden ─
{
  const preset = L.snapPresets(4).find(p => p.key === 'grid');   // 2×2
  const orden = ids(4);   // ['1','2','3','4']
  // arrastro '3' a la zona 0 (arriba-izq)
  const free = L.applyPreset(preset.cells, orden, '3', 0);
  assert.strictEqual(Object.keys(free).length, 4, 'todas las terminales colocadas');
  // '3' ocupa la celda 0
  assert.deepStrictEqual(
    { x: free['3'].x, y: free['3'].y, w: free['3'].w, h: free['3'].h },
    preset.cells[0], 'la arrastrada va a la zona elegida');
  // el resto ['1','2','4'] rellena las celdas 1,2,3 en orden
  assert.deepStrictEqual(free['1'], preset.cells[1], 'resto en orden: 1→celda1');
  assert.deepStrictEqual(free['2'], preset.cells[2], 'resto en orden: 2→celda2');
  assert.deepStrictEqual(free['4'], preset.cells[3], 'resto en orden: 4→celda3');

  // arrastro '1' a la zona 3 (última): el resto ['2','3','4'] va a 0,1,2
  const free2 = L.applyPreset(preset.cells, orden, '1', 3);
  assert.deepStrictEqual(free2['1'], preset.cells[3], 'arrastrada a la última zona');
  assert.deepStrictEqual(free2['2'], preset.cells[0], 'resto arranca en celda0');
  assert.deepStrictEqual(free2['4'], preset.cells[2], 'resto ordenado');

  // zoneIndex fuera de rango → clamp a 0 (robustez ante hit-test raro)
  const free3 = L.applyPreset(preset.cells, orden, '2', 99);
  assert.deepStrictEqual(free3['2'], preset.cells[0], 'zoneIndex inválido → zona 0');
}
console.log('OK applyPreset');

// ── Variedad REAL del catálogo (pedido 2026-07-08): opciones distintas entre sí ─
{
  // No puede haber dos presets EFECTIVAMENTE iguales para el mismo N — era parte
  // del "no te podés salir del mismo diseño": opciones que parecían distintas
  // aplicaban lo mismo.
  const firma = cells => JSON.stringify(cells.map(c => [c.x, c.y, c.w, c.h].map(v => +v.toFixed(4))));
  for (let n = 1; n <= 12; n++) {
    const presets = L.snapPresets(n);
    const vistas = new Set();
    for (const p of presets) {
      const f = firma(p.cells);
      assert.ok(!vistas.has(f), `N=${n} "${p.key}" no duplica otro preset del set`);
      vistas.add(f);
    }
  }
  // Todo N≥3 ofrece al menos 3 opciones (con 2 de las cuales elegida una queda
  // UNA sola alternativa — muy poco para "cambiar de estilo").
  for (let n = 3; n <= 12; n++)
    assert.ok(L.snapPresets(n).length >= 3, `N=${n} tiene ≥3 disposiciones (hay ${L.snapPresets(n).length})`);
  // Espejos bottom-heavy nuevos: existen y son bottom-heavy de verdad.
  const abajoPesado = key => {
    for (let n = 2; n <= 12; n++) {
      const p = L.snapPresets(n).find(q => q.key === key);
      if (!p) continue;
      const counts = L.rowCountsOf(p.cells);
      assert.ok(counts[0] < counts[counts.length - 1], `"${key}" es bottom-heavy (${counts})`);
      return true;
    }
    return false;
  };
  for (const key of ['2-4', '4-5', '4-6', '5-6', '2-3-3']) assert.ok(abajoPesado(key), `existe el espejo "${key}"`);
}
console.log('OK variedad del catálogo');

// ── cellsToFree: ids en orden de lectura → celdas exactas del preset ─────────
{
  const preset = L.snapPresets(5).find(p => p.key === '2-3');
  const free = L.cellsToFree(preset.cells, ids(5));
  assert.strictEqual(Object.keys(free).length, 5, 'todos colocados');
  ids(5).forEach((id, i) => assert.deepStrictEqual(free[id], preset.cells[i], `id ${id} → celda ${i} EXACTA`));
  // Menos ids que celdas: no explota ni inventa
  const free2 = L.cellsToFree(preset.cells, ids(3));
  assert.strictEqual(Object.keys(free2).length, 3, 'con menos ids coloca los que hay');
}
console.log('OK cellsToFree');

// ── presetMatchesFree: el tile activo es el que MATCHEA el layout real ───────
{
  const p23 = L.snapPresets(5).find(p => p.key === '2-3');
  const p32 = L.snapPresets(5).find(p => p.key === '3-2');
  const free = L.cellsToFree(p23.cells, ['9', '4', '7', '1', '2']);
  assert.ok(L.presetMatchesFree(p23.cells, free), 'el layout 2·3 matchea SU preset');
  assert.ok(!L.presetMatchesFree(p32.cells, free), 'el layout 2·3 NO matchea 3·2 (antes ambos quedaban .sel)');
  // Una pared movida a mano → ya no matchea ninguno (honesto: layout custom)
  const custom = { ...free };
  const k = Object.keys(custom)[0];
  custom[k] = { ...custom[k], w: custom[k].w + 0.08 };
  assert.ok(!L.presetMatchesFree(p23.cells, custom), 'pared movida → sin match');
  // Conteo distinto → false
  assert.ok(!L.presetMatchesFree(p23.cells, L.cellsToFree(p32.cells, ids(3))), 'conteo distinto → false');
}
console.log('OK presetMatchesFree');

// ── sinPresetActual: el layout en el que YA estás no se ofrece como opción ───
{
  const presets5 = L.snapPresets(5);
  const p32 = presets5.find(p => p.key === '3-2');
  // Estoy EXACTAMENTE en 3·2 → el panel no ofrece 3·2 (pedido 2026-07-08:
  // "que detecte en qué layout estás y no salga el mismo")
  const free = L.cellsToFree(p32.cells, ids(5));
  const sin = L.sinPresetActual(presets5, free);
  assert.ok(!sin.some(p => p.key === '3-2'), 'el preset actual NO aparece');
  assert.strictEqual(sin.length, presets5.length - 1, 'solo se excluye UNO');
  assert.deepStrictEqual(sin.map(p => p.key), presets5.filter(p => p.key !== '3-2').map(p => p.key),
    'el resto queda en su orden');
  // Layout CUSTOM (pared movida a mano): ya no es ningún preset → se ofrecen todos
  // (incluido 3·2 — sirve para "volver al 3·2 limpio")
  const custom = { ...free };
  const k = Object.keys(custom)[0];
  custom[k] = { ...custom[k], w: custom[k].w + 0.08 };
  assert.strictEqual(L.sinPresetActual(presets5, custom).length, presets5.length, 'custom → nada se excluye');
  // free vacío / conteo distinto → nada se excluye (robustez)
  assert.strictEqual(L.sinPresetActual(presets5, {}).length, presets5.length, 'free vacío → todos');
  assert.strictEqual(L.sinPresetActual(presets5, L.cellsToFree(L.snapPresets(3)[0].cells, ids(3))).length,
    presets5.length, 'conteo distinto → todos');
  // Con 2 terminales queda exactamente LA alternativa
  const presets2 = L.snapPresets(2);
  const freeCols = L.cellsToFree(presets2.find(p => p.key === 'cols').cells, ids(2));
  const sin2 = L.sinPresetActual(presets2, freeCols);
  assert.deepStrictEqual(sin2.map(p => p.key), ['rows'], 'en cols con N=2 → solo queda rows');
}
console.log('OK sinPresetActual');

// ── hitZone: punto dentro de una celda devuelve su índice ───────────────────
{
  const cells = L.snapPresets(4).find(p => p.key === 'grid').cells;   // 2×2
  assert.strictEqual(L.hitZone(cells, 0.25, 0.25), 0, 'arriba-izq → 0');
  assert.strictEqual(L.hitZone(cells, 0.75, 0.25), 1, 'arriba-der → 1');
  assert.strictEqual(L.hitZone(cells, 0.25, 0.75), 2, 'abajo-izq → 2');
  assert.strictEqual(L.hitZone(cells, 0.75, 0.75), 3, 'abajo-der → 3');
  // fuera del cuadrado → la más cercana por centro (no -1)
  assert.strictEqual(L.hitZone(cells, -0.5, -0.5), 0, 'fuera arriba-izq → celda 0 (cercana)');
  assert.strictEqual(L.hitZone(cells, 1.5, 1.5), 3, 'fuera abajo-der → celda 3 (cercana)');
}
console.log('OK hitZone');

console.log('OK terminal-snap (todos)');
