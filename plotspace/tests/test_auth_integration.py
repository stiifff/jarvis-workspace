"""
Test de integración del candado: token-gate + Host + CORS sobre la app real.

Complementa test_auth_origin (que prueba las funciones puras): acá se ejerce
el middleware montado en main.app con TestClient. Cubre los gaps que la review
marcó sin regresión (401, anti-rebinding, CORS no-reflejante).

Patrón de test_editor_standalone: fresh_db() repunta la DB a un tempfile antes
de importar la app. El token va en el header Cookie explícito (robusto entre
versiones de httpx).
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


def _cookie(token):
    return {'Cookie': f'jarvis_token={token}'}


def test_api_sin_cookie_da_401():
    client, _ = _client_y_token()
    assert client.get('/api/projects').status_code == 401


def test_api_con_cookie_valida_ok():
    client, token = _client_y_token()
    r = client.get('/api/projects', headers=_cookie(token))
    assert r.status_code == 200, r.text[:200]


def test_api_con_cookie_invalida_da_401():
    client, _ = _client_y_token()
    r = client.get('/api/projects', headers={'Cookie': 'jarvis_token=token-falso'})
    assert r.status_code == 401


def test_host_externo_rechazado_400():
    # DNS-rebinding: un dominio del atacante resolviendo a 127.0.0.1
    client, token = _client_y_token()
    r = client.get('/api/projects', headers={**_cookie(token), 'Host': 'evil.attacker.com'})
    assert r.status_code == 400


def test_host_localhost_ok():
    client, token = _client_y_token()
    r = client.get('/api/projects', headers={**_cookie(token), 'Host': 'localhost:3000'})
    assert r.status_code == 200


def test_cors_no_refleja_origin_externo():
    client, token = _client_y_token()
    r = client.get('/api/projects', headers={**_cookie(token), 'Origin': 'http://evil.com'})
    assert r.headers.get('access-control-allow-origin') != 'http://evil.com'


def test_cors_refleja_localhost():
    client, token = _client_y_token()
    r = client.get('/api/projects', headers={**_cookie(token), 'Origin': 'http://localhost:3000'})
    assert r.headers.get('access-control-allow-origin') == 'http://localhost:3000'


def test_cors_no_refleja_ip_publica():
    # El regex viejo matcheaba CUALQUIER IPv4: una web en una IP pública cruda
    # quedaba reflejada con credentials. Ahora solo loopback + LAN privada.
    client, token = _client_y_token()
    r = client.get('/api/projects', headers={**_cookie(token), 'Origin': 'http://93.184.216.34'})
    assert r.headers.get('access-control-allow-origin') != 'http://93.184.216.34'


def test_cors_refleja_lan_privada():
    client, token = _client_y_token()
    r = client.get('/api/projects', headers={**_cookie(token), 'Origin': 'http://192.168.1.50:3000'})
    assert r.headers.get('access-control-allow-origin') == 'http://192.168.1.50:3000'


# ─── CSRF: Origin en mutaciones (defensa en profundidad del lado HTTP) ────────

def test_mutacion_origin_externo_da_403():
    # POST con cookie válida pero Origin cross-site (web maliciosa) → bloqueado
    # ANTES de rutear, sin importar el body.
    client, token = _client_y_token()
    r = client.post('/api/projects', json={}, headers={**_cookie(token), 'Origin': 'http://evil.com'})
    assert r.status_code == 403


def test_mutacion_sin_origin_pasa_el_gate():
    # Cliente no-browser (curl) o navegación same-origin sin Origin: no se
    # bloquea por CSRF (puede fallar luego por validación de body, pero no 403/401).
    client, token = _client_y_token()
    r = client.post('/api/projects', json={}, headers=_cookie(token))
    assert r.status_code not in (401, 403)


def test_mutacion_origin_local_pasa_el_gate():
    client, token = _client_y_token()
    r = client.post('/api/projects', json={}, headers={**_cookie(token), 'Origin': 'http://localhost:3000'})
    assert r.status_code not in (401, 403)


def test_get_con_origin_externo_no_se_bloquea():
    # El gate CSRF es solo para métodos que mutan; un GET con Origin externo
    # no se rechaza (CORS ya impide que lo LEA).
    client, token = _client_y_token()
    r = client.get('/api/projects', headers={**_cookie(token), 'Origin': 'http://evil.com'})
    assert r.status_code == 200


# ─── /api/health no filtra datos de recon ────────────────────────────────────

def test_health_no_expone_secretos():
    client, _ = _client_y_token()
    r = client.get('/api/health')   # ruta abierta: sin cookie
    assert r.status_code == 200
    body = r.json()
    assert body.get('status') == 'ok'
    assert 'anthropic_key' not in body
    assert 'whisper_cargado' not in body


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
