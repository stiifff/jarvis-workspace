"""Fase 4 — GET /files/stat?path liviano: {path, mtime, size}, sin content."""
import os
import sys
import tempfile

# Asegurar imports absolutos 'plotspace.*' al correr el test como script suelto.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from plotspace.tests._harness import fresh_db, make_client_and_project


def main():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    fpath = os.path.join(d, "data.json")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write('{"a":1}')

    # Caso feliz
    r = client.get(f"/api/projects/{pid}/files/stat?path=data.json")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "data.json", body
    assert "content" not in body, f"stat NO debe transferir content: {body}"
    assert abs(body["mtime"] - os.path.getmtime(fpath)) < 0.01, body
    assert body["size"] == os.path.getsize(fpath), body

    # No existe -> 404
    r = client.get(f"/api/projects/{pid}/files/stat?path=no-existe.txt")
    assert r.status_code == 404, r.text

    # Es carpeta -> 404 (stat es de archivos)
    os.makedirs(os.path.join(d, "sub"))
    r = client.get(f"/api/projects/{pid}/files/stat?path=sub")
    assert r.status_code == 404, r.text

    # Traversal -> 400 (pasa por _safe_join)
    r = client.get(f"/api/projects/{pid}/files/stat?path=../../etc/passwd")
    assert r.status_code == 400, r.text

    print("OK")


if __name__ == "__main__":
    main()
