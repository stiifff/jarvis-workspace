// Tests de la lógica pura de JarvisUpdater (updater.js).
'use strict';
const assert = require('assert');
require('../updater.js');
const { debeMostrar, etiquetaBanner, lineaVersion, esHotfix, etiquetaVersionNueva,
        mostrarVersion, debeAvisarCaida, textosCaida, estadoBanner, lineaAlDia,
        debeAvisarLoop, novedadesFaltantes, novedadesTraducidas,
        novedadesRender, planAplicar, decidirRecargaReady,
        decidirOverlayPostReload, tilesOverlay } = globalThis.JarvisUpdater._pure;

// debeMostrar: solo con hay_update true
assert.strictEqual(debeMostrar({ hay_update: true }), true);
assert.strictEqual(debeMostrar({ hay_update: false }), false);
assert.strictEqual(debeMostrar({}), false);
assert.strictEqual(debeMostrar(null), false);

// etiquetaBanner: texto fijo, simple, no depende de la versión
assert.strictEqual(etiquetaBanner('4.1.0'), 'Actualizar ahora');
assert.strictEqual(etiquetaBanner(), 'Actualizar ahora');

// lineaVersion: con update pendiente muestra el salto "v1.5.08 → v1.5.09";
// sin transición conocida cae a "Jarvis vX.Y.Z"; vacío si no hay versión
assert.strictEqual(lineaVersion({ corriendo: '1.5.08', proxima: '1.5.09' }), 'v1.5.08 → v1.5.09');
assert.strictEqual(lineaVersion({ corriendo: '1.5.1', proxima: '1.5.1.1' }), 'v1.5.1 → v1.5.1.1');
assert.strictEqual(lineaVersion({ corriendo: '1.5.08', proxima: '1.5.08' }), 'Jarvis v1.5.08');
assert.strictEqual(lineaVersion({ disponible: '1.5.1' }), 'Jarvis v1.5.1');   // server viejo sin 'proxima'
assert.strictEqual(lineaVersion({ disponible: '' }), '');
assert.strictEqual(lineaVersion({}), '');
assert.strictEqual(lineaVersion(null), '');

// mostrarVersion: una minor REDONDA (patch y hotfix en cero, 1.7.00 / 1.7.00.0)
// se muestra corta como 1.7; apenas sube cualquier segmento, completa como viene
// (pedido del usuario 2026-07-07). Solo afecta el display, no el VERSION interno.
assert.strictEqual(mostrarVersion('1.7.00'), '1.7');        // minor redonda → corta
assert.strictEqual(mostrarVersion('1.7.00.0'), '1.7');      // con 4º segmento en cero, igual
assert.strictEqual(mostrarVersion('1.6.00'), '1.6');
assert.strictEqual(mostrarVersion('1.7.01'), '1.7.01');     // patch subió → completa
assert.strictEqual(mostrarVersion('1.7.00.1'), '1.7.00.1'); // hotfix sobre la redonda → completa
assert.strictEqual(mostrarVersion('1.6.97.3'), '1.6.97.3'); // hotfix normal → intacta
assert.strictEqual(mostrarVersion('1.5'), '1.5');           // ya corta → intacta
assert.strictEqual(mostrarVersion(''), '');
assert.strictEqual(mostrarVersion(null), '');
// y se refleja en lo que se MUESTRA (chip, salto de versión, al-día, badge):
assert.strictEqual(lineaVersion({ corriendo: '1.6.99', proxima: '1.7.00' }), 'v1.6.99 → v1.7');
assert.strictEqual(lineaAlDia({ corriendo: '1.7.00' }), 'Jarvis v1.7');
assert.strictEqual(etiquetaVersionNueva('1.7.00'), 'v1.7');

// estadoBanner: 'update' (burbuja con glow) | 'aldia' (píldora con la versión
// corriente) | 'oculto' (sin info, o server viejo sin 'corriendo')
assert.strictEqual(estadoBanner({ hay_update: true,  corriendo: '1.5.1' }), 'update');
assert.strictEqual(estadoBanner({ hay_update: true }), 'update');
assert.strictEqual(estadoBanner({ hay_update: false, corriendo: '1.5.1' }), 'aldia');
assert.strictEqual(estadoBanner({ hay_update: false }), 'oculto');
assert.strictEqual(estadoBanner({}), 'oculto');
assert.strictEqual(estadoBanner(null), 'oculto');

// estadoBanner ya NO mira agentes_trabajando: el gate vive en el backend, que
// pone hay_update=true SOLO cuando hay un commit nuevo (una tarea TERMINADA y
// commiteada). Así el banner aparece apenas una terminal commitea lo suyo,
// aunque otra terminal de Jarvis siga trabajando (pedido del usuario 2026-06-18).
assert.strictEqual(estadoBanner({ hay_update: true, agentes_trabajando: true, corriendo: '1.5.1' }), 'update');
assert.strictEqual(estadoBanner({ hay_update: true, agentes_trabajando: false, corriendo: '1.5.1' }), 'update');
assert.strictEqual(estadoBanner({ hay_update: false, agentes_trabajando: true, corriendo: '1.5.1' }), 'aldia');

// lineaAlDia: la versión en la que estás, visible aun sin update pendiente
assert.strictEqual(lineaAlDia({ corriendo: '1.5.1' }), 'Jarvis v1.5.1');
assert.strictEqual(lineaAlDia({ corriendo: '' }), '');
assert.strictEqual(lineaAlDia({}), '');
assert.strictEqual(lineaAlDia(null), '');

// esHotfix: 4º segmento = hotfix de esa versión
assert.strictEqual(esHotfix('1.5.1.1'), true);
assert.strictEqual(esHotfix('1.5.1'), false);
assert.strictEqual(esHotfix(''), false);
assert.strictEqual(esHotfix(undefined), false);

// etiquetaVersionNueva: badge del modal — los hotfixes se anuncian como tales
assert.strictEqual(etiquetaVersionNueva('1.5.1'), 'v1.5.1');
assert.strictEqual(etiquetaVersionNueva('1.5.1.1'), 'v1.5.1.1 · hotfix');
assert.strictEqual(etiquetaVersionNueva(''), '');

// debeAvisarCaida: solo si el health falló Y no hay otro overlay encima
// (el flujo de Actualizar del usuario tiene prioridad — no duplicar)
assert.strictEqual(debeAvisarCaida(false, false), true);   // caído, sin overlay → avisar
assert.strictEqual(debeAvisarCaida(false, true),  false);  // health OK → blip del WS, nada
assert.strictEqual(debeAvisarCaida(true,  false), false);  // ya hay overlay (Actualizar) → nada
assert.strictEqual(debeAvisarCaida(true,  true),  false);

// textosCaida: mensaje neutro del aviso de reinicio (los agentes ya no
// reinician el server — el reinicio lo dispara el usuario o Jarvis mismo)
const t = textosCaida();
assert.strictEqual(t.titulo, 'El servidor se está reiniciando');
assert.ok(t.sub.includes('recarga sola'));

// debeAvisarLoop: el server quedó en uvloop (stall del event loop → cortes de
// tipeo) → banner para reiniciar a asyncio. PERO si ya hay un update pendiente,
// NO se duplica: el botón "Actualizar ahora" ya reinicia con --loop asyncio.
assert.strictEqual(debeAvisarLoop({ loop_degradado: true,  hay_update: false }), true);
assert.strictEqual(debeAvisarLoop({ loop_degradado: true,  hay_update: true  }), false);
assert.strictEqual(debeAvisarLoop({ loop_degradado: false, hay_update: false }), false);
assert.strictEqual(debeAvisarLoop({ loop_degradado: true }), true);   // sin update → avisar
assert.strictEqual(debeAvisarLoop({}), false);
assert.strictEqual(debeAvisarLoop(null), false);

// ── Novedades en inglés (los ítems son texto libre de commits: no los cubre el
//    diccionario i18n, se traducen vía red y se cachean por texto normalizado) ──

// novedadesFaltantes: solo los que NO están en la cache, únicos y sin vacíos.
// Es lo único que se manda a la red (ahorra llamadas al re-abrir el modal).
assert.deepStrictEqual(
  novedadesFaltantes(['Arreglé el login', 'Nuevo dock'], {}),
  ['Arreglé el login', 'Nuevo dock']);
assert.deepStrictEqual(
  novedadesFaltantes(['Arreglé el login', 'Nuevo dock'], { 'Arreglé el login': 'Fixed login' }),
  ['Nuevo dock']);
// Duplicados (misma novedad en dos áreas) se piden una sola vez; normaliza espacios.
assert.deepStrictEqual(
  novedadesFaltantes(['Dock nuevo', 'Dock  nuevo', '  Dock nuevo  '], {}),
  ['Dock nuevo']);
// Vacíos / null se ignoran; lista rara no rompe.
assert.deepStrictEqual(novedadesFaltantes(['', '  ', null], {}), []);
assert.deepStrictEqual(novedadesFaltantes(null, {}), []);
assert.deepStrictEqual(novedadesFaltantes(['x'], null), ['x']);

// novedadesTraducidas: cada ítem → su traducción cacheada, o el ORIGINAL si falta
// (degradación elegante: sin red, la novedad queda en español).
assert.deepStrictEqual(
  novedadesTraducidas(['Nuevo dock', 'Sin traducir'], { 'Nuevo dock': 'New dock' }),
  ['New dock', 'Sin traducir']);
assert.deepStrictEqual(novedadesTraducidas(['Nuevo dock'], {}), ['Nuevo dock']);
assert.deepStrictEqual(novedadesTraducidas(null, {}), []);
// Preserva el orden y usa el texto normalizado como clave.
assert.deepStrictEqual(
  novedadesTraducidas(['  Dock  nuevo  '], { 'Dock nuevo': 'New dock' }),
  ['New dock']);

// novedadesRender: texto del PRIMER render (mata el flash). En inglés = traducción
// cacheada (o el original si aún no está); en español = SIEMPRE el original, aunque
// haya traducción en la cache. Preserva orden y longitud (1:1 con items).
assert.deepStrictEqual(
  novedadesRender(['Nuevo dock', 'Sin traducir'], { 'Nuevo dock': 'New dock' }, 'en'),
  ['New dock', 'Sin traducir']);
// Español: el original aunque la traducción exista en la cache.
assert.deepStrictEqual(
  novedadesRender(['Nuevo dock'], { 'Nuevo dock': 'New dock' }, 'es'),
  ['Nuevo dock']);
// Cache fría en inglés → cae al original (después lo completa la red sin flash extra).
assert.deepStrictEqual(novedadesRender(['Nuevo dock'], {}, 'en'), ['Nuevo dock']);
// Robustez: lista vacía / null no rompe.
assert.deepStrictEqual(novedadesRender(null, {}, 'en'), []);
assert.deepStrictEqual(novedadesRender([], {}, 'es'), []);

// planAplicar: qué hace falta para aplicar. Con update = restart del server;
// sin update (o sin info) = nada. El botón nunca queda inerte.
assert.deepStrictEqual(planAplicar({ hay_update: true }), { server: true });
assert.deepStrictEqual(planAplicar({ hay_update: false }), { server: false });
assert.deepStrictEqual(planAplicar(null), { server: false });

// decidirRecargaReady: gate del reload post-update. El frontend NO recarga apenas
// el server acepta conexiones (health=200 / boot_id nuevo) sino cuando terminó de
// reconciliar las sesiones tmux (/api/system/ready → {ready}). Recargar antes = la
// página fresca re-attachea las N terminales contra un tmux todavía arrancando →
// cards negras + scroll muerto. Devuelve 'recargar' | 'esperar' | 'rendirse'.
// Solo ready===true recarga:
assert.strictEqual(decidirRecargaReady({ ready: true }, 1, 120), 'recargar');
assert.strictEqual(decidirRecargaReady({ ready: true }, 119, 120), 'recargar');
// ready false = server vivo pero todavía reconciliando → esperar:
assert.strictEqual(decidirRecargaReady({ ready: false }, 1, 120), 'esperar');
// server caído (fetch falló → resp null) → esperar (todavía re-execando):
assert.strictEqual(decidirRecargaReady(null, 1, 120), 'esperar');
// respuesta rara sin el campo → esperar (no recargar a ciegas):
assert.strictEqual(decidirRecargaReady({}, 5, 120), 'esperar');
assert.strictEqual(decidirRecargaReady({ ready: 'sí' }, 5, 120), 'esperar');
// pasado el tope de intentos SIN estar listo → rendirse (fail-open: el usuario
// recarga a mano; nunca dejar la página en un loop infinito):
assert.strictEqual(decidirRecargaReady({ ready: false }, 121, 120), 'rendirse');
assert.strictEqual(decidirRecargaReady(null, 121, 120), 'rendirse');
// pero si YA está listo, recargar gana aunque se haya pasado el tope:
assert.strictEqual(decidirRecargaReady({ ready: true }, 200, 120), 'recargar');
// 4º argumento (2026-08-08): SALUD sostenida. El gate era fail-CERRADO: solo
// ready===true recargaba, así que un `ready` que nunca vira (reconcile colgado,
// semáforo inaccesible) dejaba al usuario DOS MINUTOS detrás del overlay
// "Actualizando…" con el server ya de vuelta y andando (reporte del usuario:
// "entro 25s y me salta eso, no puedo usar el workspace"). Ahora, con el server
// contestando /api/health de forma sostenida, se recarga igual: llegar tarde a
// la reconciliación es un mal MENOR que una pantalla secuestrada — y el overlay
// post-reload ya espera a que la cola de attaches drene.
assert.strictEqual(decidirRecargaReady({ ready: false }, 40, 120, 30), 'recargar');
assert.strictEqual(decidirRecargaReady(null, 40, 120, 30), 'recargar');
// pero NO antes: unos pocos pings sanos son el server recién levantado, no una
// reconciliación colgada — ahí se sigue esperando el ready de verdad.
assert.strictEqual(decidirRecargaReady({ ready: false }, 40, 120, 29), 'esperar');
assert.strictEqual(decidirRecargaReady({ ready: false }, 40, 120, 0), 'esperar');
// sin medición (wiring viejo / server caído) → exactamente como antes:
assert.strictEqual(decidirRecargaReady({ ready: false }, 40, 120), 'esperar');
assert.strictEqual(decidirRecargaReady({ ready: false }, 40, 120, null), 'esperar');

// (debeOfrecerSalida y el botón "Seguir usando Jarvis" se eliminaron el
// 2026-08-08 a pedido del usuario: el cartel de caída ya no bloquea — es un
// aviso flotante — así que no necesita salida.)

// decidirOverlayPostReload: tras el reload del update, el overlay "Actualizando…"
// SIGUE tapando el workspace hasta que la cola de attaches drenó (los seeds ya
// se aplicaron) — así el trabajo pesado pasa DENTRO del overlay y al levantarse
// todo responde (antes: workspace visible pero congelado 3-5s). estado = el
// estado() de TerminalAttach ({pendientes, activos, usada}) o null si el módulo
// no cargó. Devuelve 'mantener' | 'ocultar'.
// Cola usada y drenada (attaches terminados) → ocultar recién tras un SETTLE
// sostenido (drenadaMs ≥ 1200): el drenado marca "llegaron los seeds", pero el
// parseo + el asentamiento del server post-restart siguen unos instantes — si
// el overlay se levanta en el drenado pelado, el primer scroll cae en la
// tormenta y se siente muerto (reporte del usuario 2026-07-11). Piso 800ms de
// vida total para que no parpadee.
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 0, usada: true }, 2200, 1300), 'ocultar');
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 0, usada: true }, 2200, 400), 'mantener');   // drenó hace poco: settle
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 0, usada: true }, 300, 1300), 'mantener');   // piso de vida total
// 4º argumento (2026-07-11): pings RÁPIDOS consecutivos a /api/health — mide la
// respuesta REAL del server recién re-ejecutado (la misma cola de eventos que
// relaya la rueda). El settle fijo de 1.2s se levantaba en plena tormenta y el
// primer scroll caía muerto unos segundos (reporte del usuario):
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 0, usada: true }, 2200, 1300, 3), 'ocultar');    // server responde: levantar
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 0, usada: true }, 2200, 1300, 0), 'mantener');   // ¡EL BUG!: settle cumplido pero server aún ahogado
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 0, usada: true }, 2200, 1300, 2), 'mantener');   // todavía no sostenido
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 0, usada: true }, 2200, 1300, null), 'ocultar'); // sin medición (wiring viejo): como antes
// Tope de gracia: si los pings NUNCA se ponen rápidos (caja bajo carga crónica
// del enjambre), a los 5s de drenado se levanta igual — taparlo más no ayuda:
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 0, usada: true }, 7000, 5100, 0), 'ocultar');
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 0, usada: true }, 7000, 4000, 0), 'mantener');
// Attaches todavía en vuelo o esperando → mantener (drenadaMs no corre):
assert.strictEqual(decidirOverlayPostReload({ pendientes: 3, activos: 2, usada: true }, 5000, 0), 'mantener');
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 1, usada: true }, 5000, 0), 'mantener');
// Cola nunca usada (proyecto sin terminales / cards que tardan en crearse):
// esperar un poco más (2.5s) y ocultar:
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 0, usada: false }, 1000, 0), 'mantener');
assert.strictEqual(decidirOverlayPostReload({ pendientes: 0, activos: 0, usada: false }, 2600, 0), 'ocultar');
// Módulo ausente (cache vieja): mismo trato que cola sin usar:
assert.strictEqual(decidirOverlayPostReload(null, 1000, 0), 'mantener');
assert.strictEqual(decidirOverlayPostReload(null, 2600, 0), 'ocultar');
// Failsafe duro: pase lo que pase, a los 12s el overlay se levanta (jamás una
// página secuestrada por un attach colgado):
assert.strictEqual(decidirOverlayPostReload({ pendientes: 9, activos: 2, usada: true }, 12001, 0), 'ocultar');

// tilesOverlay: los mini-terminales del overlay post-reload — uno por attach,
// en orden listas ('on') → conectando ('run') → esperando (''), con contador
// "hechos/total" (numerales puros: sin i18n). Cap en 12 (MAX_TERMINALES).
assert.deepStrictEqual(
  tilesOverlay({ pendientes: 2, activos: 2, usada: true, hechos: 1 }),
  { tiles: ['on', 'run', 'run', '', ''], texto: '1/5' });
assert.deepStrictEqual(
  tilesOverlay({ pendientes: 0, activos: 0, usada: true, hechos: 4 }),
  { tiles: ['on', 'on', 'on', 'on'], texto: '4/4' });
// Sin attaches todavía (o módulo ausente): sin tiles ni contador.
assert.deepStrictEqual(tilesOverlay({ pendientes: 0, activos: 0, usada: false, hechos: 0 }),
  { tiles: [], texto: '' });
assert.deepStrictEqual(tilesOverlay(null), { tiles: [], texto: '' });
// Cap defensivo en 12 tiles (el contador sigue diciendo la verdad).
const _t = tilesOverlay({ pendientes: 20, activos: 2, usada: true, hechos: 8 });
assert.strictEqual(_t.tiles.length, 12);
assert.strictEqual(_t.texto, '8/30');

console.log('updater: OK');
