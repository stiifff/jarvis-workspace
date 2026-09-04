'use strict';
// Tests de la lógica pura de detección del bloque de input (Ctrl+A en terminal).
// Los casos vienen de capturas REALES de tmux con Claude Code y bash (2026-06-05).
// Corre con: node frontend/sections/terminals/__tests__/input-block.test.js
const assert = require('assert');
const B = require('../terminal-input-block.js');

const L = (text, isWrapped = false) => ({ text, isWrapped });

// ── Claude Code: una línea ────────────────────────────────────────
{
  const lineas = [
    L('respuesta previa del agente'),
    L('────────────────────────────'),
    L('❯ texto largo del que me arrepiento'),
    L('────────────────────────────'),
  ];
  const b = B.detectarBloqueInput(lineas, 2, 'claude');
  assert.deepStrictEqual(b, { start: 2, end: 2 }, 'claude 1 línea: bloque');
  assert.strictEqual(B.extraerTextoInput(lineas, b, 'claude'),
    'texto largo del que me arrepiento', 'claude 1 línea: texto');
}

// ── Claude Code: multilínea (Shift+Enter), cursor al final ────────
{
  const lineas = [
    L('────────────────────────────'),
    L('❯ uno'),
    L('  dos'),
    L('  tres'),
    L('────────────────────────────'),
  ];
  const b = B.detectarBloqueInput(lineas, 3, 'claude');
  assert.deepStrictEqual(b, { start: 1, end: 3 }, 'claude multilínea: bloque');
  assert.strictEqual(B.extraerTextoInput(lineas, b, 'claude'),
    'uno\ndos\ntres', 'claude multilínea: texto');
}

// ── Claude Code: cursor en el MEDIO del multilínea → agarra todo ──
{
  const lineas = [
    L('────────────────────────────'),
    L('❯ uno'),
    L('  dos'),
    L('  tres'),
    L('────────────────────────────'),
  ];
  const b = B.detectarBloqueInput(lineas, 2, 'claude');
  assert.deepStrictEqual(b, { start: 1, end: 3 }, 'claude cursor al medio: bloque completo');
}

// ── Claude Code: línea larga wrapeada por el ancho ────────────────
{
  const lineas = [
    L('❯ texto larguisimo que '),
    L('sigue en la fila de abajo', true),
  ];
  const b = B.detectarBloqueInput(lineas, 1, 'claude');
  assert.deepStrictEqual(b, { start: 0, end: 1 }, 'claude wrap: bloque');
  assert.strictEqual(B.extraerTextoInput(lineas, b, 'claude'),
    'texto larguisimo que sigue en la fila de abajo', 'claude wrap: texto unido sin salto');
}

// ── Claude Code: input vacío ──────────────────────────────────────
{
  const lineas = [L('❯')];
  const b = B.detectarBloqueInput(lineas, 0, 'claude');
  assert.deepStrictEqual(b, { start: 0, end: 0 }, 'claude vacío: bloque');
  assert.strictEqual(B.extraerTextoInput(lineas, b, 'claude'), '', 'claude vacío: texto vacío');
}

// ── Codex/Qwen: otros glifos de prompt ──────────────────────────
{
  const lineas = [L('› mensaje para codex')];
  const b = B.detectarBloqueInput(lineas, 0, 'codex');
  assert.strictEqual(B.extraerTextoInput(lineas, b, 'codex'),
    'mensaje para codex', 'glifo ›');
  const lineas2 = [L('> mensaje para qwen')];
  const b2 = B.detectarBloqueInput(lineas2, 0, 'qwen');
  assert.strictEqual(B.extraerTextoInput(lineas2, b2, 'qwen'),
    'mensaje para qwen', 'glifo >');
}

// ── Un borde corta el escaneo hacia arriba (no cruza cajas) ───────
{
  const lineas = [
    L('❯ input de un prompt VIEJO'),
    L('────────────────────────────'),
    L('texto cualquiera donde está el cursor'),
    L('continuación wrapeada', true),
  ];
  const b = B.detectarBloqueInput(lineas, 3, 'claude');
  assert.deepStrictEqual(b, { start: 2, end: 3 }, 'borde: no se cuelga del prompt viejo');
}

// ── bash: línea simple, pela el prompt ────────────────────────────
{
  const lineas = [L('user@DESKTOP-PV7APM8:~/jarvis$ texto que me arrepiento de escribir')];
  const b = B.detectarBloqueInput(lineas, 0, 'manual');
  assert.deepStrictEqual(b, { start: 0, end: 0 }, 'bash simple: bloque');
  assert.strictEqual(B.extraerTextoInput(lineas, b, 'manual'),
    'texto que me arrepiento de escribir', 'bash simple: texto sin prompt');
}

// ── bash: comando largo wrapeado, cursor en cualquiera de las filas ─
{
  const lineas = [
    L('user@DESKTOP-PV7APM8:~/jarvis$ echo hola esto '),
    L('es una prueba larga', true),
  ];
  for (const cursor of [0, 1]) {
    const b = B.detectarBloqueInput(lineas, cursor, 'manual');
    assert.deepStrictEqual(b, { start: 0, end: 1 }, `bash wrap cursor=${cursor}: bloque`);
  }
  const b = B.detectarBloqueInput(lineas, 1, 'manual');
  assert.strictEqual(B.extraerTextoInput(lineas, b, 'manual'),
    'echo hola esto es una prueba larga', 'bash wrap: texto unido');
}

// ── bash: NO interpreta sangrías como continuación (eso es de TUIs) ─
{
  const lineas = [
    L('user@host:~$ comando'),
    L('  salida indentada de algo previo'),
  ];
  const b = B.detectarBloqueInput(lineas, 0, 'manual');
  assert.deepStrictEqual(b, { start: 0, end: 0 }, 'bash: sangría de abajo no es input');
}

// ── Anti falso-ancla: cita "> ..." del output NO captura el bloque ─
{
  const lineas = [
    L('> esto es una cita markdown del output'),
    L('texto plano del agente'),
    L('otra fila de output donde cayó el cursor'),
  ];
  const b = B.detectarBloqueInput(lineas, 2, 'claude');
  assert.deepStrictEqual(b, { start: 2, end: 2 },
    'falso ancla: filas no-continuación entre la cita y el cursor la descartan');
}

// ── Anti falso-ancla NO rompe el caso real (continuidad por sangría) ─
{
  const lineas = [L('❯ uno'), L('  dos'), L('  tres')];
  const b = B.detectarBloqueInput(lineas, 2, 'claude');
  assert.deepStrictEqual(b, { start: 0, end: 2 }, 'contigüidad: multilínea real sigue anclando');
}

// ── OpenCode: el borde ┃ (U+2503) corta el escaneo ────────────────
{
  const lineas = [
    L('┃ contenido del input de opencode'),
    L('fila donde está el cursor'),
  ];
  const b = B.detectarBloqueInput(lineas, 1, 'opencode');
  assert.deepStrictEqual(b, { start: 1, end: 1 }, 'opencode: ┃ es borde, no ancla');
}

// ── Robustez: cursorRow fuera de rango / lineas vacías ────────────
{
  assert.strictEqual(B.detectarBloqueInput([], 0, 'claude'), null, 'lineas vacías → null');
  const lineas = [L('❯ hola')];
  const b = B.detectarBloqueInput(lineas, 99, 'claude');
  assert.deepStrictEqual(b, { start: 0, end: 0 }, 'cursor fuera de rango: clampea');
}

console.log('✓ input-block: todos los tests pasan');
