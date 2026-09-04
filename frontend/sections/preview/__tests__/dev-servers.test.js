'use strict';
// Tests de la lógica pura del menú de localhost activos.
// Corre con: node frontend/sections/preview/__tests__/dev-servers.test.js
const assert = require('assert');
const { hostPuerto, total, etiqueta } = require('../dev-servers.js')._pure;

// ── hostPuerto ────────────────────────────────────────────────────
assert.strictEqual(hostPuerto('http://localhost:5173/'), 'localhost:5173', 'host:puerto');
assert.strictEqual(hostPuerto('http://localhost:5173/app?q=1'), 'localhost:5173', 'ignora path/query');
assert.strictEqual(hostPuerto('http://127.0.0.1:8000'), '127.0.0.1:8000', 'IP:puerto');
assert.strictEqual(hostPuerto('basura'), 'basura', 'no-url → devuelve lo dado');

console.log('OK hostPuerto');

// ── total (SOLO localhost; 0 → botón oculto, sin contar terminales) ──
assert.strictEqual(total([{ url: 'a' }]), 1, 'un localhost');
assert.strictEqual(total([{ url: 'a' }, { url: 'b' }]), 2, 'varios localhost');
assert.strictEqual(total([]), 0, 'ningún localhost → 0 (botón oculto)');
assert.strictEqual(total(undefined), 0, 'tolera basura');
// Las terminales/agentes trabajando ya NO cuentan en este menú: el 2º arg se ignora.
assert.strictEqual(total([], [{ terminal_id: 1 }]), 0, 'terminales NO cuentan');

console.log('OK total');

// ── etiqueta (demos del propio Jarvis muestran su carpeta, no localhost:3000) ──
assert.strictEqual(
  etiqueta({ tipo: 'demo', url: 'http://localhost:3000/static/wb-redesigns/index.html' }),
  'wb-redesigns', 'demo → carpeta, sin /index.html');
assert.strictEqual(
  etiqueta({ tipo: 'demo', url: 'http://localhost:3000/static/sidebar-redesign/v2/index.html?x=1' }),
  'sidebar-redesign/v2', 'ruta anidada, sin index ni query');
assert.strictEqual(
  etiqueta({ tipo: 'demo', url: 'http://localhost:3000/static/demo/pagina.html' }),
  'demo/pagina.html', 'archivo con nombre propio se conserva');
assert.strictEqual(
  etiqueta({ tipo: 'server', url: 'http://localhost:5173/app' }),
  'localhost:5173', 'server → host:puerto como siempre');
assert.strictEqual(
  etiqueta({ url: 'http://localhost:8000' }),
  'localhost:8000', 'sin tipo → server');
assert.strictEqual(etiqueta(null), null, 'tolera basura');

console.log('OK etiqueta');
// (serverDeTerminal se movió al backend: buscar_url_de_terminal en
//  core/dev_detect.py, testeado en backend/tests/test_dev_detect.py.)
console.log('OK ALL');
