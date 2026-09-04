"""Test de POST /api/projects/{id}/files/rename (rename + move)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from plotspace.tests._harness import fresh_db, make_client_and_project


def _touch(d, rel, content="x"):
    full = os.path.join(d, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True) if os.path.dirname(rel) else None
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    base = f"/api/projects/{pid}/files"

    # 1) Rename simple de archivo
    _touch(d, "viejo.txt", "hola")
    r = client.post(f"{base}/rename", json={"src": "viejo.txt", "dst": "nuevo.txt"})
    assert r.status_code == 200, (r.status_code, r.text)
    assert not os.path.exists(os.path.join(d, "viejo.txt"))
    assert os.path.isfile(os.path.join(d, "nuevo.txt"))

    # 2) Mover archivo a subcarpeta existente (rename == move)
    os.makedirs(os.path.join(d, "destino"), exist_ok=True)
    r = client.post(f"{base}/rename", json={"src": "nuevo.txt", "dst": "destino/movido.txt"})
    assert r.status_code == 200, (r.status_code, r.text)
    assert os.path.isfile(os.path.join(d, "destino", "movido.txt"))

    # 3) Renombrar carpeta
    os.makedirs(os.path.join(d, "carpeta"), exist_ok=True)
    r = client.post(f"{base}/rename", json={"src": "carpeta", "dst": "carpeta2"})
    assert r.status_code == 200, (r.status_code, r.text)
    assert os.path.isdir(os.path.join(d, "carpeta2"))

    # 4) 404 si src no existe
    r = client.post(f"{base}/rename", json={"src": "fantasma.txt", "dst": "z.txt"})
    assert r.status_code == 404, (r.status_code, r.text)

    # 5) 409 si dst ya existe
    _touch(d, "uno.txt")
    _touch(d, "dos.txt")
    r = client.post(f"{base}/rename", json={"src": "uno.txt", "dst": "dos.txt"})
    assert r.status_code == 409, (r.status_code, r.text)

    # 6) Guard de sensibles en SRC (no se puede renombrar .env)
    _touch(d, ".env", "SECRET=1")
    r = client.post(f"{base}/rename", json={"src": ".env", "dst": "publico.txt"})
    assert r.status_code == 403, (r.status_code, r.text)
    assert os.path.isfile(os.path.join(d, ".env"))

    # 7) Guard de sensibles en DST (no se puede mover algo a un nombre sensible)
    _touch(d, "comun.txt")
    r = client.post(f"{base}/rename", json={"src": "comun.txt", "dst": ".env"})
    assert r.status_code == 403, (r.status_code, r.text)
    assert os.path.isfile(os.path.join(d, "comun.txt"))

    # 8) Traversal en dst rechazado (400)
    _touch(d, "fuga.txt")
    r = client.post(f"{base}/rename", json={"src": "fuga.txt", "dst": "../fuera.txt"})
    assert r.status_code == 400, (r.status_code, r.text)

    print("OK")


if __name__ == "__main__":
    main()
