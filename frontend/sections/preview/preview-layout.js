'use strict';
// ─── Web Preview: lógica pura de layouts / split view ────────────────────────
// El browser embebido puede mostrar de 1 a 4 paneles a la vez (split), con
// varias disposiciones (columnas, filas, principal+N, grilla) — más una galería
// de "snap zones" para elegirlas. Esta es la máquina pura (SIN DOM): decide la
// cantidad de paneles, el `grid-template` CSS y QUÉ pestañas se ven en cada
// panel. El render (canvas + iframes visibles) vive en preview.js.
// Patrón UMD _pure, testeable en Node (igual que preview-tabs.js).
//
// Un layout = { id, label, panes, template }. `template` es el valor de la
// propiedad CSS `grid-template` (áreas a/b/c/d en orden de panel).

(function (root) {

  const LAYOUTS = [
    { id: '1',  label: 'Único',      panes: 1, template: '"a" 1fr / 1fr' },
    { id: '2c', label: '2 columnas', panes: 2, template: '"a b" 1fr / 1fr 1fr' },
    { id: '2r', label: '2 filas',    panes: 2, template: '"a" 1fr "b" 1fr / 1fr' },
    { id: '3c', label: '3 columnas', panes: 3, template: '"a b c" 1fr / 1fr 1fr 1fr' },      // 3 verticales
    { id: '3L', label: 'Principal',  panes: 3, template: '"a b" 1fr "a c" 1fr / 1.4fr 1fr' }, // principal + 2
    { id: '3T', label: '2 + ancho',  panes: 3, template: '"a b" 1fr "c c" 1fr / 1fr 1fr' },
    { id: '4',  label: 'Grilla',     panes: 4, template: '"a b" 1fr "c d" 1fr / 1fr 1fr' },
    { id: '4c', label: '4 columnas', panes: 4, template: '"a b c d" 1fr / 1fr 1fr 1fr 1fr' },
    { id: '4L', label: 'Prin. + 3',  panes: 4, template: '"a b" 1fr "a c" 1fr "a d" 1fr / 1.5fr 1fr' },
  ];

  const DEFAULT_LAYOUT = '1';

  function _byId(id) {
    return LAYOUTS.find((l) => l.id === id) || null;
  }

  // id válido → el mismo; cualquier otra cosa → '1' (nunca rompe el render).
  function normalizar(id) {
    return _byId(id) ? id : DEFAULT_LAYOUT;
  }

  function panesDe(id) {
    const l = _byId(id);
    return l ? l.panes : 1;
  }

  function template(id) {
    const l = _byId(id) || _byId(DEFAULT_LAYOUT);
    return l.template;
  }

  // Decide QUÉ pestañas se muestran en los `panes` paneles del split:
  // las primeras N en orden de la fila, rellenando con null si faltan. Si la
  // pestaña activa quedara fuera de la ventana visible, ocupa el último panel
  // (así el usuario nunca "pierde de vista" en qué estaba parado).
  // Devuelve un array de largo exactamente `panes` de tabId|null.
  function asignar(tabIds, panes, activaId = null) {
    const n = Math.max(1, Math.trunc(panes) || 1);
    const ids = Array.isArray(tabIds) ? tabIds.slice() : [];
    const vis = ids.slice(0, n);
    if (activaId != null && ids.includes(activaId) && !vis.includes(activaId) && vis.length) {
      vis[vis.length - 1] = activaId;
    }
    while (vis.length < n) vis.push(null);
    return vis;
  }

  const _pure = { LAYOUTS, DEFAULT_LAYOUT, normalizar, panesDe, template, asignar };

  root.WebPreviewLayout = { _pure };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.WebPreviewLayout;

})(typeof window !== 'undefined' ? window : globalThis);
