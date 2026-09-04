"""
Tope de tamaño de body — incluso CHUNKED sin Content-Length (hallazgo #1 de la
2ª pasada). El LimiteBodyMiddleware cuenta los bytes reales del body y corta en
MAX_BODY_BYTES, así un upload chunked (que esquivaba el chequeo por Content-Length)
no puede llenar /tmp / la RAM.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi.testclient import TestClient

from plotspace.tests._harness import fresh_db


def _client():
    fresh_db()
    import plotspace.main as main
    return TestClient(main.app), main


def test_chunked_sin_content_length_se_corta_413():
    client, main = _client()
    prev = main.MAX_BODY_BYTES
    main.MAX_BODY_BYTES = 1000   # tope chico para el test (el mw lee el global por request)
    try:
        payload = b'{"nombre":"' + b'x' * 10000 + b'","ruta":"/tmp"}'
        def gen():
            for i in range(0, len(payload), 500):
                yield payload[i:i + 500]
        r = client.post('/api/projects', content=gen(),
                        headers={'content-type': 'application/json'})
        # 413 = el middleware cortó. 400 = Starlette envolvió el corte al parsear.
        # Lo que no puede ser es 2xx (el body gigante no se procesó).
        assert r.status_code in (413, 400), r.status_code
    finally:
        main.MAX_BODY_BYTES = prev


def test_body_chico_pasa():
    client, main = _client()
    # Un body normal (chico) no se corta: llega al handler (puede 422 por schema).
    r = client.post('/api/projects', json={'nombre': 'x', 'ruta': '/tmp'})
    assert r.status_code != 413


def test_content_length_gigante_se_rechaza_413():
    # La rama por header: un Content-Length declarado > tope se corta antes de leer.
    client, main = _client()
    prev = main.MAX_BODY_BYTES
    main.MAX_BODY_BYTES = 1000
    try:
        r = client.post('/api/system/restart', content=b'y' * 5000)  # httpx pone Content-Length
        assert r.status_code == 413, r.status_code
    finally:
        main.MAX_BODY_BYTES = prev


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
