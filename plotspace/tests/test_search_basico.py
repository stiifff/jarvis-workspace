"""Test: GET /files/search — matches básicos (un término literal en varios archivos)."""
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

    # Estructura de archivos de prueba
    os.makedirs(os.path.join(d, "src"), exist_ok=True)
    with open(os.path.join(d, "src", "a.py"), "w", encoding="utf-8") as f:
        f.write("import os\nx = buscar_esto\nprint(x)\n")
    with open(os.path.join(d, "b.txt"), "w", encoding="utf-8") as f:
        f.write("nada relevante\nbuscar_esto aparece aca\notra buscar_esto linea\n")
    with open(os.path.join(d, "c.md"), "w", encoding="utf-8") as f:
        f.write("# titulo\nsin coincidencias\n")

    client, pid = make_client_and_project(d)

    r = client.get(f"/api/projects/{pid}/files/search", params={"q": "buscar_esto"})
    assert r.status_code == 200, f"status {r.status_code}: {r.text}"
    data = r.json()

    # Contrato JSON
    assert data["query"] == "buscar_esto", data
    assert "results" in data and isinstance(data["results"], list), data
    assert "total" in data and "truncated" in data, data
    assert data.get("error") is None, data

    # Indexar resultados por archivo (paths relativos, separador /)
    by_file = {res["file"]: res for res in data["results"]}
    assert "src/a.py" in by_file, by_file
    assert "b.txt" in by_file, by_file
    assert "c.md" not in by_file, "c.md no tiene matches, no debe aparecer"

    # a.py: 1 match en la linea 2
    a = by_file["src/a.py"]
    assert len(a["matches"]) == 1, a
    m = a["matches"][0]
    assert m["line"] == 2, m
    # "x = buscar_esto" -> 'buscar_esto' empieza en index 4 (0-based) -> col 5 (1-based)
    assert m["col"] == 5, m
    assert m["length"] == len("buscar_esto"), m
    assert "buscar_esto" in m["text"], m

    # b.txt: 2 matches (lineas 2 y 3)
    b = by_file["b.txt"]
    assert len(b["matches"]) == 2, b
    assert [mm["line"] for mm in b["matches"]] == [2, 3], b

    # total = suma de matches
    assert data["total"] == 3, data
    assert data["truncated"] is False, data

    print("OK")


if __name__ == "__main__":
    main()
