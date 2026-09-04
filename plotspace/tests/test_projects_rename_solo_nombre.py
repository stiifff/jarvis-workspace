"""Renombrar un proyecto cambia SOLO el nombre visible en el dashboard.

Pedido del usuario (2026-07-03, tras el incidente): personalizar el nombre del
workspace en localhost NO debe tocar la carpeta en disco. Antes `os.rename`
movía la carpeta — y con el repo registrado como proyecto, eso lo movió entero.
Ahora el rename es puramente cosmético: `nombre` en DB, `ruta` intacta.
"""
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from plotspace.tests._harness import fresh_db
from plotspace.core.database import get_db
from plotspace.routers import projects


def _client_and_project(project_dir):
    now = datetime.now().isoformat()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO projects (nombre, ruta, fecha_creacion, ultimo_acceso) VALUES (?,?,?,?)",
        (os.path.basename(project_dir.rstrip('/')) or 'test', project_dir, now, now),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    app = FastAPI()
    app.include_router(projects.router)
    return TestClient(app), pid


def test_rename_cambia_nombre_sin_tocar_disco():
    fresh_db()
    base = tempfile.mkdtemp()                    # contenedor aislado (evita choques en /tmp)
    d = os.path.join(base, "proyecto-original")
    os.makedirs(d)
    with open(os.path.join(d, 'marker.txt'), 'w', encoding='utf-8') as f:
        f.write('contenido real')
    client, pid = _client_and_project(d)

    r = client.patch(f"/api/projects/{pid}/rename", json={"nombre": "Nombre Bonito"})
    assert r.status_code == 200, (r.status_code, r.text)
    body = r.json()

    # El nombre visible cambió...
    assert body["nombre"] == "Nombre Bonito"
    # ...pero la RUTA quedó exactamente igual (no se derivó una ruta nueva).
    assert body["ruta"] == d, (body["ruta"], d)

    # En disco: la carpeta ORIGINAL sigue existiendo con su contenido...
    assert os.path.isdir(d)
    assert os.path.isfile(os.path.join(d, 'marker.txt'))
    # ...y NO se creó ninguna carpeta con el nombre nuevo.
    assert not os.path.exists(os.path.join(os.path.dirname(d), "Nombre Bonito"))

    # En la DB quedó consistente: nombre nuevo, ruta vieja.
    conn = get_db()
    row = conn.execute("SELECT nombre, ruta FROM projects WHERE id=?", (pid,)).fetchone()
    conn.close()
    assert row["nombre"] == "Nombre Bonito"
    assert row["ruta"] == d


def test_rename_valida_nombre_vacio_y_barras():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = _client_and_project(d)
    assert client.patch(f"/api/projects/{pid}/rename", json={"nombre": "   "}).status_code == 400
    assert client.patch(f"/api/projects/{pid}/rename", json={"nombre": "a/b"}).status_code == 400
    # La ruta sigue intacta tras los rechazos.
    conn = get_db()
    assert conn.execute("SELECT ruta FROM projects WHERE id=?", (pid,)).fetchone()["ruta"] == d
    conn.close()


def main():
    test_rename_cambia_nombre_sin_tocar_disco()
    test_rename_valida_nombre_vacio_y_barras()
    print("OK")


if __name__ == "__main__":
    main()
