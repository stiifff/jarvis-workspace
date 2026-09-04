"""
Test: motor STT conmutable — parakeet (default, onnx-asr) vs whisper (vía de
escape STT_MOTOR=whisper). La carga real SIEMPRE mockeada: acá se prueba la
selección de motor y el plan de inferencia (parakeet no tiene task=translate:
transcribe español y el TEXTO se traduce después).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers import voice


# ─── _stt_motor (env) ─────────────────────────────────────────────────────────

def test_motor_default_parakeet(monkeypatch):
    monkeypatch.delenv('STT_MOTOR', raising=False)
    assert voice._stt_motor() == 'parakeet'


def test_motor_escape_whisper(monkeypatch):
    monkeypatch.setenv('STT_MOTOR', 'whisper')
    assert voice._stt_motor() == 'whisper'


def test_motor_basura_cae_a_parakeet(monkeypatch):
    monkeypatch.setenv('STT_MOTOR', 'banana')
    assert voice._stt_motor() == 'parakeet'


# ─── _plan_inferencia (pura) ──────────────────────────────────────────────────

def test_plan_parakeet_traduce_el_texto():
    assert voice._plan_inferencia('parakeet', True) == {'motor': 'parakeet', 'traducir_texto': True}
    assert voice._plan_inferencia('parakeet', False) == {'motor': 'parakeet', 'traducir_texto': False}


def test_plan_whisper_traduce_nativo():
    # whisper usa task=translate DENTRO del modelo: nada que traducir después.
    assert voice._plan_inferencia('whisper', True) == {'motor': 'whisper', 'traducir_texto': False}
    assert voice._plan_inferencia('whisper', False) == {'motor': 'whisper', 'traducir_texto': False}


# ─── _cargar_whisper despacha al loader del motor activo ─────────────────────

def test_cargar_despacha_por_motor(monkeypatch):
    monkeypatch.setattr(voice, '_whisper_model', None)
    monkeypatch.setenv('STT_MOTOR', 'whisper')
    monkeypatch.setattr(voice, '_cargar_motor_whisper', lambda: 'W')
    monkeypatch.setattr(voice, '_cargar_motor_parakeet', lambda: 'P')
    assert voice._cargar_whisper() == 'W'

    monkeypatch.setattr(voice, '_whisper_model', None)
    monkeypatch.delenv('STT_MOTOR', raising=False)
    assert voice._cargar_whisper() == 'P'


def test_cargar_no_recarga_si_ya_hay_modelo(monkeypatch):
    # Con modelo vivo, ni mira el env: renueva el timestamp y devuelve el cargado.
    centinela = object()
    monkeypatch.setattr(voice, '_whisper_model', centinela)
    monkeypatch.setattr(voice, '_whisper_ultimo_uso', 0.0)
    monkeypatch.setattr(voice, '_cargar_motor_whisper', lambda: 1 / 0)
    monkeypatch.setattr(voice, '_cargar_motor_parakeet', lambda: 1 / 0)
    assert voice._cargar_whisper() is centinela
    assert voice._whisper_ultimo_uso > 0.0


# ─── /transcribe con motor parakeet (fake con .recognize, sin .transcribe) ───

def test_transcribe_endpoint_con_parakeet_y_translate(monkeypatch):
    """El fake de parakeet devuelve español; con translate=1 el endpoint traduce
    el TEXTO vía _traducir_es_en (mockeada) en vez de pedirle inglés al modelo."""
    class _FakeParakeet:
        def recognize(self, _path, **kw):
            return "hola mundo"

    async def _fake_convertir(src, dst, filtro):
        with open(dst, "wb"):
            pass
        return 0, b""

    async def _fake_traducir(texto):
        assert texto == "hola mundo"
        return "hello world"

    monkeypatch.setenv("STT_WORKER", "off")   # ejercita el camino in-proc viejo
    monkeypatch.setattr(voice, "_convertir_a_wav", _fake_convertir)
    monkeypatch.setattr(voice, "_cargar_whisper", lambda: _FakeParakeet())
    monkeypatch.setattr(voice, "_traducir_es_en", _fake_traducir)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(voice.router)
    client = TestClient(app)

    r = client.post(
        "/api/voice/transcribe",
        files={"audio": ("a.webm", b"x" * 64, "audio/webm")},
        data={"translate": "1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hello world"

    # Sin translate: devuelve el español tal cual.
    r = client.post(
        "/api/voice/transcribe",
        files={"audio": ("a.webm", b"x" * 64, "audio/webm")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hola mundo"


# ─── POST /dictado-log (registro local de dictados) ──────────────────────────

def test_dictado_log_escribe_json_line(tmp_path, monkeypatch):
    import json
    destino = tmp_path / "dictados.log"
    monkeypatch.setattr(voice, "_DICTADOS_LOG", str(destino))

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(voice.router)
    client = TestClient(app)

    r = client.post("/api/voice/dictado-log",
                    json={"texto": "hacé commit", "fuente": "sr", "conf": 0.91})
    assert r.status_code == 200 and r.json() == {"ok": True}
    linea = json.loads(destino.read_text(encoding="utf-8").strip())
    assert linea["texto"] == "hacé commit"
    assert linea["fuente"] == "sr"
    assert linea["conf"] == 0.91
    assert "ts" in linea

    # Nunca falla hacia el cliente aunque el disco explote.
    monkeypatch.setattr(voice, "_escribir_dictado_log", lambda *_a, **_k: 1 / 0)
    r = client.post("/api/voice/dictado-log", json={"texto": "x", "fuente": "sr"})
    assert r.status_code == 200 and r.json() == {"ok": True}


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-q']))
