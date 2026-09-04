// JARVIS — Flow control del stream PTY→WS→xterm (séptima capa de
// [[tmux-size-clamping]]).
//
// xterm.js 5.3 DESCARTA datos ("write data discarded, use flow control")
// cuando su cola interna de write pasa 50MB. La cola se drena con cadenas de
// setTimeout(0) que Chrome estrangula en pestañas ocultas (1 tick/seg al
// ocultarse; 1 tick/MINUTO tras 5 min de intensive throttling) mientras los
// ws.onmessage siguen entregando a velocidad completa → con agentes
// trabajando la cola crece, cruza 50MB y se pierden chunks arbitrarios
// (secuencias ANSI cortadas al medio) → letras rotas / contenido multiplicado
// PERMANENTE hasta el F5 (tmux manda diffs: nunca repinta lo perdido).
//
// El fix: el browser confirma bytes YA PARSEADOS (callback de term.write →
// {'type':'ack','bytes':N}) y el backend frena la lectura del PTY cuando hay
// más de ~1MB sin confirmar. Acá vive la contabilidad pura del ack (testeada
// en Node); el wiring con el WS está en terminal.js.
(function (global) {
  'use strict';

  // Ack cada 64KB procesados: granularidad fina contra el watermark de 1MB
  // del backend (FC_HIGH en terminals.py), sin spamear el WS por cada chunk.
  const UMBRAL_ACK = 65536;

  // Acumulador de bytes parseados de UNA conexión WS. procesado(n) devuelve
  // 0 mientras no se llegue al umbral; al cruzarlo devuelve el total a ackear
  // y resetea. Entradas no-finitas o <= 0 se ignoran (defensivo).
  function crearContadorAck(umbral) {
    const u = (Number.isFinite(umbral) && umbral > 0) ? umbral : UMBRAL_ACK;
    let acumulado = 0;
    return {
      procesado(n) {
        if (!Number.isFinite(n) || n <= 0) return 0;
        acumulado += n;
        if (acumulado < u) return 0;
        const total = acumulado;
        acumulado = 0;
        return total;
      },
    };
  }

  // Ventana (ms) tras una tecla del usuario en la que un chunk entrante chico se
  // trata como ECO de lo que tipeó → se vuelca al instante en vez de esperar el
  // frame de rAF. Un eco normal vuelve en <50ms; 180ms cubre el round-trip
  // PTY→tmux→WS holgado sin pisar output no relacionado.
  const VENTANA_ECO_MS = 180;

  // Decide CÓMO drenar el buffer de entrada hacia xterm:
  //   true  → volcar YA por microtask (no esperar el frame).
  //   false → agendar para el próximo requestAnimationFrame (coalescing normal).
  // Reglas:
  //   - Tab OCULTA: SIEMPRE false. El rAF frenado por Chrome es la defensa que
  //     evita inflar la cola de 50MB de xterm (ver flow control). Jamás adelantar.
  //   - Tab visible + backlog grande (>= flushSize): true — drenar por tamaño para
  //     no acumular entre frames bajo flood (regla previa, preservada).
  //   - Tab visible + el usuario acaba de tipear (msDesdeInput < ventana): true —
  //     ECO interactivo: su tecla aparece sin esperar el frame. Dormido durante
  //     floods (ahí no está tipeando) → no altera la protección de la cola.
  function decidirDrenado({ inbufN, flushSize, visible, msDesdeInput, ventanaEcoMs }) {
    if (!visible) return false;
    if (inbufN >= flushSize) return true;
    const v = Number.isFinite(ventanaEcoMs) ? ventanaEcoMs : VENTANA_ECO_MS;
    return Number.isFinite(msDesdeInput) && msDesdeInput >= 0 && msDesdeInput < v;
  }

  // ── Rueda proporcional con velocidad (pedido del usuario 2026-07-02) ──
  // Convierte un WheelEvent en LÍNEAS de scroll (float, con signo). El caller
  // ACUMULA la fracción entre eventos y aplica el entero → un trackpad de deltas
  // finos no pierde movimiento y un mouse clásico rinde FACTOR× por notch.
  // deltaMode: 0=píxeles (÷18 ≈ altura de línea), 1=líneas, 2=páginas.
  const FACTOR_RUEDA = 3;          // velocidad normal (antes ~1× y con throttle que comía eventos)
  const FACTOR_RUEDA_TURBO = 15;   // con Alt apretado (fastScrollModifier)
  function lineasDeRueda({ deltaY, deltaMode, rows, turbo }) {
    if (!Number.isFinite(deltaY)) return 0;
    const base = deltaMode === 1 ? deltaY
               : deltaMode === 2 ? deltaY * rows
               : deltaY / 18;
    return base * (turbo ? FACTOR_RUEDA_TURBO : FACTOR_RUEDA);
  }


  // ── Decisión de reconexión al cerrarse el WS de una terminal ──
  // (auditoría 2026-07-02) Dos correcciones en una:
  //  · recargando=true (el updater ya decidió recargar la página, o llegó un
  //    boot_id nuevo): NO auto-reintentar — el reload hace el attach definitivo.
  //    Antes ambos caminos corrían en paralelo y cada terminal attacheaba DOS
  //    veces por reinicio del server (churn + ventana de duplicación del seed).
  //  · código 4010 (contrato con el backend: otra vista dueña tomó el control
  //    de la sesión): overlay especial SIN auto-retry — reintentar solo armaría
  //    un ping-pong de desplazamientos entre las dos ventanas.
  // Devuelve: 'nada' | 'desplazado' | 'programar' | 'overlay'.
  const CODIGO_DESPLAZADO = 4010;
  // 4404 = el motor está sano y dice que esa sesión ya NO existe (su proceso
  // terminó). Reintentar es imposible por definición, y el overlay de
  // reconexión miente: promete que "el agente sigue trabajando" cuando el
  // agente se fue. Cierre honesto, sin auto-retry.
  const CODIGO_TERMINADA = 4404;
  function decidirReintento({ cerrando, codigo, recargando, autoIntento, maxAuto }) {
    if (cerrando) return 'nada';
    if (codigo === CODIGO_DESPLAZADO) return 'desplazado';
    if (codigo === CODIGO_TERMINADA) return 'terminada';
    if (recargando) return 'nada';
    const max = Number.isFinite(maxAuto) ? maxAuto : 3;
    return ((autoIntento | 0) < max) ? 'programar' : 'overlay';
  }

  // ── Rueda sobre ALT-SCREEN: ¿app, auto-curación o nada? (2026-07-11) ──
  // En alternate el scroll es de la APP (claude fullscreen scrollea su
  // transcript vía mouse-tracking). Pero si el mouse-tracking de xterm quedó
  // INACTIVO (seed degradado: la captura del attach no re-enunció los modos),
  // la rueda se cedía a una app que jamás la recibía → SCROLL MUERTO en esa
  // terminal hasta el próximo redraw ("una terminal random no scrollea y
  // revive al mandarle un mensaje"). Acá se detecta el desacople y se
  // auto-cura: 'heal' = reset + refresh (el re-seed trae la verdad de tmux y
  // re-enuncia alt-screen + modos de mouse). Rate-limit HEAL_RUEDA_MS para no
  // re-seedear en loop si la app legítimamente no trackea el mouse (less/vim
  // sin mouse: su rueda no hace nada, igual que en cualquier terminal). Jamás
  // curar desde un observador (?qa=1): el backend ignora su refresh y el
  // reset lo dejaría en blanco.
  const HEAL_RUEDA_MS = 10000;

  function decidirRuedaAlt({ mouseActivo, wsAbierto, observador, msDesdeHeal }) {
    if (mouseActivo) return 'app';
    if (observador || !wsAbierto) return 'nada';
    return (msDesdeHeal >= HEAL_RUEDA_MS) ? 'heal' : 'nada';
  }

  // ── Backlog en pestaña OCULTA: descartar + seed en vez de parsear MB (2026-07-12) ──
  // Con la pestaña oculta el rAF está congelado → _flush nunca corre y _inbuf
  // acumula sin drenar (el failsafe FC_TIMEOUT=30s del backend gotea bytes
  // aunque no haya acks). Tras minutos de idle: MB por terminal que al volver
  // se parseaban de un SAQUE en el main thread → app congelada ~10s ("vuelvo y
  // no responde"). La cota dura de 8MB solo cubría el caso extremo.
  // Decisión pura: sobre el cap (o con seed ya pendiente), 'descartar' — el
  // caller vacía _inbuf, ackea lo descartado (contabilidad del flow control
  // intacta) y al volver visible pide reset+refresh (SEED completo, contrato
  // 2026-07-02) en vez del backlog. Visible: 'acumular' SIEMPRE — el camino
  // caliente del tipeo no cambia en nada; idle corto bajo el cap: tampoco.
  const CAP_BACKLOG_OCULTO = 512 * 1024;

  // Observador (?qa=1): JAMÁS descartar — el backend ignora su refresh (mismo
  // contrato que decidirRuedaAlt) y el reset dejaría la vista QA en blanco.
  function decidirBacklogOculto({ visible, inbufN, seedPendiente, cap, observador }) {
    if (visible || observador) return 'acumular';
    if (seedPendiente) return 'descartar';
    const c = (Number.isFinite(cap) && cap > 0) ? cap : CAP_BACKLOG_OCULTO;
    return (inbufN > c) ? 'descartar' : 'acumular';
  }

  // ── Retención de frames DEC 2026 abiertos (fix "franjas negras", 2026-07-08) ──
  // claude fullscreen envuelve cada redraw en \x1b[?2026h ... \x1b[?2026l
  // (synchronized output; medido: 67 frames/8s vía pipe-pane). xterm 5.3 NO
  // implementa 2026 — ignora los marcadores y pinta lo que haya al momento del
  // flush. Un frame grande (scroll / redraw post-resize, decenas de KB) llega
  // troceado por tmux/WS: si el flush cae a MITAD de frame se pinta medio
  // redraw → franjas NEGRAS que "después se llenan"; y si la app queda idle
  // tras el último trozo, el medio-frame PERSISTE (negro al salir de
  // fullscreen). cortarFrameSync parte el buffer pendiente en:
  //   listo → se pinta YA (todo lo anterior al primer frame sin cerrar)
  //   resto → queda en _inbuf esperando el \x1b[?2026l (el caller arma una
  //           válvula: hold vencido o resto gigante → forzar:true suelta todo).
  // También retiene una cola que sea PREFIJO de un marcador (marcador partido
  // entre chunks WS): el próximo chunk resuelve; costo = 1 flush de retraso.
  const MARCA_SYNC_H = '\x1b[?2026h';
  const MARCA_SYNC_L = '\x1b[?2026l';
  // ── Guard de CURSOR (fix "parpadeo del dot al tipear", 2026-07-17) ──
  // claude ≥2.1.214 YA NO emite 2026 (0 marcadores medidos en los logs de
  // stream de 3 terminales vivas) — la retención de arriba quedó inerte. Pero
  // cada redraw sigue siendo `\x1b[?25l …repintado… \x1b[?25h` y, con
  // full-repaint por tecla (12-43 mensajes WS por redraw), el flush caía
  // ENTRE el hide y el show → frames pintados con el cursor APAGADO
  // alternando con frames con cursor → el parpadeo. Mismo tratamiento que un
  // frame 2026: el hide ABRE un frame, el show lo CIERRA. Una app que
  // esconde el cursor A PROPÓSITO por períodos largos no se rompe: las
  // válvulas del caller (hold 150ms / cap 2MB / sequía 1s) sueltan igual.
  const MARCA_HIDE = '\x1b[?25l';
  const MARCA_SHOW = '\x1b[?25h';
  const _MARCAS = [MARCA_SYNC_H, MARCA_SYNC_L, MARCA_HIDE, MARCA_SHOW];
  const _PREFIJO_MAX = MARCA_SYNC_H.length - 1;   // cola ambigua más larga posible

  // Primer `abre` DESPUÉS del último `cierra` = arranque del frame abierto
  // (los frames no se anidan; ante un doble-abre malformado retiene desde el
  // primero: jamás se pinta un frame a medias).
  function _aperturaSinCierre(buf, abre, cierra) {
    const ultimoCierre = buf.lastIndexOf(cierra);
    return buf.indexOf(abre, ultimoCierre === -1 ? 0 : ultimoCierre + 1);
  }

  function cortarFrameSync(buf, opts) {
    if (typeof buf !== 'string' || buf === '') return { listo: buf || '', resto: '' };
    if (opts && opts.forzar) return { listo: buf, resto: '' };
    const abierto2026 = _aperturaSinCierre(buf, MARCA_SYNC_H, MARCA_SYNC_L);
    const abiertoCursor = _aperturaSinCierre(buf, MARCA_HIDE, MARCA_SHOW);
    let corte = abierto2026;
    if (abiertoCursor !== -1 && (corte === -1 || abiertoCursor < corte)) corte = abiertoCursor;
    if (corte !== -1) return { listo: buf.slice(0, corte), resto: buf.slice(corte) };
    // ¿La cola es un marcador PARTIDO? (termina en un prefijo de alguna marca:
    // \x1b[?2026[h|l] o \x1b[?25[l|h] — el próximo chunk resuelve cuál era).
    const maxCola = Math.min(_PREFIJO_MAX, buf.length);
    for (let k = maxCola; k >= 1; k--) {
      const cola = buf.slice(buf.length - k);
      // Prefijo PROPIO (más corto que la marca): una marca completa al final
      // del buffer no es ambigua — ya la resolvió la lógica de apertura/cierre.
      if (_MARCAS.some(m => m.length > k && m.startsWith(cola))) {
        return { listo: buf.slice(0, buf.length - k), resto: cola };
      }
    }
    return { listo: buf, resto: '' };
  }

  const api = { UMBRAL_ACK, VENTANA_ECO_MS, FACTOR_RUEDA, FACTOR_RUEDA_TURBO,
                CODIGO_DESPLAZADO, CODIGO_TERMINADA,
                MARCA_SYNC_H, MARCA_SYNC_L, HEAL_RUEDA_MS,
                MARCA_HIDE, MARCA_SHOW, CAP_BACKLOG_OCULTO,
                crearContadorAck, decidirDrenado, lineasDeRueda,
                decidirReintento, decidirRuedaAlt, cortarFrameSync,
                decidirBacklogOculto };
  global.TerminalFlow = Object.assign(global.TerminalFlow || {}, api);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
