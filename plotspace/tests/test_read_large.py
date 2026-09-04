"""Test del override force en /files/read para archivos grandes."""
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

    # Archivo de ~1.5 MB (texto ASCII, sin NUL → no se confunde con binario)
    big = "a" * (1536 * 1024)
    with open(os.path.join(d, "big.txt"), "w", encoding="utf-8") as f:
        f.write(big)
    # Archivo de ~6 MB (supera el tope duro)
    huge = "b" * (6 * 1024 * 1024)
    with open(os.path.join(d, "huge.txt"), "w", encoding="utf-8") as f:
        f.write(huge)

    # 1) Sin force → 413
    r = client.get(f"{base}/read", params={"path": "big.txt"})
    assert r.status_code == 413, (r.status_code, r.text)

    # 2) Con force=true y <5MB → 200 con content
    r = client.get(f"{base}/read", params={"path": "big.txt", "force": "true"})
    assert r.status_code == 200, (r.status_code, r.text)
    j = r.json()
    assert "content" in j and len(j["content"]) == len(big), (len(j.get("content", "")), len(big))

    # 3) >5MB con force → 413 igual (tope duro)
    r = client.get(f"{base}/read", params={"path": "huge.txt", "force": "true"})
    assert r.status_code == 413, (r.status_code, r.text)

    print("OK")


if __name__ == "__main__":
    main()
