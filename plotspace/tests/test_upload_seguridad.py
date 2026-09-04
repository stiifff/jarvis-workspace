# plotspace/tests/test_upload_seguridad.py
"""Fase 7 — POST /files/upload rechaza traversal, sensibles e IGNORE_DIRS."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from plotspace.tests._harness import fresh_db, make_client_and_project


def test_traversal_rechazado():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    r = client.post(
        f"/api/projects/{pid}/files/upload",
        files=[("files", ("evil", b"pwned", "text/plain"))],
        data={"rel_paths": ["../../evil.txt"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subidos"] == [], body
    assert any(x["motivo"] == "ruta inválida" for x in body["rechazados"]), body
    # No escribió nada fuera del proyecto
    parent = os.path.dirname(d.rstrip("/"))
    assert not os.path.exists(os.path.join(parent, "evil.txt"))


def test_env_rechazado():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    r = client.post(
        f"/api/projects/{pid}/files/upload",
        files=[("files", (".env", b"SECRET=1", "text/plain"))],
        data={"rel_paths": ["config/.env"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subidos"] == [], body
    assert any(x["motivo"] == "archivo sensible" for x in body["rechazados"]), body
    assert not os.path.exists(os.path.join(d, "config", ".env"))


def test_segmento_ignore_dir_rechazado():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    r = client.post(
        f"/api/projects/{pid}/files/upload",
        files=[("files", ("config", b"x", "text/plain"))],
        data={"rel_paths": ["node_modules/foo/config.js"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subidos"] == [], body
    assert any(x["motivo"] == "carpeta ignorada" for x in body["rechazados"]), body
    assert not os.path.exists(os.path.join(d, "node_modules"))


if __name__ == "__main__":
    test_traversal_rechazado()
    test_env_rechazado()
    test_segmento_ignore_dir_rechazado()
    print("OK")
