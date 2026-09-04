"""Test de POST /api/projects/{id}/files/mkdir."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from plotspace.tests._harness import fresh_db, make_client_and_project


def main():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    base = f"/api/projects/{pid}/files"

    # 1) Crear carpeta simple
    r = client.post(f"{base}/mkdir", json={"path": "sub"})
    assert r.status_code == 200, (r.status_code, r.text)
    assert r.json()["ok"] is True
    assert os.path.isdir(os.path.join(d, "sub")), "no se creó la carpeta"

    # 2) Crear carpeta anidada (makedirs crea padres)
    r = client.post(f"{base}/mkdir", json={"path": "a/b/c"})
    assert r.status_code == 200, (r.status_code, r.text)
    assert os.path.isdir(os.path.join(d, "a", "b", "c"))

    # 3) 409 si ya existe
    r = client.post(f"{base}/mkdir", json={"path": "sub"})
    assert r.status_code == 409, (r.status_code, r.text)

    # 4) Traversal rechazado (400 de _safe_join)
    r = client.post(f"{base}/mkdir", json={"path": "../escapada"})
    assert r.status_code == 400, (r.status_code, r.text)
    assert not os.path.isdir(os.path.join(os.path.dirname(d), "escapada"))

    # 5) Nombre sensible rechazado (403)
    r = client.post(f"{base}/mkdir", json={"path": ".env"})
    assert r.status_code == 403, (r.status_code, r.text)

    # 6) Path vacío rechazado (400)
    r = client.post(f"{base}/mkdir", json={"path": ""})
    assert r.status_code == 400, (r.status_code, r.text)

    print("OK")


if __name__ == "__main__":
    main()
