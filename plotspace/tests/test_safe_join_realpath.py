"""
Test: _safe_join debe rechazar symlinks que apuntan fuera del proyecto
(defensa anti zip-slip / anti-traversal vía realpath, spec §4.1 / §8).
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.tests._harness import fresh_db
from plotspace.routers.projects_files import _safe_join

from fastapi import HTTPException


def _expect_400(base, rel, msg):
    try:
        _safe_join(base, rel)
    except HTTPException as e:
        assert e.status_code == 400, f"{msg}: esperaba 400, recibí {e.status_code}"
        return
    raise AssertionError(f"{msg}: esperaba HTTPException 400, no se lanzó nada")


def main():
    fresh_db()
    base = tempfile.mkdtemp()
    outside = tempfile.mkdtemp()

    # (a) ruta normal dentro del proyecto -> OK
    full = _safe_join(base, "sub/archivo.txt")
    assert full == os.path.normpath(os.path.join(base, "sub/archivo.txt")), \
        "ruta normal: no resolvió donde esperaba"

    # (b) traversal con .. -> 400 (regresión: ya lo cubre normpath)
    _expect_400(base, "../escape.txt", "traversal con ..")

    # (c) symlink que escapa del proyecto -> 400 (NUEVO: hoy debe fallar)
    # Creamos base/link -> outside ; pedir base/link/secreto.txt resuelve fuera de base.
    link = os.path.join(base, "link")
    os.symlink(outside, link)
    with open(os.path.join(outside, "secreto.txt"), "w") as f:
        f.write("secreto")
    _expect_400(base, "link/secreto.txt", "symlink que escapa")

    print("OK")


if __name__ == "__main__":
    main()
