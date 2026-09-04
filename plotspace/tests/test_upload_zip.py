# plotspace/tests/test_upload_zip.py
"""Fase 7 — POST /files/upload-zip extrae preservando estructura.

Modo carpeta (2026-07-16): un zip SIEMPRE se convierte en una carpeta con el
nombre del zip (sufijo -2/-3 si colisiona) con el contenido adentro — nunca
se desparrama suelto en la raíz. Si el zip ya trae una única carpeta raíz con
el MISMO nombre, esa raíz pasa a ser la carpeta (sin anidado doble).
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


def test_zip_extrae_estructura():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    zb = _zip_bytes({
        "proj/main.py": "print('hi')",
        "proj/lib/util.py": "x = 1",
        "proj/empty/": "",  # entrada de directorio: debe ignorarse sin error
    })
    r = client.post(
        f"/api/projects/{pid}/files/upload-zip",
        files=[("file", ("bundle.zip", zb, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    # SIEMPRE carpeta con el nombre del zip; la estructura interna va adentro
    assert body["carpeta"] == "bundle", body
    assert sorted(body["subidos"]) == ["bundle/proj/lib/util.py", "bundle/proj/main.py"], body
    assert os.path.isfile(os.path.join(d, "bundle", "proj", "main.py"))
    assert os.path.isfile(os.path.join(d, "bundle", "proj", "lib", "util.py"))


def test_zip_raiz_con_mismo_nombre_no_anida_doble():
    """mi-app.zip que contiene mi-app/... → mi-app/ directo (NO mi-app/mi-app/)."""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    zb = _zip_bytes({"mi-app/main.py": "x = 1", "mi-app/lib/u.py": "y = 2"})
    r = client.post(
        f"/api/projects/{pid}/files/upload-zip",
        files=[("file", ("mi-app.zip", zb, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["carpeta"] == "mi-app", body
    assert sorted(body["subidos"]) == ["mi-app/lib/u.py", "mi-app/main.py"], body
    assert not os.path.exists(os.path.join(d, "mi-app", "mi-app"))


def test_zip_raiz_mismo_nombre_con_colision_renombra_la_raiz():
    """Si mi-app/ ya existe, la raíz del zip se renombra a mi-app-2/ (carpeta fresca)."""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    os.makedirs(os.path.join(d, "mi-app"))

    zb = _zip_bytes({"mi-app/main.py": "x = 1"})
    r = client.post(
        f"/api/projects/{pid}/files/upload-zip",
        files=[("file", ("mi-app.zip", zb, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["carpeta"] == "mi-app-2", body
    assert body["subidos"] == ["mi-app-2/main.py"], body


def test_zip_multiraiz_se_envuelve_en_carpeta():
    """Zip con varias entradas top-level → todo cae dentro de <nombre-del-zip>/."""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    zb = _zip_bytes({
        "a.txt": "aaa",
        "b/x.txt": "xxx",
    })
    r = client.post(
        f"/api/projects/{pid}/files/upload-zip",
        files=[("file", ("cosas.zip", zb, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["carpeta"] == "cosas", body
    assert sorted(body["subidos"]) == ["cosas/a.txt", "cosas/b/x.txt"], body
    assert os.path.isfile(os.path.join(d, "cosas", "a.txt"))
    assert os.path.isfile(os.path.join(d, "cosas", "b", "x.txt"))
    # nada quedó suelto en la raíz
    assert not os.path.exists(os.path.join(d, "a.txt"))


def test_zip_archivo_unico_tambien_se_envuelve():
    """Zip con UN archivo suelto (sin carpeta) → también va a <nombre-del-zip>/."""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    zb = _zip_bytes({"readme.txt": "hola"})
    r = client.post(
        f"/api/projects/{pid}/files/upload-zip",
        files=[("file", ("notas.zip", zb, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["carpeta"] == "notas", body
    assert body["subidos"] == ["notas/readme.txt"], body


def test_zip_colision_de_carpeta_suma_sufijo():
    """Si <nombre-del-zip>/ ya existe en el destino, se usa -2, -3…"""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)
    os.makedirs(os.path.join(d, "cosas"))
    os.makedirs(os.path.join(d, "cosas-2"))

    zb = _zip_bytes({"a.txt": "aaa", "b.txt": "bbb"})
    r = client.post(
        f"/api/projects/{pid}/files/upload-zip",
        files=[("file", ("cosas.zip", zb, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["carpeta"] == "cosas-3", body
    assert os.path.isfile(os.path.join(d, "cosas-3", "a.txt"))


def test_zip_nombre_raro_cae_al_fallback():
    """Nombre de zip vacío/raro → carpeta 'zip-extraido' (nunca ruta inválida)."""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    zb = _zip_bytes({"a.txt": "aaa", "b.txt": "bbb"})
    r = client.post(
        f"/api/projects/{pid}/files/upload-zip",
        files=[("file", ("...zip", zb, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["carpeta"] == "zip-extraido", body


def test_zip_extraidos_quedan_como_creados_ui():
    """Los archivos extraídos se marcan creados-desde-la-UI (borrables en el editor)."""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    zb = _zip_bytes({"a.txt": "aaa", "b.txt": "bbb"})
    r = client.post(
        f"/api/projects/{pid}/files/upload-zip",
        files=[("file", ("pack.zip", zb, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    tree = client.get(f"/api/projects/{pid}/files/tree").json()
    creados = set(tree.get("creados") or [])
    assert {"pack/a.txt", "pack/b.txt"} <= creados, tree.get("creados")


def test_no_es_zip():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    r = client.post(
        f"/api/projects/{pid}/files/upload-zip",
        files=[("file", ("fake.zip", b"esto no es un zip", "application/zip"))],
    )
    assert r.status_code == 400, r.text


if __name__ == "__main__":
    test_zip_extrae_estructura()
    test_zip_raiz_con_mismo_nombre_no_anida_doble()
    test_zip_raiz_mismo_nombre_con_colision_renombra_la_raiz()
    test_no_es_zip()
    test_zip_multiraiz_se_envuelve_en_carpeta()
    test_zip_archivo_unico_tambien_se_envuelve()
    test_zip_colision_de_carpeta_suma_sufijo()
    test_zip_nombre_raro_cae_al_fallback()
    test_zip_extraidos_quedan_como_creados_ui()
    print("OK")
