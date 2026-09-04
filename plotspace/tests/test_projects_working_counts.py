"""`GET /api/projects/working` trae el conteo de terminales de TODOS los proyectos.

Bug que arregla: en la franja, el contador de terminales de los workspaces que
NO son el activo se congelaba en el valor del último `GET /api/projects`. Nada
avisa cuando otro workspace abre o cierra terminales (`projects_update` solo se
emite al crear/renombrar/archivar/borrar un PROYECTO), así que estando dentro de
un workspace nunca se veían las terminales vivas de los otros.

El frontend ya pollea este endpoint cada 3s para el anillo del orbe; sumarle los
conteos hace que el contador se reconcilie por NIVEL con el mismo request (cero
polls nuevos, self-healing).
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from plotspace.tests._harness import fresh_db
from plotspace.core.database import get_db
from plotspace.routers import projects


def _sembrar(proyectos):
    """proyectos = [(nombre, [(nombre_terminal, activa), ...]), ...] → {nombre: pid}"""
    now = datetime.now().isoformat()
    conn = get_db()
    cur = conn.cursor()
    ids = {}
    for nombre, terminales in proyectos:
        cur.execute(
            "INSERT INTO projects (nombre, ruta, fecha_creacion, ultimo_acceso) VALUES (?,?,?,?)",
            (nombre, '/tmp/' + nombre, now, now),
        )
        pid = cur.lastrowid
        ids[nombre] = pid
        for tnombre, activa in terminales:
            cur.execute(
                "INSERT INTO terminals (project_id, nombre, activa, fecha_creacion) VALUES (?,?,?,?)",
                (pid, tnombre, activa, now),
            )
    conn.commit()
    conn.close()
    return ids


def _client():
    app = FastAPI()
    app.include_router(projects.router)
    return TestClient(app)


def test_working_cuenta_terminales_de_todos_los_proyectos():
    fresh_db()
    ids = _sembrar([
        # el proyecto "activo" del usuario
        ('Jarvis', [('Claude #1', 1), ('Claude #2', 1), ('vieja', 0)]),
        # el OTRO workspace: sus terminales vivas tienen que verse desde acá
        ('Derlis-APP', [('Claude #1', 1), ('Shell #2', 1), ('muerta', 0), ('muerta2', 0)]),
        ('Sin terminales', []),
    ])

    body = _client().get('/api/projects/working').json()

    assert 'counts' in body, 'el poll del anillo debe traer también los conteos'
    counts = body['counts']
    # claves como STRING: viajan por JSON y el frontend indexa por String(p.id)
    assert counts[str(ids['Jarvis'])] == 2
    assert counts[str(ids['Derlis-APP'])] == 2          # el corazón del bug
    assert str(ids['Sin terminales']) not in counts     # ausente = 0 (el front lo lee así)


def test_working_conserva_ids_y_refleja_cierres():
    fresh_db()
    ids = _sembrar([('Derlis-APP', [('Claude #1', 1), ('Shell #2', 1)])])
    pid = ids['Derlis-APP']

    body = _client().get('/api/projects/working').json()
    assert isinstance(body.get('ids'), list)            # contrato viejo intacto
    assert body['counts'][str(pid)] == 2

    conn = get_db()
    conn.execute('UPDATE terminals SET activa = 0 WHERE nombre = ?', ('Shell #2',))
    conn.commit()
    conn.close()

    body = _client().get('/api/projects/working').json()
    assert body['counts'][str(pid)] == 1                # cerrar una terminal se ve al toque


if __name__ == '__main__':
    test_working_cuenta_terminales_de_todos_los_proyectos()
    test_working_conserva_ids_y_refleja_cierres()
    print('ok')
