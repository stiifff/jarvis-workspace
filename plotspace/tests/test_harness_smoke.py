"""Smoke del harness: DB aislada + proyecto + GET /files/tree -> 200."""
import os
import sys
import tempfile

# Permitir `python3 plotspace/tests/test_harness_smoke.py` desde la raíz: el
# intérprete pone plotspace/tests en sys.path[0], no la raíz, así que el import
# absoluto 'plotspace.*' fallaría sin esto (mismo patrón que _harness.py).
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from plotspace.tests._harness import fresh_db, make_client_and_project
from plotspace.core import database


def main():
    # fresh_db apunta a un tempfile, NO a jarvis.db
    db_path = fresh_db()
    assert database.DB_PATH == db_path, "DB_PATH no quedó repuntado al tempfile"
    assert "jarvis_test_" in os.path.basename(db_path), "el tempfile no tiene el prefijo esperado"
    assert os.path.basename(db_path) != "jarvis.db", "fresh_db apuntó a la DB real"

    # Proyecto temporal con un archivo dentro
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "hola.txt"), "w", encoding="utf-8") as f:
        f.write("hola mundo")

    client, pid = make_client_and_project(d)
    assert isinstance(pid, int) and pid >= 1, f"pid inválido: {pid!r}"

    r = client.get(f"/api/projects/{pid}/files/tree")
    assert r.status_code == 200, f"tree status {r.status_code}: {r.text}"
    data = r.json()
    assert data["root"] == d, f"root inesperado: {data.get('root')!r}"
    names = [c["name"] for c in data["children"]]
    assert "hola.txt" in names, f"el archivo no aparece en el árbol: {names!r}"

    print("OK")


if __name__ == "__main__":
    main()
