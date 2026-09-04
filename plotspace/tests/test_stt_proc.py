"""
Tests: STT en proceso worker (plotspace/core/stt_proc.py).

Por qué existe el worker: onnxruntime retiene el GIL mientras crea la
InferenceSession (5-7s medidos en vivo, 20s+ en frío) — cargar el modelo "en un
thread" congelaba el proceso ENTERO del server, incluido el event loop que da
eco/scroll a todas las terminales (el freeze post-"Actualizar ahora" y cada
regreso al workspace tras la descarga por ocio). En un proceso hijo el GIL es
suyo: el server no puede stallearse por la voz.

Cubre:
  1. _atender (pura): un request del protocolo → response ok/error.
  2. WorkerSTT contra un worker FALSO (protocolo real por pipes): listo,
     round-trip de transcripción, muerte del worker (falla el pendiente y
     se puede respawnear), terminar().
  3. /transcribe y /prewarm usan el worker cuando STT_WORKER=on (default).
  4. _descargar_ociosos: el vigilante mata el worker ocioso.
"""
import asyncio
import time
import sys

sys.path.insert(0, '/home/user/jarvis')

from plotspace.core import stt_proc
from plotspace.routers import voice


# ─── _atender (pura) ──────────────────────────────────────────────────────────

def test_atender_ok():
    r = stt_proc._atender({'id': 7, 'wav': '/x.wav', 'translate': False},
                          lambda wav, tr: ('parakeet', f'texto de {wav} tr={tr}'))
    assert r == {'id': 7, 'ok': True, 'motor': 'parakeet',
                 'texto': 'texto de /x.wav tr=False'}


def test_atender_error_no_explota():
    def _inferir(wav, tr):
        raise RuntimeError('modelo roto')
    r = stt_proc._atender({'id': 3}, _inferir)
    assert r['id'] == 3 and r['ok'] is False and 'modelo roto' in r['error']


# ─── WorkerSTT contra un worker falso (protocolo real) ───────────────────────

_FAKE_OK = [sys.executable, '-u', '-c', (
    'import sys, json\n'
    'print(json.dumps({"ev": "listo", "motor": "fake"}), flush=True)\n'
    'for linea in sys.stdin:\n'
    '    req = json.loads(linea)\n'
    '    print(json.dumps({"id": req["id"], "ok": True, "motor": "fake",\n'
    '                      "texto": "eco:" + str(req.get("wav"))}), flush=True)\n'
)]

# Muere al primer request SIN responder (simula crash a mitad de inferencia).
_FAKE_MUERE = [sys.executable, '-u', '-c', (
    'import sys, json\n'
    'print(json.dumps({"ev": "listo", "motor": "fake"}), flush=True)\n'
    'sys.stdin.readline()\n'
    'sys.exit(3)\n'
)]


def test_worker_roundtrip_y_listo():
    async def _t():
        w = stt_proc.WorkerSTT(cmd=_FAKE_OK)
        await w.asegurar()
        assert w.vivo
        motor, texto = await w.transcribir('/a.wav', False, timeout=10)
        assert (motor, texto) == ('fake', 'eco:/a.wav')
        assert w.listo   # el ev listo ya llegó (respondió después de emitirlo)
        await w.terminar()
        assert not w.vivo
    asyncio.run(_t())


def test_worker_muerto_falla_el_pendiente_y_respawnea():
    async def _t():
        w = stt_proc.WorkerSTT(cmd=_FAKE_MUERE)
        await w.asegurar()
        try:
            await w.transcribir('/a.wav', False, timeout=10)
            raise AssertionError('debía fallar: el worker murió sin responder')
        except RuntimeError:
            pass
        # Respawn limpio después de la muerte.
        w._cmd = _FAKE_OK
        await w.asegurar()
        motor, _ = await w.transcribir('/b.wav', False, timeout=10)
        assert motor == 'fake'
        await w.terminar()
    asyncio.run(_t())


def test_terminar_sin_worker_es_noop():
    async def _t():
        w = stt_proc.WorkerSTT(cmd=_FAKE_OK)
        assert (await w.terminar()) is False
    asyncio.run(_t())


# ─── Integración con voice.py ────────────────────────────────────────────────

class _FakeWorkerListo:
    listo = True
    vivo = True

    def __init__(self):
        self.llamadas = []

    async def asegurar(self):
        self.llamadas.append('asegurar')

    async def transcribir(self, wav, translate, timeout=180.0):
        self.llamadas.append(('transcribir', translate))
        return ('parakeet', 'hola por worker')

    async def terminar(self):
        self.llamadas.append('terminar')
        return True


async def _fake_convertir(src, dst, filtro):
    with open(dst, 'wb'):
        pass
    return 0, b''


def test_transcribe_endpoint_via_worker(monkeypatch):
    """Con STT_WORKER default (on), /transcribe va por el worker y NUNCA carga
    el modelo dentro del server."""
    monkeypatch.delenv('STT_WORKER', raising=False)
    fake = _FakeWorkerListo()
    monkeypatch.setattr(voice, '_worker_stt', fake)
    monkeypatch.setattr(voice, '_convertir_a_wav', _fake_convertir)
    monkeypatch.setattr(voice, '_cargar_whisper', lambda: 1 / 0)  # el camino in-proc NO corre

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(voice.router)
    client = TestClient(app)

    r = client.post('/api/voice/transcribe',
                    files={'audio': ('a.webm', b'x' * 64, 'audio/webm')})
    assert r.status_code == 200, r.text
    assert r.json()['text'] == 'hola por worker'
    assert ('transcribir', False) in fake.llamadas


def test_prewarm_worker_cargando(monkeypatch):
    monkeypatch.delenv('STT_WORKER', raising=False)
    fake = _FakeWorkerListo()
    fake.listo = False
    fake.vivo = False
    monkeypatch.setattr(voice, '_worker_stt', fake)
    monkeypatch.setattr(voice, '_whisper_ultimo_uso', None)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(voice.router)
    client = TestClient(app)

    r = client.post('/api/voice/prewarm')
    assert r.json() == {'estado': 'cargando'}
    assert 'asegurar' in fake.llamadas
    assert voice._whisper_ultimo_uso is not None   # renovó la ventana de ocio


def test_prewarm_worker_listo_renueva_ventana(monkeypatch):
    monkeypatch.delenv('STT_WORKER', raising=False)
    fake = _FakeWorkerListo()
    monkeypatch.setattr(voice, '_worker_stt', fake)
    monkeypatch.setattr(voice, '_whisper_ultimo_uso', 0.0)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(voice.router)
    client = TestClient(app)

    r = client.post('/api/voice/prewarm')
    assert r.json() == {'estado': 'listo'}
    assert 'asegurar' not in fake.llamadas          # ya está: no re-spawnea
    assert voice._whisper_ultimo_uso != 0.0


def test_descargar_ociosos_mata_worker(monkeypatch):
    monkeypatch.setenv('WHISPER_IDLE_UNLOAD', '600')
    fake = _FakeWorkerListo()
    monkeypatch.setattr(voice, '_worker_stt', fake)
    monkeypatch.setattr(voice, '_whisper_model', None)
    # "Hace una eternidad" RELATIVO al reloj monotónico, no 0.0: monotonic()
    # cuenta desde que arrancó la máquina, así que en un runner de CI recién
    # booteado 0.0 es "hace 30 segundos" y el test no probaba nada. En la
    # máquina de desarrollo, con días de uptime, pasaba de casualidad.
    monkeypatch.setattr(voice, '_whisper_ultimo_uso', time.monotonic() - 100_000)
    asyncio.run(voice._descargar_ociosos())
    assert 'terminar' in fake.llamadas


def test_descargar_ociosos_respeta_uso_reciente(monkeypatch):
    import time
    monkeypatch.setenv('WHISPER_IDLE_UNLOAD', '600')
    fake = _FakeWorkerListo()
    monkeypatch.setattr(voice, '_worker_stt', fake)
    monkeypatch.setattr(voice, '_whisper_model', None)
    monkeypatch.setattr(voice, '_whisper_ultimo_uso', time.monotonic())
    asyncio.run(voice._descargar_ociosos())
    assert 'terminar' not in fake.llamadas


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-q']))


def test_el_worker_arranca_en_windows_sin_os_nice(monkeypatch):
    """REGRESIÓN (2026-07-27): `os.nice` NO existe en Windows.

    `main()` lo llamaba dentro de un `except OSError`, que NO atrapa
    AttributeError — así que el worker de voz moría al arrancar en Windows, con
    el traceback perdido en motor.log. Es una prioridad best-effort: nunca puede
    ser el motivo de que el proceso no arranque.
    """
    import os as _os
    from plotspace.core import stt_proc

    monkeypatch.delattr(_os, 'nice', raising=False)
    # Que main() no llegue a bloquearse leyendo stdin: alcanza con verificar que
    # el ajuste de prioridad no levante.
    assert not hasattr(_os, 'nice')
    fuente = open(stt_proc.__file__, encoding='utf-8').read()
    assert "hasattr(os, 'nice')" in fuente, 'el guard de Windows desapareció'
