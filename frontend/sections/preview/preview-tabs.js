'use strict';
// ─── Web Preview: lógica pura de pestañas ────────────────────────────────────
// Máquina de estados de las pestañas del browser embebido. SIN DOM: todas las
// funciones reciben un estado y devuelven uno nuevo (inmutable), testeables en
// Node (patrón UMD _pure, igual que el dock). El render vive en preview.js.
//
// estado = { tabs: [{ id, url, titulo, stack, idx }], activaId, nextId }
//   - stack/idx: historial propio de CADA pestaña (como el _stack/_idx viejo)
//   - url null = pestaña "nueva" (muestra el estado empty)

(function (root) {

  const MAX_TABS = 8; // cada iframe vivo consume memoria; conviven con 9 xterm

  function crearEstado() {
    return { tabs: [], activaId: null, nextId: 1 };
  }

  function _buscar(estado, id) {
    return estado.tabs.find((t) => t.id === id) || null;
  }

  function _reemplazar(estado, tab) {
    return { ...estado, tabs: estado.tabs.map((t) => (t.id === tab.id ? tab : t)) };
  }

  // Abre una pestaña (url null = vacía) y la deja activa.
  // Devuelve { estado, error } — error 'max' si se pasó del tope (estado igual).
  function abrirTab(estado, url = null) {
    if (estado.tabs.length >= MAX_TABS) return { estado, error: 'max' };
    const tab = {
      id: estado.nextId,
      url: url || null,
      titulo: null,
      stack: url ? [url] : [],
      idx: url ? 0 : -1,
    };
    return {
      estado: { tabs: estado.tabs.concat([tab]), activaId: tab.id, nextId: estado.nextId + 1 },
      error: null,
    };
  }

  // Cierra una pestaña. Si era la activa, activa la vecina de la DERECHA
  // (la que ocupa su lugar), si no hay, la de la izquierda; si no queda
  // ninguna, activaId null (estado empty).
  function cerrarTab(estado, id) {
    const i = estado.tabs.findIndex((t) => t.id === id);
    if (i === -1) return estado;
    const tabs = estado.tabs.slice(0, i).concat(estado.tabs.slice(i + 1));
    let activaId = estado.activaId;
    if (activaId === id) {
      const vecina = tabs[i] || tabs[i - 1] || null;
      activaId = vecina ? vecina.id : null;
    }
    return { tabs, activaId, nextId: estado.nextId };
  }

  function activarTab(estado, id) {
    if (!_buscar(estado, id)) return estado;
    return { ...estado, activaId: id };
  }

  function tabActiva(estado) {
    return _buscar(estado, estado.activaId);
  }

  // Navega la pestaña a url. push=true apila en su historial (truncando los
  // "adelante" si veníamos del medio); push=false solo cambia url (back/fwd).
  function navegarTab(estado, id, url, push = true) {
    const tab = _buscar(estado, id);
    if (!tab || !url) return estado;
    let { stack, idx } = tab;
    if (push) {
      stack = stack.slice(0, idx + 1);
      if (stack[idx] !== url) { stack = stack.concat([url]); idx = stack.length - 1; }
    }
    return _reemplazar(estado, { ...tab, url, stack, idx });
  }

  function atrasTab(estado, id) {
    const tab = _buscar(estado, id);
    if (!tab || tab.idx <= 0) return estado;
    const idx = tab.idx - 1;
    return _reemplazar(estado, { ...tab, idx, url: tab.stack[idx] });
  }

  function adelanteTab(estado, id) {
    const tab = _buscar(estado, id);
    if (!tab || tab.idx >= tab.stack.length - 1) return estado;
    const idx = tab.idx + 1;
    return _reemplazar(estado, { ...tab, idx, url: tab.stack[idx] });
  }

  function tituloTab(estado, id, titulo) {
    const tab = _buscar(estado, id);
    if (!tab) return estado;
    return _reemplazar(estado, { ...tab, titulo });
  }

  function encontrarPorUrl(estado, url) {
    const t = estado.tabs.find((t) => t.url === url);
    return t ? t.id : null;
  }

  // protocolo+host+puerto de una URL ('http://localhost:5173/app' →
  // 'http://localhost:5173'); null si no parsea.
  function _origen(url) {
    try { const u = new URL(url); return u.protocol + '//' + u.host; }
    catch { return null; }
  }

  // Igual que encontrarPorUrl pero por ORIGEN (mismo host:puerto): un dev
  // server que se reinicia por un cambio de diseño vuelve con la misma URL
  // base aunque el usuario haya navegado adentro (…/about) → reusamos SU
  // pestaña en vez de abrir una nueva. Devuelve el id o null.
  function encontrarPorOrigen(estado, url) {
    const o = _origen(url);
    if (!o) return null;
    const t = estado.tabs.find((t) => t.url && _origen(t.url) === o);
    return t ? t.id : null;
  }

  // CLAVE de reuso de pestaña. Un dev server real se identifica por su ORIGEN
  // (host:puerto): un restart o navegar adentro (…/about) reusa SU pestaña. PERO
  // los demos servidos por el PROPIO Jarvis comparten origen (localhost:3000) —
  // son `:3000/static/<dir>/…` — así que ahí la identidad es la CARPETA del demo.
  // Sin esta distinción, con varios agentes el demo de uno EVICTABA el del otro
  // (todos matcheaban por el origen :3000 → una sola pestaña que se navegaba
  // sola; bug "una pestaña le quita la del otro", 2026-07-12). `jarvisHost` =
  // host:puerto del propio workspace (location.host); sin él, todo va por origen.
  function claveReuso(url, jarvisHost) {
    let u;
    try { u = new URL(url); } catch { return null; }
    const origen = u.protocol + '//' + u.host;
    if (jarvisHost && u.host === jarvisHost && u.pathname.startsWith('/static/')) {
      const dir = u.pathname.slice('/static/'.length).split('/')[0];
      if (dir) return origen + '/static/' + dir;   // demo → por carpeta
    }
    return origen;                                   // dev server real → por origen
  }

  // Como encontrarPorOrigen pero con la clave de reuso (demos por carpeta): cada
  // agente conserva SU pestaña. Lo usan el salto al localhost del agente y el menú.
  function encontrarPorReuso(estado, url, jarvisHost) {
    const k = claveReuso(url, jarvisHost);
    if (!k) return null;
    const t = estado.tabs.find((t) => t.url && claveReuso(t.url, jarvisHost) === k);
    return t ? t.id : null;
  }

  // Mueve la pestaña `id` al índice `destino` (drag & drop de la fila).
  // Clampa el destino al rango; id inexistente o misma posición → estado
  // intacto (misma referencia). activaId no cambia (se activa por id).
  function moverTab(estado, id, destino) {
    const i = estado.tabs.findIndex((t) => t.id === id);
    if (i === -1) return estado;
    const d = Math.max(0, Math.min(estado.tabs.length - 1, Math.trunc(destino)));
    if (d === i) return estado;
    const tabs = estado.tabs.slice();
    const [tab] = tabs.splice(i, 1);
    tabs.splice(d, 0, tab);
    return { ...estado, tabs };
  }

  // A qué índice cae la pestaña arrastrada (índice final del array — lo que
  // espera moverTab). rects = [{left, width}] medidos al ARRANCAR el drag.
  //
  // EAGER: el swap dispara apenas el borde DELANTERO de la arrastrada invade
  // DRAG_FRACCION del vecino — no hace falta cruzarlo entero (con pestañas de
  // ~150px, exigir el centro se sentía como arrastrar "hasta el final").
  // HISTÉRESIS (`prev` = destino anterior, null al arrancar): des-cruzar un
  // límite ya cruzado pide DRAG_HISTERESIS px extra — sin eso, el temblor del
  // mouse justo en el borde hace flickear el reorden ida y vuelta.
  const DRAG_FRACCION = 0.35;
  const DRAG_HISTERESIS = 8; // px

  function destinoDrag(rects, idx, dx, prev = null) {
    const izq = rects[idx].left + dx;                  // borde izquierdo actual
    const der = izq + rects[idx].width;                // borde derecho actual
    let destino = idx;
    // Vecinos a la DERECHA (en orden): cada uno invadido corre el destino +1.
    for (let j = idx + 1; j < rects.length; j++) {
      let limite = rects[j].left + rects[j].width * DRAG_FRACCION;
      if (prev != null && prev >= j) limite -= DRAG_HISTERESIS;
      if (der > limite) destino = j; else break;
    }
    if (destino > idx) return destino;
    // Vecinos a la IZQUIERDA, simétrico con el borde izquierdo.
    for (let j = idx - 1; j >= 0; j--) {
      let limite = rects[j].left + rects[j].width * (1 - DRAG_FRACCION);
      if (prev != null && prev <= j) limite += DRAG_HISTERESIS;
      if (izq < limite) destino = j; else break;
    }
    return destino;
  }

  // Cambio de proyecto SIN matar iframes: estaciona el pool del proyecto
  // saliente (sus iframes siguen vivos → la música/video no se corta al
  // pasear entre proyectos) y saca el del entrante si estaba estacionado.
  // El pool ({estado, vistas}) es OPACO acá — lo arma preview.js; esto solo
  // decide park/adopt. Devuelve { pools, pool } sin mutar la entrada:
  // pool = el del entrante (null → restaurar de localStorage).
  function cambiarProyecto(pools, pidSaliente, poolSaliente, pidEntrante) {
    const nuevos = { ...(pools || {}) };
    if (pidSaliente != null && poolSaliente) nuevos[pidSaliente] = poolSaliente;
    let pool = null;
    if (pidEntrante != null && nuevos[pidEntrante]) {
      pool = nuevos[pidEntrante];
      delete nuevos[pidEntrante];
    }
    return { pools: nuevos, pool };
  }

  // Persistencia (localStorage): solo urls + índice de la activa.
  // Los historiales por pestaña NO se persisten (YAGNI).
  function serializar(estado) {
    return {
      urls: estado.tabs.map((t) => t.url),
      activa: estado.tabs.findIndex((t) => t.id === estado.activaId),
    };
  }

  function deserializar(data) {
    let estado = crearEstado();
    if (!data || !Array.isArray(data.urls)) return estado;
    for (const url of data.urls.slice(0, MAX_TABS)) {
      estado = abrirTab(estado, typeof url === 'string' ? url : null).estado;
    }
    if (!estado.tabs.length) return estado;
    const i = (Number.isInteger(data.activa) && data.activa >= 0 && data.activa < estado.tabs.length)
      ? data.activa : estado.tabs.length - 1;
    return activarTab(estado, estado.tabs[i].id);
  }

  const _pure = {
    MAX_TABS, crearEstado, abrirTab, cerrarTab, activarTab, tabActiva,
    navegarTab, atrasTab, adelanteTab, tituloTab, encontrarPorUrl, encontrarPorOrigen,
    claveReuso, encontrarPorReuso,
    moverTab, destinoDrag, cambiarProyecto, serializar, deserializar,
  };

  root.WebPreviewTabs = { _pure };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.WebPreviewTabs;

})(typeof window !== 'undefined' ? window : globalThis);
