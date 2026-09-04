// JARVIS — Review Room (UI).
// VISOR de diff: lista de archivos cambiados + diff completo coloreado.
// (El "Aprobar y commitear" se quitó: hacía git add -A, prohibido por CLAUDE.md
// y bloqueado por el hook; cada agente commitea sus archivos explícitos.)
// Expone window.JarvisReview = { init, onProjectChanged, mostrarEnPane }.
// Task 26: migrado de overlay/modal a pane del dock (#jw-pane-review).

(() => {
  let _projectId = null;
  let _data = null;

  const esc = (s) => { const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML; };

  const _pane = () => document.getElementById('jw-pane-review');

  async function _cargar() {
    const r = await fetch(`/api/projects/${_projectId}/review`);
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(e.detail || `HTTP ${r.status}`);
    }
    _data = await r.json();
  }

  /* Render del diff unificado → líneas coloreadas + headers sticky por archivo */
  function _renderDiff(diff) {
    const out = [];
    for (const linea of diff.split('\n')) {
      if (linea.startsWith('diff --git')) {
        const path = (linea.split(' b/')[1] || '').trim();
        out.push(`</div><div class="rv-file-sec" data-i18n-skip data-path="${esc(path)}">`
          + `<div class="rv-file-head">`
          + `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 2.5h8l4 4V21a.5.5 0 0 1-.5.5h-11A.5.5 0 0 1 6 21V2.5zM14 2.5v4h4"/></svg>`
          + `${esc(path)}</div>`);
      } else if (linea.startsWith('+++') || linea.startsWith('---') || linea.startsWith('index ')
              || linea.startsWith('new file') || linea.startsWith('deleted file') || linea.startsWith('similarity')
              || linea.startsWith('rename ') || linea.startsWith('old mode') || linea.startsWith('new mode')) {
        out.push(`<div class="rv-linea meta">${esc(linea)}</div>`);
      } else if (linea.startsWith('@@')) {
        out.push(`<div class="rv-linea hunk">${esc(linea)}</div>`);
      } else if (linea.startsWith('+')) {
        out.push(`<div class="rv-linea add">${esc(linea)}</div>`);
      } else if (linea.startsWith('-')) {
        out.push(`<div class="rv-linea del">${esc(linea)}</div>`);
      } else {
        out.push(`<div class="rv-linea">${esc(linea)}</div>`);
      }
    }
    // El diff es CÓDIGO/contenido (no se traduce): el skip va en cada .rv-file-sec
    // (ver arriba), que SÍ contiene sus líneas — el wrapper de acá se cierra antes
    // por el </div> inicial de la 1ª sección, así que skipearlo a él no alcanzaba.
    return `<div>${out.join('')}</div>`;
  }

  function _render() {
    const ov = _pane();
    if (!ov || !_data) return;

    ov.querySelector('.rv-branch').innerHTML =
      `en <b>${esc(_data.branch || '?')}</b> · ${esc(_data.ultimo || '')}`;

    const lista = ov.querySelector('.rv-archivos');
    const diffCont = ov.querySelector('.rv-diff');

    if (_data.limpio) {
      lista.innerHTML = '';
      diffCont.innerHTML = `
        <div class="rv-vacio" style="display:flex;flex-direction:column;align-items:center;height:100%;justify-content:center">
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12.5l5 5L20 6.5"/></svg>
          <div>Working tree limpio.<br>No hay nada para revisar — todo está commiteado.</div>
        </div>`;
      return;
    }

    lista.innerHTML = _data.archivos.map((a, i) => `
      <button class="rv-archivo" data-path="${esc(a.path)}" style="--i:${Math.min(i, 16)}" title="${esc(a.path)}">
        <span class="rv-estado ${esc(a.estado)}">${esc(a.estado)}</span>
        <span class="rv-path">&lrm;${esc(a.path)}</span>
        <span class="rv-stat"><span class="mas">+${esc(a.mas)}</span> <span class="menos">−${esc(a.menos)}</span></span>
      </button>`).join('');

    diffCont.innerHTML = _renderDiff(_data.diff || '');

    lista.querySelectorAll('.rv-archivo').forEach(b =>
      b.addEventListener('click', () => {
        lista.querySelectorAll('.rv-archivo').forEach(x => x.classList.toggle('activo', x === b));
        diffCont.querySelector(`.rv-file-sec[data-path="${CSS.escape(b.dataset.path)}"]`)
          ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }));
  }

  function _montar() {
    const pane = _pane();
    if (!pane || pane.querySelector('.rv-modal')) return;   // ya montado
    pane.innerHTML = `
      <div class="rv-modal" role="region" aria-label="Review Room">
        <div class="rv-top">
          <span class="rv-titulo">Review.</span>
          <span class="rv-branch"></span>
          <span class="rv-spacer"></span>
          <button class="rv-refresh" type="button" title="Refrescar" aria-label="Refrescar">${icon('refresh', 13)}</button>
        </div>
        <div class="rv-body">
          <div class="rv-archivos"></div>
          <div class="rv-diff"><div class="rv-vacio">Cargando diff…</div></div>
        </div>
      </div>`;
    pane.querySelector('.rv-refresh').addEventListener('click', async () => {
      try { await _cargar(); _render(); } catch (e) { toast(e.message, 'error'); }
    });
  }

  async function mostrarEnPane() {
    _montar();
    const pane = _pane();
    if (!pane) return;
    pane.querySelector('.rv-diff').innerHTML = `<div class="rv-vacio">Cargando diff…</div>`;
    // Generation-guard: si cambian de proyecto durante el fetch, no pintar el diff viejo.
    const pid = _projectId;
    try { await _cargar(); if (pid !== _projectId) return; _render(); }
    catch (e) {
      pane.querySelector('.rv-diff').innerHTML =
        `<div class="rv-vacio">No se pudo cargar el review:<br>${esc(e.message)}</div>`;
    }
  }

  window.JarvisReview = {
    init(projectId) { _projectId = projectId; },
    onProjectChanged(projectId) {
      _projectId = projectId; _data = null;
      // si el pane está montado y visible, refrescar; si no, se recarga al abrir
      const pane = _pane();
      if (pane && !pane.hidden) mostrarEnPane();
    },
    mostrarEnPane,
  };
})();
