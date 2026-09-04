"""
Test: el MOTIVO de TASK_BLOCKED/TASK_ERROR se captura end-to-end.

Antes el sistema tiraba el "por qué" de cada fallo: el sentinel parseaba
{estado, motivo} pero el poller descartaba el motivo, task_events guardaba solo
la keyword con workflow_id siempre NULL, y el broadcast decía "está bloqueado"
a secas. Sin motivos persistidos no hay nada de qué aprender (capa Captura del
sistema de memoria).

Cubre:
  - migración: task_events tiene columna motivo
  - _workflow_de_terminal: resuelve a qué workflow pertenece una terminal
  - _procesar_keyword_evento persiste motivo + workflow_id
  - sentinel._ciclo propaga el motivo del archivo
  - procesar_task_event_interno guarda el motivo en el paso JSON y lo incluye
    en los broadcasts (task_event + orquestador_mensaje)
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.tests._harness import fresh_db
from plotspace.core import database
from plotspace.core.database import get_db


# ─── Migración: columna motivo en task_events ────────────────────────────────

def test_task_events_tiene_columna_motivo():
    fresh_db()
    conn = get_db()
    try:
        cols = {r['name'] for r in conn.execute('PRAGMA table_info(task_events)').fetchall()}
    finally:
        conn.close()
    assert 'motivo' in cols, f"task_events sin columna motivo: {cols}"


# ─── _workflow_de_terminal (lógica pura, cursor en memoria) ──────────────────

def _cursor_workflows(rows):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE workflows (id TEXT, project_id INT, estado TEXT, pasos TEXT, created_at TEXT)')
    conn.executemany('INSERT INTO workflows VALUES (?, ?, ?, ?, ?)', rows)
    conn.commit()
    return conn.cursor()


def test_workflow_de_terminal_encuentra_el_activo():
    from plotspace.routers.terminals import _workflow_de_terminal
    pasos = json.dumps([{'terminal_id': 5, 'estado': 'running'}])
    cur = _cursor_workflows([('wf9', 1, 'running', pasos, '2026-07-10')])
    assert _workflow_de_terminal(cur, 1, 5) == 'wf9'


def test_workflow_de_terminal_none_si_no_pertenece():
    from plotspace.routers.terminals import _workflow_de_terminal
    pasos = json.dumps([{'terminal_id': 7, 'estado': 'running'}])
    cur = _cursor_workflows([('wf9', 1, 'running', pasos, '2026-07-10')])
    assert _workflow_de_terminal(cur, 1, 5) is None


def test_workflow_de_terminal_ignora_terminados_y_tolera_corruptos():
    from plotspace.routers.terminals import _workflow_de_terminal
    pasos = json.dumps([{'terminal_id': 5}])
    cur = _cursor_workflows([
        ('viejo', 1, 'done', pasos, '2026-07-01'),      # terminado: no cuenta
        ('roto',  1, 'running', 'no-es-json', '2026-07-02'),
        ('vivo',  1, 'paused', pasos, '2026-07-03'),     # paused también vale
    ])
    assert _workflow_de_terminal(cur, 1, 5) == 'vivo'


# ─── _procesar_keyword_evento: persiste motivo + workflow_id ─────────────────

def _preparar_workflow_en_db(project_id=1, terminal_id=5, wf_id='wf-m1'):
    """Inserta un workflow activo cuyos pasos incluyen la terminal."""
    pasos = json.dumps([{'agente': 'Backend', 'terminal_id': terminal_id,
                         'estado': 'running', 'ia_type': 'claude'}])
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO projects (id, nombre, ruta, fecha_creacion, ultimo_acceso) "
            "VALUES (?, 'proj-test', '/tmp/proj-test', '2026-07-10', '2026-07-10')",
            (project_id,))
        conn.execute(
            'INSERT INTO workflows (id, project_id, nombre, objetivo, estado, pasos, paso_actual, created_at) '
            "VALUES (?, ?, 'WF Test', '', 'running', ?, 0, '2026-07-10T10:00:00')",
            (wf_id, project_id, pasos))
        conn.execute(
            "INSERT INTO terminals (id, project_id, nombre, tipo_ia, activa, fecha_creacion) "
            "VALUES (?, ?, 'Backend', 'claude', 1, '2026-07-10T10:00:00')",
            (terminal_id, project_id))
        conn.commit()
    finally:
        conn.close()


def test_procesar_keyword_persiste_motivo_y_workflow_id():
    fresh_db()
    _preparar_workflow_en_db()

    import plotspace.routers.terminals as term
    import plotspace.routers.orchestrator as orch
    from plotspace.core import logs

    recibidos = []

    async def _fake_interno(terminal_id, event, project_id, motivo=''):
        recibidos.append((terminal_id, event, project_id, motivo))

    orig_interno, orig_evento = orch.procesar_task_event_interno, logs.evento
    orch.procesar_task_event_interno = _fake_interno
    logs.evento = lambda *a, **k: None
    try:
        asyncio.run(term._procesar_keyword_evento(5, 1, 'TASK_BLOCKED', motivo='falta la API key'))
    finally:
        orch.procesar_task_event_interno = orig_interno
        logs.evento = orig_evento

    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM task_events ORDER BY id DESC LIMIT 1').fetchone()
    finally:
        conn.close()
    assert row['event'] == 'TASK_BLOCKED'
    assert row['motivo'] == 'falta la API key'
    assert row['workflow_id'] == 'wf-m1', "workflow_id debe poblarse (antes era siempre NULL)"
    # y el motivo viaja al orquestador
    assert recibidos == [(5, 'TASK_BLOCKED', 1, 'falta la API key')]


def test_procesar_keyword_sin_motivo_sigue_andando():
    fresh_db()
    _preparar_workflow_en_db()

    import plotspace.routers.terminals as term
    import plotspace.routers.orchestrator as orch
    from plotspace.core import logs

    orig_interno, orig_evento = orch.procesar_task_event_interno, logs.evento

    async def _noop(*a, **k):
        pass

    orch.procesar_task_event_interno = _noop
    logs.evento = lambda *a, **k: None
    try:
        asyncio.run(term._procesar_keyword_evento(5, 1, 'TASK_DONE'))
    finally:
        orch.procesar_task_event_interno = orig_interno
        logs.evento = orig_evento

    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM task_events ORDER BY id DESC LIMIT 1').fetchone()
    finally:
        conn.close()
    assert row['event'] == 'TASK_DONE'
    assert row['motivo'] in (None, '')


# ─── sentinel._ciclo propaga el motivo ────────────────────────────────────────

def test_ciclo_sentinel_propaga_motivo():
    import plotspace.core.sentinel as sen
    import plotspace.routers.terminals as term

    with tempfile.TemporaryDirectory() as d:
        sig = os.path.join(d, '.jarvis', 'signals')
        os.makedirs(sig)
        with open(os.path.join(sig, 'terminal_8.json'), 'w') as f:
            f.write('{"estado":"blocked","motivo":"npm install falla con EACCES"}')

        wf = {'id': 'wf1', 'project_id': 7, 'ruta': d, 'pasos': [
            {'agente': 'Backend', 'estado': 'running', 'terminal_id': 8, 'iniciado_ts': 1.0},
        ]}
        llamadas = []

        async def _fake_proc(tid, pid, kw, motivo=None):
            llamadas.append((tid, pid, kw, motivo))

        orig_wf, orig_proc, orig_tt = sen._workflows_running, term._procesar_keyword_evento, asyncio.to_thread
        sen._workflows_running = lambda: [wf]
        term._procesar_keyword_evento = _fake_proc

        async def _direct(fn, *a, **k):
            return fn(*a, **k)

        asyncio.to_thread = _direct
        try:
            asyncio.run(sen._ciclo())
        finally:
            sen._workflows_running = orig_wf
            term._procesar_keyword_evento = orig_proc
            asyncio.to_thread = orig_tt

        assert llamadas == [(8, 7, 'TASK_BLOCKED', 'npm install falla con EACCES')]


# ─── procesar_task_event_interno: motivo al paso JSON + broadcasts ────────────

def _correr_interno(event, motivo):
    """Corre procesar_task_event_interno con broadcaster grabador y DB fresca."""
    fresh_db()
    _preparar_workflow_en_db()

    from plotspace.routers.orchestrator import procesar_task_event_interno
    from plotspace.core import events

    emitidos = []

    async def _fake_broadcast(project_id, data):
        emitidos.append(data)

    orig = events.broadcaster.broadcast
    events.broadcaster.broadcast = _fake_broadcast
    try:
        asyncio.run(procesar_task_event_interno(5, event, 1, motivo=motivo))
    finally:
        events.broadcaster.broadcast = orig

    conn = get_db()
    try:
        wf = conn.execute("SELECT * FROM workflows WHERE id = 'wf-m1'").fetchone()
    finally:
        conn.close()
    return json.loads(wf['pasos']), dict(wf), emitidos


def test_blocked_guarda_motivo_en_paso_y_broadcasts():
    pasos, wf, emitidos = _correr_interno('TASK_BLOCKED', 'falta el token de deploy')
    assert pasos[0]['estado'] == 'blocked'
    assert pasos[0]['motivo'] == 'falta el token de deploy'
    assert wf['estado'] == 'paused'

    ev_task = next(e for e in emitidos if e['type'] == 'task_event')
    assert ev_task['motivo'] == 'falta el token de deploy'
    ev_msg = next(e for e in emitidos if e['type'] == 'orquestador_mensaje')
    assert 'falta el token de deploy' in ev_msg['message']


def test_error_sin_reasignacion_guarda_motivo():
    # No hay otro agente disponible → pausa con motivo persistido en el paso.
    pasos, wf, emitidos = _correr_interno('TASK_ERROR', 'pytest rompe en test_auth')
    assert pasos[0]['estado'] == 'error'
    assert pasos[0]['motivo'] == 'pytest rompe en test_auth'
    assert wf['estado'] == 'paused'
    ev_msg = next(e for e in emitidos if e['type'] == 'orquestador_mensaje')
    assert 'pytest rompe en test_auth' in ev_msg['message']


def test_blocked_sin_motivo_no_ensucia_el_mensaje():
    pasos, wf, emitidos = _correr_interno('TASK_BLOCKED', '')
    assert pasos[0]['estado'] == 'blocked'
    assert 'motivo' not in pasos[0] or pasos[0]['motivo'] == ''
    ev_msg = next(e for e in emitidos if e['type'] == 'orquestador_mensaje')
    assert '¿Cómo continuamos?' in ev_msg['message']


if __name__ == '__main__':
    import traceback
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith('test_') and callable(fn):
            try:
                fn(); print(f'ok  {nombre}')
            except Exception:
                fallos += 1; print(f'FAIL {nombre}'); traceback.print_exc()
    sys.exit(1 if fallos else 0)
