"""
Test: projects_files debe exponer shutil y las constantes de límites
preparadas en la Fase 1 (spec §4.1, §6). Aún no se usan; se declaran una vez.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.tests._harness import fresh_db
import plotspace.routers.projects_files as pf


def main():
    fresh_db()

    # shutil importado (lo necesitan content-search y borrado recursivo)
    assert hasattr(pf, "shutil"), "falta 'import shutil' en projects_files"
    assert pf.shutil.__name__ == "shutil", "pf.shutil no es el módulo shutil"

    # Constantes de límites con los valores del spec
    esperados = {
        "MAX_UPLOAD_TOTAL":       200 * 1024 * 1024,
        "MAX_UPLOAD_FILES":       2000,
        "MAX_SEARCH_RESULTS":     500,
        "MAX_MATCHES_PER_FILE":   50,
        "SEARCH_TIMEOUT_SECS":    15,
        "MAX_QUERY_LEN":          200,
        "MAX_ZIP_RATIO":          100,
    }
    for nombre, valor in esperados.items():
        assert hasattr(pf, nombre), f"falta constante {nombre}"
        actual = getattr(pf, nombre)
        assert actual == valor, f"{nombre}: esperaba {valor}, recibí {actual}"

    print("OK")


if __name__ == "__main__":
    main()
