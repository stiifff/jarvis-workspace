/* Bienvenida: qué agentes tenés y cuáles te podemos instalar.
 *
 * POR QUÉ EXISTE
 * ==============
 * Jarvis daba por hecho que los CLIs estaban: abría la terminal y tipeaba
 * `claude`. En la máquina de alguien que acaba de instalar la app, eso muestra
 * una terminal negra con `command not found` — la primera impresión de todo
 * usuario nuevo.
 *
 * CUÁNDO APARECE
 * ==============
 * SOLO cuando no hay ningún agente instalado. Quien ya tiene los suyos no
 * necesita que le expliquemos nada: ve su console y arranca. Una pantalla de
 * bienvenida que aparece siempre es una pantalla que se aprende a cerrar sin
 * leer.
 *
 * Módulo UMD como el resto: la lógica pura se testea en Node sin DOM.
 */
(function (global) {
  'use strict';

  /** ¿Hay algo que decir? Solo si NO hay ningún agente. */
  function debeMostrarse(estado) {
    return !!(estado && Array.isArray(estado.clis) && estado.clis.length &&
              !estado.clis.some(c => c.instalado));
  }

  /** Qué acción ofrece cada agente. Nunca un botón que no pueda cumplir. */
  function accionDe(cli, hayNode) {
    if (!cli) return 'nada';
    if (cli.instalado) return 'listo';
    if (!cli.instalable) return 'aparte';   // Antigravity: app de escritorio
    if (!hayNode) return 'sin-node';        // sin npm no hay nada que prometer
    return 'instalar';
  }

  const pure = { debeMostrarse, accionDe };
  global.Bienvenida = Object.assign(global.Bienvenida || {}, { _pure: pure, ...pure });

  if (typeof document === 'undefined') return;

  const TEXTOS = {
    listo:      { etiqueta: 'listo',              accionable: false },
    aparte:     { etiqueta: 'se instala aparte',  accionable: false },
    'sin-node': { etiqueta: 'necesita Node',      accionable: false },
    instalar:   { etiqueta: 'Instalar',           accionable: true },
  };

  let _el = null;

  function _construir() {
    _el = document.createElement('section');
    _el.className = 'bv';
    _el.hidden = true;
    _el.innerHTML = `
      <h2 class="bv-titulo">Traé tus propios agentes.</h2>
      <p class="bv-texto">
        Jarvis los orquesta; la inferencia corre en <b>tus</b> cuentas.
        Esto es lo que encontramos en el sistema:
      </p>
      <ul class="bv-lista"></ul>
      <p class="bv-pie"></p>`;
    const ancla = document.getElementById('hc-empty') || document.querySelector('main');
    if (ancla && ancla.parentNode) ancla.parentNode.insertBefore(_el, ancla);
  }

  function _pintar(estado) {
    const lista = _el.querySelector('.bv-lista');
    lista.innerHTML = estado.clis.map(c => {
      const accion = accionDe(c, estado.hay_node);
      const t = TEXTOS[accion] || TEXTOS.listo;
      const marca = c.instalado ? '✓' : '·';
      return `<li class="bv-item${c.instalado ? ' on' : ''}">
          <span class="bv-marca" aria-hidden="true">${marca}</span>
          <span class="bv-nombre">${c.nombre}</span>
          ${t.accionable
            ? `<button class="bv-btn" type="button" data-cli="${c.id}">${t.etiqueta}</button>`
            : `<span class="bv-estado">${t.etiqueta}</span>`}
        </li>`;
    }).join('');
    _el.querySelector('.bv-pie').textContent = estado.hay_node
      ? 'Después de instalarlo, iniciá sesión corriéndolo una vez en una terminal.'
      : 'Sin Node instalado no podemos instalarlos por vos.';

    lista.querySelectorAll('.bv-btn').forEach(b => {
      b.addEventListener('click', () => _instalar(b));
    });
  }

  async function _instalar(boton) {
    const id = boton.dataset.cli;
    boton.disabled = true;
    boton.textContent = 'Instalando…';
    try {
      const r = await fetch(`/api/clis/${encodeURIComponent(id)}/instalar`, { method: 'POST' });
      const d = await r.json().catch(() => ({}));
      if (r.ok && d.ok) {
        boton.replaceWith(Object.assign(document.createElement('span'),
          { className: 'bv-estado', textContent: 'listo' }));
        return;
      }
      // El error de npm va TAL CUAL: quien ve esto acaba de instalar la app y
      // no tiene nada más para orientarse.
      boton.disabled = false;
      boton.textContent = 'Reintentar';
      if (global.toast) toast(d.salida || d.detail || 'No se pudo instalar', 'error');
    } catch (e) {
      boton.disabled = false;
      boton.textContent = 'Reintentar';
      if (global.toast) toast((window.JarvisI18n.t('No se pudo instalar: {msg}') || 'No se pudo instalar: {msg}').replace('{msg}', e.message), 'error');
    }
  }

  async function init() {
    let estado;
    try {
      const r = await fetch('/api/clis');
      if (!r.ok) return;
      estado = await r.json();
    } catch { return; }             // sin datos, no se muestra nada: la home
    if (!debeMostrarse(estado)) return;   // funciona igual sin esto
    if (!_el) _construir();
    _pintar(estado);
    _el.hidden = false;
  }

  global.Bienvenida.init = init;
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : globalThis);
