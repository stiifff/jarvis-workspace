"""El mount /static sirve index.html en URLs de DIRECTORIO (html=True).

Los agentes anuncian sus demos como 'localhost:3000/static/<dir>/' (sin
index.html) — sin html=True el iframe del Web Preview recibía 404 y el demo
"no se veía" (pedido del usuario 2026-07-11)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient

from plotspace.tests._harness import fresh_db


def test_static_monta_con_html_true():
    fresh_db()
    import plotspace.main as main
    mount = next(r for r in main.app.routes if getattr(r, 'name', '') == 'static')
    assert mount.app.html is True, 'StaticFiles necesita html=True para servir /static/<dir>/'


def test_static_directorio_sirve_index():
    fresh_db()
    import plotspace.main as main
    client = TestClient(main.app)
    # frontend/ tiene index.html en la raíz → /static/ debe servirlo (200),
    # igual que cualquier /static/<demo>/ con su index.html adentro.
    r = client.get('/static/')
    assert r.status_code == 200
    assert 'text/html' in r.headers.get('content-type', '')
