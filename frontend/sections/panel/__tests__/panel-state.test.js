'use strict';
// Tests de la lógica pura del Panel Único (dock). Estado:
//   { open, tab, width, maximized, badges:{tabId:n}, visible:{tabId:bool} }
// Corre con: node frontend/sections/panel/__tests__/panel-state.test.js
const assert = require('assert');
const D = require('../panel.js');
const { nextState, badgeTotal, clampWidth, resolveAgentWidth, resolveAgentTab, resolveAgentOpen } = D;

const base = () => ({
  open: false, tab: 'preview', width: 340, maximized: false,
  badges: {}, visible: { mobile: false },
});

// ── open / close / toggle ─────────────────────────────────────────
{
  let s = base();
  s = nextState(s, { type: 'open' });
  assert.strictEqual(s.open, true, 'open abre');
  assert.strictEqual(s.tab, 'preview', 'open sin tab respeta la tab actual');

  s = nextState(s, { type: 'open', tab: 'jarvis' });
  assert.strictEqual(s.tab, 'jarvis', 'open con tab cambia de pestaña');

  s = nextState(s, { type: 'close' });
  assert.strictEqual(s.open, false, 'close cierra');
  assert.strictEqual(s.maximized, false, 'close apaga maximizado');

  let t = nextState(base(), { type: 'toggle' });
  assert.strictEqual(t.open, true, 'toggle desde cerrado abre');
  t = nextState(t, { type: 'toggle' });
  assert.strictEqual(t.open, false, 'toggle desde abierto cierra');
}
console.log('OK open/close/toggle');

// ── setTab limpia el badge de la pestaña abierta ──────────────────
{
  let s = base();
  s.open = true;
  s.badges = { jarvis: 3, tasks: 2 };
  s = nextState(s, { type: 'setTab', tab: 'jarvis' });
  assert.strictEqual(s.tab, 'jarvis', 'setTab cambia la pestaña');
  assert.strictEqual(s.badges.jarvis, 0, 'setTab limpia el badge de la pestaña abierta');
  assert.strictEqual(s.badges.tasks, 2, 'setTab NO toca el badge de otras pestañas');
  // setTab también abre el dock si estaba cerrado
  let c = nextState(base(), { type: 'setTab', tab: 'editor' });
  assert.strictEqual(c.open, true, 'setTab abre el dock si estaba cerrado');
  assert.strictEqual(c.tab, 'editor', 'setTab fija la pestaña');
}
console.log('OK setTab');

// ── notify suma SOLO si la pestaña está inactiva (o el dock cerrado) ─
{
  let s = base(); s.open = true; s.tab = 'jarvis';
  // pestaña activa + dock abierto → NO suma
  s = nextState(s, { type: 'notify', tab: 'jarvis', n: 1 });
  assert.strictEqual(s.badges.jarvis || 0, 0, 'notify NO suma a la pestaña activa visible');
  // pestaña inactiva → suma
  s = nextState(s, { type: 'notify', tab: 'tasks', n: 1 });
  assert.strictEqual(s.badges.tasks, 1, 'notify suma a pestaña inactiva');
  s = nextState(s, { type: 'notify', tab: 'tasks', n: 2 });
  assert.strictEqual(s.badges.tasks, 3, 'notify acumula (default y explícito)');
  // dock cerrado → suma aunque sea la "tab" actual
  let c = base(); c.open = false; c.tab = 'jarvis';
  c = nextState(c, { type: 'notify', tab: 'jarvis', n: 1 });
  assert.strictEqual(c.badges.jarvis, 1, 'notify suma a la tab actual si el dock está cerrado');
  // notify con n por default = 1
  let d = base(); d.open = false;
  d = nextState(d, { type: 'notify', tab: 'review' });
  assert.strictEqual(d.badges.review, 1, 'notify default n=1');
}
console.log('OK notify');

// ── badgeTotal: suma de los badges de pestañas ────────────────────
{
  assert.strictEqual(badgeTotal({}), 0, 'badgeTotal vacío = 0');
  assert.strictEqual(badgeTotal({ jarvis: 3, tasks: 2, review: 0 }), 5, 'badgeTotal suma');
  assert.strictEqual(badgeTotal({ a: 0, b: 0 }), 0, 'badgeTotal solo ceros = 0');
}
console.log('OK badgeTotal');

// ── clampWidth: 300..70% del contenido, default no aplica acá ─────
{
  assert.strictEqual(clampWidth(340, 1000), 340, 'dentro de rango pasa igual');
  assert.strictEqual(clampWidth(100, 1000), 300, 'por debajo de 300 → 300');
  assert.strictEqual(clampWidth(900, 1000), 700, 'por encima de 70% → 70% del contenido');
  // si 70% del contenido < 300 (contenedor angosto), gana el min 300
  assert.strictEqual(clampWidth(50, 400), 300, 'min 300 gana sobre 70% cuando el contenido es chico');
  assert.strictEqual(clampWidth(500, 400), 300, 'tope = max(300, 70%)=300 con contenido chico');
}
console.log('OK clampWidth');

// ── maximize: válido en preview|jarvis ────────────────────────────
{
  // 'editor' salió del dock (→ editor deslizante #jw-editor): ya NO es maximizable.
  let s = base(); s.open = true; s.tab = 'editor';
  s = nextState(s, { type: 'setMax', value: true });
  assert.strictEqual(s.maximized, false, 'editor ya no es maximizable (salió del dock)');

  let p = base(); p.open = true; p.tab = 'preview';
  p = nextState(p, { type: 'setMax', value: true });
  assert.strictEqual(p.maximized, true, 'maximize permitido en preview');

  // jarvis (orquestador) ahora es maximizable → pantalla completa
  let j = base(); j.open = true; j.tab = 'jarvis';
  j = nextState(j, { type: 'setMax', value: true });
  assert.strictEqual(j.maximized, true, 'maximize permitido en jarvis (orquestador)');

  // pestaña no maximizable (tasks) → se ignora
  let t = base(); t.open = true; t.tab = 'tasks';
  t = nextState(t, { type: 'setMax', value: true });
  assert.strictEqual(t.maximized, false, 'maximize ignorado en pestañas no maximizables');

  // cambiar a una pestaña no maximizable mientras está maximizado → apaga max
  let e = base(); e.open = true; e.tab = 'editor'; e.maximized = true;
  e = nextState(e, { type: 'setTab', tab: 'tasks' });
  assert.strictEqual(e.maximized, false, 'setTab a pestaña no maximizable apaga maximizado');
}
console.log('OK maximize');

// ── setWidth: clampea contra el contenido ─────────────────────────
{
  let s = base();
  s = nextState(s, { type: 'setWidth', px: 900, contentW: 1000 });
  assert.strictEqual(s.width, 700, 'setWidth clampea al 70%');
  s = nextState(s, { type: 'setWidth', px: 120, contentW: 1000 });
  assert.strictEqual(s.width, 300, 'setWidth clampea al min');
  // resetWidth vuelve a DEFAULT_W (320)
  s = nextState(s, { type: 'resetWidth' });
  assert.strictEqual(s.width, 320, 'resetWidth → 320');
}
console.log('OK setWidth/resetWidth');

// ── resolveAgentWidth: ancho del dock al maximizar un agente ──────────
// Regla del usuario: si YA ensanchó el panel en la pantalla completa de ese
// agente (hay `saved`), se usa; si NUNCA lo tocó ahí (saved null/NaN), queda el
// ancho base "como estaba". Siempre clampeado contra el contenido.
{
  // saved presente → gana (clampeado)
  assert.strictEqual(resolveAgentWidth(500, 320, 1000), 500,
    'con ancho guardado del agente → se usa ese');
  assert.strictEqual(resolveAgentWidth(900, 320, 1000), 700,
    'ancho guardado se clampea al 70% del contenido');
  // sin guardar → base
  assert.strictEqual(resolveAgentWidth(null, 340, 1000), 340,
    'sin ancho guardado → queda el ancho base');
  assert.strictEqual(resolveAgentWidth(NaN, 360, 1000), 360,
    'NaN (localStorage vacío/roto) cuenta como sin guardar → base');
  assert.strictEqual(resolveAgentWidth(undefined, 380, 1000), 380,
    'undefined cuenta como sin guardar → base');
  // el base también se clampea (contenedor angosto)
  assert.strictEqual(resolveAgentWidth(null, 900, 1000), 700,
    'el ancho base también se clampea al 70%');
}
console.log('OK resolveAgentWidth');

// ── resolveAgentTab: pestaña del dock al maximizar un agente ──────────
// Si hay pestaña recordada para el agente Y visible → esa; si no (nunca cambió
// ahí, o quedó oculta) → la base "normal".
{
  const vis = { mobile: false, preview: true, editor: true };
  assert.strictEqual(resolveAgentTab('editor', 'preview', vis), 'editor',
    'con pestaña guardada y visible → esa');
  assert.strictEqual(resolveAgentTab(null, 'preview', vis), 'preview',
    'sin pestaña guardada → la base');
  assert.strictEqual(resolveAgentTab('', 'preview', vis), 'preview',
    'string vacío cuenta como sin guardar → base');
  assert.strictEqual(resolveAgentTab('mobile', 'preview', vis), 'preview',
    'pestaña guardada pero OCULTA ahora → base (no se muestra una oculta)');
  assert.strictEqual(resolveAgentTab('editor', 'preview', undefined),
    'editor', 'sin mapa de visibilidad → se respeta la guardada');
}
console.log('OK resolveAgentTab');

// ── resolveAgentOpen: abierto/cerrado del dock al maximizar un agente ──
// '1'/'0' = el usuario abrió/cerró el panel en la pantalla completa de ese
// agente; sin dato → como estaba (base).
{
  assert.strictEqual(resolveAgentOpen('1', false), true,
    "guardado '1' → abierto (aunque la base esté cerrada)");
  assert.strictEqual(resolveAgentOpen('0', true), false,
    "guardado '0' → cerrado (aunque la base esté abierta)");
  assert.strictEqual(resolveAgentOpen(null, false), false,
    'sin guardar → como la base (cerrada)');
  assert.strictEqual(resolveAgentOpen(null, true), true,
    'sin guardar → como la base (abierta)');
  assert.strictEqual(resolveAgentOpen(undefined, true), true,
    'undefined cuenta como sin guardar → base');
}
console.log('OK resolveAgentOpen');

// ── setTabVisible: ej. mobile solo en proyectos Expo ──────────────
{
  let s = base();
  assert.strictEqual(s.visible.mobile, false, 'mobile arranca oculta');
  s = nextState(s, { type: 'setTabVisible', tab: 'mobile', value: true });
  assert.strictEqual(s.visible.mobile, true, 'setTabVisible muestra mobile');
  // si la tab activa se oculta, el dock cae a la default (preview)
  let a = base(); a.open = true; a.tab = 'mobile'; a.visible = { mobile: true };
  a = nextState(a, { type: 'setTabVisible', tab: 'mobile', value: false });
  assert.strictEqual(a.visible.mobile, false, 'oculta mobile');
  assert.strictEqual(a.tab, 'preview', 'ocultar la tab activa cae a preview');
}
console.log('OK setTabVisible');

// ── restoreTab: la pestaña deseada OCULTA queda PENDIENTE (no se pierde) ──
// Bug: al volver a un proyecto Expo donde dejaste el dock en Móvil, te
// reaparecía en Web preview. Causa: el restore es síncrono pero la visibilidad
// real de 'mobile' se resuelve async (detección de Expo). restoreTab degrada a
// DEFAULT para renderizar algo válido PERO recuerda el deseo en `pending`, que
// setTabVisible(...,true) re-activa cuando la pestaña aparece.
{
  const { restoreTab } = D;
  assert.deepStrictEqual(restoreTab('jarvis', { mobile: false }),
    { tab: 'jarvis', pending: null }, 'tab visible se restaura directo, sin pendiente');
  assert.deepStrictEqual(restoreTab('mobile', { mobile: false }),
    { tab: 'preview', pending: 'mobile' }, 'mobile oculta AHORA → preview + pendiente mobile');
  assert.deepStrictEqual(restoreTab('mobile', { mobile: true }),
    { tab: 'mobile', pending: null }, 'mobile ya visible se restaura directo');
  assert.deepStrictEqual(restoreTab(null, { mobile: false }),
    { tab: 'preview', pending: null }, 'sin persistencia → default, sin pendiente');
  // 'web' es overlay (siempre visible:false) y nunca recibe setTabVisible(true):
  // queda como pendiente inerte y el dock muestra DEFAULT (igual que antes).
  assert.deepStrictEqual(restoreTab('web', { mobile: false, web: false }),
    { tab: 'preview', pending: 'web' }, 'web persistida → preview (pendiente inerte)');
}
console.log('OK restoreTab');

// ── resolveMobileVisible: visibilidad de Móvil resuelta SINCRÓNICAMENTE ────
// Elimina el flash "primero Web preview y después salta a Móvil": el restore ya
// sabe que Móvil va visible (cache por-proyecto + inferencia del tab persistido)
// sin esperar la detección async de Expo.
{
  const { resolveMobileVisible } = D;
  assert.strictEqual(resolveMobileVisible('1', 'preview'), true,
    "cache '1' (Expo conocido) → visible directo");
  assert.strictEqual(resolveMobileVisible('0', 'mobile'), false,
    "cache '0' (no-Expo conocido) gana sobre la inferencia");
  assert.strictEqual(resolveMobileVisible(null, 'mobile'), true,
    'sin cache: tab persistida=mobile infiere Expo → visible (1ra visita post-update, sin flash)');
  assert.strictEqual(resolveMobileVisible(null, 'preview'), false,
    'sin cache + tab no-mobile → oculta (NO arrastra el proyecto anterior)');
  assert.strictEqual(resolveMobileVisible(undefined, 'editor'), false,
    'undefined cuenta como sin cache');
}
console.log('OK resolveMobileVisible');

// ── inmutabilidad: nextState no muta el estado de entrada ─────────
{
  const s0 = base(); s0.open = true; s0.badges = { jarvis: 1 };
  const snap = JSON.stringify(s0);
  nextState(s0, { type: 'notify', tab: 'tasks', n: 5 });
  assert.strictEqual(JSON.stringify(s0), snap, 'nextState es puro (no muta la entrada)');
}
console.log('OK inmutabilidad');

// ── guards de review: falsy no-booleano y setTab a tab invisible ──
{
  // setTabVisible con 0/null (no literal false) también dispara el fallback
  let s = base(); s.open = true; s.tab = 'mobile'; s.visible = { mobile: true };
  s = nextState(s, { type: 'setTabVisible', tab: 'mobile', value: 0 });
  assert.strictEqual(s.visible.mobile, false, 'value=0 oculta');
  assert.strictEqual(s.tab, 'preview', 'value=0 también cae a preview');
  // setTab a una pestaña explícitamente oculta es no-op
  let t = base(); t.open = true; t.tab = 'editor'; t.visible = { mobile: false };
  const t2 = nextState(t, { type: 'setTab', tab: 'mobile' });
  assert.strictEqual(t2.tab, 'editor', 'setTab a tab oculta es no-op');
  // open con tab oculta NO la activa: abre en la tab actual/default
  let o = base(); o.tab = 'editor'; o.visible = { mobile: false };
  const o2 = nextState(o, { type: 'open', tab: 'mobile' });
  assert.strictEqual(o2.open, true, 'open con tab oculta igual abre el dock');
  assert.strictEqual(o2.tab, 'editor', 'open con tab oculta NO la activa (respeta la actual)');
  // open con tab visible sí la activa (control positivo)
  let p = base(); p.tab = 'editor'; p.visible = { mobile: true };
  const p2 = nextState(p, { type: 'open', tab: 'mobile' });
  assert.strictEqual(p2.tab, 'mobile', 'open con tab visible sí la activa');
}
console.log('OK guards de review');

console.log('\nTODOS OK — panel-state');
