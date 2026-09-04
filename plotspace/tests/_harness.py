"""
Harness de tests para el editor overhaul.

Aísla cada test en una base de datos SQLite temporal (nunca toca jarvis.db) y
expone un cliente FastAPI mínimo que monta SOLO el router projects_files.

Uso típico:
    from plotspace.tests._harness import fresh_db, make_client_and_project
    fresh_db()
    import tempfile
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    r = client.post(f"/api/projects/{pid}/files/mkdir", json={"path": "sub"})
    assert r.status_code == 200
"""
import os
import sys
import tempfile
from datetime import datetime

# Asegurar imports absolutos 'plotspace.*' al correr el test como script suelto.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fastapi import FastAPI
from fastapi.testclient import TestClient

from plotspace.core import database
from plotspace.core.database import init_db, get_db
from plotspace.routers import projects_files


def fresh_db() -> str:
    """Repunta database.DB_PATH a un .db temporal y crea las tablas.

    No ensucia jarvis.db. Devuelve la ruta del archivo temporal por si el
    llamador quiere inspeccionarlo. get_db() lee database.DB_PATH en cada
    conexión, así que repuntar el atributo del módulo es suficiente.
    """
    fd, path = tempfile.mkstemp(suffix=".db", prefix="jarvis_test_")
    os.close(fd)
    os.remove(path)  # init_db lo recrea; arrancamos de cero garantizado
    database.DB_PATH = path
    init_db()
    return path


def _build_app() -> FastAPI:
    """FastAPI mínimo con SOLO el router projects_files montado."""
    app = FastAPI()
    app.include_router(projects_files.router)
    return app


def make_client_and_project(project_dir: str):
    """Inserta un proyecto temporal apuntando a project_dir y devuelve
    (TestClient, project_id).

    project_dir debe existir en disco: _get_project_path() valida os.path.isdir.
    Todas las columnas NOT NULL de projects se rellenan.
    """
    now = datetime.now().isoformat()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO projects (nombre, ruta, fecha_creacion, ultimo_acceso)
            VALUES (?, ?, ?, ?)
            """,
            (os.path.basename(project_dir.rstrip("/")) or "test", project_dir, now, now),
        )
        pid = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    client = TestClient(_build_app())
    return client, pid
