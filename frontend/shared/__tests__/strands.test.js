'use strict';
const assert = require('node:assert');
const S = require('../strands.js');

// ── Constantes del port (deben calzar con los arrays del shader) ──
assert.strictEqual(S.MAX_HEBRAS, 12);
assert.strictEqual(S.MAX_COLORES, 8);
assert.strictEqual(S.DEFAULTS.count, 3);

// ── clampHebras: redondeo + clamp 1..12, basura → default ──
assert.strictEqual(S.clampHebras(3), 3);
assert.strictEqual(S.clampHebras(3.7), 4);
assert.strictEqual(S.clampHebras(0), 1);
assert.strictEqual(S.clampHebras(-5), 1);
assert.strictEqual(S.clampHebras(99), 12);
assert.strictEqual(S.clampHebras('7'), 7);
assert.strictEqual(S.clampHebras(NaN), 3);
assert.strictEqual(S.clampHebras(undefined), 3);
assert.strictEqual(S.clampHebras('hola'), 3);

// ── resolverOpciones: merge sobre defaults con coerción numérica ──
const base = S.resolverOpciones();
assert.deepStrictEqual(base, Object.assign({}, S.DEFAULTS));
const mix = S.resolverOpciones({ speed: '0.3', glow: 2, count: 20, taper: 'x', extra: 9 });
assert.strictEqual(mix.speed, 0.3);       // string numérico coerciona
assert.strictEqual(mix.glow, 2);
assert.strictEqual(mix.count, 12);        // clampeado a MAX_HEBRAS
assert.strictEqual(mix.taper, S.DEFAULTS.taper);  // no-numérico → default
assert.strictEqual(mix.extra, undefined); // claves desconocidas no pasan
assert.strictEqual(mix.opacity, 1);       // el resto queda en default

// ── armarPaleta: pad a 8 repitiendo el último, count fiel ──
const p1 = S.armarPaleta([[1, 0, 0], [0, 1, 0]]);
assert.strictEqual(p1.n, 2);
assert.strictEqual(p1.plano.length, 24);
assert.deepStrictEqual([...p1.plano.slice(0, 3)], [1, 0, 0]);
assert.deepStrictEqual([...p1.plano.slice(3, 6)], [0, 1, 0]);
assert.deepStrictEqual([...p1.plano.slice(21, 24)], [0, 1, 0]);  // pad = último color

// vacío → n 0 (el shader cae a su espectro arcoíris)
const p0 = S.armarPaleta([]);
assert.strictEqual(p0.n, 0);
assert.strictEqual(S.armarPaleta(null).n, 0);
assert.strictEqual(S.armarPaleta(undefined).n, 0);

// más de 8 → trunca el count a 8 (el shader solo indexa hasta uColorCount)
const nueve = Array.from({ length: 9 }, (_, i) => [i / 9, 0, 0]);
const p9 = S.armarPaleta(nueve);
assert.strictEqual(p9.n, 8);
assert.strictEqual(p9.plano.length, 24);

// entradas malformadas se filtran (no rompen la paleta)
const pMal = S.armarPaleta([[1, 0, 0], 'x', [0, 0], null, [0, 0, 1]]);
assert.strictEqual(pMal.n, 2);
assert.deepStrictEqual([...pMal.plano.slice(3, 6)], [0, 0, 1]);

console.log('strands.test.js OK');
