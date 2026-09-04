'use strict';
// Tests del contador de acks del flow control PTY→WS→xterm (séptima capa de
// [[tmux-size-clamping]]): el browser confirma bytes YA PARSEADOS por xterm
// (callback de term.write) y el backend deja de leer el PTY cuando hay
// demasiado sin confirmar — así la cola interna de xterm jamás llega a los
// 50MB donde tira datos ("write data discarded") en pestañas ocultas.
const assert = require('node:assert');
const F = require('../terminal-flow.js');

// Umbral default: ack cada 64KB procesados (granularidad fina contra el
// watermark de 1MB del backend, sin spamear el WS por cada chunk).
assert.strictEqual(F.UMBRAL_ACK, 65536);

const c = F.crearContadorAck(100);
assert.strictEqual(c.procesado(40), 0);      // acumula, no llegó al umbral
assert.strictEqual(c.procesado(40), 0);
assert.strictEqual(c.procesado(40), 120);    // cruzó: devuelve TODO y resetea
assert.strictEqual(c.procesado(99), 0);      // arrancó de cero tras el ack
assert.strictEqual(c.procesado(1), 100);     // umbral exacto también ackea

// Entradas basura no rompen la cuenta (defensivo: e.data raro)
assert.strictEqual(c.procesado(NaN), 0);
assert.strictEqual(c.procesado(-5), 0);
assert.strictEqual(c.procesado(Infinity), 0);
assert.strictEqual(c.procesado(0), 0);
assert.strictEqual(c.procesado(100), 100);   // la basura no dejó residuo

// Sin argumento usa UMBRAL_ACK
const d = F.crearContadorAck();
assert.strictEqual(d.procesado(65535), 0);
assert.strictEqual(d.procesado(1), 65536);

// ─── decidirDrenado: eco interactivo inmediato vs coalescing por frame ────────
const FLUSH = 512 * 1024;
const base = { inbufN: 3, flushSize: FLUSH, visible: true, msDesdeInput: 9999, ventanaEcoMs: 180 };

// Tab oculta: SIEMPRE rAF, aunque haya tipeo reciente o flood (protege la cola de 50MB)
assert.strictEqual(F.decidirDrenado({ ...base, visible: false, msDesdeInput: 5 }), false);
assert.strictEqual(F.decidirDrenado({ ...base, visible: false, inbufN: FLUSH }), false);

// Tab visible + backlog grande → drenar por tamaño (regla previa preservada)
assert.strictEqual(F.decidirDrenado({ ...base, inbufN: FLUSH }), true);
assert.strictEqual(F.decidirDrenado({ ...base, inbufN: FLUSH - 1 }), false);  // justo abajo, sin tipeo reciente

// Tab visible + tecla recién tipeada (dentro de la ventana) → eco inmediato
assert.strictEqual(F.decidirDrenado({ ...base, msDesdeInput: 0 }), true);
assert.strictEqual(F.decidirDrenado({ ...base, msDesdeInput: 50 }), true);
assert.strictEqual(F.decidirDrenado({ ...base, msDesdeInput: 179 }), true);
assert.strictEqual(F.decidirDrenado({ ...base, msDesdeInput: 180 }), false); // borde: fuera de la ventana
assert.strictEqual(F.decidirDrenado({ ...base, msDesdeInput: 9999 }), false);

// msDesdeInput basura/sin tipear nunca dispara el eco
assert.strictEqual(F.decidirDrenado({ ...base, msDesdeInput: NaN }), false);
assert.strictEqual(F.decidirDrenado({ ...base, msDesdeInput: -1 }), false);
assert.strictEqual(F.decidirDrenado({ ...base, msDesdeInput: Infinity }), false);

// ventana default cuando no se pasa
assert.strictEqual(F.VENTANA_ECO_MS, 180);
assert.strictEqual(F.decidirDrenado({ inbufN: 3, flushSize: FLUSH, visible: true, msDesdeInput: 100 }), true);

console.log('OK terminal-flow');

// ══ lineasDeRueda: rueda proporcional con FACTOR de velocidad (pedido 2026-07-02) ══
{
  // Notch clásico de mouse (deltaMode 0 = píxeles, ~120px) → 120/18 * 3 = 20 líneas.
  assert.strictEqual(F.lineasDeRueda({ deltaY: 120, deltaMode: 0, rows: 40 }), 20);
  assert.strictEqual(F.lineasDeRueda({ deltaY: -120, deltaMode: 0, rows: 40 }), -20);
  // deltaMode 1 = líneas: se multiplican directo.
  assert.strictEqual(F.lineasDeRueda({ deltaY: 3, deltaMode: 1, rows: 40 }), 9);
  // deltaMode 2 = páginas: páginas × filas.
  assert.strictEqual(F.lineasDeRueda({ deltaY: 1, deltaMode: 2, rows: 30 }), 90);
  // Turbo (Alt apretado): ×15 en vez de ×3.
  assert.strictEqual(F.lineasDeRueda({ deltaY: 120, deltaMode: 0, rows: 40, turbo: true }), 100);
  // Trackpad fino (deltas chicos): devuelve FRACCIÓN — el caller acumula (no se pierde).
  const fino = F.lineasDeRueda({ deltaY: 4, deltaMode: 0, rows: 40 });
  assert.ok(fino > 0 && fino < 1);
  // Basura defensiva.
  assert.strictEqual(F.lineasDeRueda({ deltaY: NaN, deltaMode: 0, rows: 40 }), 0);
  assert.strictEqual(F.FACTOR_RUEDA, 3);
  console.log('OK lineasDeRueda');
}

// NOTA: los bloques que testeaban decidirHoldSeleccion / corrimientoVertical /
// anclaVirtualTrasFrame / clampAncla / filaChromeInferior / crearSelScroll /
// selScrollFrame / textoSelScroll / finTrasFrame / limpiarOverlays se removieron:
// esa maquinaria de reconstrucción de selección por frame-diff se eliminó de
// terminal-flow.js en la limpieza del frame-diff (689e6ae) y esas funciones ya no
// existen (el test venía fallando en HEAD desde entonces). La selección scroll+
// select vive ahora en dos lados: nativa en el buffer normal (terminal.js, la que
// ya andaba en inline) y el MODO SELECCIÓN in-terminal para claude fullscreen
// (terminal.js: switch de buffer local + hold en _flush + reseed por refresh).

// ══ decidirReintento: qué hacer cuando el WS de una terminal se cierra ══
// (auditoría 2026-07-02: el auto-retry y el reload del updater corrían en
// paralelo → cada terminal attacheaba DOS veces por reinicio del server;
// y el close 4010 = "otra ventana tomó el control" no debe reintentar solo.)
{
  const D = F.decidirReintento;
  assert.strictEqual(F.CODIGO_DESPLAZADO, 4010);
  // Cierre intencional (navegación / eliminar): nada de nada.
  assert.strictEqual(D({ cerrando: true, codigo: 1000, recargando: false, autoIntento: 0 }), 'nada');
  // 4010 = desplazado por otra vista dueña: overlay especial, sin auto-retry
  // (reintentar solo armaría ping-pong entre las dos ventanas). Gana a todo.
  assert.strictEqual(D({ cerrando: false, codigo: 4010, recargando: false, autoIntento: 0 }), 'desplazado');
  assert.strictEqual(D({ cerrando: false, codigo: 4010, recargando: true,  autoIntento: 9 }), 'desplazado');
  // La página va a recargarse (updater/boot_id): el reload hace el attach
  // definitivo — reintentar acá era el "doble re-attach por restart".
  assert.strictEqual(D({ cerrando: false, codigo: 1006, recargando: true, autoIntento: 0 }), 'nada');
  // Presupuesto de reintentos: 0..2 programan, el 3º cae al overlay manual.
  assert.strictEqual(D({ cerrando: false, codigo: 1006, recargando: false, autoIntento: 0 }), 'programar');
  assert.strictEqual(D({ cerrando: false, codigo: 1006, recargando: false, autoIntento: 2 }), 'programar');
  assert.strictEqual(D({ cerrando: false, codigo: 1006, recargando: false, autoIntento: 3 }), 'overlay');
  // maxAuto configurable; default 3.
  assert.strictEqual(D({ cerrando: false, codigo: 1006, recargando: false, autoIntento: 1, maxAuto: 1 }), 'overlay');
  // 4404 = el motor dice que la sesión TERMINÓ. Reintentar es imposible por
  // definición y el overlay de reconexión mentiría ("tu agente sigue
  // trabajando"). Gana a todo, igual que 4010.
  assert.strictEqual(F.CODIGO_TERMINADA, 4404);
  assert.strictEqual(D({ cerrando: false, codigo: 4404, recargando: false, autoIntento: 0 }), 'terminada');
  assert.strictEqual(D({ cerrando: false, codigo: 4404, recargando: true,  autoIntento: 9 }), 'terminada');
  // Pero un cierre intencional sigue mandando: es la ✕ del usuario.
  assert.strictEqual(D({ cerrando: true, codigo: 4404, recargando: false, autoIntento: 0 }), 'nada');
  console.log('OK decidirReintento');
}

// ─── cortarFrameSync: retención de frames DEC 2026 abiertos (2026-07-08) ──────
// claude fullscreen envuelve cada redraw en \x1b[?2026h ... \x1b[?2026l
// (synchronized output). xterm 5.3 NO implementa 2026: si el flush cae a MITAD
// de un frame grande (scroll / post-resize llegan troceados por tmux/WS) se
// pinta medio redraw → franjas NEGRAS hasta que llega el resto; y si la app
// queda idle después, el medio-frame PERSISTE (negro al salir de fullscreen).
// cortarFrameSync parte el buffer pendiente en { listo, resto }: listo se
// pinta YA, resto (frame abierto o posible marcador partido) espera al cierre.
{
  const C = F.cortarFrameSync;
  const H = '\x1b[?2026h', L = '\x1b[?2026l';

  // Sin marcadores: todo pintable, nada retenido.
  assert.deepStrictEqual(C('hola\x1b[31mrojo'), { listo: 'hola\x1b[31mrojo', resto: '' });
  assert.deepStrictEqual(C(''), { listo: '', resto: '' });

  // Frame COMPLETO: pasa entero (la atomicidad ya la trae el buffer).
  assert.deepStrictEqual(C(H + 'frame' + L), { listo: H + 'frame' + L, resto: '' });
  assert.deepStrictEqual(C('antes' + H + 'frame' + L + 'después'),
                         { listo: 'antes' + H + 'frame' + L + 'después', resto: '' });

  // Frame ABIERTO al final: retener DESDE el h (lo previo se pinta).
  assert.deepStrictEqual(C('previo' + H + 'mitad-de-frame'),
                         { listo: 'previo', resto: H + 'mitad-de-frame' });

  // Completo + abierto: el completo sale, el abierto espera.
  assert.deepStrictEqual(C(H + 'f1' + L + H + 'f2-a-medias'),
                         { listo: H + 'f1' + L, resto: H + 'f2-a-medias' });

  // Solo apertura (el buffer ARRANCA con el frame abierto): nada pintable aún.
  assert.deepStrictEqual(C(H + 'apenas'), { listo: '', resto: H + 'apenas' });

  // Cierre huérfano (el h se escribió en un flush FORZADO anterior): pasa todo.
  assert.deepStrictEqual(C('resto-del-frame' + L + 'más'),
                         { listo: 'resto-del-frame' + L + 'más', resto: '' });

  // MARCADOR PARTIDO entre chunks: si la cola termina en un prefijo de
  // \x1b[?2026, retenerla (el próximo chunk resuelve si era h o l).
  assert.deepStrictEqual(C('texto\x1b[?20'), { listo: 'texto', resto: '\x1b[?20' });
  assert.deepStrictEqual(C('texto\x1b[?2026'), { listo: 'texto', resto: '\x1b[?2026' });
  assert.deepStrictEqual(C('texto\x1b'), { listo: 'texto', resto: '\x1b' });
  // ...pero una secuencia que YA divergió del marcador no se retiene:
  assert.deepStrictEqual(C('texto\x1b[31'), { listo: 'texto\x1b[31', resto: '' });
  // ('\x1b[?25' dejó de ser divergencia el 2026-07-17: es prefijo del guard
  //  de cursor ?25l/?25h — ver el bloque de abajo.)
  assert.deepStrictEqual(C('texto\x1b[?3'), { listo: 'texto\x1b[?3', resto: '' });

  // forzar=true (válvula: hold vencido / resto gigante): pasa TODO, sin retener.
  assert.deepStrictEqual(C('previo' + H + 'mitad', { forzar: true }),
                         { listo: 'previo' + H + 'mitad', resto: '' });

  // Entradas raras no rompen (defensivo).
  assert.deepStrictEqual(C(null), { listo: '', resto: '' });
  assert.deepStrictEqual(C(undefined), { listo: '', resto: '' });

  // Doble apertura sin cierre (malformado, no pasa en la práctica): se retiene
  // desde el PRIMER h sin cerrar — jamás se pinta un frame a medias.
  assert.deepStrictEqual(C(H + 'a' + H + 'b'), { listo: '', resto: H + 'a' + H + 'b' });

  console.log('OK cortarFrameSync');
}

// ─── cortarFrameSync: guard de CURSOR ?25l/?25h (fix "parpadeo del cursor",
//     2026-07-17) ─────────────────────────────────────────────────────────────
// claude ≥2.1.214 YA NO emite marcadores 2026 (medido: 0 en los logs de stream
// de 3 terminales vivas) — la retención de arriba quedó inerte. Pero cada
// redraw sigue siendo `\x1b[?25l …repintado… \x1b[?25h`, y con full-repaint
// por tecla (12-43 mensajes WS por redraw) el flush cae ENTRE el hide y el
// show → el frame pinta con el cursor APAGADO → "parpadeo del dot" al tipear.
// Mismo tratamiento que un frame 2026: el hide ABRE un frame, el show lo
// CIERRA; las válvulas del caller (hold 150ms / cap 2MB / sequía 1s) cubren
// una app que deja el cursor escondido a propósito.
{
  const C = F.cortarFrameSync;
  const H = '\x1b[?2026h', L = '\x1b[?2026l';
  const HIDE = '\x1b[?25l', SHOW = '\x1b[?25h';

  // Redraw COMPLETO (hide…show): pasa entero.
  assert.deepStrictEqual(C(HIDE + 'redraw' + SHOW),
                         { listo: HIDE + 'redraw' + SHOW, resto: '' });
  assert.deepStrictEqual(C('antes' + HIDE + 'x' + SHOW + 'después'),
                         { listo: 'antes' + HIDE + 'x' + SHOW + 'después', resto: '' });

  // Redraw ABIERTO (hide sin show posterior): retener DESDE el hide.
  assert.deepStrictEqual(C('previo' + HIDE + 'mitad-de-redraw'),
                         { listo: 'previo', resto: HIDE + 'mitad-de-redraw' });

  // hide→show→hide: el primero cerró; retener desde el SEGUNDO.
  assert.deepStrictEqual(C(HIDE + 'f1' + SHOW + HIDE + 'f2'),
                         { listo: HIDE + 'f1' + SHOW, resto: HIDE + 'f2' });

  // show huérfano (el hide salió en un flush anterior): pasa todo.
  assert.deepStrictEqual(C('resto-del-redraw' + SHOW + 'más'),
                         { listo: 'resto-del-redraw' + SHOW + 'más', resto: '' });

  // Combinado con 2026: corta en la apertura MÁS TEMPRANA.
  assert.deepStrictEqual(C('a' + HIDE + 'b' + H + 'c'),
                         { listo: 'a', resto: HIDE + 'b' + H + 'c' });
  assert.deepStrictEqual(C('a' + H + 'b' + HIDE + 'c'),
                         { listo: 'a', resto: H + 'b' + HIDE + 'c' });
  assert.deepStrictEqual(C(H + 'f' + L + HIDE + 'x'),
                         { listo: H + 'f' + L, resto: HIDE + 'x' });
  assert.deepStrictEqual(C(HIDE + 'a' + SHOW + H + 'b'),
                         { listo: HIDE + 'a' + SHOW, resto: H + 'b' });

  // Marcador de cursor PARTIDO entre chunks: retener la cola ambigua.
  assert.deepStrictEqual(C('texto\x1b[?25'), { listo: 'texto', resto: '\x1b[?25' });
  assert.deepStrictEqual(C('texto\x1b[?2'), { listo: 'texto', resto: '\x1b[?2' });

  // forzar=true (válvulas del caller): suelta TODO, sin retener.
  assert.deepStrictEqual(C(HIDE + 'mitad', { forzar: true }),
                         { listo: HIDE + 'mitad', resto: '' });

  console.log('OK cortarFrameSync (guard de cursor ?25l/?25h)');
}

// ══ decidirRuedaAlt: rueda sobre una terminal en ALT-SCREEN ══
// El handler de rueda delega el scroll a la app cuando el buffer es alternate
// (claude fullscreen scrollea su transcript vía mouse-tracking). PERO si el
// mouse-tracking de xterm quedó INACTIVO (seed degradado: la captura no re-
// enunció los modos), la rueda se cedía a una app que jamás la recibía →
// SCROLL MUERTO hasta el próximo redraw ('una terminal random no scrollea y
// revive al mandarle un mensaje', 2026-07-11). Decisión:
//   'app'  → dejar pasar a xterm (+ copias sintéticas de velocidad)
//   'heal' → auto-curar: reset + refresh (re-seed re-enuncia los modos)
//   'nada' → tragarse la rueda (heal reciente en vuelo / WS caído / observador)
{
  const D = F.decidirRuedaAlt;
  assert.strictEqual(typeof F.HEAL_RUEDA_MS, 'number');
  const base = { mouseActivo: true, wsAbierto: true, observador: false, msDesdeHeal: Infinity };
  // Mouse activo → la app recibe la rueda: camino normal.
  assert.strictEqual(D(base), 'app');
  // Mouse INACTIVO (desacople del seed) + WS vivo → auto-curar.
  assert.strictEqual(D({ ...base, mouseActivo: false }), 'heal');
  // Heal reciente (rate-limit): no re-curar en loop — tragarse la rueda.
  assert.strictEqual(D({ ...base, mouseActivo: false, msDesdeHeal: 500 }), 'nada');
  assert.strictEqual(D({ ...base, mouseActivo: false, msDesdeHeal: F.HEAL_RUEDA_MS + 1 }), 'heal');
  // WS caído: no hay a quién pedirle el refresh.
  assert.strictEqual(D({ ...base, mouseActivo: false, wsAbierto: false }), 'nada');
  // Observador (?qa=1): el backend ignora su refresh — un reset lo dejaría en
  // blanco. Jamás curar desde una vista QA.
  assert.strictEqual(D({ ...base, mouseActivo: false, observador: true }), 'nada');
  // Con mouse activo nada de lo demás importa (ni observador: solo mira).
  assert.strictEqual(D({ ...base, observador: true }), 'app');
  console.log('OK decidirRuedaAlt');
}

// ══ decidirDestinoRueda: primary+mouse (Grok) vs primary sin mouse (bash) ══
// Grok Build (y otros TUI) corren en buffer NORMAL con mouse-tracking activo.
// El handler viejo SIEMPRE interceptaba la rueda en primary y scrolleaba el
// scrollback de xterm → la app jamás recibía el wheel ("el scroll no afecta
// a Grok"). Si la app pidió mouse, la rueda es de ELLA, también fuera de alt.
{
  const R = F.decidirDestinoRueda;
  assert.strictEqual(typeof R, 'function', 'decidirDestinoRueda exportada');
  const vivo = { wsAbierto: true, observador: false, msDesdeHeal: Infinity };
  assert.strictEqual(R({ ...vivo, alt: false, mouseActivo: true }), 'app',
    'Grok: primary + mouse → la rueda va a la app');
  assert.strictEqual(R({ ...vivo, alt: false, mouseActivo: false }), 'xterm',
    'bash: primary sin mouse → scrollback local de xterm');
  assert.strictEqual(R({ ...vivo, alt: true, mouseActivo: true }), 'app',
    'claude fullscreen: alt + mouse → app');
  assert.strictEqual(R({ ...vivo, alt: true, mouseActivo: false }), 'heal',
    'alt sin mouse + WS vivo → heal (seed degradado)');
  assert.strictEqual(R({ ...vivo, alt: true, mouseActivo: false, msDesdeHeal: 500 }), 'nada',
    'alt sin mouse recién curado → no tragar en loop');
  assert.strictEqual(R({ ...vivo, alt: false, mouseActivo: true, observador: true }), 'app',
    'observador con mouse activo: deja pasar (solo mira)');
  console.log('OK decidirDestinoRueda');
}

// ══ TUI sparse en primary (Grok): sanear post-resize, no el shell ni Claude alt ══
{
  const M = F.marcarPintorTui;
  const D = F.debeSanearSparsePrimary;
  assert.strictEqual(typeof F.SPARSE_SANEAR_MS, 'number');
  assert.ok(F.SPARSE_SANEAR_MS > 0 && F.SPARSE_SANEAR_MS < 400,
    'cabe dentro de la cortina de resize (400ms)');

  const vacio = M(null, 'hello\n');
  assert.deepStrictEqual(vacio, { vioSync2026: false, vioAltScreen: false });
  const grok = M(vacio, 'x\x1b[?2026h\x1b[10;1Hhi\x1b[?2026l');
  assert.strictEqual(grok.vioSync2026, true);
  assert.strictEqual(grok.vioAltScreen, false);
  const grok2 = M(grok, 'more text');
  assert.strictEqual(grok2.vioSync2026, true, 'el flag se conserva');
  const claude = M(grok, '\x1b[?1049h');
  assert.strictEqual(claude.vioAltScreen, true);

  const vivo = { observador: false, wsAbierto: true };
  assert.strictEqual(D({ ...vivo, alt: false, vioSync2026: true, vioAltScreen: false }), true,
    'Grok: primary + 2026 sin alt → sanear (xterm refloweó el TUI)');
  assert.strictEqual(D({ ...vivo, alt: false, vioSync2026: false, vioAltScreen: false }), false,
    'bash: primary sin 2026 → el reflow del historial se queda');
  assert.strictEqual(D({ ...vivo, alt: true, vioSync2026: true, vioAltScreen: true }), false,
    'claude fullscreen: alt-screen, el watchdog de alt cubre');
  assert.strictEqual(D({ ...vivo, alt: false, vioSync2026: true, vioAltScreen: true }), false,
    'usó alt alguna vez: no es el pintor sparse de Grok');
  assert.strictEqual(D({ ...vivo, alt: false, vioSync2026: true, vioAltScreen: false, observador: true }), false,
    'QA observador no pide refresh');
  assert.strictEqual(D({ ...vivo, alt: false, vioSync2026: true, vioAltScreen: false, wsAbierto: false }), false);
  console.log('OK debeSanearSparsePrimary');
}

// ══ decidirBacklogOculto: freeze de ~10s al volver de minutos de idle ══
// (2026-07-12) Con la pestaña OCULTA el rAF está congelado → _flush nunca corre
// y _inbuf acumula sin drenar el goteo del failsafe FC_TIMEOUT (30s) del
// backend. Tras minutos de idle hay MB acumulados POR TERMINAL que al volver
// se parseaban de un saque en el main thread → app congelada ~10s. Decisión:
//   'acumular'  → comportamiento actual (visible, o idle corto bajo el cap)
//   'descartar' → vaciar _inbuf + ackear + marcar seed pendiente: al volver
//                 visible se pide reset+refresh (SEED completo, contrato
//                 2026-07-02) en vez de parsear el backlog.
{
  const D = F.decidirBacklogOculto;
  const CAP = F.CAP_BACKLOG_OCULTO;
  assert.strictEqual(typeof CAP, 'number');
  assert.ok(CAP >= 128 * 1024 && CAP <= 2 * 1024 * 1024, 'cap razonable: ni descarta alt-tabs triviales ni deja crecer MB');
  const base = { visible: true, inbufN: 0, seedPendiente: false, cap: 1000 };
  // Visible: acumular SIEMPRE — el camino caliente del tipeo no cambia en NADA.
  assert.strictEqual(D(base), 'acumular');
  assert.strictEqual(D({ ...base, inbufN: 999999 }), 'acumular');
  assert.strictEqual(D({ ...base, inbufN: 999999, seedPendiente: true }), 'acumular');
  // Oculta + poco backlog (alt-tab corto): acumular — cero regresión.
  assert.strictEqual(D({ ...base, visible: false, inbufN: 1000 }), 'acumular');
  // Oculta + backlog sobre el cap: descartar (primer overflow).
  assert.strictEqual(D({ ...base, visible: false, inbufN: 1001 }), 'descartar');
  // Oculta + seed ya pendiente: descartar TODO lo que siga llegando (no tiene
  // sentido re-acumular lo que el seed va a pisar).
  assert.strictEqual(D({ ...base, visible: false, inbufN: 1, seedPendiente: true }), 'descartar');
  // Sin cap explícito usa CAP_BACKLOG_OCULTO.
  assert.strictEqual(D({ visible: false, inbufN: CAP, seedPendiente: false }), 'acumular');
  assert.strictEqual(D({ visible: false, inbufN: CAP + 1, seedPendiente: false }), 'descartar');
  // Observador (?qa=1): JAMÁS descartar — el backend ignora su refresh (mismo
  // contrato que decidirRuedaAlt) y el reset dejaría la vista QA en blanco
  // permanente. Conserva el comportamiento histórico (acumular hasta la cota).
  assert.strictEqual(D({ ...base, visible: false, inbufN: 999999, observador: true }), 'acumular');
  assert.strictEqual(D({ ...base, visible: false, inbufN: 1, seedPendiente: true, observador: true }), 'acumular');
  console.log('OK decidirBacklogOculto');
}
