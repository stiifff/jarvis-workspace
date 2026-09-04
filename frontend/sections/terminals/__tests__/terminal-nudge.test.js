'use strict';
// Tests del "scroll fantasma" — la cura automática del transcript en blanco de
// claude fullscreen tras un resize (maximizar/restaurar/eliminar terminal).
//
// Familia: claude IDLE no redibuja el transcript en SIGWINCH (upstream #43273,
// cerrado not-planned) — tras el resize redibuja SOLO su franja viva de abajo
// (status/spinner) y deja el resto VACÍO + el pill "Jump to bottom" (foto del
// usuario 2026-07-18). El blanco está EN el dibujo de la app: ningún repintado
// local (pintarYa/refresh/re-seed) puede inventarlo. La única cura real es la
// que el usuario hace a mano: la RUEDA (claude re-layoutea y re-renderiza al
// recibirla). Esto la automatiza: rueda arriba + rueda abajo (neto CERO) por el
// mismo camino que una rueda real (coreMouseService → SGR → WS → tty del pane),
// solo cuando la firma del blanco está presente. Ver [[negro-fullscreen-frames-2026]].

const assert = require('node:assert');
const N = require('../terminal-nudge.js');

// helper: viewport fake de n filas, con contenido donde diga el mapa
function filas(n, conTexto) {
  const out = [];
  for (let i = 0; i < n; i++) out.push(conTexto.includes(i) ? `linea ${i} contenido` : '');
  return out;
}

// ── 1 · firmaTranscriptVacio: la foto del usuario (hueco gigante + franja viva abajo) ──
{
  // 37 filas: burbuja vieja arriba (0-1), hueco 2-29 (28 filas ≈ 75%), UI de claude 30-36
  const f = filas(37, [0, 1, 30, 31, 32, 33, 34, 35, 36]);
  assert.strictEqual(N.firmaTranscriptVacio(f), true, 'la firma de la foto debe detectarse');
}

// ── 2 · pantalla sana de claude (texto por todos lados, huecos chicos): NO dispara ──
{
  const conTexto = [];
  for (let i = 0; i < 37; i++) if (i % 4 !== 3) conTexto.push(i);   // huecos de 1 fila
  assert.strictEqual(N.firmaTranscriptVacio(filas(37, conTexto)), false);
}

// ── 3 · shell tras un clear (prompt arriba, resto vacío SIN contenido debajo): NO ──
{
  const f = filas(37, [0]);   // solo el prompt arriba
  assert.strictEqual(N.firmaTranscriptVacio(f), false,
    'hueco al fondo sin franja viva debajo = pantalla legítimamente vacía, no la foto');
}

// ── 4 · panel minúsculo: no opinar (sin filas suficientes la firma no es confiable) ──
{
  assert.strictEqual(N.firmaTranscriptVacio(filas(6, [5])), false);
  assert.strictEqual(N.firmaTranscriptVacio([]), false);
  assert.strictEqual(N.firmaTranscriptVacio(null), false);
}

// ── 5 · hueco justo en el umbral (40%): dispara con contenido debajo ──
{
  // 20 filas: contenido 0-5, hueco 6-13 (8 filas = 40%), contenido 14-19
  const f = filas(20, [0, 1, 2, 3, 4, 5, 14, 15, 16, 17, 18, 19]);
  assert.strictEqual(N.firmaTranscriptVacio(f), true);
  // hueco de 7 filas (35%): no alcanza
  const g = filas(20, [0, 1, 2, 3, 4, 5, 13, 14, 15, 16, 17, 18, 19]);
  assert.strictEqual(N.firmaTranscriptVacio(g), false);
}

// ── 6 · filas con solo espacios cuentan como vacías ──
{
  const f = filas(20, [0, 18, 19]);
  f[5] = '    ';   // espacios puros
  assert.strictEqual(N.firmaTranscriptVacio(f), true);
}

// ── 7 · debeNudgear: TODOS los gates tienen que estar verdes ──
{
  const base = { alt: true, mouse: true, firma: true, yaNudgeado: false, msDesdeNudge: null };
  assert.strictEqual(N.debeNudgear(base), true);
  assert.strictEqual(N.debeNudgear({ ...base, alt: false }), false,
    'buffer normal: los shells refluyen solos, la rueda scrollearía al usuario');
  assert.strictEqual(N.debeNudgear({ ...base, mouse: false }), false,
    'app sin mouse-tracking: la rueda caería como flechas al TUI — jamás');
  assert.strictEqual(N.debeNudgear({ ...base, firma: false }), false, 'sin blanco no hay nada que curar');
  assert.strictEqual(N.debeNudgear({ ...base, yaNudgeado: true }), false, 'one-shot por resize');
  assert.strictEqual(N.debeNudgear({ ...base, msDesdeNudge: 1000 }), false, 'cooldown global 3s');
  assert.strictEqual(N.debeNudgear({ ...base, msDesdeNudge: 4000 }), true, 'pasado el cooldown puede de nuevo');
}

// ── 8 · eventosRueda: up + down neto cero, misma forma que el evento real de xterm ──
{
  const evs = N.eventosRueda(204, 37);
  assert.strictEqual(evs.length, 2);
  const [up, down] = evs;
  assert.strictEqual(up.button, 4, 'button 4 = rueda (contrato del CoreMouseService vendoreado)');
  assert.strictEqual(down.button, 4);
  assert.strictEqual(up.action, 0, 'action 0 = rueda arriba (deltaY<0 en el vendor)');
  assert.strictEqual(down.action, 1, 'action 1 = rueda abajo');
  assert.strictEqual(up.col, down.col);
  assert.strictEqual(up.row, down.row);
  assert.ok(up.col > 0 && up.col < 204, 'coordenada dentro del pane (centro)');
  assert.ok(up.row > 0 && up.row < 37);
  for (const e of evs) {
    assert.strictEqual(e.ctrl, false); assert.strictEqual(e.alt, false); assert.strictEqual(e.shift, false);
    assert.strictEqual(typeof e.x, 'number'); assert.strictEqual(typeof e.y, 'number');
  }
  // panes degenerados: no romper
  const chico = N.eventosRueda(0, 0);
  assert.ok(chico[0].col >= 0 && chico[0].row >= 0);
}

// ── 9 · vigilanteTick: el blanco también NACE SIN resize (foto 2026-07-18 v2:
// card sin maximizar, claude con el transcript en blanco y el follow roto). Un
// vigilante periódico (2.5s) detecta la firma sostenida y escala en DOS pasos
// que además DIAGNOSTICAN al culpable (lo que la rueda del usuario no puede:
// cura en ambas familias sin decir cuál era):
//   idle →(firma ×2 ticks)→ 'seed'  — pide {'type':'refresh'}: pinta la VERDAD
//     de tmux. Si eso cura → el blanco era de NUESTRA vista (bug del relay/seed,
//     queda registrado). Si no…
//   →(firma persiste)→ 'rueda' — tmux también está en blanco ⇒ lo dibujó la app
//     (claude idle): la rueda neto-cero la despierta.
//   →(firma persiste)→ 'rendido' — nada la cura: se registra y NO se spamea.
// Cualquier tick sin firma = cura observada → reset y re-armado.
{
  const V = N.vigilanteTick;
  // sin firma: estado base
  let e = V(null, false);
  assert.strictEqual(e.accion, null);
  assert.strictEqual(e.fase, 'idle');
  // primer tick con firma: anti-transitorio, todavía nada
  e = V(e, true);
  assert.strictEqual(e.accion, null);
  // segundo tick consecutivo: pide el SEED (verdad de tmux) primero
  e = V(e, true);
  assert.strictEqual(e.accion, 'seed');
  assert.strictEqual(e.fase, 'seed');
  // la firma SOBREVIVE al seed ⇒ tmux también estaba en blanco ⇒ RUEDA
  e = V(e, true);
  assert.strictEqual(e.accion, 'rueda');
  assert.strictEqual(e.fase, 'rueda');
  // sigue en blanco tras la rueda: rendirse (jamás spamear a una app sorda)
  e = V(e, true);
  assert.strictEqual(e.accion, 'rendido');
  e = V(e, true);
  assert.strictEqual(e.accion, null, 'rendido es terminal: cero acciones repetidas');
  assert.strictEqual(e.fase, 'rendido');
  // cura observada (venga de donde venga): reset + re-armado
  e = V(e, false);
  assert.strictEqual(e.fase, 'idle');
  // reaparece sostenido: el ciclo completo arranca de nuevo
  e = V(e, true); e = V(e, true);
  assert.strictEqual(e.accion, 'seed', 'tras una cura observada vuelve a actuar');
  // el SEED cura (firma desaparece justo después): quedó diagnosticado como
  // bug de vista y NO se manda ninguna rueda
  let s = V(null, true); s = V(s, true);
  assert.strictEqual(s.accion, 'seed');
  s = V(s, false);
  assert.strictEqual(s.fase, 'idle');
  assert.strictEqual(s.accion, null);
  // transitorio de 1 tick: nunca dispara nada
  let t = V(null, true); t = V(t, false); t = V(t, true);
  assert.strictEqual(t.accion, null);
  // estado previo roto/nulo: no tira
  assert.doesNotThrow(() => V(undefined, true));
  assert.doesNotThrow(() => V({ basura: 1 }, true));
}

console.log('terminal-nudge.test.js OK');
