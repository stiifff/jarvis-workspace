'use strict';
const assert = require('node:assert');
const T = require('../themes.js');

// 24 temas: colección curada 2026-07-10 — se fueron indigo/cian/ambar/bordo
// (casi duplicados de violeta/azul/oro/rojo) y entraron 6 ejes nuevos; después
// bosque/petroleo (parejas bg/acento) y papel/alba (los primeros temas claros).
assert.deepStrictEqual(T.TEMAS, [
  'violeta', 'azul', 'verde', 'rosa', 'rojo',
  'oceano', 'esmeralda', 'lima', 'naranja', 'oro',
  'orquidea', 'grafito', 'hielo', 'medianoche',
  'sakura', 'salvia', 'neon', 'crepusculo', 'aurora', 'tinta',
  'bosque', 'petroleo', 'papel', 'alba',
]);
assert.strictEqual(T.TEMAS.length, 24);
assert.strictEqual(new Set(T.TEMAS).size, 24);   // sin duplicados
assert.strictEqual(T.DEFAULT_TEMA, 'violeta');
assert.strictEqual(T.normalizarTema('azul'), 'azul');
assert.strictEqual(T.normalizarTema('sakura'), 'sakura');
assert.strictEqual(T.normalizarTema('tinta'), 'tinta');
assert.strictEqual(T.normalizarTema('papel'), 'papel');    // tema claro
assert.strictEqual(T.normalizarTema('alba'), 'alba');      // tema claro
assert.strictEqual(T.normalizarTema('bosque'), 'bosque');
assert.strictEqual(T.normalizarTema('petroleo'), 'petroleo');

// ── Clasificación claro/oscuro (filtro del picker de Apariencia) ──
assert.deepStrictEqual(T.TEMAS_CLAROS, ['papel', 'alba']);
for (const t of T.TEMAS_CLAROS) assert.ok(T.TEMAS.includes(t), `claro ${t} no está en TEMAS`);
assert.strictEqual(T.esTemaClaro('papel'), true);
assert.strictEqual(T.esTemaClaro('alba'), true);
assert.strictEqual(T.esTemaClaro('violeta'), false);
assert.strictEqual(T.esTemaClaro('tinta'), false);     // negro editorial: oscuro
assert.strictEqual(T.esTemaClaro('inexistente'), false);
assert.strictEqual(T.normalizarTema('indigo'), 'violeta');   // removido → default
assert.strictEqual(T.normalizarTema('bordo'), 'violeta');    // removido → default
assert.strictEqual(T.normalizarTema('fucsia'), 'violeta');   // desconocido → default
assert.strictEqual(T.normalizarTema(null), 'violeta');
assert.strictEqual(T.normalizarTema(undefined), 'violeta');
assert.strictEqual(T.normalizarTema(''), 'violeta');

// ── Tonalidad: normalización ──
assert.deepStrictEqual(T.TINTE_DEFAULT, { matiz: 0, saturacion: 100, profundidad: 0 });
assert.deepStrictEqual(T.normalizarTinte(null), T.TINTE_DEFAULT);
assert.deepStrictEqual(T.normalizarTinte({}), T.TINTE_DEFAULT);
assert.deepStrictEqual(
  T.normalizarTinte({ matiz: 20, saturacion: 130, profundidad: -2 }),
  { matiz: 20, saturacion: 130, profundidad: -2 },
);
// clamps a los rangos de los sliders
assert.deepStrictEqual(
  T.normalizarTinte({ matiz: 999, saturacion: -5, profundidad: 99 }),
  { matiz: 40, saturacion: 50, profundidad: 3 },
);
// basura → default por campo
assert.deepStrictEqual(
  T.normalizarTinte({ matiz: 'x', saturacion: NaN, profundidad: '1.5' }),
  { matiz: 0, saturacion: 100, profundidad: 1.5 },
);
assert.strictEqual(T.esTinteNeutro(T.normalizarTinte(null)), true);
assert.strictEqual(T.esTinteNeutro(T.normalizarTinte({ matiz: 1 })), false);

// ── parseOklch: solo el formato de tokens.css ──
assert.deepStrictEqual(T.parseOklch('oklch(61% 0.22 293)'), { l: 61, c: 0.22, h: 293 });
assert.deepStrictEqual(T.parseOklch('  oklch( 13.5% 0.012 250 ) '), { l: 13.5, c: 0.012, h: 250 });
assert.strictEqual(T.parseOklch('oklch(61% 0.22 293 / 0.5)'), null);  // alpha no
assert.strictEqual(T.parseOklch('#7c5cff'), null);
assert.strictEqual(T.parseOklch(''), null);
assert.strictEqual(T.parseOklch(null), null);

// ── ajustarOklch ──
const neutro = T.normalizarTinte(null);
assert.strictEqual(T.ajustarOklch('oklch(61% 0.22 293)', neutro, false), 'oklch(61% 0.22 293)');
// matiz gira la rueda (con wrap 0..360)
assert.strictEqual(
  T.ajustarOklch('oklch(61% 0.22 293)', T.normalizarTinte({ matiz: 30 }), false),
  'oklch(61% 0.22 323)',
);
assert.strictEqual(
  T.ajustarOklch('oklch(61% 0.22 350)', T.normalizarTinte({ matiz: 30 }), false),
  'oklch(61% 0.22 20)',
);
assert.strictEqual(
  T.ajustarOklch('oklch(61% 0.22 10)', T.normalizarTinte({ matiz: -30 }), false),
  'oklch(61% 0.22 340)',
);
// saturación escala el croma (con techo 0.27 y piso 0)
assert.strictEqual(
  T.ajustarOklch('oklch(61% 0.2 293)', T.normalizarTinte({ saturacion: 150 }), false),
  'oklch(61% 0.27 293)',   // 0.3 clampeado al techo
);
assert.strictEqual(
  T.ajustarOklch('oklch(61% 0.2 293)', T.normalizarTinte({ saturacion: 50 }), false),
  'oklch(61% 0.1 293)',
);
assert.strictEqual(
  T.ajustarOklch('oklch(83% 0 0)', T.normalizarTinte({ saturacion: 150 }), false),
  'oklch(83% 0 0)',        // grafito: croma 0 queda 0
);
// profundidad SOLO con conProfundidad=true (fondos/líneas, no acento)
assert.strictEqual(
  T.ajustarOklch('oklch(13% 0.018 300)', T.normalizarTinte({ profundidad: -2 }), true),
  'oklch(11% 0.018 300)',
);
assert.strictEqual(
  T.ajustarOklch('oklch(61% 0.22 293)', T.normalizarTinte({ profundidad: -2 }), false),
  'oklch(61% 0.22 293)',
);
// piso de luminosidad (no baja de 3%)
assert.strictEqual(
  T.ajustarOklch('oklch(4% 0.01 300)', T.normalizarTinte({ profundidad: -3 }), true),
  'oklch(3% 0.01 300)',
);
assert.strictEqual(T.ajustarOklch('no-color', neutro, true), null);

console.log('themes.test.js OK');
