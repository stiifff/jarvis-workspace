'use strict';
// Tests del cálculo de dimensiones REAL del fit (corrige el bug de FitAddon que
// clipeaba la fila de abajo de cada terminal). Causa: `.terminal-body` es
// box-sizing:border-box, así que getComputedStyle(...).height devuelve la altura
// CON el padding (39px píldora + 4px) incluido; FitAddon usa esa altura del padre
// pero resta el padding del elemento `.xterm` (que es 0) → cuenta 1 fila de más,
// que sobresale del área visible y la clipea overflow:hidden. dimsReales RESTA
// el padding REAL del contenedor antes de dividir por la celda. Ver
// [[tmux-size-clamping]] (clipping del fondo, distinto al garble).
const assert = require('node:assert');
const Fit = require('../terminal-fit.js');

// Caso REAL medido en browser (el bug): body 850px border-box, padding 39+4=43,
// 8px horizontal, celda 7×23. El área visible son 807px → entran 35 filas.
// FitAddon calculaba floor(850/23)=36 (1 de más, clipeada). dimsReales = 35.
const caso = Fit.dimsReales(369, 850, 8, 43, 7, 23);
assert.strictEqual(caso.rows, 35, 'debe restar el padding vertical: floor((850-43)/23)=35, NO 36');
assert.strictEqual(caso.cols, 51, 'debe restar el padding horizontal: floor((369-8)/7)=51');

// Sin padding la cuenta es la división directa.
assert.deepStrictEqual(Fit.dimsReales(700, 460, 0, 0, 7, 23), { cols: 100, rows: 20 });

// Piso COMUNICABLE (2026-07-02): xterm jamás debe quedar en un tamaño que el
// gate de envío (cols<20 || rows<5 en onResize/refitTerminal) no puede
// comunicarle a tmux — si xterm se achica por debajo, tmux no se entera y la
// terminal queda "cortada a media card" (divergencia silenciosa, hallazgo de
// la auditoría 2026-07-02: el mínimo de celda del mosaico 160×90 quedaba por
// debajo del piso de envío). El contenido puede desbordar una card minúscula
// (overflow:hidden la recorta); eso es preferible a desincronizar tmux.
const colapsado = Fit.dimsReales(5, 40, 8, 50, 7, 23);
assert.strictEqual(colapsado.cols, 20, 'cols nunca baja de 20 (piso comunicable)');
assert.strictEqual(colapsado.rows, 5,  'rows nunca baja de 5 (piso comunicable)');

// Celda inválida (renderer no midió) → mínimos, sin NaN ni Infinity.
const sinCelda = Fit.dimsReales(700, 460, 0, 0, 0, 0);
assert.strictEqual(sinCelda.cols, 20);
assert.strictEqual(sinCelda.rows, 5);
assert.ok(Number.isFinite(sinCelda.cols) && Number.isFinite(sinCelda.rows));

// Celda mínima del mosaico (160×90, MIN_W/MIN_H de terminal-layout): con celda
// 7.8×18.2 y padding real daría 19×2 → debe clamped a 20×5 (comunicable).
const celdaMosaico = Fit.dimsReales(160, 90, 8, 43, 7.8, 18.2);
assert.ok(celdaMosaico.cols >= 20 && celdaMosaico.rows >= 5,
  `la celda mínima del mosaico queda comunicable (dio ${celdaMosaico.cols}×${celdaMosaico.rows})`);

// Redondeo: siempre floor (una fila parcial NO cuenta — si contara, se clipea).
assert.strictEqual(Fit.dimsReales(0, 806, 0, 0, 7, 23).rows, 35); // 806/23 = 35.04 → 35
assert.strictEqual(Fit.dimsReales(0, 805, 0, 0, 7, 23).rows, 35); // 805/23 = 35.00 → 35
assert.strictEqual(Fit.dimsReales(0, 804, 0, 0, 7, 23).rows, 34); // 804/23 = 34.9  → 34

// Escala de la app (zoom en <html>): al escalar, xterm RE-MIDE su celda y el alto
// puede saltar (23 → 25px CSS a 125%). Las filas hay que recalcularlas con la
// celda NUEVA — con la vieja entran 29 donde solo caben 26, y esas 3 filas de más
// se las come el overflow:hidden de la card justo abajo, tapando el composer del
// agente. Por eso _fitReal (terminal.js) refitea mientras la celda le cambie.
const AVAIL_125 = 667;                 // alto útil de la card a 125% (px CSS)
assert.strictEqual(Fit.dimsReales(0, AVAIL_125, 0, 0, 7, 23).rows, 29, 'con la celda vieja da 29 (y se corta)');
assert.strictEqual(Fit.dimsReales(0, AVAIL_125, 0, 0, 7, 25).rows, 26, 'con la celda nueva da 26 (entra entero)');
assert.ok(26 * 25 <= AVAIL_125, 'la grilla recalculada cabe en el alto útil');

// ── dimsDispositivo: la grilla se calcula en píxeles de DISPOSITIVO ──
// El buffer del canvas (lo único que se dibuja) vive en px de dispositivo, y con la
// Escala de la app el navegador lo redondea. Si la cuenta se pasa por UN píxel, esa
// fila —la del composer del agente— no se pinta NUNCA. Ver terminal.js/_fitReal.

// factor 1 (escala 100% en pantalla común): idéntico a dimsReales, sin margen.
assert.deepStrictEqual(
  Fit.dimsDispositivo(300, 971, 24, 51, 7, 23, 1),
  Fit.dimsReales(300, 971, 24, 51, 7, 23),
  'con factor 1 no cambia nada'
);
assert.strictEqual(Fit.dimsDispositivo(0, 920, 0, 0, 7, 23, 1).rows, 40, 'factor 1: no pierde la última fila');

// factor no entero: reserva 1px de dispositivo para que la última fila entre en
// el buffer redondeado (el caso 145% que dejaba el composer sin pintar).
const alto145 = 579, celdaDev145 = 35;   // px CSS útiles y celda de dispositivo a 145%
assert.strictEqual(Fit.dimsDispositivo(0, alto145, 0, 0, 7, celdaDev145, 1.45).rows, 23);
assert.ok(23 * celdaDev145 <= Math.floor(alto145 * 1.45), 'la grilla entra en el buffer');

// escala < 100%: el factor achica el área en px de dispositivo (a 80% el fit por px
// CSS pedía 47 filas y el buffer solo podía dibujar ~37).
assert.strictEqual(Fit.dimsDispositivo(0, 1175, 0, 0, 7, 25, 0.8).rows, 37);

// pisos y basura: nunca por debajo del mínimo comunicable, nunca NaN.
assert.strictEqual(Fit.dimsDispositivo(0, 10, 0, 0, 7, 25, 0.8).rows, 5);
const raro = Fit.dimsDispositivo(700, 460, 8, 43, 7, 23, 0);
assert.ok(Number.isFinite(raro.cols) && Number.isFinite(raro.rows));
assert.deepStrictEqual(raro, Fit.dimsDispositivo(700, 460, 8, 43, 7, 23, undefined), 'factor inválido → 1');

console.log('OK terminal-fit');
