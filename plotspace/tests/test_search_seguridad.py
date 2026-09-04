"""Test: GET /files/search — binarios ignorados, regex inválida sin 500,
sensibles/ignore-dirs excluidos, query demasiado larga."""
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

    # Archivo de texto con el término
    with open(os.path.join(d, "ok.txt"), "w", encoding="utf-8") as f:
        f.write("secreto aca\n")
    # Archivo binario: NUL en los primeros bytes, contiene el término en ASCII
    with open(os.path.join(d, "blob.bin"), "wb") as f:
        f.write(b"AB\x00secreto\x00CD")
    # Archivo sensible: NO debe aparecer aunque tenga el término
    with open(os.path.join(d, ".env"), "w", encoding="utf-8") as f:
        f.write("API_KEY=secreto\n")
    # Dir ignorado: NO debe aparecer
    os.makedirs(os.path.join(d, "node_modules"), exist_ok=True)
    with open(os.path.join(d, "node_modules", "x.js"), "w", encoding="utf-8") as f:
        f.write("secreto en dependencia\n")

    client, pid = make_client_and_project(d)

    # Binario ignorado + sensibles + ignore-dirs: solo ok.txt
    r = client.get(f"/api/projects/{pid}/files/search", params={"q": "secreto"})
    assert r.status_code == 200, r.text
    data = r.json()
    files = {res["file"] for res in data["results"]}
    assert files == {"ok.txt"}, f"esperaba solo ok.txt, vino {files}"
    assert data["total"] == 1, data

    # Regex inválida → 200 con {error}, NO 500
    r2 = client.get(f"/api/projects/{pid}/files/search",
                    params={"q": "(no cierra", "regex": "true"})
    assert r2.status_code == 200, f"esperaba 200, vino {r2.status_code}: {r2.text}"
    d2 = r2.json()
    assert d2["error"], f"esperaba campo error, vino {d2}"
    assert d2["results"] == [] and d2["total"] == 0, d2

    # Query demasiado larga → 400
    r3 = client.get(f"/api/projects/{pid}/files/search", params={"q": "x" * 201})
    assert r3.status_code == 400, f"esperaba 400, vino {r3.status_code}: {r3.text}"

    print("OK")


if __name__ == "__main__":
    main()
