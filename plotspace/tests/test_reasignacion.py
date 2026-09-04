"""
Test: _terminales_ocupadas — el set de agentes que NO se pueden reasignar.

La reasignación por TASK_ERROR antes podía mandarle la tarea a un agente que ya
estaba trabajando otro paso 'running', corrompiendo ambos. Ahora se excluyen
las terminales ocupadas. Se prueba la lógica con un cursor sqlite en memoria.
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers.orchestrator import _terminales_ocupadas


def _cursor(rows):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE workflows (id TEXT, project_id INT, estado TEXT, pasos TEXT)')
    conn.executemany('INSERT INTO workflows VALUES (?, ?, ?, ?)', rows)
    conn.commit()
    return conn.cursor()


def test_ocupadas_incluye_running_de_workflows_activos():
    pasos = json.dumps([
        {'estado': 'running', 'terminal_id': 5},
        {'estado': 'done',    'terminal_id': 6},   # done no ocupa
        {'estado': 'pending', 'terminal_id': 8},   # pending no ocupa
    ])
    cur = _cursor([('w1', 1, 'running', pasos)])
    assert _terminales_ocupadas(cur, 1) == {5}


def test_ocupadas_ignora_workflows_terminados():
    pasos = json.dumps([{'estado': 'running', 'terminal_id': 7}])
    cur = _cursor([('w1', 1, 'done', pasos)])   # estado del workflow no activo
    assert _terminales_ocupadas(cur, 1) == set()


def test_ocupadas_solo_del_proyecto_pedido():
    pasos = json.dumps([{'estado': 'running', 'terminal_id': 9}])
    cur = _cursor([('w1', 2, 'running', pasos)])
    assert _terminales_ocupadas(cur, 1) == set()   # es de otro proyecto


def test_ocupadas_varios_workflows_se_unen():
    p1 = json.dumps([{'estado': 'running', 'terminal_id': 1}])
    p2 = json.dumps([{'estado': 'running', 'terminal_id': 2}])
    cur = _cursor([('w1', 1, 'running', p1), ('w2', 1, 'paused', p2)])
    assert _terminales_ocupadas(cur, 1) == {1, 2}


def test_ocupadas_tolera_pasos_corruptos():
    cur = _cursor([('w1', 1, 'running', 'no-es-json')])
    assert _terminales_ocupadas(cur, 1) == set()


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
