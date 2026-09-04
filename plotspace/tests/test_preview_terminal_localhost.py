"""GET /api/orchestrator/preview/{pid}/terminal/{tid}/localhost — la fuente del
salto del Web Preview al maximizar/seleccionar la card de un agente."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient

import plotspace.core.dev_detect as dd
from plotspace.tests._harness import fresh_db


def _client():
    fresh_db()
    import plotspace.main as main
    from plotspace.core import auth
    client = TestClient(main.app)
    client.headers.update({'Cookie': f'jarvis_token={auth.obtener_token()}'})
    return client


def test_snapshot_vivo_responde_el_server_de_esa_terminal():
    client = _client()
    dd._detectados.clear()
    dd._detectados[9] = {
        'http://localhost:5173': {'terminal_id': 4, 'terminal_nombre': 'A'},
        'http://localhost:8100': {'terminal_id': 5, 'terminal_nombre': 'B', 'tipo': 'server'},
    }
    r = client.get('/api/orchestrator/preview/9/terminal/5/localhost')
    assert r.status_code == 200
    assert r.json() == {'url': 'http://localhost:8100', 'tipo': 'server'}
    dd._detectados.clear()


def test_terminal_sin_localhost_devuelve_url_null():
    client = _client()
    dd._detectados.clear()
    # terminal inexistente en la DB fresca → ni snapshot ni pane que escanear
    r = client.get('/api/orchestrator/preview/9/terminal/12345/localhost')
    assert r.status_code == 200
    assert r.json() == {'url': None}
