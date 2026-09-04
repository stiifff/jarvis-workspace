'use strict';
// "Scroll fantasma" — cura automática del transcript en blanco de claude
// fullscreen tras un resize. Ver [[negro-fullscreen-frames-2026]].
//
// Familia (foto del usuario 2026-07-18): claude IDLE no redibuja el transcript
// en SIGWINCH (upstream #43273, cerrado not-planned). Tras maximizar/restaurar/
// eliminar (todo resize), claude redibuja SOLO su franja viva de abajo
// (status/spinner/pill) y deja el resto VACÍO — el blanco está EN el dibujo de
// la app, así que ningún repintado local (pintarYa / re-seed de tmux) puede
// inventarlo. La única cura real es la que el usuario hacía a mano: la RUEDA
// (claude re-layoutea y re-renderiza al recibirla). Este módulo la automatiza:
// rueda ARRIBA + rueda ABAJO (neto CERO — si estaba al fondo vuelve al fondo y
// el follow se re-engancha; si estaba scrolleado queda ≈donde estaba) por el
// MISMO camino que una rueda real (coreMouseService.triggerMouseEvent → encoder
// SGR → WS → tty del pane). Gates duros: solo alt-screen + app trackeando mouse
// (sin tracking la rueda caería como flechas — jamás) + firma del blanco
// presente + one-shot por resize + cooldown global. Falso positivo (una app
// sana con un hueco grande legítimo) = un re-render invisible: inofensivo.
(function (global) {

  // Fracción mínima del viewport que tiene que ocupar el hueco para considerarlo
  // "transcript sin renderizar" (la foto real: ~75% vacío).
  const FRACCION_HUECO = 0.4;
  // Cooldown global entre nudges de una misma terminal (resize storms / drags).
  const COOLDOWN_MS = 3000;
  // Mínimo de filas para que la firma sea confiable (paneles minúsculos: no opinar).
  const MIN_FILAS = 8;

  /**
   * Firma de la foto: una corrida contigua de filas vacías ≥40% del viewport
   * CON contenido debajo (la franja viva de claude). El "contenido debajo"
   * excluye la pantalla legítimamente vacía (shell tras clear: hueco al fondo
   * y nada después). filas = strings del viewport (translateToString).
   */
  function firmaTranscriptVacio(filas) {
    if (!filas || !filas.length || filas.length < MIN_FILAS) return false;
    let mejorRun = 0, finMejor = -1, run = 0;
    for (let i = 0; i < filas.length; i++) {
      const vacia = !filas[i] || !String(filas[i]).trim();
      if (vacia) {
        run++;
        if (run > mejorRun) { mejorRun = run; finMejor = i; }
      } else {
        run = 0;
      }
    }
    if (mejorRun < Math.ceil(filas.length * FRACCION_HUECO)) return false;
    for (let i = finMejor + 1; i < filas.length; i++) {
      if (filas[i] && String(filas[i]).trim()) return true;
    }
    return false;
  }

  /** Todos los gates del nudge en un solo lugar (puro, testeable). */
  function debeNudgear(s) {
    if (!s) return false;
    if (!s.alt || !s.mouse || !s.firma || s.yaNudgeado) return false;
    if (s.msDesdeNudge != null && s.msDesdeNudge <= COOLDOWN_MS) return false;
    return true;
  }

  /**
   * Los dos eventos de rueda (arriba y después abajo — neto cero), con la MISMA
   * forma que arma el vendor para una rueda real: {col,row,x,y,button:4,
   * action:0|1,ctrl,alt,shift} (action 0 = arriba / deltaY<0). Coordenada al
   * centro del pane (0-based; el encoder SGR le suma 1).
   */
  function eventosRueda(cols, rows) {
    const col = Math.max(0, Math.floor((cols || 2) / 2) - 1);
    const row = Math.max(0, Math.floor((rows || 2) / 2) - 1);
    const base = { col, row, x: 0, y: 0, ctrl: false, alt: false, shift: false, button: 4 };
    return [
      Object.assign({}, base, { action: 0 }),
      Object.assign({}, base, { action: 1 }),
    ];
  }

  /**
   * Vigilante periódico (2.5s): el blanco también NACE SIN resize (follow roto
   * durante el streaming, reconexión sobre un pane ya roto, etc. — foto v2 del
   * usuario). Máquina de estados PURA por tick; escala en dos pasos que además
   * DIAGNOSTICAN al culpable (la rueda del usuario cura en ambas familias sin
   * decir cuál era):
   *   idle →(firma ×2)→ accion 'seed'   (refresh: pinta la verdad de tmux —
   *                                      si cura, el blanco era de NUESTRA vista)
   *   →(persiste)→      accion 'rueda'  (tmux también en blanco ⇒ app idle)
   *   →(persiste)→      accion 'rendido' (registrar y no spamear jamás)
   * Tick sin firma = cura observada → reset y re-armado.
   */
  function vigilanteTick(prev, firma) {
    const fase = (prev && typeof prev.fase === 'string') ? prev.fase : 'idle';
    const consec = (prev && typeof prev.consec === 'number') ? prev.consec : 0;
    if (!firma) return { fase: 'idle', consec: 0, accion: null };
    const n = consec + 1;
    if (fase === 'idle') {
      if (n >= 2) return { fase: 'seed', consec: n, accion: 'seed' };
      return { fase: 'idle', consec: n, accion: null };
    }
    if (fase === 'seed')   return { fase: 'rueda', consec: n, accion: 'rueda' };
    if (fase === 'rueda')  return { fase: 'rendido', consec: n, accion: 'rendido' };
    return { fase: 'rendido', consec: n, accion: null };
  }

  const api = { FRACCION_HUECO, COOLDOWN_MS, firmaTranscriptVacio, debeNudgear, eventosRueda,
                vigilanteTick };
  global.TerminalNudge = Object.assign(global.TerminalNudge || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
