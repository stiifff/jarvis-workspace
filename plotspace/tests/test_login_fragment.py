"""
/login: el token va por FRAGMENTO (#token=), no por query (hallazgo #10).

El fragmento nunca viaja al server → no queda en el access-log de uvicorn ni en
el history/scrollback. /login sin query sirve una página que lee #token= y lo
POSTea. La forma legacy /login?token= se mantiene por compatibilidad.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient

from plotspace.tests._harness import fresh_db


def _client_y_token():
    fresh_db()
    import plotspace.main as main
    from plotspace.core import auth
    return TestClient(main.app), auth.obtener_token()


def test_login_sin_query_sirve_pagina_de_fragmento():
    client, _ = _client_y_token()
    r = client.get('/login')
    assert r.status_code == 200
    assert 'text/html' in r.headers.get('content-type', '')
    # La página lee el token del fragmento y lo POSTea (no lo manda por query)
    assert 'location.hash' in r.text
    assert '/api/auth/login' in r.text


def test_login_query_legacy_valido_redirige_y_setea_cookie():
    client, token = _client_y_token()
    r = client.get(f'/login?token={token}', follow_redirects=False)
    assert r.status_code == 302
    assert 'jarvis_token=' in r.headers.get('set-cookie', '')


def test_login_query_invalido_da_401():
    client, _ = _client_y_token()
    r = client.get('/login?token=token-falso', follow_redirects=False)
    assert r.status_code == 401


if __name__ == '__main__':
    import traceback
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith('test_') and callable(fn):
            try:
                fn(); print(f'ok  {nombre}')
            except Exception:
                fallos += 1; print(f'FAIL {nombre}'); traceback.print_exc()
    sys.exit(1 if fallos else 0)
