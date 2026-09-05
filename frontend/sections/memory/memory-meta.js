'use strict';
// ─── Memoria: lógica pura de metadatos ───────────────────────────────────────
// SIN DOM (patrón UMD _pure, como live-state.js): badges de estado
// (lápida/obsoleta/lección), sublínea de la lista y resumen de salud del
// linter. memory.js la consume; los tests corren en Node.

(function (root) {

  const _t = (s) => (root.JarvisI18n && root.JarvisI18n.t) ? root.JarvisI18n.t(s) : s;

  // Badges visuales de una memoria: estado no-vigente primero, después la
  // marca de lección (tags [leccion] = regla de prevención del enjambre).
  function badges(m) {
    const out = [];
    const estado = ((m && m.estado) || 'vigente').toLowerCase();
    if (estado === 'lapida')   out.push({ k: 'lapida',   label: 'lápida' });
    if (estado === 'obsoleta') out.push({ k: 'obsoleta', label: 'obsoleta' });
    if (((m && m.tags) || []).some(t => String(t).toLowerCase() === 'leccion')) {
      out.push({ k: 'leccion', label: 'lección' });
    }
    return out;
  }

  // "autor · fecha · N links" — la fecha viva es actualizado (si existe) con
  // el prefijo "act." para distinguir frescura de creación.
  function subLinea(m) {
    m = m || {};
    const partes = [m.autor || '—'];
    if (m.actualizado) partes.push(_t('act. {f}').replace('{f}', m.actualizado));
    else if (m.creado) partes.push(m.creado);
    const n = (m.links || []).length;
    if (n) partes.push(n + ' link' + (n !== 1 ? 's' : ''));
    return partes.join(' · ');
  }

  // Contadores no-cero del endpoint /memory/salud → [{k, n}] para el strip.
  // Incluye los chequeos de las capas de coherencia y endurecimiento.
  function problemasSalud(salud) {
    if (!salud) return [];
    const out = [];
    const push = (k, n) => { if (n) out.push({ k: k, n: n }); };
    push('rotos', (salud.rotos || []).length);
    push('citas', (salud.citas_muertas || []).length);
    push('huerfanas', (salud.huerfanas || []).length);
    push('contrato', (salud.contrato || []).length);
    push('choques', (salud.choques || []).length);
    push('cuarentena', (salud.cuarentena || []).length);
    push('guard', (salud.candidatas_guard || []).length);
    push('duplicados', (salud.duplicados || []).length);
    push('global', (salud.candidatas_global || []).length);
    return out;
  }

  // Línea compacta del loop de lecciones (o null si el backend no lo trae):
  // cuántas reglas están siempre-cargadas y si el destilador API está trabado
  // (señales sobre el umbral sin API key = alerta — nada de degradar en silencio).
  function estadoLecciones(salud) {
    const l = (salud && salud.lecciones) || null;
    if (!l || !Object.keys(l).length) return null;
    const partes = [];
    partes.push(_t('{n} lecciones cargadas').replace('{n}', l.lecciones_memoria || 0));
    const sen = l.senales_pendientes || 0;
    const umb = l.umbral || 0;
    let alerta = false;
    if (!l.activo) {
      partes.push(_t('destilador OFF'));
    } else if (!l.api_ok && sen >= umb && umb > 0) {
      partes.push(_t('destilador trabado: {n}/{m} señales, sin API key').replace('{n}', sen).replace('{m}', umb));
      alerta = true;
    } else {
      partes.push(_t('destilador: {n}/{m} señales').replace('{n}', sen).replace('{m}', umb));
    }
    return { texto: partes.join(' · '), alerta: alerta };
  }

  // Salud desglosada por categoría → filas SOLO de las que tienen problemas,
  // ordenadas por cantidad de problemas desc (el cuadro más sucio arriba).
  function categoriasSalud(salud) {
    const por = (salud && salud.por_categoria) || {};
    const filas = [];
    for (const cid of Object.keys(por)) {
      const c = por[cid];
      const problemas = (c.rotos || 0) + (c.citas_muertas || 0) +
                        (c.huerfanas || 0) + (c.contrato || 0);
      if (problemas) filas.push({ id: cid, nombre: c.nombre || cid, total: c.total || 0, problemas: problemas });
    }
    filas.sort((a, b) => b.problemas - a.problemas || a.nombre.localeCompare(b.nombre));
    return filas;
  }

  // Altímetro (7 días): ¿el recall rinde? inyectadas vs leídas de verdad
  // (según el cierre de los agentes) y cuántas lecturas fueron en pasos OK.
  // null mientras no hay datos (rodaje): una línea de ceros solo mete ruido.
  function altimetro(salud) {
    const a = (salud && salud.altimetro) || null;
    if (!a || !Object.keys(a).length) return null;
    const iny = a.inyecciones || 0;
    const lec = a.lecturas || 0;
    if (!iny && !lec) return null;
    const partes = [_t('{d}d: {n} inyectadas').replace('{d}', a.dias || 7).replace('{n}', iny)];
    let leidas = (a.tasa_lectura !== null && a.tasa_lectura !== undefined)
      ? _t('{n} leídas ({p}%)').replace('{n}', lec).replace('{p}', Math.round(a.tasa_lectura * 100))
      : _t('{n} leídas').replace('{n}', lec);
    partes.push(leidas);
    partes.push(_t('{n} en pasos OK').replace('{n}', a.lecturas_en_done || 0));
    return { texto: _t('Altímetro') + ' ' + partes.join(' · ') };
  }

  const api = { badges, subLinea, problemasSalud, categoriasSalud, estadoLecciones, altimetro };
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.JarvisMemoryMeta = api;

}(typeof self !== 'undefined' ? self : this));
