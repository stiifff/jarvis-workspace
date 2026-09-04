"""Test: GET /files/search — la columna se reporta en unidades UTF-16 (Monaco),
no en bytes UTF-8. Must-fix de la crítica de Fase 6."""
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

    # "café → " antes de TARGET. 'café' = 4 code points (UTF-16: c,a,f,é = 4 units),
    # ' → ' = espacio + flecha (1 unit) + espacio = 3 units. Total prefijo = 7 units.
    # En bytes UTF-8: 'café'=5 bytes (é=2), ' → '= 1 + 3 + 1 = 5 bytes -> prefijo 10 bytes.
    linea = "café → TARGET aca"
    with open(os.path.join(d, "u.txt"), "w", encoding="utf-8") as f:
        f.write(linea + "\n")

    client, pid = make_client_and_project(d)
    r = client.get(f"/api/projects/{pid}/files/search", params={"q": "TARGET"})
    assert r.status_code == 200, r.text
    data = r.json()
    m = data["results"][0]["matches"][0]

    # Columna 1-based en UTF-16: prefijo "café → " son 7 unidades → col 8.
    # (Si estuviera midiendo bytes daría 11, el bug que el must-fix corrige.)
    assert m["col"] == 8, f"col debe ser 8 (UTF-16), vino {m['col']}"
    assert m["length"] == len("TARGET"), m

    # Emoji fuera del BMP (2 unidades UTF-16): "🚀X TARGET"
    linea2 = "🚀X TARGET"
    with open(os.path.join(d, "e.txt"), "w", encoding="utf-8") as f:
        f.write(linea2 + "\n")
    r2 = client.get(f"/api/projects/{pid}/files/search", params={"q": "TARGET"})
    m2 = [res for res in r2.json()["results"] if res["file"] == "e.txt"][0]["matches"][0]
    # 🚀 = 2 units, X = 1, espacio = 1 → prefijo 4 units → col 5
    assert m2["col"] == 5, f"col con emoji debe ser 5 (UTF-16), vino {m2['col']}"

    print("OK")


if __name__ == "__main__":
    main()
