'use strict';
// ─── Agents Live: lógica pura del estado de la pestaña ──────────────────────
// SIN DOM (patrón UMD _pure, como preview-tabs.js): recibe snapshots del
// backend (REST inicial + WS live_update/permiso_*/conflicto_archivo, todos
// llevan snapshot completo) y mantiene flashes de actividad para la UI.
//
// estado = { agentes, permisos, actividad, flashes: {path → tsMs} }

(function (root) {

  const FLASH_MS = 2000; // un chip destella 2s tras detectarse una op

  function crearEstado() {
    return { agentes: [], permisos: [], actividad: [], flashes: {}, _visto: null };
  }

  // Total de ops por path del snapshot anterior (para diffear qué flashea).
  function _firmas(agentes) {
    const f = {};
    for (const a of agentes || []) {
      for (const x of a.archivos || []) {
        f[x.path] = (f[x.path] || 0) + x.reads + x.writes;
      }
    }
    return f;
  }

  // Reemplaza el estado con un snapshot nuevo. Lo que subió de ops (o
  // apareció) flashea — salvo en la PRIMERA foto (carga inicial).
  function aplicarSnapshot(estado, snap, ahora) {
    // Copia podando los vencidos: el dict no crece para siempre en sesiones largas.
    const flashes = {};
    for (const p in estado.flashes) {
      if (ahora - estado.flashes[p] < FLASH_MS) flashes[p] = estado.flashes[p];
    }
    if (estado._visto) {
      const nuevas = _firmas(snap.agentes);
      for (const path in nuevas) {
        if (nuevas[path] > (estado._visto[path] || 0)) flashes[path] = ahora;
      }
    }
    return {
      agentes: snap.agentes || [],
      permisos: snap.permisos || [],
      actividad: snap.actividad || [],
      flashes,
      _visto: _firmas(snap.agentes),
    };
  }

  function flashesVigentes(estado, ahora) {
    return Object.keys(estado.flashes).filter(p => ahora - estado.flashes[p] < FLASH_MS);
  }

  // Trabajando primero; estable por nombre dentro de cada grupo.
  function ordenarAgentes(agentes) {
    return [...(agentes || [])].sort((a, b) => {
      const t = (b.estado === 'trabajando') - (a.estado === 'trabajando');
      return t !== 0 ? t : a.nombre.localeCompare(b.nombre);
    });
  }

  function hace(s) {
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    return `${Math.floor(s / 3600)}h`;
  }

  const api = { FLASH_MS, crearEstado, aplicarSnapshot, flashesVigentes, ordenarAgentes, hace };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.JarvisLiveState = api;

})(typeof window !== 'undefined' ? window : globalThis);
