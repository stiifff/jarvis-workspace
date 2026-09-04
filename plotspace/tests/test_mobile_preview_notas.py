"""Notas del proyecto (Mobile Studio): saneo puro + CRUD sobre la DB local.

Las notas guardan el saber operativo del proyecto (cuentas de Expo/EAS,
comandos, pendientes) y viven SOLO en data/jarvis.db — nunca en el repo.
"""
import os
import tempfile
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plotspace.core.database import get_db
from plotspace.routers import mobile_preview as mp
from plotspace.routers.mobile_preview import _nota_campos
from plotspace.tests._harness import fresh_db


# ── _nota_campos: saneo puro (defaults, clamps, parche parcial) ───────────────

def test_nota_campos_defaults():
    c = _nota_campos({})
    assert c == {'titulo': '', 'cuerpo': '', 'secreta': 0, 'color': 'papel',
                 'x': 0.0, 'y': 0.0, 'w': 320.0, 'h': 300.0}


def test_nota_campos_clampea_y_normaliza():
    c = _nota_campos({'titulo': 'x' * 500, 'cuerpo': 'y' * 30000, 'secreta': 'sí',
                      'color': 'fucsia', 'x': 'ñ', 'y': 99999, 'w': 10, 'h': 99999})
    assert len(c['titulo']) == 200
    assert len(c['cuerpo']) == 20000
    assert c['secreta'] == 1
    assert c['color'] == 'papel'        # color desconocido → papel
    assert c['x'] == 0.0                # basura → default
    assert c['y'] == 50000              # clampeada
    assert c['w'] == 220                # mínimo usable
    assert c['h'] == 4000               # techo


def test_nota_campos_parche_parcial_conserva_lo_previo():
    previa = {'titulo': 'Expo', 'cuerpo': 'user / pass', 'secreta': 1,
              'color': 'ambar', 'x': 40, 'y': 60, 'w': 400, 'h': 500}
    c = _nota_campos({'x': 100}, previa)
    assert c['titulo'] == 'Expo' and c['cuerpo'] == 'user / pass'
    assert c['secreta'] == 1 and c['color'] == 'ambar'
    assert c['x'] == 100.0 and c['y'] == 60.0   # solo cambia lo que vino
    assert c['w'] == 400.0 and c['h'] == 500.0
    # Vaciar un campo a propósito SÍ se respeta (no se hereda lo viejo).
    assert _nota_campos({'cuerpo': ''}, previa)['cuerpo'] == ''


def test_nota_campos_nan_cae_al_default():
    assert _nota_campos({'x': float('nan')})['x'] == 0.0


# ── CRUD sobre la DB (router montado solo) ───────────────────────────────────

@pytest.fixture()
def cliente():
    fresh_db()
    app = FastAPI()
    app.include_router(mp.router)
    d = tempfile.mkdtemp()
    now = datetime.now().isoformat()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('INSERT INTO projects (nombre, ruta, fecha_creacion, ultimo_acceso) '
                    'VALUES (?, ?, ?, ?)', (os.path.basename(d), d, now, now))
        pid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    return TestClient(app), pid


def test_crud_notas(cliente):
    client, pid = cliente
    assert client.get(f'/api/mobile-preview/{pid}/notas').json() == {'notas': []}

    r = client.post(f'/api/mobile-preview/{pid}/notas',
                    json={'titulo': 'Cuenta Expo', 'cuerpo': 'user@x.com', 'color': 'ambar'})
    assert r.status_code == 201
    nota = r.json()
    assert nota['titulo'] == 'Cuenta Expo' and nota['color'] == 'ambar'
    assert nota['project_id'] == pid and nota['id'] > 0

    # PUT parcial: solo mueve la nota, el contenido queda intacto.
    r = client.put(f'/api/mobile-preview/{pid}/notas/{nota["id"]}',
                   json={'x': 120, 'y': 40, 'secreta': True})
    assert r.status_code == 200
    upd = r.json()
    assert upd['x'] == 120 and upd['y'] == 40 and upd['secreta'] == 1
    assert upd['cuerpo'] == 'user@x.com'
    assert upd['actualizado'] >= nota['actualizado']

    assert len(client.get(f'/api/mobile-preview/{pid}/notas').json()['notas']) == 1

    assert client.delete(f'/api/mobile-preview/{pid}/notas/{nota["id"]}').status_code == 200
    assert client.get(f'/api/mobile-preview/{pid}/notas').json() == {'notas': []}
    # Borrar dos veces no miente: la segunda es 404.
    assert client.delete(f'/api/mobile-preview/{pid}/notas/{nota["id"]}').status_code == 404


def test_notas_aisladas_por_proyecto(cliente):
    client, pid = cliente
    now = datetime.now().isoformat()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute('INSERT INTO projects (nombre, ruta, fecha_creacion, ultimo_acceso) '
                    'VALUES (?, ?, ?, ?)', ('otro', tempfile.mkdtemp(), now, now))
        otro = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    nota = client.post(f'/api/mobile-preview/{pid}/notas', json={'titulo': 'A'}).json()
    assert client.get(f'/api/mobile-preview/{otro}/notas').json() == {'notas': []}
    # Una nota ajena no se toca ni se borra desde otro proyecto.
    assert client.put(f'/api/mobile-preview/{otro}/notas/{nota["id"]}', json={'titulo': 'B'}).status_code == 404
    assert client.delete(f'/api/mobile-preview/{otro}/notas/{nota["id"]}').status_code == 404


def test_tope_de_notas(cliente):
    client, pid = cliente
    for i in range(mp.MAX_NOTAS):
        assert client.post(f'/api/mobile-preview/{pid}/notas', json={'titulo': f'n{i}'}).status_code == 201
    r = client.post(f'/api/mobile-preview/{pid}/notas', json={'titulo': 'una más'})
    assert r.status_code == 409
