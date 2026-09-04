# plotspace/tests/test_extract_zip.py
"""POST /files/extract-zip — extraer un .zip que YA vive en el proyecto
(click derecho en el árbol → "Extraer en «nombre»/").

Extrae EN MODO CARPETA al lado del zip. El .zip NUNCA se borra (pedido del
usuario 2026-07-16): quedan la carpeta nueva y el zip original conviviendo.
"""
import io
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from plotspace.tests._harness import fresh_db, make_client_and_project


def _zip_bytes(miembros):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, data in miembros.items():
            z.writestr(nombre, data)
    return buf.getvalue()


def _plantar_zip(d, rel, miembros):
    full = os.path.join(d, rel)
    os.makedirs(os.path.dirname(full) or d, exist_ok=True)
    with open(full, 'wb') as f:
        f.write(_zip_bytes(miembros))


def test_extrae_al_lado_y_el_zip_queda():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    _plantar_zip(d, "sub/cosas.zip", {"a.txt": "aaa", "b/x.txt": "xxx"})

    r = client.post(f"/api/projects/{pid}/files/extract-zip", json={"path": "sub/cosas.zip"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["carpeta"] == "cosas", body
    assert sorted(body["subidos"]) == ["sub/cosas/a.txt", "sub/cosas/b/x.txt"], body
    assert os.path.isfile(os.path.join(d, "sub", "cosas", "a.txt"))
    assert os.path.isfile(os.path.join(d, "sub", "cosas", "b", "x.txt"))
    assert os.path.isfile(os.path.join(d, "sub", "cosas.zip"))   # el zip NO se toca


def test_extraccion_sucia_tambien_conserva_el_zip():
    """Con rechazados (miembro sensible), lo extraíble se extrae y el zip queda."""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    _plantar_zip(d, "pack.zip", {"a.txt": "aaa", ".env": "SECRETO=1"})

    r = client.post(f"/api/projects/{pid}/files/extract-zip", json={"path": "pack.zip"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rechazados"], body
    assert os.path.isfile(os.path.join(d, "pack.zip"))
    assert os.path.isfile(os.path.join(d, "pack", "a.txt"))


def test_siempre_carpeta_con_el_nombre_del_zip():
    """release.zip con raíz interna proj/ → carpeta release/ con proj/ adentro."""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    _plantar_zip(d, "sub/release.zip", {"proj/main.py": "x = 1"})

    r = client.post(f"/api/projects/{pid}/files/extract-zip", json={"path": "sub/release.zip"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["carpeta"] == "release", body
    assert body["subidos"] == ["sub/release/proj/main.py"], body


def test_raiz_con_mismo_nombre_no_anida_doble():
    """proj.zip que contiene proj/... → sub/proj/main.py (NO sub/proj/proj/)."""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    _plantar_zip(d, "sub/proj.zip", {"proj/main.py": "x = 1"})

    r = client.post(f"/api/projects/{pid}/files/extract-zip", json={"path": "sub/proj.zip"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["carpeta"] == "proj", body
    assert body["subidos"] == ["sub/proj/main.py"], body
    assert not os.path.exists(os.path.join(d, "sub", "proj", "proj"))
    assert os.path.isfile(os.path.join(d, "sub", "proj.zip"))   # el zip NO se toca


def test_no_es_zip_400():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    with open(os.path.join(d, "falso.zip"), 'w') as f:
        f.write("esto no es un zip")

    r = client.post(f"/api/projects/{pid}/files/extract-zip", json={"path": "falso.zip"})
    assert r.status_code == 400, r.text
    assert os.path.isfile(os.path.join(d, "falso.zip"))   # no se toca


def test_inexistente_404():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    r = client.post(f"/api/projects/{pid}/files/extract-zip", json={"path": "nada.zip"})
    assert r.status_code == 404, r.text


def test_traversal_rechazado():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    r = client.post(f"/api/projects/{pid}/files/extract-zip", json={"path": "../afuera.zip"})
    assert r.status_code == 400, r.text


def test_extraidos_quedan_como_creados_ui():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    _plantar_zip(d, "pack.zip", {"a.txt": "aaa", "b.txt": "bbb"})

    r = client.post(f"/api/projects/{pid}/files/extract-zip", json={"path": "pack.zip"})
    assert r.status_code == 200, r.text
    tree = client.get(f"/api/projects/{pid}/files/tree").json()
    creados = set(tree.get("creados") or [])
    assert {"pack/a.txt", "pack/b.txt"} <= creados, tree.get("creados")


if __name__ == "__main__":
    test_extrae_al_lado_y_el_zip_queda()
    test_extraccion_sucia_tambien_conserva_el_zip()
    test_siempre_carpeta_con_el_nombre_del_zip()
    test_raiz_con_mismo_nombre_no_anida_doble()
    test_no_es_zip_400()
    test_inexistente_404()
    test_traversal_rechazado()
    test_extraidos_quedan_como_creados_ui()
    print("OK")
