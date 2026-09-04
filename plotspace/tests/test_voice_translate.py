"""
Test: dictado con traducción a inglés en /api/voice/transcribe.

El HUD de voz permite "Traducir a inglés": el front manda translate=1 y el
backend usa el task `translate` de Whisper (cualquier idioma → inglés), en vez
del task por defecto `transcribe` (que devuelve el idioma original).

Cubrimos:
  1. _whisper_kwargs(translate) — la lógica PURA que elige el task.
  2. El endpoint /transcribe cablea el form field `translate` hasta esos kwargs.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from plotspace.routers import voice


def test_whisper_kwargs_default_es_transcribe():
    kw = voice._whisper_kwargs(False)
    assert kw["task"] == "transcribe"
    assert kw["language"] == "es"
    # Vocabulario del dominio: mejora la jerga técnica del dictado en español.
    assert isinstance(kw["initial_prompt"], str) and "Jarvis" in kw["initial_prompt"]


def test_whisper_kwargs_translate_usa_task_translate():
    kw = voice._whisper_kwargs(True)
    assert kw["task"] == "translate"
    # El resto de los flags de decode rápido se conservan.
    assert kw["beam_size"] == 1
    assert kw["temperature"] == 0.0
    # El prompt es español: en task=translate (salida inglés) NO se manda.
    assert kw["initial_prompt"] is None


def test_whisper_kwargs_sin_flags_de_openai_whisper():
    # Regresión de la migración a faster-whisper: `fp16` era un kwarg de
    # openai-whisper; faster-whisper lo rechaza con TypeError (el precision
    # se fija al cargar con compute_type="int8").
    for translate in (False, True):
        assert "fp16" not in voice._whisper_kwargs(translate)


def test_chunk_length_adapta_al_clip_corto():
    # Dictado de 5s → ventana de 8s (mínimo), no la de 30s default.
    assert voice._chunk_length_para(5.2) == 8
    # Clip mediano → duración + 2s de colchón.
    assert voice._chunk_length_para(12.5) == 14


def test_chunk_length_none_para_largos_o_desconocidos():
    # Clip largo o duración ilegible → None (faster-whisper usa su default de 30s).
    assert voice._chunk_length_para(28.0) is None
    assert voice._chunk_length_para(45.0) is None
    assert voice._chunk_length_para(None) is None
    assert voice._chunk_length_para(0) is None


def test_compute_type_default_float32(monkeypatch):
    # En CPUs sin VNNI (este Ryzen) int8 es MÁS LENTO que fp32 → default float32,
    # overrideable por env para CPUs modernas.
    monkeypatch.delenv("WHISPER_COMPUTE", raising=False)
    assert voice._compute_type() == "float32"
    monkeypatch.setenv("WHISPER_COMPUTE", "int8")
    assert voice._compute_type() == "int8"


def _fake_model(rec):
    # Contrato de faster-whisper: transcribe() devuelve (generador_de_segmentos, info)
    # y el texto se arma uniendo segment.text.
    class _Seg:
        def __init__(self, text):
            self.text = text

    class _M:
        def transcribe(self, _path, **kw):
            rec.update(kw)
            return iter([_Seg("hello"), _Seg(" world")]), {"language": "es"}
    return _M()


def test_transcribe_endpoint_propaga_translate(monkeypatch):
    rec = {}

    async def _fake_convertir(src, dst, filtro):
        with open(dst, "wb"):
            pass            # wav vacío: el modelo fake lo ignora
        return 0, b""

    monkeypatch.setenv("STT_WORKER", "off")   # ejercita el camino in-proc viejo
    monkeypatch.setattr(voice, "_convertir_a_wav", _fake_convertir)
    monkeypatch.setattr(voice, "_cargar_whisper", lambda: _fake_model(rec))

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
    assert rec.get("task") == "translate"


def test_transcribe_endpoint_sin_translate_es_transcribe(monkeypatch):
    rec = {}

    async def _fake_convertir(src, dst, filtro):
        with open(dst, "wb"):
            pass
        return 0, b""

    monkeypatch.setenv("STT_WORKER", "off")   # ejercita el camino in-proc viejo
    monkeypatch.setattr(voice, "_convertir_a_wav", _fake_convertir)
    monkeypatch.setattr(voice, "_cargar_whisper", lambda: _fake_model(rec))

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(voice.router)
    client = TestClient(app)

    r = client.post(
        "/api/voice/transcribe",
        files={"audio": ("a.webm", b"x" * 64, "audio/webm")},
    )
    assert r.status_code == 200, r.text
    assert rec.get("task") == "transcribe"


def test_transcribe_silencio_cortocircuita_sin_whisper(monkeypatch):
    # El recorte de ffmpeg deja un WAV de ~0.1s (era puro silencio) → el endpoint
    # devuelve texto vacío SIN cargar ni invocar el modelo (caso más común del
    # fallback: PTT apretado sin hablar).
    import wave as _wave

    async def _fake_convertir(src, dst, filtro):
        with _wave.open(dst, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 1600)   # 0.1s
        return 0, b""

    def _boom():
        raise AssertionError("con silencio NO se debe tocar Whisper")

    monkeypatch.setattr(voice, "_convertir_a_wav", _fake_convertir)
    monkeypatch.setattr(voice, "_cargar_whisper", _boom)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(voice.router)
    client = TestClient(app)

    r = client.post(
        "/api/voice/transcribe",
        files={"audio": ("a.webm", b"x" * 64, "audio/webm")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"] == ""


def test_parse_google_translate_une_segmentos():
    # Forma real de translate_a/single: [[[trad, orig, ...], ...], ...]
    data = [[["I want ", "Quiero ", None, None, 1], ["the box", "el cuadro", None, None, 1]], None, "es"]
    assert voice._parse_google_translate(data) == "I want the box"


def test_parse_google_translate_robusto_ante_basura():
    assert voice._parse_google_translate(None) == ""
    assert voice._parse_google_translate([]) == ""
    assert voice._parse_google_translate([[None, ["x", "y"]]]) == "x"


def test_translate_endpoint_traduce(monkeypatch):
    async def _fake(texto, sl="es", tl="en"):
        assert texto == "hola mundo"
        return "hello world"
    monkeypatch.setattr(voice, "_http_google_translate", _fake)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI(); app.include_router(voice.router)
    client = TestClient(app)
    r = client.post("/api/voice/translate", json={"text": "  hola mundo  "})
    assert r.status_code == 200, r.text
    assert r.json()["text"] == "hello world"


def test_translate_endpoint_vacio_no_llama_red(monkeypatch):
    llamado = {"n": 0}
    async def _fake(texto, sl="es", tl="en"):
        llamado["n"] += 1
        return "x"
    monkeypatch.setattr(voice, "_http_google_translate", _fake)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI(); app.include_router(voice.router)
    client = TestClient(app)
    r = client.post("/api/voice/translate", json={"text": "   "})
    assert r.status_code == 200, r.text
    assert r.json()["text"] == ""
    assert llamado["n"] == 0, "texto vacío no debe tocar la red"


def test_translate_endpoint_falla_da_502(monkeypatch):
    async def _boom(texto, sl="es", tl="en"):
        raise RuntimeError("network down")
    monkeypatch.setattr(voice, "_http_google_translate", _boom)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI(); app.include_router(voice.router)
    client = TestClient(app)
    r = client.post("/api/voice/translate", json={"text": "hola"})
    assert r.status_code == 502, r.text


# ─── Lote (novedades del modal "Actualizar ahora" en inglés) ──────────────────

def test_translate_endpoint_lote_preserva_orden(monkeypatch):
    # El modal "Actualizar ahora" manda TODAS las novedades de una y las quiere
    # de vuelta en el MISMO orden para pintar cada <li> donde corresponde.
    async def _fake(texto, sl="es", tl="en"):
        return {"hola": "hello", "mundo": "world"}.get(texto.strip(), texto.upper())
    monkeypatch.setattr(voice, "_http_google_translate", _fake)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI(); app.include_router(voice.router)
    client = TestClient(app)
    r = client.post("/api/voice/translate", json={"texts": ["hola", "mundo", "che"]})
    assert r.status_code == 200, r.text
    assert r.json()["texts"] == ["hello", "world", "CHE"]


def test_translate_endpoint_lote_item_vacio_y_fallo_no_rompen(monkeypatch):
    # Degradación elegante: un ítem vacío queda vacío (sin red) y uno que falla
    # vuelve como su ORIGINAL — esa novedad se muestra en español, el resto en
    # inglés. Nunca 502 por un ítem: el lote entero debe sobrevivir.
    async def _fake(texto, sl="es", tl="en"):
        if texto.strip() == "rompe":
            raise RuntimeError("boom")
        return "ok"
    monkeypatch.setattr(voice, "_http_google_translate", _fake)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI(); app.include_router(voice.router)
    client = TestClient(app)
    r = client.post("/api/voice/translate", json={"texts": ["  ", "rompe", "dale"]})
    assert r.status_code == 200, r.text
    assert r.json()["texts"] == ["", "rompe", "ok"]


def test_translate_endpoint_lote_vacio_no_toca_red(monkeypatch):
    llamado = {"n": 0}
    async def _fake(texto, sl="es", tl="en"):
        llamado["n"] += 1
        return "x"
    monkeypatch.setattr(voice, "_http_google_translate", _fake)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI(); app.include_router(voice.router)
    client = TestClient(app)
    r = client.post("/api/voice/translate", json={"texts": []})
    assert r.status_code == 200, r.text
    assert r.json()["texts"] == []
    assert llamado["n"] == 0, "lote vacío no debe tocar la red"


def test_translate_endpoint_lote_sl_auto(monkeypatch):
    # Los títulos vivos de las cards mandan sl='auto': el pane title puede venir
    # YA en inglés (Codex u otra CLI) y forzar sl=es lo estropearía. Google
    # detecta el idioma origen y un texto inglés vuelve intacto.
    visto = {"sl": None}
    async def _fake(texto, sl="es", tl="en"):
        visto["sl"] = sl
        return "fixing the bug"
    monkeypatch.setattr(voice, "_http_google_translate", _fake)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI(); app.include_router(voice.router)
    client = TestClient(app)
    r = client.post("/api/voice/translate", json={"texts": ["arreglando el bug"], "sl": "auto"})
    assert r.status_code == 200, r.text
    assert r.json()["texts"] == ["fixing the bug"]
    assert visto["sl"] == "auto"


def test_translate_endpoint_sl_default_e_invalido_caen_a_es(monkeypatch):
    # Sin sl (dictado, novedades del updater) y con sl basura: se traduce desde
    # español como siempre — el parámetro nuevo no cambia a los callers viejos.
    visto = {"sls": []}
    async def _fake(texto, sl="es", tl="en"):
        visto["sls"].append(sl)
        return "hello"
    monkeypatch.setattr(voice, "_http_google_translate", _fake)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI(); app.include_router(voice.router)
    client = TestClient(app)
    assert client.post("/api/voice/translate", json={"text": "hola"}).status_code == 200
    assert client.post("/api/voice/translate", json={"texts": ["hola"], "sl": "xx"}).status_code == 200
    assert visto["sls"] == ["es", "es"]


def test_transcribe_limpia_tmp_dir_si_ffmpeg_falla(monkeypatch, tmp_path):
    # Regresión: cuando ffmpeg falla (rc!=0 con y sin recorte) el endpoint devuelve
    # 500 PERO igual borra el tmp_dir (antes salía con raise antes del finally).
    import os
    forzado = str(tmp_path / "jarvis_audio_forzado")
    os.makedirs(forzado, exist_ok=True)
    monkeypatch.setattr(voice, "_nuevo_dir_audio", lambda: forzado)

    async def _ffmpeg_falla(src, dst, filtro):
        return 1, b"boom"
    monkeypatch.setattr(voice, "_convertir_a_wav", _ffmpeg_falla)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(voice.router)
    client = TestClient(app)

    r = client.post(
        "/api/voice/transcribe",
        files={"audio": ("a.webm", b"x" * 64, "audio/webm")},
    )
    assert r.status_code == 500, r.text
    assert not os.path.exists(forzado), "el tmp_dir quedó huérfano tras el fallo de ffmpeg"
