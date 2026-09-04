"""
Test: límites y aislamiento de archivos temporales en voice.py.

Dos endurecimientos:
  1. /transcribe rechaza audio que supera MAX_AUDIO_BYTES (DoS por memoria/disco)
     en vez de cargar un body ilimitado en RAM.
  2. transcribe y el TTS usan archivos temporales ÚNICOS por request (tempfile),
     no rutas fijas en /tmp — así dos requests concurrentes no se pisan el
     archivo (correctitud) y no hay symlink-attack sobre un nombre predecible.
"""
import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from fastapi import HTTPException, UploadFile

from plotspace.routers import voice


def _upload(data: bytes) -> UploadFile:
    return UploadFile(filename="a.webm", file=io.BytesIO(data))


def test_leer_audio_limitado_acepta_bajo_el_tope():
    uf = _upload(b'x' * 100)
    out = asyncio.run(voice._leer_audio_limitado(uf, max_bytes=1000))
    assert out == b'x' * 100


def test_leer_audio_limitado_rechaza_sobre_el_tope():
    uf = _upload(b'x' * 5000)
    try:
        asyncio.run(voice._leer_audio_limitado(uf, max_bytes=1000))
        assert False, "debió rechazar el audio gigante"
    except HTTPException as e:
        assert e.status_code == 413


def test_transcribe_413_sin_invocar_ffmpeg(monkeypatch):
    # Body > tope → 413 ANTES de tocar ffmpeg/whisper. Bajamos el tope para no
    # tener que mandar 25 MB en el test.
    monkeypatch.setattr(voice, 'MAX_AUDIO_BYTES', 1024)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(voice.router)
    client = TestClient(app)

    r = client.post('/api/voice/transcribe',
                    files={'audio': ('a.webm', b'x' * 4096, 'audio/webm')})
    assert r.status_code == 413, r.text


def test_temp_audio_paths_son_unicos():
    # El helper de rutas temporales devuelve un dir nuevo cada vez (tempfile),
    # nunca el viejo /tmp/jarvis_audio.webm fijo.
    d1 = voice._nuevo_dir_audio()
    d2 = voice._nuevo_dir_audio()
    try:
        assert d1 != d2
        assert os.path.isdir(d1) and os.path.isdir(d2)
        # mkdtemp crea con 0700 → no world-writable (anti symlink/predecible).
        assert (os.stat(d1).st_mode & 0o077) == 0
    finally:
        for d in (d1, d2):
            try:
                os.rmdir(d)
            except OSError:
                pass


if __name__ == '__main__':
    import traceback
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if (nombre.startswith('test_') and callable(fn)
                and getattr(fn, '__code__', None) and fn.__code__.co_argcount == 0):
            try:
                fn(); print(f'ok  {nombre}')
            except Exception:
                fallos += 1; print(f'FAIL {nombre}'); traceback.print_exc()
    sys.exit(1 if fallos else 0)
