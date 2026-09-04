# Contratos del "modo app" (shell de escritorio) — Hito 1 del Escalón A.
#
# El shell lanza el backend con JARVIS_PORT propio y se loguea solo vía
# GET /login?token=<token> (lee el token del data dir y abre el webview ya
# autenticado). Estos tests fijan ese contrato: si alguien lo rompe, el shell
# de escritorio deja de poder abrir la app.

import importlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))


def test_puerto_jarvis_sigue_env_en_orchestrator():
    """El guard de embebibilidad (localhost:<puerto de Jarvis>) sigue a
    JARVIS_PORT — con la app en un puerto dinámico, `localhost:3000` deja de
    ser especial."""
    import plotspace.routers.orchestrator as orch
    previo = os.environ.get('JARVIS_PORT')
    try:
        os.environ['JARVIS_PORT'] = '5432'
        o2 = importlib.reload(orch)
        assert o2._JARVIS_PORT == '5432'
        assert o2._fuente_permite_jarvis('http://localhost:5432')
        assert not o2._fuente_permite_jarvis('http://localhost:3000')
        os.environ.pop('JARVIS_PORT', None)
        assert importlib.reload(orch)._JARVIS_PORT == '3000'
    finally:
        if previo is None:
            os.environ.pop('JARVIS_PORT', None)
        else:
            os.environ['JARVIS_PORT'] = previo
        importlib.reload(orch)


def test_puerto_jarvis_sigue_env_en_dev_detect():
    """dev_detect excluye al puerto REAL de Jarvis (no al 3000 fijo) de la
    detección de dev servers y los demos /static."""
    import plotspace.core.dev_detect as dd
    previo = os.environ.get('JARVIS_PORT')
    try:
        os.environ['JARVIS_PORT'] = '5432'
        assert importlib.reload(dd).PUERTO_JARVIS == 5432
        os.environ.pop('JARVIS_PORT', None)
        assert importlib.reload(dd).PUERTO_JARVIS == 3000
    finally:
        if previo is None:
            os.environ.pop('JARVIS_PORT', None)
        else:
            os.environ['JARVIS_PORT'] = previo
        importlib.reload(dd)


def test_contrato_auto_login_del_shell():
    """GET /login?token=<válido> → cookie httpOnly + redirect a '/' (lo que usa
    el shell); token inválido → 401; sin token → página que consume #token=."""
    from fastapi.testclient import TestClient

    import plotspace.core.auth as auth
    import plotspace.main as main

    # Armado por concatenación para no disparar el escáner anti-secretos
    # (regla del repo: los secretos falsos de los tests se concatenan).
    token_fake = 'token-de-' + 'prueba-contrato'
    token_previo = auth._TOKEN
    env_previo = os.environ.get('JARVIS_TOKEN')
    try:
        auth._TOKEN = None
        os.environ['JARVIS_TOKEN'] = token_fake
        client = TestClient(main.app)   # sin context manager: no corre lifespan

        ok = client.get('/login', params={'token': token_fake},
                        follow_redirects=False)
        assert ok.status_code == 302
        assert ok.headers['location'] == '/'
        set_cookie = ok.headers.get('set-cookie', '')
        assert 'jarvis_token=' in set_cookie
        assert 'HttpOnly' in set_cookie

        mal = client.get('/login', params={'token': 'nope'}, follow_redirects=False)
        assert mal.status_code == 401

        pagina = client.get('/login')
        assert pagina.status_code == 200
        assert 'token=' in pagina.text   # el JS que consume el fragmento
    finally:
        auth._TOKEN = token_previo
        if env_previo is None:
            os.environ.pop('JARVIS_TOKEN', None)
        else:
            os.environ['JARVIS_TOKEN'] = env_previo
