"""
Headers de seguridad en TODA respuesta (defensa en profundidad).

Verifica que el middleware aplique nosniff + anti-clickjacking (X-Frame-Options
+ CSP frame-ancestors) + Referrer-Policy no-referrer en HTML, /api y rutas
abiertas — incluso en respuestas de error del propio candado (400/401/403).
Patrón: fresh_db() antes de importar la app; cookie en header explícito.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient

from plotspace.tests._harness import fresh_db

ESPERADOS = {
    'x-content-type-options': 'nosniff',
    'x-frame-options': 'SAMEORIGIN',
    'content-security-policy': "frame-ancestors 'self'",
    'referrer-policy': 'no-referrer',
}


def _client_y_token():
    fresh_db()
    import plotspace.main as main
    from plotspace.core import auth
    return TestClient(main.app), auth.obtener_token()


def _assert_headers(r):
    for k, v in ESPERADOS.items():
        assert r.headers.get(k) == v, f'falta/!= {k}: {r.headers.get(k)!r}'


def test_headers_en_html_home():
    client, _ = _client_y_token()
    _assert_headers(client.get('/'))


def test_headers_en_health_ruta_abierta():
    client, _ = _client_y_token()
    _assert_headers(client.get('/api/health'))


def test_headers_en_api_autenticada():
    client, token = _client_y_token()
    r = client.get('/api/projects', headers={'Cookie': f'jarvis_token={token}'})
    assert r.status_code == 200
    _assert_headers(r)


def test_headers_tambien_en_401():
    # Hasta la respuesta de "no autenticado" lleva los headers de endurecimiento.
    client, _ = _client_y_token()
    r = client.get('/api/projects')
    assert r.status_code == 401
    _assert_headers(r)


def test_headers_en_static():
    client, _ = _client_y_token()
    r = client.get('/static/shell/workspace.html')
    assert r.status_code == 200
    _assert_headers(r)


# ─── Cache-Control: el documento HTML del shell se revalida siempre ──────────
# Sin Cache-Control el browser cachea el HTML por heurística (tiene ETag/
# Last-Modified) y queda apuntando a los ?v=N viejos → carga JS viejo aunque el
# server ya tenga el nuevo. `no-cache` fuerza revalidar el documento en cada
# navegación → F5 trae siempre el HTML actual con los scripts actuales.

def test_html_pages_son_no_cache():
    client, token = _client_y_token()
    cookie = {'Cookie': f'jarvis_token={token}'}
    for ruta in ('/', '/workspace', '/editor'):
        r = client.get(ruta, headers=cookie)
        assert r.status_code == 200, f'{ruta} → {r.status_code}'
        assert r.headers.get('cache-control') == 'no-cache', \
            f'{ruta}: cache-control = {r.headers.get("cache-control")!r}'


def test_static_no_recibe_no_cache():
    # Los estáticos versionados con ?v= NO deben heredar no-cache: su URL cambia
    # cuando cambia el contenido, así que se cachean fuerte (cero revalidación).
    client, _ = _client_y_token()
    r = client.get('/static/sections/terminals/terminal.js')
    assert r.status_code == 200
    assert r.headers.get('cache-control') != 'no-cache', \
        'el .js NO debería llevar no-cache (rompería el cache-busting por ?v=)'


def test_html_de_static_si_es_no_cache():
    # Los .html de /static (el shell del workspace, los prototipos) son
    # DOCUMENTOS: referencian .js/.css con ?v=N y deben revalidar en cada carga.
    client, _ = _client_y_token()
    r = client.get('/static/shell/workspace.html')
    assert r.status_code == 200
    assert r.headers.get('cache-control') == 'no-cache', \
        f'workspace.html: cache-control = {r.headers.get("cache-control")!r}'


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
