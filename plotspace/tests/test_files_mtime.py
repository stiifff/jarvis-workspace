"""Fase 4 — read/save devuelven mtime entero/float coherente con el disco."""
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

    # Crear un archivo en disco directamente
    fpath = os.path.join(d, "hola.txt")
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("contenido inicial")
    disk_mtime = os.path.getmtime(fpath)

    # read incluye mtime
    r = client.get(f"/api/projects/{pid}/files/read?path=hola.txt")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "mtime" in body, f"read sin mtime: {body}"
    assert abs(body["mtime"] - disk_mtime) < 0.01, f"mtime read != disco: {body['mtime']} vs {disk_mtime}"
    assert body["content"] == "contenido inicial"

    # save incluye mtime y refleja el nuevo valor en disco
    r = client.post(f"/api/projects/{pid}/files/save",
                    json={"path": "hola.txt", "content": "nuevo contenido"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "mtime" in body, f"save sin mtime: {body}"
    assert abs(body["mtime"] - os.path.getmtime(fpath)) < 0.01, \
        f"mtime save != disco: {body['mtime']} vs {os.path.getmtime(fpath)}"

    # read de nuevo: el mtime subió respecto al inicial
    r = client.get(f"/api/projects/{pid}/files/read?path=hola.txt")
    assert r.json()["mtime"] >= disk_mtime

    print("OK")


if __name__ == "__main__":
    main()
