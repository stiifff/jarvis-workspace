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
        def gen():
            for _ in range(20):
                yield b'x' * 500   # 10 KB en chunks → SIN Content-Length (chunked)
        r = client.post('/api/auth/login', content=gen())
        assert r.status_code == 413, r.status_code
    finally:
        main.MAX_BODY_BYTES = prev


def test_body_chico_pasa():
    client, main = _client()
    # Un body normal (chico) no se corta: llega al handler (login con token malo → 401).
    r = client.post('/api/auth/login', json={'token': 'x'})
    assert r.status_code in (401, 200)


def test_content_length_gigante_se_rechaza_413():
    # La rama por header: un Content-Length declarado > tope se corta antes de leer.
    client, main = _client()
    prev = main.MAX_BODY_BYTES
    main.MAX_BODY_BYTES = 1000
    try:
        r = client.post('/api/auth/login', content=b'y' * 5000)  # httpx pone Content-Length
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
