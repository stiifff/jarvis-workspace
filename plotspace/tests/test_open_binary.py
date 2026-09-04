"""Test de deteccion de binarios/imagenes en /files/read y del endpoint /files/raw."""
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

    # PNG falso: firma PNG + un NUL byte (suficiente para la heuristica de imagen por extension)
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR\x00\x00\x00\x01"
    with open(os.path.join(d, "logo.png"), "wb") as f:
        f.write(png_bytes)
    # Binario con NUL en los primeros 1024 bytes, extension no-imagen
    with open(os.path.join(d, "app.bin"), "wb") as f:
        f.write(b"MZ\x00\x00\x90\x00" + b"\x01" * 64)
    # Texto normal
    with open(os.path.join(d, "hola.txt"), "w", encoding="utf-8") as f:
        f.write("hola mundo\nlínea 2 con acento é\n")

    # 1) Imagen → binary:true, kind:image, SIN content
    r = client.get(f"{base}/read", params={"path": "logo.png"})
    assert r.status_code == 200, (r.status_code, r.text)
    j = r.json()
    assert j.get("binary") is True, j
    assert j.get("kind") == "image", j
    assert "content" not in j, j

    # 2) Binario no-imagen → binary:true, kind:binary, SIN content
    r = client.get(f"{base}/read", params={"path": "app.bin"})
    assert r.status_code == 200, (r.status_code, r.text)
    j = r.json()
    assert j.get("binary") is True, j
    assert j.get("kind") == "binary", j
    assert "content" not in j, j

    # 3) Texto normal → sigue devolviendo content (sin binary)
    r = client.get(f"{base}/read", params={"path": "hola.txt"})
    assert r.status_code == 200, (r.status_code, r.text)
    j = r.json()
    assert j.get("binary") in (None, False), j
    assert "content" in j and "hola mundo" in j["content"], j

    # 4) /files/raw devuelve 200 y los bytes crudos del PNG
    r = client.get(f"{base}/raw", params={"path": "logo.png"})
    assert r.status_code == 200, (r.status_code, r.text)
    assert r.content == png_bytes, (len(r.content), len(png_bytes))

    # 5) /files/raw bloquea sensibles (.env)
    with open(os.path.join(d, ".env"), "w", encoding="utf-8") as f:
        f.write("SECRET=1\n")
    r = client.get(f"{base}/raw", params={"path": ".env"})
    assert r.status_code == 403, (r.status_code, r.text)

    # 6) /files/raw bloquea traversal
    r = client.get(f"{base}/raw", params={"path": "../../etc/passwd"})
    assert r.status_code in (400, 403, 404), (r.status_code, r.text)

    print("OK")


if __name__ == "__main__":
    main()
