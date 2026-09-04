"""
Test: el menú de "Localhost activos" de la barra lista SOLO localhost.

El endpoint GET /api/orchestrator/preview/{id}/servers alimenta el botón
#jw-localhosts-btn. A pedido del usuario (2026-06-20) ese menú es exclusivamente
de dev servers locales detectados en los previews: NO debe listar terminales /
agentes que estén trabajando. Acá probamos justamente eso — que la respuesta
trae solo `servers` (y nunca `shells`), aun habiendo agentes runeando.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.tests._harness import fresh_db
from plotspace.core.database import get_db


def _insertar_terminal(pid, tid, nombre, tipo='claude'):
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO terminals (id, project_id, nombre, tipo_ia, activa, fecha_creacion) '
            'VALUES (?, ?, ?, ?, 1, ?)',
            (tid, pid, nombre, tipo, datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def _proyecto(nombre='proj'):
    conn = get_db()
    try:
        cur = conn.cursor()
        now = datetime.now().isoformat()
        cur.execute(
            'INSERT INTO projects (nombre, ruta, fecha_creacion, ultimo_acceso) VALUES (?, ?, ?, ?)',
            (nombre, f'/tmp/{nombre}', now, now),
        )
        pid = cur.lastrowid
        conn.commit()
        return pid
    finally:
        conn.close()


def test_endpoint_lista_solo_localhost_sin_terminales(monkeypatch):
    # Hay una terminal TRABAJANDO + un dev server detectado. El menú debe traer
    # SOLO el localhost; la terminal trabajando NO aparece (ni como `shells`).
    fresh_db()
    import asyncio
    from plotspace.core import dev_detect, agent_watch
    from plotspace.routers.orchestrator import listar_servers_preview

    pid = _proyecto('endpoint')
    _insertar_terminal(pid, 30, 'Backend', 'claude')
    # Aunque agent_watch diga que la terminal está trabajando...
    monkeypatch.setattr(agent_watch, '_estados', {30: {'fase': 'trabajando', 'esperando': False}})
    # ...y haya un dev server vivo detectado en su preview:
    monkeypatch.setattr(dev_detect, 'servers_detectados', lambda project_id: [
        {'url': 'http://localhost:5173/', 'terminal_id': 30, 'terminal_nombre': 'Backend'},
    ])

    d = asyncio.run(listar_servers_preview(pid))

    # El menú es SOLO de localhost: ni la clave `shells` debe existir.
    assert 'shells' not in d, d
    assert len(d['servers']) == 1
    s = d['servers'][0]
    assert s['url'] == 'http://localhost:5173/'
    assert s['terminal_nombre'] == 'Backend'
    assert s['propio'] is False


def test_endpoint_sin_localhost_devuelve_vacio_aunque_haya_agentes(monkeypatch):
    # Sin dev servers, el menú está vacío AUNQUE haya agentes trabajando: el
    # botón de la barra se oculta (la lógica de ocultar vive en el cliente, pero
    # acá garantizamos que el backend no inyecta terminales en la respuesta).
    fresh_db()
    import asyncio
    from plotspace.core import dev_detect, agent_watch
    from plotspace.routers.orchestrator import listar_servers_preview

    pid = _proyecto('vacio')
    _insertar_terminal(pid, 40, 'Frontend', 'codex')
    monkeypatch.setattr(agent_watch, '_estados', {40: {'fase': 'trabajando', 'esperando': False}})
    monkeypatch.setattr(dev_detect, 'servers_detectados', lambda project_id: [])

    d = asyncio.run(listar_servers_preview(pid))
    assert d['servers'] == []
    assert 'shells' not in d, d


if __name__ == '__main__':
    import traceback

    class _MP:
        def __init__(self): self._undo = []
        def setattr(self, obj, name, val):
            old = getattr(obj, name); self._undo.append((obj, name, old))
            setattr(obj, name, val)
        def deshacer(self):
            for obj, name, old in reversed(self._undo): setattr(obj, name, old)

    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith('test_') and callable(fn):
            mp = _MP()
            try:
                fn(mp); print(f'ok  {nombre}')
            except Exception:
                fallos += 1; print(f'FAIL {nombre}'); traceback.print_exc()
            finally:
                mp.deshacer()
    sys.exit(1 if fallos else 0)
