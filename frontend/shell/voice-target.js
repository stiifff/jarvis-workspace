'use strict';
// ─── Destino de la voz: a quién le va el dictado ────────────────────────────
// Lógica PURA (sin DOM) de "¿a qué terminal —o a Jarvis— va este dictado?".
// El cableado a los eventos reales (hover, click, foco) vive en workspace.js.
// Patrón UMD _pure, testeable en Node.
//
// Regla de oro (pedido 2026-07-23): el MOUSE apunta. Tener el cursor sobre una
// terminal alcanza para hablarle — no hace falta clickearla. El destino se
// congela al arrancar la grabación (_activeVoiceSession en workspace.js), así
// que mover el mouse mientras dictás NUNCA desvía el mensaje en curso.

(function (root) {

  // Cuánto hay que quedarse sobre una terminal para que quede APUNTADA al
  // salir el cursor. Cruzarla de paso no deja residuo; apoyarse encima sí.
  // (El hover en curso vale desde el primer milisegundo — ver `hover` abajo:
  //  esto es solo para lo que queda pegado DESPUÉS de irse.)
  const HOVER_DWELL_MS = 200;

  // Entradas (todas ya resueltas por el caller, sin tocar el DOM acá):
  //   proyectoAbierto — hay workspace abierto (el chat necesita project_id)
  //   jarvisVisible   — el dock está abierto en la pestaña 'jarvis'
  //   fijado          — último destino apuntado (click o hover con dwell)
  //   hover           — qué hay bajo el cursor AHORA: {type:'terminal',id} |
  //                     {type:'jarvis'} | null
  //   terminales      — ids de las terminales vivas
  //   activaId        — id de la terminal marcada `.activa` (última clickeada)
  //   focoJarvis      — el foco del teclado está en el composer de Jarvis
  // Devuelve el destino o null (sin destino: el caller avisa y no graba).
  function resolverDestinoVoz({ proyectoAbierto, jarvisVisible, fijado, hover,
                                terminales, activaId, focoJarvis }) {
    if (!proyectoAbierto) return null;
    const vivas = Array.isArray(terminales) ? terminales : [];
    const vive  = (id) => id != null && vivas.includes(id);

    // 1. El cursor sobre una terminal MANDA, clickeada o no (vale desde el
    //    primer instante: apuntar y hablar tiene que ser inmediato). Gana
    //    incluso sobre el foco del composer, que es un estado pegajoso e
    //    invisible —pudiste haber clickeado el chat hace diez minutos— mientras
    //    que el mouse encima de la card es intención de AHORA. Y antes de soltar
    //    el PTT la píldora dice a quién le estás hablando.
    if (hover?.type === 'terminal' && vive(hover.id)) return { type: 'terminal', id: hover.id };

    // 2. Con el cursor fuera de toda terminal, escribir en el chat manda: el
    //    dictado anexa al texto que estás tipeando ahí.
    if (focoJarvis) return { type: 'jarvis' };
    if (hover?.type === 'jarvis') return { type: 'jarvis' };

    // 3. Sin cursor encima de nada: vale el último apuntado (click o dwell).
    if (fijado?.type === 'terminal' && vive(fijado.id)) return { type: 'terminal', id: fijado.id };

    // 4. Fijado en Jarvis (o terminal que murió). Con el chat a la vista, suyo.
    if (jarvisVisible) return { type: 'jarvis' };

    // 5. Jarvis oculto: la voz se la queda una terminal.
    if (vive(activaId)) return { type: 'terminal', id: activaId };
    // Pantalla de arranque (ninguna terminal): hablar al aire ES hablarle a
    // Jarvis — pedís "creame dos terminales" y el orquestador lo ejecuta sin
    // abrir el dock. `manosLibres` = el usuario no está mirando el chat.
    if (!vivas.length) return { type: 'jarvis', manosLibres: true };
    // Una sola terminal: no hay ambigüedad, es ella (antes pedía "seleccioná
    // una terminal" teniendo una sola en pantalla).
    if (vivas.length === 1) return { type: 'terminal', id: vivas[0] };
    // Varias y ninguna referencia: sin destino (el caller avisa).
    return null;
  }

  const api = { resolverDestinoVoz, HOVER_DWELL_MS };
  api._pure = api;

  root.VoiceTarget = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;

})(typeof window !== 'undefined' ? window : globalThis);
