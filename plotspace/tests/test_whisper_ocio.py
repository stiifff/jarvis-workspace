"""
Test: Whisper on-demand + descarga por ocio (la RAM vuelve al SO).

El modelo ya NO vive residente desde el boot: se carga al primer dictado (o al
prewarm que dispara el PTT) y un vigilante lo descarga tras WHISPER_IDLE_UNLOAD
segundos sin uso — en este box el turbo fp32 eran 3,2 GB de RSS clavados en el
uvicorn aunque nadie dictara jamás. Acá se prueba la lógica pura de la decisión,
la descarga segura (serializada con las inferencias vía el executor) y el
endpoint /prewarm, con la carga real SIEMPRE mockeada (ningún test toca el
modelo de verdad).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers import voice


# ─── _debe_descargar (pura) ───────────────────────────────────────────────────

def test_debe_descargar_con_ocio_superado():
    assert voice._debe_descargar(ultimo_uso=100.0, ahora=800.0, umbral=600) is True


def test_no_descarga_con_uso_reciente():
    assert voice._debe_descargar(ultimo_uso=700.0, ahora=800.0, umbral=600) is False


def test_no_descarga_sin_umbral():
    # WHISPER_IDLE_UNLOAD=off → umbral None → nunca descarga.
    assert voice._debe_descargar(ultimo_uso=0.0, ahora=1e9, umbral=None) is False


def test_no_descarga_sin_uso_registrado():
    # Modelo cargado pero sin timestamp (estado imposible salvo carrera): no tocar.
    assert voice._debe_descargar(ultimo_uso=None, ahora=800.0, umbral=600) is False


# ─── _umbral_ocio (env) ───────────────────────────────────────────────────────

def test_umbral_default_600(monkeypatch):
    monkeypatch.delenv('WHISPER_IDLE_UNLOAD', raising=False)
    assert voice._umbral_ocio() == 600


def test_umbral_off_desactiva(monkeypatch):
    monkeypatch.setenv('WHISPER_IDLE_UNLOAD', 'off')
    assert voice._umbral_ocio() is None
    monkeypatch.setenv('WHISPER_IDLE_UNLOAD', '0')
    assert voice._umbral_ocio() is None


def test_umbral_basura_cae_al_default(monkeypatch):
    monkeypatch.setenv('WHISPER_IDLE_UNLOAD', 'banana')
    assert voice._umbral_ocio() == 600


# ─── _descargar_whisper ───────────────────────────────────────────────────────

def test_descargar_sin_modelo_es_noop(monkeypatch):
    monkeypatch.setattr(voice, '_whisper_model', None)
    assert voice._descargar_whisper() is False


def test_descargar_libera_el_modelo(monkeypatch):
    monkeypatch.setattr(voice, '_whisper_model', object())
    monkeypatch.setattr(voice, '_whisper_ultimo_uso', time.monotonic() - 10_000)
    monkeypatch.setenv('WHISPER_IDLE_UNLOAD', '600')
    assert voice._descargar_whisper() is True
    assert voice._whisper_model is None


def test_descargar_respeta_uso_reciente(monkeypatch):
    # Una inferencia encolada ANTES que la descarga corre primero (executor de 1
    # hilo) y renueva el timestamp → la descarga re-chequea y se abstiene.
    centinela = object()
    monkeypatch.setattr(voice, '_whisper_model', centinela)
    monkeypatch.setattr(voice, '_whisper_ultimo_uso', time.monotonic())
    monkeypatch.setenv('WHISPER_IDLE_UNLOAD', '600')
    assert voice._descargar_whisper() is False
    assert voice._whisper_model is centinela


# ─── _cargar_whisper sella el último uso ─────────────────────────────────────

def test_cargar_whisper_sella_ultimo_uso(monkeypatch):
    # Con el modelo ya "cargado" (mock), cada llamada renueva el timestamp sin
    # tocar faster_whisper.
    monkeypatch.setattr(voice, '_whisper_model', object())
    monkeypatch.setattr(voice, '_whisper_ultimo_uso', 0.0)
    voice._cargar_whisper()
    assert voice._whisper_ultimo_uso > 0.0


# ─── POST /prewarm ────────────────────────────────────────────────────────────

def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(voice.router)
    return TestClient(app)


def _flush_executor():
    voice._whisper_executor.submit(lambda: None).result(timeout=10)


def test_prewarm_dispara_carga_en_executor(monkeypatch):
    # STT_WORKER=off: estos tres tests cubren la vía de escape in-proc (con el
    # worker default, prewarm spawnearía un PROCESO real que carga el modelo
    # real — el camino worker se testea con fakes en test_stt_proc.py).
    monkeypatch.setenv('STT_WORKER', 'off')
    llamadas = []
    monkeypatch.setattr(voice, '_whisper_model', None)
    monkeypatch.setattr(voice, '_cargar_whisper', lambda: llamadas.append(1))

    r = _client().post('/api/voice/prewarm')
    assert r.status_code == 200
    assert r.json() == {'estado': 'cargando'}
    _flush_executor()
    assert llamadas == [1]


def test_prewarm_con_modelo_cargado_no_recarga(monkeypatch):
    monkeypatch.setenv('STT_WORKER', 'off')
    llamadas = []
    monkeypatch.setattr(voice, '_whisper_model', object())
    monkeypatch.setattr(voice, '_cargar_whisper', lambda: llamadas.append(1))

    r = _client().post('/api/voice/prewarm')
    assert r.status_code == 200
    assert r.json() == {'estado': 'listo'}
    _flush_executor()
    assert llamadas == []


def test_prewarm_no_explota_si_la_carga_falla(monkeypatch):
    # La carga corre en el executor DESPUÉS de responder: una excepción ahí no
    # debe matar el hilo de whisper ni filtrar un 500 tardío.
    def _boom():
        raise RuntimeError('sin modelo en disco')
    monkeypatch.setenv('STT_WORKER', 'off')
    monkeypatch.setattr(voice, '_whisper_model', None)
    monkeypatch.setattr(voice, '_cargar_whisper', _boom)

    r = _client().post('/api/voice/prewarm')
    assert r.status_code == 200
    _flush_executor()   # si el hilo murió, esto cuelga/explota


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__, '-q']))
