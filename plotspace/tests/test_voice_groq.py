"""
Test: motor STT remoto Groq (STT_MOTOR=groq) en /api/voice/transcribe.

Groq corre whisper-large-v3-turbo en sus LPUs: la transcripción sale de la CPU
local (cero carga de modelo, cero RAM) y el motor local queda como FALLBACK si
la llamada falla (sin red, 5xx, timeout). Cubrimos:
  1. _stt_motor() acepta 'groq' y _plan_inferencia lo mapea (traducción por texto).
  2. core/stt_groq: armado del form y parseo de la respuesta (puras).
  3. _groq_habilitado(): exige STT_MOTOR=groq Y GROQ_API_KEY presente.
  4. /transcribe usa Groq primero SIN tocar el motor local; si Groq falla cae
     al camino local; translate=1 traduce el TEXTO (Groq transcribe español).
  5. /prewarm con Groq activo es no-op (ni worker ni modelo local).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.core import stt_groq
from plotspace.routers import voice

# Concatenada para no disparar el candado anti-secretos (scan_secretos).
FAKE_KEY = "gsk_" + "t" * 32


# ─── Lógica pura ──────────────────────────────────────────────────────────────

def test_stt_motor_acepta_groq(monkeypatch):
    monkeypatch.setenv("STT_MOTOR", "groq")
    assert voice._stt_motor() == "groq"
    monkeypatch.setenv("STT_MOTOR", "basura")
    assert voice._stt_motor() == "parakeet"


def test_plan_inferencia_groq_traduce_por_texto():
    # Groq transcribe SIEMPRE español (turbo no tiene task=translate): si el
    # pedido era traducir, se traduce el TEXTO después (camino rápido).
    assert voice._plan_inferencia("groq", False) == {"motor": "groq", "traducir_texto": False}
    assert voice._plan_inferencia("groq", True) == {"motor": "groq", "traducir_texto": True}


def test_groq_habilitado_exige_motor_y_key(monkeypatch):
    monkeypatch.setenv("STT_MOTOR", "groq")
    monkeypatch.setenv("GROQ_API_KEY", FAKE_KEY)
    assert voice._groq_habilitado() is True
    monkeypatch.delenv("GROQ_API_KEY")
    assert voice._groq_habilitado() is False
    monkeypatch.setenv("GROQ_API_KEY", FAKE_KEY)
    monkeypatch.setenv("STT_MOTOR", "parakeet")
    assert voice._groq_habilitado() is False


def test_armar_form_transcripcion_es():
    form = stt_groq.armar_form("whisper-large-v3-turbo", "Jarvis, tmux")
    assert form["model"] == "whisper-large-v3-turbo"
    assert form["language"] == "es"
    assert form["prompt"] == "Jarvis, tmux"
    # Decode determinista, mismo criterio que el motor local.
    assert form["temperature"] == "0"


def test_armar_form_sin_prompt():
    assert "prompt" not in stt_groq.armar_form("whisper-large-v3-turbo", None)


def test_parsear_respuesta_robusta_ante_basura():
    assert stt_groq.parsear_respuesta({"text": " hola mundo "}) == "hola mundo"
    assert stt_groq.parsear_respuesta({}) == ""
    assert stt_groq.parsear_respuesta(None) == ""
    assert stt_groq.parsear_respuesta("basura") == ""


def test_modelo_default_y_override(monkeypatch):
    monkeypatch.delenv("GROQ_STT_MODEL", raising=False)
    assert stt_groq.modelo() == "whisper-large-v3-turbo"
    monkeypatch.setenv("GROQ_STT_MODEL", "whisper-large-v3")
    assert stt_groq.modelo() == "whisper-large-v3"


# ─── Endpoint /transcribe ─────────────────────────────────────────────────────

def _app_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(voice.router)
    return TestClient(app)


async def _fake_convertir(src, dst, filtro):
    with open(dst, "wb"):
        pass  # wav vacío: duración ilegible → no cortocircuita por silencio
    return 0, b""


def _fake_model_local(rec):
    # Contrato de faster-whisper (o su fake): transcribe() → (segmentos, info).
    class _Seg:
        def __init__(self, text):
            self.text = text

    class _M:
        def transcribe(self, _path, **kw):
            rec.update(kw)
            return iter([_Seg("hola"), _Seg(" local")]), {"language": "es"}
    return _M()


def _entorno_groq(monkeypatch):
    monkeypatch.setenv("STT_MOTOR", "groq")
    monkeypatch.setenv("GROQ_API_KEY", FAKE_KEY)
    monkeypatch.setenv("STT_WORKER", "off")  # el camino local de estos tests es in-proc
    monkeypatch.setattr(voice, "_convertir_a_wav", _fake_convertir)


def test_transcribe_usa_groq_sin_tocar_motor_local(monkeypatch):
    _entorno_groq(monkeypatch)

    def _boom():
        raise AssertionError("con Groq OK no se debe tocar el motor local")
    monkeypatch.setattr(voice, "_cargar_whisper", _boom)

    async def _fake_groq(wav):
        assert os.path.exists(wav)
        return "hola desde groq"
    monkeypatch.setattr(voice, "_transcribir_groq", _fake_groq)

    r = _app_client().post(
        "/api/voice/transcribe",
        files={"audio": ("a.webm", b"x" * 64, "audio/webm")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hola desde groq"
    assert r.json().get("motor") == "groq"


def test_transcribe_groq_falla_cae_al_motor_local(monkeypatch):
    rec = {}
    _entorno_groq(monkeypatch)
    monkeypatch.setattr(voice, "_cargar_whisper", lambda: _fake_model_local(rec))

    async def _groq_caido(wav):
        raise RuntimeError("connect timeout")
    monkeypatch.setattr(voice, "_transcribir_groq", _groq_caido)

    r = _app_client().post(
        "/api/voice/transcribe",
        files={"audio": ("a.webm", b"x" * 64, "audio/webm")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hola local"


def test_transcribe_groq_translate_traduce_el_texto(monkeypatch):
    _entorno_groq(monkeypatch)

    async def _fake_groq(wav):
        return "hola mundo"
    monkeypatch.setattr(voice, "_transcribir_groq", _fake_groq)

    async def _fake_http(texto, sl="es", tl="en"):
        assert texto == "hola mundo"
        return "hello world"
    monkeypatch.setattr(voice, "_http_google_translate", _fake_http)

    r = _app_client().post(
        "/api/voice/transcribe",
        files={"audio": ("a.webm", b"x" * 64, "audio/webm")},
        data={"translate": "1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hello world"


def test_transcribe_sin_key_va_directo_al_motor_local(monkeypatch):
    # STT_MOTOR=groq pero SIN GROQ_API_KEY: ni intenta Groq, camino local directo.
    rec = {}
    _entorno_groq(monkeypatch)
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.setattr(voice, "_cargar_whisper", lambda: _fake_model_local(rec))

    async def _no_debe_correr(wav):
        raise AssertionError("sin key no se debe llamar a Groq")
    monkeypatch.setattr(voice, "_transcribir_groq", _no_debe_correr)

    r = _app_client().post(
        "/api/voice/transcribe",
        files={"audio": ("a.webm", b"x" * 64, "audio/webm")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hola local"


# ─── /prewarm ─────────────────────────────────────────────────────────────────

def test_prewarm_con_groq_es_noop(monkeypatch):
    monkeypatch.setenv("STT_MOTOR", "groq")
    monkeypatch.setenv("GROQ_API_KEY", FAKE_KEY)

    class _WorkerProhibido:
        listo = False
        vivo = False

        async def asegurar(self):
            raise AssertionError("prewarm con Groq no debe spawnear el worker")
    monkeypatch.setattr(voice, "_worker_stt", _WorkerProhibido())

    r = _app_client().post("/api/voice/prewarm")
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "listo"
