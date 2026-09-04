# plotspace/tests/test_upload_zip_seguridad.py
"""Fase 7 — POST /files/upload-zip rechaza zip-slip, sensibles, IGNORE_DIRS y zip-bomb."""
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


def _subir(client, pid, miembros):
    zb = _zip_bytes(miembros)
    r = client.post(
        f"/api/projects/{pid}/files/upload-zip",
        files=[("file", ("b.zip", zb, "application/zip"))],
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_zip_slip_rechazado():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    body = _subir(client, pid, {"../../evil.txt": "pwned"})
    assert body["subidos"] == [], body
    assert any(x["motivo"] == "ruta inválida" for x in body["rechazados"]), body
    parent = os.path.dirname(d.rstrip("/"))
    assert not os.path.exists(os.path.join(parent, "evil.txt"))


def test_zip_slip_un_nivel_tampoco_escapa_de_la_carpeta():
    """Un solo '../' colapsaría DENTRO del proyecto (escapando de la carpeta
    envoltorio) — también se rechaza explícitamente."""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    body = _subir(client, pid, {"../evil.txt": "pwned", "ok.txt": "bien"})
    assert body["subidos"] == ["b/ok.txt"], body
    assert any(x["motivo"] == "ruta inválida" for x in body["rechazados"]), body
    assert not os.path.exists(os.path.join(d, "evil.txt"))
    assert not os.path.exists(os.path.join(d, "b", "evil.txt"))


def test_zip_env_rechazado():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    body = _subir(client, pid, {"cfg/.env": "SECRET=1"})
    assert body["subidos"] == [], body
    assert any(x["motivo"] == "archivo sensible" for x in body["rechazados"]), body
    assert not os.path.exists(os.path.join(d, "cfg", ".env"))


def test_zip_ignore_dir_rechazado():
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    body = _subir(client, pid, {".git/config": "[core]", "node_modules/x/i.js": "1"})
    assert body["subidos"] == [], body
    motivos = {x["motivo"] for x in body["rechazados"]}
    assert motivos == {"carpeta ignorada"}, body
    assert not os.path.exists(os.path.join(d, ".git"))
    assert not os.path.exists(os.path.join(d, "node_modules"))


def test_zip_bomb_ratio_rechazado():
    """Un zip muy compresible (todo ceros) dispara el tope por ratio o por total."""
    fresh_db()
    d = tempfile.mkdtemp()
    client, pid = make_client_and_project(d)

    # 50 archivos de 1 MB de ceros: comprimen muchísimo -> ratio alto.
    miembros = {f"f/{i}.bin": b"\x00" * (1024 * 1024) for i in range(50)}
    body = _subir(client, pid, miembros)
    motivos = {x["motivo"] for x in body["rechazados"]}
    assert any("ratio" in m or "supera" in m for m in motivos), body
    # No escribió los 50 MB: se cortó antes.
    escritos = body["subidos"]
    assert len(escritos) < 50, body


if __name__ == "__main__":
    test_zip_slip_rechazado()
    test_zip_slip_un_nivel_tampoco_escapa_de_la_carpeta()
    test_zip_env_rechazado()
    test_zip_ignore_dir_rechazado()
    test_zip_bomb_ratio_rechazado()
    print("OK")
