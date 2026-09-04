// Tests de la cola de attaches (attach-queue.js): los WS/seeds de las N
// terminales se abren de a CONCURRENCIA (no todos juntos) — sin esto, tras un
// reload con 6-9 terminales los seeds de 2000 líneas se parsean todos en el
// mismo instante en el main thread = freeze de 3-5s (bug del update).
'use strict';
const assert = require('assert');
const { crearCola, CONCURRENCIA, TIMEOUT_SLOT_MS } = require('../attach-queue.js');

// Defaults sanos
assert.strictEqual(CONCURRENCIA, 2);
assert.ok(TIMEOUT_SLOT_MS >= 3000, 'failsafe de slot razonable');

// Pass-through: con la cola libre, el attach corre SÍNCRONO (una terminal
// suelta no espera nada).
{
  const cola = crearCola();
  let corrio = false;
  cola.pedir(1, () => { corrio = true; });
  assert.strictEqual(corrio, true, 'attach inmediato con cola libre');
  assert.deepStrictEqual(cola.estado(), { pendientes: 0, activos: 1, usada: true, hechos: 0 });
}

// Progreso para el overlay post-update: `hechos` cuenta los attaches que YA
// soltaron su slot (seed entregado / cerrado / cancelado tras correr) —
// hechos + activos + pendientes = total de tiles a pintar.
{
  const cola = crearCola();
  for (const id of [1, 2, 3, 4]) cola.pedir(id, () => {});
  assert.deepStrictEqual(cola.estado(), { pendientes: 2, activos: 2, usada: true, hechos: 0 });
  cola.listo(1);
  assert.deepStrictEqual(cola.estado(), { pendientes: 1, activos: 2, usada: true, hechos: 1 });
  cola.listo(2); cola.listo(3); cola.listo(4);
  assert.deepStrictEqual(cola.estado(), { pendientes: 0, activos: 0, usada: true, hechos: 4 });
  // listo repetido / desconocido: no infla el progreso.
  cola.listo(4); cola.listo(99);
  assert.strictEqual(cola.estado().hechos, 4);
  // cancelar un pedido EN ESPERA no cuenta como hecho (nunca corrió)…
  cola.pedir(5, () => {}); cola.pedir(6, () => {}); cola.pedir(7, () => {});
  cola.cancelar(7);
  assert.strictEqual(cola.estado().hechos, 4);
  // …pero cancelar uno ACTIVO sí (corrió y liberó su slot).
  cola.cancelar(5);
  assert.strictEqual(cola.estado().hechos, 5);
}

// Concurrencia 2 + FIFO: de 5 pedidos corren 2; cada listo() libera el
// siguiente EN ORDEN.
{
  const cola = crearCola();
  const corridos = [];
  for (const id of [1, 2, 3, 4, 5]) cola.pedir(id, () => corridos.push(id));
  assert.deepStrictEqual(corridos, [1, 2], 'solo 2 en vuelo');
  assert.deepStrictEqual(cola.estado(), { pendientes: 3, activos: 2, usada: true, hechos: 0 });
  cola.listo(1);
  assert.deepStrictEqual(corridos, [1, 2, 3], 'listo(1) despacha el 3º');
  cola.listo(3);
  cola.listo(2);
  assert.deepStrictEqual(corridos, [1, 2, 3, 4, 5], 'todos corren en orden FIFO');
  assert.deepStrictEqual(cola.estado(), { pendientes: 0, activos: 2, usada: true, hechos: 3 });
}

// listo() de un id desconocido / repetido: no-op (no libera slots de más).
{
  const cola = crearCola();
  const corridos = [];
  for (const id of [1, 2, 3]) cola.pedir(id, () => corridos.push(id));
  cola.listo(99);
  cola.listo(99);
  assert.deepStrictEqual(corridos, [1, 2], 'listo desconocido no despacha');
  cola.listo(1);
  cola.listo(1);   // repetido: el slot ya se liberó una vez
  assert.deepStrictEqual(corridos, [1, 2, 3]);
  assert.deepStrictEqual(cola.estado(), { pendientes: 0, activos: 2, usada: true, hechos: 1 });
}

// cancelar(): un pedido en ESPERA se descarta (la card se eliminó antes de su
// turno); un pedido ACTIVO libera su slot.
{
  const cola = crearCola();
  const corridos = [];
  for (const id of [1, 2, 3, 4]) cola.pedir(id, () => corridos.push(id));
  cola.cancelar(4);              // en espera → nunca corre
  cola.cancelar(1);              // activo → libera el slot → corre el 3
  assert.deepStrictEqual(corridos, [1, 2, 3], 'el 4 cancelado no corre');
  cola.listo(2); cola.listo(3);
  assert.deepStrictEqual(corridos, [1, 2, 3]);
}

// Re-pedir el MISMO id (reconexión con backoff): el pedido viejo en espera se
// reemplaza (no corre dos veces) y el slot activo viejo se libera.
{
  const cola = crearCola();
  const corridos = [];
  cola.pedir(1, () => corridos.push('a1'));
  cola.pedir(2, () => corridos.push('a2'));
  cola.pedir(3, () => corridos.push('viejo3'));
  cola.pedir(3, () => corridos.push('nuevo3'));   // reemplaza al viejo en espera
  cola.listo(1);
  assert.deepStrictEqual(corridos, ['a1', 'a2', 'nuevo3'], 'el pedido viejo del 3 no corre');
}

// Un fn que TIRA no traba la cola (slot liberado al toque).
{
  const cola = crearCola();
  const corridos = [];
  cola.pedir(1, () => { throw new Error('boom'); });
  cola.pedir(2, () => corridos.push(2));
  cola.pedir(3, () => corridos.push(3));
  assert.deepStrictEqual(corridos, [2, 3], 'el fn roto no retiene su slot');
}

// Failsafe por timeout: si el seed nunca llega (WS muerto sin onclose), el slot
// se libera solo y la cola sigue fluyendo. (timeout corto inyectado para el test)
(async () => {
  const cola = crearCola({ timeoutMs: 30 });
  const corridos = [];
  for (const id of [1, 2, 3]) cola.pedir(id, () => corridos.push(id));
  assert.deepStrictEqual(corridos, [1, 2]);
  await new Promise(r => setTimeout(r, 90));
  assert.deepStrictEqual(corridos, [1, 2, 3], 'el timeout liberó los slots');
  console.log('attach-queue: OK');
})();
