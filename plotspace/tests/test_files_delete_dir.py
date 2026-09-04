"""Test de DELETE /api/projects/{id}/files/dir?path (recursivo seguro)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from plotspace.tests._harness import fresh_db, make_client_and_project


def _touch(d, rel, content="x"):
    full = os.path.join(d, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    base = f"/api/projects/{pid}/files"

    # 1) Borrar carpeta recursiva normal
    _touch(d, "pkg/mod/a.py")
    _touch(d, "pkg/b.py")
    r = client.delete(f"{base}/dir", params={"path": "pkg"})
    assert r.status_code == 200, (r.status_code, r.text)
    assert not os.path.exists(os.path.join(d, "pkg"))

    # 2) 404 si no existe
    r = client.delete(f"{base}/dir", params={"path": "noexiste"})
    assert r.status_code == 404, (r.status_code, r.text)

    # 3) 400 si apunta a un archivo (no carpeta)
    _touch(d, "archivo.txt")
    r = client.delete(f"{base}/dir", params={"path": "archivo.txt"})
    assert r.status_code == 400, (r.status_code, r.text)
    assert os.path.isfile(os.path.join(d, "archivo.txt"))

    # 4) Rechazar borrar la RAÍZ del proyecto (400) — path vacío
    r = client.delete(f"{base}/dir", params={"path": ""})
    assert r.status_code == 400, (r.status_code, r.text)
    assert os.path.isdir(d)

    # 5) Rechazar borrar la raíz vía "." o "/"
    for p in (".", "/"):
        r = client.delete(f"{base}/dir", params={"path": p})
        assert r.status_code == 400, (p, r.status_code, r.text)
        assert os.path.isdir(d)

    # 6) Rechazar nombres en IGNORE_DIRS (ej: .git)
    os.makedirs(os.path.join(d, ".git", "objects"), exist_ok=True)
    r = client.delete(f"{base}/dir", params={"path": ".git"})
    assert r.status_code == 403, (r.status_code, r.text)
    assert os.path.isdir(os.path.join(d, ".git"))

    # 7) Abortar si el árbol contiene un archivo sensible anidado (.env)
    _touch(d, "config/.env", "SECRET=1")
    _touch(d, "config/settings.py")
    r = client.delete(f"{base}/dir", params={"path": "config"})
    assert r.status_code == 403, (r.status_code, r.text)
    assert os.path.isfile(os.path.join(d, "config", ".env")), "no debe borrar carpeta con secretos"

    # 8) Traversal rechazado (400)
    r = client.delete(f"{base}/dir", params={"path": "../"})
    assert r.status_code == 400, (r.status_code, r.text)

    print("OK")


if __name__ == "__main__":
    main()
