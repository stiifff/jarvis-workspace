/* ════════════════════════════════════════════════════════════════
   Sampler del Mobile Studio — corre DENTRO de la app del usuario.

   Lo inyecta el endpoint /api/mobile-preview/{id}/sampler ANTES del <base>
   (así este src relativo resuelve contra Jarvis). Corre en la app VISIBLE de
   cada teléfono: reporta el color de fondo real de CADA pantalla en vivo —
   navegación incluida — para que el workspace pinte la franja del status bar
   y la del home indicator como el aparato real.

   Lecciones aprendidas acá (2026-07-11, app real del usuario):
   1. Un bundle de Metro tarda SEGUNDOS en pintar → muestreo gateado por
      contenido montado (one-shot reportaba el blanco vacío).
   2. El <base> hacia Metro hace que expo-router pase URLs de :8081 a
      history.* (SecurityError) y que el HMR intente WS contra Jarvis (403):
      esos errores abren el LOGBOX de Expo (header coral + cuerpo negro) que
      TAPA la app. Por eso los parches de history/WebSocket, ANTES del bundle.
      El WS se RE-APUNTA a Metro (no se anula): el hot reload sigue vivo.
   3. expo-router lee location.pathname como ruta → reescribimos la URL a la
      ruta real (?ruta=) o renderiza su 404 negro.
   4. FUENTES: el browser exige CORS para @font-face cross-origin y Metro no
      manda ACAO → la app caía a serif. Se reescriben las url() de los <style>
      con @font-face hacia el proxy same-origin /asset de Jarvis.
   5. Fondos con GRADIENTE: backgroundColor transparente + background-image →
      se extraen los stops (primero arriba, último abajo).
   Solo LEE estilos computados y solo parchea DENTRO de esta página.
═══════════════════════════════════════════════════════════════ */
(() => {
  'use strict';
  // Marca same-origin: el workspace la lee en el load del iframe para saber
  // que lo cargado ES el espejo instrumentado (y no una página de Jarvis).
  window.__mpsSampler = true;
  // Origen de Jarvis: el src de ESTE script (resuelto antes del <base>).
  let ORIGEN = '*';
  try { ORIGEN = new URL(document.currentScript.src).origin; } catch { /* '*' */ }
  // Base de la API del proyecto — capturada ANTES de reescribir la URL (parche 3).
  const API_BASE = location.pathname.replace(/\/sampler$/, '');
  const metroOrigen = () => { try { return new URL(document.baseURI).origin; } catch { return null; } };

  // Muestreo INSTANTÁNEO: navegación o mutación visual → tick al frame
  // siguiente. Leading+trailing: durante una transición animada (mutaciones
  // sostenidas) tickea cada ~120ms — el color ACOMPAÑA la animación en vez de
  // esperar a que termine. Declarado ACÁ arriba: el parche 3 ya lo usa.
  let _deb = null, _ultimoTick = 0;
  function pronto() {
    const ahora = Date.now();
    if (ahora - _ultimoTick > 120) { _ultimoTick = ahora; requestAnimationFrame(tick); }
    clearTimeout(_deb);
    _deb = setTimeout(() => { _ultimoTick = Date.now(); requestAnimationFrame(tick); }, 90);
  }

  // ── Parche 1: history seguro. expo-router resuelve rutas contra el <base>
  // (:8081) y history.* con URL cross-origin TIRA SecurityError → LogBox.
  ['pushState', 'replaceState'].forEach((m) => {
    const orig = history[m].bind(history);
    history[m] = function (st, tt, url) {
      try {
        if (url != null) {
          const u = new URL(String(url), location.href);
          if (u.origin !== location.origin) url = u.pathname + u.search + u.hash;
        }
        const r = orig(st, tt, url);
        pronto();   // navegación → muestrear YA (color de la pantalla nueva)
        return r;
      } catch {
        try { return orig(st, tt); } catch { /* estado sin URL tampoco anduvo */ }
      }
    };
  });
  window.addEventListener('popstate', () => pronto());

  // ── Parche 2: WebSockets del HMR re-apuntados a METRO. Con el <base>, el
  // cliente de Metro arma ws:// contra el origen de Jarvis (fallaba 403 y el
  // spam abría el LogBox). El hot reload importa: se reescribe al host real
  // de Metro — verificado que Metro acepta WS cross-origin.
  const WSNativo = window.WebSocket;
  window.WebSocket = function (url, protos) {
    try {
      const u = new URL(String(url), location.href);
      if (u.host === location.host) {
        const base = new URL(document.baseURI);   // <base> = origen de Metro
        if (base.host !== location.host) {
          u.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
          u.host = base.host;
          return new WSNativo(u.href, protos);
        }
      }
    } catch { /* URL rara → nativo */ }
    return new WSNativo(url, protos);
  };
  window.WebSocket.prototype = WSNativo.prototype;
  ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'].forEach((k, i) => { window.WebSocket[k] = i; });

  // ── Parche 3: la ruta de la app. Esta página vive en /api/mobile-preview/…
  // y expo-router lee location.pathname como ruta inicial → renderizaba su 404
  // negro ("Unmatched Route") y el sampler muestreaba ESO. Reescribimos la URL
  // a la ruta real (viene en ?ruta=) ANTES de que cargue el bundle.
  try {
    const ruta = new URLSearchParams(location.search).get('ruta') || '/';
    if (ruta.charAt(0) === '/' && ruta.charAt(1) !== '/') history.replaceState(null, '', ruta);
  } catch { /* la app caerá en su not-found y el fondo igual se muestrea */ }

  // ── Parche 4: FUENTES same-origin. Las url() de @font-face que apuntan a
  // Metro se reescriben al proxy /asset de Jarvis (CORS resuelto). Idempotente:
  // tras reescribir, las url() ya no apuntan a Metro y no se vuelven a tocar.
  const URL_CSS_RE = /url\(\s*(['"]?)([^)'"]+)\1\s*\)/g;
  function reescribirUrlsCss(txt) {
    const mo = metroOrigen();
    if (!mo || mo === location.origin) return txt;
    return txt.replace(URL_CSS_RE, (todo, q, u) => {
      let abs;
      try { abs = new URL(u, document.baseURI).href; } catch { return todo; }
      if (abs.indexOf(mo + '/') !== 0) return todo;   // externas (CDNs): quedan
      // ABSOLUTA hacia Jarvis: una url relativa resolvería contra el <base>
      // (Metro) → 404 y además re-entraba al rewrite anidándose (bug real).
      return `url("${location.origin}${API_BASE}/asset?u=${encodeURIComponent(abs)}")`;
    });
  }
  function procesarStyle(el) {
    if (!el || el.tagName !== 'STYLE') return;
    const t = el.textContent || '';
    if (t.indexOf('@font-face') === -1 || t.indexOf('url(') === -1) return;
    const nuevo = reescribirUrlsCss(t);
    if (nuevo !== t) el.textContent = nuevo;
  }
  // FontFace API por las dudas (expo-font puede usarla directo).
  const FFNativo = window.FontFace;
  if (FFNativo) {
    window.FontFace = function (fam, src, desc) {
      if (typeof src === 'string') src = reescribirUrlsCss(src);
      return new FFNativo(fam, src, desc);
    };
    window.FontFace.prototype = FFNativo.prototype;
  }

  // ── Parche 5: los FULL RELOADS no escapan a Jarvis. El parche 3 dejó la URL
  // del documento en la ruta de la app (p.ej. "/"), así que un reload completo
  // (HMR de Metro que no puede aplicar el update, `r` en la terminal de Metro,
  // location.reload() de la app) recarga ESA ruta contra el origen de Jarvis →
  // el dashboard adentro del teléfono (bug real 2026-07-17). location.reload
  // no es parcheable (Location es no-configurable), pero beforeunload avisa al
  // arrancar CUALQUIER navegación de descarga: el workspace la cancela
  // re-apuntando el iframe al espejo instrumentado con la ruta actual.
  // pagehide queda de red de seguridad (si beforeunload no corrió); el aviso
  // duplicado es inocuo (el workspace suprime por timestamp).
  const _bye = () => {
    try {
      window.parent.postMessage({
        tipo: 'mps-sampler-bye',
        ruta: location.pathname + location.search + location.hash,
      }, ORIGEN);
    } catch { /* sin parent no hay a quién avisar */ }
  };
  window.addEventListener('beforeunload', _bye);
  window.addEventListener('pagehide', _bye);

  const TRANSPARENTE = /^rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*0(?:\.0+)?\s*\)$|^transparent$/i;

  // Color pintado de una capa: backgroundColor sólido, o el stop del gradiente
  // ('inicio' para la franja de arriba, 'fin' para la de abajo).
  function colorDeCapa(cs, extremo) {
    const c = cs.backgroundColor;
    if (c && !TRANSPARENTE.test(c)) return c;
    const bi = cs.backgroundImage || '';
    if (bi.indexOf('gradient') !== -1) {
      const stops = bi.match(/rgba?\([^)]*\)|#[0-9a-f]{3,8}/gi);
      if (stops && stops.length) return extremo === 'fin' ? stops[stops.length - 1] : stops[0];
    }
    return null;
  }

  // Fondo EFECTIVO en un punto: la capa más profunda que pinte algo (subiendo
  // por ancestros); si nadie pinta, body/html o blanco (canvas default).
  function fondoEn(x, y, extremo) {
    let el = null;
    try { el = document.elementFromPoint(x, y); } catch { /* doc raro */ }
    while (el) {
      const c = colorDeCapa(getComputedStyle(el), extremo);
      if (c) return c;
      el = el.parentElement;
    }
    for (const raiz of [document.body, document.documentElement]) {
      if (!raiz) continue;
      const c = colorDeCapa(getComputedStyle(raiz), extremo);
      if (c) return c;
    }
    return 'rgb(255, 255, 255)';
  }

  // ¿La app YA montó contenido real? (React tarda; el HTML llega vacío y
  // muestrear ahí devuelve el blanco default → color equivocado pintado.)
  function contenidoListo() {
    const raiz = document.getElementById('root') || document.body;
    return !!(raiz && raiz.childElementCount > 0 && raiz.scrollHeight > 40);
  }

  // Si el fondo de la pantalla es un GRADIENTE que cubre (casi) todo el
  // viewport, se manda el gradiente ENTERO: el workspace lo pinta detrás del
  // teléfono a pantalla completa y las franjas del status bar / home son la
  // CONTINUACIÓN real del degradado (un color plano "congela" el gradiente —
  // feedback del usuario). Un gradiente chico (una card) NO representa el
  // fondo → null. Capas sólidas por encima → null (manda el color sólido).
  function gradienteViewport() {
    const w = window.innerWidth || 393, h = window.innerHeight || 852;
    let el = null;
    try { el = document.elementFromPoint(w / 2, Math.min(40, h / 4)); } catch { return null; }
    while (el) {
      const cs = getComputedStyle(el);
      const bi = cs.backgroundImage || '';
      if (bi.indexOf('gradient') !== -1 && bi.indexOf('url(') === -1) {
        const r = el.getBoundingClientRect();
        return (r.width >= w * 0.8 && r.height >= h * 0.8) ? bi : null;
      }
      if (cs.backgroundColor && !TRANSPARENTE.test(cs.backgroundColor)) return null;
      el = el.parentElement;
    }
    return null;
  }

  function muestra() {
    const w = window.innerWidth || 393, h = window.innerHeight || 852;
    return {
      tipo: 'mps-sampler',
      top: fondoEn(w / 2, 6, 'inicio'),
      topIzq: fondoEn(12, 6, 'inicio'),
      topDer: fondoEn(w - 12, 6, 'inicio'),
      bottom: fondoEn(w / 2, h - 8, 'fin'),
      bottomIzq: fondoEn(12, h - 8, 'fin'),
      bottomDer: fondoEn(w - 12, h - 8, 'fin'),
      grad: gradienteViewport(),
    };
  }

  let ultimo = null;
  function tick() {
    if (!document.body || !contenidoListo()) return;
    const m = muestra();
    const k = m.top + '|' + m.topIzq + '|' + m.topDer + '|' + m.bottom + '|' + m.bottomIzq + '|' + m.bottomDer + '|' + m.grad;
    if (k === ultimo) return;
    ultimo = k;
    window.parent.postMessage(m, ORIGEN);
  }

  // Un solo observer: reescritura de fuentes (styles nuevos) + gatillo de
  // muestreo por mutación visual (tick solo postea si el color CAMBIÓ, así
  // el costo de los disparos redundantes es cero).
  new MutationObserver((ms) => {
    for (const m of ms) {
      if (m.type === 'childList') {
        m.addedNodes.forEach((n) => {
          procesarStyle(n);
          if (n.querySelectorAll) n.querySelectorAll('style').forEach(procesarStyle);
        });
      } else if (m.type === 'characterData' && m.target.parentElement) {
        procesarStyle(m.target.parentElement);
      }
    }
    pronto();
  }).observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['style', 'class'] });

  // Red de seguridad: tick permanente cada 500ms (vive lo que vive la app).
  setInterval(tick, 500);
})();
