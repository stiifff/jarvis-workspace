'use strict';
// Tests de la lógica pura del mosaico de terminales (grilla por fracciones).
// Modelo: { rows: [ { hFrac, cells: [ {id, wFrac} ] } ] }  con
//   Σ rows[].hFrac == 1  y  por fila  Σ cells[].wFrac == 1.
// Corre con: node frontend/sections/terminals/__tests__/terminal-layout.test.js
const assert = require('assert');
const L = require('../terminal-layout.js');

const W = 1200, H = 800, GAP = L.GAP;
const ids = n => Array.from({ length: n }, (_, i) => String(i + 1));
const approx = (a, b, tol = 1.5) => Math.abs(a - b) <= tol;
const sum = arr => arr.reduce((s, x) => s + x, 0);

// ── balancedGrid: patrón cols=ceil(√N), última fila estira ────────
{
  // Conteo de celdas por fila para N=1..9 (lo acordado con el usuario).
  const esperado = {
    1: [1], 2: [2], 3: [2, 1], 4: [2, 2], 5: [3, 2],
    6: [3, 3], 7: [3, 3, 1], 8: [3, 3, 2], 9: [3, 3, 3],
  };
  for (const n of Object.keys(esperado)) {
    const g = L.balancedGrid(ids(Number(n)));
    const filas = g.rows.map(r => r.cells.length);
    assert.deepStrictEqual(filas, esperado[n], `patrón de filas para N=${n}`);
    // fracciones suman 1 (con tolerancia de redondeo)
    assert.ok(approx(sum(g.rows.map(r => r.hFrac)), 1, 1e-6), `Σ hFrac==1 N=${n}`);
    for (const r of g.rows) assert.ok(approx(sum(r.cells.map(c => c.wFrac)), 1, 1e-6), `Σ wFrac==1 N=${n}`);
    // todos los ids presentes, sin repetir, en orden
    assert.deepStrictEqual(L.gridIds(g), ids(Number(n)), `gridIds N=${n}`);
  }
}
console.log('OK balancedGrid');

// ── deriveRects: llena W×H, sin solapes, dentro de los bordes ─────
{
  for (const n of [1, 2, 3, 5, 7, 9]) {
    const g = L.balancedGrid(ids(n));
    const rects = L.deriveRects(g, W, H, GAP);
    const rs = Object.values(rects);
    assert.strictEqual(rs.length, n, `N=${n} rects`);
    for (const r of rs) {
      assert.ok(r.x >= 0 && r.y >= 0, `dentro origen N=${n}`);
      assert.ok(r.x + r.w <= W + 1, `no se pasa a la derecha N=${n}`);
      assert.ok(r.y + r.h <= H + 1, `no se pasa abajo N=${n}`);
    }
    for (let i = 0; i < rs.length; i++)
      for (let j = i + 1; j < rs.length; j++)
        assert.ok(!L.overlaps(rs[i], rs[j]), `sin solape N=${n}`);
  }
  // Caso 2: deben llenar el ancho (dos celdas lado a lado tocando los bordes útiles)
  const g = L.balancedGrid(ids(2));
  const r = L.deriveRects(g, W, H, GAP);
  assert.ok(approx(r['1'].x, GAP), 'primera celda pegada al margen izq');
  assert.ok(approx(r['2'].x + r['2'].w, W - GAP), 'segunda celda llega al margen der');
  assert.ok(approx(r['1'].h, H - 2 * GAP), 'una fila => alto completo');
}
console.log('OK deriveRects');

// ── findCell: ubica (rowIdx, cellIdx) de un id ────────────────────
{
  const g = L.balancedGrid(ids(5)); // [1,2,3]/[4,5]
  assert.deepStrictEqual(L.findCell(g, '3'), { rowIdx: 0, cellIdx: 2 }, 'id 3 en fila0 col2');
  assert.deepStrictEqual(L.findCell(g, '4'), { rowIdx: 1, cellIdx: 0 }, 'id 4 en fila1 col0');
  assert.strictEqual(L.findCell(g, 'nope'), null, 'id inexistente => null');
}
console.log('OK findCell');

// ── resizeVertical: divisor entre celda y su vecina de la fila ────
{
  const g = L.balancedGrid(ids(2)); // una fila, 2 celdas 0.5/0.5
  const minFrac = 0.1;
  const g2 = L.resizeVertical(g, 0, 0, 0.2, minFrac); // celda0 +0.2, celda1 -0.2
  assert.ok(approx(g2.rows[0].cells[0].wFrac, 0.7, 1e-6), 'celda0 creció');
  assert.ok(approx(g2.rows[0].cells[1].wFrac, 0.3, 1e-6), 'vecina se achicó (no se movió)');
  assert.ok(approx(sum(g2.rows[0].cells.map(c => c.wFrac)), 1, 1e-6), 'suma se mantiene');
  assert.deepStrictEqual(L.gridIds(g2), L.gridIds(g), 'ids intactos');
  // reversible: volver a achicar restituye a la vecina
  const g3 = L.resizeVertical(g2, 0, 0, -0.2, minFrac);
  assert.ok(approx(g3.rows[0].cells[1].wFrac, 0.5, 1e-6), 'vecina volvió a crecer');
  // clamp al mínimo: no se puede pasar
  const g4 = L.resizeVertical(g, 0, 0, 0.9, minFrac);
  assert.ok(approx(g4.rows[0].cells[1].wFrac, minFrac, 1e-6), 'vecina topa en el mínimo');
  assert.ok(approx(g4.rows[0].cells[0].wFrac, 1 - minFrac, 1e-6), 'la otra toma el resto');
  // última celda de la fila: no hay vecina => no-op
  const last = L.resizeVertical(g, 0, 1, 0.2, minFrac);
  assert.deepStrictEqual(last, g, 'sin vecina a la derecha => no cambia');
}
console.log('OK resizeVertical');

// ── resizeHorizontal: divisor entre fila y la fila siguiente ──────
{
  const g = L.balancedGrid(ids(4)); // 2 filas 0.5/0.5
  const minFrac = 0.1;
  const g2 = L.resizeHorizontal(g, 0, 0.2, minFrac);
  assert.ok(approx(g2.rows[0].hFrac, 0.7, 1e-6), 'fila0 creció');
  assert.ok(approx(g2.rows[1].hFrac, 0.3, 1e-6), 'fila vecina se achicó');
  assert.ok(approx(sum(g2.rows.map(r => r.hFrac)), 1, 1e-6), 'suma alturas se mantiene');
  // última fila: no-op
  const last = L.resizeHorizontal(g, 1, 0.2, minFrac);
  assert.deepStrictEqual(last, g, 'sin fila debajo => no cambia');
}
console.log('OK resizeHorizontal');

// ── deriveDividers: divisores invisibles en los gutters ──────────
{
  // N=1: sin vecinos => sin divisores
  assert.deepStrictEqual(L.deriveDividers(L.balancedGrid(ids(1)), W, H, GAP), [], 'N=1 sin divisores');

  // N=2 (una fila, 2 celdas): un divisor vertical en el gap, sin horizontales
  {
    const g = L.balancedGrid(ids(2));
    const rects = L.deriveRects(g, W, H, GAP);
    const divs = L.deriveDividers(g, W, H, GAP);
    assert.strictEqual(divs.length, 1, 'N=2 => 1 divisor');
    const d = divs[0];
    assert.strictEqual(d.type, 'v', 'es vertical');
    assert.deepStrictEqual({ rowIdx: d.rowIdx, cellIdx: d.cellIdx }, { rowIdx: 0, cellIdx: 0 }, 'entre celda 0 y 1');
    assert.ok(approx(d.x, rects['1'].x + rects['1'].w), 'arranca donde termina la celda izq');
    assert.ok(approx(d.w, GAP), 'ancho = gap');
    assert.ok(approx(d.x + d.w, rects['2'].x), 'termina donde arranca la celda der');
    assert.ok(approx(d.y, rects['1'].y) && approx(d.h, rects['1'].h), 'cubre el alto de la fila');
  }

  // N=4 (2×2): un vertical por fila + un horizontal entre filas
  {
    const g = L.balancedGrid(ids(4));
    const rects = L.deriveRects(g, W, H, GAP);
    const divs = L.deriveDividers(g, W, H, GAP);
    const vs = divs.filter(d => d.type === 'v');
    const hs = divs.filter(d => d.type === 'h');
    assert.strictEqual(vs.length, 2, 'N=4 => 2 verticales');
    assert.strictEqual(hs.length, 1, 'N=4 => 1 horizontal');
    const h = hs[0];
    assert.strictEqual(h.rowIdx, 0, 'horizontal entre fila 0 y 1');
    assert.ok(approx(h.y, rects['1'].y + rects['1'].h), 'arranca donde termina la fila 0');
    assert.ok(approx(h.h, GAP), 'alto = gap');
    assert.ok(approx(h.y + h.h, rects['3'].y), 'termina donde arranca la fila 1');
    assert.ok(approx(h.x, 0) && approx(h.w, W), 'cruza todo el ancho (mueve filas enteras)');
    // los divisores verticales NO pisan ninguna celda
    for (const d of vs)
      for (const r of Object.values(rects))
        assert.ok(!L.overlaps(d, r), 'divisor vertical no solapa celdas');
  }

  // N=5 ([3,2]): 2 verticales en fila 0, 1 en fila 1, 1 horizontal
  {
    const g = L.balancedGrid(ids(5));
    const divs = L.deriveDividers(g, W, H, GAP);
    const vsFila0 = divs.filter(d => d.type === 'v' && d.rowIdx === 0);
    const vsFila1 = divs.filter(d => d.type === 'v' && d.rowIdx === 1);
    const hs = divs.filter(d => d.type === 'h');
    assert.strictEqual(vsFila0.length, 2, 'fila de 3 celdas => 2 divisores');
    assert.strictEqual(vsFila1.length, 1, 'fila de 2 celdas => 1 divisor');
    assert.strictEqual(hs.length, 1, '2 filas => 1 horizontal');
  }
}
console.log('OK deriveDividers');

// ── swapCells: intercambia ids, conserva los tamaños de cada celda ─
{
  const g = L.balancedGrid(ids(3)); // [1,2]/[3]
  const g2 = L.swapCells(g, '1', '3');
  assert.strictEqual(g2.rows[0].cells[0].id, '3', 'id 3 ahora en pos de 1');
  assert.strictEqual(g2.rows[1].cells[0].id, '1', 'id 1 ahora en pos de 3');
  // los wFrac de cada SLOT se conservan (cada card adopta el tamaño de su celda)
  assert.ok(approx(g2.rows[0].cells[0].wFrac, g.rows[0].cells[0].wFrac, 1e-6), 'wFrac del slot se conserva');
  // swap consigo mismo o id inexistente => sin cambios
  assert.deepStrictEqual(L.swapCells(g, '1', '1'), g, 'swap consigo mismo no cambia');
  assert.deepStrictEqual(L.swapCells(g, '1', 'nope'), g, 'swap con inexistente no cambia');
}
console.log('OK swapCells');

// ── setInteracting: drags externos (splitter del dock) NO refitean por frame ─
// El motor DOM (browser-only) se instala recién cuando existe `document`: lo
// fakeamos y re-requerimos el módulo para testear el contrato del API en Node.
// Contrato: mientras una interacción está activa (drag del splitter del dock o
// de un divisor del grid), relayoutAll() solo re-renderiza — NO refitea. Cada
// fit manda un resize a tmux y el TUI redibuja entero: un drag continuo sería
// una tormenta de redraws que tritura el scrollback (ver [[tmux-size-clamping]]).
// El refit ÚNICO sale al soltar: setInteracting(false) + relayoutAll().
(async () => {
  globalThis.document = {};   // habilita el bloque "Motor DOM" del módulo
  globalThis.requestAnimationFrame = fn => setTimeout(fn, 16); // _refit(force) usa rAF
  // localStorage fake: _persistLibre escribe acá → es la ventana para OBSERVAR
  // el _free interno del motor (no hay getter a propósito).
  globalThis.localStorage = {
    _s: {},
    setItem(k, v) { this._s[k] = String(v); },
    getItem(k) { return (k in this._s) ? this._s[k] : null; },
  };
  delete require.cache[require.resolve('../terminal-layout.js')];
  require('../terminal-layout.js');
  const TL = globalThis.TerminalLayout;
  delete globalThis.document;

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  let refits = 0;
  TL.setRefitCallback(() => { refits++; });
  assert.strictEqual(typeof TL.setInteracting, 'function', 'expone setInteracting()');

  // Layout con una card (sin _gridEl: render() no-opea, _refit sí corre).
  TL.init(1, null);
  TL.add('7');                 // refitea (force) — esperar y resetear el contador
  await sleep(300);
  refits = 0;

  TL.setInteracting(true);
  assert.strictEqual(TL.isInteracting(), true, 'isInteracting refleja el flag');
  TL.relayoutAll();            // frame de drag: render solo
  TL.relayoutAll();            // otro frame
  await sleep(150);            // _refit agenda a 60ms — esperar de sobra
  assert.strictEqual(refits, 0, 'durante la interacción relayoutAll NO refitea');

  TL.setInteracting(false);
  assert.strictEqual(TL.isInteracting(), false, 'el flag vuelve a false');
  TL.relayoutAll();            // pointerup: el refit único
  await sleep(150);
  assert.ok(refits > 0, 'al soltar, relayoutAll SÍ refitea');

  console.log('OK setInteracting');

  // ── remove() del motor DOM: la banda queda PAREJA al cerrar (cableado) ──────
  // Contrato (pedido 2026-07-03): cerrar una terminal re-reparte su banda en
  // partes IGUALES (quitarDeBandaF) — antes una vecina absorbía todo y quedaba
  // el doble de ancha. Se observa por el _free persistido en el localStorage fake.
  {
    TL.setInteracting(false);
    TL.init(99, null);          // proyecto limpio (sin layout persistido)
    TL.add('a'); TL.add('b'); TL.add('c');   // → 3 columnas de ⅓ (tile2col)
    await sleep(300);
    const leer = () => JSON.parse(globalThis.localStorage.getItem('jarvis.terminals.layout.99')).free;
    const antes = leer();
    assert.ok(Math.abs(antes['b'].w - 1 / 3) < 1e-9, 'punto de partida: tercios');

    TL.remove('b');             // cerrar la del medio
    const despues = leer();
    assert.strictEqual(despues['b'], undefined, 'la cerrada sale del layout');
    assert.ok(Math.abs(despues['a'].x - 0) < 1e-9 && Math.abs(despues['a'].w - 0.5) < 1e-9,
              'a queda en mitad izquierda (no ⅔ por absorción)');
    assert.ok(Math.abs(despues['c'].x - 0.5) < 1e-9 && Math.abs(despues['c'].w - 0.5) < 1e-9,
              'c queda en mitad derecha (se corre y agranda)');
    console.log('OK remove() re-reparte la banda pareja (motor DOM)');
  }

  // ── add() 1→12 por el motor DOM: JAMÁS 3 filas + ABAJO CONGELADA (pedido real) ──
  // Pedido 2026-07-04: al agregar de a una, pasar de 9 no abre 3ª fila y — lo clave —
  // el 10º/11º/12º "se crean arriba" SIN mover a las 3 de abajo. Se maneja el add()
  // real (agregarVerticalF) y se observa el _free persistido.
  {
    TL.setInteracting(false);
    TL.init(77, null);                    // proyecto limpio, modo libre (default)
    const leer = () => JSON.parse(globalThis.localStorage.getItem('jarvis.terminals.layout.77')).free;
    const eq = (a, b) => !!a && !!b && Math.abs(a.x-b.x)<1e-9 && Math.abs(a.y-b.y)<1e-9 &&
                         Math.abs(a.w-b.w)<1e-9 && Math.abs(a.h-b.h)<1e-9;
    let abajo9 = null;
    for (let i = 1; i <= 12; i++) {
      TL.add(String(i));
      await sleep(20);
      const f = leer();
      assert.ok(L.contarFilasF(f) <= 2, `add() con ${i} terminales → ≤2 filas`);
      if (i === 9) abajo9 = Object.fromEntries(Object.entries(f).filter(([, r]) => r.y >= 0.25).map(([k, r]) => [k, { ...r }]));
      if (i >= 10) {
        // las 3 de ABAJO (fijadas en n=9) NO se movieron ni un pixel al agregar arriba
        for (const k of Object.keys(abajo9)) assert.ok(eq(leer()[k], abajo9[k]), `${i}: abajo ${k} intacta`);
        assert.ok(Math.abs(f[String(i)].y - 0) < 1e-9, `${i}: la nueva se creó ARRIBA (y=0)`);
      }
    }
    const f = leer();
    assert.strictEqual(Object.keys(f).length, 12, '12 terminales presentes');
    assert.strictEqual(L.contarFilasF(f), 2, '12 → exactamente 2 filas (no 3)');
    assert.strictEqual(Object.values(f).filter(r => r.y < 0.25).length, 9, '12 → 9 arriba');
    assert.strictEqual(Object.values(f).filter(r => r.y >= 0.25).length, 3, '12 → 3 abajo');
    assert.strictEqual(Object.keys(abajo9).length, 3, 'la fila de abajo se fijó en 3');
    console.log('OK add() 1→12: nunca 3ª fila + abajo congelada (motor DOM)');
  }

  // ── remove() re-agrupa al layout canónico del modo vertical (pedido 2026-07-04) ──
  // Al eliminar, las que quedan siguen "el mecanismo": ≤6 colapsa a UNA fila; >6 se
  // mantiene en 2 filas canónicas (abajo capada en 3, top-fill). Antes borrar una de
  // arriba con 7 dejaba [5,1] (6 terminales en 2 filas) en vez de colapsar a [6].
  {
    TL.setInteracting(false);
    TL.init(88, null);
    const leer = () => JSON.parse(globalThis.localStorage.getItem('jarvis.terminals.layout.88')).free;
    for (let i = 1; i <= 7; i++) { TL.add(String(i)); await sleep(12); }
    assert.strictEqual(L.contarFilasF(leer()), 2, '7 → 2 filas (parte de [6,1])');
    // eliminar una de ARRIBA → quedan 6 → debe COLAPSAR a 1 fila (no [5,1])
    TL.remove('1'); await sleep(12);
    const f = leer();
    assert.strictEqual(Object.keys(f).length, 6, '6 terminales tras eliminar');
    assert.strictEqual(L.contarFilasF(f), 1, '≤6 → 1 sola fila (colapsa)');
    for (const k of Object.keys(f))
      assert.ok(Math.abs(f[k].y) < 1e-9 && Math.abs(f[k].w - 1 / 6) < 1e-9, 'las 6 en columnas parejas, 1 fila');
    console.log('OK remove() colapsa a 1 fila con ≤6 (motor DOM)');
  }

  // remove() con >6 mantiene 2 filas canónicas (abajo 3) hasta colapsar en 6
  {
    TL.setInteracting(false);
    TL.init(89, null);
    const leer = () => JSON.parse(globalThis.localStorage.getItem('jarvis.terminals.layout.89')).free;
    const nArr = f => Object.values(f).filter(r => r.y < 0.25).length;
    const nAba = f => Object.values(f).filter(r => r.y >= 0.25).length;
    for (let i = 1; i <= 12; i++) { TL.add(String(i)); await sleep(10); }
    let f = leer();
    assert.ok(nArr(f) === 9 && nAba(f) === 3, '12 → [9,3]');
    const esperado = [[8, 3], [7, 3], [6, 3], [6, 2], [6, 1]];   // 11,10,9,8,7
    for (let i = 0; i < esperado.length; i++) {
      TL.remove(String(i + 1)); await sleep(10); f = leer();
      const [a, b] = esperado[i];
      assert.ok(nArr(f) === a && nAba(f) === b, `${11 - i} → [${a},${b}]`);
    }
    TL.remove('6'); await sleep(10); f = leer();                 // → 6
    assert.strictEqual(L.contarFilasF(f), 1, '6 → 1 fila (colapsa)');
    console.log('OK remove() mantiene 2 filas canónicas y colapsa en 6 (motor DOM)');
  }

  console.log('OK ALL');
})();


// ══ Modo Libre v3: ventanas en fracciones (0-1) ══════════════════════════════
{
  const mW = 0.1, mH = 0.1;
  const ov = (a, b) => L._overlapF(a, b, 0.003);
  // clampF: dentro de [0,1] + mínimos
  {
    assert.deepStrictEqual(L.clampF({ x: -0.2, y: 1.5, w: 2, h: 0.05 }, mW, mH), { x: 0, y: 1 - mH, w: 1, h: mH });
  }
  // ajustarF: la activa se achica para entrar; las demás NO se tocan
  {
    const f = { a: { x: 0, y: 0, w: 0.7, h: 0.4 }, b: { x: 0.5, y: 0, w: 0.5, h: 0.4 } };
    const r = L.ajustarF(f, 'a', mW, mH);
    assert.ok(r && r.w <= 0.51, 'a se achicó para no pisar a b');
    assert.ok(!ov(r, f.b), 'sin solape tras ajustar');
    assert.deepStrictEqual(f.b, { x: 0.5, y: 0, w: 0.5, h: 0.4 }, 'b NO se movió');
    // imposible (b cubre la columna de a) → null
    const f2 = { a: { x: 0, y: 0, w: 0.5, h: 0.5 }, b: { x: 0, y: 0, w: 0.5, h: 0.5 } };
    assert.strictEqual(L.ajustarF(f2, 'a', mW, mH), null, 'si no entra → null');
  }
  // topeF: crecer topea contra la vecina (no la invade)
  {
    const f = { a: { x: 0, y: 0, w: 0.3, h: 0.4 }, b: { x: 0.5, y: 0, w: 0.5, h: 0.4 } };
    const t = L.topeF(f, 'a', 0.9, 0.4, mW, mH);
    assert.ok(t.w <= 0.505, 'a no crece más allá del borde de b');
    assert.ok(!ov({ x: 0, y: 0, w: t.w, h: t.h }, f.b), 'sin solape');
  }
  // findGapF: devuelve un rect que NO solapa a los existentes
  {
    const f = { a: { x: 0, y: 0, w: 0.5, h: 1 } };  // mitad izquierda ocupada
    const g = L.findGapF(f, 0.45, 0.45, mW, mH);
    assert.ok(!ov(g, f.a), 'el hueco no pisa a la card existente');
    assert.ok(g.x >= 0.45 || g.y >= 0, 'cae en la zona libre (derecha)');
  }
  // tileF: ids → tile sin solape, todos presentes
  {
    const f = L.tileF(['1', '2', '3', '4']);
    assert.deepStrictEqual(Object.keys(f).sort(), ['1', '2', '3', '4']);
    const ids = Object.keys(f);
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++)
      assert.ok(!ov(f[ids[i]], f[ids[j]]), 'tileF sin solape');
  }
  console.log('OK modo libre v3 (fracciones/ventana)');
}

// ══ tile2col: N columnas verticales en MÁXIMO 2 filas (10/11/12 suben, no 3ª fila) ══
{
  const ov=(a,b)=>L._overlapF(a,b,0.003);
  const ap=(a,b)=>Math.abs(a-b)<1e-9;
  // 1 → ancho completo
  assert.deepStrictEqual(L.tile2col(['1']), { '1': { x:0,y:0,w:1,h:1 } });
  // 2 → lado a lado
  const f2=L.tile2col(['1','2']);
  assert.deepStrictEqual(f2['1'], { x:0,y:0,w:0.5,h:1 });
  assert.deepStrictEqual(f2['2'], { x:0.5,y:0,w:0.5,h:1 });
  // 3 → 3 columnas en 1 fila
  const f3=L.tile2col(['1','2','3']);
  for(const id in f3){ assert.ok(ap(f3[id].w,1/3)&&ap(f3[id].h,1)&&ap(f3[id].y,0),'3 cols'); }
  assert.ok(ap(f3['3'].x,2/3));
  // 4 → 4 columnas en UNA fila (no 2×2)
  const f4=L.tile2col(['1','2','3','4']);
  for(const id in f4){ assert.ok(ap(f4[id].w,0.25)&&ap(f4[id].h,1)&&ap(f4[id].y,0),'4 en 1 fila'); }
  // 6 → 6 columnas
  const f6=L.tile2col(['1','2','3','4','5','6']);
  for(const id in f6){ assert.ok(ap(f6[id].w,1/6)&&ap(f6[id].h,1),'6 cols'); }
  // 7 → 6 arriba (w 1/6) + la 7ª ABAJO (full)
  const f7=L.tile2col(['1','2','3','4','5','6','7']);
  assert.ok(ap(f7['1'].h,0.5)&&ap(f7['1'].w,1/6)&&ap(f7['1'].y,0),'fila0 de 6');
  assert.ok(ap(f7['7'].y,0.5)&&ap(f7['7'].w,1),'la 7ª abajo, full');
  // 9 (tope del producto) → 6 arriba + 3 ABAJO (regla "máximo 3 abajo")
  const f9=L.tile2col(Array.from({length:9},(_,i)=>String(i+1)));
  assert.ok(ap(f9['1'].w,1/6)&&ap(f9['1'].y,0),'fila0 de 6');
  assert.ok(ap(f9['7'].y,0.5)&&ap(f9['7'].w,1/3),'abajo 3 parejas');
  // 10, 11, 12 → SIEMPRE 2 filas (pedido 2026-07-04 "dos filas y no tres"): la de
  // ABAJO capada en 3, el EXCEDENTE SUBE a la fila de arriba (top-fill). Jamás 3 filas.
  const nfilas=(f)=>new Set(Object.values(f).map(r=>r.y)).size;
  // 10 → arriba 7 + abajo 3
  const f10=L.tile2col(Array.from({length:10},(_,i)=>String(i+1)));
  assert.strictEqual(nfilas(f10),2,'10 → 2 filas');
  assert.ok(ap(f10['1'].w,1/7)&&ap(f10['1'].y,0),'10: arriba 7');
  assert.ok(ap(f10['8'].w,1/3)&&ap(f10['8'].y,0.5),'10: abajo 3');
  // 11 → arriba 8 + abajo 3
  const f11=L.tile2col(Array.from({length:11},(_,i)=>String(i+1)));
  assert.strictEqual(nfilas(f11),2,'11 → 2 filas');
  assert.ok(ap(f11['1'].w,1/8)&&ap(f11['1'].y,0),'11: arriba 8');
  assert.ok(ap(f11['9'].w,1/3)&&ap(f11['9'].y,0.5),'11: abajo 3');
  // 12 (tope del producto) → arriba 9 + abajo 3 (capada), 2 filas, NO 3
  const ids=Array.from({length:12},(_,i)=>String(i+1));
  const f12=L.tile2col(ids);
  assert.strictEqual(Object.keys(f12).length, 12);
  assert.strictEqual(nfilas(f12),2,'12 → 2 filas (no 3)');
  assert.ok(ap(f12['1'].w,1/9)&&ap(f12['1'].y,0),'12: arriba 9');
  assert.ok(ap(f12['10'].w,1/3)&&ap(f12['10'].y,0.5),'12: abajo 3 (capada)');
  for(const f of [f3,f4,f6,f7,f9,f10,f11,f12]){ const ks=Object.keys(f);
    for(let i=0;i<ks.length;i++)for(let j=i+1;j<ks.length;j++) assert.ok(!ov(f[ks[i]],f[ks[j]]),'sin solape'); }
  console.log('OK tile2col (N columnas verticales, máx 2 filas)');
}

// ── contarFilasF: migración de layouts persistidos viejos de 3 filas a 2 ──────
// Un `free` guardado antes del tope de 2 filas podía tener 3 bandas (10→6+1+3,
// 12→6+3+3). init() lo detecta con contarFilasF>2 y re-siembra con tile2col.
{
  assert.strictEqual(L.contarFilasF({}), 0, 'vacío → 0');
  assert.strictEqual(L.contarFilasF(L.tile2col(['1','2','3'])), 1, '3 en 1 fila → 1');
  assert.strictEqual(L.contarFilasF(L.tile2col(Array.from({length:9},(_,i)=>String(i+1)))), 2, '9 (6+3) → 2');
  assert.strictEqual(L.contarFilasF(L.tile2col(Array.from({length:12},(_,i)=>String(i+1)))), 2, '12 nuevo (9+3) → 2');
  // Layout VIEJO de 3 filas (6+3+3 en y = 0, 1/3, 2/3): contarFilasF lo delata.
  const viejo={};
  for(let i=0;i<6;i++)  viejo[String(i+1)]  ={x:i/6,y:0,   w:1/6,h:1/3};
  for(let i=0;i<3;i++)  viejo[String(i+7)]  ={x:i/3,y:1/3, w:1/3,h:1/3};
  for(let i=0;i<3;i++)  viejo[String(i+10)] ={x:i/3,y:2/3, w:1/3,h:1/3};
  assert.strictEqual(L.contarFilasF(viejo), 3, 'layout viejo 6+3+3 → 3 filas (migra)');
  console.log('OK contarFilasF (migración 3→2 filas)');
}

// ── agregarVerticalF: alta determinista — la nueva a su fila, la OTRA congelada ──
// Pedido 2026-07-04: al agregar, la nueva NO debe empujar a las de abajo hacia
// arriba; con 3 abajo, la nueva "se crea arriba" y las 3 de abajo quedan intactas.
{
  const ap=(a,b)=>Math.abs(a-b)<1e-9;
  const eq=(a,b)=>!!a&&!!b&&ap(a.x,b.x)&&ap(a.y,b.y)&&ap(a.w,b.w)&&ap(a.h,b.h);
  const nArriba=(f)=>Object.keys(f).filter(id=>f[id].y<0.25).length;
  const nAbajo =(f)=>Object.keys(f).filter(id=>f[id].y>=0.25).length;
  // Alta sobre vacío → ancho completo
  assert.deepStrictEqual(L.agregarVerticalF({},'1',6,3), {'1':{x:0,y:0,w:1,h:1}});
  // Construir 1→12 incremental (perRow=6) y chequear la forma en cada tramo.
  let f={};
  for(let n=1;n<=6;n++) f=L.agregarVerticalF(f,String(n),6,3);
  assert.strictEqual(L.contarFilasF(f),1,'6 → 1 fila');
  for(let n=1;n<=6;n++) assert.ok(ap(f[String(n)].w,1/6)&&ap(f[String(n)].y,0),'6 en 1 fila');
  // 7 → [6,1]: la nueva abajo full width; las 6 quedan arriba (media altura)
  f=L.agregarVerticalF(f,'7',6,3);
  assert.strictEqual(L.contarFilasF(f),2,'7 → 2 filas');
  assert.ok(ap(f['7'].y,0.5)&&ap(f['7'].w,1),'7ª abajo, full');
  assert.ok(ap(f['1'].y,0)&&ap(f['1'].h,0.5),'las 6 quedan arriba a media altura');
  // 8, 9 → crecen ABAJO, arriba intacta
  const arriba7={1:{...f['1']}};
  f=L.agregarVerticalF(f,'8',6,3);
  f=L.agregarVerticalF(f,'9',6,3);
  assert.ok(ap(f['7'].y,0.5)&&ap(f['7'].w,1/3),'9 → abajo 3 parejas');
  assert.ok(eq(f['1'],arriba7[1]),'9: la fila de arriba no se movió al crecer abajo');
  assert.strictEqual(nArriba(f),6,'9 → 6 arriba');
  // Snapshot de las de ABAJO (7,8,9) en [6,3]
  const ab={7:{...f['7']},8:{...f['8']},9:{...f['9']}};
  // 10 → la nueva ARRIBA; las 3 de ABAJO CONGELADAS
  f=L.agregarVerticalF(f,'10',6,3);
  assert.ok(eq(f['7'],ab[7])&&eq(f['8'],ab[8])&&eq(f['9'],ab[9]),'10: abajo 7/8/9 INTACTAS');
  assert.ok(ap(f['10'].y,0),'10: la nueva se crea ARRIBA');
  assert.strictEqual(nArriba(f),7,'10 → 7 arriba');
  // 11, 12 → siguen entrando ARRIBA, abajo sigue intacta
  f=L.agregarVerticalF(f,'11',6,3);
  f=L.agregarVerticalF(f,'12',6,3);
  assert.ok(ap(f['11'].y,0)&&ap(f['12'].y,0),'11 y 12 también se crean arriba');
  assert.ok(eq(f['7'],ab[7])&&eq(f['8'],ab[8])&&eq(f['9'],ab[9]),'12: abajo 7/8/9 SIGUEN intactas');
  assert.strictEqual(L.contarFilasF(f),2,'12 → 2 filas');
  assert.strictEqual(nArriba(f),9,'12 → 9 arriba');
  assert.strictEqual(nAbajo(f),3,'12 → 3 abajo');
  // Sin solapes en el layout final
  const ks=Object.keys(f), ov=(a,b)=>L._overlapF(a,b,0.003);
  for(let i=0;i<ks.length;i++)for(let j=i+1;j<ks.length;j++) assert.ok(!ov(f[ks[i]],f[ks[j]]),'12: sin solape');
  console.log('OK agregarVerticalF (nueva arriba, abajo congelada)');
}

// ── Alta/baja por BANDA (agregarEnBandaF / quitarDeBandaF) ───────────────────
// Alta (pedido 2026-07-03): la terminal nueva entra a la banda de la card más
// ancha y la banda ENTERA se reparte en partes IGUALES (antes se partía la más
// ancha a la mitad y quedaba "una más grande que las otras dos"). Las otras
// bandas no se tocan.
// Baja (pedido 2026-07-03, espejo del alta): al cerrar una terminal, su banda
// ENTERA se re-reparte en partes IGUALES (antes UNA vecina absorbía todo el
// espacio y quedaba el doble de ancha que las demás). Las otras bandas no se
// tocan; si era la única de su banda → null (expandirF reclama el hueco).
{
  const P = L;
  // Vacío: la primera terminal ocupa todo.
  let r = P.agregarEnBandaF({}, 'n', 0.1);
  assert.deepStrictEqual(r.free['n'], { x: 0, y: 0, w: 1, h: 1 });
  assert.deepStrictEqual(r.banda, []);

  // Banda única de 3 columnas desparejas + nueva → 4 IGUALES, orden preservado,
  // la nueva al final.
  const base = {
    a: { x: 0,    y: 0, w: 0.5,  h: 1 },
    b: { x: 0.5,  y: 0, w: 0.25, h: 1 },
    c: { x: 0.75, y: 0, w: 0.25, h: 1 },
  };
  r = P.agregarEnBandaF(base, 'n', 0.1);
  assert.deepStrictEqual(r.banda, ['a', 'b', 'c']);
  for (const [id, x] of [['a', 0], ['b', 0.25], ['c', 0.5], ['n', 0.75]]) {
    assert.ok(Math.abs(r.free[id].x - x) < 1e-9, `${id} en x=${x}`);
    assert.ok(Math.abs(r.free[id].w - 0.25) < 1e-9, `${id} pareja`);
  }
  assert.deepStrictEqual(base.a, { x: 0, y: 0, w: 0.5, h: 1 }); // sin mutar la entrada

  // 6 arriba + 1 abajo (full): la banda de abajo es la más ancha → pasa a 2×0.5
  // IGUALES; las 6 de arriba byte-idénticas.
  const dos = {};
  for (let i = 0; i < 6; i++) dos[String(i + 1)] = { x: i / 6, y: 0, w: 1 / 6, h: 0.5 };
  dos['b0'] = { x: 0, y: 0.5, w: 1, h: 0.5 };
  r = P.agregarEnBandaF(dos, 'n', 0.1);
  assert.deepStrictEqual(r.banda, ['b0']);
  assert.deepStrictEqual(r.free['b0'], { x: 0, y: 0.5, w: 0.5, h: 0.5 });
  assert.deepStrictEqual(r.free['n'], { x: 0.5, y: 0.5, w: 0.5, h: 0.5 });
  assert.deepStrictEqual(r.free['3'], dos['3']);   // arriba intacto

  // El caso del usuario: abajo con 2 → la 3ª entra y quedan 3×⅓ EXACTAS.
  const abajoDos = {};
  for (let i = 0; i < 6; i++) abajoDos[String(i + 1)] = { x: i / 6, y: 0, w: 1 / 6, h: 0.5 };
  abajoDos['b0'] = { x: 0, y: 0.5, w: 0.5, h: 0.5 };
  abajoDos['b1'] = { x: 0.5, y: 0.5, w: 0.5, h: 0.5 };
  r = P.agregarEnBandaF(abajoDos, 'n', 0.1);
  assert.deepStrictEqual(r.banda, ['b0', 'b1']);
  for (const [id, i] of [['b0', 0], ['b1', 1], ['n', 2]]) {
    assert.ok(Math.abs(r.free[id].x - i / 3) < 1e-9 && Math.abs(r.free[id].w - 1 / 3) < 1e-9,
              `${id} = tercio ${i}`);
  }

  // No entra ni repartiendo (minW) → null (el caller re-tilea).
  assert.strictEqual(P.agregarEnBandaF({ a: { x: 0, y: 0, w: 0.2, h: 1 } }, 'n', 0.15), null);

  // Quitar: la banda ENTERA se re-reparte en partes IGUALES (el caso del
  // usuario: cerrar una de 3 desparejas → las 2 que quedan a 0.5 cada una).
  const tres = {
    a: { x: 0,    y: 0, w: 0.25, h: 1 },
    m: { x: 0.25, y: 0, w: 0.25, h: 1 },
    z: { x: 0.5,  y: 0, w: 0.5,  h: 1 },
  };
  let q = P.quitarDeBandaF(tres, 'm');
  assert.deepStrictEqual(q.banda, ['a', 'z']);
  assert.deepStrictEqual(q.free['a'], { x: 0, y: 0, w: 0.5, h: 1 });
  assert.deepStrictEqual(q.free['z'], { x: 0.5, y: 0, w: 0.5, h: 1 });
  assert.strictEqual(q.free['m'], undefined);
  assert.deepStrictEqual(tres.z, { x: 0.5, y: 0, w: 0.5, h: 1 }); // sin mutar la entrada

  // Dos bandas — quitar ABAJO: la banda de abajo queda pareja, arriba intacto.
  const dosBandas = {};
  for (let i = 0; i < 6; i++) dosBandas[String(i + 1)] = { x: i / 6, y: 0, w: 1 / 6, h: 0.5 };
  dosBandas['b0'] = { x: 0,       y: 0.5, w: 1 / 3, h: 0.5 };
  dosBandas['b1'] = { x: 1 / 3,   y: 0.5, w: 1 / 3, h: 0.5 };
  dosBandas['b2'] = { x: 2 / 3,   y: 0.5, w: 1 / 3, h: 0.5 };
  q = P.quitarDeBandaF(dosBandas, 'b1');
  assert.deepStrictEqual(q.banda, ['b0', 'b2']);
  assert.ok(Math.abs(q.free['b0'].x - 0) < 1e-9 && Math.abs(q.free['b0'].w - 0.5) < 1e-9, 'b0 mitad');
  assert.ok(Math.abs(q.free['b2'].x - 0.5) < 1e-9 && Math.abs(q.free['b2'].w - 0.5) < 1e-9, 'b2 mitad');
  assert.deepStrictEqual(q.free['3'], dosBandas['3']);     // arriba byte-idéntico

  // Dos bandas — quitar ARRIBA: la banda de arriba queda pareja, abajo intacto.
  q = P.quitarDeBandaF(dosBandas, '2');
  assert.deepStrictEqual(q.banda, ['1', '3', '4', '5', '6']);
  for (const [id, i] of [['1', 0], ['3', 1], ['4', 2], ['5', 3], ['6', 4]]) {
    assert.ok(Math.abs(q.free[id].x - i / 5) < 1e-9 && Math.abs(q.free[id].w - 1 / 5) < 1e-9,
              `${id} = quinto ${i}`);
  }
  assert.deepStrictEqual(q.free['b1'], dosBandas['b1']);   // abajo byte-idéntico

  // Única de su banda (otra fila entera): no hay con quién repartir → null
  // (el caller deja que expandirF reclame el hueco).
  q = P.quitarDeBandaF({
    a: { x: 0, y: 0,   w: 1, h: 0.5 },
    b: { x: 0, y: 0.5, w: 1, h: 0.5 },
  }, 'a');
  assert.strictEqual(q, null);

  // Única card → null. Id inexistente → null.
  assert.strictEqual(P.quitarDeBandaF({ solo: { x: 0, y: 0, w: 1, h: 1 } }, 'solo'), null);
  assert.strictEqual(P.quitarDeBandaF({ solo: { x: 0, y: 0, w: 1, h: 1 } }, 'nadie'), null);

  console.log('OK agregarEnBandaF/quitarDeBandaF (alta/baja por banda)');
}

// ── Alturas MIXTAS en la misma fila (bug 2026-07-02): la banda excluye a la
// card de altura distinta, pero el rango min→max la CONTIENE → el re-reparto
// la pisaba (solape que ni expandirF ni sanearFreeF corrigen, y se persistía).
// Regla: si el reparto solaparía una ajena → null (el caller cae al flujo
// hueco + expandirF / tile2col, que jamás solapan). ─────────────────────────
{
  const P = L;
  const mixta = {
    a: { x: 0,     y: 0, w: 1 / 3, h: 0.5 },
    b: { x: 1 / 3, y: 0, w: 1 / 3, h: 0.6 },   // más alta: queda fuera de la banda
    c: { x: 2 / 3, y: 0, w: 1 / 3, h: 0.5 },
  };
  // Quitar 'a': banda=[c] pero el rango 0..1 contiene a 'b' → pisaría → null.
  assert.strictEqual(P.quitarDeBandaF(mixta, 'a'), null);
  assert.deepStrictEqual(mixta.b, { x: 1 / 3, y: 0, w: 1 / 3, h: 0.6 }); // sin mutar

  // Espejo del alta: banda=[a,c], el reparto en tercios pisa a 'b' → null
  // (el caller re-tilea con tile2col, que no solapa).
  assert.strictEqual(P.agregarEnBandaF(mixta, 'n', 0.1), null);

  // No-regresión: ajena de altura distinta FUERA del rango de la banda →
  // el reparto sigue funcionando normal.
  const lateral = {
    a: { x: 0,   y: 0, w: 0.3, h: 0.5 },
    m: { x: 0.3, y: 0, w: 0.3, h: 0.5 },
    z: { x: 0.6, y: 0, w: 0.4, h: 0.9 },       // distinta altura, a la derecha
  };
  const q = P.quitarDeBandaF(lateral, 'm');
  assert.deepStrictEqual(q.banda, ['a']);
  assert.ok(Math.abs(q.free['a'].x - 0) < 1e-9 && Math.abs(q.free['a'].w - 0.6) < 1e-9, 'a absorbe hasta z');
  assert.deepStrictEqual(q.free['z'], lateral.z); // ajena intacta

  console.log('OK bandas con alturas mixtas (guard anti-solape)');
}

// ══ sanearFreeF: el layout persistido se VALIDA al cargar (nada crudo al DOM) ═
{
  const P = L;
  // Rects válidos pasan clampeados (idénticos si ya están en rango).
  const ok = { a: { x: 0, y: 0, w: 0.5, h: 1 }, b: { x: 0.5, y: 0, w: 0.5, h: 1 } };
  assert.deepStrictEqual(P.sanearFreeF(ok, 0.02, 0.02), ok);

  // Basura: no-objeto, campos faltantes, NaN/Infinity, w/h <= 0 → se DESCARTAN.
  const sucio = {
    a: { x: 0, y: 0, w: 0.5, h: 1 },
    b: null,
    c: 'hola',
    d: { x: 0, y: 0 },                            // sin w/h
    e: { x: NaN, y: 0, w: 0.5, h: 1 },
    f: { x: 0, y: 0, w: Infinity, h: 1 },
    g: { x: 0, y: 0, w: 0, h: 1 },                // degenerada
    h: { x: 0, y: 0, w: -0.3, h: 0.5 },           // negativa
  };
  assert.deepStrictEqual(Object.keys(P.sanearFreeF(sucio, 0.02, 0.02)), ['a']);

  // Fuera de rango: se clampa adentro del contenedor (mismo contrato que clampF).
  const fuera = P.sanearFreeF({ a: { x: 0.9, y: -2, w: 0.5, h: 3 } }, 0.02, 0.02);
  assert.deepStrictEqual(fuera.a, P.clampF({ x: 0.9, y: -2, w: 0.5, h: 3 }, 0.02, 0.02));
  assert.ok(fuera.a.x + fuera.a.w <= 1.0001 && fuera.a.y >= 0);

  // Entrada no-objeto → {} (jamás revienta).
  assert.deepStrictEqual(P.sanearFreeF(null, 0.02, 0.02), {});
  assert.deepStrictEqual(P.sanearFreeF('x', 0.02, 0.02), {});

  console.log('OK sanearFreeF (layout persistido validado)');
}

// ══ tile2col con perRowMax: columnas parejas con ANCHO MÍNIMO real ═══════════
{
  // Sin perRowMax: comportamiento histórico (hasta 6 por fila) — no cambia.
  const f6 = L.tile2col(['1','2','3','4','5','6']);
  assert.ok(Math.abs(f6['6'].x - 5/6) < 1e-9 && f6['6'].y === 0);

  // perRowMax=4: 8 ids → abajo se capa en 3 y el excedente sube (5 arriba + 3 abajo;
  // la regla "máximo 3 abajo" le gana al techo de columnas por fila).
  const f8 = L.tile2col(['1','2','3','4','5','6','7','8'], 4);
  assert.deepStrictEqual(f8['1'], { x: 0, y: 0, w: 0.2, h: 0.5 });
  assert.deepStrictEqual(f8['5'], { x: 0.8, y: 0, w: 0.2, h: 0.5 });
  assert.deepStrictEqual(f8['6'], { x: 0, y: 0.5, w: 1 / 3, h: 0.5 });
  assert.deepStrictEqual(f8['8'], { x: 2 / 3, y: 0.5, w: 1 / 3, h: 0.5 });

  // perRowMax=2: 3 ids → fila de 2 + fila de 1 (la última estira a ancho completo).
  const f3 = L.tile2col(['a','b','c'], 2);
  assert.deepStrictEqual(f3['a'], { x: 0, y: 0, w: 0.5, h: 0.5 });
  assert.deepStrictEqual(f3['c'], { x: 0, y: 0.5, w: 1, h: 0.5 });

  // perRowMax degenerado (0 / negativo / >6) se clampa a [1, 6].
  const f2 = L.tile2col(['a','b'], 0);
  assert.deepStrictEqual(f2['a'], { x: 0, y: 0, w: 1, h: 0.5 });   // 1 por fila
  const f7 = L.tile2col(['1','2','3','4','5','6','7'], 99);
  assert.ok(Math.abs(f7['6'].x - 5/6) < 1e-9);                      // sigue capado a 6

  console.log('OK tile2col con perRowMax (ancho mínimo de columna)');
}

// ══ expandirF: las cards ESTIRAN hacia el espacio libre (pedido 2026-07-02:
// en modo vertical las columnas ocupan SIEMPRE toda la altura; al cerrar o
// cargar no quedan bandas muertas). Solo crece/corre hacia el hueco — jamás
// achica a nadie. ═══════════════════════════════════════════════════════════
{
  const P = L;
  const ov = (a, b) => P._overlapF(a, b, 0.003);
  const ap = (a, b) => Math.abs(a - b) < 1e-9;

  // Caso del usuario: 6 columnas a media altura + banda inferior muerta
  // (herencia de un layout de 2 filas) → TODAS estiran a alto completo.
  const seis = {};
  for (let i = 0; i < 6; i++) seis[String(i + 1)] = { x: i / 6, y: 0, w: 1 / 6, h: 0.5 };
  const e6 = P.expandirF(seis);
  for (const id in e6) {
    assert.ok(ap(e6[id].y, 0) && ap(e6[id].h, 1), `columna ${id} a alto completo`);
    assert.ok(ap(e6[id].x, seis[id].x) && ap(e6[id].w, seis[id].w), `columna ${id} conserva su ancho`);
  }
  assert.deepStrictEqual(seis['1'], { x: 0, y: 0, w: 1 / 6, h: 0.5 }, 'entrada sin mutar');

  // Layout que YA llena todo → idéntico (no molesta a nadie).
  const lleno = { a: { x: 0, y: 0, w: 0.5, h: 1 }, b: { x: 0.5, y: 0, w: 0.5, h: 0.5 }, c: { x: 0.5, y: 0.5, w: 0.5, h: 0.5 } };
  assert.deepStrictEqual(P.expandirF(lleno), lleno);

  // Stack con huecos arriba/entre/abajo → la columna se llena sin solapar,
  // preservando el orden vertical.
  const stack = { a: { x: 0, y: 0.1, w: 1, h: 0.2 }, b: { x: 0, y: 0.6, w: 1, h: 0.2 } };
  const es = P.expandirF(stack);
  assert.ok(ap(es.a.y, 0), 'a sube al tope');
  assert.ok(ap(es.b.y, es.a.y + es.a.h), 'b pegada debajo de a');
  assert.ok(ap(es.b.y + es.b.h, 1), 'b llega al fondo');
  assert.ok(!ov(es.a, es.b), 'sin solape');

  // Se cerró la columna izquierda (banda incompatible, absorber devolvía null):
  // las de la derecha reclaman también el ANCHO libre.
  const der = { b: { x: 0.5, y: 0, w: 0.5, h: 0.5 }, c: { x: 0.5, y: 0.5, w: 0.5, h: 0.5 } };
  const ed = P.expandirF(der);
  assert.ok(ap(ed.b.x, 0) && ap(ed.b.w, 1), 'b toma todo el ancho');
  assert.ok(ap(ed.c.x, 0) && ap(ed.c.w, 1), 'c toma todo el ancho');
  assert.ok(!ov(ed.b, ed.c), 'sin solape');

  // Hueco al MEDIO de una banda: se reparte sin solapar ni dejar espacio.
  const medio = { a: { x: 0, y: 0, w: 0.3, h: 1 }, b: { x: 0.6, y: 0, w: 0.4, h: 1 } };
  const em = P.expandirF(medio);
  assert.ok(ap(em.a.x, 0), 'a queda en el borde');
  assert.ok(ap(em.b.x, em.a.x + em.a.w), 'b pegada a a');
  assert.ok(ap(em.a.w + em.b.w, 1), 'entre las dos cubren el ancho');
  assert.ok(!ov(em.a, em.b), 'sin solape');

  // Una sola card chica → pantalla completa. Vacío → {}. Nunca revienta.
  assert.deepStrictEqual(P.expandirF({ solo: { x: 0.3, y: 0.3, w: 0.3, h: 0.3 } }), { solo: { x: 0, y: 0, w: 1, h: 1 } });
  assert.deepStrictEqual(P.expandirF({}), {});
  assert.deepStrictEqual(P.expandirF(null), {});

  console.log('OK expandirF (estirar al espacio libre)');
}

// ══ Paredes ACOPLADAS (pedido 2026-07-02): el resize libre se elimina — agrandar
// una terminal = arrastrar la PARED compartida: una crece y la vecina se achica
// exactamente lo mismo; el patrón nunca se rompe, no quedan huecos. ═════════════
{
  const P = L;
  const ap = (a, b) => Math.abs(a - b) < 1e-9;

  // 3 columnas → 2 paredes verticales de alto completo.
  const cols = { a: { x: 0, y: 0, w: 1 / 3, h: 1 }, b: { x: 1 / 3, y: 0, w: 1 / 3, h: 1 }, c: { x: 2 / 3, y: 0, w: 1 / 3, h: 1 } };
  const vs = P.deriveWallsF(cols).filter(w => w.type === 'v');
  assert.strictEqual(vs.length, 2, '3 columnas → 2 paredes');
  const w1 = vs.find(w => Math.abs(w.pos - 1 / 3) < 1e-3);
  assert.deepStrictEqual([w1.antes, w1.despues], [['a'], ['b']], 'pared a|b');
  assert.ok(ap(w1.d0, 0) && ap(w1.d1, 1), 'pared de alto completo');

  // Mover +0.1: a crece, b se corre y achica LO MISMO; c byte-idéntica.
  const m = P.moverParedF(cols, w1, 0.1, 0.05, 0.05);
  assert.ok(ap(m.a.w, 1 / 3 + 0.1), 'a creció');
  assert.ok(ap(m.b.x, 1 / 3 + 0.1) && ap(m.b.w, 1 / 3 - 0.1), 'b cedió exactamente lo mismo');
  assert.deepStrictEqual(m.c, cols.c, 'c intacta');
  assert.deepStrictEqual(cols.a, { x: 0, y: 0, w: 1 / 3, h: 1 }, 'entrada sin mutar');

  // Clamp: la vecina nunca baja del mínimo; delta 0 o imposible → mismo objeto.
  const mc = P.moverParedF(cols, w1, 0.9, 0.1, 0.1);
  assert.ok(mc.b.w >= 0.1 - 1e-9, 'b topa en el mínimo');
  assert.ok(ap(mc.a.w + mc.b.w, 2 / 3), 'la suma se conserva');
  assert.strictEqual(P.moverParedF(cols, w1, 0, 0.1, 0.1), cols, 'delta 0 → no-op');

  // 6 columnas arriba + 1 full-width abajo: UNA pared horizontal (las 6 de un
  // lado, la 7ª del otro) — moverla ajusta la banda ENTERA sin romper el patrón.
  const seis = {};
  for (let i = 0; i < 6; i++) seis[String(i + 1)] = { x: i / 6, y: 0, w: 1 / 6, h: 0.5 };
  seis['7'] = { x: 0, y: 0.5, w: 1, h: 0.5 };
  const ws = P.deriveWallsF(seis);
  const hs = ws.filter(w => w.type === 'h');
  assert.strictEqual(hs.length, 1, 'una sola pared horizontal');
  assert.strictEqual(hs[0].antes.length, 6, 'las 6 de arriba');
  assert.deepStrictEqual(hs[0].despues, ['7'], 'la 7ª abajo');
  assert.ok(ap(hs[0].d0, 0) && ap(hs[0].d1, 1), 'cruza todo el ancho');
  // las paredes verticales de arriba solo llegan hasta la banda (0.5)
  const vt = ws.filter(w => w.type === 'v');
  assert.strictEqual(vt.length, 5, '5 paredes entre las 6 columnas');
  for (const w of vt) assert.ok(w.d1 <= 0.5 + 1e-3, 'pared vertical corta en la banda');
  const mh = P.moverParedF(seis, hs[0], 0.2, 0.05, 0.05);
  assert.ok(ap(mh['3'].h, 0.7), 'las de arriba crecen');
  assert.ok(ap(mh['7'].y, 0.7) && ap(mh['7'].h, 0.3), 'la de abajo cede');

  // T-junction: A (alto completo) | B arriba + C abajo → UNA pared fusionada;
  // moverla mantiene el tiling (B y C se mueven juntas, sin solape ni hueco).
  const t = { A: { x: 0, y: 0, w: 0.5, h: 1 }, B: { x: 0.5, y: 0, w: 0.5, h: 0.5 }, C: { x: 0.5, y: 0.5, w: 0.5, h: 0.5 } };
  const wt = P.deriveWallsF(t).filter(w => w.type === 'v');
  assert.strictEqual(wt.length, 1, 'pared fusionada (no una por par)');
  assert.deepStrictEqual([wt[0].antes, wt[0].despues.slice().sort()], [['A'], ['B', 'C']]);
  const mt = P.moverParedF(t, wt[0], -0.1, 0.05, 0.05);
  assert.ok(ap(mt.A.w, 0.4), 'A cedió');
  assert.ok(ap(mt.B.x, 0.4) && ap(mt.C.x, 0.4) && ap(mt.B.w, 0.6) && ap(mt.C.w, 0.6), 'B y C juntas');
  assert.ok(!P._overlapF(mt.A, mt.B, 0.003) && !P._overlapF(mt.A, mt.C, 0.003), 'sin solape');

  // Paredes en la MISMA línea que solo se TOCAN en la juntura de bandas (sin
  // card compartida) NO se fusionan (pedido 2026-07-03: agrandar una terminal
  // de abajo no tiene que mover las de arriba). 6 arriba + 3 abajo: los bordes
  // de abajo (⅓, ⅔) coinciden con bordes de arriba (2/6, 4/6) → separadas.
  const bandas = {};
  for (let i = 0; i < 6; i++) bandas[String(i + 1)] = { x: i / 6, y: 0, w: 1 / 6, h: 0.5 };
  for (let i = 0; i < 3; i++) bandas['b' + i] = { x: i / 3, y: 0.5, w: 1 / 3, h: 0.5 };
  const wb = P.deriveWallsF(bandas).filter(w => w.type === 'v');
  assert.strictEqual(wb.length, 7, '5 paredes arriba + 2 abajo (nada fusionado)');
  const en13 = wb.filter(w => Math.abs(w.pos - 1 / 3) < 1e-3);
  assert.strictEqual(en13.length, 2, 'en x=1/3 hay DOS paredes (arriba y abajo)');
  const abajo13 = en13.find(w => w.d0 > 0.4);
  assert.deepStrictEqual([abajo13.antes, abajo13.despues], [['b0'], ['b1']], 'la de abajo es solo b0|b1');
  const mm = P.moverParedF(bandas, abajo13, 0.1, 0.05, 0.05);
  assert.deepStrictEqual(mm['3'], bandas['3'], 'arriba NO se toca');
  assert.ok(ap(mm.b0.w, 1 / 3 + 0.1) && ap(mm.b1.x, 1 / 3 + 0.1), 'abajo sí se acopla');

  // Vacío / una sola card → sin paredes.
  assert.deepStrictEqual(P.deriveWallsF({}), []);
  assert.deepStrictEqual(P.deriveWallsF({ solo: { x: 0, y: 0, w: 1, h: 1 } }), []);

  console.log('OK deriveWallsF/moverParedF (paredes acopladas)');
}

// ══ Máximo 3 ABAJO (pedido 2026-07-03): la banda de más abajo admite hasta 3
// terminales; con el tope lleno, la nueva se agrega ARRIBA. ══════════════════
{
  const P = L;
  // 6 arriba (h 0.5) + 3 abajo: abajo está LLENO → aunque las de abajo sean las
  // más anchas, la nueva entra ARRIBA (y arriba queda 7 IGUALES).
  const lleno = {};
  for (let i = 0; i < 6; i++) lleno[String(i + 1)] = { x: i / 6, y: 0, w: 1 / 6, h: 0.5 };
  for (let i = 0; i < 3; i++) lleno['b' + i] = { x: i / 3, y: 0.5, w: 1 / 3, h: 0.5 };
  let r = P.agregarEnBandaF(lleno, 'n', 0.05, 3);
  assert.deepStrictEqual(r.banda, ['1', '2', '3', '4', '5', '6'], 'con abajo lleno la banda es la de ARRIBA');
  assert.ok(Math.abs(r.free['n'].y - 0) < 1e-9, 'la nueva quedó arriba');
  assert.ok(Math.abs(r.free['n'].w - 1 / 7) < 1e-9 && Math.abs(r.free['1'].w - 1 / 7) < 1e-9, 'arriba 7 iguales');
  assert.deepStrictEqual(r.free['b0'], lleno['b0'], 'abajo intacto');

  // Abajo con 2 (hay lugar): la nueva entra abajo (la banda de la más ancha).
  const conLugar = {};
  for (let i = 0; i < 6; i++) conLugar[String(i + 1)] = { x: i / 6, y: 0, w: 1 / 6, h: 0.5 };
  conLugar['b0'] = { x: 0, y: 0.5, w: 0.5, h: 0.5 };
  conLugar['b1'] = { x: 0.5, y: 0.5, w: 0.5, h: 0.5 };
  r = P.agregarEnBandaF(conLugar, 'n', 0.05, 3);
  assert.deepStrictEqual(r.banda, ['b0', 'b1'], 'con lugar abajo, entra abajo');
  assert.ok(Math.abs(r.free['n'].y - 0.5) < 1e-9, 'la nueva quedó abajo');

  // Una sola banda (todas y=0): sin restricción — no existe "abajo".
  const banda = { a: { x: 0, y: 0, w: 0.5, h: 1 }, b: { x: 0.5, y: 0, w: 0.5, h: 1 } };
  r = P.agregarEnBandaF(banda, 'n', 0.05, 3);
  assert.deepStrictEqual(r.banda, ['a', 'b'], 'una banda: comportamiento normal');

  // Abajo lleno y arriba SIN lugar (mínimo no da) → null (el caller re-tilea).
  const apretado = {
    a: { x: 0, y: 0, w: 0.3, h: 0.5 }, b: { x: 0.3, y: 0, w: 0.7, h: 0.5 },
    c: { x: 0, y: 0.5, w: 0.3, h: 0.5 }, d: { x: 0.3, y: 0.5, w: 0.3, h: 0.5 }, e: { x: 0.6, y: 0.5, w: 0.4, h: 0.5 },
  };
  assert.strictEqual(P.agregarEnBandaF(apretado, 'n', 0.4, 3), null, 'arriba no da el mínimo → null');

  // Sin el parámetro: sin tope — entra a la banda de la más ancha global (abajo).
  r = P.agregarEnBandaF(lleno, 'n', 0.05);
  assert.deepStrictEqual(r.banda, ['b0', 'b1', 'b2'], 'sin tope: banda de la más ancha global');

  console.log('OK agregarEnBandaF con máximo 3 abajo');
}

// ══ bordesF: qué borde/esquina de qué card controla qué pared (las agarraderas
// viven EN la terminal — las barritas del gutter se fueron, pedido 2026-07-03) ═
{
  const P = L;
  // 3 columnas: 2 paredes verticales → a{der}, b{izq,der}, c{izq}; sin esquinas.
  const cols = { a: { x: 0, y: 0, w: 1 / 3, h: 1 }, b: { x: 1 / 3, y: 0, w: 1 / 3, h: 1 }, c: { x: 2 / 3, y: 0, w: 1 / 3, h: 1 } };
  const wc = P.deriveWallsF(cols);
  const bc = P.bordesF(wc);
  const lados = id => bc.bordes.filter(b => b.id === id).map(b => b.lado).sort();
  assert.deepStrictEqual(lados('a'), ['der']);
  assert.deepStrictEqual(lados('b'), ['der', 'izq']);
  assert.deepStrictEqual(lados('c'), ['izq']);
  assert.deepStrictEqual(bc.esquinas, [], 'sin paredes h no hay esquinas');

  // 2 arriba + 1 abajo full: los de arriba tienen 'aba' (la pared h) y el de
  // abajo 'arr'; esquinas sw/se en las cards de arriba que tienen ambas paredes.
  const dos = {
    a: { x: 0, y: 0, w: 0.5, h: 0.5 }, b: { x: 0.5, y: 0, w: 0.5, h: 0.5 },
    c: { x: 0, y: 0.5, w: 1, h: 0.5 },
  };
  const wd = P.deriveWallsF(dos);
  const bd = P.bordesF(wd);
  const lados2 = id => bd.bordes.filter(b => b.id === id).map(b => b.lado).sort();
  assert.deepStrictEqual(lados2('a'), ['aba', 'der']);
  assert.deepStrictEqual(lados2('b'), ['aba', 'izq']);
  assert.deepStrictEqual(lados2('c'), ['arr']);
  const esq = bd.esquinas.map(q => q.id + ':' + q.esquina).sort();
  assert.deepStrictEqual(esq, ['a:se', 'b:sw'], 'esquinas inferiores donde confluyen ambas paredes');
  for (const q of bd.esquinas) {
    assert.strictEqual(wd[q.wallV].type, 'v', 'wallV es vertical');
    assert.strictEqual(wd[q.wallH].type, 'h', 'wallH es horizontal');
  }

  // Vacío → sin nada.
  assert.deepStrictEqual(P.bordesF([]), { bordes: [], esquinas: [] });

  console.log('OK bordesF (agarraderas en la card)');
}

// ══ podarFreeF: limpiar posiciones de terminales muertas SIN tocar las que
// están esperando su add() (carga de proyecto) — el bug de "cambio de posición,
// navego a otro proyecto, vuelvo y se perdió" salía de podar de más. ═════════
{
  const P = L;
  const free = {
    viva:      { x: 0,   y: 0, w: 0.4, h: 1 },
    esperando: { x: 0.4, y: 0, w: 0.3, h: 1 },
    muerta:    { x: 0.7, y: 0, w: 0.3, h: 1 },
  };
  // vivas = en el layout; protegidas = guardadas esperando su add().
  const out = P.podarFreeF(free, ['viva'], new Set(['esperando']));
  assert.deepStrictEqual(Object.keys(out).sort(), ['esperando', 'viva'], 'muerta podada, esperando protegida');
  assert.deepStrictEqual(out.viva, free.viva);
  // Sin protegidas: poda todo lo que no esté vivo.
  assert.deepStrictEqual(Object.keys(P.podarFreeF(free, ['viva'], null)), ['viva']);
  // Ids numéricos vs string: se normaliza.
  assert.deepStrictEqual(Object.keys(P.podarFreeF({ 7: { x: 0, y: 0, w: 1, h: 1 } }, [7], null)), ['7']);
  // Entradas vacías: jamás revienta.
  assert.deepStrictEqual(P.podarFreeF(null, [], null), {});
  console.log('OK podarFreeF (poda protegida)');
}
