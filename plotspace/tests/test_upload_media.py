"""
Upload de media (video/imagen) a terminales — POST /api/terminals/{id}/upload-media.

Por qué existe: el drag-drop de VIDEOS sobre una card viajaba como base64 dentro
de un JSON al endpoint de imágenes (/upload-image, tope 15 MB) → HTTP 413 con
cualquier video real. El endpoint multipart streamea a disco en chunks con tope
por tipo (video 200 MB default / imagen 15 MB) sin materializar el archivo en RAM.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from plotspace.tests._harness import fresh_db


def _client():
    fresh_db()
    from plotspace.routers import terminals
    app = FastAPI()
    app.include_router(terminals.router)
    return TestClient(app), terminals


def _post_media(client, contenido: bytes, filename: str, mime: str, terminal_id: int = 1):
    return client.post(
        f'/api/terminals/{terminal_id}/upload-media',
        files={'archivo': (filename, io.BytesIO(contenido), mime)},
    )


def test_video_multipart_ok():
    client, terminals = _client()
    datos = b'\x00\x01video-bytes' * 1000          # ~14 KB, holgado bajo el tope
    r = _post_media(client, datos, 'demo clip.mp4', 'video/mp4', terminal_id=7)
    assert r.status_code == 200, r.text
    path = r.json()['path']
    assert os.path.isfile(path), path
    assert os.path.basename(path).startswith('t7_')
    assert path.endswith('demo_clip.mp4')          # nombre saneado (espacio → _)
    with open(path, 'rb') as f:
        assert f.read() == datos                   # bytes intactos (sin base64 de por medio)
    os.remove(path)


def test_video_supera_tope_413_y_no_deja_parcial():
    client, terminals = _client()
    prev = terminals.MAX_VIDEO_BYTES
    terminals.MAX_VIDEO_BYTES = 1024               # tope chico para el test
    try:
        r = _post_media(client, b'v' * 5000, 'grande.mp4', 'video/mp4')
        assert r.status_code == 413, r.text
        assert 'Video' in r.json()['detail']
        # El parcial escrito hasta el corte NO queda en disco.
        restos = [n for n in os.listdir(terminals.UPLOAD_DIR) if n.endswith('grande.mp4')]
        assert restos == [], restos
    finally:
        terminals.MAX_VIDEO_BYTES = prev


def test_imagen_multipart_usa_tope_de_imagen():
    client, terminals = _client()
    prev = terminals.MAX_UPLOAD_BYTES
    terminals.MAX_UPLOAD_BYTES = 1024
    try:
        r = _post_media(client, b'i' * 5000, 'foto.png', 'image/png')
        assert r.status_code == 413, r.text
        assert 'Imagen' in r.json()['detail']
    finally:
        terminals.MAX_UPLOAD_BYTES = prev


def test_upload_image_json_sigue_andando():
    # Regresión: el endpoint viejo (paste de imágenes, base64 JSON) no cambia.
    import base64
    client, terminals = _client()
    r = client.post(
        '/api/terminals/3/upload-image',
        json={'image_base64': base64.b64encode(b'png-bytes').decode(), 'filename': 'clip.png'},
    )
    assert r.status_code == 200, r.text
    path = r.json()['path']
    assert os.path.isfile(path)
    os.remove(path)


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
